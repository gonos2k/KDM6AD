#!/usr/bin/env python3
"""One corrected passive trace H; reuse the retained first control products."""
from __future__ import annotations
import json
import multiprocessing as mp
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trace_saved07 as base


def main():
    old = json.loads((base.OLD / "PLAN.json").read_text())
    prior = json.loads((base.PACKET / "TRACE_PLAN.json").read_text())
    build_path = base.TRACE_BUILD / "BUILD_CONTEXT_V2.json"
    build = json.loads(build_path.read_text())
    exe = Path(build["build"]["v2_executable"])
    run = base.PRIVATE / "SAVED07_TRACE_CORRECTED_01"
    if (not __debug__ or os.environ.get("PYTHONOPTIMIZE") != "0"
            or sys.executable != old["python_executable"]
            or any(os.environ.get(k) != v for k, v in old["thread_environment"].items())):
        raise ValueError("original interpreter/assertions/one-thread environment required")
    if run.exists():
        raise FileExistsError("corrected trace is a fresh separately declared run")
    if base.sha(exe) != build["build"]["v2_executable_sha256"]:
        raise ValueError("corrected trace executable changed")
    for path, digest in prior["bindings"].items():
        if base.sha(path) != digest:
            raise ValueError("first trace input/source changed: " + path)
    run.mkdir(mode=0o700)
    fixture = run / "fixture"
    source = Path(old["time_contexts"]["7"]["H_config"]["fixture_case_dir"])
    shutil.copytree(source, fixture)
    script = fixture / "out/run.sh"
    lines = script.read_text().splitlines()
    index = next(i for i, s in enumerate(lines) if "rttov_test.exe >" in s)
    lines[index] = " " + str(exe) + " > rttov_test.log 2>&1"
    lines.insert(lines.index(". ./env.sh") + 1,
                 "export KDM6AD_EXT_TRACE='" + str(run / "EXT_TRACE.txt") + "'")
    script.write_text("\n".join(lines) + "\n")
    pins = {str(Path(__file__).resolve()): base.sha(__file__),
            str(build_path): base.sha(build_path), str(exe): base.sha(exe),
            **prior["bindings"], **{str(p): base.sha(p) for p in fixture.rglob("*") if p.is_file()}}
    control_case = next((base.RUN / "control").glob("*/case"))
    products = ("direct/radiance.txt", "direct/transmission.txt", "k/radiance.txt", "k/transmission.txt", "k/profiles_k.txt")
    pins.update({str(control_case / "out" / rel): base.sha(control_case / "out" / rel) for rel in products})
    plan = {"time_index": 7, "physical_channels": [8, 9], "internal_to_physical": {"1": 8, "2": 9},
            "new_logical_H_calls": 1, "M_optimizer_native_calls": 0, "bindings": pins,
            "first_attempt_preserved": True, "control_reused": str(control_case)}
    base.write(base.PACKET / "TRACE_V2_PLAN.json", plan)
    base.write(run / "STARTED_ONCE.json", {"plan_sha256": base.sha(base.PACKET / "TRACE_V2_PLAN.json")})
    import numpy as np
    import torch
    from kdm6.obs.allsky_shard import sharded_allsky
    torch.set_num_threads(1)
    ctx = base.load(base.OLD / "prepare_hourly_h.py", "saved07_trace_v2_context").load_context(old, 7)
    cfg = dict(ctx["rttov_cfg"], channels=(8, 9), fixture_case_dir=str(fixture))
    target = torch.zeros((1, 2), dtype=torch.float64)
    try:
        with mp.get_context("spawn").Pool(1) as pool:
            out = sharded_allsky(ctx["state"], ctx["forcing"], torch.tensor([0]), target,
                torch.ones_like(target), ctx["xland"], cfg, str(run / "H"),
                pool=base.RetainingPool(pool), n_workers=1, grad=False)
        event = {"BT_K": out["bt"].tolist(), "rad_quality": out["rq"].tolist()}
        base.write(run / "H_RESULT.json", event)
        for path, digest in pins.items():
            if base.sha(path) != digest:
                raise ValueError("corrected trace input/source changed: " + path)
        case = next((run / "H").glob("*/case"))
        assert (case / "in/channels.txt").read_text().split() == ["8", "9"]
        rows = [s.split() for s in (run / "EXT_TRACE.txt").read_text().splitlines()]
        for internal in (1, 2):
            for kind in ("EDD_CALL", "EDD_PRE", "EDD_POST"):
                assert any(len(r) > 3 and r[0] == kind and int(r[3]) == internal for r in rows), (kind, internal)
        comparison = {rel: {"control_sha256": base.sha(control_case / "out" / rel),
                           "trace_sha256": base.sha(case / "out" / rel),
                           "byte_equal": (control_case / "out" / rel).read_bytes() == (case / "out" / rel).read_bytes()}
                      for rel in products}
        expected = json.loads((base.ROOT / "harness/evidence/pr418_nine_channels_2026-10-12/RESULT.json").read_text())["events_added_channels"][1]
        result = {"status": "CORRECTED_TRACE_RETURNED", "event": event, "new_logical_H_calls": 1,
                  "total_trace_campaign_logical_H_calls": 3, "M_optimizer_native_calls": 0,
                  "raw_noninterference": comparison, "all_raw_products_byte_equal": all(v["byte_equal"] for v in comparison.values()),
                  "matches_original_PR418_BT_bits": np.array_equal(np.asarray(event["BT_K"]), np.asarray(expected["BT_K"])),
                  "trace_file": str(run / "EXT_TRACE.txt"), "trace_sha256": base.sha(run / "EXT_TRACE.txt"),
                  "runtime_case": str(case), "internal_to_physical": plan["internal_to_physical"]}
        base.write(base.PACKET / "TRACE_V2_RESULT.json", result)
        base.write(run / "RESULT.json", result)
        print(json.dumps(result), flush=True)
        assert result["all_raw_products_byte_equal"]
    except Exception as exc:
        base.write(run / "FAILED.json", {"error": repr(exc)})
        raise


if __name__ == "__main__":
    main()
