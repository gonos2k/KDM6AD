#!/usr/bin/env python3
"""Two added-channel value-only calls; reuse frozen PR417 channels 10..16.

This is a channel-wise composite, not a new simultaneous nine-channel H run.
No M, optimizer, observation target or 05 UTC evaluation is requested.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys

PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[2]
OLD = ROOT / "harness/evidence/pr417_hourly_rttov_2026-10-12"
PRIVATE = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr418_added_channels_20261012")
sys.path.insert(0, str(ROOT / "oracle"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, obj):
    with Path(path).open("x") as stream:
        json.dump(obj, stream, indent=2, allow_nan=False)
        stream.write("\n")


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def validate(plan):
    for path, digest in plan["bindings"].items():
        if sha(path) != digest:
            raise ValueError("bound source/result changed: " + path)
    old_plan = json.loads((OLD / "PLAN.json").read_text())
    module(OLD / "run_hourly_h.py", "pr418_old_guard").check(old_plan)
    return old_plan


def prepare():
    if PRIVATE.exists() or (PACKET / "PLAN.json").exists():
        raise FileExistsError("new plan/output must be fresh; no overwrite or retry")
    old_plan = json.loads((OLD / "PLAN.json").read_text())
    old_result = json.loads((OLD / "RESULT.json").read_text())
    if (old_result["status"] != "RETURNED_TWO_ACTUAL_VALUE_ONLY_H"
            or old_result["plan_sha256"] != sha(OLD / "PLAN.json")
            or old_result["channels"] != list(range(10, 17))):
        raise ValueError("completed original seven-channel result is required")
    bindings = {str(p.resolve()): sha(p) for p in OLD.iterdir() if p.is_file()}
    bindings[str(Path(__file__).resolve())] = sha(__file__)
    plan = {"schema": "pr418_added_two_channels_v1", "base_main": "b07af3fe",
            "channels_newly_evaluated": [8, 9], "channels_reused": list(range(10, 17)),
            "composite_channels": list(range(8, 17)), "time_indices": [6, 7],
            "max_logical_H_calls": 2, "grad": False, "M_optimizer_calls": 0,
            "python_executable": old_plan["python_executable"],
            "thread_environment": old_plan["thread_environment"],
            "output_root": str(PRIVATE), "bindings": bindings,
            "geometry_policy": "native-center viewing angles unchanged; AMI GEOS navigation donor separate",
            "quality_policy": "record every flag; composite analysis eligible only if all nine are quality zero",
            "between_runs": "same hash-bound states/auxiliaries/assets; composite is not a simultaneous nine-channel call"}
    validate(plan)
    write(PACKET / "PLAN.json", plan)


def main():
    if sys.argv[1:] == ["--prepare"]:
        prepare()
        return
    if sys.argv[1:]:
        raise ValueError("only --prepare or the one declared execution is supported")
    plan_path = PACKET / "PLAN.json"
    digest = sha(plan_path)
    plan = json.loads(plan_path.read_text())
    if (not __debug__ or os.environ.get("PYTHONOPTIMIZE") != "0"
            or sys.executable != plan["python_executable"]
            or any(os.environ.get(k) != v for k, v in plan["thread_environment"].items())):
        raise ValueError("declared interpreter/assertions/single-thread environment required")
    if (plan["channels_newly_evaluated"] != [8, 9] or plan["time_indices"] != [6, 7]
            or plan["max_logical_H_calls"] != 2 or plan["grad"] is not False):
        raise ValueError("only the two added-channel calls are declared")
    old_plan = validate(plan)
    import numpy as np
    import torch
    from kdm6.obs.allsky_shard import sharded_allsky
    torch.set_num_threads(1)
    if str(torch.__version__) != "2.13.0":
        raise ValueError("declared Torch version changed")
    prep = module(OLD / "prepare_hourly_h.py", "pr418_existing_context")
    output = Path(plan["output_root"])
    output.mkdir(mode=0o700, exist_ok=False)
    write(output / "STARTED_ONCE.json", {"plan_sha256": digest, "logical_H_max": 2})
    events = []
    try:
        with mp.get_context("spawn").Pool(1) as pool:
            for ti in (6, 7):
                ctx = prep.load_context(old_plan, ti)
                cfg = dict(ctx["rttov_cfg"], channels=(8, 9))
                target = torch.zeros((1, 2), dtype=torch.float64)
                event = {"time_index": ti, "returned": False, "grad_requested": False}
                events.append(event)
                out = sharded_allsky(ctx["state"], ctx["forcing"], torch.tensor([0]),
                    target, torch.ones_like(target), ctx["xland"], cfg,
                    str(output / f"H_{ti:02d}"), pool=pool, n_workers=1, grad=False)
                # Explicit value-only serialization boundary, outside the AD path.
                bt, rq = out["bt"].detach().numpy(), out["rq"].detach().numpy()
                if (bt.shape != (1, 2) or rq.shape != (1, 2)
                        or not np.isfinite(bt).all() or not np.isfinite(rq).all()):
                    raise ValueError("added channel shape/nonfinite failure; no removal/retry")
                event.update(returned=True, BT_K=bt.tolist(), rad_quality=rq.tolist())
                write(output / f"H_{ti:02d}.json", event)
                print(json.dumps(event), flush=True)
        validate(plan)
        if sha(plan_path) != digest:
            raise ValueError("plan changed during execution")
        old = json.loads((OLD / "RESULT.json").read_text())
        composite = []
        for added, previous in zip(events, old["events"], strict=True):
            if added["time_index"] != previous["time_index"]:
                raise ValueError("time-order mismatch")
            composite.append({"time_index": added["time_index"],
                "BT_K": [added["BT_K"][0] + previous["BT_K"][0]],
                "rad_quality": [added["rad_quality"][0] + previous["rad_quality"][0]]})
        eligible = all(not np.any(np.asarray(e["rad_quality"]) != 0) for e in composite)
        result = {"schema": "pr418_channel_composite_v1", "status": "RETURNED_ADDED_CHANNEL_H",
            "plan_sha256": digest, "channels": list(range(8, 17)),
            "new_logical_H_calls": 2, "new_M_optimizer_calls": 0,
            "simultaneous_nine_channel_H_executed": False,
            "events_added_channels": events, "composite_events": composite,
            "all_nine_quality_zero_both_times": eligible,
            "dummy_cost_discarded": True, "observation_fit_assessed": False,
            "BT_delta_07_minus_06_K": (np.asarray(composite[1]["BT_K"]) - np.asarray(composite[0]["BT_K"])).tolist(),
            "old_result_sha256": sha(OLD / "RESULT.json")}
        write(output / "RESULT.json", result)
        write(PACKET / "RESULT.json", result)
        names = ("WV063", "WV069", "WV073", "IR087", "IR096", "IR105", "IR112", "IR123", "IR133")
        with (PACKET / "CHANNEL_RESPONSE.csv").open("x", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("channel_id", "channel", "BT06_K", "BT07_K", "delta07_minus06_K", "quality06", "quality07", "origin"))
            for i, name in enumerate(names):
                writer.writerow((8+i, name, composite[0]["BT_K"][0][i], composite[1]["BT_K"][0][i],
                    result["BT_delta_07_minus_06_K"][0][i], composite[0]["rad_quality"][0][i],
                    composite[1]["rad_quality"][0][i], "new_added_channel_H" if i < 2 else "reused_PR417"))
    except Exception as exc:
        write(output / "FAILED.json", {"error": repr(exc), "events": events, "automatic_retry": False})
        raise


if __name__ == "__main__":
    main()
