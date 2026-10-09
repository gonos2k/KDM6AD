#!/usr/bin/env python3
"""Recompute PR391 weak-point activation, density-coordinate and cost arithmetic.

Consumes only small saved JSON receipts and the cached weak-point NPZ. It does
not import/run KDM6, RTTOV, the native forecast reader, a model or an optimizer.
The formulas below are explicit arithmetic checks of the recorded values.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
GREEN = ROOT / "harness/evidence/pr391_clear_state_2026-10-09/result.json"
WEAK = ROOT / "harness/evidence/pr391_tq_response_2026-10-09/RESULT_weak_cloud_Tminus0p8.json"
RESPONSE = ROOT / "harness/evidence/pr391_tq_response_2026-10-09/RESULT_summary.json"
COST = ROOT / "harness/evidence/pr391_tq_cost_2026-10-09/RESULT.json"
NPZ = ROOT / "graphify-out/pr391-red/weak_cloud_Tminus0p8_checkpoint.npz"
OUT = ROOT / "harness/evidence/pr392_branch_coordinate_2026-10-09/result.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def qsat_water(t: float, p: float, tp: dict[str, float]) -> float:
    tr = tp["ttp"] / max(t, 1.0)
    es = tp["psat"] * math.exp(math.log(tr) * tp["xa"]) * math.exp(tp["xb"] * (1.0 - tr))
    es = min(es, 0.99 * p)
    return max(tp["ep2"] * es / max(p - es, tp["qmin"]), tp["qmin"])


def solve_temperature_for_sw(q: float, p: float, target_sw_percent: float,
                             tp: dict[str, float]) -> float:
    """Bisection on q/qs_water(T,p)−1; monotone over this warm-layer bracket."""
    low, high = 280.0, 310.0
    def f(t: float) -> float:
        return 100.0 * (q / qsat_water(t, p, tp) - 1.0) - target_sw_percent
    if f(low) <= 0.0 or f(high) >= 0.0:
        raise ValueError("warm-layer temperature root not bracketed")
    for _ in range(100):
        mid = (low + high) / 2.0
        if f(mid) > 0.0:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=OUT)
    args = ap.parse_args()
    green = json.loads(GREEN.read_text())
    weak = json.loads(WEAK.read_text())
    response = json.loads(RESPONSE.read_text())
    cost = json.loads(COST.read_text())
    tp = green["thermodynamics"]["executed_constants_f64"]
    entry = weak["selected_entry"]
    t_weak = float(entry["T_K"])
    qv = float(entry["qv_kgkg_dry"])
    p = float(entry["p_Pa"])
    qs = qsat_water(t_weak, p, tp)
    sw_percent = 100.0 * (qv / qs - 1.0)
    sat_ratio = sw_percent / 0.48
    activation_fraction = min(1.0, max(sat_ratio, 0.0) ** 0.6)
    t_saturation = solve_temperature_for_sw(qv, p, 0.0, tp)
    t_activation_cap = solve_temperature_for_sw(qv, p, 0.48, tp)

    # Only cached selected-column density/number arrays are read here.
    archive = np.load(NPZ, allow_pickle=False)
    k = 3
    rho_m = float(archive["rho_m_forcing"][k])
    qv_npz = float(archive["state_in_qv"][k])
    nccn_in_dry = float(archive["state_in_nccn"][k])
    nccn_out_dry = float(archive["state_out_nccn"][k])
    rho_dry = rho_m / (1.0 + qv_npz)
    rho_dry_recorded = float(archive["rho_d_runtime_entry"][k])
    nccn_in_volume = nccn_in_dry * rho_dry
    nccn_out_volume = nccn_out_dry * rho_dry
    nccn_min_volume = 1.0e8
    d_nccn_dry_d_qv = nccn_min_volume / rho_m
    recorded_jvp = float(weak["whole_runtime_jvp"]["directions"][1]["jvp"][-1])

    qc_out = float(archive["state_out_qc"][k])
    qi_out = float(archive["state_out_qi"][k])
    condensate_g_m3 = (qc_out + qi_out) * rho_dry * 1000.0
    cost_baseline = cost["scenarios"][0]
    cost_weak = next(s for s in cost["scenarios"] if s["scenario"] == "T_minus_0p8K")
    cost_drop = float(cost_baseline["huber_cost"] - cost_weak["huber_cost"])
    cost_drop_percent = 100.0 * cost_drop / float(cost_baseline["huber_cost"])
    ir105_index0 = 3  # public AMI IR105 sample aligns with channel 13 in the saved 10–16 vector
    ir105 = {}
    for name, scenario in (("baseline", cost_baseline), ("T_minus_0p8K", cost_weak)):
        residual = float(scenario["residual_K"][ir105_index0])
        delta = float(cost["cost_contract"]["huber_delta"])
        sigma = float(cost["cost_contract"]["sigma_K"])
        normalized = residual / sigma
        huber = abs(normalized) - delta / 2.0 if abs(normalized) > delta else normalized * normalized / 2.0
        recorded = float(scenario["unmasked_per_channel_huber"][ir105_index0])
        ir105[name] = {
            "channel_1based": 13,
            "residual_model_minus_observation_K": residual,
            "normalized_residual_sigma_units": normalized,
            "huber_delta_sigma_units": delta,
            "computed_huber_contribution": huber,
            "recorded_huber_contribution": recorded,
            "positive_linear_huber_branch": bool(normalized > delta),
        }

    parts = response["equal_final_time_constant_forcing"]
    qc_by_partition = [float(x["selected_qc_kgkg"]) for x in parts]
    d_20_10 = qc_by_partition[0] - qc_by_partition[1]
    d_10_5 = qc_by_partition[1] - qc_by_partition[2]
    observed_ratio = abs(d_20_10 / d_10_5)
    observed_p = math.log2(observed_ratio)

    # Sanity guards are about arithmetic/data alignment only, not branch safety.
    if not math.isclose(sw_percent, float(entry["sw_percent"]), rel_tol=0.0, abs_tol=2e-12):
        raise AssertionError("weak-point supersaturation differs from cached receipt")
    if not math.isclose(rho_dry, rho_dry_recorded, rel_tol=0.0, abs_tol=1e-14):
        raise AssertionError("dry density does not match cached coordinate")
    if not math.isclose(nccn_out_volume, nccn_min_volume, rel_tol=0.0, abs_tol=2e-7):
        raise AssertionError("returned NCCN does not map to the stated volume floor")
    if not math.isclose(d_nccn_dry_d_qv, recorded_jvp, rel_tol=1e-14, abs_tol=1e-8):
        raise AssertionError("dry-coordinate NCCN JVP arithmetic does not match receipt")
    if not math.isclose(condensate_g_m3, float(weak["selected_output"]["condensate_g_m3_using_runtime_entry_rho_dry"]), rel_tol=1e-13):
        raise AssertionError("weak-point content arithmetic differs from receipt")

    receipt = {
        "study": "PR392 conditional branch and output-coordinate arithmetic audit",
        "scope": "cached/public receipt arithmetic only; no KDM/RTTOV/forecast execution or native input reads",
        "worktree_head": "5a7701ed",
        "inputs": {
            "green_saturation_receipt_sha256": sha256(GREEN),
            "weak_cloud_receipt_sha256": sha256(WEAK),
            "response_summary_sha256": sha256(RESPONSE),
            "cost_result_sha256": sha256(COST),
            "cached_weak_checkpoint_sha256": sha256(NPZ),
            "checkpoint_selected_indices": {"wrf_k_zero_based_bottom_up": k, "wrf_j_zero_based": 86, "wrf_i_zero_based": 48},
        },
        "activation_coordinate": {
            "formula": "F=min(1,max(S/0.48,0)^0.6), S=100*(qv/qs_water-1) percent",
            "entry_T_K": t_weak,
            "entry_qv_dry_kgkg": qv,
            "entry_p_Pa": p,
            "qs_water_kgkg": qs,
            "q_over_qs": qv / qs,
            "S_percent": sw_percent,
            "uncapped_saturation_fraction": sat_ratio,
            "saturation_based_activated_fraction": activation_fraction,
            "fixed_p_q_temperature_roots": {
                "water_saturation_gate_S0_T_K": t_saturation,
                "full_activation_fraction_S0p48_T_K": t_activation_cap,
                "weak_point_minus_saturation_start_K": t_weak - t_saturation,
                "weak_point_minus_full_activation_cap_K": t_weak - t_activation_cap,
                "delta_T_to_saturation_onset_from_weak_point_K": t_saturation - t_weak,
                "delta_T_to_full_activation_cap_from_weak_point_K": t_activation_cap - t_weak,
            },
            "scope_limit": "These margins bound only the diagnosed warm-water saturation/CCN-fraction sub-branch; they are not a radius free of every KDM limiter, clamp, microphysics, cloud-operator, or RTTOV branch change.",
        },
        "dry_number_output_coordinate": {
            "rho_m_forcing_kg_m3": rho_m,
            "entry_qv_dry_kgkg": qv_npz,
            "rho_dry_runtime_kg_m3": rho_dry,
            "rho_dry_cached_kg_m3": rho_dry_recorded,
            "input_nccn_dry_specific_per_kg_dry_air": nccn_in_dry,
            "input_nccn_volume_per_m3": nccn_in_volume,
            "output_nccn_dry_specific_per_kg_dry_air": nccn_out_dry,
            "output_nccn_volume_per_m3": nccn_out_volume,
            "nccn_lower_floor_per_m3": nccn_min_volume,
            "derived_d_output_nccn_dry_specific_per_kg_dry_air_d_qv_kgkg": d_nccn_dry_d_qv,
            "recorded_selected_output_jvp": recorded_jvp,
            "interpretation": "At the active volume-floor branch, output NCCN volume stays clamped at 1e8 m^-3. The nonzero dry-specific JVP is the derivative of converting that fixed volume count through rho_dry=rho_m/(1+qv); it is not a physical NCCN production sensitivity.",
        },
        "weak_cloud_content": {
            "qc_dry_kgkg": qc_out,
            "qi_dry_kgkg": qi_out,
            "condensate_g_m3_from_cached_qc_qi_and_runtime_rho_dry": condensate_g_m3,
            "content_gate_threshold_g_m3": 1e-6,
            "derived_binary_cloud_fraction": float(weak["selected_output"]["derived_binary_cfrac"]),
        },
        "conditional_cost_arithmetic": {
            "baseline_seven_channel_huber_sum": float(cost_baseline["huber_cost"]),
            "T_minus_0p8K_seven_channel_huber_sum": float(cost_weak["huber_cost"]),
            "absolute_cost_drop": cost_drop,
            "relative_cost_drop_percent": cost_drop_percent,
            "ir105_residual_and_huber": ir105,
            "cost_support_condition": "both cited cases retain 7/7 channels; strong-cloud cases with new flags are excluded from this pairwise common-support arithmetic",
            "interpretation_limit": "conditional saved-artifact what-if, not an accepted observation match, optimization descent, calibrated error model, or validation result",
        },
        "partition_arithmetic": {
            "fixed_forcing_selected_qc_kgkg_20s_10s_5s": qc_by_partition,
            "activation_gate_sequences": [x["activation_gate_sequence"] for x in parts],
            "difference_20minus10": d_20_10,
            "difference_10minus5": d_10_5,
            "absolute_difference_ratio": observed_ratio,
            "p_observed_log2_ratio": observed_p,
            "interpretation_limit": "Conditional three-partition diagnostic only: activation patterns differ and the sequence is not evidence of asymptotic order, convergence rate, or whole-host timestep accuracy.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({
        "output": str(args.output),
        "activation_fraction": activation_fraction,
        "T_saturation_K": t_saturation,
        "T_cap_K": t_activation_cap,
        "cost_drop_percent": cost_drop_percent,
        "p_obs": observed_p,
        "NCCN_coordinate_JVP_matches": math.isclose(d_nccn_dry_d_qv, recorded_jvp, rel_tol=1e-14, abs_tol=1e-8),
    }, indent=2))


if __name__ == "__main__":
    main()
