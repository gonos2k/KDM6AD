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


def comparable(a, b) -> None:
    """Refuse two files that are not the same experiment.

    `coverage` walked `_fields(a)` alone, so a field present only in `b` was
    silently not compared and the count read as agreement. And nothing asked
    whether the two runs share a grid, a field universe or a time axis -- so
    two forecasts of different domains would compare, field by field, and
    report a number.
    """
    import numpy as np
    fa, fb = set(_fields(a)), set(_fields(b))
    if fa != fb:
        raise SystemExit(
            f"field universes differ: only in A {sorted(fa - fb)}; "
            f"only in B {sorted(fb - fa)}")
    ta = np.asarray(a["Times"][:])
    tb = np.asarray(b["Times"][:])
    if ta.shape != tb.shape or not np.array_equal(ta, tb):
        raise SystemExit(f"time axes differ: A {ta.shape}, B {tb.shape}")
    for v in sorted(fa):
        if a[v].shape != b[v].shape:
            raise SystemExit(
                f"{v}: shape {a[v].shape} in A, {b[v].shape} in B")


def coverage(a, b) -> list:
    """Per frame: how many fields differ, and which are new since the last."""
    import numpy as np
    comparable(a, b)
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
    """One field at one frame, conditional AND unconditional.

    NOT-A-NUMBER IS A DIFFERENCE. The test used to be `abs(x - y) > 0`, and
    `abs(nan - 1.0)` is `nan`, which is not greater than zero. So a field that
    went NaN in ONE decomposition and stayed finite in the other reported
    `differing = 0` -- "the two agree everywhere" -- for the one outcome a
    divergence tool exists to catch. `coverage()` calls the same field
    different, because `array_equal` is NaN-correct, so the two statistics this
    module reports contradicted each other exactly there.

    `x != y` is the same test `array_equal` makes, elementwise: NaN differs
    from everything including NaN, so the two now agree by construction. The
    non-finite census is reported beside the counts, because a reader owed the
    number of differing cells is also owed whether they differ by being broken.

    The magnitude statistics are taken over the FINITE differences only. A
    single NaN makes every percentile NaN, which reports nothing about the
    other cells and is not a size.
    """
    import numpy as np
    x = np.asarray(a[name][t], dtype="float64")
    y = np.asarray(b[name][t], dtype="float64")
    d = np.abs(x - y)
    diff = x != y
    fx, fy = np.isfinite(x), np.isfinite(y)
    finite = np.isfinite(d)
    fd = d[finite]
    out = {"field": name, "frame": t,
           "cells": int(d.size),
           "differing": int(diff.sum()),
           "differing_fraction": float(diff.mean()),
           # THREE WAYS TO DIFFER, SEPARATED. `differing` answers "are the two
           # runs the same", which is the question `coverage` answers and the
           # one that must agree with it -- so NaN counts, since NaN differs
           # from everything including NaN. But "they disagree numerically",
           # "one of them broke", and "both broke in the same place" are three
           # different findings, and a single count cannot be read as any one
           # of them. They partition `differing` exactly.
           "finite_value_differing": int((fx & fy & diff).sum()),
           "finiteness_differing": int((fx ^ fy).sum()),
           "common_nonfinite": int((~fx & ~fy).sum()),
           "nonfinite_a": int((~fx).sum()),
           "nonfinite_b": int((~fy).sum()),
           # NAMED FOR THE POPULATION THEY ARE OVER. Called `domain_p99` these
           # read as the domain's, and they are not when anything is non-finite:
           # the cells that are excluded are exactly the broken ones.
           "finite_domain_p99": float(np.percentile(fd, 99)) if fd.size else None,
           "finite_domain_p999": float(np.percentile(fd, 99.9)) if fd.size else None,
           "finite_domain_mean_abs": float(fd.mean()) if fd.size else None,
           "finite_signed_mean": float((y - x)[finite].mean()) if fd.size else None}
    cond = diff & finite
    if cond.any():
        out["conditional_p99"] = float(np.percentile(d[cond], 99))
        out["conditional_median"] = float(np.median(d[cond]))
    if mask is not None and mask.any():
        # THE FIXED MASK NEEDS THE FINITE MASK TOO. It is chosen at the FIRST
        # time and followed, so it can easily contain a cell that went
        # non-finite later -- and one of those makes the median and the p99 NaN,
        # which reports nothing about the rest of the held population. The
        # domain statistics above were fixed for this and this one was missed.
        held = mask & finite
        out["fixed_mask_cells"] = int(mask.sum())
        out["fixed_mask_finite_cells"] = int(held.sum())
        out["fixed_mask_nonfinite_cells"] = int((mask & ~finite).sum())
        out["fixed_mask_median"] = (float(np.median(d[held]))
                                    if held.any() else None)
        out["fixed_mask_p99"] = (float(np.percentile(d[held], 99))
                                 if held.any() else None)
    return out


def cell_area(state_path: Path, a):
    """`A_ij = DX*DY / MAPFAC_M**2`, from a file that carries the map factor.

    The forecast frames here do not; `wrfinput_d01` does. Without it every
    spatial statistic is a grid-cell one, which this module labels as such.
    """
    import netCDF4
    import numpy as np
    d = netCDF4.Dataset(str(state_path))
    mf = np.asarray(d["MAPFAC_M"][0], dtype="float64")
    dx, dy = float(d.getncattr("DX")), float(d.getncattr("DY"))
    # The map factor must be THIS domain's. A wrfinput from another run of the
    # same grid size would pass silently and weight every cell wrongly.
    ref = a["RAINNC"].shape[-2:] if "RAINNC" in a.variables else a["T"].shape[-2:]
    if mf.shape != tuple(ref):
        raise SystemExit(f"MAPFAC_M is {mf.shape}, the forecast grid is {tuple(ref)}")
    for key in ("DX", "DY"):
        if key in a.ncattrs() and abs(float(a.getncattr(key)) - (dx if key == "DX" else dy)) > 1e-6:
            raise SystemExit(f"{key} differs between the map-factor file and the forecast")
    return dx * dy / (mf * mf)


def precipitation(a, b, t: int, name: str = "RAINNC", area=None) -> dict:
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
    # NON-FINITE, the same hole `field_stats` had. `abs(nan) > thr` is False,
    # so a column that went NaN counts as NOT exceeding every threshold and the
    # exceedance fractions understate silently. `reflectivity` is immune by
    # construction -- its physical screen drops NaN and reports the count -- so
    # this is the one of the three that needed the census made explicit.
    finite = np.isfinite(d)
    fd = d[finite]
    n = fd.size
    out = {"field": name, "frame": t,
           "signed_gridcell_mean_mm": float(fd.mean()) if n else None,
           "signed_sum_mm_times_columns": float(fd.sum()) if n else None,
           "gross_sum_mm_times_columns": float(np.abs(fd).sum()) if n else None,
           "cancellation_ratio": (float(abs(fd.sum()) / np.abs(fd).sum())
                                  if n and np.abs(fd).sum() else None),
           "columns": int(d.size),
           "nonfinite_columns": int((~finite).sum())}
    if area is not None:
        # AREA-WEIGHTED, which a grid-cell mean is not on a map projection.
        # Volume in m^3 of liquid water: mm -> m is 1e-3.
        af = np.asarray(area)[finite]
        out["area_weighted_mean_mm"] = float((fd * af).sum() / af.sum()) if n else None
        out["signed_volume_m3"] = float((fd * af).sum() * 1e-3) if n else None
        out["gross_volume_m3"] = float((np.abs(fd) * af).sum() * 1e-3) if n else None
    for thr in (1e-3, 1e-2, 1e-1):
        # over the FINITE columns; `nonfinite_columns` says how many are not in
        # this population, so the fraction has a stated denominator.
        out[f"fraction_over_{thr:g}mm"] = (float((np.abs(fd) > thr).mean())
                                           if n else None)
        out[f"columns_over_{thr:g}mm"] = int((np.abs(fd) > thr).sum())
    return out


def reflectivity(a, b, t: int, name: str = "REFL_10CM", area=None) -> dict:
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
        ma, mb = (x >= thr) & (x <= hi), (y >= thr) & (y <= hi)
        out[f"cells_over_{thr:g}dbz_a"] = int(ma.sum())
        out[f"cells_over_{thr:g}dbz_b"] = int(mb.sum())
        if area is not None:
            # the column is a cell; area weighting collapses the vertical
            ca, cb = ma.any(axis=0), mb.any(axis=0)
            out[f"area_km2_over_{thr:g}dbz_a"] = float((ca * area).sum() * 1e-6)
            out[f"area_km2_over_{thr:g}dbz_b"] = float((cb * area).sum() * 1e-6)
    return out


def _fmt(v) -> str:
    """A missing or empty population prints as itself, not as `nan`.

    The row fell back to `float('nan')` when a field had no held population at
    all -- RAINNC, whose fixed mask is empty -- and a printed `nan` reads as a
    measurement that came out undefined rather than as one that was never
    taken.
    """
    return "-" if v is None else f"{v:.3e}"


def main() -> int:
    import netCDF4
    import numpy as np
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_a", type=Path)
    ap.add_argument("run_b", type=Path)
    ap.add_argument("--frames", default="1,5,10")
    ap.add_argument("--fixed-mask-frame", type=int, default=1)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--mapfac-from", type=Path, default=None,
                    help="a file carrying MAPFAC_M and DX/DY (wrfinput_d01); "
                         "enables area-weighted precipitation and area in km2")
    args = ap.parse_args()
    a, b = netCDF4.Dataset(str(args.run_a)), netCDF4.Dataset(str(args.run_b))
    area = cell_area(args.mapfac_from, a) if args.mapfac_from else None
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
                  f"{r['finite_domain_p99']:11.3e} "
                  f"{_fmt(r.get('fixed_mask_median')):>15s}")
        if "RAINNC" in a.variables:
            doc["precipitation"].append(precipitation(a, b, t, area=area))
        if "REFL_10CM" in a.variables:
            doc["reflectivity"].append(reflectivity(a, b, t, area=area))

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
