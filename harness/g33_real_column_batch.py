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
    den = p / (RD * temp * (1.0 + 0.608 * qv))
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
            "nr_levels": int((g("QNRAIN")[:, j, i] > 0).sum())}


def residuals(build_root: Path, arm: str) -> dict:
    """Build and run one arm on the manifest as it currently stands."""
    import g33_number_basis as nb
    out = build_root / arm
    b = subprocess.run(
        ["bash", str(HERE / "g33_fortran" / "refine_build.sh"), str(out),
         f"--fixture=g33_fixture_{FIXTURE_ID}", f"--algo={arm}", "--nflux"],
        capture_output=True, text=True, cwd=REPO)
    if b.returncode != 0:
        raise SystemExit(f"{arm}: build failed\n{b.stdout[-800:]}{b.stderr[-800:]}")
    r = subprocess.run([str(out / "g33_refine_driver"), "12", "rezero", "1"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"{arm}: driver crashed\n{r.stderr[-800:]}")
    return nb.from_stream(r.stdout, "nr")[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("state", type=Path)
    ap.add_argument("--columns", type=int, default=12)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args()

    keep = MANIFEST.read_text()          # the committed column, restored at the end
    rows = []
    try:
        for j, i in candidates(a.state, a.columns):
            meta = write_manifest(a.state, j, i)
            gen = subprocess.run([sys.executable, str(HERE / "g33_fixture_v1.py"),
                                  "--write", f"--fixture-id={FIXTURE_ID}"],
                                 capture_output=True, text=True, cwd=REPO)
            if gen.returncode != 0:
                print(f"  ({j},{i}) refused by the manifest: "
                      f"{gen.stderr.strip().splitlines()[-1][:90]}")
                continue
            with tempfile.TemporaryDirectory(prefix="g33-col.") as td:
                try:
                    leg = residuals(Path(td), "legacy")
                    nm = residuals(Path(td), "nmass")
                except SystemExit as exc:
                    print(f"  ({j},{i}) {exc}")
                    continue
            row = dict(meta,
                       legacy_moist=leg["moist"] / leg["start_moist"],
                       legacy_dry=leg["dry"] / leg["start_dry"],
                       armn_moist_xfer=nm["moist_xfer"] / nm["start_moist"],
                       armn_dry=nm["dry"] / nm["start_dry"],
                       armn_dry_xfer=nm["dry_xfer"] / nm["start_dry"])
            row["fraction_left"] = abs(row["armn_dry"]) / abs(row["legacy_dry"]) \
                if row["legacy_dry"] else None
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
    fr = sorted(r["fraction_left"] for r in rows if r["fraction_left"] is not None)
    n = len(fr)
    summary = {"columns": n, "median": fr[n // 2], "min": fr[0], "max": fr[-1]}
    print(f"\n  {n} columns: Arm N leaves median {summary['median']:.4%} "
          f"(min {summary['min']:.4%}, max {summary['max']:.4%})")
    if a.json:
        a.json.write_text(json.dumps({"summary": summary, "columns": rows},
                                     indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
