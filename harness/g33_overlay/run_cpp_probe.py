#!/usr/bin/env python3
"""Pass 1 of the two-pass C++ schedule: run the probe, derive the contract, seal it.

    run_cpp_probe.py --diagnostic-driver DRIVER --algo legacy \
        --fixture-id arithmetic_multisubcycle_v1 --out probe_dir

The C++ expectation manifest has to declare `loops` and `mstepmax_{chain}[loop]`
before the run, but the substep count is knowable only BY running. The sealed
container path cannot answer that — it refuses any container id that was not declared
first — so this drives the separate probe channel (`KDM6_G33_SCHED_PROBE`), which
writes raw operands to stdout and touches none of the sealed machinery.

What comes out is NOT evidence and is written as such: no run identity, no binary
binding, no descriptors. It exists to produce `schedule.json`, which pass 2 seals and
runs against for real.

Two properties this enforces rather than assumes:

  * the run's own `mstep_native` must equal what Python re-derives from the fall
    speeds it dumped alongside it — including `work1_qs`/`work1_qg`, which the sealed
    evidence omits and which frequently decide the substep count;
  * with `--check-noninvasive`, the ABC output with the probe on must be byte-identical
    to the same driver with it off. A probe that perturbed the run it measures would
    seal a schedule for a different execution than the one under test.

Nothing here reads the Fortran leg. If the two backends ever disagree on mstep, the
C++ contract is still built from C++ operands and the disagreement reaches the
comparator as INCONCLUSIVE instead of being sealed away.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import g33_abc_noninvasiveness as abc   # noqa: E402
import g33_fixture_v1 as gfx           # noqa: E402
import g33_schedule_probe as gsp       # noqa: E402

CASE = "fourcase_v1"
SUBCYCLE_SECONDS = 120.0               # the cloud sub-cycle threshold: loops=ceil(dt/it)


def _clean_env() -> dict:
    """No KDM6_G33_* inherited: the probe must run with the sealed path dormant."""
    return {k: v for k, v in os.environ.items() if not k.startswith("KDM6_G33_")}


def _run(driver: Path, algo: str, env: dict) -> str:
    proc = subprocess.run([str(driver), algo, CASE], cwd=ROOT, env=env,
                          capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(f"probe driver failed ({algo}):\n"
                         f"{proc.stderr.decode('utf-8', 'replace')[:2000]}")
    return proc.stdout.decode("ascii", "replace")


def step_schedule(authority: dict) -> tuple[int, float]:
    """(loops, dtcld) implied by the fixture's own dt — never passed in by hand."""
    import struct
    dt = struct.unpack(">f", bytes.fromhex(authority["common_parameters"]["dt"]))[0]
    loops = max(1, -(-int(dt) // int(SUBCYCLE_SECONDS)))       # ceil
    return loops, dt / loops


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="C++ schedule probe (pass 1 of 2)")
    ap.add_argument("--diagnostic-driver", type=Path, required=True)
    ap.add_argument("--algo", required=True, choices=["legacy", "conservative"])
    ap.add_argument("--fixture-id", default=gfx.DEFAULT_FIXTURE_ID,
                    choices=sorted(gfx.FIXTURES))
    ap.add_argument("--out", type=Path, required=True, help="fresh directory")
    ap.add_argument("--check-noninvasive", action="store_true",
                    help="prove the probe does not perturb the run it measures")
    a = ap.parse_args(argv)

    if not a.diagnostic_driver.is_file():
        raise SystemExit(f"driver not found: {a.diagnostic_driver}")
    a.out.mkdir(parents=True)
    _, authority = gfx.load_fixture(a.fixture_id)
    loops, dtcld = step_schedule(authority)

    clean = _clean_env()
    raw = _run(a.diagnostic_driver, a.algo, {**clean, "KDM6_G33_SCHED_PROBE": "1"})
    sched_lines = [ln for ln in raw.splitlines() if ln.startswith("KDM6SCHED ")]
    (a.out / "probe.sched").write_text("\n".join(sched_lines) + "\n")

    if a.check_noninvasive:
        off = _run(a.diagnostic_driver, a.algo, clean)
        on = "\n".join(ln for ln in raw.splitlines() if not ln.startswith("KDM6SCHED "))
        if off.strip() != on.strip():
            raise SystemExit("the probe PERTURBS the run it measures — a schedule "
                             "sealed from it would describe a different execution")
        print("noninvasive: ABC stream byte-identical with the probe on and off")

    probe = gsp.probe_from_stream("\n".join(sched_lines))
    # Build the base from the CANONICAL schedule builder and let the probe override
    # only what it measured. Hand-rolling the dict here would silently drop whatever
    # keys the contract gains later — qcrmin and instrumented_stages already.
    abc.CASES[CASE] = (authority["B"], authority["K"])
    base = abc._schedule(a.algo, CASE, loops=loops, dtcld=dtcld)
    sealed = gsp.sealed_schedule(base, probe)
    if sealed["loops"] != loops:
        raise SystemExit(f"probe ran {sealed['loops']} outer loops but the fixture's "
                         f"dt implies {loops} — the run is not the declared problem")

    (a.out / "schedule.json").write_text(json.dumps(sealed, indent=2, sort_keys=True)
                                         + "\n")
    (a.out / "switch_margin.json").write_text(json.dumps(
        {f"L{k[0]}/{k[1]}/col{k[2]}": v
         for k, v in sorted(gsp.switch_margin("\n".join(sched_lines)).items())},
        indent=2, sort_keys=True) + "\n")
    print(f"PROBE {a.algo} fixture={a.fixture_id} loops={sealed['loops']} "
          f"mstepmax_main={sealed['mstepmax_main']} "
          f"mstepmax_ice={sealed['mstepmax_ice']}")
    print(f"  derivation from raw fall speeds == the run's own mstep_native")
    print(f"  wrote {a.out}/schedule.json (NOT evidence — pass 2 seals and re-runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
