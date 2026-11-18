#!/usr/bin/env python3
"""Inspect actual C3 nucleation operands in the PR #504 synthetic full runtime."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch

from harness.ice_chain_applied_budget import IceChainAppliedCapture
from harness.tests.test_ice_chain_applied_budget import _inputs
from oracle.kdm6 import cold as cold_module
from oracle.kdm6 import constants as c
from oracle.kdm6.runtime import _kdm6_pure, make_parameters
from oracle.kdm6.sensitivity_diagnostics import SensitivityTrace
from oracle.kdm6.state import Forcing, State

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
H = 1e-4
OUTPUT_FIELDS = ("qi", "ni", "qv", "th")
OUTPUT_SCALES = {"qi": 1e8, "ni": 1.0, "qv": 1e3, "th": 1.0}


def require(value, message):
    if not value:
        raise ValueError(message)


def check_sources():
    manifest = json.loads((ROOT / "source_manifest.json").read_bytes())
    for relative, expected in manifest.items():
        path = REPO / relative
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                "source digest " + relative)


def bits_equal(left, right):
    if left.dtype != right.dtype or left.shape != right.shape:
        return False
    integer = torch.int32 if left.dtype == torch.float32 else torch.int64
    return torch.equal(left.contiguous().view(integer), right.contiguous().view(integer))


def build_state(dtype=torch.float64):
    selected, forcing, _mask, _params, _work = _inputs(dtype)

    def reverse(value):
        return value.flip(-1)

    state = State(
        th=reverse(selected.t), qv=reverse(selected.qv),
        qc=reverse(selected.qc), qr=reverse(selected.qr),
        qi=reverse(selected.qi), qs=reverse(selected.qs),
        qg=reverse(selected.qg), nccn=torch.full_like(selected.qi, 1e8),
        nc=reverse(selected.nc), ni=reverse(selected.ni),
        nr=reverse(selected.nr), bg=reverse(selected.brs),
    )
    physical = Forcing(
        rho=reverse(forcing.den), pii=torch.ones_like(forcing.den),
        p=reverse(forcing.p), delz=reverse(forcing.delz),
    )
    return state, physical


class ProducerCapture:
    def __init__(self):
        self.records = []

    def run(self, state, forcing, *, normalized):
        original = cold_module.ice_nucleation_torch

        def intercept(*args, **kwargs):
            result = original(*args, **kwargs)
            self.records.append({
                "inputs": tuple(value.detach().clone() for value in args),
                "params": kwargs["params"],
                "dtcld": float(kwargs["dtcld"]),
                "output": type(result)(*(value.detach().clone() for value in result)),
            })
            return result

        trace = SensitivityTrace()
        ice = IceChainAppliedCapture()
        with patch.object(cold_module, "ice_nucleation_torch", intercept):
            output = _kdm6_pure(
                state, forcing, make_parameters(), 1.0,
                diagnostic_trace=trace, sed_substep_fns=(None, ice),
                normalize_ice_handoff=normalized,
            )
        return output, trace, ice


def run_plain(state, forcing, *, normalized, trace=False, ice=False):
    record = SensitivityTrace() if trace else None
    capture = IceChainAppliedCapture() if ice else None
    output = _kdm6_pure(
        state, forcing, make_parameters(), 1.0,
        diagnostic_trace=record,
        sed_substep_fns=(None, capture) if capture is not None else None,
        normalize_ice_handoff=normalized,
    )
    return output, record, capture


def source_minud(params):
    """Independent scalar binary32 evaluation of the Fortran-shaped mass seed."""
    pi = np.float32(math.pi)
    radius = np.float32(params.rinud)
    density = np.float32(params.deni)
    cubic_radius = np.float32(np.float32(radius * radius) * radius)
    return float(np.float32(np.float32(np.float32(np.float32(4.0 / 3.0) * pi) *
                                             density) * cubic_radius))


def inspect_producer(record):
    supcol, supsat, rh, prevp, ni, den = record["inputs"]
    params, dt = record["params"], record["dtcld"]
    result = record["output"]
    minud = source_minud(params)
    cold_super = (supcol > params.supcol_threshold) & (supsat > 0)
    high_rh = rh > params.rh_ice_threshold
    outer = cold_super | high_rh
    nid_raw = params.cooper_a * torch.exp(params.cooper_b * supcol) * params.cooper_unit
    nid = torch.clamp(nid_raw, min=0.0, max=params.nid_max)
    inner = nid > ni
    den_safe = torch.clamp(den, min=c.QCRMIN)
    satdt = supsat / dt
    supice = satdt - prevp
    deficit = (nid - ni) / dt / den_safe * minud
    half = 0.5 * satdt
    candidate = torch.minimum(torch.minimum(deficit, half), supice)
    active = outer & inner
    pinud = torch.where(active, candidate, torch.zeros_like(candidate))
    ninud = torch.where(active, pinud * den_safe / minud, torch.zeros_like(candidate))
    ifsat = outer & (torch.abs(prevp + pinud) >= torch.abs(satdt))
    require(bits_equal(pinud, result.pinud) and bits_equal(ninud, result.ninud) and
            torch.equal(ifsat, result.ifsat), "C3 producer operand replay")
    return {
        "supcol": supcol, "supsat_ice": supsat, "rh_ice": rh,
        "prevp": prevp, "ni_in": ni, "den": den,
        "minud": minud, "cold_super": cold_super, "high_rh": high_rh,
        "outer": outer, "nid_raw": nid_raw, "nid": nid,
        "inner": inner, "satdt": satdt, "supice": supice,
        "deficit_mass_rate": deficit, "half_satdt": half,
        "pinud": result.pinud, "ninud": result.ninud, "ifsat": result.ifsat,
    }


def first_column_top(value):
    return value[0].flip(-1).detach().cpu().tolist()


def inspect_runtime_variant(state, forcing, *, normalized):
    probe = ProducerCapture()
    output, trace, ice = probe.run(state, forcing, normalized=normalized)
    plain, _, _ = run_plain(state, forcing, normalized=normalized)
    for name in State._fields:
        require(bits_equal(getattr(output, name), getattr(plain, name)),
                "instrumentation noninterference " + name)
    require(len(probe.records) == 1 and len(ice.records) == 1 and
            len(trace.subcycles) == 1, "one runtime C3/ice/subcycle call")
    topology = trace.subcycles[0]
    require(topology["main_by_column"] == [1.0, 1.0] and
            topology["ice_by_column"] == [1.0, 1.0], "selected runtime mstep")
    require(torch.count_nonzero(ice.records[0].qi_after[0]) ==
            (0 if not normalized else 3), "first-column post-sed QI class")
    require(torch.all(ice.records[0].number.after[0] > 0), "post-sed NI positive")
    start = trace.by_name("d1_melt")[0].state_in
    require(bits_equal(start.qi[0].flip(-1), ice.records[0].qi_after[0]) and
            bits_equal(start.ni[0].flip(-1), ice.records[0].number.after[0]),
            "ice substep to microphysics handoff")
    diagnostics = inspect_producer(probe.records[0])
    require(torch.all(diagnostics["outer"][0]) and
            torch.all(diagnostics["inner"][0]) and
            torch.all(diagnostics["pinud"][0] > 0) and
            torch.all(diagnostics["ninud"][0] > 0), "actual target-deficit branch")
    require(torch.all(diagnostics["deficit_mass_rate"][0] <
                      diagnostics["half_satdt"][0]) and
            torch.all(diagnostics["deficit_mass_rate"][0] <
                      diagnostics["supice"][0]), "uncapped target deficit")
    cold_raw = trace.by_name("cold")[0].rates
    cold_limited = trace.by_name("cold_limited")[0].rates
    require(bits_equal(diagnostics["pinud"], cold_raw.pinud) and
            bits_equal(diagnostics["ninud"], cold_raw.ninud),
            "C3 producer to cold rates")
    require(bits_equal(cold_raw.pinud, cold_limited.pinud) and
            bits_equal(cold_raw.ninud, cold_limited.ninud),
            "uncapped actual C3 rates in this fixture")
    return output, trace, diagnostics, {
        "normalized_first_handoff": normalized,
        "subcycle_topology": topology,
        "post_sed_qi": ice.records[0].qi_after[0].detach().tolist(),
        "post_sed_ni": ice.records[0].number.after[0].detach().tolist(),
        "post_micro_qi": first_column_top(output.qi),
        "post_micro_ni": first_column_top(output.ni),
        "C3": {name: first_column_top(diagnostics[name]) for name in (
            "supcol", "supsat_ice", "rh_ice", "prevp", "ni_in", "den",
            "nid_raw", "nid", "satdt", "supice", "deficit_mass_rate",
            "half_satdt", "pinud", "ninud")},
        "C3_branch": {name: first_column_top(diagnostics[name]) for name in (
            "cold_super", "high_rh", "outer", "inner", "ifsat")},
        "minud": diagnostics["minud"],
    }


def isolated_branches(actual):
    """Direct C3 input contrasts; these are not full-runtime states."""
    p = actual["params"]
    sup, supsat, rh, prevp, ni, den = actual["inputs"]
    def top(value):
        return value[0, -1].reshape(1, 1)

    sup0, sat0, rh0, prev0, ni0, den0 = map(top, (sup, supsat, rh, prevp, ni, den))
    base = cold_module.ice_nucleation_torch(
        sup0, sat0, rh0, prev0, ni0, den0, params=p, dtcld=1.0)
    minud = source_minud(p)
    nid0 = p.cooper_a * math.exp(p.cooper_b * float(sup0)) * p.cooper_unit
    nid_equal = torch.clamp(
        p.cooper_a * torch.exp(p.cooper_b * sup0) * p.cooper_unit,
        min=0.0, max=p.nid_max)
    raw0 = (nid0 - float(ni0)) / float(den0) * minud
    qs_ref = float(sat0) / (float(rh0) - 1.0)
    weak_sat = torch.full_like(sat0, raw0)
    weak_rh = torch.full_like(rh0, 1.0 + raw0 / qs_ref)
    cases = {
        "target_deficit": (sup0, sat0, rh0, prev0, ni0, den0),
        "half_supply_cap": (sup0, weak_sat, weak_rh, torch.zeros_like(prev0), ni0, den0),
        "remaining_supply_cap": (sup0, weak_sat, weak_rh, 0.8 * weak_sat, ni0, den0),
        "outer_inactive": (torch.full_like(sup0, 8.0), weak_sat,
                           torch.full_like(rh0, 1.01), torch.zeros_like(prev0), ni0, den0),
        "outer_inactive_exhausted_prev": (
            torch.full_like(sup0, 8.0), sat0,
            torch.full_like(rh0, 1.01), 2.0 * sat0, ni0, den0),
        "target_exceeded": (sup0, sat0, rh0, prev0,
                            torch.full_like(ni0, nid0 + 1.0), den0),
        "target_equal": (sup0, sat0, rh0, prev0, nid_equal, den0),
        "inner_inactive_exhausted_prev": (
            sup0, sat0, rh0, 2.0 * sat0,
            torch.full_like(ni0, nid0 + 1.0), den0),
    }
    results = {}
    for name, inputs in cases.items():
        output = cold_module.ice_nucleation_torch(*inputs, params=p, dtcld=1.0)
        record = {"inputs": inputs, "params": p, "dtcld": 1.0, "output": output}
        derived = inspect_producer(record)
        if name == "target_equal":
            require(bits_equal(derived["nid"], inputs[4]) and
                    bool(derived["outer"][0, 0]) and
                    not bool(derived["inner"][0, 0]) and
                    float(output.pinud[0, 0]) == float(output.ninud[0, 0]) == 0.0,
                    "exact C3 target equality")
        active = bool((derived["outer"] & derived["inner"])[0, 0])
        candidates = {key: float(derived[key][0, 0]) for key in (
            "deficit_mass_rate", "half_satdt", "supice")}
        winner = min(candidates, key=candidates.get) if active else "inactive"
        if active:
            require(all(candidates[winner] < value for key, value in candidates.items()
                        if key != winner), "isolated C3 cap tie " + name)
        results[name] = {
            "active": active, "cap_winner": winner,
            "candidates": candidates,
            "pinud": float(output.pinud[0, 0]),
            "ninud": float(output.ninud[0, 0]),
            "ifsat": bool(output.ifsat[0, 0]),
        }
    require(results["target_deficit"]["cap_winner"] == "deficit_mass_rate" and
            results["half_supply_cap"]["cap_winner"] == "half_satdt" and
            results["remaining_supply_cap"]["cap_winner"] == "supice" and
            not results["outer_inactive"]["active"] and
            not results["target_exceeded"]["active"] and
            not results["target_equal"]["active"] and
            not results["outer_inactive_exhausted_prev"]["ifsat"] and
            results["inner_inactive_exhausted_prev"]["ifsat"],
            "isolated C3 branch sweep")
    require(bits_equal(base.pinud, actual["output"].pinud[0, -1].reshape(1, 1)) and
            bits_equal(base.ninud, actual["output"].ninud[0, -1].reshape(1, 1)),
            "isolated actual producer baseline")
    return results


def direct_nucleation_derivative(actual):
    """For the uncapped C3 branch, compare its exact scalar tangent to JVP/FD."""
    p = actual["params"]
    sup, supsat, rh, prevp, ni, den = actual["inputs"]
    def one(value):
        return value[0, -1].reshape(1, 1)

    sup, supsat, rh, prevp, ni, den = map(one, (sup, supsat, rh, prevp, ni, den))
    def evaluate(number):
        out = cold_module.ice_nucleation_torch(
            sup, supsat, rh, prevp, number, den, params=p, dtcld=1.0)
        return number + out.ninud, out.pinud
    direction = torch.ones_like(ni)
    primal, tangent = torch.autograd.functional.jvp(evaluate, ni, direction)
    plus = evaluate(ni + H * direction)
    minus = evaluate(ni - H * direction)
    fd = tuple((pval - mval) / (2 * H) for pval, mval in zip(plus, minus))
    expected_mass = -source_minud(p) / float(den)
    require(abs(float(tangent[0])) <= 2e-12 and abs(float(fd[0])) <= 2e-10,
            "uncapped C3 number target tangent")
    require(math.isclose(float(tangent[1]), expected_mass, rel_tol=2e-12),
            "uncapped C3 mass tangent")
    require(math.isclose(float(fd[1]), expected_mass, rel_tol=1e-8),
            "uncapped C3 mass finite difference")
    return {"number_after_nucleation": float(primal[0]),
            "number_jvp": float(tangent[0]), "number_fd": float(fd[0]),
            "mass_rate_jvp": float(tangent[1]), "mass_rate_fd": float(fd[1])}


def runtime_derivatives(state, forcing, *, normalized):
    """Selected QI/NI input directions through the full public runtime map."""
    def packed(qi, ni, *, observed):
        trial = state._replace(qi=qi, ni=ni)
        if observed:
            probe = ProducerCapture()
            out, trace, _ = probe.run(trial, forcing, normalized=normalized)
            require(len(probe.records) == 1, "derivative C3 producer call count")
        else:
            out, trace, _ = run_plain(trial, forcing, normalized=normalized)
        values = torch.cat((
            (out.qi * 1e8).reshape(-1), out.ni.reshape(-1),
            (out.qv * 1e3).reshape(-1), out.th.reshape(-1),
        ))
        return values, trace

    def value(qi, ni, observed):
        return packed(qi, ni, observed=observed)[0]

    baseline, base_trace = packed(state.qi, state.ni, observed=True)
    weights = torch.arange(1, baseline.numel() + 1, dtype=baseline.dtype)
    weights[1::2] *= -1.0
    results = {}
    for name in ("qi_only", "ni_only"):
        dqi, dni = torch.zeros_like(state.qi), torch.zeros_like(state.ni)
        if name == "qi_only":
            dqi[0, 1] = state.qi[0, 1]
        else:
            dni[0, 1] = state.ni[0, 1]
        plain, jvp_plain = torch.autograd.functional.jvp(
            lambda qi, ni: value(qi, ni, False),
            (state.qi, state.ni), (dqi, dni))
        seen, jvp_seen = torch.autograd.functional.jvp(
            lambda qi, ni: value(qi, ni, True),
            (state.qi, state.ni), (dqi, dni))
        require(bits_equal(plain, seen) and bits_equal(jvp_plain, jvp_seen),
                "runtime trace JVP noninterference " + name)
        gradients = []
        for observed in (False, True):
            qi = state.qi.clone().requires_grad_(True)
            ni = state.ni.clone().requires_grad_(True)
            result = value(qi, ni, observed)
            gradients.append(torch.autograd.grad((weights * result).sum(), (qi, ni)))
        for ordinary, traced in zip(*gradients):
            require(bits_equal(ordinary, traced), "runtime trace VJP noninterference " + name)
        dot = (gradients[0][0] * dqi).sum() + (gradients[0][1] * dni).sum()
        require(torch.allclose(dot, (weights * jvp_plain).sum(), rtol=2e-11, atol=1e-11),
                "runtime JVP/VJP inner product " + name)
        plus, plus_trace = packed(state.qi + H * dqi, state.ni + H * dni,
                                  observed=True)
        minus, minus_trace = packed(state.qi - H * dqi, state.ni - H * dni,
                                    observed=True)
        require(base_trace.subcycles == plus_trace.subcycles == minus_trace.subcycles and
                base_trace.signature() == plus_trace.signature() == minus_trace.signature(),
                "runtime captured topology changed " + name)
        for trial in (state._replace(qi=state.qi + H * dqi, ni=state.ni + H * dni),
                      state._replace(qi=state.qi - H * dqi, ni=state.ni - H * dni)):
            probe = ProducerCapture()
            _, _, _ = probe.run(trial, forcing, normalized=normalized)
            require(len(probe.records) == 1, "runtime perturbed C3 count")
            derived = inspect_producer(probe.records[0])
            require(torch.all(derived["outer"][0]) and torch.all(derived["inner"][0]) and
                    torch.all(derived["deficit_mass_rate"][0] < derived["half_satdt"][0]) and
                    torch.all(derived["deficit_mass_rate"][0] < derived["supice"][0]),
                    "runtime perturbed C3 branch " + name)
        fd = (plus - minus) / (2 * H)
        error = fd - jvp_plain
        signal = torch.linalg.vector_norm(jvp_plain)
        require(bool(torch.isfinite(fd).all()) and signal > 0 and
                torch.allclose(fd, jvp_plain, rtol=1e-5, atol=1e-9),
                "runtime FD-JVP selected direction " + name)
        ncell = state.qi.numel()
        fields = {}
        for index, field in enumerate(OUTPUT_FIELDS):
            factor = OUTPUT_SCALES[field]
            selected = slice(index * ncell, (index + 1) * ncell)
            j_raw = (jvp_plain[selected] / factor).reshape(state.qi.shape)
            fd_raw = (fd[selected] / factor).reshape(state.qi.shape)
            e_raw = fd_raw - j_raw
            field_signal = torch.linalg.vector_norm(j_raw)
            fields[field] = {
                "output_scale_used_in_packed_check": factor,
                "jvp_wrf_bottom_first": j_raw.detach().tolist(),
                "fd_wrf_bottom_first": fd_raw.detach().tolist(),
                "fd_minus_jvp_wrf_bottom_first": e_raw.detach().tolist(),
                "max_abs_fd_minus_jvp": float(e_raw.abs().max()),
                "relative_l2_fd_minus_jvp": (
                    float(torch.linalg.vector_norm(e_raw) / field_signal)
                    if bool(field_signal > 0) else None),
            }
        direction = dqi if name == "qi_only" else dni
        field_name = "qi" if name == "qi_only" else "ni"
        baseline_value = float(getattr(state, field_name)[0, 1])
        direction_value = float(direction[0, 1])
        results[name] = {
            "max_abs_fd_minus_jvp_scaled": float(error.abs().max()),
            "relative_l2_fd_minus_jvp_scaled": float(torch.linalg.vector_norm(error) / signal),
            "jvp_scaled_norm": float(signal),
            "selected_c3_branch": "active strict number-deficit minimum at baseline and endpoints",
            "captured_stage_masks_equal": True,
            "input_direction": {
                "field": field_name, "column_zero_based": 0,
                "wrf_level_zero_based": 1,
                "top_first_level_zero_based": state.qi.shape[-1] - 1 - 1,
                "baseline_value": baseline_value,
                "absolute_direction_per_unit_epsilon": direction_value,
                "relative_direction": direction_value / baseline_value,
                "fd_step": H,
                "plus_input": baseline_value + H * direction_value,
                "minus_input": baseline_value - H * direction_value,
            },
            "outputs_by_field": fields,
        }
    return results


def precision_probe():
    """Input f32 here is a mixed-precision oracle run, not operational f32 parity."""
    state, forcing = build_state(torch.float32)
    result = {}
    for normalized in (False, True):
        out, trace, _ = run_plain(state, forcing, normalized=normalized, trace=True)
        post_sed = trace.by_name("d1_melt")[0].state_in
        post_freeze = trace.by_name("d2_d4_freeze")[0].state_out
        require(post_sed.qi.dtype == torch.float32 and
                post_freeze.qi.dtype == out.qi.dtype == out.ni.dtype == torch.float64,
                "mixed-precision oracle boundary")
        result["normalized" if normalized else "legacy"] = {
            "post_sed_qi_dtype": str(post_sed.qi.dtype),
            "post_freeze_qi_dtype": str(post_freeze.qi.dtype),
            "final_qi_dtype": str(out.qi.dtype),
            "final_ni_dtype": str(out.ni.dtype),
            "subcycles": trace.subcycles,
        }
    return result


def main():
    torch.set_num_threads(1)
    check_sources()
    state, forcing = build_state()
    variants = {}
    actual_record = None
    for normalized in (False, True):
        output, trace, diagnosed, result = inspect_runtime_variant(
            state, forcing, normalized=normalized)
        variants["normalized" if normalized else "legacy"] = result
        if not normalized:
            # The producer call is deterministic; take the actual arguments once
            # more with a scoped recorder for the isolated branch and JVP checks.
            probe = ProducerCapture()
            again, _, _ = probe.run(state, forcing, normalized=False)
            for name in State._fields:
                require(bits_equal(getattr(output, name), getattr(again, name)),
                        "repeat producer capture " + name)
            actual_record = probe.records[0]
            require(bits_equal(diagnosed["pinud"], actual_record["output"].pinud),
                    "actual C3 output repeat")
    require(actual_record is not None, "missing legacy C3 record")
    isolated = isolated_branches(actual_record)
    derivative = direct_nucleation_derivative(actual_record)
    runtime_ad = {
        "normalized" if normalized else "legacy": runtime_derivatives(
            state, forcing, normalized=normalized)
        for normalized in (False, True)
    }
    for field in ("qi", "ni"):
        legacy = runtime_ad["legacy"]["ni_only"]["outputs_by_field"][field]
        normalized = runtime_ad["normalized"]["ni_only"]["outputs_by_field"][field]
        require(legacy["jvp_wrf_bottom_first"][0][1] < 0 and
                normalized["jvp_wrf_bottom_first"][0][1] > 0,
                "selected NI sensitivity sign contrast " + field)
    precision = precision_probe()
    print(json.dumps({"status": "ICE_NUCLEATION_RUNTIME_REPLAY_PASSED",
                      "scientific_status": "INCONCLUSIVE",
                      "scope": "PR504 synthetic state; full public runtime at dt=1, with CCN and automatic mstep; no private host/RTTOV",
                      "variants": variants,
                      "isolated_C3_branches": isolated,
                      "uncapped_C3_derivative": derivative,
                      "runtime_selected_derivatives": runtime_ad,
                      "precision_probe": precision,
                      "torch_version": torch.__version__}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
