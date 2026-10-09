#!/usr/bin/env python3
"""Reconstruct satadj applied quantities from the cached value-only observer.

This is scalar source-equation arithmetic only. It does not invoke kdm6_step,
coordinator functions, RTTOV, NetCDF, or a forecast; source pin and input hashes
are recorded so reviewers can distinguish captured values from reconstruction.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import argparse

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "graphify-out/pr391-red/selected_column_response_private.json"
CHECKPOINT = ROOT / "graphify-out/pr391-red/selected_column_checkpoint.npz"
OUT_DEFAULT = Path(__file__).resolve().parent / "RESULT.json"
K = 3
RD, RV, CPV, CLIQ, CICE = 287.0, 461.6, 1846.4, 4190.0, 2106.0
T0, TTP, PSAT = 273.15, 273.16, 610.78
EPS, ACTK, SATMAX = 1.0e-15, 0.6, 0.48
ACTR, DENR = 1.5, 1000.0
NCCN_MIN, NCCN_MAX = 1.0e8, 2.0e10


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def thermo_coefficients():
    # Mirror default_thermo_params()'s stepwise f32 coefficient preparation.
    cpv_f, cliq_f, cice_f, rv_f = map(f32, (CPV, CLIQ, CICE, RV))
    ttp_f = f32(TTP)
    xlv0_f, xls_f = f32(2.5e6), f32(2.85e6)
    xa = f32(-f32(cpv_f - cliq_f) / rv_f)
    xb = f32(xa + f32(xlv0_f / f32(rv_f * ttp_f)))
    xai = f32(-f32(cpv_f - cice_f) / rv_f)
    xbi = f32(xai + f32(xls_f / f32(rv_f * ttp_f)))
    return {"xa": xa, "xb": xb, "xai": xai, "xbi": xbi, "ep2": RD / RV}


TH = thermo_coefficients()


def qs_water(t: float, p: float) -> float:
    tr = TTP / max(t, 1.0)
    es = PSAT * math.exp(math.log(tr) * TH["xa"]) * math.exp(TH["xb"] * (1.0 - tr))
    es = min(es, 0.99 * p)
    return max(TH["ep2"] * es / max(p - es, EPS), EPS)


def pcact_mass_constant() -> float:
    # Mirror coordinator.py's f32 operation order, not a double reassociation.
    ax = f32(f32(ACTR) * f32(1.0e-6))
    ax3 = f32(f32(ax * ax) * ax)
    pif = f32(math.pi)
    return f32(f32(f32(4.0 * pif) * f32(DENR)) * ax3)


PC_ACT_K = pcact_mass_constant()


def reconstruct_call(obs: dict, p: float, rho_m: float, dtcld: float) -> dict:
    """Reconstruct a, c, b and NCCN clip from recorded stage endpoints/source."""
    qv = float(obs["qv_in"])
    qc = float(obs["qc_in"])
    t = float(obs["T_in_K"])
    nc = float(obs["nc_volume_in"])
    nccn = float(obs["nccn_volume_in"])
    dend = float(obs["dend_dry_kg_m3"])
    den = float(obs["den_moist_kg_m3"])
    xl = float(obs["xl_J_kg"])
    cpm = float(obs["cpm_J_kg_K"])
    sw_recorded = float(obs["sw_percent_pre_activation"])

    qs_entry = qs_water(t, p)
    sw_calc = (qv / qs_entry - 1.0) * 100.0
    sw_ratio = max(sw_calc / SATMAX, 0.0)
    activated_fraction = min(1.0, max(sw_ratio, EPS) ** ACTK)
    ncact_raw = max((nccn + nc) * activated_fraction - nc, 0.0) / dtcld
    ncact = min(ncact_raw, max(nccn, 0.0) / dtcld)
    if sw_calc <= 0.0:  # exact source gate: sw_percent > 0
        ncact = 0.0
    b = ncact * dtcld  # reconstructed applied NC activation [m^-3]

    pcact_raw = PC_ACT_K * ncact / (3.0 * dend)
    pcact = min(pcact_raw, max(qv, 0.0) / dtcld)
    a = pcact * dtcld  # reconstructed activation water [kg/kg dry]
    activation_mass = pcact * dtcld
    qv_pp = max(qv - pcact * dtcld, 0.0)
    qc_pp = max(qc + pcact * dtcld, 0.0)
    t_pp = t + pcact * xl / cpm * dtcld
    qs_pp = qs_water(t_pp, p)
    denom = 1.0 + xl * xl / (RV * cpm) * qs_pp / (max(t_pp, 1.0) * max(t_pp, 1.0))
    work1 = (max(qv_pp, EPS) - qs_pp) / denom
    if work1 > 0.0:
        pcond = min(work1, max(qv_pp, 0.0)) / dtcld
    elif work1 < 0.0 and qc_pp > 0.0:
        pcond = max(work1, -qc_pp) / dtcld
    else:
        pcond = 0.0
    c = pcond * dtcld  # reconstructed applied pcond transfer [kg/kg dry]
    qv_expected = max(qv_pp - pcond * dtcld, 0.0)
    qc_expected = max(qc_pp + pcond * dtcld, 0.0)
    t_expected = t_pp + pcond * xl / cpm * dtcld

    # Captured NC/NCCN endpoints do not retain nc_evap or pre-clamp NCCN.
    # Here qc_out remains positive for every cached call, excluding full-cloud
    # evaporation; under that source branch e=nc_evap=0 and the floor departure
    # can be reconstructed from the number inventories and the source clamp.
    qc_out = float(obs["qc_out"])
    nc_out = float(obs["nc_volume_out"])
    nccn_out = float(obs["nccn_volume_out"])
    no_complete_evap_supported_by_positive_qc = qc_out > 0.0
    nccn_preclip = max(nccn - b, 0.0)
    nccn_source_clamp = min(max(nccn_preclip, NCCN_MIN), NCCN_MAX)
    C = nccn_source_clamp - nccn_preclip

    qv_out = float(obs["qv_out"])
    t_out = float(obs["T_out_K"])
    water_residual = (qv_out - qv) + (qc_out - qc)
    latent_residual = (t_out - t) - (xl / cpm) * (a + c)
    rho_d_expected = rho_m / (1.0 + qv)
    return {
        "dtcld_s_f32": f32(dtcld),
        "captured": {
            "sw_percent": sw_recorded,
            "activation_gate_sw_gt_zero": bool(obs["activation_gate_sw_gt_zero"]),
            "qv_qc_T_in": [qv, qc, t], "qv_qc_T_out": [qv_out, qc_out, t_out],
            "NC_NCCN_volume_in_m3": [nc, nccn], "NC_NCCN_volume_out_m3": [nc_out, nccn_out],
            "rho_moist_kg_m3": den, "rho_dry_kg_m3": dend,
            "xl_J_kg": xl, "cpm_J_kg_K": cpm,
        },
        "reconstructed_from_source_equations": {
            "qv_minus_qs_entry_kgkg": qv - qs_entry,
            "qv_minus_qs_from_sw_kgkg": qv - qv / (1.0 + sw_recorded / 100.0),
            "qv_minus_qs_sw_formula_error": sw_calc - sw_recorded,
            "rho_dry_from_fixed_rho_m_and_entry_qv_kg_m3": rho_d_expected,
            "rho_dry_capture_error_kg_m3": dend - rho_d_expected,
            "activated_fraction": activated_fraction,
            "ncact_m3_s": ncact,
            "a_pcact_applied_mass_kgkg": activation_mass,
            "c_pcond_applied_mass_kgkg": c,
            "pcond_rate_kgkg_s": pcond,
            "b_ncact_applied_number_m3": b,
            "NCCN_preclip_m3_if_no_complete_evap": nccn_preclip,
            "C_final_reservoir_clip_m3_if_no_complete_evap": C,
            "complete_evaporation_excluded_by_positive_qc_out": no_complete_evap_supported_by_positive_qc,
            "formula_endpoint_errors_qv_qc_T": [qv_expected - qv_out, qc_expected - qc_out, t_expected - t_out],
        },
        "captured_stage_closures": {
            "delta_qv_plus_delta_qc_kgkg": water_residual,
            "delta_T_minus_xl_over_cpm_times_a_plus_c_K": latent_residual,
        },
        "unit_basis": {
            "qv_qc_a_c": "kg water / kg dry air",
            "T": "K",
            "NC_NCCN_b_C": "number / m^3 in coordinator stage",
            "state_boundary_NC_NCCN": "number / kg dry air; must not sum directly with stage volume inventory",
            "density": "rho_moist and rho_dry in kg / m^3; rho_dry recalculated at each kdm6_step entry",
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(f"refusing to overwrite existing result: {args.output}")
    cached = json.loads(INPUT.read_text())
    z = np.load(CHECKPOINT)
    p = float(z["p_center_native_bottomup_Pa"][K])
    rho_m = float(z["rho_m_forcing_native_bottomup_kg_m3"][K])
    dt_by_name = {"20s_once": 20.0, "10s_twice": 10.0, "5s_four_times": 5.0}
    partitions = []
    for part in cached["equal_final_time_fixed_forcing"]["runs"]:
        dt = dt_by_name[part["name"]]
        calls = [reconstruct_call(c, p, rho_m, dt) for c in part["satadj_selected_layer_calls"]]
        sums = {}
        for key in ("a_pcact_applied_mass_kgkg", "c_pcond_applied_mass_kgkg",
                    "b_ncact_applied_number_m3", "C_final_reservoir_clip_m3_if_no_complete_evap"):
            sums[key] = sum(c["reconstructed_from_source_equations"][key] for c in calls)
        sums["a_plus_c_water_transfer_kgkg"] = sums["a_pcact_applied_mass_kgkg"] + sums["c_pcond_applied_mass_kgkg"]
        sums["stage_water_closure_cumulative_kgkg"] = sum(c["captured_stage_closures"]["delta_qv_plus_delta_qc_kgkg"] for c in calls)
        sums["stage_latent_closure_cumulative_K"] = sum(c["captured_stage_closures"]["delta_T_minus_xl_over_cpm_times_a_plus_c_K"] for c in calls)
        rebases = []
        for i in range(len(calls) - 1):
            old, new = calls[i], calls[i + 1]
            d0 = old["captured"]["rho_dry_kg_m3"]
            d1 = new["captured"]["rho_dry_kg_m3"]
            for species, idx in (("NC", 0), ("NCCN", 1)):
                out_vol = old["captured"]["NC_NCCN_volume_out_m3"][idx]
                in_vol = new["captured"]["NC_NCCN_volume_in_m3"][idx]
                expected = out_vol * d1 / d0
                rebase = expected - out_vol
                rebases.append({"between_calls": [i, i+1], "species": species,
                                "previous_volume_out_m3": out_vol,
                                "next_volume_in_m3": in_vol,
                                "density_only_rebased_volume_m3": expected,
                                "observed_minus_density_rebase_m3": in_vol - expected,
                                "basis_change_volume_m3": rebase,
                                "method": "previous dry-specific boundary = previous volume / previous entry rho_d; next stage volume = boundary * next entry rho_d"})
        partitions.append({"partition": part["name"], "physical_dt_s": dt,
                           "source_dtcld_f32_s": f32(dt),
                           "activation_gate_history_sw_gt_zero": [c["captured"]["activation_gate_sw_gt_zero"] for c in calls],
                           "calls": calls, "sums_across_captured_satadj_calls": sums,
                           "intercall_density_rebases": rebases,
                           "endpoint_selected_qc_kgkg_dry": part["output"]["selected_layer_output"]["qc"],
                           "satadj_scope_warning": "These sums cover only captured coordinator satadj stages; not full KDM M, host budget, or external source/sink ledger."})
    result = {
        "study": "Offline applied satadj partition reconstruction from cached Red value-only observer",
        "scope": "No KDM6/RTTOV/forecast/model run; uses existing selected_column_response_private.json, checkpoint NPZ, and pinned source equations only.",
        "selected_column": {"k_bottomup_zero_based": K, "p_Pa": p, "rho_moist_forcing_kg_m3": rho_m},
        "captured_vs_reconstructed": {
            "directly_captured_per_call": ["dtcld indirectly known from declared fixed-dt partition and runtime loops=1", "sw_percent and strict gate", "qv/qc/T endpoints", "NC/NCCN volume endpoints", "den/dend", "xl/cpm"],
            "reconstructed_not_instrumented": ["qs and qv-qs gap", "ncact and applied b", "pcact rate and applied mass a", "pcond rate and applied amount c", "pre-clamp NCCN and reservoir clip C", "water/latent residuals from endpoints and source coefficients"],
            "not_claimed_as_direct_measurement": ["pcact or pcond rates", "pcond branch trace", "nc_evap", "complete-evap trace", "full dry-number ledger or S17 budget"],
        },
        "method": {
            "pcond_equation": "source satadj.py:78-96 evaluated on post-pcact state; c=pcond*dtcld; strict source operation grouping",
            "activation_equation": "coordinator.py:1974-2017; fraction=min(1,max(sw_percent/0.48,EPS)^0.6), strict sw_percent>0; source number-rate cap then b=ncact*dtcld",
            "NCCN_clip": "coordinator.py:2022-2025; no full-evap branch in these calls because observed qc_out>0; C=clamp(NCCN_in-b,1e8,2e10)-(NCCN_in-b)",
            "dry_density": "runtime.py:535-557; rho_dry=rho_m/(1+qv_entry) is recomputed at each external kdm6_step call, and returned State numbers are per kg dry air",
            "dtcld": "runtime.py:608-612; compute_loops_max(dt,DTCLDCR) is 1 for 5/10/20 s, dtcld is float32(dt/loops)",
            "pcond_mass_constant": PC_ACT_K,
            "nccn_min_volume_m3": NCCN_MIN,
            "nccn_max_volume_m3": NCCN_MAX,
        },
        "partition_summary": partitions,
        "source_sha256": {name: sha(ROOT / name) for name in (
            "oracle/kdm6/runtime.py", "oracle/kdm6/coordinator.py", "oracle/kdm6/thermo.py",
            "oracle/kdm6/satadj.py", "oracle/kdm6/constants.py", "oracle/kdm6/fconst.py")},
        "cached_input_sha256": {"selected_column_response_private.json": sha(INPUT),
                                 "selected_column_checkpoint.npz": sha(CHECKPOINT)},
        "analysis_script_sha256": sha(Path(__file__)),
        "result_limits": [
            "Activation b and clip C are source-reconstructed from captured stage inventories, not separately instrumented rates.",
            "The inferred no-complete-evap branch is validated for this record by positive observed qc_out at every call; no generic claim is made.",
            "Intercall volume rebases are density-coordinate changes, not microphysical activation/clip amounts.",
            "No universal number conservation, external CCN source, full KDM water/heat budget, or convergence order is inferred.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"result": str(args.output), "partitions": [
        {"partition": p["partition"], "b_m3": p["sums_across_captured_satadj_calls"]["b_ncact_applied_number_m3"],
         "C_m3": p["sums_across_captured_satadj_calls"]["C_final_reservoir_clip_m3_if_no_complete_evap"],
         "a_kgkg": p["sums_across_captured_satadj_calls"]["a_pcact_applied_mass_kgkg"],
         "c_kgkg": p["sums_across_captured_satadj_calls"]["c_pcond_applied_mass_kgkg"],
         "gate_history": p["activation_gate_history_sw_gt_zero"]} for p in partitions]}, indent=2))


if __name__ == "__main__":
    main()
