#!/usr/bin/env python3
"""Pin current QNC calculators and compare three block28 observation baselines."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import runpy
import sys

import numpy as np


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
OLD = REPO / "harness/evidence/native_qnc_host_backoff_2026-10-27"
OLD_MANIFEST_SHA = "b2655e61ce31d358499e95c11fb93b76747135a81ca180dbbed05b3b31cbe833"
BASELINE = REPO / "harness/evidence/native_full_physics_observation_2026-10-25"
BASELINE_MANIFEST_SHA = "84a20ae7d337c0c10aec6dd872ae75af75400822f809888a0b35656d3cd12663"
READY_SHA = "0c4836a2a44531c98d38d3ded15cab5048679b1139f3e4fd96fb62eff84bfad3"
SUPPORT_SHA = "c4154b4b735fcbfb5509b1f23ee53f4cfe17b46ccf0c6930f63aa244f2a0f9a9"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _inventory(root: Path, manifest: dict) -> None:
    seen = set()
    for item in manifest["files"]:
        rel = item["path"]
        if (not isinstance(rel, str) or rel in seen or Path(rel).is_absolute()
                or ".." in Path(rel).parts or "__pycache__" in Path(rel).parts
                or Path(rel).suffix == ".pyc"):
            raise ValueError(f"unsafe or repeated packet path: {rel}")
        seen.add(rel)
        path = root / rel
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"packet path escapes: {rel}")
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or _sha(raw) != item["sha256"]:
            raise ValueError(f"packet asset differs: {rel}")


def _rmse(bt: np.ndarray, obs: np.ndarray, mask: np.ndarray) -> float:
    squared = (bt - obs)[mask] ** 2
    return math.sqrt(math.fsum(float(value) for value in squared) / squared.size)


def _reason_flags(words: dict[str, str]) -> set[str]:
    values = {name: float(np.asarray([int(word, 16)], dtype=np.uint32).view(np.float32)[0])
              for name, word in words.items()}
    qc, nc, qi, ni = (values[name] for name in ("QCLOUD", "QNCLOUD", "QICE", "QNICE"))
    return {name for condition, name in (
        (qc > 0 and nc <= 0, "liquid_QC_positive_NC_nonpositive"),
        (qi > 0 and ni <= 0, "ice_QI_positive_NI_nonpositive"),
        (nc < 0, "negative_NC"), (ni < 0, "negative_NI")) if condition}


def build_analysis() -> dict:
    old_raw = (OLD / "manifest.json").read_bytes()
    baseline_raw = (BASELINE / "manifest.json").read_bytes()
    if _sha(old_raw) != OLD_MANIFEST_SHA or _sha(baseline_raw) != BASELINE_MANIFEST_SHA:
        raise ValueError("historical host or baseline manifest changed")
    old_manifest = json.loads(old_raw)
    baseline_manifest = json.loads(baseline_raw)
    _inventory(OLD, old_manifest)
    for name, expected in old_manifest["external_source_pins"].items():
        if _sha((REPO / name).read_bytes()) != expected:
            raise ValueError(f"historical PR465 pinned source changed: {name}")
    baseline_npz = BASELINE / baseline_manifest["packet"]["file"]
    if _sha(baseline_npz.read_bytes()) != baseline_manifest["packet"]["sha256"]:
        raise ValueError("baseline observation array changed")
    state7 = REPO / "harness/evidence/native_qnc_state7_2026-10-27/receipts/execution_summary.json"
    baseline_sha = baseline_manifest["analysis"]["checkpoint_sha256"]
    if json.loads(state7.read_text())["cases"]["control"]["off"]["checkpoint_sha256"] != baseline_sha:
        raise ValueError("original observation baseline is not the PR461 control endpoint")
    old_replay = runpy.run_path(str(OLD / "replay.py"))
    prior = old_replay["build_analysis"]()
    prior_bytes = (json.dumps(prior, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if (OLD / "analysis.json").read_bytes() != prior_bytes:
        raise ValueError("current calculators changed published PR465 analysis")
    reasons_path = PACKET / "residual_reason_rows.json"
    reasons = json.loads(reasons_path.read_text())
    ready_receipt_path = PACKET / "ready_boundary_receipt.json"
    ready_receipt = json.loads(ready_receipt_path.read_text())
    step_control_source = REPO / "harness/native_step_control_overlay.py"
    old_execution = json.loads((OLD / "execution_summary.json").read_text())
    prior_alpha = old_execution["runs"]["alpha025"]["off"]
    if (ready_receipt["schema"] != "kdm6.native_qnc_pre_command_ready_boundary.v1" or
            ready_receipt["initial_input_checkpoint_sha256"] != prior_alpha["origin_checkpoint_sha256"] or
            ready_receipt["pre_command_READY40_checkpoint_sha256"] != READY_SHA or
            ready_receipt["analysis_background_checkpoint_sha256"] != READY_SHA or
            ready_receipt["output_checkpoint_sha256"] != prior_alpha["checkpoint_sha256"] or
            ready_receipt["control_family"] != "ANALYSIS_TQ" or
            ready_receipt["applied_TQ_points"] != prior_alpha["applied_control"]["applied_rows"] or
            ready_receipt["applied_TQ_components"] != prior_alpha["applied_control"]["applied_components"] or
            ready_receipt["step_control_overlay_source_sha256"] != _sha(step_control_source.read_bytes()) or
            ready_receipt["directly_written_host_fields"] != ["grid%t_2", "grid%moist(...,P_QV)"] or
            ready_receipt["hydrometeor_QC_NC_QI_NI_direct_write"] is not False or
            ready_receipt["post_command_READY40_checkpoint_observed"] is not False):
        raise ValueError("pre-command READY40/analysis TQ boundary receipt differs")
    producer = REPO / "harness/native_qnc_residual_reason_producer.py"
    expected_inputs = {"pre_command_READY40": READY_SHA,
                       "candidate_final": prior["off_on_checkpoint_comparison"]["alpha025"]["checkpoint_sha256"],
                       "published_M0": baseline_manifest["packet"]["sha256"],
                       "published_hard_masks": SUPPORT_SHA}
    with np.load(OLD / "support_masks.npz", allow_pickle=False) as z:
        old_m0 = np.asarray(z["m0_mask"], dtype=np.bool_)
        bad_alpha = np.asarray(z["alpha025_hard_invalid"], dtype=np.bool_)
    missing = np.flatnonzero(bad_alpha & old_m0.any(axis=1))
    rows = reasons["rows"]
    if (reasons["producer_sha256"] != _sha(producer.read_bytes()) or
            reasons["input_sha256"] != expected_inputs or
            reasons["remaining_invalid_M0_profiles"] != 54 or
            reasons["remaining_invalid_M0_channel_cells"] != 378 or
            reasons["M0_profiles"] != int(old_m0.any(axis=1).sum()) or
            len(rows) != 54 or [row["flat_index_zero_based"] for row in rows] != missing.tolist() or
            reasons["model_calls"] != {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0}):
        raise ValueError("residual failure producer/source/support binding differs")
    counted = {name: 0 for name in ("liquid_QC_positive_NC_nonpositive",
                                   "ice_QI_positive_NI_nonpositive", "negative_NC", "negative_NI")}
    for row in rows:
        flat_index = row["flat_index_zero_based"]
        if (row["i_one_based"] != flat_index % 234 + 1 or
                row["j_one_based"] != flat_index // 234 + 1 or
                row["M0_channel_count"] != int(old_m0[flat_index].sum())):
            raise ValueError("residual failure coordinate or M0 channel count differs")
        reconstructed = {stage: {} for stage in ("ready", "final")}
        for layer in row["failing_level_words"]:
            k1 = layer["native_k_one_based"]
            if type(k1) is not int or not 1 <= k1 <= 39:
                raise ValueError("residual failure native level differs")
            for stage in ("ready", "final"):
                for name in _reason_flags(layer[f"{stage}_f32_hex"]):
                    reconstructed[stage].setdefault(name, []).append(k1)
        if (reconstructed["ready"] != row["ready_reason_levels_one_based"] or
                reconstructed["final"] != row["final_reason_levels_one_based"] or
                row["already_hard_invalid_at_ready"] != bool(reconstructed["ready"])):
            raise ValueError("residual failure bitwords/reason stages differ")
        for name in reconstructed["final"]:
            counted[name] += 1
    if (counted != reasons["reason_profile_counts"] or
            sum(row["already_hard_invalid_at_ready"] for row in rows) !=
                reasons["remaining_already_invalid_at_pre_command_READY40"] or
            sum(not row["already_hard_invalid_at_ready"] for row in rows) !=
                reasons["remaining_new_since_pre_command_READY40"]):
        raise ValueError("residual failure category totals differ")
    with np.load(baseline_npz, allow_pickle=False) as z:
        flat = np.asarray(z["flat_index"], dtype=np.int32)
        obs = np.asarray(z["obs_bt_k"][14336:14848], dtype=np.float64)
        mask = np.asarray(z["m0_mask"][14336:14848], dtype=np.bool_)
        baseline_bt = np.asarray(z["baseline_bt_kma_v3_0"][14336:14848], dtype=np.float64)
        channels = np.asarray(z["channel_id"], dtype=np.int16)
    if (not np.array_equal(flat, np.arange(65988, dtype=np.int32)) or
            obs.shape != (512, 7) or mask.shape != (512, 7) or
            not np.array_equal(channels, np.arange(10, 17, dtype=np.int16)) or
            int(mask.sum()) != 2009 or int(mask.any(axis=1).sum()) != 287 or
            not mask[392].all()):
        raise ValueError("baseline block28 support or channels differ")
    results = {}
    for name, bt in (("original_control", baseline_bt),):
        results[name] = {"target_BT_K": bt[392].tolist(),
                         "target_sim_minus_obs_K": (bt[392] - obs[392]).tolist(),
                         "block_M0_RMSE_K": _rmse(bt, obs, mask),
                         "M0_changed_profile_count_vs_original": 0}
    for case in ("control", "alpha025"):
        path = OLD / "data" / case / "block28_direct.npz"
        with np.load(path, allow_pickle=False) as z:
            block_flat = np.asarray(z["flat_indices"], dtype=np.int32)
            candidate_obs = np.asarray(z["obs_bt_k"], dtype=np.float64)
            candidate_mask = np.asarray(z["m0_mask"], dtype=np.bool_)
            bt = np.asarray(z["bt_kma_v3_0"], dtype=np.float64)
            valid = np.asarray(z["actual_valid_mask"], dtype=np.bool_)
        if (not np.array_equal(block_flat, np.arange(14336, 14848, dtype=np.int32)) or
                not np.array_equal(candidate_obs, obs) or
                not np.array_equal(candidate_mask, mask) or
                not np.array_equal(valid & mask, mask) or
                not np.isfinite(bt[mask]).all()):
            raise ValueError(f"variant {case} cannot use original block28 comparison")
        previous = prior["block28_direct"][case]
        if (previous["M0_channel_cells"] != 2009 or previous["M0_loss"] != 0 or
                previous["target_BT_K"] != bt[392].tolist() or
                previous["target_sim_minus_obs_K"] != (bt[392] - obs[392]).tolist()):
            raise ValueError(f"published variant {case} BT differs")
        changed = np.any((bt.view(np.uint64) != baseline_bt.view(np.uint64)) & mask, axis=1)
        results[f"variant_{case}"] = {
            "target_BT_K": bt[392].tolist(),
            "target_sim_minus_obs_K": (bt[392] - obs[392]).tolist(),
            "block_M0_RMSE_K": _rmse(bt, obs, mask),
            "M0_changed_profile_count_vs_original": int(changed.sum()),
        }
    original = results["original_control"]
    control = results["variant_control"]
    alpha = results["variant_alpha025"]
    return {
        "schema": "kdm6.native_qnc_host_backoff_current_source_review.v1",
        "status": "CURRENT_CALCULATORS_PINNED_THREE_BASELINES_COMPARED_GLOBAL_GATE_OPEN",
        "historical_pr465_manifest_sha256": OLD_MANIFEST_SHA,
        "baseline_observation_manifest_sha256": BASELINE_MANIFEST_SHA,
        "historical_pr465_analysis_sha256": _sha(prior_bytes),
        "block": {"index": 28, "original_columns": 512, "M0_profiles": 287,
                  "M0_channel_cells": 2009, "target_flat_index": 14728,
                  "target_full_row_zero_based": 392, "channel_ids": channels.tolist()},
        "comparisons": results,
        "target_ir105_bt_difference_K": {
            "variant_control_minus_original": control["target_BT_K"][3] - original["target_BT_K"][3],
            "variant_alpha_minus_original": alpha["target_BT_K"][3] - original["target_BT_K"][3],
            "variant_alpha_minus_variant_control": alpha["target_BT_K"][3] - control["target_BT_K"][3],
        },
        "block_M0_RMSE_difference_K": {
            "variant_alpha_minus_original": alpha["block_M0_RMSE_K"] - original["block_M0_RMSE_K"],
            "variant_alpha_minus_variant_control": alpha["block_M0_RMSE_K"] - control["block_M0_RMSE_K"],
        },
        "remaining_full_M0_hard_failures": {
            "producer_sha256": reasons["producer_sha256"],
            "reason_rows_sha256": _sha(reasons_path.read_bytes()),
            "pre_command_READY40_receipt_sha256": _sha(ready_receipt_path.read_bytes()),
            "profile_count": len(rows),
            "channel_cell_count": reasons["remaining_invalid_M0_channel_cells"],
            "reason_profile_counts": counted,
            "already_invalid_at_pre_command_READY40":
                reasons["remaining_already_invalid_at_pre_command_READY40"],
            "new_since_pre_command_READY40":
                reasons["remaining_new_since_pre_command_READY40"],
            "flat_indices_zero_based": missing.tolist(),
        },
        "full_fixed_support_candidate_cost_defined": False,
        "offline_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
    }


def main() -> int:
    manifest = json.loads((PACKET / "manifest.json").read_text())
    if manifest.get("schema") != "kdm6.native_qnc_host_backoff_current_source_packet.v1":
        raise ValueError("wrong host-backoff current-source packet schema")
    if manifest.get("historical_pr465_manifest_sha256") != OLD_MANIFEST_SHA:
        raise ValueError("historical PR465 manifest pin differs")
    _inventory(PACKET, manifest)
    for name, expected in manifest["external_source_pins"].items():
        if _sha((REPO / name).read_bytes()) != expected:
            raise ValueError(f"current host-backoff source changed: {name}")
    result = build_analysis()
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if (PACKET / "analysis.json").read_bytes() != raw:
        raise ValueError("three-baseline analysis differs from published bytes")
    print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": _sha(raw),
                      "offline_model_calls": result["offline_model_calls"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
