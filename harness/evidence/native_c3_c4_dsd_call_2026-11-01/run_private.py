#!/usr/bin/env python3
"""Isolated, pinned one-step mp137 native C3/C4/DSD diagnostic run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
CANONICAL = Path("/Users/yhlee/KDM6AD-k")
PLAN = CANONICAL / "host/research_evidence/native_qnc_flux_trace_20261026/plans/pr457_v5/experiment_plan.json"
PLAN_SHA = "6032da73badc756c06410669d540daf53491afaa4f9705765ba7f270ac4343f7"
HISTORICAL_ENDPOINT_SHA = "950bc5d67dc8cf4980091ecac19a9b7b1ba94756e83d9bd101180e55863c0bb6"
BUILD_RECEIPT = ROOT / "build/isolated_v6/build_receipt.json"
BUILD_RECEIPT_SHA = "d91ab3f48a78db2d970433862d9069e3368de15483b8b2a87549fc77e0858f2c"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--mode", choices=("baseline", "off_v6", "on_v6"), required=True)
    # Candidate one-rank tile 2 mapping: I=2..233, J=143..281 gives
    # B=(164-2)*139+(242-143). The exporter must prove this against
    # the independent host MP_INPUT words before accepting the coordinate.
    parser.add_argument("--batch-index", type=int, default=22617)
    args = parser.parse_args()
    if digest(PLAN) != PLAN_SHA:
        raise ValueError("historical input plan differs")
    runtime = json.loads(PLAN.read_bytes())["runtime"]
    inputs = [(runtime["origin"]["checkpoint_path"], runtime["origin"]["checkpoint_sha256"]),
              (runtime["namelist_source_path"], runtime["namelist_source_sha256"])]
    inputs += [(item["path"], item["sha256"]) for item in runtime["assets"]]
    for path, expected in inputs:
        if digest(path) != expected:
            raise ValueError("host input pin differs: " + path)
    compiled = {}
    if args.mode != "baseline":
        if digest(BUILD_RECEIPT) != BUILD_RECEIPT_SHA:
            raise ValueError("isolated diagnostic build receipt differs")
        compiled = json.loads(BUILD_RECEIPT.read_bytes())
        if digest(args.library) != compiled["dso_sha256"]:
            raise ValueError("diagnostic DSO differs from build receipt")
        for relative, expected in compiled["source_sha256"].items():
            if digest(ROOT / "build/isolated_v6/source" / relative) != expected:
                raise ValueError("compiled overlay source differs: " + relative)
        if digest(compiled["historical_archive"]) != compiled["historical_archive_sha256"]:
            raise ValueError("historical physics archive differs")
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OMP_THREAD_LIMIT", "VECLIB_MAXIMUM_THREADS"):
        if runtime["environment_without_trace"].get(name) != "1":
            raise ValueError("one-rank one-thread environment differs: " + name)
    if shutil.disk_usage(ROOT).free < 8 * (1 << 30):
        raise OSError("less than 8 GiB free for full-domain host step")
    run = ROOT / "runs" / args.mode
    run.mkdir(parents=True, exist_ok=False)
    scratch = run / "scratch"
    scratch.mkdir()
    capture = run / "capture"
    if args.mode.startswith("on"):
        capture.mkdir()
    sys.path.insert(0, str(args.worktree.resolve()))
    from harness.native_host_transition import NativeCheckpoint, NativeInputs, PinnedFile
    from harness.native_live_stepper import NativeLiveStepper

    origin = NativeCheckpoint.capture(
        runtime["origin"]["checkpoint_path"], expected_time=runtime["start_time"],
        expected_itimestep=runtime["origin"]["itimestep"])
    if origin.file.sha256 != runtime["origin"]["checkpoint_sha256"]:
        raise ValueError("origin checkpoint identity differs")
    env = dict(runtime["environment_without_trace"])
    env["KDM6AD_QNC_LIVE_GUARD"] = "1"
    if args.mode.startswith("on"):
        env.update(KDM6_NATIVE_CAPTURE_DIR=str(capture.resolve()),
                   KDM6_NATIVE_CAPTURE_CALL="all",
                   KDM6_NATIVE_CAPTURE_B=str(args.batch_index),
                   KDM6_NATIVE_CAPTURE_K1="20", KDM6_NATIVE_CAPTURE_K2="22")
    external = NativeInputs(
        namelist=PinnedFile.bind(runtime["namelist_source_path"]),
        assets=tuple((item["case_basename"], PinnedFile.bind(item["path"]))
                     for item in runtime["assets"]),
        environment=tuple(sorted(env.items())),
    )
    with NativeLiveStepper(
        initial=origin, external=external,
        executable=PinnedFile.bind(args.exe.resolve()),
        library=PinnedFile.bind(args.library.resolve()),
        runner=PinnedFile.bind(args.worktree.resolve() / "harness/run_ss_case.py"),
        work_root=scratch, steps=1, dt_seconds=20,
        trace_column=(164, 242), radiation_every_step=True,
        control_family="ANALYSIS_TQ", capture_ready_checkpoint=True,
    ) as stepper:
        ready = stepper.current
        if ready is None or ready.ready is None:
            raise RuntimeError("host did not expose the READY state")
        final = stepper.advance(ready, ())
        result = {
            "schema": "kdm6.native_c3_c4_dsd_run.v1", "mode": args.mode,
            "worktree_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=args.worktree, text=True).strip(),
            "historical_plan_sha256": PLAN_SHA,
            "isolated_build_receipt_sha256": BUILD_RECEIPT_SHA if compiled else None,
            "compiled_source_sha256": compiled.get("source_sha256", {}),
            "source_sha256": {
                relative: digest(args.worktree.resolve() / relative)
                for relative in ("libtorch/CMakeLists.txt", "libtorch/src/coordinator.cpp",
                                 "libtorch/src/runtime.cpp", "libtorch/bridge/kdm6_c_api.cpp",
                                 "harness/native_live_stepper.py", "harness/run_ss_case.py")
            },
            "private_runner_sha256": digest(Path(__file__)),
            "executable_sha256": digest(args.exe), "dso_sha256": digest(args.library),
            "origin_sha256": origin.file.sha256,
            "startup_sha256": ready.checkpoint.file.sha256,
            "endpoint_sha256": final.checkpoint.file.sha256,
            "historical_endpoint_sha256": HISTORICAL_ENDPOINT_SHA,
            "historical_endpoint_match": final.checkpoint.file.sha256 == HISTORICAL_ENDPOINT_SHA,
            "session_record": str(stepper.case / "live_session.json"),
            "capture_files": {p.name: digest(p) for p in sorted(capture.iterdir())} if args.mode.startswith("on") else {},
        }
        path = run / "run_result.json"
        with path.open("x") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
