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
import sys
from pathlib import Path

#: Outside this, `REFL_10CM` is not being used as a reflectivity.
REFL_PHYSICAL = (-35.0, 80.0)


def _signed_mean(x, y, finite):
    """Mean signed difference over the finite cells.

    Same reason as the subtraction above: `inf - inf` warns, the NaN is excluded
    by `finite`, and the warning would only hide a real one later.
    """
    import numpy as np
    with np.errstate(invalid="ignore"):
        return float((y - x)[finite].mean())


def _num(var, index):
    """A numeric field, through the guard (owner review 8.3).

    `np.asarray` on a netCDF variable DROPS a mask, and this module then feeds
    the result to equality, a non-finite census, and precipitation and
    reflectivity thresholds. `g33_number_basis` was wired through the guard and
    this one -- equally load-bearing -- was not.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import g33_netcdf_read as nr
    return nr.read_numeric(var, index)["data"]


def _fields(d):
    import numpy as np
    return [v for v in d.variables
            if d[v].dtype == np.float32 and d[v].ndim >= 3
            and "Time" in d[v].dimensions]


def _forecast_in(run_dir):
    """The one forecast file in a run directory, or a refusal naming what it found."""
    from pathlib import Path
    cands = sorted(p for p in Path(run_dir).iterdir()
                   if p.is_file() and (p.name.startswith("klfs_lc05_fcst.")
                                       or p.name.startswith("wrfout_d01_")))
    if len(cands) != 1:
        raise SystemExit(
            f"{run_dir}: expected exactly one forecast file, found {len(cands)}"
            + (f": {[c.name for c in cands]}" if cands else ""))
    return cands[0]


def same_experiment(dir_a, dir_b, *, expect: str = "decomposition") -> dict:
    """Refuse two RUNS that are not the same experiment (owner review 8.2).

    `comparable` below checks the two FILES agree in field universe, time axis
    and shape. That is necessary and nowhere near sufficient: two forecasts of
    different initial states, built from different binaries, under different
    namelists, all pass it -- and then a divergence statistic gets attributed to
    the decomposition.

    `run_ss_case` now records what settles it. This reads that metadata and
    states which of the four agree, so an attribution has something to stand on
    besides the array shapes.

    `expect` names what SHOULD differ: "decomposition" wants the same binary,
    runner and namelist with a different processor grid; "perturbation" wants
    all four identical, the input having been changed instead.
    """
    from pathlib import Path

    def read(d, name):
        p = Path(d) / name
        return p.read_text().strip() if p.is_file() else None

    def first(text):
        return text.splitlines()[0].strip() if text else None

    out = {"applied": True, "expect": expect,
           "a": str(dir_a), "b": str(dir_b), "agree": {}, "differ": {}}
    for key, name, pick in (("wrf_exe", "wrf_exe_sha256", first),
                            ("runner", "runner_sha256", first),
                            ("proc_grid", "proc_grid", lambda t: t),
                            ("namelist", "namelist.input", lambda t: t)):
        va, vb = pick(read(dir_a, name)), pick(read(dir_b, name))
        if va is None or vb is None:
            out["differ"][key] = "not recorded in one or both runs"
        elif va == vb:
            out["agree"][key] = True
        else:
            out["differ"][key] = "differs"

    must_agree = {"decomposition": ("wrf_exe", "runner"),
                  "perturbation": ("wrf_exe", "runner", "proc_grid", "namelist")}[expect]
    bad = [k for k in must_agree if k not in out["agree"]]
    if bad:
        raise SystemExit(
            f"these runs are not one {expect} experiment: {bad} "
            f"({ {k: out['differ'].get(k) for k in bad} }). "
            f"A divergence measured across them cannot be attributed to "
            f"{expect}.")
    if expect == "decomposition" and "proc_grid" in out["agree"]:
        raise SystemExit(
            "both runs used the same processor grid, so there is no "
            "decomposition difference to attribute anything to.")
    return out


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
               if not np.array_equal(_num(a[v], t), _num(b[v], t),
                                     equal_nan=False)}
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
    x = _num(a[name], t)
    y = _num(b[name], t)
    # `inf - inf` is NaN and warns. The NaN is expected and handled -- `finite`
    # excludes it below -- so the warning is noise that would hide a real one.
    # Suppressed around the subtraction only; it changes no value.
    with np.errstate(invalid="ignore"):
        d = np.abs(x - y)
    diff = x != y
    fx, fy = np.isfinite(x), np.isfinite(y)
    finite = np.isfinite(d)
    fd = d[finite]
    out = {"field": name, "frame": t,
           "cells": int(d.size),
           "differing": int(diff.sum()),
           "differing_fraction": float(diff.mean()),
           # THREE WAYS TO DIFFER, AND THEY PARTITION `differing` -- which the
           # first version of this got wrong. "Both non-finite" is NOT one of
           # them: `+inf` against `+inf` is both-non-finite and `x != y` is
           # FALSE, so counting it as a way to differ made the three sum to
           # MORE than `differing`. Two cells of `[+inf, nan]` against
           # themselves gave 0 + 0 + 2 against a `differing` of 1.
           #
           # The both-non-finite cells split: NaN differs from NaN, `+inf` does
           # not. Only the differing half belongs in the partition, and the
           # equal half is reported beside it because "both runs broke in the
           # same place, identically" is a finding of its own.
           "finite_value_differing": int((fx & fy & diff).sum()),
           "finiteness_differing": int((fx ^ fy).sum()),
           "both_nonfinite_differing": int((~fx & ~fy & diff).sum()),
           "both_nonfinite_equal": int((~fx & ~fy & ~diff).sum()),
           "nonfinite_a": int((~fx).sum()),
           "nonfinite_b": int((~fy).sum()),
           # NAMED FOR THE POPULATION THEY ARE OVER. Called `domain_p99` these
           # read as the domain's, and they are not when anything is non-finite:
           # the cells that are excluded are exactly the broken ones.
           "finite_domain_p99": float(np.percentile(fd, 99)) if fd.size else None,
           "finite_domain_p999": float(np.percentile(fd, 99.9)) if fd.size else None,
           "finite_domain_mean_abs": float(fd.mean()) if fd.size else None,
           "finite_signed_mean": _signed_mean(x, y, finite) if fd.size else None}
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
    mf = _num(d["MAPFAC_M"], 0)
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
    x = _num(a[name], t)
    y = _num(b[name], t)
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
    x = _num(a[name], t)
    y = _num(b[name], t)
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


def _fmt(v, spec: str = ".3e") -> str:
    """A missing or empty population prints as itself, not as `nan`.

    The row fell back to `float('nan')` when a field had no held population at
    all -- RAINNC, whose fixed mask is empty -- and a printed `nan` reads as a
    measurement that came out undefined rather than as one that was never
    taken.

    The precipitation row formatted its values directly, which crashed on
    `cancellation_ratio`. That field is None in exactly one case: the gross sum
    is zero, because the two decompositions AGREE. So the summary was reachable
    only while the runs still differed, and the first pair that matched took the
    whole report down -- including the JSON, written further on. Every printed
    statistic there is None on an empty population, so all of them go through
    here.
    """
    return "-" if v is None else format(v, spec)


def main() -> int:
    import netCDF4
    import numpy as np
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_a", type=Path,
                    help="a run DIRECTORY (gated) or a forecast file (ungated)")
    ap.add_argument("run_b", type=Path)
    ap.add_argument("--expect", choices=["decomposition", "perturbation"],
                    default="decomposition",
                    help="what the two runs are allowed to differ in")
    ap.add_argument("--frames", default="1,5,10")
    ap.add_argument("--fixed-mask-frame", type=int, default=1)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--mapfac-from", type=Path, default=None,
                    help="a file carrying MAPFAC_M and DX/DY (wrfinput_d01); "
                         "enables area-weighted precipitation and area in km2")
    args = ap.parse_args()
    # THE GATE RUNS HERE, OR THE ARTIFACT SAYS IT DID NOT. same_experiment() was
    # written and then called from nothing, so every comparison this CLI made
    # was ungated -- a guard that exists and does not guard is worse than none,
    # because its existence reads as protection (owner review 7).
    #
    # A RUN DIRECTORY carries the metadata that settles attribution; a bare
    # forecast file does not. Both are accepted, and the difference is recorded:
    # given directories the gate runs and a mismatch refuses; given files the
    # comparison proceeds and says, in the JSON and on stderr, that no
    # experiment gate was applied.
    gate = None
    if args.run_a.is_dir() and args.run_b.is_dir():
        gate = same_experiment(args.run_a, args.run_b, expect=args.expect)
        file_a, file_b = _forecast_in(args.run_a), _forecast_in(args.run_b)
    elif args.run_a.is_dir() or args.run_b.is_dir():
        raise SystemExit("pass two run directories or two files, not one of each")
    else:
        file_a, file_b = args.run_a, args.run_b
        print("g33_mpi_divergence: NO EXPERIMENT GATE. These are forecast files, "
              "so nothing here checked that the two runs share a binary, a "
              "runner, a namelist or an input. Pass the run DIRECTORIES to have "
              "that checked.", file=sys.stderr)
    a, b = netCDF4.Dataset(str(file_a)), netCDF4.Dataset(str(file_b))
    area = cell_area(args.mapfac_from, a) if args.mapfac_from else None
    frames = [int(f) for f in args.frames.split(",")]

    # THE REQUESTED FRAMES MUST EXIST. Asking for minute 10 of a one-minute run
    # raised `IndexError: index exceeds dimension bounds` from inside netCDF4 --
    # true, and it names neither the frame nor the file. A comparison that
    # cannot be made should say which one and stop.
    n_frames = a["Times"].shape[0]
    missing = [f for f in frames if f >= n_frames or f < -n_frames]
    if missing:
        raise SystemExit(
            f"these runs carry {n_frames} frames (0..{n_frames - 1}) and "
            f"frames {missing} were asked for. Pass --frames with what the "
            f"files actually hold.")
    cov = coverage(a, b)
    print("  frame  differing fields   new since previous")
    for row in cov:
        new = ", ".join(row["new_since_previous"][:8])
        print(f"  {row['frame']:5d}  {row['differing']:16d}   "
              f"{new[:70]}{'...' if len(new) > 70 else ''}")

    masks = {}
    for name in ("T", "REFL_10CM", "QVAPOR"):
        if name in a.variables:
            x = _num(a[name], args.fixed_mask_frame)
            y = _num(b[name], args.fixed_mask_frame)
            masks[name] = x != y

    # THE ARTIFACT SAYS WHETHER IT WAS GATED. A reader cannot tell from the
    # numbers whether the two runs were one experiment, so the answer travels
    # with them -- including "not checked", which is not the same as "checked
    # and fine".
    doc = {"experiment_gate": gate if gate is not None else {
               "applied": False,
               "why": "compared forecast FILES, not run directories; nothing "
                      "checked that the two runs share a binary, runner, "
                      "namelist or input"},
           "coverage": cov, "fields": [], "precipitation": [],
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

    # The JSON is the measurement; the tables below are a reading of it. It is
    # written FIRST so a formatting fault cannot destroy the result it reports.
    if args.json:
        args.json.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")

    print(f"\n  {'t':>3s} {'signed cell-mean':>17s} {'cancel ratio':>13s} "
          f"{'>1e-3':>9s} {'>1e-2':>9s} {'>1e-1':>9s}")
    for r in doc["precipitation"]:
        print(f"  {r['frame']:>3d} {_fmt(r['signed_gridcell_mean_mm'], '.4e'):>17s} "
              f"{_fmt(r['cancellation_ratio'], '.4f'):>13s} "
              f"{_fmt(r['fraction_over_0.001mm'], '.3%'):>9s} "
              f"{_fmt(r['fraction_over_0.01mm'], '.3%'):>9s} "
              f"{_fmt(r['fraction_over_0.1mm'], '.3%'):>9s}")

    print(f"\n  {'t':>3s} {'in-range':>9s} {'screened p99':>13s} "
          f"{'>20dBZ cells a':>14s} {'cells b':>9s}")
    for r in doc["reflectivity"]:
        print(f"  {r['frame']:>3d} {r['physical_fraction']:8.3%} "
              f"{r.get('screened_p99_dbz', float('nan')):13.4f} "
              f"{r['cells_over_20dbz_a']:14d} {r['cells_over_20dbz_b']:9d}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
