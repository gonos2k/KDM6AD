#!/usr/bin/env python3
"""Convergence of one operator under external timestep refinement (owner §9).

The `cpm`/`xl` finding leaves a question parity cannot answer: the reference holds
the thermodynamic coefficients fixed across a kernel call's internal subcycles and
the port refreshes them each subcycle, and "refreshes more often" is not on its own
an argument that the answer is better. What separates them is whether each
operator's sequence converges as the step shrinks.

THE SWEEP MUST BE DESIGNED ON dtcld, NOT ON delt. The kernel sets its own
internal step at F:930-932:

    loops = max(nint(delt/dtcldcr), 1)      dtcldcr = 120 s
    dtcld = delt/loops   (or delt when delt <= dtcldcr)

so the N = 1,2,3,6,12 sweep of §9 gives dtcld = 100, 150, 100, 50, 25. That is not
a refinement sequence: N=2 integrates at 150 s, COARSER than N=1 and past the
kernel's own 120 s criterion, and N=3 duplicates N=1's internal step. Measured on
it, the error to the finest is non-monotone, which reads as an operator that does
not converge and is actually a sweep that does not refine. N in {3,6,12,24} gives
dtcld = 100, 50, 25, 12.5 -- a clean halving chain.

The discarded members are not waste. N=1 and N=3 share dtcld = 100 s and the same
three subcycles of integration, and differ only in how many times the coefficients
are refreshed (once, held across three subcycles, against three times). That pair
is a controlled contrast of the thermodynamic-coefficient policy alone, which the
refinement chain itself cannot isolate.

Reports both standard readings, because they answer different questions:

  successive differences  E_h = |X_h - X_{h/2}| over the doubling pairs present.
                          Self-convergence, no reference solution assumed. THE
                          ONLY PLACE AN ORDER IS COMPUTED.
  error to the finest     E_N = |X_N - X_finest|. Magnitude and monotonicity only.
                          NO ORDER (owner review §4).

The finest member is not the exact solution, and treating it as one biases the
exponent upward. With X_h = X* + C h^p,

    E_h = |X_h - X_hf| = |C| |h^p - hf^p|     so     E_h / E_{h/2} != 2^p

For a truly FIRST-order operator with hf = 12.5 s the ratio reads

    p(100->50) = +1.222        p(50->25) = +1.585

An earlier version of this module computed an order from that series and the
result was read as "near or above first order". It was not: +1.221 and +1.413 for
`th`, +1.205 and +1.614 for `number`, against a first-order prediction of +1.222
and +1.585. The estimator produced the exponent, not the operator. Those numbers
are withdrawn; the successive-difference series is the one that means anything.

This computes nothing about which policy is more physical. Convergence order is
one input to that; the moist-energy ledger of §8 is the other, and §3.1's
Kirchhoff point -- the code's dxlf/dT = c_l - c_pv = 2343.6 against a consistent
c_l - c_i = 2084 -- means a policy can refresh a formula more faithfully while
tracking the thermodynamics less well.
"""
from __future__ import annotations

import math
import re
import struct
import sys
from pathlib import Path

_STATE = re.compile(r"^G33R STATE\s+(\S+)\s+(\d+)\s+(-?\d+)\s+([0-9A-Fa-f]{8})$")
_PREC = re.compile(r"^G33R PREC\s+(\d+)\s+(\d+)\s+([0-9A-Fa-f]{8})$")
_FORCING = re.compile(r"^G33R FORCING\s+(rho|delz)\s+(\d+)\s+(-?\d+)\s+([0-9A-Fa-f]{8})$")

#: Reported separately. A mass field and a number moment can converge at
#: different rates, and averaging them hides exactly the number-moment behaviour
#: the conservative-nr blocker is about.
MASS = ("qv", "qc", "qr", "qi", "qs", "qg")
NUMBER = ("nc", "ni", "nr", "nccn")


def f32(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits))[0]


#: The exact record universe one member must contain. A refinement member is a
#: complete state, not "at least one record": a stream missing the cell that
#: carries the largest difference produces a SMALLER error norm and reads as
#: better convergence, so a permissive reader here fails in the direction that
#: flatters the result (owner review §2).
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

    Every check here corresponds to a way a truncated, duplicated or mislabelled
    stream would otherwise be analysed as a valid result. The parser this replaced
    accepted any file containing one parseable record.
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
            fld, i, k, b = m.groups()
            key = ("state", fld, int(i), int(k))
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
        for nm in ("rho", "delz"):
            got = {(k[2], k[3]) for k in fo if k[1] == nm}
            _expect(got == cells,
                    f"forcing `{nm}` covers {len(got)} cells, state covers "
                    f"{len(cells)}", path)
    out[("meta", "nsplit")] = got_n
    out[("meta", "mode")] = mode
    out[("meta", "algorithm")] = algo
    if loops is not None:
        out[("meta", "delt")] = float(delt)
        out[("meta", "loops")] = int(loops)
        out[("meta", "dtcld")] = float(dtcld)
    return out


def require_same_universe(runs: dict) -> None:
    """Every member must carry the SAME identities before any norm is taken.

    Comparing over the intersection lets a member that is missing records report a
    smaller error than one that is complete, which is convergence measured on
    absence. Checked once, up front, rather than per comparison.
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
    """Max absolute difference over `keys`.

    Max, not RMS: a per-cell operator difference that shows up in one cell is a
    real difference, and an RMS over 144 cells dilutes it by the cells where
    nothing is happening. The fixture is arithmetic-synthetic and most cells are
    quiet, so RMS here would mostly measure how many cells are quiet.
    """
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

#: Physical column budgets (owner review §7). The grouped max norms above are over
#: MIXING RATIOS and are set by one field at one cell, which migrates with
#: resolution. These are the quantities conservation is actually about:
#:
#:     W_col   = sum_k rho_k dz_k (qv+qc+qr+qi+qs+qg)
#:     N_x,col = sum_k rho_k dz_k n_x
#:
#: Reported per column, so a budget error in one column is not diluted by the rest.
_WATER = ("qv", "qc", "qr", "qi", "qs", "qg")


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
            w[k] * sum(run[("state", f, c, k)] for f in _WATER) for k in ks)
        for n in ("nr", "ni", "nc", "nccn"):
            out[(n, c)] = sum(w[k] * run[("state", n, c, k)] for k in ks)
    return out


def budget_report(runs: dict) -> None:
    ns = sorted(runs)
    b = {n: column_budgets(runs[n]) for n in ns}
    if not b[ns[0]]:
        print("\n  column budgets: forcing not present in this stream set")
        return
    pairs = [(n, 2 * n) for n in ns if 2 * n in runs]
    quantities = sorted({q for q, _ in b[ns[0]]})
    cols = sorted({c for _, c in b[ns[0]]})
    print("\n  rho*dz column budgets — successive order per column")
    hdr = "  ".join(f"{300/lo:g}->{150/lo:g}".rjust(13) for lo, _ in pairs[:-1])
    print(f"    {'quantity':10} {'col':>3} {hdr}")
    for q in quantities:
        for c in cols:
            row = []
            for i, (lo, hi) in enumerate(pairs[:-1]):
                e = abs(b[lo][(q, c)] - b[hi][(q, c)])
                e2 = abs(b[hi][(q, c)] - b[pairs[i + 1][1]][(q, c)])
                row.append("      -      " if e == 0 or e2 == 0
                           else f"{math.log2(e / e2):+13.3f}")
            if any(x.strip() != "-" for x in row):
                print(f"    {q:10} {c:3d} " + "  ".join(row))


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

    Owner review §7. A grouped max norm is not a physical norm: it reports one
    field at one cell, and if that cell moves between resolutions the apparent
    order is partly a record of the move. On this fixture the mass group is set by
    `qc` throughout but migrates col3 k3 -> k2 -> k1 at the fine end, and the group
    order stalls at +0.018 while `qv` stays near 1 -- two different behaviours
    averaged into one number.
    """
    ns = sorted(runs)
    pairs = [(n, 2 * n) for n in ns if 2 * n in runs]
    print("\n  per-field successive order")
    fields = sorted({k[1] for k in runs[ns[0]] if k[0] == "state"})
    hdr = "  ".join(f"{300/lo:g}->{150/lo:g}".rjust(13) for lo, _ in pairs[:-1])
    print(f"    {'field':6} {hdr}")
    for f in fields:
        row = []
        for i, (lo, hi) in enumerate(pairs[:-1]):
            k = [x for x in runs[lo] if x[0] == "state" and x[1] == f]
            e = _norm(runs[lo], runs[hi], k)
            e2 = _norm(runs[hi], runs[pairs[i + 1][1]], k)
            row.append("      -      " if e == 0 or e2 == 0
                       else f"{math.log2(e / e2):+13.3f}")
        if any(c.strip() != "-" for c in row):
            print(f"    {f:6} " + "  ".join(row))
    print("\n  cell setting each group max (a moving cell makes the group order "
          "partly a record of the move)")
    for g in GROUPS:
        if g == "prec":
            continue
        trail = []
        for lo, hi in pairs:
            k = _keys(runs[lo], g)
            _, best = max((abs(runs[lo][x] - runs[hi][x]), x) for x in k)
            trail.append(f"{best[1]}/c{best[2]}k{best[3]}")
        print(f"    {g:7} " + " -> ".join(trail))


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
