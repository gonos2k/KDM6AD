#!/usr/bin/env python3
"""Recompute a bounded two-control saturation-boundary prior diagnostic.

Reads only the public PR391 clear-state thermodynamic JSON, weak T-minus-0.8 K
receipt, and seven-channel cost-scenario JSON. Uses Python's standard library;
does not import KDM6, open NPZ data, or run an optimizer/model/RTTOV.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CLEAR = ROOT / "harness/evidence/pr391_clear_state_2026-10-09/result.json"
DEFAULT_WEAK = ROOT / "harness/evidence/pr391_tq_response_2026-10-09/RESULT_weak_cloud_Tminus0p8.json"
DEFAULT_COST = ROOT / "harness/evidence/pr391_tq_cost_2026-10-09/RESULT.json"
DEFAULT_OUTPUT = Path(__file__).with_name("RESULT.json")
TH_SIGMA_K = 0.8
QV_LOG_SIGMA = 0.08
GRID_POINTS = 20_001


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def water_qs_and_log_derivative(t_k: float, p_pa: float, thermo: dict) -> tuple[float, float, dict]:
    """Uncapped warm-water Goff-Gratch qsat and d(log(qsat))/dT."""
    tr = thermo["ttp"] / t_k
    es = (thermo["psat"] * math.exp(math.log(tr) * thermo["xa"])
          * math.exp(thermo["xb"] * (1.0 - tr)))
    qs = thermo["ep2"] * es / (p_pa - es)
    dlog_es = (-thermo["xa"] / t_k
               + thermo["xb"] * thermo["ttp"] / (t_k * t_k))
    dlog_qs = p_pa / (p_pa - es) * dlog_es
    return qs, dlog_qs, {"tr": tr, "es_Pa": es, "dlog_es_dT_per_K": dlog_es}


def scenario_map(cost_receipt: dict) -> dict:
    return {row["scenario"]: row for row in cost_receipt["scenarios"]}


def analyze(clear_path: Path, weak_path: Path, cost_path: Path) -> dict:
    clear = json.loads(clear_path.read_text())
    weak = json.loads(weak_path.read_text())
    cost = json.loads(cost_path.read_text())
    thermo = clear["thermodynamics"]["executed_constants_f64"]
    if clear["thermodynamics"]["f32_rounded_coefficients_are_used_by_default_thermo_params"] is not True:
        raise ValueError("clear-state receipt does not attest the executed code-rounded thermo constants")

    base = clear["thermodynamics"]["at_max"]
    weak_entry = weak["selected_entry"]
    delta_t = weak["case"]["delta_T_K"]
    delta_theta = weak["case"]["theta_delta_K"]
    if not math.isclose(delta_t, -0.8, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"expected the saved −0.8 K scenario, got {delta_t}")
    t_b = base["T_K"]
    q_b = base["q_dry_kgkg"]
    p_pa = weak_entry["p_Pa"]
    baseline_profile = scenario_map(cost)["baseline"]["profile_identity"]
    if not math.isclose(base["p_hPa"] * 100.0, p_pa, rel_tol=0.0, abs_tol=1e-8):
        raise ValueError("weak and clear-state receipts disagree on selected pressure")
    if not math.isclose(baseline_profile["k3_wrf_zero_based_temperature_K"],
                        t_b, rel_tol=0.0, abs_tol=1e-10):
        raise ValueError("baseline cost profile temperature disagrees with clear-state input")
    q_ppmv_cost = baseline_profile["k3_wrf_zero_based_q_ppmv_moist"]
    if not math.isclose(q_ppmv_cost, base["q_ppmv_moist"],
                        rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("baseline cost profile q disagrees with clear-state input")
    chi = q_ppmv_cost * 1.0e-6
    q_dry_from_cost = (18.01528 / 28.9647) * chi / (1.0 - chi)
    if not math.isclose(q_dry_from_cost, q_b, rel_tol=0.0, abs_tol=1e-14):
        raise ValueError("baseline cost profile moist-ppm conversion disagrees with clear-state qdry")
    if not math.isclose(weak_entry["qv_kgkg_dry"], q_b, rel_tol=0.0, abs_tol=1e-15):
        raise ValueError("weak scenario did not preserve the baseline qv used by this cost model")
    if not math.isclose(weak_entry["T_K"], t_b + delta_t, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("saved weak-state temperature does not match its declared delta_T")
    exner = delta_t / delta_theta
    s_t = TH_SIGMA_K * exner
    s_q = QV_LOG_SIGMA
    if not (math.isfinite(exner) and exner > 0.0 and s_t > 0.0):
        raise ValueError("derived Exner/prior scales are invalid")

    def objective_and_derivative(t_k: float) -> tuple[float, float, dict]:
        qs, dlog_qs, details = water_qs_and_log_derivative(t_k, p_pa, thermo)
        log_ratio = math.log(qs / q_b)
        j = 0.5 * (((t_k - t_b) / s_t) ** 2 + (log_ratio / s_q) ** 2)
        dj = ((t_k - t_b) / (s_t * s_t)
              + log_ratio * dlog_qs / (s_q * s_q))
        return j, dj, {**details, "qs_water_kgkg": qs,
                       "log_qs_over_qb": log_ratio, "dlog_qs_dT_per_K": dlog_qs}

    lo, hi = t_b - 2.0, t_b + 2.0
    g_lo, g_hi = objective_and_derivative(lo)[1], objective_and_derivative(hi)[1]
    if not (g_lo < 0.0 < g_hi):
        raise ValueError("bounded interval does not bracket the declared stationary root")

    # Bisection on the derivative gives an independent one-dimensional
    # stationary point. It is intentionally bounded to Tb±2 K.
    root_lo, root_hi = t_b - 1.0, t_b
    if not (objective_and_derivative(root_lo)[1] < 0.0
            < objective_and_derivative(root_hi)[1]):
        raise ValueError("expected the local root bracket [Tb−1,Tb] to straddle zero")
    for _ in range(100):
        mid = 0.5 * (root_lo + root_hi)
        if objective_and_derivative(mid)[1] > 0.0:
            root_hi = mid
        else:
            root_lo = mid
    t_star = 0.5 * (root_lo + root_hi)
    j_star, derivative_star, details_star = objective_and_derivative(t_star)
    u_star = (t_star - t_b) / s_t
    v_star = details_star["log_qs_over_qb"] / s_q
    q_star = details_star["qs_water_kgkg"]

    # Independent 20,001-point grid countercheck across the entire bounded
    # interval. This is a discretized check, not a global multi-control search.
    dx = (hi - lo) / (GRID_POINTS - 1)
    grid_best_i = min(range(GRID_POINTS),
                      key=lambda i: objective_and_derivative(lo + i * dx)[0])
    t_grid = lo + grid_best_i * dx
    j_grid = objective_and_derivative(t_grid)[0]
    if j_grid < j_star - 2.0e-9:
        raise AssertionError("the independent grid found a lower cost than the stationary point")

    # One-control boundary distances and the linearized two-control norm step.
    # The stored clear-state root is independently checked with the same qsat.
    cool_lo, cool_hi = lo, t_b
    if not (water_qs_and_log_derivative(cool_lo, p_pa, thermo)[0] < q_b
            < water_qs_and_log_derivative(cool_hi, p_pa, thermo)[0]):
        raise ValueError("cooling-only saturation crossing is not bracketed")
    for _ in range(100):
        mid = 0.5 * (cool_lo + cool_hi)
        if water_qs_and_log_derivative(mid, p_pa, thermo)[0] > q_b:
            cool_hi = mid
        else:
            cool_lo = mid
    t_cool = 0.5 * (cool_lo + cool_hi)
    cool_j = 0.5 * ((t_cool - t_b) / s_t) ** 2
    stored_cool_t = base["constant_p_q_water_saturation_root_T_K"]

    qs_b, dlog_b, detail_b = water_qs_and_log_derivative(t_b, p_pa, thermo)
    r0 = math.log(qs_b / q_b)
    moist_j = 0.5 * (r0 / s_q) ** 2
    linear_vector = (-s_t * dlog_b, s_q)
    linear_scale = r0 / (linear_vector[0] ** 2 + linear_vector[1] ** 2)
    u_linear = linear_scale * linear_vector[0]
    v_linear = linear_scale * linear_vector[1]
    j_linear = 0.5 * (u_linear * u_linear + v_linear * v_linear)

    # Check every grid point for the saturation clamps/regime assumed by the
    # derivative. The formulas remain on the warm water branch in this bracket.
    guard_minima = {
        "T_K": float("inf"), "es_cap_margin_Pa": float("inf"),
        "qs_floor_margin_kgkg": float("inf"),
        "p_minus_es_margin_Pa": float("inf"),
        "water_branch_margin_K": float("inf"),
    }
    for i in range(GRID_POINTS):
        t = lo + i * dx
        qs, _, detail = water_qs_and_log_derivative(t, p_pa, thermo)
        guard_minima["T_K"] = min(guard_minima["T_K"], t)
        guard_minima["es_cap_margin_Pa"] = min(
            guard_minima["es_cap_margin_Pa"], 0.99 * p_pa - detail["es_Pa"])
        guard_minima["qs_floor_margin_kgkg"] = min(
            guard_minima["qs_floor_margin_kgkg"], qs - thermo["qmin"])
        guard_minima["p_minus_es_margin_Pa"] = min(
            guard_minima["p_minus_es_margin_Pa"], p_pa - detail["es_Pa"] - thermo["qmin"])
        guard_minima["water_branch_margin_K"] = min(
            guard_minima["water_branch_margin_K"], t - thermo["ttp"])
    if not (guard_minima["T_K"] > 1.0
            and guard_minima["es_cap_margin_Pa"] > 0.0
            and guard_minima["qs_floor_margin_kgkg"] > 0.0
            and guard_minima["p_minus_es_margin_Pa"] > 0.0
            and guard_minima["water_branch_margin_K"] > 0.0):
        raise AssertionError("a saturation clamp or warm-water branch guard became active")

    scenarios = scenario_map(cost)
    cost_contract = cost["cost_contract"]
    expected_channels = list(range(10, 17))
    if (cost_contract["channels_1based"] != expected_channels
            or cost_contract["sigma_K"] != 1.0
            or cost_contract["bias_K"] != 0.0
            or cost_contract["huber_delta"] != 1.0):
        raise ValueError("PR391 cost receipt does not match the declared seven-channel diagnostic")
    baseline = scenarios["baseline"]
    half_kelvin_case = scenarios["T_minus_0p5K"]
    weak_case = scenarios["T_minus_0p8K"]
    if (baseline["valid_channel_count"] != 7
            or half_kelvin_case["valid_channel_count"] != 7
            or weak_case["valid_channel_count"] != 7):
        raise ValueError("baseline, T−0.5 K, and T−0.8 K costs need the same seven-channel support")
    weak_jb = 0.5 * (delta_t / s_t) ** 2
    weak_jb_direct_theta = 0.5 * (delta_theta / TH_SIGMA_K) ** 2
    if not math.isclose(weak_jb, weak_jb_direct_theta,
                        rel_tol=0.0, abs_tol=1.0e-14):
        raise AssertionError("physical-T and potential-temperature prior costs do not agree")
    weak_total = weak_case["huber_cost"] + weak_jb
    thermal_prior_rows = []
    for name, scenario, scenario_delta_t in (
            ("baseline", baseline, 0.0),
            ("T_minus_0p5K", half_kelvin_case, -0.5),
            ("T_minus_0p8K", weak_case, delta_t)):
        jb = 0.5 * (scenario_delta_t / s_t) ** 2
        total = scenario["huber_cost"] + jb
        thermal_prior_rows.append({
            "scenario": name,
            "delta_physical_T_K": scenario_delta_t,
            "Jo_saved_seven_channel_huber": scenario["huber_cost"],
            "valid_channel_count": scenario["valid_channel_count"],
            "Jb_th_prior_from_sT": jb,
            "Jtotal_Jb_plus_saved_Jo": total,
            "Jtotal_minus_baseline_Jo": total - baseline["huber_cost"],
        })

    # Self-arithmetic pins and scenario checks against the requested values.
    expected = {
        "cooling_only_j": 0.4281588809398883,
        "moist_only_j": 0.16304710738537354,
        "joint_j": 0.11818300348272258,
        "joint_u": -0.25513666046827227,
        "joint_v": 0.4138493584029613,
    }
    actual = {"cooling_only_j": cool_j, "moist_only_j": moist_j,
              "joint_j": j_star, "joint_u": u_star, "joint_v": v_star}
    for name, value in actual.items():
        if not math.isclose(value, expected[name], rel_tol=0.0, abs_tol=2.0e-8):
            raise AssertionError(f"{name} mismatch: {value} != {expected[name]}")
    if not math.isclose(t_cool, stored_cool_t, rel_tol=0.0, abs_tol=1.0e-10):
        raise AssertionError("independent cooling-only root differs from clear-state receipt")

    scenarios_out = []
    for name in ("baseline", "T_minus_0p5K", "T_minus_0p8K",
                 "T_minus_1p0K", "qv_plus_2pct", "qv_plus_6pct"):
        row = scenarios[name]
        scenarios_out.append({
            "scenario": name,
            "Jo_huber_sum": row["huber_cost"],
            "valid_channel_count": row["valid_channel_count"],
            "comparable_on_fixed_seven_channel_support": row["valid_channel_count"] == 7,
        })

    return {
        "study": "PR394 bounded prior-regularized saturation-boundary scalar",
        "scope": (
            "Offline one-temperature saturation-boundary calculation from exactly three public JSON receipts. "
            "No NPZ, KDM6 integration, RTTOV, optimizer, native run, or external data was read or executed."),
        "inputs": {
            "clear_state_result": display_path(clear_path),
            "clear_state_result_sha256": sha256(clear_path),
            "weak_delta_receipt": display_path(weak_path),
            "weak_delta_receipt_sha256": sha256(weak_path),
            "cost_scenario_receipt": display_path(cost_path),
            "cost_scenario_receipt_sha256": sha256(cost_path),
            "analysis_script": display_path(Path(__file__).resolve()),
            "analysis_script_sha256": sha256(Path(__file__).resolve()),
        },
        "selected_baseline": {
            "T_b_K": t_b,
            "q_b_dry_kgkg": q_b,
            "q_ppmv_moist_from_cost_profile": q_ppmv_cost,
            "q_b_recomputed_from_cost_profile_kgkg_dry": q_dry_from_cost,
            "p_Pa": p_pa,
            "saved_weak_delta_T_K": delta_t,
            "saved_weak_delta_theta_K": delta_theta,
            "Exner_from_saved_delta_T_over_delta_theta": exner,
            "th_prior_sigma_K": TH_SIGMA_K,
            "qv_log_prior_sigma": QV_LOG_SIGMA,
            "induced_physical_T_prior_sigma_K": s_t,
            "pressure_matches_clear_receipt": True,
            "qv_matches_clear_receipt": True,
        },
        "thermo_constants_from_clear_receipt": thermo,
        "objective_contract": {
            "qs_water": "es=psat*exp(log(ttp/T)*xa)*exp(xb*(1-ttp/T)); qs=ep2*es/(p-es)",
            "prior_regularized_boundary_cost": "0.5*((T-Tb)/sT)^2 + 0.5*(log(qs(T)/qb)/sq)^2",
            "stationarity": "(T-Tb)/sT^2 + log(qs(T)/qb)*(dlogqs/dT)/sq^2 = 0",
            "dlogqs_dT": "p/(p-es)*(-xa/T + xb*ttp/T^2)",
            "control_coordinates": {"u": "(T-Tb)/sT", "v": "log(qs(T)/qb)/sq"},
            "bounded_temperature_interval_K": [lo, hi],
            "prior_scope": "two controls only: potential-temperature additive prior mapped by saved Exner, and qv multiplicative log prior; not the full 51-control space",
        },
        "boundary_minimum": {
            "method": "100-step bisection on analytic derivative in [Tb−1,Tb], plus endpoint and 20,001-point grid comparisons over Tb±2 K",
            "stationary_bracket_K": [root_lo, root_hi],
            "dJ_dT_at_root": derivative_star,
            "T_star_K": t_star,
            "delta_T_K": t_star - t_b,
            "qs_star_kgkg": q_star,
            "qv_factor_star": q_star / q_b,
            "qv_relative_change_percent": 100.0 * (q_star / q_b - 1.0),
            "u_star": u_star,
            "v_star": v_star,
            "J_star": j_star,
            "grid_check": {
                "points": GRID_POINTS,
                "spacing_K": dx,
                "minimum_T_K": t_grid,
                "minimum_J": j_grid,
                "grid_minus_root_J": j_grid - j_star,
            },
        },
        "one_control_and_linearized_comparisons": {
            "cooling_only": {
                "T_sat_q_fixed_K": t_cool,
                "delta_T_K": t_cool - t_b,
                "J": cool_j,
                "stored_clear_receipt_root_K": stored_cool_t,
            },
            "moist_only": {
                "T_K": t_b,
                "qv_factor": qs_b / q_b,
                "log_qv_increment": r0,
                "J": moist_j,
            },
            "linearized_minimum_norm": {
                "baseline_log_saturation_gap": r0,
                "a_vector_u_v": list(linear_vector),
                "u": u_linear,
                "v": v_linear,
                "J": j_linear,
            },
        },
        "guard_applicability_on_grid": {
            "T_lower_clamp_inactive_T_gt_1": True,
            "es_upper_cap_inactive_es_lt_0p99p": True,
            "qs_lower_floor_inactive_qs_gt_qmin": True,
            "p_minus_es_denominator_safe": True,
            "warm_water_branch_T_gt_ttp": True,
            "minimum_margins": guard_minima,
        },
        "saved_cost_scenarios": {
            "cost_contract": cost_contract,
            "rows": scenarios_out,
            "temperature_prior_adjusted_table": thermal_prior_rows,
            "weak_minus_0p8_prior_adjustment": {
                "saved_Jo": weak_case["huber_cost"],
                "Jb_from_physical_T_delta_over_sT": weak_jb,
                "Jb_direct_theta_delta_over_sigma": weak_jb_direct_theta,
                "prior_coordinate_closure": weak_jb - weak_jb_direct_theta,
                "Jb_plus_saved_Jo": weak_total,
                "baseline_Jo": baseline["huber_cost"],
                "difference_vs_baseline_Jo": weak_total - baseline["huber_cost"],
                "same_seven_channel_support": True,
            },
        },
        "interpretation_and_limits": [
            "The scalar boundary minimum is conditional on exactly two prior-scaled controls and the uncapped warm-water qsat formula in Tb±2 K; it is not a global 51-control minimum or a suggested optimizer seed.",
            "The saved T−0.8 K and qv perturbation Jo values are forward diagnostic scenarios, not optimized analyses. Their prior-adjusted arithmetic does not create a new observation match.",
            "The T−1 K and qv+6% scenarios lose one or more channels; they are explicitly marked incomparable with the fixed seven-channel objective.",
            "No KDM/RTTOV profile derivative, high-level optimizer, physical prior calibration, observation admissibility, or forecast skill is inferred by this scalar calculation.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear-result", type=Path, default=DEFAULT_CLEAR)
    parser.add_argument("--weak-result", type=Path, default=DEFAULT_WEAK)
    parser.add_argument("--cost-result", type=Path, default=DEFAULT_COST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"refusing to overwrite existing output {args.output}; pass a fresh --output path")
    result = analyze(args.clear_result, args.weak_result, args.cost_result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({
        "output": display_path(args.output),
        "T_star_K": result["boundary_minimum"]["T_star_K"],
        "J_star": result["boundary_minimum"]["J_star"],
        "grid_minus_root_J": result["boundary_minimum"]["grid_check"]["grid_minus_root_J"],
        "input_hashes": {k: v for k, v in result["inputs"].items()
                         if k.endswith("sha256")},
    }, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
