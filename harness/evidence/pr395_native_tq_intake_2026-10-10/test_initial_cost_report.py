#!/usr/bin/env python3
"""Synthetic receipt test: zero-mask QC cost is distinct from Jo at zero control."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))
DRIVER_PATH = ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/run_analysis.py"
spec = importlib.util.spec_from_file_location("pr395_analysis_driver", DRIVER_PATH)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)

def receipt_fixture():
    target = torch.full((1, 7), 290.0, dtype=torch.float64)
    bt = np.full((1, 7), 290.5, dtype=np.float64)
    frozen_mask = np.ones((1, 7), dtype=np.float64)
    zero_mask = np.zeros((1, 7), dtype=np.float64)
    jo = float(driver.compute_obs_loss(
        torch.as_tensor(bt), {"bt": target, "bias": 0.0},
        torch.as_tensor(frozen_mask), 1.0, delta=1.0))
    state_hash = "a" * 64
    capture = {
        "logical_h_calls": [
            {"call_index": 0, "grad": False, "BT_K": bt.tolist(),
             "fixed_mask": zero_mask.tolist(), "state_sha256": state_hash},
            {"call_index": 1, "grad": True, "BT_K": bt.tolist(),
             "fixed_mask": frozen_mask.tolist(), "state_sha256": state_hash},
        ],
        "objective": {"initial_zero_control_closure": {
            "trace_index": 0, "Jb_state": 0.0, "Jtheta": 0.0, "Jo": jo,
            "Jtotal": jo, "n_valid": 7, "operator_signature_sha256": "b" * 64,
            "frozen_mask": {"shape": [1, 7], "dtype": "float64",
                            "values": frozen_mask.tolist(), "sha256_f64": "c" * 64},
        }},
        "background_quality_probe": {
            "raw_J_huber": 0.0,
            "cost_semantics": "non-grad background quality probe with all-zero loss mask; not initial closure Jo",
            "BT_K": bt.tolist(), "target_BT_K": target.tolist(),
            "rad_quality": np.zeros((1, 7)).tolist(),
            "mask": {"shape": [1, 7], "dtype": "float64", "values": zero_mask.tolist(),
                     "sha256_f64": "d" * 64},
        },
    }
    
    return capture, target, jo


def test_true_initial_cost_is_separate_from_zero_mask_probe():
    capture, target, jo = receipt_fixture()
    result = driver._audit_initial_objectives(capture, target)
    assert result["status"] == "CROSSCHECKED", result
    assert result["initial_zero_control_objective"]["Jo0_huber"] == jo and jo > 0.0
    assert result["background_quality_probe"]["probe_masked_cost"] == 0.0
    assert result["background_quality_probe"]["zero_mask_cost_recomputed"] == 0.0
    assert result["background_quality_probe"]["probe_BT_cost_recomputed_with_frozen_mask"] == jo
    assert result["crosschecks"]["h_or_m_re_evaluations_for_crosscheck"] == 0
    
    # Guard against relabeling the raw zero-mask callback cost as optimizer Jo0.
    assert result["initial_zero_control_objective"]["Jo0_huber"] != result[
        "background_quality_probe"]["probe_masked_cost"]


def test_initial_cost_relabeling_fails_crosscheck():
    capture, target, _ = receipt_fixture()
    capture["objective"]["initial_zero_control_closure"]["Jo"] = 0.0
    capture["objective"]["initial_zero_control_closure"]["Jtotal"] = 0.0
    result = driver._audit_initial_objectives(capture, target)
    assert result["status"] == "MISMATCH"
    assert not result["crosschecks"]["probe_BT_under_frozen_mask_matches_initial_zero_control_Jo"]
