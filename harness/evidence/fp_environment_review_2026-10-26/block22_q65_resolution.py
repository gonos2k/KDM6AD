#!/usr/bin/env python3
"""Offline replay of the requested-direction block22 RT-Q65 FD envelope.

Reads only hash-pinned saved NumPy artifacts from the historical block22 packet.
It does not import KDM/RTTOV code or execute a model.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from decimal import Decimal, localcontext

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
PACKET = ROOT / "harness/evidence/block22_activation_2026-10-25"
EXPECTED_PUBLICATION_SHA = "e08ac2d9c5a56b51a75b58d6525b0044c8e953d3dc41cd549eadfca4337b2638"
EXPECTED_INPUT_MANIFEST_SHA = "1aad1ef9ce41faba56cfff6e23fc0bacf3e89c6422f505e65c80ffc269667a5d"
EXPECTED_PLAN_SHA = "fab2afb081d1f74556709a8fbed8dd3f01242ae3aaa417e207ebcf1e617b250f"
EXPECTED_LINEAGE_SHA = "603d2c6f42a0218168002c7f158177df5d466c9a61f77cc8a331f5967b9e9504"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_npz(path: Path, expected_sha: str) -> dict[str, np.ndarray]:
    if sha(path) != expected_sha:
        raise ValueError(f"saved endpoint hash mismatch: {path.relative_to(ROOT)}")
    with np.load(path, allow_pickle=False) as archive:
        return {key: np.array(archive[key], copy=True) for key in archive.files}


def main() -> dict:
    manifest_path = PACKET / "publication_manifest.json"
    input_path = PACKET / "input_manifest.json"
    plan_path = PACKET / "data/experiment_plan_v2.json"
    lineage_path = PACKET / "direction_lineage.json"
    for path, expected in (
        (manifest_path, EXPECTED_PUBLICATION_SHA),
        (input_path, EXPECTED_INPUT_MANIFEST_SHA),
        (plan_path, EXPECTED_PLAN_SHA),
        (lineage_path, EXPECTED_LINEAGE_SHA),
    ):
        if sha(path) != expected:
            raise ValueError(f"source document hash mismatch: {path.relative_to(ROOT)}")

    publication = json.loads(manifest_path.read_text())
    published = {item["path"]: item for item in publication["artifacts"]}
    input_manifest = json.loads(input_path.read_text())
    plan = json.loads(plan_path.read_text())
    lineage = json.loads(lineage_path.read_text())
    if lineage["no_model_rerun"] is not True or not lineage["all_numeric_direction_values_match"]:
        raise ValueError("direction lineage does not establish the requested vector")
    if "not the later post-f32 effective-native C4 direction" not in lineage["scope"]:
        raise ValueError("packet direction scope is not the original requested direction")

    batch = plan["batch"]
    if (batch["block0"], batch["flat_start0"], batch["target_row0"],
            batch["target_flat0"], batch["B"], batch["L"]) != (22, 11264, 368, 11632, 512, 39):
        raise ValueError("requested target mapping differs from the frozen block22 plan")
    if batch["flat_start0"] + batch["target_row0"] != batch["target_flat0"]:
        raise ValueError("target flat index is inconsistent with chunk-local row")

    profile = plan["local_FD"]
    epsilons = [float(x) for x in profile["epsilons"]]
    atol = float(profile["profile_coordinate_atol"])
    rtol = float(profile["profile_coordinate_rtol"])
    if (atol, rtol) != (1.0e-8, 3.0e-5):
        raise ValueError("the frozen Q profile coordinate tolerance changed")

    def item(rel: str) -> dict:
        value = input_manifest["roles"].get(rel)
        if value is None:
            raise ValueError(f"input manifest lacks role {rel}")
        return value

    # The input manifest stores the reference baseline K and profile JVP.
    baseline_info = item("baseline_K")
    jvp_info = item("profile_jvp")
    ad_info = item("ad_control")
    base = load_npz(PACKET / baseline_info["file"], baseline_info["sha256"])
    jvp = load_npz(PACKET / jvp_info["file"], jvp_info["sha256"])
    ad = load_npz(PACKET / ad_info["file"], ad_info["sha256"])
    baseline_theta = np.asarray(ad["baseline__theta_m_input"], dtype=np.float64)
    baseline_qv = np.asarray(ad["baseline__qv_input"], dtype=np.float64)
    direction_theta = np.asarray(ad["baseline__direction_theta_m"], dtype=np.float64)
    direction_qv = np.asarray(ad["baseline__direction_qv"], dtype=np.float64)
    if not (baseline_theta.shape == baseline_qv.shape == direction_theta.shape == direction_qv.shape == (512, 39)):
        raise ValueError("saved AD original-direction input arrays have unexpected shape")
    q0 = np.asarray(base["profile_Q"], dtype=np.float64)
    jq = np.asarray(jvp["JVP_Q"], dtype=np.float64)
    if q0.shape != (1, 66) or jq.shape != (1, 66):
        raise ValueError(f"unexpected baseline/JVP Q shape: {q0.shape}/{jq.shape}")

    # One-based RTTOV layer 65 is zero-based profile_Q/JVP_Q index 64.
    row0, layer0, target_flat0 = int(batch["target_row0"]), 64, int(batch["target_flat0"])
    jvp_q65 = float(jq[0, layer0])
    base_q65 = float(q0[0, layer0])
    native_qv = np.asarray(ad["baseline__primal_native_qv"], dtype=np.float64)
    native_dqv = np.asarray(ad["baseline__tangent_native_qv"], dtype=np.float64)
    if native_qv.shape != native_dqv.shape or native_qv.shape != (512, 39):
        raise ValueError("saved post-finish native qv / tangent shape mismatch")
    target_native_qv = native_qv[row0]
    target_native_dqv = native_dqv[row0]
    # Verify the exact profile-to-native coordinate association using the
    # source-ordered mixture-ratio conversion and the 27-layer upper prefix.
    # The prefix count follows from 66 emitted profile layers - 39 native layers.
    md64, mv64 = np.float64(28.9647e-3), np.float64(18.01528e-3)
    native_num = target_native_qv / mv64
    native_den = (1.0 / md64) + native_num
    native_profile_q = 1.0e6 * native_num / native_den
    upper_prefix = int(q0.shape[1] - target_native_qv.size)
    if upper_prefix != 27 or not np.array_equal(q0[0, upper_prefix:], native_profile_q[::-1]):
        raise ValueError("RT-Q profile order/prefix does not exactly map to reversed native qv")
    native_k0 = target_native_qv.size - 1 - (layer0 - upper_prefix)
    if native_k0 != 1:
        raise ValueError("Q65 no longer maps to target native qv k0=1")

    # Independently derive dQ/dqv in 80-digit Decimal arithmetic from the
    # saved primal qv and saved post-finish dqv tangent. Do not invert dQ.
    with localcontext() as ctx:
        ctx.prec = 80
        dec = lambda x: Decimal.from_float(float(x))
        md_dec, mv_dec = dec(md64), dec(mv64)
        w_dec = dec(target_native_qv[native_k0])
        dw_dec = dec(target_native_dqv[native_k0])
        inv_md = Decimal(1) / md_dec
        inv_mv = Decimal(1) / mv_dec
        qv_denominator = inv_md + w_dec * inv_mv
        dQ_dqv = Decimal(1_000_000) * inv_mv * inv_md / (qv_denominator * qv_denominator)
        analytic_q65_jvp = dQ_dqv * dw_dec
        saved_q65_jvp_dec = dec(jvp_q65)
        analytic_abs_err = abs(analytic_q65_jvp - saved_q65_jvp_dec)
        analytic_rel_err = analytic_abs_err / abs(analytic_q65_jvp)
    reports = []
    source_hashes = {
        "publication_manifest.json": sha(manifest_path),
        "input_manifest.json": sha(input_path),
        "data/experiment_plan_v2.json": sha(plan_path),
        "direction_lineage.json": sha(lineage_path),
        baseline_info["file"]: baseline_info["sha256"],
        jvp_info["file"]: jvp_info["sha256"],
        ad_info["file"]: ad_info["sha256"],
        "oracle/kdm6/obs/model_profile_builder.py": sha(ROOT / "oracle/kdm6/obs/model_profile_builder.py"),
    }
    for eps in epsilons:
        pair = {}
        endpoint_inputs_match = {}
        for sign in (1, -1):
            endpoint_record = next(
                entry for entry in input_manifest["endpoints"]
                if float(entry["epsilon"]) == eps and int(entry["sign"]) == sign
            )
            endpoint_info = endpoint_record["native"]
            endpoint = load_npz(PACKET / endpoint_info["file"], endpoint_info["sha256"])
            profile_q = np.asarray(endpoint["profile_Q"], dtype=np.float64)
            if profile_q.shape != (512, 66):
                raise ValueError(f"unexpected endpoint profile_Q shape at eps={eps}: {profile_q.shape}")
            theta_expected = np.ascontiguousarray(baseline_theta + sign * eps * direction_theta)
            qv_expected = np.ascontiguousarray(baseline_qv + sign * eps * direction_qv)
            theta_saved = np.asarray(endpoint["theta_m_input"], dtype=np.float64)
            qv_saved = np.asarray(endpoint["qv_input"], dtype=np.float64)
            theta_match = theta_saved.shape == theta_expected.shape and theta_saved.view(np.uint64).tobytes() == theta_expected.view(np.uint64).tobytes()
            qv_match = qv_saved.shape == qv_expected.shape and qv_saved.view(np.uint64).tobytes() == qv_expected.view(np.uint64).tobytes()
            if not (theta_match and qv_match):
                raise ValueError(f"endpoint T/Q input differs from original requested direction at eps={eps}, sign={sign}")
            endpoint_inputs_match["plus" if sign > 0 else "minus"] = True
            pair[sign] = float(profile_q[row0, layer0])
            source_hashes[endpoint_info["file"]] = endpoint_info["sha256"]
        q_plus, q_minus = pair[1], pair[-1]
        fd = (q_plus - q_minus) / (2.0 * eps)
        denominator = atol + rtol * max(abs(fd), abs(jvp_q65))
        error = abs(fd - jvp_q65)
        ratio = error / denominator
        ulp = float(np.spacing(np.float64(base_q65)))
        gap_units = (q_plus - q_minus) / ulp
        expected_gap_units = 2.0 * eps * jvp_q65 / ulp
        nearest_gap_units = int(round(expected_gap_units))
        nearest_fd = nearest_gap_units * ulp / (2.0 * eps)
        best_lattice_error = abs(nearest_fd - jvp_q65)
        best_lattice_ratio = best_lattice_error / (
            atol + rtol * max(abs(nearest_fd), abs(jvp_q65))
        )
        reports.append({
            "epsilon": eps,
            "q_plus_ppmv": q_plus,
            "q_minus_ppmv": q_minus,
            "endpoint_TQ_inputs_bitwise_match_original_requested_direction": endpoint_inputs_match,
            "endpoint_gap_ppmv": q_plus - q_minus,
            "endpoint_gap_in_local_f64_ulps": gap_units,
            "jvp_ppmv_per_alpha": jvp_q65,
            "centered_fd_ppmv_per_alpha": fd,
            "absolute_error": error,
            "coordinate_tolerance_denominator": denominator,
            "coordinate_tolerance_ratio": ratio,
            "passes_frozen_Q_coordinate_gate": bool(ratio <= 1.0),
            "nearest_lattice_gap_ulps_for_JVP": nearest_gap_units,
            "JVP_implied_gap_in_ulps": expected_gap_units,
            "nearest_lattice_centered_fd": nearest_fd,
            "best_possible_lattice_error": best_lattice_error,
            "best_possible_lattice_ratio": best_lattice_ratio,
            "no_lattice_value_can_pass_at_this_epsilon": bool(best_lattice_ratio > 1.0),
        })

    q1 = reports[-1]
    # For the final pair, both outputs occupy the same binary64 binade. Any
    # pairwise difference is an integer number of that ULP. This is the exact
    # finite-endpoint lattice used for the impossibility statement.
    q_plus = q1["q_plus_ppmv"]
    q_minus = q1["q_minus_ppmv"]
    if not (float(np.spacing(np.float64(q_plus))) == float(np.spacing(np.float64(q_minus)))
            == float(np.spacing(np.float64(base_q65)))):
        raise ValueError("Q65 endpoint values do not share the expected local f64 ULP")
    if not q1["no_lattice_value_can_pass_at_this_epsilon"]:
        raise ValueError("the stored Q65 finite-difference lattice can pass; no impossibility claim")

    result = {
        "schema": "kdm6.block22_requested_direction_q65_fd_resolution_replay.v1",
        "status": "OFFLINE_SAVED_ARRAY_REPLAY_PASSED",
        "no_model_or_RTTOV_calls": True,
        "scope": "Original requested continuous proposal only; not post-f32 effective-native C4 direction.",
        "source_documents": {
            "publication_manifest_sha256": sha(manifest_path),
            "input_manifest_sha256": sha(input_path),
            "experiment_plan_sha256": sha(plan_path),
            "direction_lineage_sha256": sha(lineage_path),
            "saved_array_sha256": source_hashes,
        },
        "target_coordinate": {
            "block0": 22,
            "flat_start0": 11264,
            "row0": row0,
            "flat_index0": target_flat0,
            "native_i_j_k1": [*batch["target_native_ijk1"][:2], native_k0 + 1],
            "activation_witness_native_i_j_k1": batch["target_native_ijk1"],
            "field": "Q",
            "units": "ppmv",
            "grid": "RTTOV profile layer grid; 66 layers in top-to-surface order, preceded by the 27 fixed upper-reference layer prefix",
            "level_one_based": 65,
            "array_index_zero_based": layer0,
            "profile_shape": [1, 66],
            "baseline_Q_ppmv": base_q65,
            "JVP_Q_ppmv_per_alpha": jvp_q65,
            "verified_native_mapping": {
                "profile_upper_prefix_layers": upper_prefix,
                "native_levels_in_profile_are_reversed": True,
                "native_qv_index_zero_based": native_k0,
                "native_qv_primal": float(target_native_qv[native_k0]),
                "native_qv_tangent_post_finish": float(target_native_dqv[native_k0]),
                "all_39_native_Q_profile_values_match_source_order_conversion_bitwise": True,
            },
            "independent_80_digit_decimal_chain_rule": {
                "m_dry_air_source_float": float(md64),
                "m_water_vapor_source_float": float(mv64),
                "dQ_dqv_ppmv_per_kgkg": str(dQ_dqv),
                "analytic_JVP_ppmv_per_alpha": str(analytic_q65_jvp),
                "saved_profile_Q_JVP_ppmv_per_alpha": str(saved_q65_jvp_dec),
                "absolute_difference": str(analytic_abs_err),
                "relative_difference": str(analytic_rel_err),
            },
        },
        "gate": {
            "formula": "abs(FD-JVP)/(atol+rtol*max(abs(FD),abs(JVP)))",
            "atol": atol,
            "rtol": rtol,
            "criterion": "ratio <= 1",
            "scope": "one Q coordinate only; profile coordinate gate, not native17 fieldmax or joint33",
        },
        "epsilon_results": reports,
        "epsilon_1e_minus_6_resolution_result": {
            "observed_endpoint_gap_ulps": q1["endpoint_gap_in_local_f64_ulps"],
            "JVP_implied_gap_ulps": q1["JVP_implied_gap_in_ulps"],
            "nearest_gap_ulps": q1["nearest_lattice_gap_ulps_for_JVP"],
            "nearest_lattice_ratio": q1["best_possible_lattice_ratio"],
            "interpretation": "At epsilon=1e-6, the centered endpoint-difference lattice is too coarse for this one Q coordinate to meet the frozen tolerance: even the nearest binary64-representable endpoint gap has ratio >1. This is a saved-output resolution limit, not evidence that the JVP is wrong. It does not extend to other epsilons or the post-f32 effective direction.",
        },
    }
    return result


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True, indent=2, allow_nan=False))
