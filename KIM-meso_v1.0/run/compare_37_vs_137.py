#!/usr/bin/env python3
"""Quantify per-variable differences between slot-37 and slot-137 wrfout files.

Reports:
  - identical (max-abs-diff == 0)
  - close (max-abs-diff > 0 but max-rel < 1e-6)
  - DIFFER (max-rel >= 1e-6)
For DIFFER rows: prints max-abs, max-rel, and the (x,k,y) index where the max-abs occurs.

Usage:
  python3 compare_37_vs_137.py wrfout.37 wrfout.137 [--frame N]
Default frame: 0 (initial), -1 (final). The script picks the LAST common frame.
"""
import sys, numpy as np, netCDF4 as nc

def main():
    p37 = sys.argv[1] if len(sys.argv) > 1 else "wrfout_d01_2007-06-01_00:00:00.37"
    p137 = sys.argv[2] if len(sys.argv) > 2 else "wrfout.137.30min.nc"

    a = nc.Dataset(p37, "r")
    b = nc.Dataset(p137, "r")
    n_common = min(a.dimensions["Time"].size, b.dimensions["Time"].size)
    frame = n_common - 1
    print(f"# {p37} (frames={a.dimensions['Time'].size})  vs  {p137} (frames={b.dimensions['Time'].size})")
    print(f"# Comparing frame index {frame} (last common, t = ~{frame} min sim time)")
    print()

    cats = {"identical": [], "close": [], "DIFFER": [], "missing": []}

    common = sorted(set(a.variables) & set(b.variables))
    only_a = sorted(set(a.variables) - set(b.variables))
    only_b = sorted(set(b.variables) - set(a.variables))

    for v in common:
        va, vb = a.variables[v], b.variables[v]
        if va.dimensions != vb.dimensions:
            cats["missing"].append((v, f"dim mismatch {va.dimensions} vs {vb.dimensions}"))
            continue
        if "Time" in va.dimensions:
            try:
                xa = va[frame]; xb = vb[frame]
            except IndexError:
                cats["missing"].append((v, "frame index out of range"))
                continue
        else:
            xa = va[:]; xb = vb[:]
        if xa.dtype.kind not in ("f", "i", "u"):
            continue
        try:
            xa = np.asarray(xa, dtype=np.float64)
            xb = np.asarray(xb, dtype=np.float64)
        except Exception as e:
            cats["missing"].append((v, f"asarray fail: {e}")); continue
        d = np.abs(xa - xb)
        max_abs = float(d.max()) if d.size else 0.0
        if max_abs == 0.0:
            cats["identical"].append(v)
            continue
        denom = np.maximum(np.abs(xa), np.abs(xb))
        with np.errstate(divide="ignore", invalid="ignore"):
            rel = np.where(denom > 0, d / denom, 0.0)
        max_rel = float(np.nanmax(rel))
        idx = np.unravel_index(int(np.argmax(d)), d.shape)
        if max_rel < 1e-6:
            cats["close"].append((v, max_abs, max_rel, idx))
        else:
            cats["DIFFER"].append((v, max_abs, max_rel, idx,
                                    float(xa[idx]), float(xb[idx]),
                                    float(np.abs(xa).mean()), float(np.abs(xb).mean())))

    print(f"## summary  identical={len(cats['identical'])}  close={len(cats['close'])}  DIFFER={len(cats['DIFFER'])}  errors={len(cats['missing'])}")
    print(f"## only-in-37: {len(only_a)} | only-in-137: {len(only_b)}")
    print()

    if cats["DIFFER"]:
        print("## DIFFER (max-rel >= 1e-6) — sorted by max-rel desc")
        print(f"{'var':20s} {'max-abs':>12s} {'max-rel':>12s} {'idx':>20s} {'val37':>13s} {'val137':>13s} {'mean37':>13s} {'mean137':>13s}")
        for v, ma, mr, idx, va_v, vb_v, ma_mean, mb_mean in sorted(cats["DIFFER"], key=lambda r: -r[2]):
            print(f"{v:20s} {ma:12.3e} {mr:12.3e} {str(idx):>20s} {va_v:13.5e} {vb_v:13.5e} {ma_mean:13.5e} {mb_mean:13.5e}")
        print()

    if only_a:
        print(f"## only-in-37 ({len(only_a)}): {only_a[:20]}{' ...' if len(only_a)>20 else ''}")
    if only_b:
        print(f"## only-in-137 ({len(only_b)}): {only_b[:20]}{' ...' if len(only_b)>20 else ''}")

    if cats["close"]:
        print(f"## close (max-rel < 1e-6, count {len(cats['close'])}):")
        for v, ma, mr, idx in cats["close"][:30]:
            print(f"  {v:20s} max-abs {ma:.3e} rel {mr:.3e} at {idx}")
    if cats["missing"]:
        print(f"## errors/skipped ({len(cats['missing'])}):")
        for v, reason in cats["missing"][:20]:
            print(f"  {v:20s} {reason}")

if __name__ == "__main__":
    main()
