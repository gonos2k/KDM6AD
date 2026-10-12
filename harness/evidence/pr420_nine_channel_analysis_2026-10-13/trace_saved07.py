#!/usr/bin/env python3
"""One saved07 profile, two isolated control/trace H calls; no M/optimizer.

Retain the existing worker's raw direct/K files for numerical noninterference.
The prepared snapshot is preserved; only copied run scripts select executables.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
PACKET = Path(__file__).resolve().parent
OLD = ROOT / "harness/evidence/pr417_hourly_rttov_2026-10-12"
PRIVATE = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr420_nine_channel_20261013")
TRACE_BUILD = PRIVATE / "rttov_trace"
RUN = PRIVATE / "SAVED07_TRACE_ONCE"
sys.path.insert(0, str(ROOT / "oracle"))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(p, name):
    s = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def write(p, obj):
    with Path(p).open("x") as f:
        json.dump(obj, f, indent=2, allow_nan=False)
        f.write("\n")


class RetainCase:
    """Explicit diagnostic output retention; no change to numeric worker code."""
    def __init__(self, **kwargs):
        self.name = tempfile.mkdtemp(**kwargs)
    def __enter__(self):
        return self.name
    def __exit__(self, *_args):
        return False


def retained_worker(job):
    from kdm6.obs import allsky_shard as worker
    original = worker.tempfile.TemporaryDirectory
    worker.tempfile.TemporaryDirectory = RetainCase
    try:
        return worker._allsky_columns_worker(job)
    finally:
        worker.tempfile.TemporaryDirectory = original


class RetainingPool:
    def __init__(self, pool):
        self.pool = pool
    def map(self, _fn, jobs):
        return self.pool.map(retained_worker, jobs)


def main():
    old = json.loads((OLD / "PLAN.json").read_text())
    build = json.loads((TRACE_BUILD / "BUILD_CONTEXT.json").read_text())
    if (not __debug__ or os.environ.get("PYTHONOPTIMIZE") != "0"
            or sys.executable != old["python_executable"]
            or any(os.environ.get(k) != v for k, v in old["thread_environment"].items())):
        raise ValueError("declared interpreter/assertions/one-thread environment required")
    if RUN.exists():
        raise FileExistsError("single saved07 trace output exists; no retry/overwrite")
    source = Path(old["time_contexts"]["7"]["H_config"]["fixture_case_dir"])
    # Original raw template is not recovered bit-for-bit; this call consumes
    # the actual hash-bound prepared07 snapshot fixture and saved input bundle.
    pins = {str(Path(__file__).resolve()): sha(__file__),
            str((OLD / "PLAN.json").resolve()): sha(OLD / "PLAN.json"),
            str((OLD / "prepare_hourly_h.py").resolve()): sha(OLD / "prepare_hourly_h.py"),
            str(Path(old["private_npz"])): old["time_inputs_npz_sha256"],
            str(TRACE_BUILD / "BUILD_CONTEXT.json"): sha(TRACE_BUILD / "BUILD_CONTEXT.json")}
    prior_result = ROOT / "harness/evidence/pr418_nine_channels_2026-10-12/RESULT.json"
    pins[str(prior_result.resolve())] = sha(prior_result)
    pins.update({p: v for p, v in old["fixture_hashes"].items() if Path(p).is_relative_to(source)})
    for path, digest in build["runtime_libraries"].items():
        pins[path] = digest
    for relative in ("oracle/kdm6/obs/allsky_shard.py", "oracle/kdm6/obs/model_profile_builder.py",
                     "oracle/kdm6/obs/rttov_case_writer.py", "oracle/kdm6/obs/rttov_runner.py",
                     "oracle/kdm6/obs/rttov_input_builder.py", "oracle/kdm6/obs/rttov_obs_operator.py",
                     "oracle/kdm6/obs/ami_bt_coordinate.py", "oracle/kdm6/rttov_bridge.py",
                     "oracle/kdm6/da_driver.py", "oracle/kdm6/state.py"):
        path = ROOT / relative
        pins[str(path.resolve())] = sha(path)
    for path, record in old["external_assets"].items():
        if not Path(path).is_relative_to(Path("/private/tmp/KDM6AD-viirs-native-run-20261007")):
            pins[path] = record["sha256"]
    for p, v in pins.items():
        if sha(p) != v:
            raise ValueError("saved snapshot/input/build changed: " + p)
    executables = {
        "control": TRACE_BUILD / "src/bin/rttov_test_control.exe",
        "instrumented": TRACE_BUILD / "src/bin/rttov_test_instrumented.exe"}
    for name, exe in executables.items():
        if sha(exe) != build["executables"][name]["sha256"]:
            raise ValueError("staged executable changed: " + name)
    RUN.mkdir(mode=0o700)
    fixtures = {}
    for name, exe in executables.items():
        target = RUN / (name + "_fixture")
        shutil.copytree(source, target)
        script = target / "out/run.sh"
        lines = script.read_text().splitlines()
        matches = [i for i, line in enumerate(lines) if "rttov_test.exe >" in line]
        if len(matches) != 1:
            raise ValueError("expected one executable in copied run script")
        lines[matches[0]] = " " + str(exe) + " > rttov_test.log 2>&1"
        if name == "instrumented":
            index = lines.index(". ./env.sh")
            lines.insert(index + 1, "export KDM6AD_EXT_TRACE='" + str(RUN / "EXT_TRACE.txt") + "'")
        script.write_text("\n".join(lines) + "\n")
        fixtures[name] = str(target)
        pins.update({str(p): sha(p) for p in target.rglob("*") if p.is_file()})
    plan = {"channels": [8, 9], "saved_time_index": 7, "logical_H_calls": 2,
            "M_optimizer_native_calls": 0, "fixture_copies": fixtures,
            "bindings": pins, "executables": {n: {"path": str(p), "sha256": sha(p)} for n, p in executables.items()},
            "output_retention_only": True, "threads": old["thread_environment"]}
    write(PACKET / "TRACE_PLAN.json", plan)
    write(RUN / "STARTED_ONCE.json", {"plan_sha256": sha(PACKET / "TRACE_PLAN.json")})
    import numpy as np
    import torch
    from kdm6.obs.allsky_shard import sharded_allsky
    torch.set_num_threads(1)
    prep = load(OLD / "prepare_hourly_h.py", "pr420_saved07_context")
    events = []
    try:
        with mp.get_context("spawn").Pool(1) as pool:
            for name in ("control", "instrumented"):
                ctx = prep.load_context(old, 7)
                cfg = dict(ctx["rttov_cfg"], channels=(8, 9), fixture_case_dir=fixtures[name])
                target = torch.zeros((1, 2), dtype=torch.float64)
                out = sharded_allsky(ctx["state"], ctx["forcing"], torch.tensor([0]),
                    target, torch.ones_like(target), ctx["xland"], cfg,
                    str(RUN / name), pool=RetainingPool(pool), n_workers=1, grad=False)
                event = {"name": name, "BT_K": out["bt"].tolist(), "rad_quality": out["rq"].tolist()}
                events.append(event)
                write(RUN / (name + ".json"), event)
                print(json.dumps(event), flush=True)
        for p, v in pins.items():
            if sha(p) != v:
                raise ValueError("bound input/source changed during calls: " + p)
        for name, exe in executables.items():
            if sha(exe) != plan["executables"][name]["sha256"]:
                raise ValueError("executable changed during trace")
        cases = {name: next((RUN / name).glob("*/case")) for name in executables}
        compared = {}
        for rel in ("direct/radiance.txt", "direct/transmission.txt", "k/radiance.txt", "k/transmission.txt", "k/profiles_k.txt"):
            files = {n: c / "out" / rel for n, c in cases.items()}
            compared[rel] = {"sha256": {n: sha(p) for n, p in files.items()},
                             "byte_equal": files["control"].read_bytes() == files["instrumented"].read_bytes()}
        trace_rows = [line.split() for line in (RUN / "EXT_TRACE.txt").read_text().splitlines()]
        for channel in (8, 9):
            for kind in ("EDD_CALL", "EDD_PRE", "EDD_POST"):
                if not any(len(row) >= 4 and row[0] == kind and int(row[3]) == channel for row in trace_rows):
                    raise ValueError("missing trace records: " + kind + "/" + str(channel))
        expected = json.loads(prior_result.read_text())["events_added_channels"][1]
        result = {"events": events, "raw_products": compared,
                  "all_raw_products_byte_equal": all(x["byte_equal"] for x in compared.values()),
                  "matches_original_PR418_BT_bits": np.array_equal(np.asarray(events[0]["BT_K"]), np.asarray(expected["BT_K"])),
                  "trace_file": str(RUN / "EXT_TRACE.txt"), "trace_sha256": sha(RUN / "EXT_TRACE.txt"),
                  "logical_H_calls": 2, "native_M_optimizer_calls": 0}
        write(PACKET / "TRACE_RESULT.json", result)
        write(RUN / "RESULT.json", result)
        if not result["all_raw_products_byte_equal"]:
            raise ValueError("passive trace failed raw-product noninterference")
    except Exception as exc:
        write(RUN / "FAILED.json", {"error": repr(exc), "events": events})
        raise


if __name__ == "__main__":
    main()
