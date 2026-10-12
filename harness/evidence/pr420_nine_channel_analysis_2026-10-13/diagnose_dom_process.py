#!/usr/bin/env python3
"""Complete the PR412-style joint M response using three missing saved H values.

H(background initial,9) serves both supports; each returned initial has its
own H. Existing background/final slots are reused. No M or optimizer runs.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
from pathlib import Path
import sys

import numpy as np

PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[2]
sys.path.insert(0, str(PACKET))
sys.path.insert(0, str(ROOT / "oracle"))
from run_dom_pair import PRIVATE, check, module  # noqa: E402
from trace_saved07 import RetainingPool, sha, write  # noqa: E402


def huber(bt, target):
    residual = np.asarray(bt) - np.asarray(target)
    magnitude = np.abs(residual)
    return float(np.where(magnitude <= 1, 0.5 * residual**2, magnitude - 0.5).sum())


def main():
    old = json.loads((ROOT / "harness/evidence/pr417_hourly_rttov_2026-10-12/PLAN.json").read_text())
    assert __debug__ and os.environ.get("PYTHONOPTIMIZE") == "0"
    assert sys.executable == old["python_executable"]
    assert all(os.environ.get(k) == v for k, v in old["thread_environment"].items())
    import torch
    from kdm6.obs.allsky_shard import sharded_allsky
    from kdm6.state import State
    torch.set_num_threads(1)
    assert str(torch.__version__) == "2.13.0"
    output = PRIVATE / "DOM_PROCESS_RESPONSE_ONCE_01"
    if output.exists():
        raise FileExistsError("single saved-state H diagnostic only")
    prep = json.loads((PACKET / "PAIRED_DOM1_PREPARATION.json").read_text())
    driver = module(ROOT / "harness/evidence/pr418_nine_channels_2026-10-12/run_case_analysis_nine.py", "process_driver")
    intake = module(driver.INTAKE_SOURCE, "process_intake")
    legacy = driver.load_module(driver.LEGACY_DRIVER, "process_legacy")
    manifest, arrays = intake.load_bound_intake(prep["intake_manifest_path"], prep["intake_npz_path"])
    pins = dict(json.loads((PACKET / "ANALYSIS_PLAN.json").read_text())["bindings"])
    for p in (Path(__file__), PACKET / "ANALYSIS_PLAN.json",
              ROOT / "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"):
        pins[str(p.resolve())] = sha(p)
    contexts, saved, captures = {}, {}, {}
    for name, channels in (("DOM9", tuple(range(8, 17))), ("DOM7", tuple(range(10, 17)))):
        cp = PACKET / (name + "_CAPTURE.json")
        capture = json.loads(cp.read_text())
        checkpoint = Path(capture["private_checkpoint"]["path"])
        assert sha(checkpoint) == capture["private_checkpoint"]["sha256"]
        pins[str(cp.resolve())] = sha(cp)
        pins[str(checkpoint)] = sha(checkpoint)
        captures[name] = capture
        with np.load(checkpoint, allow_pickle=False) as z:
            saved[name] = {k: z[k].copy() for k in z.files}
        fixture = Path(prep["runs"][name]["fixture"]["prepared_fixture_copy"])
        contexts[name] = driver.build_inputs(manifest, arrays, fixture, legacy.TEMPLATE_FIXTURE, legacy, channels=channels)
        assert list(capture["observations"]["channels_ami_physical_ids"]) == list(channels)
        assert np.array_equal(saved[name]["observation_y_bt_K"], contexts[name]["y_bt"].numpy())
        assert np.all(saved[name]["final_slot_rad_quality"] == 0)
        assert np.all(saved[name]["final_slot_frozen_mask"] == 1)
    for f in State._fields:
        assert np.array_equal(saved["DOM9"]["background_initial_state__" + f], saved["DOM7"]["background_initial_state__" + f])
        assert np.array_equal(saved["DOM9"]["background_slot_state__" + f], saved["DOM7"]["background_slot_state__" + f])
    bg9 = np.asarray(captures["DOM9"]["background_quality_probe"]["BT_K"])
    bg7 = np.asarray(captures["DOM7"]["background_quality_probe"]["BT_K"])
    assert np.array_equal(bg9[:, 2:], bg7)
    check(pins)
    plan = {"schema": "pr420_saved_dom_joint_M_response_v1", "display_timezone": "KST",
        "bindings": pins, "calls": ["background_initial_DOM9", "returned_initial_DOM9", "returned_initial_DOM7"],
        "logical_H_calls": 3, "M_optimizer_native_calls": 0,
        "operator": "same opt-in DOM1 with frozen inputs and complete selected support",
        "purpose": "PR412-style R_M, I_M, and nonlinear cost gain with/without M",
        "common_background_DOM7": "reuse actual DOM9 initial BT common channels after background-slot equality check",
        "named_process_or_cloud_only_attribution": False,
        "bypassed_M_is_same_time_host_state": False,
        "calibration_prepost_bound_here_but_not_original_pair": True}
    write(PACKET / "PROCESS_PLAN.json", plan)
    output.mkdir(mode=0o700)
    values = {}
    with mp.get_context("spawn").Pool(1) as pool:
        for label, name, prefix in (("background_initial_DOM9", "DOM9", "background_initial_state"),
                                    ("returned_initial_DOM9", "DOM9", "returned_analysis_initial_state"),
                                    ("returned_initial_DOM7", "DOM7", "returned_analysis_initial_state")):
            check(pins)
            ctx = contexts[name]
            state = State(*(torch.as_tensor(saved[name][prefix + "__" + f], dtype=torch.float64) for f in State._fields))
            response = sharded_allsky(state, ctx["forcing"], torch.tensor([0]), ctx["y_bt"],
                torch.ones_like(ctx["y_bt"]), ctx["xland"], ctx["rttov_cfg"], str(output / label),
                n_workers=1, grad=False, pool=RetainingPool(pool))
            assert response["adj"] is None
            assert torch.equal(response["rq"], torch.zeros_like(response["rq"]))
            values[label] = {"BT_K": response["bt"].tolist(), "quality": response["rq"].tolist(),
                             "raw_value_only_j_ignored": float(response["j"])}
            check(pins)
    summary = {}
    for name in ("DOM9", "DOM7"):
        target = contexts[name]["y_bt"].numpy()
        bg_initial = np.asarray(values["background_initial_DOM9"]["BT_K"])
        if name == "DOM7":
            bg_initial = bg_initial[:, 2:]
        analysis_initial = np.asarray(values["returned_initial_" + name]["BT_K"])
        bg_slot = np.asarray(captures[name]["background_quality_probe"]["BT_K"])
        analysis_slot = saved[name]["final_slot_bt_K"]
        rm_bg = bg_slot - bg_initial
        rm_analysis = analysis_slot - analysis_initial
        jo_bg_initial, jo_bg_slot = huber(bg_initial, target), huber(bg_slot, target)
        jo_analysis_initial, jo_analysis_slot = huber(analysis_initial, target), huber(analysis_slot, target)
        gm, g0 = jo_bg_slot - jo_analysis_slot, jo_bg_initial - jo_analysis_initial
        summary[name] = {"channels": list(contexts[name]["rttov_cfg"]["channels"]),
            "background_initial_BT_K": bg_initial.tolist(), "returned_initial_BT_K": analysis_initial.tolist(),
            "background_slot_BT_K": bg_slot.tolist(), "returned_slot_BT_K": analysis_slot.tolist(),
            "R_M_background_K": rm_bg.tolist(), "R_M_returned_K": rm_analysis.tolist(),
            "I_M_K": (rm_analysis - rm_bg).tolist(),
            "Jo_background_initial": jo_bg_initial, "Jo_background_slot": jo_bg_slot,
            "Jo_returned_initial": jo_analysis_initial, "Jo_returned_slot": jo_analysis_slot,
            "G_M": gm, "G_0_bypassed_M": g0, "G_M_minus_G_0": gm - g0}
    result = {"schema": plan["schema"], "status": "RETURNED_THREE_SAVED_STATE_H_DIAGNOSTICS",
              "plan_sha256": sha(PACKET / "PROCESS_PLAN.json"), "quality_all_zero": True,
              "bound_assets_unchanged_before_after": True, "calls": values, "runs": summary,
              "logical_H_calls": 3, "M_optimizer_native_calls": 0,
              "interpretation": "joint input/whole-M response at separately returned states; no isolated process attribution"}
    write(PACKET / "PROCESS_RESPONSE.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
