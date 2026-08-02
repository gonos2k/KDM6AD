#!/usr/bin/env python3
"""Convergence and energy budgets of one operator under timestep refinement.

Reads `G33R` streams from the refinement drivers and reports, per member:
successive-difference orders, rho*dz column budgets, branch topology, and the two
energy ledgers of owner review §8.

Two rules a reader must know, because breaking either silently produces a number
that looks like a result:

  * SWEEPS ARE DESIGNED ON dtcld, NOT delt. The kernel picks its own internal step
    (F:930-932), so N = 1,2,3,6,12 gives dtcld = 100,150,100,50,25 -- not a
    refinement sequence. N in {3,6,12,24,48,96} halves cleanly.
  * ORDERS COME ONLY FROM SUCCESSIVE DIFFERENCES. Against the finest member the
    exponent is biased upward: a first-order operator reads +1.222 then +1.585.

Both are derived, measured and argued in harness/evidence/
FINDING_refinement_design_v1.md; the ledger results are in
FINDING_moist_enthalpy_ledger_v1.md. This module does not restate them.
"""
from __future__ import annotations

import math
import re
import struct
import sys
from pathlib import Path

_STATE = re.compile(r"^G33R (STATE|INITIAL)\s+(\S+)\s+(\d+)\s+(-?\d+)\s+([0-9A-Fa-f]{8})$")
_PREC = re.compile(r"^G33R PREC\s+(\d+)\s+(\d+)\s+([0-9A-Fa-f]{8})$")
_FORCING = re.compile(r"^G33R FORCING\s+(rho|delz|pii)\s+(\d+)\s+(-?\d+)\s+([0-9A-Fa-f]{8})$")

#: The water species, split by the phase the code's latent heats treat them as.
#: MASS is derived, not restated: two copies of one species list is how a species
#: gets added to only one of them.
LIQUID = ("qc", "qr")
ICE = ("qi", "qs", "qg")
MASS = ("qv",) + LIQUID + ICE

#: Reported separately from MASS. A mass field and a number moment can converge at
#: different rates, and averaging them hides exactly the number-moment behaviour
#: the conservative-nr blocker is about.
NUMBER = ("nc", "ni", "nr", "nccn")


def f32(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits))[0]


#: A member is a COMPLETE state, not "at least one record".
STATE_FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg",
                "nccn", "nc", "ni", "nr", "bg")
# `\s+`: the Fortran `merge` pads the mode to a fixed width, so the emitted
# separator is not always one space. A single-space pattern rejected every
# real member -- which is the safe direction, but for the wrong reason.
_BEGIN = re.compile(r"^G33R BEGIN nsplit\s+(\d+)\s+(carry|rezero)\s+(\S+)"
                    r"(?:\s+delt\s+(\S+)\s+loops\s+(\d+)\s+dtcld\s+(\S+))?$")
_END = re.compile(r"^G33R END$")


class RefineError(Exception):
    """A member that cannot be analysed. Never downgraded to a warning."""


def _expect(cond, msg, path):
    if not cond:
        raise RefineError(f"{path}: {msg}")


def read(path: Path, *, nsplit=None) -> dict:
    """One member, or raise.

    Every check corresponds to a way a truncated, duplicated or mislabelled stream
    would otherwise read as a valid result -- always in the flattering direction,
    since a member missing records shows a SMALLER error (§2).
    """
    lines = [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]
    begins = [ln for ln in lines if ln.startswith("G33R BEGIN")]
    ends = [ln for ln in lines if _END.match(ln)]
    _expect(len(begins) == 1, f"expected exactly 1 BEGIN, found {len(begins)}", path)
    _expect(len(ends) == 1, f"expected exactly 1 END, found {len(ends)} "
                            "(a truncated run has none)", path)
    m = _BEGIN.match(begins[0])
    _expect(m, f"unparseable BEGIN: {begins[0]!r}", path)
    got_n, mode, algo = int(m.group(1)), m.group(2), m.group(3)
    # delt/loops/dtcld are what the KERNEL actually used. Recording them makes the
    # dtcld design rule checkable from the output instead of recomputed from delt
    # by whoever reads the table (owner review §2.3).
    delt, loops, dtcld = m.group(4), m.group(5), m.group(6)
    if nsplit is not None:
        _expect(got_n == nsplit,
                f"BEGIN says nsplit={got_n}, filename says {nsplit} "
                "(a member analysed under the wrong step)", path)

    bi, ei = lines.index(begins[0]), lines.index(ends[0])
    _expect(bi < ei, "END precedes BEGIN", path)
    _expect(not [ln for ln in lines[:bi] + lines[ei + 1:] if ln.startswith("G33R")],
            "G33R records outside BEGIN..END", path)

    out, seen = {}, set()
    for ln in lines[bi + 1:ei]:
        if not ln.startswith("G33R"):
            continue                     # non-record chatter inside the block
        if m := _STATE.match(ln):
            cls, fld, i, k, b = m.groups()
            key = (cls.lower(), fld, int(i), int(k))
        elif m := _PREC.match(ln):
            f, i, b = m.groups()
            key = ("prec", int(f), int(i))
        elif m := _FORCING.match(ln):
            nm, i, k, b = m.groups()
            key = ("forcing", nm, int(i), int(k))
        else:
            raise RefineError(f"{path}: unrecognised G33R record: {ln!r}")
        _expect(key not in seen,
                f"duplicate record {key} — a second value would silently "
                "overwrite the first", path)
        seen.add(key)
        v = f32(int(b, 16))
        _expect(v == v and abs(v) != float("inf"),
                f"non-finite value at {key}", path)
        out[key] = v

    fo = [k for k in out if k[0] == "forcing"]
    init = [k for k in out if k[0] == "initial"]
    st = [k for k in out if k[0] == "state"]
    pr = [k for k in out if k[0] == "prec"]
    fields = {k[1] for k in st}
    _expect(fields == set(STATE_FIELDS),
            f"state field set is {sorted(fields)}, expected {sorted(STATE_FIELDS)}",
            path)
    cells = {(k[2], k[3]) for k in st}
    _expect(len(st) == len(STATE_FIELDS) * len(cells),
            f"state records {len(st)} != {len(STATE_FIELDS)} fields x "
            f"{len(cells)} cells — the grid is ragged", path)
    cols = {k[2] for k in pr}
    _expect(len(pr) == 3 * len(cols),
            f"prec records {len(pr)} != 3 species x {len(cols)} columns", path)
    # rho/delz are optional so streams from before they were emitted still parse,
    # but if either is present BOTH must be complete -- a half-populated forcing
    # set would silently drop columns from a physical budget.
    if fo:
        for nm in {k[1] for k in fo}:
            got = {(k[2], k[3]) for k in fo if k[1] == nm}
            _expect(got == cells,
                    f"forcing `{nm}` covers {len(got)} cells, state covers "
                    f"{len(cells)}", path)
    if init:
        _expect(len(init) == len(st),
                f"initial state has {len(init)} records, final has {len(st)}", path)
    out[("meta", "nsplit")] = got_n
    out[("meta", "mode")] = mode
    out[("meta", "algorithm")] = algo
    if loops is not None:
        out[("meta", "delt")] = float(delt)
        out[("meta", "loops")] = int(loops)
        out[("meta", "dtcld")] = float(dtcld)
    return out


def require_same_universe(runs: dict) -> None:
    """Same identities in every member, checked once up front.

    Comparing over an intersection lets an incomplete member report a smaller
    error -- convergence measured on absence.
    """
    keyed = {n: {k for k in r if k[0] != "meta"} for n, r in runs.items()}
    ref_n = min(keyed)
    for n, ks in keyed.items():
        if ks != keyed[ref_n]:
            miss, extra = keyed[ref_n] - ks, ks - keyed[ref_n]
            raise RefineError(
                f"member N={n} has a different record universe from N={ref_n}: "
                f"{len(miss)} missing, {len(extra)} extra")
    algos = {r[("meta", "algorithm")] for r in runs.values()}
    if len(algos) > 1:
        raise RefineError(f"members mix algorithms: {sorted(algos)}")


def _norm(a: dict, b: dict, keys) -> float:
    """Max absolute difference over `keys` — not RMS, which on a mostly-quiet
    synthetic fixture would measure how many cells are quiet."""
    # No `if k in a and k in b` guard: `require_same_universe` has already
    # established both carry every key, and a silent skip here is exactly how a
    # missing record turns into a smaller error norm.
    return max((abs(a[k] - b[k]) for k in keys), default=0.0)


def _keys(run, group):
    if group == "prec":
        return [k for k in run if k[0] == "prec"]
    if group == "th":
        return [k for k in run if k[0] == "state" and k[1] == "th"]
    names = MASS if group == "mass" else NUMBER
    return [k for k in run if k[0] == "state" and k[1] in names]


GROUPS = ("th", "mass", "number", "prec")

#: Physical column budgets (§7): sum_k rho_k dz_k q, per column so one bad column
#: is not diluted by the rest. The grouped max norms above are over MIXING RATIOS
#: and are set by a single migrating cell; these are what conservation is about.


def column_budgets(run: dict) -> dict:
    """{(quantity, col): rho*dz-weighted column integral}, or {} without forcing."""
    if not any(k[0] == "forcing" for k in run):
        return {}
    cells = {(k[2], k[3]) for k in run if k[0] == "state"}
    cols = sorted({c for c, _ in cells})
    out = {}
    for c in cols:
        ks = sorted(k for cc, k in cells if cc == c)
        w = {k: run[("forcing", "rho", c, k)] * run[("forcing", "delz", c, k)]
             for k in ks}
        out[("water", c)] = sum(
            w[k] * sum(run[("state", f, c, k)] for f in MASS) for k in ks)
        for n in ("nr", "ni", "nc", "nccn"):
            out[(n, c)] = sum(w[k] * run[("state", n, c, k)] for k in ks)
    return out


def _halving_pairs(runs: dict) -> list:
    """(coarse, fine) member pairs whose step actually halved."""
    return [(n, 2 * n) for n in sorted(runs) if 2 * n in runs]


def _order_table(runs: dict, title: str, head: str, rows) -> None:
    """Successive orders p = log2(E_h / E_{h/2}) for labelled series.

    `rows` yields (label, err) with `err(lo, hi)` the difference between two
    members — a max norm over cells for one caller, a column integral for the
    other, which is why the error function is the interface. A dash where either
    error is exactly zero: bit-identical members are the absence of a rate, not a
    rate of zero. All-dash rows carry no signal and are not printed.
    """
    pairs = _halving_pairs(runs)
    print(f"\n  {title}")
    print(f"    {head}" + "  ".join(f"{300/lo:g}->{150/lo:g}".rjust(13)
                                    for lo, _ in pairs[:-1]))
    for label, err in rows:
        cells = []
        for i, (lo, hi) in enumerate(pairs[:-1]):
            e, e2 = err(lo, hi), err(hi, pairs[i + 1][1])
            cells.append("      -      " if e == 0 or e2 == 0
                         else f"{math.log2(e / e2):+13.3f}")
        if any(c.strip() != "-" for c in cells):
            print(f"    {label} " + "  ".join(cells))


def budget_report(runs: dict) -> None:
    b = {n: column_budgets(runs[n]) for n in sorted(runs)}
    if not b[min(b)]:
        print("\n  column budgets: forcing not present in this stream set")
        return
    keys = sorted(b[min(b)])                       # (quantity, column)
    _order_table(
        runs, "rho*dz column budgets — successive order per column",
        f"{'quantity':10} {'col':>3} ",
        ((f"{q:10} {c:3d}",
          lambda lo, hi, q=q, c=c: abs(b[lo][(q, c)] - b[hi][(q, c)]))
         for q, c in keys))


def successive(runs: dict) -> dict:
    """E_h = |X_h - X_{h/2}| for the doubling pairs this sweep contains."""
    pairs = [(n, 2 * n) for n in sorted(runs) if 2 * n in runs]
    out = {}
    for g in GROUPS:
        row = {}
        for lo, hi in pairs:
            if lo in runs and hi in runs:
                row[300 / lo] = _norm(runs[lo], runs[hi], _keys(runs[lo], g))
        out[g] = row
    return out


def to_finest(runs: dict) -> dict:
    finest = max(runs)
    out = {}
    for g in GROUPS:
        out[g] = {300 / n: _norm(runs[n], runs[finest], _keys(runs[n], g))
                  for n in sorted(runs) if n != finest}
    return out


def orders(series: dict) -> list:
    """p = log2(E_h / E_{h/2}) for each adjacent halving present.

    Reported as None when either error is exactly zero: a zero difference means
    the two members agree to the last bit, which is not an order-0 convergence
    rate, it is an absence of the signal the rate describes.
    """
    hs = sorted(series, reverse=True)
    out = []
    for h, hh in zip(hs, hs[1:]):
        if abs(h - 2 * hh) > 1e-9:
            continue
        e, ee = series[h], series[hh]
        out.append((h, e, ee, None if e == 0 or ee == 0 else math.log2(e / ee)))
    return out


def report(runs: dict, label: str) -> None:
    print(f"\n=== {label} ===")
    print(f"    members: N = {sorted(runs)}  "
          f"(delt = {[round(300 / n, 4) for n in sorted(runs)]} s)")
    # (label, series, may_report_order). The flag is the point of this table:
    # an order from the error-to-finest series is biased upward and was misread
    # once already, so which series may carry one is fixed here rather than left
    # to the caller.
    for name, series, ordered in (
            ("successive |X_h - X_h/2|   (order estimated HERE)",
             successive(runs), True),
            (f"error to finest (N={max(runs)})   magnitude + monotonicity only",
             to_finest(runs), False)):
        print(f"\n  {name}")
        for g in GROUPS:
            s = series[g]
            if not s:
                continue
            cells = "  ".join(f"h={h:g}:{v:.6e}" for h, v in sorted(s.items(), reverse=True))
            print(f"    {g:7} {cells}")
            if ordered:
                for h, e, ee, p in orders(s):
                    pt = "n/a (a member is bit-identical)" if p is None else f"{p:+.3f}"
                    print(f"            order {h:g}->{h/2:g}: p = {pt}")
            else:
                v = [s[h] for h in sorted(s, reverse=True)]
                mono = all(a >= b for a, b in zip(v, v[1:]))
                print(f"            monotone decreasing: {mono}"
                      f"   (no order: the finest member is not the exact solution)")


def per_field(runs: dict) -> None:
    """Order per FIELD, and which cell sets each group max.

    A grouped max norm reports one field at one cell, so if that cell migrates the
    group order is partly a record of the move (§7). Both are printed so the group
    numbers can be read against the fields they actually came from.
    """
    first = runs[min(runs)]
    fields = sorted({k[1] for k in first if k[0] == "state"})
    _order_table(
        runs, "per-field successive order", f"{'field':6} ",
        ((f"{f:6}",
          lambda lo, hi, f=f: _norm(runs[lo], runs[hi],
                                    [x for x in runs[lo]
                                     if x[0] == "state" and x[1] == f]))
         for f in fields))

    print("\n  cell setting each group max (a moving cell makes the group order "
          "partly a record of the move)")
    for g in GROUPS:
        if g == "prec":
            continue
        trail = []
        for lo, hi in _halving_pairs(runs):
            _, best = max((abs(runs[lo][x] - runs[hi][x]), x)
                          for x in _keys(runs[lo], g))
            trail.append(f"{best[1]}/c{best[2]}k{best[3]}")
        print(f"    {g:7} " + " -> ".join(trail))


#: Above this a species counts as PRESENT. The kernel's own qmin; a crossing of it
#: between two members is a branch the arithmetic took differently, not a smaller
#: number.
_PRESENCE_EPS = 1.0e-12
T0C = 273.15


def topology(run: dict) -> dict:
    """Final branch state: the cold/warm mask and which species are present.

    A classical order is only meaningful within one smooth branch (§5). This is
    ONE-SIDED: a difference between members proves the topology moved; agreement
    does not prove it stayed, since an intermediate flip can heal. The per-subcycle
    masks live inside the kernel and are not recoverable here.
    """
    if not any(k[0] == "forcing" and k[1] == "pii" for k in run):
        return {}
    cells = sorted({(k[2], k[3]) for k in run if k[0] == "state"})
    out = {}
    for c, k in cells:
        t = run[("state", "th", c, k)] * run[("forcing", "pii", c, k)]
        out[("cold", c, k)] = t <= T0C
        for f in MASS + ("nr", "ni", "nc"):
            out[(f, c, k)] = abs(run[("state", f, c, k)]) > _PRESENCE_EPS
    return out


def topology_report(runs: dict) -> None:
    ns = sorted(runs)
    t = {n: topology(runs[n]) for n in ns}
    if not t[ns[0]]:
        print("\n  topology: `pii` not present in this stream set")
        return
    ref = t[ns[0]]
    print(f"\n  final branch topology, against the coarsest member (N={ns[0]})")
    any_diff = False
    for n in ns[1:]:
        diff = sorted(k for k in ref if ref[k] != t[n][k])
        if diff:
            any_diff = True
            print(f"    N={n:3d} (h={300/n:g}s): {len(diff)} flips  " +
                  ", ".join(f"{a}@c{b}k{c}" for a, b, c in diff[:6]))
        else:
            print(f"    N={n:3d} (h={300/n:g}s): identical")
    if not any_diff:
        print("    -> the FINAL topology is stable across the whole chain. That is "
              "consistent\n       with the exponents being rates, and does not "
              "establish it: an\n       intermediate flip can heal before the end.")


# ── physical moist-enthalpy ledger (owner review §8.2) ───────────────────────
#
# All from module_model_constants.F, the authority both legs compile against:
CPD, CPV = 7 * 287.0 / 2, 4 * 461.6      # 1004.5, 1846.4  (F:20, F:24)
CLIQ, CICE = 4190.0, 2106.0              # F:27, F:28
XLV, XLF, XLS = 2.5e6, 3.5e5, 2.85e6     # F:55, F:56, F:54
# XLS - XLV == XLF exactly, so the set is self-consistent at T0 and the reference
# enthalpies below cannot disagree with the code's own latent heats at T0.

def _enthalpies(t: float) -> tuple:
    """h_d, h_v, h_l, h_i at T, referenced to T0, per-phase heat capacities.

    Reproduces the code's latent heats at T0 (h_v-h_l = XLV, h_l-h_i = XLF) but
    NOT its temperature dependence -- that gap is what §8.2 measures.
    """
    dt = t - T0C
    return CPD * dt, CPV * dt + XLV, CLIQ * dt, CICE * dt - XLF


def _ledger(run: dict, h_cell, h_precip_out) -> dict:
    """residual = (H_end - H_start) + H carried out by precipitation, per column.

    Zero with no external forcing. The two ledgers differ ONLY in `h_cell` and
    `h_precip_out`, so their physics sits side by side and can be compared by
    reading it.
    """
    if not any(k[0] == "initial" for k in run) or \
       not any(k[0] == "forcing" and k[1] == "pii" for k in run):
        return {}
    cells = {(k[2], k[3]) for k in run if k[0] == "state"}
    out = {}
    for c in sorted({x for x, _ in cells}):
        ks = sorted(k for cc, k in cells if cc == c)

        def H(cls):
            return sum(run[("forcing", "rho", c, k)] * run[("forcing", "delz", c, k)]
                       * h_cell(run, cls, c, k) for k in ks)

        # `pii` increases downward, so the larger one is the bottom level.
        kbot = ks[-1] if run[("forcing", "pii", c, ks[0])] < \
            run[("forcing", "pii", c, ks[-1])] else ks[0]
        h_start = H("initial")
        d = {"dH": H("state") - h_start,
             "H_precip_out": h_precip_out(run, c, kbot, ks),
             "H_start": h_start}
        d["residual"] = d["dH"] + d["H_precip_out"]
        d["relative"] = d["residual"] / abs(h_start) if h_start else float("nan")
        out[c] = d
    return out


def _t(run: dict, cls: str, c: int, k: int) -> float:
    return run[(cls, "th", c, k)] * run[("forcing", "pii", c, k)]


def _h_consistent(run, cls, c, k) -> float:
    """h = h_d + qv h_v + ql h_l + qi h_i, per-phase heat capacities (§8.2)."""
    hd, hv, hl, hi = _enthalpies(_t(run, cls, c, k))
    return (hd + run[(cls, "qv", c, k)] * hv
            + sum(run[(cls, f, c, k)] for f in LIQUID) * hl
            + sum(run[(cls, f, c, k)] for f in ICE) * hi)


def _water_out(run, c, ks) -> float:
    """Water that actually LEFT the column, from the rho*dz budget.

    NOT the fallout diagnostic. docs/STATUS.md records that the diagnostic and the
    column water loss disagree by an O(1) amount (P0-4b, the inflow cap), and a
    ledger built on the diagnostic inherits that defect instead of measuring
    thermodynamics: for legacy the diagnostic flux term is 4-7x the enthalpy change,
    so the residual becomes a restatement of the diagnostic error. Measured on this
    fixture, switching to the budget moves legacy's column-2 residual from
    -1.27e-02 to +9.8e-04 and removes essentially all of the apparent gap to the
    conservative interface.
    """
    return -sum(run[("forcing", "rho", c, k)] * run[("forcing", "delz", c, k)]
                * sum(run[("state", f, c, k)] - run[("initial", f, c, k)] for f in MASS)
                for k in ks)


def _ice_fraction(run, c) -> float:
    """Share of the departing water that is frozen. The diagnostic is used for the
    RATIO only, which is far less sensitive than its magnitude."""
    ice = run[("prec", 2, c)] + run[("prec", 3, c)]
    tot = run[("prec", 1, c)] + ice
    return ice / tot if tot else 0.0


def _precip_consistent(run, c, kbot, ks) -> float:
    """Departing water carries liquid or ice enthalpy at the bottom-level T."""
    _, _, hl, hi = _enthalpies(_t(run, "state", c, kbot))
    f = _ice_fraction(run, c)
    return _water_out(run, c, ks) * ((1.0 - f) * hl + f * hi)


def enthalpy_ledger(run: dict) -> dict:
    """Residual against CONSISTENT thermodynamics (§8.2).

    Approximate — dry-air mixing ratios against moist rho, precipitation flux at
    the bottom level — but identically so for every leg, so residuals COMPARE even
    where an absolute value would not.
    """
    return _ledger(run, _h_consistent, _precip_consistent)


# The code's own thermodynamics (module_mp_kdm6.F): cpmcal F:818, xlcal F:819,
# xlv1 = cl - cpv F:3406, and ONE cpm for the whole parcel rather than per-phase
# heat capacities (F:886-888). Reproducing the approximation is the point.
XLV1 = 4190.0 - 4 * 461.6      # cl - cpv = 2343.6, the slope §3.1 is about


def _code_coeffs(t: float, qv: float, qmin: float = 1.0e-32) -> tuple:
    q = max(qv, qmin)
    cpm = CPD * (1.0 - q) + q * CPV
    xl = XLV - XLV1 * (t - T0C)
    return cpm, xl, XLS - xl


def _h_code(run, cls, c, k) -> float:
    """h_op = cpm(qv)(T-T0) + xl(T) qv - xlf(T) q_ice — the code's own potential.

    Its heat updates all have the form `cpm dT = L dq`, so a conversion leaves this
    flat: vapour->liquid gives `cpm dT + xl dqv = 0`, liquid->ice gives
    `cpm dT - xlf dq_ice = 0`. Liquid's coefficient is zero because the code applies
    no latent heat to it.
    """
    t = _t(run, cls, c, k)
    qv = run[(cls, "qv", c, k)]
    cpm, xl, xlf = _code_coeffs(t, qv)
    return cpm * (t - T0C) + xl * qv - xlf * sum(run[(cls, f, c, k)] for f in ICE)


def _precip_code(run, c, kbot, ks) -> float:
    """Sedimentation removes mass with no temperature change, so departing ice
    carries -xlf out and departing rain carries nothing -- the same convention the
    code's own updates imply. Departing water from the budget, not the diagnostic
    (see `_water_out`)."""
    _, _, xlf = _code_coeffs(_t(run, "state", c, kbot),
                             run[("state", "qv", c, kbot)])
    return _water_out(run, c, ks) * _ice_fraction(run, c) * -xlf


def operator_ledger(run: dict) -> dict:
    """Residual against the code's OWN equations (§8.1).

    xl/xlf at the LOCAL temperature for every leg: the reference holds them at
    kernel entry and the port refreshes per sub-cycle, so one convention here keeps
    the ledger from encoding the answer to the question it is measuring.
    """
    return _ledger(run, _h_code, _precip_code)


def ledger_report(runs: dict) -> None:
    """Both ledgers, one table shape, different physics — the point of running two:
    §8.2 asks whether the code agrees with consistent thermodynamics, §8.1 whether
    it agrees with its own equations, and they can disagree."""
    ns = sorted(runs)
    for title, ledger in (
            ("moist-enthalpy column residual   (dH + H_precip_out; zero if closed)",
             enthalpy_ledger),
            ("OPERATOR-consistency residual   (code's own cpm/xl; §8.1)",
             operator_ledger)):
        L = {n: ledger(runs[n]) for n in ns}
        if not L[ns[0]]:
            print("\n  ledger: initial state or `pii` missing")
            return
        print(f"\n  {title}")
        print(f"    {'h (s)':>7} {'col':>3} {'residual [J/m2]':>18} {'relative':>12}")
        for n in ns:
            for c in sorted(L[n]):
                d = L[n][c]
                print(f"    {300/n:7g} {c:3d} {d['residual']:18.6e} "
                      f"{d['relative']:12.3e}")


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    d = Path(argv[0])
    runs = {}
    for p in sorted(d.glob("n*.rezero.txt")):
        n = int(re.match(r"n(\d+)\.", p.name).group(1))
        runs[n] = read(p, nsplit=n)
    if len(runs) < 2:
        raise SystemExit(f"need at least two members, found {sorted(runs)}")
    require_same_universe(runs)
    report(runs, d.name)
    per_field(runs)
    budget_report(runs)
    topology_report(runs)
    ledger_report(runs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
