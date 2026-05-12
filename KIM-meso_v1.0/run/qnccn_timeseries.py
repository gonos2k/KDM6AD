#!/usr/bin/env python3
"""QNCCN per-frame trajectory comparison between mp=37 and mp=137 wrfout files.

Output per frame:
  frame  t(min)  mean37        mean137       ratio37_137  max-abs-diff  max-rel
"""
import sys, numpy as np, netCDF4 as nc

p37 = sys.argv[1] if len(sys.argv) > 1 else "wrfout.37.30min.nc"
p137 = sys.argv[2] if len(sys.argv) > 2 else "wrfout.137.30min.nc"

a = nc.Dataset(p37, "r")
b = nc.Dataset(p137, "r")
n = min(a.dimensions["Time"].size, b.dimensions["Time"].size)
qa = a.variables["QNCCN"]
qb = b.variables["QNCCN"]

print(f"# {p37} vs {p137}, {n} frames, var=QNCCN dims={qa.dimensions} shape_per_frame={qa.shape[1:]}")
print(f"{'frame':>5s} {'t(min)':>7s} {'mean37':>13s} {'mean137':>13s} {'ratio':>8s} {'max-abs':>12s} {'max-rel':>10s} {'std37':>13s} {'std137':>13s}")

prev_ratio = None
for f in range(n):
    x = np.asarray(qa[f], dtype=np.float64)
    y = np.asarray(qb[f], dtype=np.float64)
    m37 = x.mean(); m137 = y.mean()
    s37 = x.std(); s137 = y.std()
    d = np.abs(x - y); maxabs = d.max()
    denom = np.maximum(np.abs(x), np.abs(y))
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(denom > 0, d / denom, 0.0)
    maxrel = float(np.nanmax(rel))
    ratio = m37 / m137 if m137 > 0 else float("inf")
    delta = ""
    if prev_ratio is not None:
        d_ratio = ratio - prev_ratio
        if abs(d_ratio) >= 0.01:
            delta = f"  Δratio={d_ratio:+.3f}"
    prev_ratio = ratio
    print(f"{f:5d} {f:7d} {m37:13.5e} {m137:13.5e} {ratio:8.4f} {maxabs:12.3e} {maxrel:10.3e} {s37:13.5e} {s137:13.5e}{delta}")

print()
print(f"# IC frame (t=0): mean37 = mean137 should be true if start_em.F init is identical")
print(f"# look for first frame where ratio departs from 1.0 — that step is where the bug fires")
