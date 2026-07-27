#!/usr/bin/env python3
"""Bind the ACTUAL C++ A/B/C entry path to the shared four-backend fixture.

The fixture-only probe emits the tensors/parameters the driver really constructs;
this checker requires exact equality with the checked-in raw-bit authority. It
then executes canonical A, diagnostic/env-off B and diagnostic/env-on C for both
physics variants and validates C's sealed op evidence using the existing A/B/C
checker. No detached anchor can self-attest: p and qv are actual FIXIN fields.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g33_abc_noninvasiveness as abc  # noqa: E402
import g33_dump as gd  # noqa: E402
import g33_fixture_v1 as fixture  # noqa: E402
import g33_run_env as gre  # noqa: E402
import g33_bundle_io as bio  # noqa: E402
import g33_schedule_probe as gsp  # noqa: E402

EXIT_SKIP, EXIT_DRIVER, EXIT_EVIDENCE, EXIT_FIDELITY = 2, 3, 4, 5
CASE = "fourcase_v1"


def _die(code: int, message: str) -> None:
    print(message, file=sys.stderr, flush=True)
    raise SystemExit(code)


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("KDM6_G33_")}


def _run(driver: Path, argv: list[str], cwd: Path, env: dict[str, str]) -> bytes:
    cwd.mkdir(parents=True, exist_ok=False)
    proc = subprocess.run([str(driver), *argv], cwd=cwd, env=env, capture_output=True)
    if proc.returncode != 0:
        _die(EXIT_DRIVER, f"driver failed rc={proc.returncode}: {driver.name} {argv}\n"
             f"stdout:\n{proc.stdout.decode(errors='replace')}\n"
             f"stderr:\n{proc.stderr.decode(errors='replace')}")
    return proc.stdout


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha_path(p: Path) -> str:
    return _sha(p.read_bytes())



def _schedule_arg(pairs, algo):
    """The ALGO=path entry for `algo`, or None."""
    for raw in pairs:
        text = str(raw)
        if "=" not in text:
            _die(EXIT_SKIP, f"--schedule wants ALGO=path, got {text!r}")
        name, path = text.split("=", 1)
        if name == algo:
            return Path(path)
    return None


def _sealed_schedule(pairs, algo):
    path = _schedule_arg(pairs, algo)
    if path is None:
        return None
    sealed = json.loads(path.read_text())
    gsp.assert_not_evidence(sealed.get("case_id", ""))   # a probe is not a contract
    return sealed


def _probe_reading(pairs, algo):
    """The probe's own mstep vectors, alongside the schedule it produced."""
    path = _schedule_arg(pairs, algo)
    if path is None:
        return None
    stream = path.parent / "probe.sched"
    if not stream.is_file():
        _die(EXIT_SKIP, f"{path} has no probe.sched beside it — the schedule cannot "
                        f"be traced back to the run that produced it")
    return gsp.probe_from_stream(stream.read_text())

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--canonical-driver", type=Path, required=True)
    ap.add_argument("--diagnostic-driver", type=Path, required=True)
    # --out persists a decision-grade C++ A/B/C bundle (analogous to
    # run_fortran_abc) instead of a temp root that is deleted on success — so the
    # four-case comparator has a durable C++ artifact (owner P0-6/item 10).
    ap.add_argument("--out", type=Path, default=None,
                    help="fresh dir; persist the bundle + manifest here")
    ap.add_argument("--fixture-id", default=fixture.DEFAULT_FIXTURE_ID,
                    choices=sorted(fixture.FIXTURES),
                    help="which fixture authority this run uses")
    ap.add_argument("--schedule", type=Path, action="append", default=[],
                    metavar="ALGO=schedule.json",
                    help="sealed schedule from run_cpp_probe.py (pass 2). Required "
                         "for any fixture whose substep count is not 1: the "
                         "declaration cannot be guessed and must not come from the "
                         "other backend.")
    args = ap.parse_args()
    for path in (args.canonical_driver, args.diagnostic_driver):
        if not path.is_file():
            _die(EXIT_SKIP, f"SKIP: ABC driver not found: {path}")

    authority = fixture.load_manifest(fixture.spec(args.fixture_id).manifest)
    B, K = authority["B"], authority["K"]
    abc.CASES[CASE] = (B, K)
    canonical = args.canonical_driver.resolve()
    diagnostic = args.diagnostic_driver.resolve()
    clean = _clean_env()
    persist = args.out is not None
    if persist:
        args.out.mkdir(parents=True, exist_ok=False)
        root = args.out
    else:
        root = Path(tempfile.mkdtemp(prefix="g33-fourcase-fixture-"))
    bundle: dict = {"algorithms": {}}
    try:
        for algo in abc.ALGORITHMS:
            raw_a = _run(canonical, [algo, CASE, "--fixture-only"],
                         root / f"{algo}-fixture-A", clean)
            raw_b = _run(diagnostic, [algo, CASE, "--fixture-only"],
                         root / f"{algo}-fixture-B", clean)
            got_a = fixture.parse_fixture_protocol(raw_a, authority)
            got_b = fixture.parse_fixture_protocol(raw_b, authority)
            if raw_a != raw_b or got_a != got_b:
                _die(EXIT_FIDELITY, f"canonical/diagnostic fixture stream differs: {algo}")

            out_a = _run(canonical, [algo, CASE], root / f"{algo}-A", clean)
            out_b = _run(diagnostic, [algo, CASE], root / f"{algo}-B", clean)
            abc.parse_output(out_a, algo, CASE)
            abc.parse_output(out_b, algo, CASE)
            if out_a != out_b:
                _die(EXIT_FIDELITY, f"shared fixture A!=B: {algo}")

            schedule = _sealed_schedule(args.schedule, algo) or abc._schedule(algo, CASE)
            evidence = root / f"{algo}-C-evidence"
            env_c = gre.build_env(
                schedule, evidence, binary=diagnostic,
                column_map=[[i, 0, i, i] for i in range(B)],
                run_uuid=f"fourcase-{algo}-{uuid.uuid4().hex[:10]}",
                column_layout_id=f"fourcase-v1-{B}col")
            out_c = _run(diagnostic, [algo, CASE], root / f"{algo}-C",
                         {**clean, **env_c})
            abc.parse_output(out_c, algo, CASE)
            if out_a != out_c:
                _die(EXIT_FIDELITY, f"shared fixture A!=C: {algo}")
            diag = abc._validate_c_evidence(evidence, env_c, schedule)
            # REPRODUCE GATE: the sealed run must have made the same scheduling
            # decisions the probe did. Otherwise the contract describes one
            # execution and the evidence another.
            probe_read = _probe_reading(args.schedule, algo)
            if probe_read is not None:
                try:
                    gsp.assert_reproduced(probe_read, gsp.read_probe(
                        bio.verify_cpp_evidence(evidence, algo)["containers"]))
                except (gsp.ProbeError, bio.BundleError) as e:
                    _die(EXIT_EVIDENCE, f"FAIL: {algo} evidence does not reproduce "
                                        f"the probe schedule: {e}")
                print(f"  reproduced the probe schedule exactly ({algo})")
            print(f"FOURCASE PASS {algo} fixture={got_a[0][:16]} "
                  f"params={got_a[1][:16]} containers={diag['containers']} "
                  f"mstep={diag['mstep_min']}..{diag['mstep_max']}")
            if persist:
                for name, raw in (("A", out_a), ("B", out_b), ("C", out_c)):
                    (root / f"{algo}-{name}" / "stdout.abc").write_bytes(raw)
                bundle["algorithms"][algo] = {
                    "fixture_sha256": got_a[0], "parameter_sha256": got_a[1],
                    "abc_equal": True,
                    "stdout_sha256": {"A": _sha(out_a), "B": _sha(out_b), "C": _sha(out_c)},
                    "containers": diag["containers"],
                    "mstep_min": diag["mstep_min"], "mstep_max": diag["mstep_max"],
                    "evidence_dir": f"{algo}-C-evidence",
                }
        print("FOURCASE FIXTURE PASS — actual C++ A/B/C tensors and common "
              "parameters match the shared raw-bit authority")
    except (ValueError, gd.G33Corruption) as exc:
        print(f"(fourcase evidence preserved at {root})", file=sys.stderr)
        _die(EXIT_EVIDENCE, f"shared fixture evidence invalid: {exc}")
    except BaseException:
        print(f"(fourcase evidence preserved at {root})", file=sys.stderr)
        raise
    else:
        if persist:
            manifest = {
                "schema_version": 1,
                "fixture_id": authority["fixture_id"],
                "fixture_manifest_sha256": fixture.manifest_sha256(authority),
                "canonical_driver_sha256": _sha_path(canonical),
                "diagnostic_driver_sha256": _sha_path(diagnostic),
                "os": platform.platform(), "architecture": platform.machine(),
                "python_version": platform.python_version(),
                "algorithms": bundle["algorithms"],
            }
            tmp = root / "cpp_abc_manifest.json.tmp"
            tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True))
            tmp.replace(root / "cpp_abc_manifest.json")
            print(f"C++ A/B/C bundle persisted -> {root}/cpp_abc_manifest.json")
        else:
            shutil.rmtree(root)


if __name__ == "__main__":
    main()
