#!/usr/bin/env python3
"""Build the C++ ABC drivers and persist a decision-grade four-case C++ bundle.

The C++ counterpart of run_fortran_abc.py: it builds the canonical + diagnostic
ABC drivers (selfcheck_build.sh), then runs the shared-fixture four-case check in
persist mode so legacy/conservative A/B/C raw outputs, C sealed containers + run
contract, driver/fixture/parameter hashes and a root manifest survive as an
immutable bundle the four-case comparator can consume (owner item 10) — instead
of the temp root the gate deletes on success.

    run_cpp_abc.py --out <fresh_dir>
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True, help="fresh bundle directory")
    args = ap.parse_args()
    if args.out.exists():
        raise SystemExit(f"output path already exists (refusing): {args.out}")

    build = args.out.with_name(args.out.name + "-build")
    if build.exists():
        raise SystemExit(f"build path already exists (refusing): {build}")
    # selfcheck_build.sh creates the dir itself and REFUSES a pre-existing one, so
    # the parent must exist but the build dir must not — do not mkdir it here.
    build.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["bash", str(HERE / "selfcheck_build.sh"), str(build)], cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit("C++ ABC build failed")

    canonical = build / "abc_canonical_driver"
    diagnostic = build / "abc_diagnostic_driver"
    r = subprocess.run(
        [sys.executable, str(ROOT / "harness" / "g33_fourcase_fixture_check.py"),
         "--canonical-driver", str(canonical),
         "--diagnostic-driver", str(diagnostic), "--out", str(args.out)],
        cwd=ROOT)
    raise SystemExit(r.returncode)


if __name__ == "__main__":
    main()
