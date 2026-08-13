#!/usr/bin/env python3
"""Matched mass/number closure on ONE chain, ONE call set (owner §5.2).

The earlier closure compared `qr` on the MAIN chain over 1-3 calls against `ni`
on the ICE chain over 95, using the UNCAPPED `fall`/`falln` accumulators, and
excluded any call where a cap bound -- detected by an endpoint recursion that
only works at `mstep == 1`. It supported the defect but was not a controlled
contrast.

The overlay now emits the ACTUAL capped bottom-cell transfers per sub-step,

    G33F XFER <loop> <n> <col> <main|ice> f32 <dq> <dn>

from the same statement pair the kernel uses, so for each chain:

    R_q = [W(post) - W(pre)] + sum_n den_bot*delz_bot*dq
    R_n = [N(post) - N(pre)] + sum_n den_bot*delz_bot*dn

are formed on the SAME call, the SAME chain, and the SAME cap state -- and
`mstep > 1` is admissible, because nothing is reconstructed.

`main` carries qr/nr, `ice` carries qi/ni (F:1179-1180).
"""
from __future__ import annotations

import re
import struct
from typing import NamedTuple
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import g33_number_transport as nt  # noqa: E402
import g33_refine_analyze as ra  # noqa: E402
import g33_probe_read as pr  # noqa: E402

def endpoints(d: dict) -> dict:
    """The window's true first and last inventory, distinguished from the sums.

    `start`/`final` accumulate x0 and x1 over every call, so they are
    sum_i N_i^pre and sum_i N_i^post -- an inventory counted once per call, not
    the inventory the column began and ended with. Dividing a cumulative residual
    by them yields an inventory-weighted per-call mean, which is a real
    statistic and is not what "of the initial column" means (owner P0-2).
    """
    pcs = sorted(d.get("per_call") or [], key=lambda p: p.get("call", 0))
    return {
        # NAMED for what they are (owner §16-3). These are SEDIMENTATION SEGMENT
        # endpoints -- the first call's pre-sed column and the last call's
        # post-sed column -- not the window's. Other microphysics runs before the
        # first sedimentation and after the last, so they are not equal in
        # general. `window_inventories()` reads the actual window endpoints from
        # the G33R INITIAL/STATE records in the same stream.
        "first_segment_pre_inventory": pcs[0]["start"] if pcs else None,
        "last_segment_post_inventory": pcs[-1]["final"] if pcs else None,
        "sum_start": d.get("start"), "sum_final": d.get("final"),
        "calls": len(pcs)}


def window_inventories(stream: str, basis: str = "operator",
                       nsplit: int | None = None) -> dict:
    """{(field, col): (window_initial, window_final)} from G33R INITIAL/STATE.

    The true endpoints of the microphysics window, read from the SAME stream the
    segment endpoints come from -- so "is the segment endpoint the window
    endpoint" is a measurement rather than an assumption (owner §16-3).

    BASIS-CONSISTENT (owner P1-2). This used raw `rho_m*dz` whatever basis the
    caller was working in, so `physical` mode divided a dry-air residual by a
    MOIST-air inventory. Under `physical` the dry-air layer mass is held at its
    WINDOW-INITIAL value for both endpoints: dry air does not leave the column
    during microphysics, so recomputing it from each endpoint's own qv would
    make a conserved quantity move.

    Returns `{}` ONLY when the stream carries no G33R records at all. A stream
    that HAS them and fails to parse RAISES -- that is evidence corruption, and
    swallowing it would report a corrupt member as one that merely lacked
    endpoints (owner P1-3).
    """
    if "G33R BEGIN" not in stream:
        return {}
    run = ra.read_text(stream, nsplit=nsplit)

    def layer_mass(col, k):
        rho = run[("forcing", "rho", col, k)] * run[("forcing", "delz", col, k)]
        if basis == "physical":
            return rho / (1.0 + run[("initial", "qv", col, k)])
        return rho

    cols = sorted({k[2] for k in run if k[0] == "state"})
    out = {}
    for field in ("nr", "ni", "qr", "qi"):
        for col in cols:
            ks = sorted(k[3] for k in run
                        if k[0] == "state" and k[1] == field and k[2] == col)
            if ks:
                out[(field, col)] = tuple(
                    sum(layer_mass(col, k) * run[(cls, field, col, k)] for k in ks)
                    for cls in ("initial", "state"))
    return out


#: chain -> (mass field, number field) as the kernel's two sub-cycles carry them.
CHAIN = {"main": ("qr", "nr"), "ice": ("qi", "ni")}


def _f32(h: str) -> float:
    return struct.unpack(">f", bytes.fromhex(h))[0]


def transfers(stream: str) -> dict:
    """{(call_index, loop, col, chain): (sum dq, sum dn)} over the sub-steps.

    Read from the STRICT parser's `xfer` store, not a private regex (owner
    P0-E1): that store refuses duplicates, rejects records outside a call, and
    checks the sub-step universe against `mstep`, so a missing record cannot
    shrink a flux here and a duplicate cannot double it.
    """
    out = {}
    for i, call in enumerate(nt.calls(stream), start=1):
        for (lp, _n, col, chain), (dq, dn) in call["xfer"].items():
            k = (i, lp, col, chain)
            a, b = out.get(k, (0.0, 0.0))
            out[k] = (a + dq, b + dn)
    return out


#: The two column measures (owner §9). `den` passed to the kernel is MOIST-air
#: density (rho_m = rho_d(1+qv)), while `nr` and the `q` fields are mixing ratios
#: per DRY-air kg -- so the physically conserved column integral uses rho_d and
#: the operator's own integral uses rho_m. Reporting only one of them makes a
#: statement about the operator read as a statement about the atmosphere.
MEASURES = ("operator", "physical")


def _density(rec: dict, basis: str) -> float:
    if basis == "operator":
        return rec["rho"]
    return rec["rho"] / (1.0 + rec["qv"])


class CellMeasure(NamedTuple):
    """One layer's IMMUTABLE measure for the whole microphysics window.

    `mass` is the conserved quantity. `density` and `delz` are kept beside it
    because the interface analysis needs a density DIFFERENCE,
    `(rho_lo - rho_up) * dz_up`, which a mass alone cannot express.
    """
    density: float
    delz: float
    mass: float


def window_cell_mass(stream: str, basis: str) -> dict:
    """{(col, k): CellMeasure} -- one measure, fixed for the whole window.

    Three corrections over the first version, all owner P0-1:

    * `rho` and `delz` come from the UNION of every call's pre-sed records, not
      from the FIRST call. Under a multi-tile decomposition the first call
      covers only the first tile, so keying on it made a legitimate `(2,1)` run
      raise "no window measure for cell 3". They are FORCING -- verified here to
      be identical in every call that carries them, rather than assumed.
    * `qv` for the physical basis comes from `G33R INITIAL`, the window's true
      start. The first sedimentation call's pre-sed `qv` is a SEGMENT quantity:
      other microphysics runs before it. This repository established exactly
      that distinction for the number inventory (§16-3), and the first version
      of this function regressed it.
    * The measure is a LAYER MASS, `rho * dz`, frozen together. Freezing only
      the density and multiplying by each call's own `delz` would let the
      measure move with `delz`.

    Keyed `(col, k)`: a layer mass is not a property of a loop or a tile.
    """
    forcing = {}
    for call in nt.calls(stream):
        for (_lp, col, k), rec in call["outer_pre_sed"].items():
            prev = forcing.get((col, k))
            if prev is not None and prev != (rec["rho"], rec["delz"]):
                raise ValueError(
                    f"cell ({col},{k}): rho/delz differ between calls -- {prev} "
                    f"then {(rec['rho'], rec['delz'])}. They are forcing; a "
                    f"measure built on them cannot be fixed for the window.")
            forcing[(col, k)] = (rec["rho"], rec["delz"])

    qv0 = {}
    if basis != "operator":
        # G33R INITIAL, or G33P INITIAL when the build emitted no G33R --
        # the same values in a different encoding (owner D6 follow-on).
        try:
            run = pr.window_state(stream)
        except pr.ProbeError as e:
            # This function has refused a windowless stream with ValueError
            # since it existed, and callers catch that. The SELECTION rule
            # stays in one place; only the type is restored at the boundary,
            # because changing an exception type silently is a break nothing
            # downstream would report (Codex).
            raise ValueError(str(e)) from e
        # `run` also holds 3-tuple `prec` and `meta` keys, so the shape is
        # checked before unpacking rather than after it raises.
        qv0 = {(key[2], key[3]): v for key, v in run.items()
               if len(key) == 4 and key[0] == "initial" and key[1] == "qv"}

    out = {}
    for (col, k), (rho, dz) in forcing.items():
        if basis == "operator":
            den = rho
        elif (col, k) in qv0:
            den = rho / (1.0 + qv0[(col, k)])
        else:
            raise ValueError(f"cell ({col},{k}): no G33R INITIAL qv, so its "
                             f"window-initial dry-air mass is unknown")
        out[(col, k)] = CellMeasure(den, dz, den * dz)
    return out


def measure_at(measure: dict, key, label: str) -> CellMeasure:
    """The window measure for one cell, or a refusal.

    Falling back to the call's own density would silently restore the moving
    weight for exactly the cells the window measure does not cover.
    """
    if key not in measure:
        raise ValueError(f"{label}: no window measure for cell {key}")
    return measure[key]


def closures(stream: str, basis: str = "operator") -> dict:
    """{(chain, species, col): {'out':…, 'residual':…, 'calls':…}}."""
    if basis not in MEASURES:
        raise ValueError(f"basis must be one of {MEASURES}, got {basis!r}")
    xf = transfers(stream)
    measure = window_cell_mass(stream, basis)
    acc = {}
    for i, call in enumerate(nt.calls(stream), start=1):
        for lp in sorted(call["loops"]):
            pre, post = call["outer_pre_sed"], call["outer_post_sed"]
            for col in sorted({c for l, c, _ in pre if l == lp}):
                ks = sorted(k for l, c, k in pre if c == col and l == lp)
                cm = [measure_at(measure, (col, k), "closures") for k in ks]
                w = cm[-1].mass                 # bottom-cell layer mass
                for chain, (mass, num) in CHAIN.items():
                    if (i, lp, col, chain) not in xf:
                        continue
                    dq, dn = xf[(i, lp, col, chain)]
                    for species, transfer in ((mass, dq), (num, dn)):
                        x0 = sum(cm[t].mass * pre[(lp, col, ks[t])][species]
                                 for t in range(len(ks)))
                        x1 = sum(cm[t].mass * post[(lp, col, ks[t])][species]
                                 for t in range(len(ks)))
                        d = acc.setdefault((chain, species, col),
                                           {"out": 0.0, "residual": 0.0,
                                            "start": 0.0, "final": 0.0,
                                            "transported": 0.0, "calls": 0,
                                            "per_call": []})
                        r = (x1 - x0) + w * transfer
                        d["out"] += w * transfer
                        d["residual"] += r
                        d["start"] += x0
                        # The endpoints and the throughput, so the residual can be
                        # normalised by something other than the surface flux
                        # (owner §11): R/F is NOT "the column gained 9-15%".
                        d["final"] += x1
                        d["transported"] += abs(w * transfer)
                        d["calls"] += 1
                        # PER CALL, because the aggregate hides cancellation:
                        # +1e-3 on one call and -1e-3 on the next summed to a
                        # residual of zero and the control passed while BOTH
                        # calls' accounting had failed (owner §6.3).
                        #
                        # Each call carries its own scale and operation count.
                        # The scale is |X0|+|X1|+|F| rather than |F| alone: a
                        # forward-error bound depends on the magnitudes that
                        # entered the sum, and a near-cancelling budget can have
                        # |F| far smaller than the terms that produced it
                        # (owner §6.2). The count is cells x (sub-steps + the two
                        # column sums) rather than a flat 8, so `mstep` and `K`
                        # actually appear in it (owner §6.1).
                        ms = call["mstep"][(lp, chain, col)]
                        d["per_call"].append({
                            "call": i, "residual": r, "out": w * transfer,
                            # The endpoints of THIS call. Summing them across
                            # calls gives sum_i N_i, which is NOT the window's
                            # initial or final inventory -- calls run in
                            # sequence, so N_2^pre is roughly N_1^post, and the
                            # sum counts the column once per call (owner P0-2).
                            "start": x0, "final": x1,
                            "scale": abs(x0) + abs(x1) + abs(w * transfer),
                            "ops": len(ks) * (ms + 2)})
    return acc


#: A mass control closes when its residual is within the floating-point error a
#: chain of this length can accumulate, not within a round number. gamma_n is the
#: textbook form for n sequential f32 operations.
#:
#: NOT A CERTIFICATE (owner §6). This is a SCREENING threshold, and calling it a
#: proof of roundoff would be overclaiming. The operation count is a floor -- it
#: counts the cells, the sub-steps and the two column sums, but not each update's
#: individual multiply/divide/add, the cap re-evaluations, or state accumulated
#: across calls -- and gamma_n itself assumes a straight-line summation that the
#: capped, branching kernel is not. What it is good for is exactly what it is
#: used for: refusing rows whose accounting is visibly missing a term.
_F32_EPS = 2.0 ** -24


def control_tolerance(n_ops: int, scale: float) -> float:
    g = n_ops * _F32_EPS / (1 - n_ops * _F32_EPS) if n_ops * _F32_EPS < 1 else 1.0
    return g * scale


def control(d: dict) -> dict:
    """Net, gross and worst-per-call residual, each against its own threshold.

    The aggregate alone allowed cancellation, so `max_ratio` -- the worst single
    call measured against that call's own threshold -- is the binding one. Net
    and gross are reported because they say different things: net is what a
    reader who only saw the total would have seen, and gross is how much
    accounting error was present regardless of sign.
    """
    # A row assembled by hand (a test, or a caller building one row) has no
    # per-call breakdown; it is then its own single call.
    pcs = d.get("per_call") or [{"residual": d["residual"],
                                 "scale": abs(d["out"]),
                                 "ops": max(d["calls"], 1) * 8}]
    worst = max((abs(p["residual"]) / t if (t := control_tolerance(
        p["ops"], p["scale"])) else float("inf") if p["residual"] else 0.0)
        for p in pcs)
    return {"net": sum(p["residual"] for p in pcs),
            "gross": sum(abs(p["residual"]) for p in pcs),
            "max_abs": max(abs(p["residual"]) for p in pcs),
            "max_ratio": worst,
            "tolerance_basis": "gamma_n screening threshold, not a proven bound"}


def usable(d: dict) -> tuple[bool, str]:
    """Is this chain's row evidence? EVERY call's mass residual must be within
    that call's own threshold -- one bad call disqualifies the row even if the
    others cancel it out."""
    c = control(d)
    if c["max_ratio"] <= 1.0:
        return True, ""
    return False, (f"matched_mass_control_failed: worst call is "
                   f"{c['max_ratio']:.3g}x its gamma_n screening threshold "
                   f"(net={c['net']:.3e}, gross={c['gross']:.3e})")


def report(stream: str) -> None:
    acc = closures(stream)
    print("  MATCHED closure — same chain, same calls, actual capped transfers")
    print("  mstep is NOT restricted: nothing is reconstructed from endpoints.\n")
    print(f"  {'chain':>5} {'sp':>3} {'col':>3} {'calls':>6} {'surface out':>14} "
          f"{'residual':>14} {'resid/out':>11}")
    for (chain, sp, col), d in sorted(acc.items()):
        if d["out"] == 0:
            continue
        print(f"  {chain:>5} {sp:>3} {col:>3} {d['calls']:>6} {d['out']:14.5e} "
              f"{d['residual']:14.5e} {d['residual']/d['out']:10.4%}")
    print("\n  A matched pair is the two rows sharing a chain and a column:")
    print("  the mass row is the CONTROL for the number row beside it. If the mass")
    print("  row does not close, the accounting for that chain is missing a term")
    print("  and NEITHER row of the pair is evidence.")
    for (chain, sp, col), d in sorted(acc.items()):
        if not sp.startswith("q") or not d["out"]:
            continue
        ok, why = usable(d)
        if not ok:
            print(f"    !! {chain}/{sp} col {col}: {why} — the {chain} col {col} "
                  f"rows are NOT usable")


def analysis(stream: str, basis: str = "operator") -> dict:
    """The table as JSON, with unusable rows carrying `number_result: null`.

    A warning printed under a table gets separated from it the moment someone
    copies the table (owner §6.2). Here the exclusion is structural.
    """
    acc = closures(stream, basis)
    ctrl = {(ch, col): usable(d) for (ch, sp, col), d in acc.items()
            if sp.startswith("q")}
    out = {}
    for (ch, sp, col), d in sorted(acc.items()):
        ok, why = ctrl.get((ch, col), (False, "no_mass_control_for_this_chain"))
        out[f"{ch}/{sp}/{col}"] = {
            "calls": d["calls"], "surface_out": d["out"],
            "residual": d["residual"], "usable": ok,
            "reason": why or None,
            # Recorded so a reader can see cancellation rather than infer it
            # from a total that hides it (owner §14 priority-3).
            "control": control(d),
            "number_result": (d["residual"] / d["out"]
                              if ok and d["out"] and not sp.startswith("q")
                              else None),
        }
    return out


def main(argv) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__)
        print("usage: g33_matched_closure.py <driver---nflux> <nsplit> "
              "[analysis.json]")
        return 2
    r = subprocess.run([argv[0], argv[1], "rezero"], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"driver exited {r.returncode}\n{r.stderr[-2000:]}")
    report(r.stdout)
    if len(argv) == 3:
        # The table and the JSON come from ONE call, so a quoted number and a
        # digested artifact cannot disagree.
        import json
        Path(argv[2]).write_text(json.dumps(
            {"nsplit": int(argv[1]), "rows": analysis(r.stdout)},
            indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
