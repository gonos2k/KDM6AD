#!/usr/bin/env python3
"""Preflight and run one direct-RTTOV H comparison over a fixed native 3x3 patch.

The default command writes a hash-bound no-H plan and verifies whether the
already executed PR398 center-column H can serve as the center row. The explicit
one-shot command runs H exactly once for each of the eight neighbors only when
that center reuse is fully established. It never calls the KDM6 model M step,
optimization, or a native forecast.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))

from kdm6.da_driver import OsseObsConfig, batched_allsky_bt  # noqa: E402
from kdm6.obs.model_profile_builder import (  # noqa: E402
    RttovProfileConfig, qv_to_q_ppmv_moist,
)

PACKET = ROOT / "harness/evidence/pr399_vertical_neighbor_2026-10-10"
PLAN = PACKET / "NEIGHBOR_PLAN_attempt2.json"
RESULT = PACKET / "NEIGHBOR_RESULT_attempt2.json"
REPORT = PACKET / "NEIGHBOR_REPORT_attempt2.md"
TABLE = PACKET / "NEIGHBOR_TABLE_attempt2.csv"
OUT = ROOT / "graphify-out/pr399-native-neighbor-h-attempt2-2026-10-10"
PRIVATE = OUT / "private"
STARTED = PRIVATE / "STARTED_ONCE.json"
FAILURE = PRIVATE / "FAILURE.json"
CANONICAL_DIR = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr399_native_neighbor_h_20261010")
CANONICAL_NPZ = CANONICAL_DIR / "attempt2_native_3x3_direct_h_inputs_outputs.npz"
OFFLINE_ROOT = PRIVATE / "offline_fixture_preflight"
OFFLINE_RECEIPT = PRIVATE / "OFFLINE_FIXTURE_PREFLIGHT.json"
ATTEMPT1_FAILURE = ROOT / "graphify-out/pr399-native-neighbor-h-2026-10-10/private/FAILURE.json"

NATIVE_RESULT = PACKET.parent / "pr398_spatial_representativeness_2026-10-10/NATIVE_PATCH_RESULT_v3.json"
NATIVE_NPZ = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr398_sensitivity_20261010/native_patch_3x3_frames_1_4_6_v3.npz")
INTAKE_MANIFEST = ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/INTAKE.json"
INTAKE_NPZ = ROOT / "graphify-out/pr395-native-tq-intake-2026-10-10/private/native_column_8frame.npz"
OBS_RECEIPT = ROOT / "harness/evidence/pr395_observation_matchup_2026-10-10/RECEIPT.json"
AMI_CANDIDATE = ROOT / "harness/evidence/VIIRS_AMI_candidate_result_2026-10-07.json"
V2_PLAN = ROOT / "harness/evidence/pr398_followup_2026-10-10/PREDECLARED_v2.json"
V2_RESULT = ROOT / "harness/evidence/pr398_followup_2026-10-10/RESULT_v2.json"
V2_DRIVER = ROOT / "harness/evidence/pr398_followup_2026-10-10/run_time_geometry_sensitivity_v2.py"
ANALYSIS_DRIVER = ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/run_analysis.py"
NATIVE_READER = ROOT / "harness/evidence/native358_artifact_diag_2026-10-08/recipe/run_native_kma_bt_frames.py"
FRAME_POSITION = 0  # frame index 1, exactly 2025-07-19 05:56:00
FRAME_INDEX = 1
TIME_LABEL = "2025-07-19_05:56:00"
CHANNELS = tuple(range(10, 17))
CHANNEL_NAMES = ("wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133")
STATE_FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg")
FORCING_FIELDS = ("rho", "pii", "p", "delz")
SURFACE_FIELDS = ("TSK", "T2", "Q2", "U10", "V10", "HGT", "xland", "seaice",
                  "latitude_deg", "longitude_deg")
F64 = {"dtype": torch.float64}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def array_sha256(values) -> str:
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import source module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_paths() -> dict[str, Path]:
    return {
        "neighbor_rttov": Path(__file__).resolve(),
        "analysis_driver": ANALYSIS_DRIVER,
        "native_reader": NATIVE_READER,
        "v2_direct_h_driver": V2_DRIVER,
        "intake_consumer": ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/intake_native_tq.py",
        "da_driver": ROOT / "oracle/kdm6/da_driver.py",
        "rttov_case_writer": ROOT / "oracle/kdm6/obs/rttov_case_writer.py",
        "rttov_input_builder": ROOT / "oracle/kdm6/obs/rttov_input_builder.py",
        "rttov_runner": ROOT / "oracle/kdm6/obs/rttov_runner.py",
        "ami_bt_coordinate": ROOT / "oracle/kdm6/obs/ami_bt_coordinate.py",
        "model_profile_builder": ROOT / "oracle/kdm6/obs/model_profile_builder.py",
        "allsky_shard": ROOT / "oracle/kdm6/obs/allsky_shard.py",
        "allsky_observation_operator": ROOT / "oracle/kdm6/obs/rttov_obs_operator.py",
        "observation_loss": ROOT / "oracle/kdm6/obs/obs_loss.py",
    }


def _load_inputs() -> dict:
    if not all(p.is_file() for p in (NATIVE_RESULT, NATIVE_NPZ, INTAKE_MANIFEST, INTAKE_NPZ,
                                      OBS_RECEIPT, AMI_CANDIDATE, V2_PLAN, V2_RESULT)):
        raise FileNotFoundError("one or more predeclared native/observation/PR398 evidence inputs are missing")
    native_result = json.loads(NATIVE_RESULT.read_text())
    native_plan = json.loads((PACKET.parent / "pr398_spatial_representativeness_2026-10-10/NATIVE_PATCH_v3.json").read_text())
    intake = json.loads(INTAKE_MANIFEST.read_text())
    intake_npz_sha = sha256(INTAKE_NPZ)
    native_npz_sha = sha256(NATIVE_NPZ)
    if (native_plan.get("schema") != "pr398_native_patch_plan_v3"
            or native_plan.get("status") != "PREDECLARED_NO_STATE_DIAGNOSTICS"
            or native_result.get("schema") != "pr398_native_patch_result_v3"
            or native_result.get("status") != "READY_NATIVE_PATCH_DIAGNOSTIC_ONLY"
            or native_result.get("H_calls") != 0 or native_result.get("M_calls") != 0
            or native_result.get("center_matches_intake_at_all_frames") is not True
            or native_result.get("canonical_npz", {}).get("sha256") != native_npz_sha
            or native_plan.get("outputs", {}).get("canonical_private_npz") != str(NATIVE_NPZ)
            or native_npz_sha != "947c72c12ebe289b7ddc84fba1281635d77ffbcfe23f204345cc97abeebc1c21"):
        raise ValueError("native patch result/plan does not bind the canonical V3 NPZ")
    if (intake.get("schema") != "pr395_native_tq_intake_v1"
            or intake.get("status") != "READY_VALID_NATIVE_INTAKE"
            or intake.get("npz", {}).get("sha256") != intake_npz_sha
            or intake.get("science_approved") is not False):
        raise ValueError("PR395 native intake is not the hash-bound diagnostic-only case")
    with np.load(NATIVE_NPZ, allow_pickle=False) as archive:
        native = {key: archive[key].copy() for key in archive.files}
    with np.load(INTAKE_NPZ, allow_pickle=False) as archive:
        intake_arrays = {key: archive[key].copy() for key in archive.files}
    receipt = json.loads(OBS_RECEIPT.read_text())
    candidate = json.loads(AMI_CANDIDATE.read_text())
    plan = json.loads(V2_PLAN.read_text())
    result = json.loads(V2_RESULT.read_text())
    if (plan.get("schema") != "pr398_time_geometry_sensitivity_plan_v2"
            or result.get("schema") != "pr398_time_geometry_sensitivity_result_v2"
            or result.get("status") != "ALL_PREDECLARED_CASES_RETURNED"
            or len(result.get("results", [])) != 6
            or result.get("plan_sha256") != sha256(V2_PLAN)
            or result.get("driver_sha256") != sha256(V2_DRIVER)
            or plan.get("driver_sha256") != sha256(V2_DRIVER)
            or plan.get("execution", {}).get("actual_BT_available") is not False
            or result.get("n_model_M_calls") != 0
            or result.get("n_backward_calls") != 0):
        raise ValueError("PR398 V2 direct-H result is not a complete pinned six-row diagnostic")
    if (receipt.get("schema") != "pr395_observation_matchup_receipt_v1"
            or receipt.get("physical_matchup_approved") is not False
            or receipt["fixed_candidate"].get("native_j_i_zero_based") != [86, 48]
            or receipt["ami_candidate_result"].get("row_col_zero_based") != [320, 48]
            or receipt["channel_order"][2:9] != list(CHANNEL_NAMES)):
        raise ValueError("fixed observation/native candidate contract changed")
    if (native.get("frame_indices", np.array([])).tolist() != [1, 4, 6]
            or native.get("time_labels_ascii") is None
            or "2025-07-19_05:56:00" not in native["time_labels_ascii"].tobytes().decode("ascii")
            or native["native_patch__state__th"].shape != (3,3,3,39)
            or native["native_patch__p_half_calc_p8w_bottomup_Pa"].shape != (3,3,3,40)):
        raise ValueError("V3 native patch does not preserve exact frame/time index 1")
    return {
        "native_result": native_result, "native_plan": native_plan,
        "native_npz_sha256": native_npz_sha, "native": native,
        "intake_manifest": intake, "intake_manifest_sha256": sha256(INTAKE_MANIFEST),
        "intake_npz_sha256": intake_npz_sha, "intake_arrays": intake_arrays,
        "receipt": receipt, "receipt_sha256": sha256(OBS_RECEIPT),
        "candidate": candidate, "candidate_sha256": sha256(AMI_CANDIDATE),
        "v2_plan": plan, "v2_plan_sha256": sha256(V2_PLAN),
        "v2_result": result, "v2_result_sha256": sha256(V2_RESULT),
    }


def _profile_for_cell(reader, native: dict[str, np.ndarray], row: int, col: int,
                      reference: dict) -> tuple:
    frame = {
        "p_pa": native["native_patch__p_pa"][FRAME_POSITION, row, col],
        "th": native["native_patch__state__th"][FRAME_POSITION, row, col],
        "pii": native["native_patch__pii"][FRAME_POSITION, row, col],
        "p8w_pa": native["native_patch__p_half_calc_p8w_bottomup_Pa"][FRAME_POSITION, row, col],
        "state": {"QVAPOR": native["native_patch__wrf_raw__QVAPOR"][FRAME_POSITION, row, col]},
    }
    return reader.extend_above_native_top(frame, reference)


def _cell_metadata(native: dict[str, np.ndarray], row: int, col: int,
                   profile: tuple, baseline_case: dict, baseline_plan_case: dict) -> dict:
    state_hash = {
        field: array_sha256(native[f"native_patch__state__{field}"][FRAME_POSITION, row, col][None, :])
        for field in STATE_FIELDS
    }
    forcing_key = {"rho": "rho", "pii": "pii", "p": "p_pa", "delz": "delz"}
    forcing_hash = {
        field: array_sha256(native[f"native_patch__{key}"][FRAME_POSITION, row, col][None, :])
        for field, key in forcing_key.items()
    }
    rho_d = native["native_patch__rho_d"][FRAME_POSITION, row, col]
    calculated_rho_d = native["native_patch__rho"][FRAME_POSITION, row, col] / (
        1.0 + native["native_patch__state__qv"][FRAME_POSITION, row, col])
    if not np.array_equal(rho_d, calculated_rho_d):
        raise ValueError(f"rho_d mismatch at j={85+row}, i={47+col}")
    rho_d_hash = array_sha256(rho_d[None, :])
    surface_hash = {
        field: array_sha256(np.asarray([native[f"native_patch__surface__{field}"][FRAME_POSITION,row,col]],
                                       dtype=np.float64))
        for field in SURFACE_FIELDS
    }
    p8w = native["native_patch__p_half_calc_p8w_bottomup_Pa"][FRAME_POSITION, row, col]
    profile_names = ("p_lay_hPa", "p_half_hPa", "t_native_plus_fixed_upper_reference_K",
                     "q_native_plus_fixed_upper_reference_ppmv", "o3_ppmv", "co2_ppmv")
    profile_hash = {name: array_sha256(values) for name, values in zip(profile_names, profile)}
    profile_file_names = ("p.txt", "p_half.txt", "t.txt", "q.txt", "o3.txt", "co2.txt")
    profile_file_hash = {
        filename: hashlib.sha256("".join(
            f"{float(value):{'.16E' if filename in ('t.txt','q.txt') else '.17E'}}\n"
            for value in values).encode()).hexdigest()
        for filename, values in zip(profile_file_names, profile)
    }
    offline_profile_file_hash = {
        filename: hashlib.sha256("".join(f"{float(value):.17E}\n" for value in values).encode()).hexdigest()
        for filename, values in zip(profile_file_names, profile)
    }
    state_forcing_match = (state_hash == {
        key.removeprefix("native_window_state__"): value
        for key, value in baseline_case["state_sha256_by_field"].items()
    } and forcing_hash == baseline_case["forcing_sha256_by_field"]
      and rho_d_hash == baseline_case["rho_d_sha256"]
      and array_sha256(p8w) == baseline_plan_case["p8w_sha256"])
    profile_match = profile_hash == baseline_case["rttov_profile_sha256"]
    surface_match = surface_hash == baseline_plan_case["surface_sha256_by_field"]
    return {
        "row": row, "col": col, "j": 85 + row, "i": 47 + col,
        "lat_lon_deg": [float(native["native_patch__surface__latitude_deg"][FRAME_POSITION,row,col]),
                        float(native["native_patch__surface__longitude_deg"][FRAME_POSITION,row,col])],
        "state_sha256_by_field": state_hash, "forcing_sha256_by_field": forcing_hash,
        "rho_d_sha256": rho_d_hash, "p8w_sha256": array_sha256(p8w),
        "surface_sha256_by_field": surface_hash, "rttov_profile_sha256": profile_hash,
        "rttov_profile_file_sha256": profile_file_hash,
        "offline_profile_file_sha256": offline_profile_file_hash,
        "exact_state_forcing_pressure_rho_d_match_to_reused_center": bool(state_forcing_match),
        "exact_surface_match_to_reused_center": bool(surface_match),
        "exact_pressure_gas_profile_match_to_reused_center": bool(profile_match),
    }


def _baseline_context(ctx: dict, analysis, reader) -> tuple[dict, dict, dict, dict, list[dict]]:
    native = ctx["native"]
    reference = reader.load_reference()
    baseline_case = next(
        row for row in ctx["v2_result"]["results"]
        if row["case_id"] == "frame1_fixed_AMI_candidate_pixel_center")
    baseline_plan_case = next(
        row for row in ctx["v2_plan"]["planned_cases"]
        if row["case_id"] == "frame1_fixed_AMI_candidate_pixel_center")
    if (baseline_case.get("all_seven_rad_quality_zero") is not True
            or baseline_case.get("Jo_huber_K_units") is None
            or baseline_case.get("rad_quality") != [[0.0] * 7]
            or baseline_case.get("frozen_support") != [[1.0] * 7]
            or baseline_case.get("geometry") != baseline_plan_case.get("geometry")
            or baseline_case.get("geometry_scenario") != "fixed_AMI_candidate_pixel_center"):
        raise ValueError("existing PR398 center H is not accepted on the fixed all-seven support")
    comparison = ctx["v2_plan"].get("observations_and_support", {})
    profile_policy = ctx["v2_plan"].get("profile_policy", {})
    if (comparison.get("sigma_K") != 1.0 or comparison.get("bias_K") != 0.0
            or comparison.get("huber_delta_K") != 1.0
            or comparison.get("channels_1based") != list(CHANNELS)
            or comparison.get("channel_names") != list(CHANNEL_NAMES)
            or profile_policy.get("dry_number") is not True
            or profile_policy.get("ami_kma_bt") is not True
            or profile_policy.get("ncmin_land") != 10.0
            or profile_policy.get("ncmin_sea") != 10.0
            or profile_policy.get("t_q_blend_octaves") != 0.0):
        raise ValueError("PR398 central H configuration differs from PR399's fixed cost/operator policy")
    obs = ctx["receipt"]["ami_candidate_result"]
    target = np.asarray(obs["bt_K"][2:9], dtype=np.float64).reshape(1, 7)
    dqf = np.asarray(obs["dqf"][2:9], dtype=np.float64).reshape(1, 7)
    mask = np.asarray(baseline_case["frozen_support"], dtype=np.float64)
    if (not np.isfinite(target).all() or not np.array_equal(dqf, np.zeros((1, 7)))
            or not np.array_equal(mask, np.ones((1, 7)))
            or baseline_case["channels_1based"] != list(CHANNELS)
            or baseline_case["channel_names"] != list(CHANNEL_NAMES)):
        raise ValueError("observation/frozen support differs from the V2 seven-channel diagnostic")
    if array_sha256(target) != comparison.get("target_bt_sha256_f64"):
        raise ValueError("fixed AMI target BT differs from the central PR398 run")
    from kdm6.obs.obs_loss import compute_obs_loss
    center_jo_recomputed = float(compute_obs_loss(
        torch.as_tensor(baseline_case["BT_K"], **F64),
        {"bt": torch.as_tensor(target, **F64), "bias": 0.0},
        torch.as_tensor(mask, **F64), 1.0, delta=1.0))
    if not np.isclose(center_jo_recomputed, baseline_case["Jo_huber_K_units"], rtol=0.0, atol=1e-12):
        raise ValueError("reused central cost does not recompute under the exact fixed cost contract")
    metadata = []
    profiles = []
    for row in range(3):
        for col in range(3):
            profile = _profile_for_cell(reader, native, row, col, reference)
            if tuple(map(len, profile)) != (66, 67, 66, 66, 66, 66):
                raise ValueError(f"cell {(row,col)} did not produce the fixed native+reference 66/67 profile")
            profiles.append(profile)
            metadata.append(_cell_metadata(native, row, col, profile, baseline_case, baseline_plan_case))
    center = next(m for m in metadata if (m["row"], m["col"]) == (1, 1))
    source_assets = load_module(V2_DRIVER, "pr399_current_v2_source_asset_map")._source_asset_map(analysis)
    if source_assets != ctx["v2_plan"]["execution"]["rttov_assets"]:
        raise ValueError("current RTTOV/static fixture assets differ from the V2 source-pinned profile")
    static_surface = source_assets["static_surface_skin"]
    if static_surface != ctx["v2_plan"]["profile_policy"]["static_template_files_used_and_pinned"]["static_surface_skin"]:
        raise ValueError("static skin source/hash differs from the existing direct-H plan")
    center_profile_dir = (Path(baseline_case["case_output_dir"])
                          / "in/profiles/001/atm")
    actual_center_profile_files = {
        name: sha256(center_profile_dir / name)
        for name in ("p.txt", "p_half.txt", "t.txt", "q.txt", "o3.txt", "co2.txt")
        if (center_profile_dir / name).is_file()
    }
    if len(actual_center_profile_files) != 6:
        raise FileNotFoundError("accepted PR398 center H case lacks its exact active six-profile input files")
    # The center can be reused only when every state/forcing, pressure, optical
    # density, surface, profile, geometry, fixed cost, and asset binding matches.
    reuse = bool(center["exact_state_forcing_pressure_rho_d_match_to_reused_center"]
                 and center["exact_surface_match_to_reused_center"]
                 and center["exact_pressure_gas_profile_match_to_reused_center"]
                 and baseline_case["geometry"] == baseline_plan_case["geometry"]
                 and baseline_case["Jo_huber_K_units"] is not None
                 and center["rttov_profile_file_sha256"] == actual_center_profile_files)
    if not reuse:
        raise RuntimeError("existing central H does not fully bind the fixed PR399 center; do not run neighbor batch")
    return baseline_case, baseline_plan_case, source_assets, {
        "target_bt_K": target, "dqf": dqf, "frozen_mask": mask,
        "profiles": profiles, "reuse_central_result": True,
        "central_active_profile_file_sha256": actual_center_profile_files,
    }, metadata


def _offline_fixture_preflight(metadata: list[dict], profiles: list[tuple],
                               analysis, source_assets: dict) -> list[dict]:
    """Prepare and validate every neighbor fixture without constructing or running H."""
    profile_names = ("p.txt", "p_half.txt", "t.txt", "q.txt", "o3.txt", "co2.txt")
    neighbors = [(m, p) for m, p in zip(metadata, profiles)
                 if (m["row"], m["col"]) != (1, 1)]
    current_sources = {key: sha256(path) for key, path in _source_paths().items()}
    if OFFLINE_RECEIPT.exists():
        receipt = json.loads(OFFLINE_RECEIPT.read_text())
        if (receipt.get("schema") != "pr399_offline_fixture_preflight_v1"
                or receipt.get("source_sha256") != current_sources
                or receipt.get("rttov_assets") != source_assets
                or len(receipt.get("neighbor_fixtures", [])) != 8):
            raise ValueError("existing offline fixture preflight differs from current source/assets/case count")
        for record, (meta, profile) in zip(receipt["neighbor_fixtures"], neighbors):
            case_id = f"frame1_j{meta['j']}_i{meta['i']}_fixed_AMI_geometry"
            fixture = Path(record["fixture_path"])
            expected_file_hashes = {name: meta["offline_profile_file_sha256"][name]
                                    for name in profile_names}
            actual_file_hashes = {name: sha256(fixture / "in/profiles/001/atm" / name)
                                  for name in profile_names}
            if (record.get("case_id") != case_id
                    or record.get("fixture_file_sha256") != actual_file_hashes
                    or actual_file_hashes != expected_file_hashes
                    or record.get("profile_array_sha256") != meta["rttov_profile_sha256"]):
                raise ValueError(f"offline fixture changed or no longer matches expected profile for {case_id}")
        return receipt["neighbor_fixtures"]

    if OFFLINE_ROOT.exists():
        raise FileExistsError("offline fixture directory exists without its receipt; refuse to repair/overwrite")
    OFFLINE_ROOT.mkdir(parents=True, exist_ok=False, mode=0o700)
    records = []
    for meta, profile in neighbors:
        case_id = f"frame1_j{meta['j']}_i{meta['i']}_fixed_AMI_geometry"
        fixture = OFFLINE_ROOT / f"fixture-{case_id}"
        p_lay, p_half, t_profile, q_profile, o3, co2 = profile
        arrays = {
            "p_lay_rttov_topdown_hPa": p_lay,
            "p_half_rttov_topdown_hPa": p_half,
            "t_rttov_topdown_K": t_profile,
            "q_rttov_topdown_ppmv": q_profile,
            "o3_rttov_topdown_ppmv": o3,
            "co2_rttov_topdown_ppmv": co2,
        }
        fixture_info = analysis._prepare_fixture_copy(
            analysis.TEMPLATE_FIXTURE.resolve(), fixture, arrays)
        atm = fixture / "in/profiles/001/atm"
        for filename, values in (("p.txt", p_lay), ("p_half.txt", p_half),
                                 ("o3.txt", o3), ("co2.txt", co2)):
            _write_vector(atm / filename, values)
        file_hashes = {name: sha256(atm / name) for name in profile_names}
        loaded_vectors = {name: np.loadtxt(atm / name, dtype=np.float64) for name in profile_names}
        expected_vectors = dict(zip(profile_names, profile))
        if any(not np.array_equal(loaded_vectors[name], expected_vectors[name])
               for name in profile_names):
            raise ValueError(f"prepared RTTOV profile text changed a value at {case_id}")
        fixture_info["prepared_files_sha256"].update({
            f"in/profiles/001/atm/{name}": file_hashes[name] for name in profile_names
        })
        records.append({
            "case_id": case_id, "j": meta["j"], "i": meta["i"],
            "fixture_path": str(fixture), "fixture_file_sha256": file_hashes,
            "profile_array_sha256": meta["rttov_profile_sha256"],
            "profile_lengths": [int(x.size) for x in profile],
            "fixture_info": fixture_info,
            "h_calls": 0,
        })
    receipt = {
        "schema": "pr399_offline_fixture_preflight_v1",
        "status": "ALL_EIGHT_FIXTURES_PREPARED_NO_H",
        "source_sha256": current_sources,
        "rttov_assets": source_assets,
        "neighbor_fixture_count": 8,
        "profile_keys_supplied_to_existing_helper": [
            "p_lay_rttov_topdown_hPa", "p_half_rttov_topdown_hPa",
            "t_rttov_topdown_K", "q_rttov_topdown_ppmv",
            "o3_rttov_topdown_ppmv", "co2_rttov_topdown_ppmv",
        ],
        "neighbor_fixtures": records,
        "H_calls": 0, "M_calls": 0, "optimizer_calls": 0,
    }
    with OFFLINE_RECEIPT.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    OFFLINE_RECEIPT.chmod(0o600)
    return records


def _plan_payload() -> dict:
    ctx = _load_inputs()
    analysis = load_module(ANALYSIS_DRIVER, "pr399_pinned_analysis_driver")
    reader = load_module(NATIVE_READER, "pr399_native_profile_reader")
    baseline_case, baseline_plan_case, assets, objective, metadata = _baseline_context(ctx, analysis, reader)
    offline_fixtures = _offline_fixture_preflight(metadata, objective["profiles"], analysis, assets)
    source_hashes = {key: sha256(path) for key, path in _source_paths().items()}
    for key, digest in ctx["v2_plan"]["execution"]["source_sha256"].items():
        if key in source_hashes and source_hashes[key] != digest:
            raise ValueError(f"production source {key} changed since central H: {source_hashes[key]} != {digest}")
    profile_specs = []
    for cell, profile in zip(metadata, objective["profiles"]):
        profile_specs.append({
            **{key: value for key, value in cell.items() if key != "row" and key != "col"},
            "profile_lengths": [len(p) for p in profile],
        })
    center_reuse = {
        "case_id": baseline_case["case_id"],
        "result_sha256": ctx["v2_result_sha256"],
        "plan_sha256": ctx["v2_plan_sha256"],
        "BT_K": baseline_case["BT_K"],
        "rad_quality": baseline_case["rad_quality"],
        "Jo_huber_K_units": baseline_case["Jo_huber_K_units"],
        "all_seven_rad_quality_zero": baseline_case["all_seven_rad_quality_zero"],
        "actual_active_profile_file_sha256": objective["central_active_profile_file_sha256"],
        "reuse_reason": "exact full State/Forcing/rho_d/P8W/surface/profile/geometry/options/source-asset binding to native patch center",
    }
    return {
        "schema": "pr399_vertical_neighbor_plan_v1",
        "status": "PREDECLARED_NO_NEIGHBOR_H_EXECUTED",
        "scope": "fixed 3x3 native saved frame 1 at 05:56:00; direct RTTOV H only; one existing center result reused and the eight neighbors evaluated serially once after review",
        "selection": {
            "frame_index": FRAME_INDEX, "time_label": TIME_LABEL,
            "native_j_range_inclusive": [85, 87], "native_i_range_inclusive": [47, 49],
            "AMI_candidate_row_col_zero_based": [320, 48],
            "observation_receipt_sha256": ctx["receipt_sha256"],
            "channels_1based": list(CHANNELS), "channel_names": list(CHANNEL_NAMES),
            "geometry": baseline_case["geometry"],
            "geometry_policy": "same fixed AMI candidate geometry for all nine native columns; no cell reassignment, best-neighbor search, parallax or footprint inference",
        },
        "inputs": {
            "native_v3_result_sha256": sha256(NATIVE_RESULT),
            "native_v3_npz_path": str(NATIVE_NPZ), "native_v3_npz_sha256": ctx["native_npz_sha256"],
            "pr395_intake_manifest_sha256": ctx["intake_manifest_sha256"],
            "pr395_intake_npz_sha256": ctx["intake_npz_sha256"],
            "pr398_v2_plan_sha256": ctx["v2_plan_sha256"],
            "pr398_v2_result_sha256": ctx["v2_result_sha256"],
            "observation_receipt_sha256": ctx["receipt_sha256"],
            "AMI_candidate_sha256": ctx["candidate_sha256"],
        },
        "central_reuse": center_reuse,
        "setup_attempt_history": {
            "prior_setup_attempt_count": 1,
            "prior_attempt_status": "FAILED_BEFORE_FIRST_H_CALL_NO_RETRY",
            "prior_attempt_failure_sha256": sha256(ATTEMPT1_FAILURE),
            "prior_attempt_H_calls": 0,
            "current_setup_attempt_number": 2,
        },
        "offline_fixture_preflight": {
            "path": str(OFFLINE_RECEIPT),
            "sha256": sha256(OFFLINE_RECEIPT),
            "status": "ALL_EIGHT_FIXTURES_PREPARED_NO_H",
            "H_calls": 0,
            "fixture_case_ids": [r["case_id"] for r in offline_fixtures],
        },
        "per_cell_input_hashes": profile_specs,
        "comparison_contract": {
            "fixed_frozen_support": objective["frozen_mask"].tolist(), "n_valid": 7,
            "observation_sigma_K": 1.0, "observation_bias_K": 0.0, "huber_delta_K": 1.0,
            "cost": "Jo=sum(mask*Huber((BT-target_BT-bias)/sigma)); retained only if every frozen channel rad_quality=0",
            "quality_policy": "never shrink support or cherry-pick; preserve every one of the nine predeclared columns and withhold Jo when any frozen-support channel fails",
            "H_options": {
                "ami_kma_bt": True, "dry_number": True, "ncmin_land": 10.0,
                "ncmin_sea": 10.0, "t_blend_octaves": 0.0, "q_blend_octaves": 0.0,
                "cloud": True, "gas_units": 2, "qv_convention": "mixing_ratio_kgkg_dry",
                "solar": False,
            },
            "surface_and_profile_policy": "per-cell TSK/T2/Q2/U10/V10/HGT/Xland/seaice; native 39-layer center pressure and T/Q/cloud, native 40 P8W interfaces, native rho_d, fixed frame-0 upper atmosphere O3/CO2 reference, original static skin and coefficient/executable",
        },
        "source_sha256": source_hashes,
        "rttov_assets": assets,
        "planned_rows": [{"j": m["j"], "i": m["i"], "lat_lon_deg": m["lat_lon_deg"],
                           "case_role": "reused_center" if (m["row"],m["col"]) == (1,1) else "one_direct_H",
                           "input_hashes": {k:v for k,v in m.items()
                                            if k not in ("row","col","j","i","lat_lon_deg",
                                                         "exact_state_forcing_pressure_rho_d_match_to_reused_center",
                                                         "exact_surface_match_to_reused_center",
                                                         "exact_pressure_gas_profile_match_to_reused_center")}}
                          for m in metadata],
        "execution": {
            "one_shot_required": True, "neighbor_H_calls_expected": 8,
            "center_H_reuse_no_new_call": True, "M_calls": 0,
            "optimizer_calls": 0, "native_runs": 0,
            "automatic_retry": False, "parallelism": 1,
            "source_driver_sha256": sha256(Path(__file__)),
        },
        "limits": [
            "This is direct H(native saved State, Forcing), not H(M(xb)); there is no KDM model step.",
            "The fixed AMI candidate viewing geometry is identical for all columns; row-to-row BT/cost differences therefore combine native State, pressure, density and surface changes under that geometry.",
            "No footprint overlap, pixel-level time match, parallax, or scientific matchup approval is claimed.",
            "No external model/reanalysis data, additional observation acquisition, native run, or optimization is used.",
        ],
    }


def write_plan() -> int:
    if PLAN.exists() or RESULT.exists() or OUT.exists() or CANONICAL_NPZ.exists():
        raise FileExistsError("PR399 output path already exists; refuse to overwrite or implicitly retry")
    PACKET.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=False, mode=0o700)
    PRIVATE.mkdir(mode=0o700)
    PRIVATE.chmod(0o700)
    PACKET.chmod(0o755)
    plan = _plan_payload()
    plan["created_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with PLAN.open("x") as stream:
        json.dump(plan, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    PLAN.chmod(0o644)
    print(json.dumps({"status": plan["status"], "plan": str(PLAN),
                      "plan_sha256": sha256(PLAN), "neighbor_H_calls": 8,
                      "center_reused": True, "H_executed": False}, indent=2))
    return 0


def _write_vector(path: Path, values) -> None:
    a = np.asarray(values, dtype=np.float64).reshape(-1)
    if not np.isfinite(a).all():
        raise ValueError(f"profile input is non-finite: {path}")
    path.write_text("".join(f"{value:.17E}\n" for value in a))


def _build_surface(analysis, native: dict[str, np.ndarray], row: int, col: int,
                   static_surface_skin: Path) -> dict:
    skin = analysis._read_scalar_fields(static_surface_skin, "k0")
    def get(field: str) -> float:
        return float(native[f"native_patch__surface__{field}"][FRAME_POSITION,row,col])
    skin["t"] = get("TSK")
    q2 = torch.as_tensor([get("Q2")], **F64)
    q2_ppmv = float(qv_to_q_ppmv_moist(q2, gas_units=2,
                                        qv_convention="mixing_ratio_kgkg_dry")[0])
    return {"skin": skin, "near_surface": {
        "t2m": get("T2"), "q2m": q2_ppmv, "wind_u10m": get("U10"),
        "wind_v10m": get("V10"), "wind_fetch": 0.0,
    }}


def _atomic_npz(path: Path, arrays: dict[str, np.ndarray]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    os.fchmod(fd, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            np.savez_compressed(stream, **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        digest = sha256(temp)
        os.link(temp, path)
        path.chmod(0o600)
        temp.unlink()
        return digest
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def _run_neighbor(case_meta: dict, profile: tuple, offline_fixture: dict,
                  analysis, native: dict[str, np.ndarray],
                  fixed_geometry: dict, target: np.ndarray, dqf: np.ndarray, mask: np.ndarray,
                  run_root: Path, source_info: dict) -> dict:
    row, col, j, i = case_meta["row"], case_meta["col"], case_meta["j"], case_meta["i"]
    case_id = f"frame1_j{j}_i{i}_fixed_AMI_geometry"
    p_lay, p_half, t_profile, q_profile, o3, co2 = profile
    state = analysis.State(*(torch.as_tensor(
        native[f"native_patch__state__{field}"][FRAME_POSITION,row,col][None,:], **F64)
        for field in STATE_FIELDS))
    forcing_values = {
        "rho": native["native_patch__rho"][FRAME_POSITION,row,col],
        "pii": native["native_patch__pii"][FRAME_POSITION,row,col],
        "p": native["native_patch__p_pa"][FRAME_POSITION,row,col],
        "delz": native["native_patch__delz"][FRAME_POSITION,row,col],
    }
    forcing = analysis.Forcing(**{name: torch.as_tensor(values[None,:], **F64)
                                  for name, values in forcing_values.items()})
    rho_d = forcing.rho / (1.0 + state.qv)
    if not np.array_equal(rho_d.detach().cpu().numpy()[0],
                          native["native_patch__rho_d"][FRAME_POSITION,row,col]):
        raise ValueError(f"converted optical dry density changed at j={j}, i={i}")
    xland = float(native["native_patch__surface__xland"][FRAME_POSITION,row,col])
    seaice = float(native["native_patch__surface__seaice"][FRAME_POSITION,row,col])
    if xland != 2.0 or seaice != 0.0:
        raise ValueError(f"fixed 3x3 patch includes non-open-ocean column at j={j}, i={i}")
    surface = _build_surface(analysis, native, row, col,
                             Path(source_info["static_surface_skin"]["path"]))
    fixture = Path(offline_fixture["fixture_path"])
    fixture_info = offline_fixture["fixture_info"]
    atm = fixture / "in/profiles/001/atm"
    profile_file_names = ("p.txt", "p_half.txt", "t.txt", "q.txt", "o3.txt", "co2.txt")
    fixture_file_hashes = {name: sha256(atm / name) for name in profile_file_names}
    if fixture_file_hashes != offline_fixture["fixture_file_sha256"]:
        raise ValueError(f"offline prepared fixture changed before H at j={j}, i={i}")
    input_cfg = analysis.RttovInputConfig(
        "paired-case_00-GK2A-AMI", CHANNELS, surface=surface, geometry=fixed_geometry)
    profile_cfg = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=torch.as_tensor(p_lay, **F64),
        rttov_level_pressure=torch.as_tensor(p_half, **F64), cloud=True,
        rho_d=rho_d, dry_number=True)
    case_dir = run_root / f"hcase-{case_id}"
    run_k = analysis.make_live_run_k(
        case_dir, fixture_case_dir=fixture,
        timeout=analysis.DEFAULT_RTTOV_TIMEOUT, ami_kma_bt=True)
    obs_cfg = OsseObsConfig(
        run_k=run_k, profile_cfg=profile_cfg, input_cfg=input_cfg,
        obs_sigma=1.0, t_ref=torch.as_tensor(t_profile, **F64),
        q_ref=torch.as_tensor(q_profile, **F64), t_blend_octaves=0.0, q_blend_octaves=0.0)
    with torch.no_grad():
        bt, rad_quality, _ = batched_allsky_bt(
            state, forcing, obs_cfg, xland=torch.as_tensor([xland], **F64),
            ncmin_land=10.0, ncmin_sea=10.0)
    bt_np = bt.detach().cpu().numpy()
    quality_np = rad_quality.detach().cpu().numpy().astype(np.float64)
    quality_ok = bool(np.array_equal(quality_np, np.zeros((1, 7), dtype=np.float64)))
    jo = None
    if quality_ok:
        from kdm6.obs.obs_loss import compute_obs_loss
        jo = float(compute_obs_loss(torch.as_tensor(bt_np, **F64),
                                    {"bt": torch.as_tensor(target, **F64), "bias": 0.0},
                                    torch.as_tensor(mask, **F64), 1.0, delta=1.0))
    native_p8w = native["native_patch__p_half_calc_p8w_bottomup_Pa"][FRAME_POSITION,row,col]
    return {
        "case_id": case_id, "j": j, "i": i,
        "lat_lon_deg": case_meta["lat_lon_deg"], "native_time_label": TIME_LABEL,
        "status": "H_RETURNED" if quality_ok else "H_RETURNED_QUALITY_GATE_FAILED",
        "operator_semantics": "direct H(native saved frame 1 State, Forcing); no M, interpolation, or backward",
        "geometry": fixed_geometry, "channels_1based": list(CHANNELS),
        "channel_names": list(CHANNEL_NAMES), "BT_K": bt_np.tolist(),
        "rad_quality": quality_np.tolist(), "fixed_observation_quality_DQF": dqf.tolist(),
        "frozen_support": mask.tolist(), "frozen_support_n_valid": int(np.count_nonzero(mask)),
        "all_seven_rad_quality_zero": quality_ok, "Jo_huber_K_units": jo,
        "state_sha256_by_field": case_meta["state_sha256_by_field"],
        "forcing_sha256_by_field": case_meta["forcing_sha256_by_field"],
        "rho_d_sha256": case_meta["rho_d_sha256"], "p8w_sha256": array_sha256(native_p8w),
        "surface_sha256_by_field": case_meta["surface_sha256_by_field"],
        "rttov_profile_sha256": case_meta["rttov_profile_sha256"],
        "rttov_assets": {
            "source_asset_sha256": source_info,
            "prepared_fixture_info": fixture_info,
            "per_cell_pressure_gases_sha256": {
                name: sha256(atm / name) for name in ("p.txt", "p_half.txt", "o3.txt", "co2.txt")
            },
        },
        "case_output_dir": str(case_dir), "automatic_retry": False,
    }


def _make_private_arrays(ctx: dict, metadata: list[dict], profiles: list[tuple],
                         results: list[dict]) -> dict[str, np.ndarray]:
    native = ctx["native"]
    state = np.stack([[native[f"native_patch__state__{field}"][FRAME_POSITION,m["row"],m["col"]]
                       for field in STATE_FIELDS] for m in metadata])
    forcing_map = {"rho":"rho", "pii":"pii", "p":"p_pa", "delz":"delz"}
    forcing = np.stack([[native[f"native_patch__{key}"][FRAME_POSITION,m["row"],m["col"]]
                         for key in forcing_map.values()] for m in metadata])
    surface = np.stack([[float(native[f"native_patch__surface__{field}"][FRAME_POSITION,m["row"],m["col"]])
                         for field in SURFACE_FIELDS] for m in metadata])
    bt = np.asarray([r["BT_K"][0] for r in results], dtype=np.float64)
    quality = np.asarray([r["rad_quality"][0] for r in results], dtype=np.float64)
    cost = np.asarray([np.nan if r["Jo_huber_K_units"] is None else r["Jo_huber_K_units"]
                       for r in results], dtype=np.float64)
    return {
        "j_i_0based": np.asarray([[m["j"],m["i"]] for m in metadata],dtype=np.int32),
        "latitude_longitude_deg": np.asarray([m["lat_lon_deg"] for m in metadata],dtype=np.float64),
        "state_fields": np.asarray(STATE_FIELDS,dtype="U8"),
        "state_native_bottomup": state,
        "forcing_fields": np.asarray(list(forcing_map),dtype="U8"),
        "forcing_native_bottomup": forcing,
        "rho_d_native_bottomup_kg_m3": np.stack([
            native["native_patch__rho_d"][FRAME_POSITION,m["row"],m["col"]] for m in metadata]),
        "p_half_native_bottomup_Pa_real4": np.stack([
            native["native_patch__p_half_calc_p8w_bottomup_Pa"][FRAME_POSITION,m["row"],m["col"]]
            for m in metadata]),
        "surface_fields": np.asarray(SURFACE_FIELDS,dtype="U16"),
        "surface_values": surface,
        "profile_fields": np.asarray(("p_lay_hPa","p_half_hPa","t_native_plus_reference_K",
                                      "q_native_plus_reference_ppmv","o3_ppmv","co2_ppmv"),dtype="U40"),
        "profile_p_lay_hPa": np.stack([p[0] for p in profiles]),
        "profile_p_half_hPa": np.stack([p[1] for p in profiles]),
        "profile_t_K": np.stack([p[2] for p in profiles]),
        "profile_q_ppmv": np.stack([p[3] for p in profiles]),
        "profile_o3_ppmv": np.stack([p[4] for p in profiles]),
        "profile_co2_ppmv": np.stack([p[5] for p in profiles]),
        "observation_target_BT_K": np.asarray(ctx["receipt"]["ami_candidate_result"]["bt_K"][2:9],dtype=np.float64),
        "observation_dqf": np.asarray(ctx["receipt"]["ami_candidate_result"]["dqf"][2:9],dtype=np.float64),
        "frozen_support": np.asarray(results[0]["frozen_support"],dtype=np.float64),
        "BT_K": bt, "rad_quality": quality, "Jo_huber_K_units": cost,
    }


def _write_report(payload: dict, result_sha: str, npz_sha: str) -> None:
    rows = payload["results"]
    center = next(r for r in rows if (r["j"],r["i"]) == (86,48))
    lines = [
        "# PR399 fixed native 3x3 direct-H comparison",
        "",
        "This is a single direct RTTOV H batch on the nine already-saved native columns at frame index 1 (2025-07-19 05:56:00), with the same fixed AMI candidate geometry, seven channels, baseline quality mask, and observation cost for every row. The center result is reused from the hash-bound PR398 V2 execution because its complete saved input/profile/asset bindings match; only the eight neighboring columns required new H calls.",
        "",
        f"Result status: `{payload['status']}`; result SHA256 `{result_sha}`; private NPZ SHA256 `{npz_sha}`.",
        f"Center `(j=86,i=48)` reused with `Jo={center['Jo_huber_K_units']:.12g}` and all-seven rad_quality zero.",
        "",
        "| j | i | latitude | longitude | all 7 quality zero | Jo (Huber K units) | max |ΔBT| from center (K) |",
        "|---:|---:|---:|---:|:---:|---:|---:|",
    ]
    center_bt = np.asarray(center["BT_K"],dtype=np.float64)[0]
    for row in rows:
        bt = np.asarray(row["BT_K"],dtype=np.float64)[0]
        max_delta = float(np.max(np.abs(bt-center_bt)))
        jo = "withheld" if row["Jo_huber_K_units"] is None else f"{row['Jo_huber_K_units']:.12g}"
        lines.append(f"| {row['j']} | {row['i']} | {row['lat_lon_deg'][0]:.7f} | {row['lat_lon_deg'][1]:.7f} | {row['all_seven_rad_quality_zero']} | {jo} | {max_delta:.7g} |")
    lines.extend([
        "",
        "The full seven-channel BT vectors, per-channel `rad_quality`, state/forcing/density/pressure/surface/profile hashes, fixture asset hashes, and exact input arrays are preserved in the result JSON and private NPZ. If any row fails the fixed all-seven quality gate, its cost is withheld while the row and support remain present.",
        "",
        "This comparison isolates each native column only under the fixed AMI geometry; BT and cost differences can reflect native State, pressure, density, and surface differences. It is not H(M(xb)), a footprint or parallax calculation, pixel-time validation, or science acceptance. The experiment made no M, optimizer, or native-model calls and had no retry path.",
        "",
    ])
    REPORT.write_text("\n".join(lines))
    REPORT.chmod(0o644)
    with TABLE.open("x", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("j","i","latitude_deg","longitude_deg","all_seven_rad_quality_zero","Jo_huber_K_units","BT_K_channels_10_16","delta_BT_from_center_K_channels_10_16","case_role"))
        for row in rows:
            bt=np.asarray(row["BT_K"],dtype=np.float64)[0]
            delta=bt-center_bt
            role="reused_existing_center_H" if (row["j"],row["i"])==(86,48) else "one_new_direct_H"
            writer.writerow((row["j"],row["i"],*row["lat_lon_deg"],row["all_seven_rad_quality_zero"],
                             row["Jo_huber_K_units"],json.dumps(bt.tolist()),json.dumps(delta.tolist()),role))
    TABLE.chmod(0o644)


def execute_one_shot() -> int:
    if (not PLAN.is_file() or STARTED.exists() or RESULT.exists() or FAILURE.exists()
            or CANONICAL_NPZ.exists() or TABLE.exists() or REPORT.exists()):
        raise FileExistsError("one-shot PR399 execution requires a clean output namespace and immutable preflight")
    stored = json.loads(PLAN.read_text())
    stored.pop("created_utc", None)
    current = _plan_payload()
    if stored != current:
        raise ValueError("predeclared PR399 inputs, sources, central binding, or RT assets changed before H")
    plan_sha = sha256(PLAN)
    PRIVATE.chmod(0o700)
    with STARTED.open("x") as stream:
        json.dump({"status":"STARTED_ONCE","plan_sha256":plan_sha,
                   "source_driver_sha256":sha256(Path(__file__)),"expected_new_H_calls":8},stream)
        stream.write("\n")
    STARTED.chmod(0o600)
    ctx=_load_inputs()
    analysis=load_module(ANALYSIS_DRIVER,"pr399_execute_analysis")
    reader=load_module(NATIVE_READER,"pr399_execute_reader")
    baseline_case, baseline_plan_case, assets, objective, metadata = _baseline_context(ctx,analysis,reader)
    profiles=objective["profiles"]
    offline_fixtures=_offline_fixture_preflight(metadata,profiles,analysis,assets)
    fixture_by_case={record["case_id"]:record for record in offline_fixtures}
    centerrow=dict(baseline_case)
    centerrow.update({"j":86,"i":48,"lat_lon_deg":metadata[4]["lat_lon_deg"],
                      "case_role":"REUSED_PR398_V2_CENTRAL_H","automatic_retry":False})
    # The original center output already contains the direct H result. Keep its
    # source case directory and result provenance intact; do not replay H.
    results=[]
    run_root=PRIVATE/"cases"
    run_root.mkdir(mode=0o700)
    target=objective["target_bt_K"]
    dqf=objective["dqf"]
    mask=objective["frozen_mask"]
    try:
        for case_meta,profile in zip(metadata,profiles):
            if (case_meta["row"],case_meta["col"])==(1,1):
                results.append(centerrow)
            else:
                case_id=f"frame1_j{case_meta['j']}_i{case_meta['i']}_fixed_AMI_geometry"
                results.append(_run_neighbor(case_meta,profile,fixture_by_case[case_id],analysis,ctx["native"],
                                             baseline_case["geometry"],target,dqf,mask,run_root,assets))
        results.sort(key=lambda row:(row["j"],row["i"]))
        if len(results)!=9 or {(r["j"],r["i"]) for r in results}!={(j,i) for j in range(85,88) for i in range(47,50)}:
            raise ValueError("completed result does not include exactly the fixed predeclared nine columns")
        status="ALL_NINE_ROWS_RETURNED" if all(r["status"] in ("H_RETURNED","H_RETURNED_QUALITY_GATE_FAILED") for r in results) else "INCOMPLETE_NO_RETRY"
        result_payload={
            "schema":"pr399_vertical_neighbor_result_v1","status":status,
            "plan_path":str(PLAN),"plan_sha256":plan_sha,"source_driver_sha256":sha256(Path(__file__)),
            "native_npz_sha256":ctx["native_npz_sha256"],"intake_manifest_sha256":ctx["intake_manifest_sha256"],
            "intake_npz_sha256":ctx["intake_npz_sha256"],"pr398_v2_result_sha256":ctx["v2_result_sha256"],
            "center_h_reused":True,"center_new_h_calls":0,"neighbor_h_calls":8,
            "m_calls":0,"optimizer_calls":0,"native_runs":0,"automatic_retry":False,
            "fixed_observation":{"BT_K":target.tolist(),"DQF":dqf.tolist(),
                                 "frozen_support":mask.tolist(),"sigma_K":1.0,"bias_K":0.0,"huber_delta_K":1.0},
            "results":results,
            "scientific_acceptance":"NOT_ASSESSED",
        }
        arrays=_make_private_arrays(ctx,metadata,profiles,results)
        npz_sha=_atomic_npz(CANONICAL_NPZ,arrays)
        result_payload["private_npz"]={"path":str(CANONICAL_NPZ),"sha256":npz_sha,
                                       "mode_octal":"0600","directory_mode_octal":"0700",
                                       "array_names":sorted(arrays)}
        with RESULT.open("x") as stream:
            json.dump(result_payload,stream,indent=2,sort_keys=True,allow_nan=False)
            stream.write("\n")
        RESULT.chmod(0o644)
        _write_report(result_payload,sha256(RESULT),npz_sha)
        print(json.dumps({"status":status,"result":str(RESULT),"private_npz":str(CANONICAL_NPZ),
                          "new_H_calls":8,"M_calls":0},indent=2))
        return 0
    except BaseException as exc:
        failure={"schema":"pr399_vertical_neighbor_failure_v1","status":"FAILED_NO_RETRY",
                 "plan_sha256":plan_sha,"error_type":type(exc).__name__,"error":str(exc),
                 "completed_rows":results,"m_calls":0,"optimizer_calls":0,
                 "automatic_retry":False}
        with FAILURE.open("x") as stream:
            json.dump(failure,stream,indent=2,sort_keys=True,allow_nan=False)
            stream.write("\n")
        FAILURE.chmod(0o600)
        raise


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--plan-only",action="store_true",help="write the preflight plan without running RTTOV H")
    mode.add_argument("--execute-one-shot",action="store_true",help="run the authorized eight-neighbor direct-H batch once")
    args=parser.parse_args()
    return execute_one_shot() if args.execute_one_shot else write_plan()


if __name__=="__main__":
    raise SystemExit(main())
