#!/usr/bin/env python3
"""Many real columns, one at a time, through the actual kernel.

`FINDING_real_column_replay_v1` ran one column of the operational case and
found Arm N leaving 1.88 % of the legacy dry defect -- against a coefficient
estimate of 1.92-1.98 % over the whole domain. One column is an instance, which
is why that fixture's ceiling is STRUCTURAL_ONLY, and a single agreement can be
a coincidence.

This is the same experiment over a SAMPLE. The fixture data are compile-time
constants, so each column needs its own build: the manifest is rewritten, the
generator run, both arms built, both run, and the residuals taken. Slow and
completely mechanical.

WHAT IT CANNOT FIX. The columns come from one case at one time, so this is a
sample of THAT atmosphere and not of atmospheres. It answers "is 1.88 %
typical of this state" and nothing wider.

    python3 harness/g33_real_column_batch.py <wrfout> --columns 12 --json out.json
"""
from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parent
RD, CP, P0, G = 287.04, 1004.5, 1.0e5, 9.81
FIXTURE_ID = "lc05_column_v1"
MANIFEST = HERE / "g33_fixture_lc05_column_v1.json"


def candidates(path: Path, want: int, field: str = "QNRAIN", levels: int = 6):
    """Columns carrying `field` over at least `levels` levels, spread evenly.

    Evenly over the SORTED candidate list rather than at random: the point is a
    spread across the domain's regimes, and a seeded random pick would be one
    more thing to have to reproduce.

    NOT STRATIFIED. Row-major order spreads the sample spatially and balances
    nothing -- not land against sea, not moisture-gradient quantile, not
    precipitation intensity, not the size of the legacy defect. So the
    distribution this produces is a deterministic spatial sample of one state
    and is NOT an unbiased estimate of that state's columns (owner review §8.3).
    """
    import netCDF4
    import numpy as np
    d = netCDF4.Dataset(str(path))
    n = np.asarray(d[field][-1], dtype="float64")
    hits = np.argwhere((n > 0).sum(axis=0) >= levels)
    if len(hits) == 0:
        raise SystemExit(f"no column carries {field} over {levels} levels")
    step = max(1, len(hits) // want)
    return [tuple(int(v) for v in hits[i]) for i in range(0, len(hits), step)][:want]


def write_manifest(path: Path, j: int, i: int) -> dict:
    """Rewrite the committed manifest for one column. Returns its own summary."""
    import netCDF4
    import numpy as np
    d = netCDF4.Dataset(str(path))
    g = lambda k: np.asarray(d[k][-1], dtype="float64")      # noqa: E731
    K = d.dimensions["bottom_top"].size
    p = (g("P") + g("PB"))[:, j, i]
    th = (g("T") + 300.0)[:, j, i]
    qv = g("QVAPOR")[:, j, i]
    temp = th * (p / P0) ** (RD / CP)
    ph = (g("PH") + g("PHB"))[:, j, i]
    dz = np.diff(ph) / G
    # THE MODEL'S OWN DENSITY, not a thermodynamic estimate. WRF's hydrostatic
    # relation makes `rho_d * dz = mu_d |d(eta)| / g` exact in its own
    # discretisation, and the host forms the `rho` it hands to microphysics as
    # `rho_d * (1 + qv)` (module_big_step_utilities_em.F:4856). The first
    # version of this used `p / (Rd T (1 + 0.608 qv))`, which differs from the
    # canonical route by a median 2.3e-03 and up to 31 % on this state
    # (FINDING_number_basis_gap_v1). The replay column now carries the density
    # the kernel would actually have been given (owner review §10.2).
    mu = (np.asarray(d["MU"][-1], dtype="float64")
          + np.asarray(d["MUB"][-1], dtype="float64"))[j, i]
    dnw = np.asarray(d["DNW"][-1], dtype="float64")
    rho_d = (mu * np.abs(dnw)) / G / dz
    den = rho_d * (1.0 + qv)
    pii = (p / P0) ** (RD / CP)
    f2b = lambda v: struct.pack(">f", float(v)).hex()        # noqa: E731
    flip = lambda a: list(a[::-1])                           # WRF k=0 is BOTTOM
    src = json.loads(MANIFEST.read_text())
    fields = {}
    for nm, arr in (("th", th), ("qv", qv), ("qc", g("QCLOUD")[:, j, i]),
                    ("qr", g("QRAIN")[:, j, i]), ("qi", g("QICE")[:, j, i]),
                    ("qs", g("QSNOW")[:, j, i]), ("qg", g("QGRAUP")[:, j, i]),
                    ("nccn", g("QNCCN")[:, j, i]), ("nc", g("QNCLOUD")[:, j, i]),
                    ("ni", g("QNICE")[:, j, i]), ("nr", g("QNRAIN")[:, j, i]),
                    ("rho", den), ("pii", pii), ("p", p), ("delz", dz)):
        fields[nm] = [f2b(v) for v in flip(arr)]
    fields["bg"] = [f2b(0.0)] * K
    out = dict(src)
    out.update({"B": 1, "K": K, "fields": fields,
                "xland": [f2b(g("XLAND")[j, i])]})
    MANIFEST.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    return {"j": j, "i": i, "xland": float(g("XLAND")[j, i]),
            "qv_surface": float(qv[0]), "qv_top": float(qv[-1]),
            "nr_levels": int((g("QNRAIN")[:, j, i] > 0).sum()),
            "density": "canonical mu_d|d(eta)|/g, rho_m = rho_d(1+qv)"}


def residuals(build_root: Path, arm: str, nsplits=(12,)) -> dict:
    """Build one arm on the manifest as it currently stands; run it once per
    `nsplit`. The call step is `60 s / nsplit`, so 12, 6, 3, 2 give 5, 10, 20
    and 30 s -- the operational call is 20 s. `nsplit` is a runtime argument,
    so the timestep matrix costs no extra builds (owner review §9)."""
    import g33_number_basis as nb
    out = build_root / arm
    b = subprocess.run(
        ["bash", str(HERE / "g33_fortran" / "refine_build.sh"), str(out),
         f"--fixture=g33_fixture_{FIXTURE_ID}", f"--algo={arm}", "--nflux"],
        capture_output=True, text=True, cwd=REPO)
    if b.returncode != 0:
        raise SystemExit(f"{arm}: build failed\n{b.stdout[-800:]}{b.stderr[-800:]}")
    got = {}
    for n in nsplits:
        r = subprocess.run([str(out / "g33_refine_driver"), str(n), "rezero", "1"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"{arm} nsplit={n}: driver crashed\n{r.stderr[-800:]}")
        got[n] = nb.from_stream(r.stdout, "nr")[1]
    return got


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("state", type=Path)
    ap.add_argument("--columns", type=int, default=12)
    ap.add_argument("--nsplits", default="12",
                    help="comma-separated; 12,6,3,2 is the 5/10/20/30 s matrix")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args()

    # THE COMMITTED MANIFEST IS OVERWRITTEN WHILE THIS RUNS. A `git add -A`
    # issued mid-batch stages a transient column as if it were the fixture --
    # which happened once, and was caught only because the status was read.
    # Two defences: refuse to start if the manifest already differs from HEAD
    # (a crashed run left it dirty), and say so loudly while running.
    dirty = subprocess.run(["git", "status", "--porcelain", "--", str(MANIFEST)],
                           capture_output=True, text=True, cwd=REPO).stdout.strip()
    if dirty:
        raise SystemExit(f"{MANIFEST.name} is modified relative to HEAD; a "
                         f"previous batch did not restore it. Inspect before "
                         f"running another.")
    print(f"  NOTE: {MANIFEST.name} is rewritten per column until this finishes; "
          f"do not stage it meanwhile")
    keep = MANIFEST.read_text()          # the committed column, restored at the end
    # REJECTED COLUMNS ARE PART OF THE RESULT. A sample reported only through
    # what survived cannot be checked for survivorship bias: if the columns that
    # fail are the ones with the largest defect, the distribution is a
    # selection. Every requested column is recorded with its verdict.
    rows, rejected = [], []
    try:
        for j, i in candidates(a.state, a.columns):
            meta = write_manifest(a.state, j, i)
            gen = subprocess.run([sys.executable, str(HERE / "g33_fixture_v1.py"),
                                  "--write", f"--fixture-id={FIXTURE_ID}"],
                                 capture_output=True, text=True, cwd=REPO)
            if gen.returncode != 0:
                why = gen.stderr.strip().splitlines()[-1][:120]
                rejected.append(dict(meta, stage="manifest", reason=why))
                print(f"  ({j},{i}) refused by the manifest: {why[:90]}")
                continue
            nsplits = tuple(int(v) for v in a.nsplits.split(","))
            with tempfile.TemporaryDirectory(prefix="g33-col.") as td:
                try:
                    legs = residuals(Path(td), "legacy", nsplits)
                    nms = residuals(Path(td), "nmass", nsplits)
                except SystemExit as exc:
                    rejected.append(dict(meta, stage="build_or_run",
                                         reason=str(exc)[:200]))
                    print(f"  ({j},{i}) {exc}")
                    continue
            leg, nm = legs[nsplits[0]], nms[nsplits[0]]
            row = dict(meta,
                       # the per-timestep matrix, ratio only: what the review
                       # asked to see is whether the FRACTION is timestep-
                       # invariant across the sample, as it was on one column
                       timestep_matrix={
                           f"{60 // n}s": (abs(nms[n]["dry_xfer"] / nms[n]["start_dry"])
                                           / abs(legs[n]["dry_xfer"] / legs[n]["start_dry"]))
                           for n in nsplits if legs[n]["dry_xfer"]},
                       legacy_moist=leg["moist"] / leg["start_moist"],
                       legacy_dry=leg["dry"] / leg["start_dry"],
                       # BOTH READERS, and `legacy_dry_xfer` was missing
                       # entirely -- so the ratio could only ever be formed
                       # from the recovered pair (owner review §10.1).
                       legacy_dry_xfer=leg["dry_xfer"] / leg["start_dry"],
                       legacy_moist_xfer=leg["moist_xfer"] / leg["start_moist"],
                       armn_moist_xfer=nm["moist_xfer"] / nm["start_moist"],
                       armn_dry=nm["dry"] / nm["start_dry"],
                       armn_dry_xfer=nm["dry_xfer"] / nm["start_dry"])
            row["fraction_left"] = abs(row["armn_dry"]) / abs(row["legacy_dry"]) \
                if row["legacy_dry"] else None
            row["fraction_left_xfer"] = (
                abs(row["armn_dry_xfer"]) / abs(row["legacy_dry_xfer"])
                if row["legacy_dry_xfer"] else None)
            rows.append(row)
            print(f"  ({j:3d},{i:3d}) xland={meta['xland']:.0f} "
                  f"legacy_dry {row['legacy_dry']:11.4e}  "
                  f"armN_dry {row['armn_dry']:11.4e}  "
                  f"leaves {row['fraction_left']:.4%}")
    finally:
        MANIFEST.write_text(keep)
        subprocess.run([sys.executable, str(HERE / "g33_fixture_v1.py"),
                        "--write", f"--fixture-id={FIXTURE_ID}"],
                       capture_output=True, text=True, cwd=REPO)

    if not rows:
        raise SystemExit("no column produced a usable pair")
    import statistics
    fr = sorted(r["fraction_left"] for r in rows if r["fraction_left"] is not None)
    fx = sorted(r["fraction_left_xfer"] for r in rows
                if r.get("fraction_left_xfer") is not None)
    n = len(fr)
    # `fr[n // 2]` is the UPPER MIDDLE value on an even sample, not the median.
    # With 22 columns that is the 12th value where the median is the mean of the
    # 11th and 12th -- a small difference and the wrong name for it.
    summary = {"columns": n, "median": statistics.median(fr),
               "upper_middle": fr[n // 2], "min": fr[0], "max": fr[-1],
               "p25": statistics.quantiles(fr, n=4)[0] if n >= 4 else None,
               "p75": statistics.quantiles(fr, n=4)[2] if n >= 4 else None,
               # The ACTUAL-transfer statistic beside the recovered one. They
               # are different quantities and the headline should say which.
               "median_xfer": statistics.median(fx) if fx else None,
               "min_xfer": fx[0] if fx else None,
               "max_xfer": fx[-1] if fx else None,
               "columns_xfer": len(fx)}
    print(f"\n  {n} columns, RECOVERED transfers: Arm N leaves median "
          f"{summary['median']:.4%} (min {summary['min']:.4%}, "
          f"max {summary['max']:.4%})")
    if fx:
        print(f"  {len(fx)} columns, ACTUAL XFER:       median "
              f"{summary['median_xfer']:.4%} (min {summary['min_xfer']:.4%}, "
              f"max {summary['max_xfer']:.4%})")
    if rejected:
        print(f"  {len(rejected)} column(s) rejected; reasons in the JSON")
    if a.json:
        a.json.write_text(json.dumps(
            {"summary": summary, "columns": rows, "rejected": rejected,
             "requested": len(rows) + len(rejected)},
            indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
