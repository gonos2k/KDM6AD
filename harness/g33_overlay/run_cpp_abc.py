#!/usr/bin/env python3
"""Build the C++ ABC drivers and persist a decision-grade four-case C++ bundle.

The C++ counterpart of run_fortran_abc.py: it builds the canonical + diagnostic
ABC drivers (selfcheck_build.sh), then runs the shared-fixture four-case check in
persist mode so legacy/conservative A/B/C raw outputs, C sealed containers + run
contract, driver/fixture/parameter hashes and a root manifest survive as an
immutable bundle the four-case comparator can consume (owner item 10) — instead
of the temp root the gate deletes on success.

    run_cpp_abc.py --out <fresh_dir> [--fixture-id ID]

Runs the WHOLE two-pass sequence: build, probe each algorithm, seal the derived
schedules, produce the A/B/C evidence, require it to reproduce the probe, and persist
the probe lineage with the bundle. Previously it called the checker directly, which
falls back to a one-loop default schedule when none is given — so a multi-subcycle
fixture could be driven through this entry point and sealed against a contract its
own run could not satisfy.
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import g33_fixture_v1 as gfx      # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True, help="fresh bundle directory")
    ap.add_argument("--fixture-id", default=gfx.DEFAULT_FIXTURE_ID,
                    choices=sorted(gfx.FIXTURES),
                    help="selects BOTH the build's fixture header and the "
                         "checker's authority")
    args = ap.parse_args()
    if args.out.exists():
        raise SystemExit(f"output path already exists (refusing): {args.out}")

    build = args.out.with_name(args.out.name + "-build")
    if build.exists():
        raise SystemExit(f"build path already exists (refusing): {build}")
    # selfcheck_build.sh creates the dir itself and REFUSES a pre-existing one, so
    # the parent must exist but the build dir must not — do not mkdir it here.
    build.parent.mkdir(parents=True, exist_ok=True)
    spec = gfx.spec(args.fixture_id)
    # The build selects the fixture HEADER and the checker selects the AUTHORITY.
    # Driving both from one id is what stops a driver built for one fixture being
    # checked against another's authority.
    build_cmd = ["bash", str(HERE / "selfcheck_build.sh"), str(build)]
    if spec.cpp_define:
        build_cmd.append(f"--fixture={spec.cpp_define}")
    r = subprocess.run(build_cmd, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit("C++ ABC build failed")

    canonical = build / "abc_canonical_driver"
    diagnostic = build / "abc_diagnostic_driver"

    # PASS 1, per algorithm. Without it the checker falls back to a one-loop default
    # schedule, so a multi-subcycle fixture would be sealed with a contract its own
    # run cannot satisfy. The probe is the only place mstep can be derived from all
    # four fall speeds, so it is run for every fixture rather than only the ones
    # believed to need it.
    schedule_args = []
    for algo in ("legacy", "conservative"):
        probe_dir = args.out.parent / f"{args.out.name}-probe-{algo}"
        if probe_dir.exists():
            raise SystemExit(f"probe path already exists (refusing): {probe_dir}")
        r = subprocess.run(
            [sys.executable, str(HERE / "run_cpp_probe.py"),
             "--diagnostic-driver", str(diagnostic), "--algo", algo,
             "--fixture-id", args.fixture_id, "--out", str(probe_dir),
             "--check-noninvasive"],
            cwd=ROOT)
        if r.returncode != 0:
            raise SystemExit(f"C++ schedule probe failed ({algo})")
        schedule_args += ["--schedule", f"{algo}={probe_dir / 'schedule.json'}"]

    # PASS 2: seal those schedules, run for real, and require the evidence to
    # reproduce them. The probe travels into the bundle from here.
    r = subprocess.run(
        [sys.executable, str(ROOT / "harness" / "g33_fourcase_fixture_check.py"),
         "--canonical-driver", str(canonical),
         "--diagnostic-driver", str(diagnostic), "--out", str(args.out),
         "--fixture-id", args.fixture_id, *schedule_args],
        cwd=ROOT)
    raise SystemExit(r.returncode)


if __name__ == "__main__":
    main()
