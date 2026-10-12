#!/usr/bin/env python3
"""Two value-only C/M/H evaluations of a fixed accepted DOM9 direction.

No optimization/retry; independently sum Huber and prior from returned BT.
Checkpoint tensor extraction is explicit value-only diagnostic work.
"""
from __future__ import annotations

import dataclasses
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


def main():
    old = json.loads((ROOT / "harness/evidence/pr417_hourly_rttov_2026-10-12/PLAN.json").read_text())
    assert __debug__ and os.environ.get("PYTHONOPTIMIZE") == "0"
    assert sys.executable == old["python_executable"]
    assert all(os.environ.get(k) == v for k, v in old["thread_environment"].items())
    output = PRIVATE / "DOM9_DIRECTION_ONCE_01"
    if output.exists():
        raise FileExistsError("single bounded direction check only")
    import torch
    from kdm6.da_cvt import cvt_apply, make_default_cvt
    from kdm6.da_dual import default_param_prior, params_from_vtheta
    from kdm6.da_window import collect_window_trajectory
    from kdm6.obs.allsky_shard import sharded_allsky
    from kdm6.state import State
    torch.set_num_threads(1)
    assert str(torch.__version__) == "2.13.0"
    prep = json.loads((PACKET / "PAIRED_DOM1_PREPARATION.json").read_text())
    driver = module(ROOT / "harness/evidence/pr418_nine_channels_2026-10-12/run_case_analysis_nine.py", "direction_driver")
    intake = module(driver.INTAKE_SOURCE, "direction_intake")
    legacy = driver.load_module(driver.LEGACY_DRIVER, "direction_legacy")
    manifest, arrays = intake.load_bound_intake(prep["intake_manifest_path"], prep["intake_npz_path"])
    fixture = Path(prep["runs"]["DOM9"]["fixture"]["prepared_fixture_copy"])
    ctx = driver.build_inputs(manifest, arrays, fixture, legacy.TEMPLATE_FIXTURE, legacy, channels=tuple(range(8, 17)))
    checkpoint = PRIVATE / "DOM_ANALYSIS_PAIR_ONCE_01/DOM9/private/accepted_state.npz"
    pins = dict(json.loads((PACKET / "ANALYSIS_PLAN.json").read_text())["bindings"])
    for p in (Path(__file__), checkpoint, PACKET / "ANALYSIS_PLAN.json",
              ROOT / "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"):
        pins[str(p.resolve())] = sha(p)
    check(pins)
    with np.load(checkpoint, allow_pickle=False) as z:
        v = torch.as_tensor(z["control__optimizer_v_state_control"].copy(), dtype=torch.float64)
        grad = torch.as_tensor(z["control__optimizer_final_gradient_v_state"].copy(), dtype=torch.float64)
        saved_initial = State(*(torch.as_tensor(z["returned_analysis_initial_state__" + f].copy(), dtype=torch.float64) for f in State._fields))
        saved_sigma = State(*(torch.as_tensor(z["control__b_sigma__" + f].copy(), dtype=torch.float64) for f in State._fields))
    spec, sigma = make_default_cvt(ctx["xb"], th_sigma=0.8, qv_sigma=0.08, qv_levels=12,
        sigma_overrides={f: 0.0 for f in State._fields if f not in ("th", "qv")})
    assert all(torch.equal(a, b) for a, b in zip(sigma, saved_sigma))
    initial, _ = cvt_apply(ctx["xb"], sigma, v, spec)
    assert all(torch.equal(a, b) for a, b in zip(initial, saved_initial))
    active = torch.stack(list(sigma)) > 0
    assert torch.equal(grad[~active], torch.zeros_like(grad[~active]))
    direction = grad / torch.linalg.vector_norm(grad)
    h = 1e-3
    ad = float((grad * direction).sum())
    window = dataclasses.replace(ctx["window_config"],
        params=params_from_vtheta(default_param_prior(active=()), torch.zeros(4, dtype=torch.float64), live=False))
    plan = {"schema": "pr420_dom9_direction_v1", "display_timezone": "KST",
        "bindings": pins, "point": "saved returned DOM9 control", "direction": "normalized saved full state-control gradient",
        "active_controls": int(active.sum()), "step_control_units": h,
        "ad_directional_total_cost": ad, "calls": ["plus", "minus"],
        "logical_H_calls": 2, "KDM_value_steps": 2, "optimizer_calls": 0,
        "selected_channels": list(range(8, 17)), "thermal_solver": 1,
        "calibration_json_bound_for_this_check": True,
        "calibration_json_bound_before_original_pair": False,
        "acceptance_absolute": 1e-4, "acceptance_relative": 1e-3,
        "scope": "one first-order total-cost direction at one returned iterate; no higher-order or full-Jacobian certification"}
    write(PACKET / "DIRECTION_PLAN.json", plan)
    output.mkdir(mode=0o700)
    np.savez(output / "direction.npz", direction=direction.numpy())
    results = {}
    with mp.get_context("spawn").Pool(1) as pool:
        for label, sign in (("plus", 1), ("minus", -1)):
            check(pins)
            control = v + sign * h * direction
            x0, _ = cvt_apply(ctx["xb"], sigma, control, spec)
            slot = collect_window_trajectory(x0, (ctx["forcing"],), window, {1})[1]
            response = sharded_allsky(slot, ctx["forcing"], torch.tensor([0]), ctx["y_bt"],
                torch.ones_like(ctx["y_bt"]), ctx["xland"], ctx["rttov_cfg"], str(output / label),
                n_workers=1, grad=False, pool=RetainingPool(pool))
            assert response["adj"] is None
            assert torch.equal(response["rq"], torch.zeros_like(response["rq"]))
            residual = response["bt"].numpy() - ctx["y_bt"].numpy()
            a = np.abs(residual)
            jo = float(np.where(a <= 1, 0.5 * residual**2, a - 0.5).sum())
            prior = float(0.5 * (control * control).sum())
            results[label] = {"BT_K": response["bt"].tolist(), "quality": response["rq"].tolist(),
                              "Jo": jo, "Jb": prior, "Jtotal": jo + prior,
                              "returned_j_ignored_value_only": float(response["j"])}
            check(pins)
    fd = (results["plus"]["Jtotal"] - results["minus"]["Jtotal"]) / (2 * h)
    difference = abs(fd - ad)
    passed = difference <= plan["acceptance_absolute"] + plan["acceptance_relative"] * abs(ad)
    result = {"status": "PASS" if passed else "MISMATCH", "plan_sha256": sha(PACKET / "DIRECTION_PLAN.json"),
              "directional_FD": fd, "directional_AD": ad, "absolute_error": difference,
              "relative_error": difference / abs(ad), "results": results,
              "quality_all_zero": True, "original_control_reconstruction_bit_equal": True,
              "bound_assets_unchanged_before_after": True}
    write(PACKET / "DIRECTION_RESULT.json", result)
    print(json.dumps(result), flush=True)
    if not passed:
        raise ValueError("DOM9 independent first-order direction mismatch")


if __name__ == "__main__":
    main()
