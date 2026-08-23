#!/usr/bin/env python3
"""Two decompositions of one forecast, compared without flattering either.

`FINDING_mpi_trajectory_growth_v1` reported quantiles over the cells that
DIFFER, a reflectivity growth factor across a support that changes between the
two times it compares, and an accumulated-precipitation maximum. Each is a real
number and none of them is what a reader takes it for (owner review §10-13).

Four corrections, and every statistic says which population it is over.

CONDITIONAL AND UNCONDITIONAL. `p99` over differing cells is not the domain's
`p99`. Both are reported; the first says how big a difference is where there is
one, the second how much of the domain carries it.

A FIXED MASK FOR GROWTH. Comparing a median at one minute with a median at ten
compares two different sets of cells, because the differing support grows from
4.8 % to 11.2 %. Growth is measured on the cells that differ at the FIRST time
and followed, so the population is held still.

SIGNED, FOR PRECIPITATION. `|dP|` cannot tell a domain that rains more from one
that rains the same in different places. The signed domain integral and the
exceedance fractions are what separate them.

REFLECTIVITY IN ITS OWN TERMS. The field's range here reaches 174.8 dBZ, which
is not a reflectivity, so a maximum is dominated by whatever produces those.
The physically screened population, the linear-Z ratio and the threshold AREAS
are reported instead -- the last being what a forecast is read in.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

#: Outside this, `REFL_10CM` is not being used as a reflectivity.
REFL_PHYSICAL = (-35.0, 80.0)


def _fields(d):
    import numpy as np
    return [v for v in d.variables
            if d[v].dtype == np.float32 and d[v].ndim >= 3
            and "Time" in d[v].dimensions]


def coverage(a, b) -> list:
    """Per frame: how many fields differ, and which are new since the last."""
    import numpy as np
    out, prev = [], set()
    for t in range(a["Times"].shape[0]):
        now = {v for v in _fields(a)
               if not np.array_equal(np.asarray(a[v][t]), np.asarray(b[v][t]))}
        out.append({"frame": t, "differing": len(now),
                    "new_since_previous": sorted(now - prev),
                    "gone_since_previous": sorted(prev - now)})
        prev = now
    return out


def field_stats(a, b, name: str, t: int, mask=None) -> dict:
    """One field at one frame, conditional AND unconditional."""
    import numpy as np
    x = np.asarray(a[name][t], dtype="float64")
    y = np.asarray(b[name][t], dtype="float64")
    d = np.abs(x - y)
    diff = d > 0
    out = {"field": name, "frame": t,
           "cells": int(d.size),
           "differing": int(diff.sum()),
           "differing_fraction": float(diff.mean()),
           "domain_p99": float(np.percentile(d, 99)),
           "domain_p999": float(np.percentile(d, 99.9)),
           "domain_mean_abs": float(d.mean()),
           "signed_mean": float((y - x).mean())}
    if diff.any():
        out["conditional_p99"] = float(np.percentile(d[diff], 99))
        out["conditional_median"] = float(np.median(d[diff]))
    if mask is not None and mask.any():
        out["fixed_mask_median"] = float(np.median(d[mask]))
        out["fixed_mask_p99"] = float(np.percentile(d[mask], 99))
    return out


def precipitation(a, b, t: int, name: str = "RAINNC") -> dict:
    """Signed and thresholded, because `|dP|` cannot tell more rain from
    rain somewhere else."""
    import numpy as np
    x = np.asarray(a[name][t], dtype="float64")
    y = np.asarray(b[name][t], dtype="float64")
    d = y - x
    # UNITS. `RAINNC` is mm per column, so a bare sum is mm x columns and is
    # not a depth. The domain MEAN is a depth; the sum is reported as what it
    # is, and the cancellation RATIO is dimensionless and unaffected either way
    # (owner review §11). A volume needs cell areas, which this frame does not
    # carry, so it is not claimed.
    # GRID-CELL mean, not area-weighted. On a map projection the cells differ
    # in area, so this is a model-grid statistic and not a domain precipitation
    # depth; a volume would need MAPFAC_M, which this frame does not carry
    # (owner review §12.2).
    out = {"field": name, "frame": t,
           "signed_gridcell_mean_mm": float(d.mean()),
           "signed_sum_mm_times_columns": float(d.sum()),
           "gross_sum_mm_times_columns": float(np.abs(d).sum()),
           "cancellation_ratio": (float(abs(d.sum()) / np.abs(d).sum())
                                  if np.abs(d).sum() else None),
           "columns": int(d.size)}
    for thr in (1e-3, 1e-2, 1e-1):
        out[f"fraction_over_{thr:g}mm"] = float((np.abs(d) > thr).mean())
        out[f"columns_over_{thr:g}mm"] = int((np.abs(d) > thr).sum())
    return out


def reflectivity(a, b, t: int, name: str = "REFL_10CM") -> dict:
    """Screened to the physical range, in linear Z, and as threshold AREAS."""
    import numpy as np
    x = np.asarray(a[name][t], dtype="float64")
    y = np.asarray(b[name][t], dtype="float64")
    lo, hi = REFL_PHYSICAL
    ok = (x >= lo) & (x <= hi) & (y >= lo) & (y <= hi)
    out = {"field": name, "frame": t,
           "physical_fraction": float(ok.mean()),
           "outside_physical": int((~ok).sum())}
    if ok.any():
        d = np.abs(x - y)[ok]
        out["screened_p99_dbz"] = float(np.percentile(d, 99))
        out["screened_max_dbz"] = float(d.max())
        zx, zy = 10.0 ** (x[ok] / 10.0), 10.0 ** (y[ok] / 10.0)
        r = np.where(zx > 0, zy / np.where(zx > 0, zx, 1.0), np.nan)
        out["linear_Z_ratio_p99"] = float(np.nanpercentile(r, 99))
    # CELL COUNTS, not areas. A physical area needs the map factor,
    #     A_ij = DX*DY / MAPFAC_M_ij**2
    # and this frame does not carry MAPFAC_M, so the count is reported as a
    # count and the word "area" is not used (owner review §12.1).
    for thr in (10.0, 20.0, 30.0, 40.0):
        out[f"cells_over_{thr:g}dbz_a"] = int(((x >= thr) & (x <= hi)).sum())
        out[f"cells_over_{thr:g}dbz_b"] = int(((y >= thr) & (y <= hi)).sum())
    return out


def main() -> int:
    import netCDF4
    import numpy as np
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_a", type=Path)
    ap.add_argument("run_b", type=Path)
    ap.add_argument("--frames", default="1,5,10")
    ap.add_argument("--fixed-mask-frame", type=int, default=1)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    a, b = netCDF4.Dataset(str(args.run_a)), netCDF4.Dataset(str(args.run_b))
    frames = [int(f) for f in args.frames.split(",")]

    cov = coverage(a, b)
    print("  frame  differing fields   new since previous")
    for row in cov:
        new = ", ".join(row["new_since_previous"][:8])
        print(f"  {row['frame']:5d}  {row['differing']:16d}   "
              f"{new[:70]}{'...' if len(new) > 70 else ''}")

    masks = {}
    for name in ("T", "REFL_10CM", "QVAPOR"):
        if name in a.variables:
            x = np.asarray(a[name][args.fixed_mask_frame], dtype="float64")
            y = np.asarray(b[name][args.fixed_mask_frame], dtype="float64")
            masks[name] = x != y

    doc = {"coverage": cov, "fields": [], "precipitation": [],
           "reflectivity": [], "fixed_mask_frame": args.fixed_mask_frame}
    print(f"\n  {'field':10s} {'t':>3s} {'differ':>8s} {'cond p99':>11s} "
          f"{'domain p99':>11s} {'fixed-mask med':>15s}")
    for t in frames:
        for name in ("T", "QVAPOR", "REFL_10CM", "RAINNC"):
            if name not in a.variables:
                continue
            r = field_stats(a, b, name, t, masks.get(name))
            doc["fields"].append(r)
            print(f"  {name:10s} {t:>3d} {r['differing_fraction']:7.2%} "
                  f"{r.get('conditional_p99', float('nan')):11.3e} "
                  f"{r['domain_p99']:11.3e} "
                  f"{r.get('fixed_mask_median', float('nan')):15.3e}")
        if "RAINNC" in a.variables:
            doc["precipitation"].append(precipitation(a, b, t))
        if "REFL_10CM" in a.variables:
            doc["reflectivity"].append(reflectivity(a, b, t))

    print(f"\n  {'t':>3s} {'signed cell-mean':>17s} {'cancel ratio':>13s} "
          f"{'>1e-3':>9s} {'>1e-2':>9s} {'>1e-1':>9s}")
    for r in doc["precipitation"]:
        print(f"  {r['frame']:>3d} {r['signed_gridcell_mean_mm']:17.4e} "
              f"{r['cancellation_ratio']:13.4f} "
              f"{r['fraction_over_0.001mm']:8.3%} "
              f"{r['fraction_over_0.01mm']:8.3%} {r['fraction_over_0.1mm']:8.3%}")

    print(f"\n  {'t':>3s} {'in-range':>9s} {'screened p99':>13s} "
          f"{'>20dBZ cells a':>14s} {'cells b':>9s}")
    for r in doc["reflectivity"]:
        print(f"  {r['frame']:>3d} {r['physical_fraction']:8.3%} "
              f"{r.get('screened_p99_dbz', float('nan')):13.4f} "
              f"{r['cells_over_20dbz_a']:14d} {r['cells_over_20dbz_b']:9d}")

    if args.json:
        args.json.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
