#!/usr/bin/env python3
"""Recompute the local satadj residual from two public JSON receipts only.

This reader is value-only. It does not import KDM6 code or load archived
forecast arrays, NPZ checkpoints, native runs, or RTTOV products.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CLEAR = ROOT / "harness/evidence/pr391_clear_state_2026-10-09/result.json"
DEFAULT_PARTITION = ROOT / "harness/evidence/pr392_applied_partition_2026-10-09/RESULT.json"
DEFAULT_OUTPUT = Path(__file__).with_name("RESULT.json")


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


def qsat_water(t_k: float, p_pa: float, thermo: dict) -> tuple[float, float]:
    """Exact real derivative target for the uncapped water Goff-Gratch map."""
    ttp = thermo["ttp"]
    tr = ttp / t_k
    es = (thermo["psat"] * math.exp(math.log(tr) * thermo["xa"])
          * math.exp(thermo["xb"] * (1.0 - tr)))
    qs = thermo["ep2"] * es / (p_pa - es)
    return qs, es


def dqsdT_water(t_k: float, p_pa: float, thermo: dict, es: float) -> float:
    """Analytic derivative of ep2*es/(p-es), with the constants held fixed."""
    dloges_dT = (-thermo["xa"] / t_k
                 + thermo["xb"] * thermo["ttp"] / (t_k * t_k))
    des_dT = es * dloges_dT
    return thermo["ep2"] * p_pa / ((p_pa - es) * (p_pa - es)) * des_dT


def reconstruct_call(call: dict, p_pa: float, thermo: dict) -> dict:
    captured = call["captured"]
    applied = call["reconstructed_from_source_equations"]
    qv_in, qc_in, t_in = captured["qv_qc_T_in"]
    qv_out, qc_out, t_out = captured["qv_qc_T_out"]
    xl = captured["xl_J_kg"]
    cpm = captured["cpm_J_kg_K"]
    activation_amount = applied["a_pcact_applied_mass_kgkg"]

    # Coordinator pcact (a) runs before satadj. The public applied-partition
    # receipt labels this a as reconstructed, not as a directly captured rate.
    qv_post_a = qv_in - activation_amount
    qc_post_a = qc_in + activation_amount
    t_post_a = t_in + (xl / cpm) * activation_amount
    qs, es = qsat_water(t_post_a, p_pa, thermo)
    dqs_dT = dqsdT_water(t_post_a, p_pa, thermo, es)
    g = qv_post_a - qs

    # Preserve the source's left-associated arithmetic for the implemented
    # denominator: 1 + ((((xl*xl)/(rv*cpm))*qs)/(T*T)).
    implemented_term = (((xl * xl) / (thermo["rv"] * cpm)) * qs) \
        / (t_post_a * t_post_a)
    d_impl = 1.0 + implemented_term
    d_exact = 1.0 + (xl / cpm) * dqs_dT
    work1 = g / d_impl

    if g > 0.0:
        branch = "condensation"
        amount_limited = min(work1, max(qv_post_a, 0.0))
        limiter_active = amount_limited != work1
    elif g < 0.0 and qc_post_a > 0.0:
        branch = "evaporation"
        amount_limited = max(work1, -qc_post_a)
        limiter_active = amount_limited != work1
    else:
        branch = "zero"
        amount_limited = 0.0
        limiter_active = work1 != 0.0

    qs_out, es_out = qsat_water(t_out, p_pa, thermo)
    g_plus = qv_out - qs_out
    predicted_residual_ratio = 1.0 - d_exact / d_impl
    observed_residual_ratio = g_plus / g if g != 0.0 else None
    c_observed_reconstruction = applied["c_pcond_applied_mass_kgkg"]
    endpoint_closure = {
        "qv_out_minus_postactivation_minus_c_kgkg":
            qv_out - (qv_post_a - c_observed_reconstruction),
        "qc_out_minus_postactivation_plus_c_kgkg":
            qc_out - (qc_post_a + c_observed_reconstruction),
        "T_out_minus_postactivation_latent_update_K":
            t_out - (t_post_a + (xl / cpm) * c_observed_reconstruction),
    }

    t_clamp_inactive = t_post_a > 1.0
    vapor_pressure_cap_inactive = es < 0.99 * p_pa
    qs_floor_inactive = qs > thermo["qmin"]
    pressure_denominator_safe = p_pa - es > thermo["qmin"]
    water_branch = t_post_a >= thermo["ttp"]
    activation_q_floor_inactive = qv_post_a > thermo["qmin"]

    return {
        "call_index_1based": call["call_index_1based"],
        "activation_gate_sw_gt_zero": captured["activation_gate_sw_gt_zero"],
        "sw_percent": captured["sw_percent"],
        "dtcld_s_f32": call["dtcld_s_f32"],
        "post_activation_reconstruction": {
            "a_pcact_applied_mass_kgkg_from_public_partition_receipt": activation_amount,
            "qv_kgkg_dry": qv_post_a,
            "qc_kgkg_dry": qc_post_a,
            "T_K": t_post_a,
        },
        "water_saturation": {
            "es_Pa": es,
            "qs_kgkg_dry": qs,
            "g_qv_minus_qs_kgkg": g,
            "dqsdT_kgkg_per_K": dqs_dT,
            "dlog_es_dT_per_K": (-thermo["xa"] / t_post_a
                                    + thermo["xb"] * thermo["ttp"]
                                    / (t_post_a * t_post_a)),
        },
        "denominator_comparison": {
            "Dimpl_left_associated": d_impl,
            "Dexact_local_thermo_derivative": d_exact,
            "Dexact_over_Dimpl_minus_1": d_exact / d_impl - 1.0,
        },
        "satadj_amount": {
            "work1_g_over_Dimpl_kgkg": work1,
            "source_branch": branch,
            "amount_after_source_availability_cap_kgkg": amount_limited,
            "availability_cap_active": limiter_active,
            "c_applied_reconstructed_from_public_receipt_kgkg": c_observed_reconstruction,
            "amount_reconstruction_error_kgkg": amount_limited - c_observed_reconstruction,
        },
        "endpoint_closure_checks": endpoint_closure,
        "residual_after_applied_amount": {
            "gplus_from_returned_qv_T_kgkg": g_plus,
            "predicted_first_order_gplus_over_g": predicted_residual_ratio,
            "observed_finite_change_gplus_over_g": observed_residual_ratio,
            "observed_minus_predicted": (None if observed_residual_ratio is None else
                                         observed_residual_ratio - predicted_residual_ratio),
        },
        "applicability_and_guard_checks": {
            "T_lower_clamp_inactive": t_clamp_inactive,
            "es_upper_cap_es_lt_0p99p": vapor_pressure_cap_inactive,
            "qs_lower_floor_inactive": qs_floor_inactive,
            "p_minus_es_denominator_safe": pressure_denominator_safe,
            "water_branch_T_ge_ttp": water_branch,
            "qv_floor_inactive": activation_q_floor_inactive,
            "observed_qc_positive_for_evaporation_availability": qc_post_a > 0.0,
            "endpoint_es_upper_cap_inactive": es_out < 0.99 * p_pa,
        },
    }


def analyze(clear_path: Path, partition_path: Path) -> dict:
    clear = json.loads(clear_path.read_text())
    partition = json.loads(partition_path.read_text())
    thermo = clear["thermodynamics"]["executed_constants_f64"]
    p_pa = partition["selected_column"]["p_Pa"]
    five_second = next(p for p in partition["partition_summary"]
                       if p["partition"] == "5s_four_times")
    calls = five_second["calls"]
    if len(calls) != 4:
        raise ValueError(f"expected four 5 s calls, received {len(calls)}")

    reconstructed = []
    for i, call in enumerate(calls, start=1):
        reconstructed.append(reconstruct_call(
            {**call, "call_index_1based": i}, p_pa, thermo))

    # These assertions make the public receipt arithmetic auditable and catch
    # wrong source inputs, operation grouping, or a changed formula.
    expected = {
        2: (3.630693761, 3.707384080, -0.021122773, -0.021023471),
        3: (3.630022710, 3.706670897, -0.021115071, -0.021117159),
    }
    comparisons = []
    for index, published in expected.items():
        row = reconstructed[index - 1]
        d = row["denominator_comparison"]
        residual = row["residual_after_applied_amount"]
        actual = (d["Dimpl_left_associated"], d["Dexact_local_thermo_derivative"],
                  residual["predicted_first_order_gplus_over_g"],
                  residual["observed_finite_change_gplus_over_g"])
        if not all(math.isclose(a, e, rel_tol=0.0, abs_tol=5.0e-10)
                   for a, e in zip(actual, published)):
            raise AssertionError(
                f"call {index} failed published reconstruction check: "
                f"actual={actual}, expected={published}")
        comparisons.append({"call_index_1based": index,
                            "published_rounded": list(published),
                            "recomputed": list(actual),
                            "absolute_errors": [abs(a - e)
                                                for a, e in zip(actual, published)]})

    # N1: check the third 5 s call's positive activation gate against the
    # reconstructed fraction and captured coordinator-stage number inventory.
    # NC/NCCN are captured volume coordinates; F, b, and a are reconstructed.
    n1_call = calls[2]
    n1_captured = n1_call["captured"]
    n1_reconstructed = n1_call["reconstructed_from_source_equations"]
    nc_in, nccn_in = n1_captured["NC_NCCN_volume_in_m3"]
    activation_fraction = n1_reconstructed["activated_fraction"]
    activation_threshold = nc_in / (nc_in + nccn_in)
    b_raw = (nc_in + nccn_in) * activation_fraction - nc_in
    b_from_equation = min(max(b_raw, 0.0), nccn_in)
    b_stored = n1_reconstructed["b_ncact_applied_number_m3"]
    a_stored = n1_reconstructed["a_pcact_applied_mass_kgkg"]
    if not n1_captured["activation_gate_sw_gt_zero"]:
        raise AssertionError("N1 expected the third 5 s call's activation gate true")
    if not (0.0 < activation_fraction < activation_threshold):
        raise AssertionError("N1 activation fraction must be positive and below inventory threshold")
    if b_from_equation != 0.0 or b_stored != 0.0 or a_stored != 0.0:
        raise AssertionError(
            "N1 inventory clamp must reproduce stored reconstructed b=0 and a=0")

    # The source guards must be inactive for every analytic derivative point.
    for row in reconstructed:
        guards = row["applicability_and_guard_checks"]
        for name in ("T_lower_clamp_inactive", "es_upper_cap_es_lt_0p99p",
                     "qs_lower_floor_inactive", "p_minus_es_denominator_safe",
                     "water_branch_T_ge_ttp", "qv_floor_inactive"):
            if not guards[name]:
                raise AssertionError(f"call {row['call_index_1based']}: guard active: {name}")
        if row["satadj_amount"]["availability_cap_active"]:
            raise AssertionError(
                f"call {row['call_index_1based']}: satadj availability cap became active")
        if not math.isclose(row["satadj_amount"]["amount_after_source_availability_cap_kgkg"],
                            row["satadj_amount"]["c_applied_reconstructed_from_public_receipt_kgkg"],
                            rel_tol=0.0, abs_tol=1.0e-15):
            raise AssertionError(
                f"call {row['call_index_1based']}: local amount does not match receipt")
        if any(abs(value) > 1.0e-12 for value in
               row["endpoint_closure_checks"].values()):
            raise AssertionError(
                f"call {row['call_index_1based']}: reconstructed a+c endpoint "
                "closure exceeded 1e-12")

    sums = five_second["sums_across_captured_satadj_calls"]
    return {
        "study": "PR393 local saturation-adjustment residual derivative check",
        "scope": (
            "Offline scalar thermodynamic reconstruction from exactly two public JSON "
            "receipts. No KDM6 step, RTTOV, optimizer, forecast, NPZ, native artifact, "
            "or source-based microphysics rerun was read or executed."),
        "inputs": {
            "clear_state_result": display_path(clear_path),
            "clear_state_result_sha256": sha256(clear_path),
            "applied_partition_result": display_path(partition_path),
            "applied_partition_result_sha256": sha256(partition_path),
            "analysis_script_sha256": sha256(Path(__file__).resolve()),
        },
        "thermo_constants_from_clear_receipt": thermo,
        "selected_column_from_partition_receipt": partition["selected_column"],
        "formula_contract": {
            "qs_water": "es=psat*exp(log(ttp/T)*xa)*exp(xb*(1-ttp/T)); qs=ep2*es/(p-es)",
            "exact_derivative": "dqs/dT=ep2*p/(p-es)^2 * es*(-xa/T+xb*ttp/T^2)",
            "Dimpl": "1 + ((((L*L)/(Rv*cp))*qs)/(T*T)); each division/multiply is left-associated",
            "Dexact": "1 + (L/cp)*(dqs/dT), holding L and cp fixed at the captured call values",
            "postactivation": "qv_a=qv_in-a; qc_a=qc_in+a; T_a=T_in+(L/cp)*a",
            "residual_prediction": "gplus_linear/g = 1-Dexact/Dimpl for one infinitesimal linearized satadj correction c=g/Dimpl",
            "observed_residual": "(qv_out-qs(T_out))/(qv_a-qs(T_a)); endpoints include finite applied a+c",
        },
        "five_second_calls": reconstructed,
        "published_second_third_reconstruction_checks": comparisons,
        "N1_activation_inventory_arithmetic": {
            "partition": "5s_four_times",
            "call_index_1based": 3,
            "captured_fields": {
                "activation_gate_sw_gt_zero": n1_captured["activation_gate_sw_gt_zero"],
                "sw_percent": n1_captured["sw_percent"],
                "NC_volume_in_m3": nc_in,
                "NCCN_volume_in_m3": nccn_in,
            },
            "reconstructed_fields": {
                "activated_fraction_F": activation_fraction,
                "ncact_m3_s": n1_reconstructed["ncact_m3_s"],
                "applied_b_volume_m3": b_stored,
                "applied_a_mass_kgkg": a_stored,
            },
            "derived_arithmetic": {
                "inventory_activation_threshold_NC_over_NC_plus_NCCN": activation_threshold,
                "activation_fraction_minus_threshold": activation_fraction - activation_threshold,
                "unclamped_b_m3": b_raw,
                "b_from_min_max_equation_m3": b_from_equation,
                "formula": "b=min(max((NC+NCCN)*F-NC,0),NCCN)",
            },
            "interpretation": (
                "The recorded strict sw_percent>0 gate is true, but reconstructed F is "
                "below NC/(NC+NCCN); the lower clamp therefore gives b=0, matching the "
                "stored reconstructed b and a. NC/NCCN inputs were captured volume "
                "inventories; F and b/a are reconstructed, not directly instrumented."),
        },
        "limited_satadj_budget_from_existing_partition_receipt": {
            "a_plus_c_water_transfer_kgkg": sums["a_plus_c_water_transfer_kgkg"],
            "stage_water_closure_cumulative_kgkg": sums["stage_water_closure_cumulative_kgkg"],
            "stage_latent_closure_cumulative_K": sums["stage_latent_closure_cumulative_K"],
            "endpoint_selected_qc_kgkg_dry": five_second["endpoint_selected_qc_kgkg_dry"],
            "budget_scope": five_second["satadj_scope_warning"],
        },
        "interpretation_and_limits": [
            "Dexact is the local derivative of the uncapped water qs formula with L/cp frozen; it does not replace or alter the implemented Dimpl or any physics.",
            "The second and third calls match the published local first-order residual predictions. Their observed endpoint ratios are finite changes and need not equal the linear prediction.",
            "Call 1 applies a much larger finite correction and shows a larger prediction discrepancy; do not use it as a local infinitesimal derivative validation.",
            "Call 4 is near saturation; its ratio is sensitive to float64 endpoint rounding because g is only about 3.18e-9 kg/kg.",
            "The reported water and latent closures are limited to captured satadj stages. They are not a full KDM6/host budget, and this is not a sixth-order or convergence-order result.",
            "The denominator comparison says nothing about RTTOV quality, observations, optimization acceptance, higher derivatives, or physical admissibility beyond these scalar checks.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear-result", type=Path, default=DEFAULT_CLEAR)
    parser.add_argument("--partition-result", type=Path, default=DEFAULT_PARTITION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = analyze(args.clear_result, args.partition_result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({
        "output": str(args.output),
        "input_sha256": {
            "clear_result": result["inputs"]["clear_state_result_sha256"],
            "partition_result": result["inputs"]["applied_partition_result_sha256"],
        },
        "checks": result["published_second_third_reconstruction_checks"],
        "five_second_calls": len(result["five_second_calls"]),
    }, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
