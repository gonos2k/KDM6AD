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
                          Self-convergence: no reference solution assumed.
  error to the finest     E_N = |X_N - X_finest|. What "approaches the refined
                          sequence" means, at the cost of treating the finest
                          member as truth.

An operator that converges should look like it under both.

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

#: Reported separately. A mass field and a number moment can converge at
#: different rates, and averaging them hides exactly the number-moment behaviour
#: the conservative-nr blocker is about.
MASS = ("qv", "qc", "qr", "qi", "qs", "qg")
NUMBER = ("nc", "ni", "nr", "nccn")


def f32(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits))[0]


def read(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        if m := _STATE.match(line.strip()):
            fld, i, k, b = m.groups()
            out[("state", fld, int(i), int(k))] = f32(int(b, 16))
        elif m := _PREC.match(line.strip()):
            f, i, b = m.groups()
            out[("prec", int(f), int(i))] = f32(int(b, 16))
    if not out:
        raise SystemExit(f"no G33R records in {path}")
    return out


def _norm(a: dict, b: dict, keys) -> float:
    """Max absolute difference over `keys`.

    Max, not RMS: a per-cell operator difference that shows up in one cell is a
    real difference, and an RMS over 144 cells dilutes it by the cells where
    nothing is happening. The fixture is arithmetic-synthetic and most cells are
    quiet, so RMS here would mostly measure how many cells are quiet.
    """
    d = [abs(a[k] - b[k]) for k in keys if k in a and k in b]
    return max(d) if d else 0.0


def _keys(run, group):
    if group == "prec":
        return [k for k in run if k[0] == "prec"]
    if group == "th":
        return [k for k in run if k[0] == "state" and k[1] == "th"]
    names = MASS if group == "mass" else NUMBER
    return [k for k in run if k[0] == "state" and k[1] in names]


GROUPS = ("th", "mass", "number", "prec")


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
    for name, series in (("successive |X_h - X_h/2|", successive(runs)),
                         (f"error to finest (N={max(runs)})", to_finest(runs))):
        print(f"\n  {name}")
        for g in GROUPS:
            s = series[g]
            if not s:
                continue
            cells = "  ".join(f"h={h:g}:{v:.6e}" for h, v in sorted(s.items(), reverse=True))
            print(f"    {g:7} {cells}")
            for h, e, ee, p in orders(s):
                pt = "n/a (a member is bit-identical)" if p is None else f"{p:+.3f}"
                print(f"            order {h:g}->{h/2:g}: p = {pt}")


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    d = Path(argv[0])
    runs = {}
    for p in sorted(d.glob("n*.rezero.txt")):
        n = int(re.match(r"n(\d+)\.", p.name).group(1))
        runs[n] = read(p)
    if len(runs) < 2:
        raise SystemExit(f"need at least two members, found {sorted(runs)}")
    report(runs, d.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
