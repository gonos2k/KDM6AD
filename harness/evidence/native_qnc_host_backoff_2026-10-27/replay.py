#!/usr/bin/env python3
"""Replay public target-QNC host-variant and block28 direct-observation evidence."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.analyze_native_qnc_state7_trace import read_state7_trace  # noqa: E402
from harness.analyze_qnc_shared_face_trace import STAR, TARGET, _SHARED, read_shared_trace  # noqa: E402
from harness.analyze_qnc_weighted_ledger import analyze_weighted_ledger  # noqa: E402
from harness.analyze_saved_qnc_scale_backoff import analyze_one_ulp_backoff  # noqa: E402
from harness.native_moment_trace_records import read_moment_trace_v2  # noqa: E402
from harness.replay_qnc_flux_limiter_trace import read_qnc_flux_trace  # noqa: E402


OLD = REPO / "harness/evidence/native_qnc_state7_2026-10-27"
OLD_MANIFEST_SHA = "6737fdabf1c023fe808c00c39b5d1007a43aa1323737f19a63ba1b7fb643ed02"
BASELINE = REPO / "harness/evidence/native_full_physics_observation_2026-10-25"
BASELINE_MANIFEST_SHA = "84a20ae7d337c0c10aec6dd872ae75af75400822f809888a0b35656d3cd12663"
PREDICTION = REPO / "harness/evidence/native_qnc_scale_backoff_2026-10-27"
PREDICTION_MANIFEST_SHA = "c81e545cda01d815f53525364a003b3446ab1f9ecac82048975be9001e38985a"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _files(root: Path, manifest: dict) -> None:
    seen = set()
    for item in manifest["files"]:
        rel = item["path"]
        if (not isinstance(rel, str) or rel in seen or Path(rel).is_absolute()
                or ".." in Path(rel).parts or "__pycache__" in Path(rel).parts
                or Path(rel).suffix == ".pyc"):
            raise ValueError(f"unsafe/repeated evidence path: {rel}")
        seen.add(rel)
        path = root / rel
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"evidence path escapes packet: {rel}")
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or _sha(raw) != item["sha256"]:
            raise ValueError(f"evidence asset changed: {rel}")


def _f32_bits(value: float) -> int:
    return int(np.asarray([value], dtype=np.float32).view(np.uint32)[0])


def _target_moments(folder: Path, state, target: dict) -> dict:
    inventory = read_moment_trace_v2(folder / "host.hex", folder / "kernel.hex")
    owners = [call for call, header in inventory.headers.items()
              if header.owns(221, 63) and header.kts <= 6 <= header.kte]
    if len(owners) != 1:
        raise ValueError("target must have exactly one KDM wrapper owner")
    call = owners[0]

    def record(stage: str, field: str):
        return inventory.values[(call, stage, 221, 6, 63, field)]

    rk = state.at((221, 63, 6), 0, "PRE_MICROPHYSICS", "QNC")
    if (record("MP_INPUT", "NC").bits != rk.bits or
            float(record("FP64_INPUT", "NC").value) != float(rk.f32) or
            _f32_bits(float(record("FP64_OUTPUT", "NC").value)) != record("MOMENTS_POST", "NC").bits or
            record("MOMENTS_POST", "NC").bits != _f32_bits(target["QNCLOUD"]) or
            record("MOMENTS_POST", "QC").bits != _f32_bits(target["QCLOUD"])):
        raise ValueError("target RK/KDM/host moment boundary differs")
    return {"wrapper_call_id": call,
            "rk3_nc_raw": float(rk.f32),
            "fp64_input_nc_raw": float(record("FP64_INPUT", "NC").value),
            "fp64_output_nc_raw": float(record("FP64_OUTPUT", "NC").value),
            "host_moments_post_nc_raw": float(record("MOMENTS_POST", "NC").value)}


def build_analysis() -> dict:
    old_raw = (OLD / "manifest.json").read_bytes()
    if _sha(old_raw) != OLD_MANIFEST_SHA:
        raise ValueError("historical PR461 trace manifest changed")
    old_manifest = json.loads(old_raw)
    _files(OLD, old_manifest)
    historical_analyzer = REPO / (
        "harness/evidence/native_qnc_state_budget_2026-10-27/"
        "source_snapshots/pr461_analyze_native_qnc_state7_trace.py.txt")
    for name, expected in old_manifest["external_source_pins"].items():
        path = historical_analyzer if name == "harness/analyze_native_qnc_state7_trace.py" else REPO / name
        if _sha(path.read_bytes()) != expected:
            raise ValueError(f"historical PR461 trace source differs: {name}")
    old_shared = REPO / "harness/evidence/native_qnc_shared_face_2026-10-27/manifest.json"
    if _sha(old_shared.read_bytes()) != old_manifest["historical_pr459_packet_manifest_sha256"]:
        raise ValueError("historical PR459 shared-face manifest differs")
    prediction_raw = (PREDICTION / "manifest.json").read_bytes()
    if _sha(prediction_raw) != PREDICTION_MANIFEST_SHA:
        raise ValueError("historical saved backoff prediction manifest differs")
    _files(PREDICTION, json.loads(prediction_raw))
    prediction = json.loads((PREDICTION / "analysis.json").read_text())["cases"]
    old_execution = json.loads((OLD / "receipts/execution_summary.json").read_text())
    summary = json.loads((PACKET / "execution_summary.json").read_text())
    target_state = json.loads((PACKET / "target_state.json").read_text())
    runtime_receipt = OLD / "receipts/runtime_flags.json"
    old_runtime = json.loads(runtime_receipt.read_text())
    expected_flags = {"NO_MP_HEATING": "0", "MP_PHYSICS": "137",
                      "RA_LW_PHYSICS": "4", "RA_SW_PHYSICS": "4",
                      "BL_PBL_PHYSICS": "11", "CU_PHYSICS": "37"}
    if any(any(old_runtime["cases"][case]["raw_values"].get(name) != value
               for name, value in expected_flags.items()) for case in ("control", "alpha025")):
        raise ValueError("historical execution physics flags differ")
    if (summary["runtime"]["source_pr461_receipt_sha256"] != _sha(runtime_receipt.read_bytes()) or
            summary["runtime"]["no_mp_heating"] != "0" or
            summary["runtime"]["host_step_seconds"] != 20 or
            summary["runtime"]["native_columns"] != 65988 or
            summary["runtime"]["native_levels"] != 39 or
            not summary["runtime"]["one_rank_one_thread"] or
            not summary["runtime"]["nonadiabatic_processes_enabled"] or
            summary["build"]["base_receipt_sha256"] !=
                "184ba4b4fb0483d60e920d55daa6ea4f0915fe7bc0b62104191e13b4eeccb8b4" or
            summary["build"]["source_sha256"] !=
                "5bf9c6308e129bf24b01ee25c8efeed7c7fe43283213fd968abcb45b6dba5544" or
            summary["build"]["changed_archive_members"] != ["module_advect_em.o"] or
            not summary["build"]["module_interface_unchanged"] or
            summary["model_calls"] != {"host_steps": 4, "KDM_wrapper_entries_expected": 8,
                                       "RTTOV_direct_calls": 2, "RTTOV_K_calls": 0,
                                       "optimizer_calls": 0}):
        raise ValueError("variant build/execution scope differs")
    for case in ("control", "alpha025"):
        arms = summary["runs"][case]
        comparison = summary["off_on_comparisons"][case]
        for mode in ("off", "on"):
            arm = arms[mode]
            prior = old_execution["cases"][case][mode]
            plan_path = PACKET / "receipts/plans" / f"{case}_{mode}.json"
            plan_raw = plan_path.read_bytes()
            plan = json.loads(plan_raw)
            if (_sha(plan_raw) != arm["plan_sha256"] or
                    plan["run_id"] != f"{case}_backoff_v1_{mode}" or
                    plan["trace_mode"] != mode or plan["source_case"] != case or
                    plan["host_steps_requested"] != 1 or plan["RTTOV_calls"] != 0 or
                    plan["optimizer_calls"] != 0 or plan["free_bytes_at_launch"] < 3 * (1 << 30) or
                    plan["expected_reference_checkpoint_sha256"] != prior["checkpoint_sha256"] or
                    plan["source_plan_sha256"] != arm["source_plan_sha256"] or
                    plan["build_receipt_sha256"] != arm["build_receipt_sha256"] or
                    plan["executable_sha256"] != arm["executable_sha256"] or
                    plan["dso_sha256"] != arm["dso_sha256"] or
                    arm["source_plan_sha256"] != prior["source_plan_sha256"] or
                    arm["origin_checkpoint_sha256"] !=
                        "7a353f1fa4f6636864ac169c9ee8d16869d1f38c8e998762c19659404cbb9c8e" or
                    plan["origin_checkpoint_sha256"] != arm["origin_checkpoint_sha256"] or
                    arm["applied_control"] != prior["applied_control"] or
                    arm["build_receipt_sha256"] != summary["private_build_receipt_sha256"] or
                    arm["executable_sha256"] != summary["build"]["executable_sha256"] or
                    arm["dso_sha256"] != summary["build"]["dso_sha256"] or
                    arm["trace_mode"] != mode or arm["source_case"] != case):
                raise ValueError(f"{case} {mode} private run/input binding differs")
        if (arms["off"]["status"] != "PASS" or arms["on"]["status"] != "PASS" or
                arms["off"]["checkpoint_sha256"] != arms["on"]["checkpoint_sha256"] or
                comparison["checkpoint_sha256"] != arms["off"]["checkpoint_sha256"] or
                not comparison["raw_bitwise_equal"] or comparison["variable_count"] != 652 or
                comparison["numeric_elements_compared"] != 322426586 or
                comparison["numeric_element_mismatches"] != 0 or
                not all(arm["ACK_byte_identical_to_historical_same_input"] for arm in arms.values())):
            raise ValueError(f"{case} trace-off/on host receipt differs")
        historical = summary["historical_comparisons"][case]
        if (historical["numeric_elements_compared"] != 322426586 or
                historical["numeric_element_mismatches"] != 2 or
                set(historical["changed_variables"]) != {"QNCLOUD", "RE_CLOUD"} or
                any(row["mismatch_count"] != 1 or row["first_mismatch_index"] != [5, 62, 220]
                    for row in historical["changed_variables"].values())):
            raise ValueError(f"{case} historical checkpoint change scope differs")

    with np.load(BASELINE / "native_full_physics_observation_baseline.npz", allow_pickle=False) as z:
        baseline_m0 = np.asarray(z["m0_mask"], dtype=np.bool_)
    baseline_manifest_raw = (BASELINE / "manifest.json").read_bytes()
    if _sha(baseline_manifest_raw) != BASELINE_MANIFEST_SHA:
        raise ValueError("published baseline observation manifest changed")
    published = json.loads(baseline_manifest_raw)
    if (_sha((BASELINE / "native_full_physics_observation_baseline.npz").read_bytes()) !=
            published["packet"]["sha256"]):
        raise ValueError("published fixed observation support differs")
    with np.load(PACKET / "support_masks.npz", allow_pickle=False) as z:
        m0 = np.asarray(z["m0_mask"], dtype=np.bool_)
        flat = np.asarray(z["flat_indices"], dtype=np.int32)
        masks = {case: np.asarray(z[f"{case}_hard_invalid"], dtype=np.bool_)
                 for case in ("historical_alpha", "control", "alpha025")}
    if (m0.shape != (65988, 7) or not np.array_equal(m0, baseline_m0) or
            not np.array_equal(flat, np.arange(65988, dtype=np.int32)) or
            any(mask.shape != (65988,) for mask in masks.values())):
        raise ValueError("fixed support or hard moment masks differ")
    supported = m0.any(axis=1)
    bad = {case: np.flatnonzero(mask & supported) for case, mask in masks.items()}
    if (len(bad["historical_alpha"]) != 55 or len(bad["control"]) != 0 or
            len(bad["alpha025"]) != 54 or
            set(bad["historical_alpha"]) - set(bad["alpha025"]) != {14728} or
            set(bad["alpha025"]) - set(bad["historical_alpha"])):
        raise ValueError("full-domain hard-admission difference is not target-only")
    support_result = {case: {"invalid_m0_profiles": int(len(indices)),
                             "lost_m0_channel_cells": int(m0[indices].sum())}
                      for case, indices in bad.items()}
    support_result["recovered_flat_index"] = 14728
    mask_path = PACKET / "support_masks.npz"
    mask_receipt = json.loads((PACKET / "support_mask_producer_receipt.json").read_text())
    producer = REPO / "harness/native_qnc_support_mask_producer.py"
    if (mask_receipt["producer_sha256"] != _sha(producer.read_bytes()) or
            mask_receipt["published_M0_sha256"] != published["packet"]["sha256"] or
            mask_receipt["output_npz_sha256"] != _sha(mask_path.read_bytes()) or
            mask_receipt["output_npz_bytes"] != mask_path.stat().st_size or
            mask_receipt["input_checkpoint_sha256"] != {
                "historical_alpha": old_execution["cases"]["alpha025"]["off"]["checkpoint_sha256"],
                "control": summary["runs"]["control"]["off"]["checkpoint_sha256"],
                "alpha025": summary["runs"]["alpha025"]["off"]["checkpoint_sha256"]} or
            mask_receipt["hard_invalid_M0_profiles"] != {
                name: value["invalid_m0_profiles"] for name, value in support_result.items()
                if name != "recovered_flat_index"} or
            mask_receipt["M0_profiles"] != int(supported.sum()) or
            mask_receipt["M0_channel_cells"] != int(m0.sum()) or
            mask_receipt["recovered_flat_indices"] != [14728] or
            any(mask_receipt[key] != 0 for key in ("host_calls", "KDM6_calls", "RTTOV_calls"))):
        raise ValueError("public hard-mask producer receipt differs")

    optical = target_state["optical_config"]
    if optical["ncmin_land_raw"] != 10.0 or optical["ncmin_sea_raw"] != 10.0:
        raise ValueError("saved optical NC gate differs")
    cases = {}
    observations = {}
    for case in ("control", "alpha025"):
        folder = PACKET / "data" / case
        listed = summary["runs"][case]["on"]["traces"]
        for tag, item in listed.items():
            path = PACKET / item["path"]
            if path != folder / {"state7": "qnc_state7.tsv", "shared": "qnc_shared.tsv",
                                 "flux": "qnc_flux.tsv", "host": "host.hex", "kernel": "kernel.hex"}[tag]:
                raise ValueError("trace path differs")
            raw = path.read_bytes()
            if len(raw) != item["bytes"] or _sha(raw) != item["sha256"]:
                raise ValueError("same-run trace receipt differs")
        state = read_state7_trace(folder / "qnc_state7.tsv")
        shared = read_shared_trace(folder / "qnc_shared.tsv")
        flux = read_qnc_flux_trace(folder / "qnc_flux.tsv").select_qnc_scalar_group()
        original_data = OLD / "data" / case
        original_flux = read_qnc_flux_trace(original_data / "qnc_flux.tsv").select_qnc_scalar_group()
        original_scale = original_flux.at(3, "RK3_PD_LIMIT_CELL", "SCALE")
        variant_scale = flux.at(3, "RK3_PD_LIMIT_CELL", "SCALE")
        if int(variant_scale.bits) != int(original_scale.bits) - 1:
            raise ValueError(f"{case} target scale is not one binary32 ULP lower")
        owner = shared["owner_call_id"]
        for _, neighbor, target_face, neighbor_face, _, _ in _SHARED:
            if (shared["records"][(owner, "RK3_POST", *TARGET, target_face)] !=
                    shared["records"][(owner, "RK3_POST", *neighbor, neighbor_face)]):
                raise ValueError("modified correction face is not shared bitwise")
        old_face = analyze_weighted_ledger(read_shared_trace(OLD / "data" / case / "qnc_shared.tsv"), run_id=case)
        new_face = analyze_weighted_ledger(shared, run_id=case)
        if old_face["exact_face_total"]["exact"] != new_face["exact_face_total"]["exact"]:
            raise ValueError("paired target backoff changed seven-cell outer face total")
        predicted = analyze_one_ulp_backoff(
            read_state7_trace(original_data / "qnc_state7.tsv"),
            read_shared_trace(original_data / "qnc_shared.tsv"), original_flux, case=case)
        for changed in predicted["changed_shared_correction_faces"]:
            key = (owner, "RK3_POST", *TARGET, changed["target_face"])
            if f"{shared['records'][key]:08X}" != changed["after_hex"]:
                raise ValueError("actual scaled correction face differs from saved prediction")
        for i, k, j in STAR:
            label = f"i{i}_j{j}_k{k}"
            actual_rk = float(state.at((i, j, k), 3, "RKSCALAR_AFTER", "QNC").f32)
            if actual_rk not in predicted["cells"][label]["candidate_source_compatible_f32_qnc_raw"]:
                raise ValueError("actual seven-cell RK state differs from saved prediction")
        target = target_state["cases"][case]
        if (target["checkpoint_sha256"] != summary["runs"][case]["off"]["checkpoint_sha256"] or
                target["native_target_state"]["XLAND"] != 1.0 or
                target["rttov_layer61"]["p"][0] != target["native_target_state"]["P_CENTER_HPA"]):
            raise ValueError("target checkpoint/profile coordinate differs")
        conversion = target["optical_number_conversion"]
        al = np.float32(conversion["AL_raw_f32"])
        alb = np.float32(conversion["ALB_raw_f32"])
        rho = np.float32(np.float32(1.0) / np.float32(al + alb))
        raw_nc = target["native_target_state"]["QNCLOUD"]
        bridge_nc = raw_nc / float(rho)
        dsd_nc = bridge_nc * float(rho)
        inactive = dsd_nc <= optical["ncmin_land_raw"]
        if (_f32_bits(float(rho)) != _f32_bits(conversion["rho_d_from_f32_AL_ALB_kg_dry_m3"]) or
                bridge_nc != conversion["bridge_input_raw_div_rho_d"] or
                dsd_nc != conversion["dsd_gate_nc_bridge_times_rho_d"] or
                conversion["ncmin_threshold_raw_coordinate"] != optical["ncmin_land_raw"] or
                conversion["inactive_slope_gate"] is not inactive):
            raise ValueError("target dry-number optical gate conversion differs")
        moments = _target_moments(folder, state, target["native_target_state"])
        predicted_rk = prediction[case]["cells"]["i221_j63_k6"]["candidate_source_compatible_f32_qnc_raw"]
        if (moments["rk3_nc_raw"] != float(state.at((221, 63, 6), 3, "RKSCALAR_AFTER", "QNC").f32) or
                predicted_rk != [moments["rk3_nc_raw"]] or
                not math.isclose(target["rttov_layer61"]["hydro_deff"][5],
                                 52.0 if case == "control" else 5.02, abs_tol=1e-12)):
            raise ValueError("target RK or liquid diameter differs")
        cases[case] = {"scale_original_hex": original_scale.raw_hex,
                       "scale_variant_hex": variant_scale.raw_hex,
                       "saved_prediction_scaled_faces_confirmed": 6,
                       "saved_prediction_rk_cells_confirmed": 7,
                       "shared_correction_pairs_bitwise_equal": 6,
                       "seven_cell_exact_face_total_unchanged": True,
                       "target_moments": moments,
                       "target_checkpoint_state": target["native_target_state"],
                       "target_rttov_layer61": target["rttov_layer61"],
                       "optical_number_conversion": conversion,
                       "liquid_slope_inactive_at_ncmin": inactive}
        direct = summary["block28_direct"][case]
        path = PACKET / direct["capture_path"]
        if path != folder / "block28_direct.npz" or _sha(path.read_bytes()) != direct["capture_sha256"]:
            raise ValueError("block28 direct capture differs")
        with np.load(path, allow_pickle=False) as z:
            block_flat = np.asarray(z["flat_indices"], dtype=np.int32)
            obs = np.asarray(z["obs_bt_k"], dtype=np.float64)
            bt = np.asarray(z["bt_kma_v3_0"], dtype=np.float64)
            mask = np.asarray(z["m0_mask"], dtype=np.bool_)
            actual = np.asarray(z["actual_valid_mask"], dtype=np.bool_)
            profile_valid = np.asarray(z["profile_valid"], dtype=np.bool_)
            quality = np.asarray(z["quality"], dtype=np.int32)
        if (not np.array_equal(block_flat, np.arange(14336, 14848, dtype=np.int32)) or
                obs.shape != (512, 7) or bt.shape != (512, 7) or
                profile_valid.shape != (512,) or int(profile_valid.sum()) != direct["nprofiles"] or
                not np.array_equal(mask, m0[14336:14848]) or
                not np.array_equal(mask & profile_valid[:, None], mask) or
                not np.array_equal(mask & actual, mask) or not np.isfinite(bt[mask]).all() or
                not np.array_equal(quality[mask], np.zeros(int(mask.sum()), dtype=np.int32)) or
                direct["direct_calls"] != 1 or direct["K_calls"] != 0 or
                direct["M0_cells"] != int(mask.sum()) or direct["M0_cells_lost"] != 0):
            raise ValueError("block28 direct call or fixed support differs")
        target_compact_row = int(profile_valid[:392].sum())
        if not profile_valid[392] or target_compact_row != 390:
            raise ValueError("target block row to RTTOV compact profile mapping differs")
        residual = (bt - obs)[mask]
        observations[case] = {"block_index": 28, "original_B": 512,
                              "rttov_input_profiles": direct["nprofiles"],
                              "target_full_block_row_zero_based": 392,
                              "target_compact_profile_row_zero_based": target_compact_row,
                              "target_rttov_profile_directory_one_based": target_compact_row + 1,
                              "M0_channel_cells": int(mask.sum()),
                              "M0_loss": 0,
                              "block_M0_rmse_K": math.sqrt(math.fsum(float(x * x) for x in residual) / residual.size),
                              "target_BT_K": bt[392].tolist(),
                              "target_observation_K": obs[392].tolist(),
                              "target_sim_minus_obs_K": (bt[392] - obs[392]).tolist()}
    control = np.abs(np.asarray(observations["control"]["target_sim_minus_obs_K"]))
    candidate = np.abs(np.asarray(observations["alpha025"]["target_sim_minus_obs_K"]))
    return {"schema": "kdm6.native_qnc_target_backoff_host_public_analysis.v1",
            "status": "TARGET_HOST_AND_BLOCK28_LOCAL_RESPONSE_CONFIRMED_GLOBAL_SUPPORT_FAILED",
            "host_execution_from_receipts": summary["model_calls"],
            "offline_replay_model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0},
            "off_on_checkpoint_comparison": summary["off_on_comparisons"],
            "historical_checkpoint_change": summary["historical_comparisons"],
            "support": support_result,
            "cases": cases,
            "block28_direct": observations,
            "target_abs_residual_candidate_minus_control_K": (candidate - control).tolist(),
            "block28_M0_RMSE_candidate_minus_control_K":
                observations["alpha025"]["block_M0_rmse_K"] - observations["control"]["block_M0_rmse_K"],
            "full_fixed_support_candidate_cost_defined": False,
            "limits": {"raw_NC_physical_units_certified": False,
                       "general_limiter_rule_certified": False,
                       "full_domain_fixed_support_preserved": False,
                       "observation_pixel_time_verified": False,
                       "second_assimilation_performed": False}}


def main() -> int:
    manifest = json.loads((PACKET / "manifest.json").read_text())
    if manifest.get("schema") != "kdm6.native_qnc_target_backoff_host_public_packet.v1":
        raise ValueError("wrong host-backoff packet schema")
    if (manifest.get("historical_pr461_manifest_sha256") != OLD_MANIFEST_SHA or
            manifest.get("baseline_observation_manifest_sha256") != BASELINE_MANIFEST_SHA or
            manifest.get("historical_pr463_prediction_manifest_sha256") != PREDICTION_MANIFEST_SHA):
        raise ValueError("host-backoff historical manifest pins differ")
    _files(PACKET, manifest)
    for name, expected in manifest["external_source_pins"].items():
        if _sha((REPO / name).read_bytes()) != expected:
            raise ValueError(f"host-backoff replay source changed: {name}")
    result = build_analysis()
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if (PACKET / "analysis.json").read_bytes() != raw:
        raise ValueError("host-backoff analysis differs from published bytes")
    print(json.dumps({"status": "REPLAY_PASSED", "analysis_sha256": _sha(raw),
                      "offline_model_calls": result["offline_replay_model_calls"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
