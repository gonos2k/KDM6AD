#!/usr/bin/env python3
"""Future corrected vertical diagnostic source; NOT executed.

Derive bounded vertical diagnostics from the immutable PR398 selected patch NPZ.

No native forecast, M/H, optimizer, or observation operator is opened or called.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))
PACKET = ROOT / "harness/evidence/pr399_vertical_neighbor_2026-10-10"
OUT = ROOT / "graphify-out/pr399-vertical-neighbor-v3-2026-10-10"
PRIVATE = OUT / "private"
CANONICAL = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr399_vertical_neighbor_20261010_v3")
SOURCES = CANONICAL / "sources"
INPUT_NPZ = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr398_sensitivity_20261010/native_patch_3x3_frames_1_4_6_v3.npz")
INPUT_RESULT = ROOT / "harness/evidence/pr398_spatial_representativeness_2026-10-10/NATIVE_PATCH_RESULT_v3.json"
INPUT_PLAN = ROOT / "harness/evidence/pr398_spatial_representativeness_2026-10-10/NATIVE_PATCH_v3.json"
READER = ROOT / "harness/evidence/native358_artifact_diag_2026-10-08/recipe/run_native_kma_bt_frames.py"
THERMO = ROOT / "oracle/kdm6/thermo.py"
CONSTANTS = ROOT / "oracle/kdm6/constants.py"
PLAN_PATH = PACKET / "VERTICAL_PLAN_v3.json"
RESULT_PATH = PACKET / "VERTICAL_RESULT_v3.json"
CSV_PATH = PACKET / "VERTICAL_RESULT_v3.csv"
CONTEXT_CSV = PACKET / "VERTICAL_MAXSAT_CONTEXT_v3.csv"
REPORT_PATH = PACKET / "VERTICAL_REPORT_v3.md"
DERIVED_NPZ = PRIVATE / "vertical_structure_27columns_3times_v3.npz"
CANONICAL_NPZ = CANONICAL / DERIVED_NPZ.name
STARTED = PRIVATE / "STARTED_ONCE_v3.json"
FAILED = PRIVATE / "FAILED_v3.json"
FRAME_LABELS = ("2025-07-19_05:56:00", "2025-07-19_05:57:00", "2025-07-19_05:57:40")
FRAME_INDICES = (1, 4, 6)
LOWER_LEVELS = 12
MAXSAT_TARGET_LEVEL = 3
R_D = 287.0
R_V = 461.6
EPS = R_D / R_V
G = 9.81


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def arr_sha(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def _source_map() -> dict:
    paths = {
        "vertical_structure_driver": Path(__file__).resolve(),
        "native_patch_npz": INPUT_NPZ,
        "native_patch_result": INPUT_RESULT,
        "native_patch_plan": INPUT_PLAN,
        "selected_frame_reader": READER,
        "kdm6_thermo": THERMO,
        "kdm6_constants": CONSTANTS,
    }
    missing = [str(p) for p in paths.values() if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"required pinned inputs/sources are missing: {missing}")
    return {k: {"path": str(v), "sha256": sha256(v)} for k, v in paths.items()}


def _check_input_binding() -> tuple[dict, dict]:
    receipt = json.loads(INPUT_RESULT.read_text())
    plan = json.loads(INPUT_PLAN.read_text())
    expected = "947c72c12ebe289b7ddc84fba1281635d77ffbcfe23f204345cc97abeebc1c21"
    if receipt.get("status") != "READY_NATIVE_PATCH_DIAGNOSTIC_ONLY":
        raise ValueError("PR398 native patch is not the accepted bounded diagnostic result")
    if receipt.get("private_npz", {}).get("sha256") != expected or sha256(INPUT_NPZ) != expected:
        raise ValueError("canonical PR398 source NPZ SHA does not match the frozen input")
    if receipt.get("canonical_npz", {}).get("sha256") != expected:
        raise ValueError("PR398 canonical NPZ binding differs from the frozen input")
    if receipt.get("M_calls") != 0 or receipt.get("H_calls") != 0 or receipt.get("optimizer_calls") != 0:
        raise ValueError("input receipt has unexpected model/operator/optimizer execution")
    if receipt.get("selection", {}).get("frame_indices") != list(FRAME_INDICES):
        raise ValueError("PR398 frame indices differ from vertical diagnostic scope")
    if receipt.get("selection", {}).get("times") != list(FRAME_LABELS):
        raise ValueError("PR398 selected times differ from vertical diagnostic scope")
    if plan.get("native_patch_driver_sha256") != receipt.get("native_patch_driver_sha256"):
        raise ValueError("source patch driver hash does not match the accepted plan/result")
    return receipt, plan


def plan_payload() -> dict:
    receipt, plan = _check_input_binding()
    return {
        "schema": "pr399_vertical_structure_plan_v3",
        "status": "PREDECLARED_DERIVATION_NO_MODEL_OR_OPERATOR",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": "read immutable PR398 NPZ only; no forecast re-read, new model run, M/H, optimizer, or regridding",
        "input_npz": {"path": str(INPUT_NPZ), "sha256": sha256(INPUT_NPZ)},
        "input_result": {"path": str(INPUT_RESULT.relative_to(ROOT)), "sha256": sha256(INPUT_RESULT)},
        "input_plan": {"path": str(INPUT_PLAN.relative_to(ROOT)), "sha256": sha256(INPUT_PLAN)},
        "input_selection": {"frames": list(FRAME_INDICES), "times": list(FRAME_LABELS),
                            "j": [85, 86, 87], "i": [47, 48, 49], "levels": 39},
        "diagnostics": {
            "detailed_levels_bottom_up_zero_based": list(range(LOWER_LEVELS)),
            "maxsat_target_level_bottom_up_zero_based": MAXSAT_TARGET_LEVEL,
            "maxsat_definition": "qv / KDM6 phase-aware qs_ice at all native levels; report actual model midheight AGL and native center pressure for maximum and adjacent levels",
            "liquid_saturation": "KDM6 compute_qs_water(T,p) at native center levels; no vertical remapping",
            "virtual_potential_temperature": "theta_v = theta_d*(1+qv/epsilon)/(1+qv) = (THM+300)/(1+qv), epsilon=Rd/Rv; independently verify both expressions",
            "height": "native interface geopotential z=(PH+PHB)/g using float64-first arrays; layer midheight is adjacent-interface mean; AGL subtracts saved HGT; preserve nonuniform actual center-height differences",
            "pressure": "native float64-first P+PB centers; P8W REAL(4) Python transcription remains separately labeled and only brackets native layers",
            "local_saturation_change": "S=100*qv/qs_water at bottom-up maxsat layer; for endpoint pairs 1→4, 4→6, and 1→6, first-order local partial contributions in qv,T,p at the start endpoint plus exact nonlinear remainder; no division by elapsed time and no process-rate attribution",
            "stability": "report adjacent-level dT/dz and dtheta_v/dz over lower 12 levels; positive dT/dz flags a temperature inversion layer and positive dtheta_v/dz is stable-sign stratification, neither attributes a cause",
        },
        "source_sha256": _source_map(),
        "outputs": {"result": str(RESULT_PATH.relative_to(ROOT)), "profiles_csv": str(CSV_PATH.relative_to(ROOT)),
                    "maxsat_context_csv": str(CONTEXT_CSV.relative_to(ROOT)), "report": str(REPORT_PATH.relative_to(ROOT)),
                    "private_npz": str(DERIVED_NPZ), "canonical_private_npz": str(CANONICAL_NPZ)},
        "limits": ["No arbitrary-height regrid", "No model or RTTOV execution", "Not a process-tendency or cause attribution",
                   "Saturation partial decomposition applies only to native warm, unclipped layer-3 endpoints; clipped/unstable endpoints are excluded and recorded"],
        "input_run_id": receipt.get("native_run_id"),
        "native_source_times_full_hash": plan.get("native_intake", {}).get("forecast_sha256"),
    }


def write_plan() -> None:
    if PLAN_PATH.exists() or OUT.exists() or CANONICAL.exists():
        raise FileExistsError("vertical analysis output path already exists; refusing overwrite")
    payload = plan_payload()
    OUT.mkdir(mode=0o700, parents=True)
    OUT.chmod(0o700)
    PRIVATE.mkdir(mode=0o700)
    PRIVATE.chmod(0o700)
    CANONICAL.mkdir(mode=0o700, parents=True)
    CANONICAL.chmod(0o700)
    SOURCES.mkdir(mode=0o700)
    SOURCES.chmod(0o700)
    payload["driver_sha256"] = sha256(Path(__file__))
    with PLAN_PATH.open("x") as f:
        json.dump(payload, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    PLAN_PATH.chmod(0o644)
    print(json.dumps({"status": payload["status"], "plan_sha256": sha256(PLAN_PATH),
                      "input_sha256": payload["input_npz"]["sha256"], "NPZ_written": False}, indent=2))


def _read_input() -> tuple[dict[str, np.ndarray], dict, dict]:
    receipt, plan = _check_input_binding()
    arrays = {}
    with np.load(INPUT_NPZ, allow_pickle=False) as z:
        for key in z.files:
            arrays[key] = z[key].copy()
    if len(arrays) != receipt["private_npz"]["array_count"]:
        raise ValueError("canonical NPZ array count differs from PR398 receipt")
    if arrays["frame_indices"].tolist() != list(FRAME_INDICES):
        raise ValueError("canonical NPZ frame indices changed")
    for k, spec in receipt["private_npz"]["arrays"].items():
        a = arrays[k]
        if list(a.shape) != spec["shape"] or str(a.dtype) != spec["dtype"] or arr_sha(a) != spec["sha256"]:
            raise ValueError(f"PR398 input array binding failed for {k}")
        if a.dtype.kind == "f" and not np.isfinite(a).all():
            raise ValueError(f"non-finite value in bound input {k}")
    return arrays, receipt, plan


def _derive(arrays: dict[str, np.ndarray]) -> tuple[dict[str, np.ndarray], list[dict], list[dict], dict]:
    from kdm6.thermo import compute_qs_ice, compute_qs_water, default_thermo_params

    qv = arrays["native_patch__state__qv"].astype(np.float64)
    theta_d = arrays["native_patch__state__th"].astype(np.float64)
    p = arrays["native_patch__p_centers_native_bottomup_Pa"].astype(np.float64)
    temp = arrays["native_patch__temperature_K"].astype(np.float64)
    thm = arrays["native_patch__thm_moist_potential_K"].astype(np.float64)
    raw_ph = arrays["native_patch__wrf_raw__PH"].astype(np.float64)
    raw_phb = arrays["native_patch__wrf_raw__PHB"].astype(np.float64)
    raw_p = arrays["native_patch__wrf_raw__P"].astype(np.float64)
    raw_pb = arrays["native_patch__wrf_raw__PB"].astype(np.float64)
    raw_thm = arrays["native_patch__wrf_raw__THM"].astype(np.float64)
    pii = arrays["native_patch__pii"].astype(np.float64)
    hgt = arrays["native_patch__surface__HGT"].astype(np.float64)
    p8w = arrays["native_patch__p_half_calc_p8w_bottomup_Pa"].astype(np.float64)
    if qv.shape != (3, 3, 3, 39) or raw_ph.shape != (3, 3, 3, 40):
        raise ValueError("bound NPZ profile shape differs from fixed 27 native columns")
    if not np.array_equal(p, raw_p + raw_pb):
        raise ValueError("stored native center pressure is not float64-first P+PB")
    if not np.array_equal(temp, theta_d * pii):
        raise ValueError("stored physical temperature differs from dry theta times Exner")
    if not np.array_equal(thm, raw_thm + 300.0):
        raise ValueError("stored moist potential temperature differs from raw THM plus 300 K")
    if not np.all(p8w[..., :-1] > p8w[..., 1:]):
        raise ValueError("stored REAL(4) P8W interfaces are not bottom-up decreasing")

    z_interface = (raw_ph + raw_phb) / G
    z_mid_asl = 0.5 * (z_interface[..., :-1] + z_interface[..., 1:])
    z_mid_agl = z_mid_asl - hgt[..., None]
    dz_center = np.diff(z_mid_agl, axis=-1)
    dz_layer = np.diff(z_interface, axis=-1)
    if (not np.isfinite(z_mid_agl).all() or not np.isfinite(dz_center).all()
            or np.any(dz_center <= 0.0) or np.any(dz_layer <= 0.0)):
        raise ValueError("native interface geometry is not finite/strictly bottom-up")

    theta_v_a = theta_d * (1.0 + qv / EPS) / (1.0 + qv)
    theta_v_b = thm / (1.0 + qv)
    if not np.allclose(theta_v_a, theta_v_b, rtol=3e-15, atol=3e-12):
        raise ValueError("equivalent virtual potential temperature formulas differ")
    theta_v = theta_v_a
    prm = default_thermo_params()
    t_t = torch.as_tensor(temp, dtype=torch.float64)
    p_t = torch.as_tensor(p, dtype=torch.float64)
    qsw = compute_qs_water(t_t, p_t, params=prm).detach().cpu().numpy()
    qsi = compute_qs_ice(t_t, p_t, params=prm).detach().cpu().numpy()
    s_water_pct = 100.0 * qv / qsw
    maxsat = qv / np.maximum(qsi, prm.qmin)
    maxsat_level = np.argmax(maxsat, axis=-1).astype(np.int16)

    t_safe = np.maximum(temp, 1.0)
    tr = prm.ttp / t_safe
    es_raw = prm.psat * np.exp(np.log(tr) * prm.xa) * np.exp(prm.xb * (1.0 - tr))
    es_clip = es_raw >= 0.99 * p
    denom_clip = (p - np.minimum(es_raw, 0.99 * p)) <= prm.qmin
    qs_raw_after_es = prm.ep2 * np.minimum(es_raw, 0.99 * p) / np.maximum(
        p - np.minimum(es_raw, 0.99 * p), prm.qmin)
    qmin_clip = qs_raw_after_es <= prm.qmin
    t_clip = temp <= 1.0
    clip_any = es_clip | denom_clip | qmin_clip | t_clip

    derived = {
        "frame_indices": arrays["frame_indices"].copy(),
        "j_indices": arrays["j_indices"].copy(),
        "i_indices": arrays["i_indices"].copy(),
        "z_interface_m_asl": z_interface,
        "z_mid_m_agl": z_mid_agl,
        "midheight_spacing_up_m": dz_center,
        "layer_thickness_m": dz_layer,
        "p_center_native_Pa": p,
        "p8w_half_bottomup_REAL4_transcription_Pa": arrays["native_patch__p_half_calc_p8w_bottomup_Pa"].copy(),
        "temperature_K": temp,
        "qv_kgkg_dry": qv,
        "qs_water_kgkg": qsw,
        "qs_phase_aware_kgkg": qsi,
        "S_liquid_percent": s_water_pct,
        "qv_over_qs_phase_aware": maxsat,
        "maxsat_level_bottomup_zero_based": maxsat_level,
        "theta_d_K": theta_d,
        "theta_v_K": theta_v,
        "saturation_clip_any": clip_any,
        "saturation_es_clip": es_clip,
        "saturation_qmin_clip": qmin_clip,
    }

    profiles: list[dict] = []
    context: list[dict] = []
    frames = arrays["frame_indices"].tolist()
    labels = [x.decode("ascii") for x in arrays["time_labels_ascii"].tolist()]
    js, is_ = arrays["j_indices"].tolist(), arrays["i_indices"].tolist()
    max_layer_unique = set(int(x) for x in maxsat_level.ravel())
    if max_layer_unique != {MAXSAT_TARGET_LEVEL}:
        raise ValueError(f"maxsat layer differs from predeclared layer 3: {sorted(max_layer_unique)}")
    for tix, (frame, label) in enumerate(zip(frames, labels)):
        for y, j in enumerate(js):
            for x, i in enumerate(is_):
                c = {
                    "frame_index": int(frame), "time": label, "j": int(j), "i": int(i),
                    "latitude_deg": float(arrays["native_patch__surface__latitude_deg"][tix, y, x]),
                    "longitude_deg": float(arrays["native_patch__surface__longitude_deg"][tix, y, x]),
                    "HGT_m": float(hgt[tix, y, x]),
                }
                for k in range(LOWER_LEVELS):
                    up_spacing = float(dz_center[tix, y, x, k]) if k < LOWER_LEVELS - 1 else None
                    dz_below = float(dz_center[tix, y, x, k - 1]) if k > 0 else None
                    dtemp = float(temp[tix, y, x, k] - temp[tix, y, x, k - 1]) if k > 0 else None
                    dthetav = float(theta_v[tix, y, x, k] - theta_v[tix, y, x, k - 1]) if k > 0 else None
                    dz_for_grad = dz_below
                    profiles.append({
                        **c, "k_bottom_up": k,
                        "z_mid_AGL_m": float(z_mid_agl[tix, y, x, k]),
                        "midheight_spacing_to_next_level_m": up_spacing,
                        "layer_thickness_m": float(dz_layer[tix, y, x, k]),
                        "p_center_hPa": float(p[tix, y, x, k] / 100.0),
                        "p8w_bottom_interface_hPa": float(p8w[tix, y, x, k] / 100.0),
                        "p8w_top_interface_hPa": float(p8w[tix, y, x, k + 1] / 100.0),
                        "temperature_K": float(temp[tix, y, x, k]),
                        "qv_kgkg_dry": float(qv[tix, y, x, k]),
                        "qs_water_kgkg": float(qsw[tix, y, x, k]),
                        "S_liquid_percent": float(s_water_pct[tix, y, x, k]),
                        "qv_over_qs_phase_aware_percent": float(maxsat[tix, y, x, k] * 100.0),
                        "theta_d_K": float(theta_d[tix, y, x, k]),
                        "theta_v_K": float(theta_v[tix, y, x, k]),
                        "dT_vs_below_K": dtemp,
                        "dtheta_v_vs_below_K": dthetav,
                        "dT_dz_vs_below_K_per_km": (float(dtemp / dz_for_grad * 1000.0)
                                                     if dz_for_grad is not None else None),
                        "dtheta_v_dz_vs_below_K_per_km": (float(dthetav / dz_for_grad * 1000.0)
                                                           if dz_for_grad is not None else None),
                        "temperature_inversion_upward_flag": (bool(dtemp > 0.0) if dtemp is not None else None),
                        "stable_sign_theta_v_gradient_flag": (bool(dthetav > 0.0) if dthetav is not None else None),
                        "water_saturation_clipped": bool(clip_any[tix, y, x, k]),
                        "water_es_clip": bool(es_clip[tix, y, x, k]),
                        "water_qmin_clip": bool(qmin_clip[tix, y, x, k]),
                    })
                kmax = int(maxsat_level[tix, y, x])
                row = {**c, "maxsat_layer_bottom_up_zero_based": kmax,
                       "maxsat_phase_aware_percent": float(maxsat[tix, y, x, kmax] * 100.0),
                       "liquid_S_percent_at_maxsat_layer": float(s_water_pct[tix, y, x, kmax]),
                       "layer_context_note": "native maxsat layer and immediate bottom/above native layers; no remap"}
                for suffix, kk in (("below", kmax - 1), ("maxsat", kmax), ("above", kmax + 1)):
                    if not (0 <= kk < 39):
                        row[f"{suffix}_layer"] = None
                        continue
                    row[f"{suffix}_layer"] = kk
                    row[f"{suffix}_z_mid_AGL_m"] = float(z_mid_agl[tix, y, x, kk])
                    row[f"{suffix}_p_center_hPa"] = float(p[tix, y, x, kk] / 100.0)
                    row[f"{suffix}_p8w_bottom_hPa"] = float(p8w[tix, y, x, kk] / 100.0)
                    row[f"{suffix}_p8w_top_hPa"] = float(p8w[tix, y, x, kk + 1] / 100.0)
                    row[f"{suffix}_T_K"] = float(temp[tix, y, x, kk])
                    row[f"{suffix}_qv_kgkg"] = float(qv[tix, y, x, kk])
                    row[f"{suffix}_qs_water_kgkg"] = float(qsw[tix, y, x, kk])
                    row[f"{suffix}_theta_v_K"] = float(theta_v[tix, y, x, kk])
                    row[f"{suffix}_phase_sat_percent"] = float(maxsat[tix, y, x, kk] * 100.0)
                context.append(row)

    endpoint_rows: list[dict] = []
    pairs = ((0, 1), (1, 2), (0, 2))
    q_leaf = torch.as_tensor(qv[..., MAXSAT_TARGET_LEVEL], dtype=torch.float64).clone().requires_grad_(True)
    t_leaf = torch.as_tensor(temp[..., MAXSAT_TARGET_LEVEL], dtype=torch.float64).clone().requires_grad_(True)
    p_leaf = torch.as_tensor(p[..., MAXSAT_TARGET_LEVEL], dtype=torch.float64).clone().requires_grad_(True)
    s_leaf = 100.0 * q_leaf / compute_qs_water(t_leaf, p_leaf, params=prm)
    dq, dt, dp = torch.autograd.grad(s_leaf.sum(), (q_leaf, t_leaf, p_leaf), allow_unused=False)
    dS_dq = dq.detach().cpu().numpy()
    dS_dT = dt.detach().cpu().numpy()
    dS_dp = dp.detach().cpu().numpy()
    for a, b in pairs:
        for y, j in enumerate(js):
            for x, i in enumerate(is_):
                k = MAXSAT_TARGET_LEVEL
                safe = not bool(clip_any[a, y, x, k] or clip_any[b, y, x, k])
                warm = bool(temp[a, y, x, k] > prm.ttp and temp[b, y, x, k] > prm.ttp)
                q0, q1 = float(qv[a, y, x, k]), float(qv[b, y, x, k])
                t0, t1 = float(temp[a, y, x, k]), float(temp[b, y, x, k])
                p0, p1 = float(p[a, y, x, k]), float(p[b, y, x, k])
                s0, s1 = float(s_water_pct[a, y, x, k]), float(s_water_pct[b, y, x, k])
                partial_q = float(dS_dq[a, y, x]) * (q1 - q0) if safe and warm else None
                partial_t = float(dS_dT[a, y, x]) * (t1 - t0) if safe and warm else None
                partial_p = float(dS_dp[a, y, x]) * (p1 - p0) if safe and warm else None
                actual = s1 - s0
                remainder = actual - (partial_q + partial_t + partial_p) if safe and warm else None
                time0 = datetime.strptime(labels[a], "%Y-%m-%d_%H:%M:%S")
                time1 = datetime.strptime(labels[b], "%Y-%m-%d_%H:%M:%S")
                elapsed_seconds = int((time1 - time0).total_seconds())
                endpoint_rows.append({
                    "from_frame": int(frames[a]), "from_time": labels[a],
                    "to_frame": int(frames[b]), "to_time": labels[b],
                    "elapsed_seconds_context_not_used_as_rate_denominator": elapsed_seconds,
                    "j": int(j), "i": int(i), "k_bottom_up": k,
                    "z_from_AGL_m": float(z_mid_agl[a, y, x, k]),
                    "z_to_AGL_m": float(z_mid_agl[b, y, x, k]),
                    "p_from_center_hPa": p0 / 100.0, "p_to_center_hPa": p1 / 100.0,
                    "T_from_K": t0, "T_to_K": t1, "qv_from_kgkg": q0, "qv_to_kgkg": q1,
                    "S_liquid_from_percent": s0, "S_liquid_to_percent": s1,
                    "delta_S_liquid_percentage_points": actual,
                    "partial_q_contribution_percentage_points": partial_q,
                    "partial_T_contribution_percentage_points": partial_t,
                    "partial_p_contribution_percentage_points": partial_p,
                    "local_linear_sum_percentage_points": (partial_q + partial_t + partial_p) if safe and warm else None,
                    "nonlinear_remainder_percentage_points": remainder,
                    "local_partials_evaluated_at_from_endpoint": safe and warm,
                    "warm_unclipped_endpoint_scope": safe and warm,
                    "clip_any_at_from_endpoint": bool(clip_any[a, y, x, k]),
                    "clip_any_at_to_endpoint": bool(clip_any[b, y, x, k]),
                    "interpretation": "finite endpoint change decomposition only; remainder is nonlinear/finite-step closure, not a process rate or tendency attribution",
                })

    summary = {
        "maxsat_layer_counts": {str(k): int(np.count_nonzero(maxsat_level == k)) for k in sorted(max_layer_unique)},
        "maxsat_phase_aware_percent_range_all_layers": [float(np.min(maxsat) * 100.0), float(np.max(maxsat) * 100.0)],
        "layer3_maxsat_phase_aware_percent_range": [float(np.min(np.max(maxsat, axis=-1)) * 100.0), float(np.max(np.max(maxsat, axis=-1)) * 100.0)],
        "lower12": {
            "temperature_K_range": [float(temp[..., :LOWER_LEVELS].min()), float(temp[..., :LOWER_LEVELS].max())],
            "qv_kgkg_dry_range": [float(qv[..., :LOWER_LEVELS].min()), float(qv[..., :LOWER_LEVELS].max())],
            "qs_water_kgkg_range": [float(qsw[..., :LOWER_LEVELS].min()), float(qsw[..., :LOWER_LEVELS].max())],
            "theta_v_K_range": [float(theta_v[..., :LOWER_LEVELS].min()), float(theta_v[..., :LOWER_LEVELS].max())],
            "z_mid_AGL_m_range": [float(z_mid_agl[..., :LOWER_LEVELS].min()), float(z_mid_agl[..., :LOWER_LEVELS].max())],
            "actual_midheight_spacing_m_range": [float(dz_center[..., :LOWER_LEVELS - 1].min()), float(dz_center[..., :LOWER_LEVELS - 1].max())],
            "water_saturation_clip_count": int(np.count_nonzero(clip_any[..., :LOWER_LEVELS])),
            "warm_unclipped_layer3_endpoint_count": int(np.count_nonzero((temp[..., MAXSAT_TARGET_LEVEL] > prm.ttp) & ~clip_any[..., MAXSAT_TARGET_LEVEL])),
            "temperature_inversion_adjacent_pair_count": int(sum(row["temperature_inversion_upward_flag"] is True for row in profiles)),
            "adjacent_pair_count": sum(row["dT_vs_below_K"] is not None for row in profiles),
        },
        "layer3": {
            "center_pressure_hPa_range": [float(p[..., MAXSAT_TARGET_LEVEL].min() / 100), float(p[..., MAXSAT_TARGET_LEVEL].max() / 100)],
            "midheight_AGL_m_range": [float(z_mid_agl[..., MAXSAT_TARGET_LEVEL].min()), float(z_mid_agl[..., MAXSAT_TARGET_LEVEL].max())],
            "temperature_K_range": [float(temp[..., MAXSAT_TARGET_LEVEL].min()), float(temp[..., MAXSAT_TARGET_LEVEL].max())],
            "qv_kgkg_dry_range": [float(qv[..., MAXSAT_TARGET_LEVEL].min()), float(qv[..., MAXSAT_TARGET_LEVEL].max())],
            "qs_water_kgkg_range": [float(qsw[..., MAXSAT_TARGET_LEVEL].min()), float(qsw[..., MAXSAT_TARGET_LEVEL].max())],
            "theta_v_K_range": [float(theta_v[..., MAXSAT_TARGET_LEVEL].min()), float(theta_v[..., MAXSAT_TARGET_LEVEL].max())],
        },
        "endpoint_pair_count": len(endpoint_rows),
        "endpoint_decomposition_rows": len(endpoint_rows),
        "all_endpoint_rows_warm_unclipped": all(row["warm_unclipped_endpoint_scope"] for row in endpoint_rows),
        "elapsed_time_division_performed": False,
        "cause_or_process_rate_attribution": False,
        "arbitrary_height_regrid": False,
        "model_H_or_RTTOV_calls": 0,
    }
    return derived, profiles, context, {"endpoint_rows": endpoint_rows, "summary": summary}


def _write_csv(path: Path, rows: list[dict]) -> str:
    if not rows:
        raise ValueError(f"no rows for {path}")
    fields = list(rows[0])
    with path.open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o644)
    return sha256(path)


def _copy_private(src: Path, dst: Path) -> str:
    if dst.exists():
        raise FileExistsError(dst)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.", dir=dst.parent)
    tmp = Path(tmp_name)
    try:
        os.fchmod(tmp_fd, 0o600)
        with os.fdopen(tmp_fd, "wb") as out, src.open("rb") as inp:
            shutil.copyfileobj(inp, out, length=1 << 20)
            out.flush()
            os.fsync(out.fileno())
        os.link(tmp, dst)
        tmp.unlink()
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    return sha256(dst)


def execute() -> int:
    if STARTED.exists() or FAILED.exists() or RESULT_PATH.exists() or CSV_PATH.exists() or DERIVED_NPZ.exists():
        raise FileExistsError("vertical analysis already started or published; refusing repeat")
    if not PLAN_PATH.is_file():
        raise FileNotFoundError("run --plan-only before calculation")
    plan = json.loads(PLAN_PATH.read_text())
    current = plan_payload()
    if plan.get("driver_sha256") != sha256(Path(__file__)):
        raise ValueError("vertical driver changed after plan freeze")
    if {k: v for k, v in plan.items() if k != "created_utc"} != {
        k: v for k, v in current.items() if k != "created_utc"
    } | {"driver_sha256": plan.get("driver_sha256")}:
        raise ValueError("vertical plan/input/source binding changed after predeclaration")
    start = {"status": "STARTED_ONCE", "plan_sha256": sha256(PLAN_PATH),
             "driver_sha256": sha256(Path(__file__)), "input_npz_sha256": sha256(INPUT_NPZ),
             "M_calls": 0, "H_calls": 0, "optimizer_calls": 0}
    with STARTED.open("x") as f:
        json.dump(start, f, indent=2, sort_keys=True)
        f.write("\n")
    STARTED.chmod(0o600)
    try:
        arrays, receipt, source_plan = _read_input()
        derived, profiles, context, output = _derive(arrays)
        if sha256(INPUT_NPZ) != plan["input_npz"]["sha256"]:
            raise ValueError("source NPZ hash changed during vertical derivation")
        with DERIVED_NPZ.open("xb") as f:
            np.savez_compressed(f, **derived)
            f.flush()
            os.fsync(f.fileno())
        DERIVED_NPZ.chmod(0o600)
        canonical_hash = _copy_private(DERIVED_NPZ, CANONICAL_NPZ)
        private_hash = sha256(DERIVED_NPZ)
        if canonical_hash != private_hash:
            raise IOError("canonical derived archive differs from worktree private archive")
        profile_hash = _write_csv(CSV_PATH, profiles)
        context_hash = _write_csv(CONTEXT_CSV, context)
        endpoint_rows = output["endpoint_rows"]
        endpoint_path = PACKET / "VERTICAL_SENSITIVITY_v3.csv"
        endpoint_hash = _write_csv(endpoint_path, endpoint_rows)
        source_map = plan["source_sha256"]
        # Preserve the exact source files used to derive the public/private outputs.
        source_names = {
            "vertical_structure.py": Path(__file__),
            "run_native_kma_bt_frames.py": READER,
            "thermo.py": THERMO,
            "constants.py": CONSTANTS,
        }
        copied_source_hashes = {}
        for name, source in source_names.items():
            dst = SOURCES / name
            if dst.exists():
                raise FileExistsError(dst)
            shutil.copyfile(source, dst)
            dst.chmod(0o600)
            copied_source_hashes[name] = sha256(dst)
            if copied_source_hashes[name] != sha256(source):
                raise IOError(f"canonical source copy hash mismatch: {name}")
        result = {
            "schema": "pr399_vertical_structure_result_v3",
            "status": "READY_DERIVED_DIAGNOSTIC_ONLY",
            "plan_path": str(PLAN_PATH.relative_to(ROOT)), "plan_sha256": sha256(PLAN_PATH),
            "driver_sha256": sha256(Path(__file__)), "source_sha256": source_map,
            "canonical_source_copy_sha256": copied_source_hashes,
            "input_npz_path": str(INPUT_NPZ), "input_npz_sha256": sha256(INPUT_NPZ),
            "input_result_sha256": sha256(INPUT_RESULT), "input_plan_sha256": sha256(INPUT_PLAN),
            "private_npz": {"path": str(DERIVED_NPZ), "sha256": private_hash,
                            "mode": oct(stat.S_IMODE(DERIVED_NPZ.stat().st_mode)),
                            "arrays": {k: {"shape": list(v.shape), "dtype": str(v.dtype), "sha256": arr_sha(v)}
                                       for k, v in sorted(derived.items())}},
            "canonical_private_npz": {"path": str(CANONICAL_NPZ), "sha256": canonical_hash,
                                      "mode": oct(stat.S_IMODE(CANONICAL_NPZ.stat().st_mode)),
                                      "directory_mode": oct(stat.S_IMODE(CANONICAL.stat().st_mode))},
            "canonical_sources_directory": {"path": str(SOURCES), "mode": oct(stat.S_IMODE(SOURCES.stat().st_mode))},
            "public_outputs": {
                "profiles_csv": {"path": str(CSV_PATH.relative_to(ROOT)), "sha256": profile_hash, "rows": len(profiles)},
                "maxsat_context_csv": {"path": str(CONTEXT_CSV.relative_to(ROOT)), "sha256": context_hash, "rows": len(context)},
                "endpoint_sensitivity_csv": {"path": str(endpoint_path.relative_to(ROOT)), "sha256": endpoint_hash, "rows": len(endpoint_rows)},
            },
            "summary": output["summary"],
            "definitions": plan["diagnostics"],
            "claims": {"no_native_forecast_opened": True, "no_model_or_H_calls": True,
                       "no_optimizer": True, "no_RTTOV": True, "no_height_regridding": True,
                       "endpoint_differences_are_rates": False, "remainder_is_process_rate": False,
                       "inversion_or_stability_diagnostic_only": True},
        }
        with RESULT_PATH.open("x") as f:
            json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
            f.write("\n")
        RESULT_PATH.chmod(0o644)
        report = _report(result, output["summary"])
        with REPORT_PATH.open("x") as f:
            f.write(report)
        REPORT_PATH.chmod(0o644)
        print(json.dumps({"status": result["status"], "profile_rows": len(profiles),
                          "maxsat_context_rows": len(context), "sensitivity_rows": len(endpoint_rows),
                          "canonical_npz_sha256": canonical_hash, "M_H_calls": 0}, indent=2))
        return 0
    except BaseException as exc:
        failure = {"schema": "pr399_vertical_failure_v3", "status": "FAILED_NO_RETRY",
                   "error_type": type(exc).__name__, "error": str(exc), "M_calls": 0, "H_calls": 0}
        with FAILED.open("x") as f:
            json.dump(failure, f, indent=2, sort_keys=True)
            f.write("\n")
        FAILED.chmod(0o600)
        raise


def _report(result: dict, summary: dict) -> str:
    lo, hi = summary["lower12"]["z_mid_AGL_m_range"]
    spacing = summary["lower12"]["actual_midheight_spacing_m_range"]
    sl, sh = summary["layer3"]["center_pressure_hPa_range"]
    zl, zh = summary["layer3"]["midheight_AGL_m_range"]
    maxlo, maxhi = summary["layer3_maxsat_phase_aware_percent_range"]
    return f"""# PR399 native vertical-neighbor diagnostic

This diagnostic reads the hash-bound PR398 saved native patch NPZ only. It performs no native forecast read, model integration, M/H call, optimizer, RTTOV execution, or arbitrary-height remapping. The same 27 fixed columns and three saved endpoints are retained.

## Vertical structure

All layer coordinates are native WRF levels in bottom-up order. Interface geopotential is computed from float64-first `(PH+PHB)/g`; native midheight is the average of adjacent interfaces, then surface `HGT` is subtracted for AGL. The lower 12 native levels span {lo:.1f}–{hi:.1f} m AGL, with actual adjacent midheight spacing {spacing[0]:.1f}–{spacing[1]:.1f} m, so the diagnostic preserves nonuniform vertical spacing. The complete per-column lower-12 profiles are in `VERTICAL_RESULT_v3.csv`; the native maxsat level plus its immediately lower and upper neighbors, with actual height and pressure, are in `VERTICAL_MAXSAT_CONTEXT_v3.csv`.

Across all 27 columns at all three times, the phase-aware `qv/qs` maximum occurs at bottom-up layer 3. At that native layer, center pressure is {sl:.2f}–{sh:.2f} hPa, midheight is {zl:.1f}–{zh:.1f} m AGL, and phase-aware saturation diagnostic is {maxlo:.3f}–{maxhi:.3f}%. Native center pressure is float64-first `P+PB`. P8W interface pressures are separately shown as the existing Python REAL(4) transcription; they are not actual host-produced interfaces.

The report includes native temperature, dry mixing ratio `qv`, KDM6 liquid `qs_water`, liquid ratio `S=100*qv/qs_water`, and virtual potential temperature. `theta_v` is computed both as `theta_d*(1+qv/epsilon)/(1+qv)` and `(THM+300)/(1+qv)`; the two forms are checked for agreement. Temperature inversion and positive `dtheta_v/dz` stable-sign flags are descriptive diagnostics only; they do not identify PBL forcing or causes.

## Endpoint changes

`VERTICAL_SENSITIVITY_v3.csv` compares frames 1→4, 4→6, and 1→6 at each column’s layer-3 maxsat level. Each finite endpoint change in liquid saturation `S` is decomposed using local partial derivatives with respect to `qv`, `T`, and `p` evaluated at the starting endpoint. The exact endpoint difference minus those first-order terms is reported as a nonlinear/finite-step remainder. The table does not divide by elapsed seconds; neither the terms nor remainder are process rates or process-tendency attribution. All layer-3 endpoints are warm and outside the KDM6 liquid-q saturation clip branches; the result records this gate explicitly.

Detailed data and source identities are in `VERTICAL_RESULT_v3.json`. Canonical private derived arrays: `{result['canonical_private_npz']['path']}` (SHA256 `{result['canonical_private_npz']['sha256']}`, file 0600, parent 0700). Input PR398 NPZ SHA256 `{result['input_npz_sha256']}`. Science acceptance is not asserted.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--plan-only", action="store_true")
    modes.add_argument("--run-once", action="store_true")
    args = parser.parse_args()
    if args.run_once:
        return execute()
    write_plan()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
