#!/usr/bin/env python3
"""Departure against arrival, interface by interface (owner §14 priority-4).

The numbers this produces -- the cap explaining 100.00% of the ice mass residual,
binding at 39 of 255 interfaces, and the main chain's created/predicted ratio of
1.0000 -- were computed ad hoc and published from a document. There was no tool,
so nothing could recompute them and nothing could be digested into a bundle.

## The pairing

`G33F CAPIN` gives, for a cell at stream level `k`, its OWN outflow beside the
inflow it received from above. `G33F TOPOUT` gives the top cell's removal, which
CAPIN cannot: the top cell is updated outside the interior loop, so without it the
topmost interface is invisible.

For the interface between level `j-1` (above) and `j` (below):

    departure = own(j-1)      TOPOUT when j-1 == 0, else CAPIN's own
    arrival   = inflow(j)     CAPIN's inflow at j

Both are mixing ratios in their own cell's units -- the kernel adds `dq(i,k+1)`
straight into `qrs(i,k)` -- so under the column measure they weigh differently:

    delta = rho(j)*delz(j)*arrival - rho(j-1)*delz(j-1)*departure

which is signed the way the closure residual is: negative where the interface
destroys. The cap BINDS at an interface when departure != arrival, and that
difference is the P0-4b post-update-reservoir gap: `dq(i,k+1)` is written twice,
capped against the cell above PRE-update as its outflow and POST-update as the
inflow below.

For NUMBER the same pairing gives what the interface CREATES, which is compared
against the rho*dz-vs-dz prediction

    sum over interfaces of (rho(j) - rho(j-1)) * delz(j-1) * departure_n

on the same interfaces. Where the cap does not bind, the two must agree.

    python g33_cap_interface.py <driver---nflux> <nsplit> [out.json]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import g33_matched_closure as mc  # noqa: E402
import g33_number_transport as nt  # noqa: E402
import g33_refine_analyze as ra  # noqa: E402
import g33_probe_read as pr  # noqa: E402


class Interface(NamedTuple):
    """One interface, one chain, one sub-step, with the column measure applied.

    `mass_term` is signed the way the closure residual is: NEGATIVE where the
    interface destroys. The cap BINDS where departure differs from arrival --
    the P0-4b post-update-reservoir gap, `dq(i,k+1)` written twice.
    """
    chain: str
    col: int
    call: int              # 1-based external kernel call
    loop: int
    substep: int
    k_up: int              # departure level
    k_lo: int              # arrival level
    t_up: float            # THIS call's pre-sed temperature at k_up ...
    t_lo: float            # ... and at k_lo
    mass_term: float       # w_lo*dq_in - w_up*dq_out
    number_created: float  # the same, for number
    number_predicted: float  # what the measure mismatch alone predicts
    number_out: float      # number leaving the upper cell, column measure
    mass_differs: bool
    number_differs: bool


def _walk(stream: str, basis: str):
    """Every interface in the stream, once.

    `interfaces()` sums these and `cap_sink()` keeps them apart; both used to
    carry their own copy of this nested loop.

    Requires `capin` and `topout`; the strict parser has already checked their
    exact universes, so a level or sub-step missing here is not possible.
    """
    measure = mc.window_cell_mass(stream, basis)
    for ci, call in enumerate(nt.calls(stream), start=1):
        for lp in sorted(call["loops"]):
            pre = call["outer_pre_sed"]
            for col in sorted({c for l, c, _ in pre if l == lp}):
                ks = sorted(k for l, c, k in pre if c == col and l == lp)
                cm = {k: mc.measure_at(measure, (col, k), "_walk") for k in ks}
                rho = {k: c.density for k, c in cm.items()}
                dz = {k: c.delz for k, c in cm.items()}
                # THIS call's own pre-sed temperature. The window-initial one is
                # a different quantity: on column 3 it is 1.77 K away by call 12,
                # worth ~21 J/m2 against a 28 J/m2 correction (owner §16-4 P0-1).
                # `.get`: the MASS analysis does not need a temperature, and
                # `t` is not in STAGE_REQUIRED, so a stream without it still
                # yields interfaces. The enthalpy path refuses on `None`
                # instead -- failing where the value is actually required.
                t = {k: pre[(lp, col, k)].get("t") for k in ks}
                for chain in ("main", "ice"):
                    ms = call["mstep"].get((lp, chain, col))
                    if ms is None:
                        continue
                    for n in range(1, ms + 1):
                        # TOPOUT gives the top cell's removal, which CAPIN cannot:
                        # that cell is updated outside the interior loop.
                        top = call["topout"].get((lp, n, col, chain, 0))
                        if top is None:
                            continue
                        own, inflow = {0: top}, {}
                        for j in ks[1:]:
                            cap = call["capin"].get((lp, n, col, chain, j))
                            if cap is None:
                                continue
                            oq, iq, on, ino = cap
                            own[j], inflow[j] = (oq, on), (iq, ino)
                        for j in ks[1:]:
                            if j not in inflow or (j - 1) not in own:
                                continue
                            dq_out, dn_out = own[j - 1]
                            dq_in, dn_in = inflow[j]
                            w_up, w_lo = rho[j - 1] * dz[j - 1], rho[j] * dz[j]
                            yield Interface(
                                chain, col, ci, lp, n, j - 1, j,
                                t[j - 1], t[j],
                                w_lo * dq_in - w_up * dq_out,
                                w_lo * dn_in - w_up * dn_out,
                                (rho[j] - rho[j - 1]) * dz[j - 1] * dn_out,
                                w_up * dn_out,
                                dq_out != dq_in, dn_out != dn_in)


def _totals() -> dict:
    """A column's running interface totals.

    NET is what the closure residual compares to; GROSS and MAX say how much
    interface activity produced it, because a column whose positive and negative
    terms cancel has a small net and is not quiet (owner P1-11.2).

    The two `differ` counts are NAMED for what they compare (owner §10). One
    `cap_bound` count silently meant the MASS cap only. Every count is reported
    beside its magnitude, because exact inequality makes a roundoff-scale
    difference and a residual-dominating one the same event.

    `number_transported` is the throughput the residual should be compared
    against (owner §11); R/F uses the surface transfer alone.
    """
    return {"mass_interface_term": 0.0, "sum_abs_interface_term": 0.0,
            "max_abs_interface_term": 0.0, "number_created": 0.0,
            "number_predicted": 0.0, "number_transported": 0.0,
            "interfaces": 0, "mass_departure_arrival_differ": 0,
            "number_departure_arrival_differ": 0, "either_differ": 0}


def interfaces(stream: str, basis: str = "operator") -> dict:
    """{(chain, col): totals} -- the interface terms, and how often the cap bound."""
    acc = {}
    for f in _walk(stream, basis):
        d = acc.setdefault((f.chain, f.col), _totals())
        d["mass_interface_term"] += f.mass_term
        d["sum_abs_interface_term"] += abs(f.mass_term)
        d["max_abs_interface_term"] = max(d["max_abs_interface_term"],
                                          abs(f.mass_term))
        d["number_created"] += f.number_created
        d["number_predicted"] += f.number_predicted
        d["number_transported"] += abs(f.number_out)
        d["interfaces"] += 1
        d["mass_departure_arrival_differ"] += int(f.mass_differs)
        d["number_departure_arrival_differ"] += int(f.number_differs)
        d["either_differ"] += int(f.mass_differs or f.number_differs)
    return acc


#: chain -> the phase of the water it moves, from the kernel array each CAPIN
#: site reads. `main` is anchored on `qrs(i,k,1) = ... dqr ...` (F:1225), which is
#: RAIN; `ice` on `qci(i,k,2) = ... dqi ...` (F:1289), which is CLOUD ICE. So the
#: phase of a cap sink is not inferred from a surface diagnostic -- it is the site.
CHAIN_PHASE = {"main": "liquid", "ice": "ice"}

#: The kernel caps FOUR species: dqr (F:1225), dqs (F:1237), dqg (F:1243) and dqi
#: (F:1289). Only the first and last carry a CAPIN anchor, so a sink measured here
#: is a LOWER BOUND on the column's internal destruction. Snow and graupel are
#: present on this fixture, so the shortfall is real rather than hypothetical.
INSTRUMENTED_SPECIES = ("qr", "qi")
UNINSTRUMENTED_SPECIES = ("qs", "qg")


class Sink(NamedTuple):
    """One interface's internal mass defect, at the call where it happened.

    `signed` is the interface term negated. It is a SIGNED DEFECT, not a sink:
    an interface with `mass_term > 0` yields a negative value here. Energy
    accounting takes the signed number -- both directions have to be charged for
    the ledger to close -- while the physical sentence "the cap destroyed X"
    takes `destroyed` only (owner §16-4 P1-1).
    """
    col: int
    k_up: int
    k_lo: int
    signed: float
    phase: str
    t_up: float
    t_lo: float

    @property
    def destroyed(self) -> float:
        return max(self.signed, 0.0)

    @property
    def created(self) -> float:
        return max(-self.signed, 0.0)


def cap_sink(stream: str, basis: str = "operator") -> dict:
    """{col: [Sink, ...]} -- the internal mass defect, interface by interface.

    This is the direct measurement of what `outflow_split()` can only infer.
    That computes `D_internal = water_out - P_bottom` from the fallout
    DIAGNOSTIC and returns a NEGATIVE internal destruction in all three columns
    -- impossible for a cap, which only destroys (owner §16-4).
    """
    out = {}
    for f in _walk(stream, basis):
        if f.mass_term:
            out.setdefault(f.col, []).append(
                Sink(f.col, f.k_up, f.k_lo, -f.mass_term,
                     CHAIN_PHASE[f.chain], f.t_up, f.t_lo))
    return out


def enthalpy_with_cap_sink(stream: str, basis: str = "operator") -> dict:
    """The moist-enthalpy ledger with the internal cap sink charged where it died.

    BOTH ledgers, side by side. Publishing only the corrected one would replace
    every previously-quoted residual with no way to see what moved; publishing
    only the old one would leave the correction opt-in and never exercised.
    """
    # Whichever family carries the window: an f64 build emits no G33R
    # and the probe stream holds the same values (owner D6 follow-on).
    try:
        run = pr.window_state(stream)
    except pr.ProbeError as e:
        # `ra.read_text` raised RefineError here before, and the type is part
        # of what a caller sees (Codex).
        raise ra.RefineError(str(e)) from e
    if not run:
        return {}
    sink = cap_sink(stream, basis)
    split, surface = ra.enthalpy_ledger(run, basis, sink), ra.enthalpy_ledger(run, basis)
    for col, d in split.items():
        rows = sink.get(col, [])
        # SIGNED for accounting, GROSS for the physical sentence (owner P1-1).
        d["net_signed_internal_defect"] = sum(s.signed for s in rows)
        d["gross_destroyed_mass"] = sum(s.destroyed for s in rows)
        d["gross_created_mass"] = sum(s.created for s in rows)
        d["cap_sink_share_of_column_loss"] = (
            d["gross_destroyed_mass"] / d["water_out"] if d["water_out"] else None)
        # A numerical annihilation has no single true location, so the level it
        # is charged at is a BAND, not a point (owner P0-1).
        dep = ra._sink_enthalpy(rows)
        arr = ra._sink_enthalpy(rows, arrival=True)
        d["H_sink_at_departure_temperature"] = dep
        d["H_sink_at_arrival_temperature"] = arr
        d["H_sink_temperature_band"] = abs(dep - arr)
        # How much of what the ledger called "precipitation out" never
        # precipitated -- the difference between the two charges.
        d["H_internal_cap_correction"] = (d["H_precip_out"]
                                          - surface[col]["H_precip_out"])
        # Only dqr and dqi carry a CAPIN anchor (see UNINSTRUMENTED_SPECIES).
        d["cap_sink_is_lower_bound"] = True
    return {"with_internal_cap_sink": split,
            "all_charged_at_surface": surface,
            "instrumented_species": list(INSTRUMENTED_SPECIES),
            "uninstrumented_species": list(UNINSTRUMENTED_SPECIES),
            "note": "The sink is a LOWER BOUND: the kernel caps dqr/dqs/dqg/dqi "
                    "and only dqr (F:1225) and dqi (F:1289) carry a CAPIN "
                    "anchor. Snow and graupel sedimentation caps (F:1237, "
                    "F:1243) are not instrumented."}


def analysis(stream: str) -> dict:
    """The interface table beside the matched closure it is meant to explain."""
    closure, iface = mc.analysis(stream), interfaces(stream)
    rows = {}
    for (chain, col), d in sorted(iface.items()):
        mass = closure.get(f"{chain}/{mc.CHAIN[chain][0]}/{col}")
        resid = mass["residual"] if mass else None
        rows[f"{chain}/{col}"] = {
            **d,
            "mass_residual": resid,
            # How much of the closure's mass residual the interface term is.
            # `null` rather than a division when there is no residual to explain.
            "explained": (d["mass_interface_term"] / resid
                          if resid not in (None, 0.0) else None),
            "created_over_predicted": (d["number_created"] / d["number_predicted"]
                                       if d["number_predicted"] else None),
        }
    # Split BY CHAIN, and beside the magnitude. A bare count said "39 of 255,
    # all in the ice chain"; the main chain in fact differs at 23 interfaces too,
    # but for a total interface term of 2.7e-11 against ice's 8.6e-03. Counting
    # without the magnitude made a roundoff-scale difference and a
    # residual-dominating one the same event.
    by_chain = {}
    for (chain, col), d in iface.items():
        c = by_chain.setdefault(chain, {
            "mass_departure_arrival_differ": 0,
            "number_departure_arrival_differ": 0, "either_differ": 0,
            "interfaces": 0, "net_interface_term": 0.0,
            "sum_abs_interface_term": 0.0, "max_abs_interface_term": 0.0})
        for k in ("mass_departure_arrival_differ",
                  "number_departure_arrival_differ", "either_differ",
                  "interfaces"):
            c[k] += d[k]
        # abs(net-per-column) UNDERSTATES activity when terms cancel inside a
        # column; the gross sum is accumulated per interface instead.
        c["net_interface_term"] += d["mass_interface_term"]
        c["sum_abs_interface_term"] += d["sum_abs_interface_term"]
        c["max_abs_interface_term"] = max(c["max_abs_interface_term"],
                                          d["max_abs_interface_term"])
    return {"rows": rows, "by_chain": by_chain,
            "mass_departure_arrival_differ":
                sum(d["mass_departure_arrival_differ"] for d in iface.values()),
            "number_departure_arrival_differ":
                sum(d["number_departure_arrival_differ"] for d in iface.values()),
            "either_differ": sum(d["either_differ"] for d in iface.values()),
            "total_interfaces": sum(d["interfaces"] for d in iface.values())}


def report(stream: str) -> None:
    a = analysis(stream)
    print("  Departure vs arrival, per interface. The cap binds where they differ.\n")
    print(f"  {'row':10} {'mass residual':>14} {'interface term':>15} "
          f"{'explained':>10} {'created/predicted':>18} {'cap':>8}")
    for k, r in a["rows"].items():
        ex = f"{100*r['explained']:.2f}%" if r["explained"] is not None else "-"
        cp = f"{r['created_over_predicted']:.4f}" \
            if r["created_over_predicted"] is not None else "-"
        print(f"  {k:10} {r['mass_residual']:14.6e} {r['mass_interface_term']:15.6e} "
              f"{ex:>10} {cp:>18} "
              f"{r['mass_departure_arrival_differ']:3}m/"
              f"{r['number_departure_arrival_differ']:<3}n")
    print(f"\n  Departure differs from arrival, of {a['total_interfaces']} "
          f"interfaces: mass at {a['mass_departure_arrival_differ']}, number at "
          f"{a['number_departure_arrival_differ']},")
    print(f"  either at {a['either_differ']}. A single 'cap-bound' count "
          f"conflated the mass cap")
    print("  with the number one, and a count alone conflates a roundoff-scale")
    print("  difference with a residual-dominating one:")
    for ch, c in sorted(a["by_chain"].items()):
        print(f"    {ch:5} mass {c['mass_departure_arrival_differ']:3} / number "
              f"{c['number_departure_arrival_differ']:3} of "
              f"{c['interfaces']:<4} net {c['net_interface_term']:+.3e} "
              f"gross {c['sum_abs_interface_term']:.3e} "
              f"max {c['max_abs_interface_term']:.3e}")


def main(argv) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__)
        return 2
    r = subprocess.run([argv[0], argv[1], "rezero"], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"driver exited {r.returncode}\n{r.stderr[-2000:]}")
    report(r.stdout)
    if len(argv) == 3:
        Path(argv[2]).write_text(
            json.dumps(analysis(r.stdout), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
