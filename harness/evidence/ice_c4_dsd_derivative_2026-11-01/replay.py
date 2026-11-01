#!/usr/bin/env python3
"""Branch-interior AD checks for the recorded C4/DSD saturation cases."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import torch

from oracle.kdm6 import constants as c
from oracle.kdm6 import fconst
from oracle.kdm6.coordinator import CoordinatorState, apply_dsd_number_limiters_torch
from oracle.kdm6.sensitivity_diagnostics import SensitivityTrace
from oracle.kdm6.thermo import compute_qs_ice, default_thermo_params

PARENT = importlib.import_module("harness.evidence.ice_c4_dsd_boundary_2026-11-01.replay")
NATIVE = importlib.import_module("harness.evidence.interior_profile_jvp_2026-10-31.replay")
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
DIRECTION = 1e-12  # qv per unit dimensionless parameter, first column top WRF level
STEP = 0.01
OUTPUT_FIELDS = ("qi", "ni", "qv", "th")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_sources():
    PARENT.verify_sources()
    manifest = json.loads((ROOT / "source_manifest.json").read_bytes())
    for relative, expected in manifest.items():
        path = REPO / relative
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                "source digest " + relative)


def _evaluate(qv, *, observed, diagnose=True):
    state, forcing, _, _ = PARENT.SUPPLY.coherent_state(0.0, qv=qv)
    if observed:
        capture = PARENT.C4Capture()
        output, trace, _, c3_records, c4_records = capture.run(state, forcing)
        require(len(c3_records) == len(c4_records) == 1, "one C3/C4 call")
        if diagnose:
            c3 = PARENT.PARENT.inspect_producer(c3_records[0])
            c4 = PARENT.reconstruct_pidep(c4_records[0])
            branch = {
                "C3_outer": bool(c3["outer"][0, -1]),
                "C3_inner": bool(c3["inner"][0, -1]),
                "C3_ifsat": bool(c3["ifsat"][0, -1]),
                "C4_active": bool(c4["active"][0, -1]),
                "C4_raw_negative": bool(c4["raw"][0, -1] < 0),
                "C4_winners": PARENT.cap_selection(c4),
                "DSD_masks": PARENT.dsd_ice(trace)["masks"],
            }
        else:
            branch = None
    else:
        output, trace, _ = PARENT.PARENT.run_plain(state, forcing, normalized=False)
        branch = None
    values = torch.stack(tuple(getattr(output, name)[0, -1] for name in OUTPUT_FIELDS))
    return values, trace, branch


def _values(qv, observed):
    return _evaluate(qv, observed=observed, diagnose=False)[0]


def branch_direction(offset):
    """Differentiate the coherent qv/rho family inside one selected branch."""
    require(offset in (-1e-12, 1e-12), "strict-sided saturation reference")
    state, _, _, _ = PARENT.SUPPLY.coherent_state(offset)
    q0 = state.qv
    seed = torch.zeros_like(q0)
    seed[0, -1] = DIRECTION
    nominal_delta = STEP * DIRECTION
    q_plus = q0 + STEP * seed
    q_minus = q0 - STEP * seed
    actual_plus = float(q_plus[0, -1] - q0[0, -1])
    actual_minus = float(q0[0, -1] - q_minus[0, -1])
    actual_width = float(q_plus[0, -1] - q_minus[0, -1])
    require(actual_width > 0 and actual_plus > 0 and actual_minus > 0,
            "represented qv perturbation")

    primal, jvp = torch.autograd.functional.jvp(
        lambda qv: _values(qv, False), q0, seed)
    observed, observed_jvp = torch.autograd.functional.jvp(
        lambda qv: _values(qv, True), q0, seed)
    require(PARENT.PARENT.bits_equal(primal, observed) and
            PARENT.PARENT.bits_equal(jvp, observed_jvp),
            "C3/C4 observation JVP noninterference")
    base, base_trace, base_branch = _evaluate(q0, observed=True)
    plus, plus_trace, plus_branch = _evaluate(q_plus, observed=True)
    minus, minus_trace, minus_branch = _evaluate(q_minus, observed=True)
    require(PARENT.PARENT.bits_equal(base, primal) and
            base_trace.subcycles == plus_trace.subcycles == minus_trace.subcycles and
            base_trace.signature() == plus_trace.signature() == minus_trace.signature() and
            base_branch == plus_branch == minus_branch,
            "selected branch and trace topology at represented endpoints")
    require((not base_branch["C3_outer"] and base_branch["C4_active"] and
             base_branch["C4_raw_negative"] and base_branch["C4_winners"] == ["remaining"])
            if offset < 0 else
            (base_branch["C3_outer"] and base_branch["C3_ifsat"] and
             not base_branch["C4_active"] and
             base_branch["C4_winners"] == ["inactive_ifsat"]),
            "side-specific C3/C4 branch")
    fd_nominal = (plus - minus) / (2.0 * STEP)
    fd_actual = DIRECTION * (plus - minus) / actual_width
    require(bool(torch.isfinite(fd_actual).all()) and
            bool(torch.isfinite(jvp).all()) and float(jvp[0]) != 0.0,
            "finite nonzero ice-mass direction")
    require(abs(float(fd_actual[0] - jvp[0])) <= 1e-6 * abs(float(jvp[0])),
            "ice-mass FD-JVP within represented-input comparison")
    if offset > 0:
        require(abs(float(fd_actual[1] - jvp[1])) <= 1e-8 * abs(float(jvp[1])) and
                float(jvp[1]) != 0.0,
                "above-saturation ice-number FD-JVP")
    spacing = torch.nextafter(base, torch.full_like(base, float("inf"))) - base

    # The selected qv/rho family is differentiated by autograd. The detached
    # capture is evidence of the consumed values, never a gradient substitute.
    return {
        "reference_offset": offset,
        "input": {"field": "qv", "column_zero_based": 0,
                  "wrf_level_zero_based": q0.shape[-1] - 1,
                  "baseline": float(q0[0, -1]),
                  "direction_per_unit_parameter": DIRECTION,
                  "parameter_step": STEP, "nominal_one_sided_delta": nominal_delta,
                  "actual_plus": float(q_plus[0, -1]),
                  "actual_minus": float(q_minus[0, -1]),
                  "represented_plus_delta": actual_plus,
                  "represented_minus_delta": actual_minus,
                  "represented_width": actual_width,
                  "midpoint_offset_from_baseline": (actual_plus - actual_minus) / 2.0},
        "branch": base_branch,
        "outputs": {
            name: {"baseline": float(base[index]), "jvp": float(jvp[index]),
                   "fd_nominal": float(fd_nominal[index]),
                   "fd_actual_secant": float(fd_actual[index]),
                   "nominal_minus_jvp": float(fd_nominal[index] - jvp[index]),
                   "actual_minus_jvp": float(fd_actual[index] - jvp[index]),
                   "actual_output_signal": float(plus[index] - minus[index]),
                   "baseline_output_binary64_spacing": float(spacing[index])}
            for index, name in enumerate(OUTPUT_FIELDS)
        },
        "observer_jvp_raw_bits_equal": True,
        "checked_branch_and_trace_topology_equal": True,
    }


def _ice_state(qi, ni):
    z = torch.zeros_like(qi)
    return CoordinatorState(qv=z, qc=z, qr=z, qs=z, qg=z, qi=qi,
                            nc=z, nr=z, ni=ni, brs=z,
                            t=torch.full_like(qi, 260.0))


def dsd_local_derivative():
    """Evaluate the actual DSD helper at the exact case's recorded input."""
    state, forcing, _, _ = PARENT.SUPPLY.coherent_state(0.0)
    _, trace, _, _, _ = PARENT.C4Capture().run(state, forcing)
    stage = trace.by_name("dsd_limiter")[0]
    recorded = PARENT.dsd_ice(trace)
    require(recorded["masks"]["ice_active"] and
            recorded["masks"]["ice_final_ncmin_gate"] and
            recorded["masks"]["ice_too_large"] and
            not recorded["masks"]["ice_too_small"],
            "recorded strict ice maximum-slope snap")
    qi0 = stage.state_in.qi[0, -1].detach().reshape(1, 1)
    ni0 = stage.state_in.ni[0, -1].detach().reshape(1, 1)
    den = stage.operands["ice_den"][0, -1].detach().reshape(1, 1)
    ncmin = torch.full_like(qi0, 10.0)
    require(float(qi0) > 1e-15 and float(ni0) > float(ncmin) and
            recorded["ice_lamda"] > c.LAMDAIMAX and
            float(ni0 * (1 - 1e-3)) > recorded["ice_n_at_max"] * (1 + 1e-3),
            "strict DSD branch margin across local differences")

    def calculate(qi, ni, *, diagnostic_trace=None):
        return apply_dsd_number_limiters_torch(
            _ice_state(qi, ni), den, ncmin_tensor=ncmin,
            diagnostic_trace=diagnostic_trace).ni

    def endpoint(qi, ni):
        endpoint_trace = SensitivityTrace()
        value = calculate(qi, ni, diagnostic_trace=endpoint_trace)
        decision = endpoint_trace.by_name("dsd_limiter")[0]
        labels = decision.metadata["branch_labels"]
        masks = {name: bool(decision.branch[index, 0, 0])
                 for index, name in enumerate(labels) if name.startswith("ice_")}
        require(masks == recorded["masks"], "DSD branch at represented FD endpoint")
        return value

    actual = calculate(qi0, ni0)
    require(PARENT.PARENT.bits_equal(actual, stage.state_out.ni[0, -1].reshape(1, 1)),
            "isolated helper reproduces actual DSD result")
    qi = qi0.clone().requires_grad_(True)
    ni = ni0.clone().requires_grad_(True)
    grad_qi, grad_ni = torch.autograd.grad(calculate(qi, ni).sum(), (qi, ni))
    dq = qi0
    dn = ni0
    _, tangent_qi = torch.func.jvp(calculate, (qi0, ni0), (dq, torch.zeros_like(dn)))
    _, tangent_ni = torch.func.jvp(calculate, (qi0, ni0), (torch.zeros_like(dq), dn))
    coefficient = (c.LAMDAIMAX ** c.DMI) / fconst.PIDNI
    expected_qi = den * coefficient
    require(float(grad_ni[0, 0]) == float(tangent_ni[0, 0]) == 0.0 and
            torch.allclose(grad_qi, expected_qi, rtol=1e-15, atol=0) and
            torch.allclose(tangent_qi, actual, rtol=1e-15, atol=0),
            "DSD independent snap differential")
    step = 1e-3
    fd_qi = (endpoint(qi0 * (1 + step), ni0) -
             endpoint(qi0 * (1 - step), ni0)) / (2 * step)
    fd_ni = (endpoint(qi0, ni0 * (1 + step)) -
             endpoint(qi0, ni0 * (1 - step))) / (2 * step)
    require(torch.allclose(fd_qi, actual, rtol=1e-12, atol=0) and
            float(fd_ni[0, 0]) == 0.0,
            "DSD branch-preserving directional differences")
    return {"qi_before": float(qi0), "ni_before": float(ni0),
            "den_fixed": float(den), "ni_after": float(actual),
            "partial_ni_out_by_ni_in": float(grad_ni),
            "relative_qi_jvp": float(tangent_qi),
            "relative_qi_fd": float(fd_qi),
            "relative_qi_sensitivity": float(tangent_qi / actual),
            "relative_ni_jvp": float(tangent_ni),
            "relative_ni_fd": float(fd_ni),
            "branch": recorded["masks"],
            "fd_endpoint_ice_masks_equal": True}


def native_candidate_preflight():
    """Reconstruct saved candidates; this cannot attest an executed C3/C4 call."""
    metadata, data = NATIVE.load_fixture()
    prep = metadata["prep_configuration"]
    pressure = NATIVE._f32_sum(data["P"], data["PB"])
    rows = {}
    for native_k in (21, 23):
        index = native_k - 1
        qv = float(data["QVAPOR"][index])
        p = float(pressure[index])
        temperature = ((float(data["THM_2"][index]) + prep["t0"]) /
                       (1.0 + prep["alpha"] * qv) *
                       (p / prep["p0"]) ** prep["kappa"])
        qs = float(compute_qs_ice(
            torch.tensor([[temperature]], dtype=torch.float64),
            torch.tensor([[p]], dtype=torch.float64),
            params=default_thermo_params())[0, 0])
        require(temperature < 273.15 and float(data["QICE"][index]) > 0 and
                (qv < qs if native_k == 21 else qv > qs),
                "native checkpoint candidate side")
        rows[str(native_k)] = {
            "native_ijk_1based": [*metadata["native_ijk_1based"][:2], native_k],
            "rttov_row_0based": metadata["fixed_upper_count"] + 39 - native_k,
            "temperature_k_reconstructed": temperature,
            "pressure_pa_f32_sum_widened": p,
            "qv_checkpoint": qv,
            "qs_ice_reconstructed": qs,
            "ice_relative_humidity_reconstructed": qv / qs,
            "qv_minus_qs_ice_reconstructed": qv - qs,
            "qi_checkpoint": float(data["QICE"][index]),
        }
    return {"evidence_class": "stored checkpoint reconstruction, not a same-call C3/C4/DSD trace",
            "fixture_sha256": metadata["fixture_sha256"],
            "candidates": rows,
            "same_call_required": ["executed build and inputs", "dt and selected subcycles",
                                   "consumed T/QV/P/rho and saturation stage",
                                   "C3 producer and C4 signed candidates",
                                   "limited rates and state update", "final DSD pre/post QI/NI"]}


def main():
    torch.set_num_threads(1)
    verify_sources()
    below = branch_direction(-1e-12)
    above = branch_direction(1e-12)
    local = dsd_local_derivative()
    native = native_candidate_preflight()
    print(json.dumps({
        "status": "ICE_C4_DSD_DERIVATIVE_REPLAY_PASSED",
        "scientific_status": "INCONCLUSIVE",
        "scope": "synthetic coherent f64 public runtime and isolated final DSD at actual recorded operands; no native host or RTTOV",
        "below_saturation": below, "above_saturation": above,
        "exact_saturation_dsd_local": local,
        "native_candidate_preflight": native,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
