#!/usr/bin/env python3
"""Full-runtime weak ice supersaturation with a strict C3 supply cap."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import torch

from oracle.kdm6.state import State
from oracle.kdm6.thermo import (
    compute_qs_ice,
    compute_qs_water,
    default_thermo_params,
)

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
PARENT = importlib.import_module(
    "harness.evidence.ice_nucleation_runtime_2026-10-31.replay")
T_K = 263.15
P_PA = 80000.0
WEAK_OFFSET = 1e-10
STRONG_OFFSET = 5e-10
OUTPUT_FIELDS = ("qi", "ni", "qv", "th")
OUTPUT_SCALES = {"qi": 1e8, "ni": 1.0, "qv": 1e3, "th": 1.0}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_sources():
    PARENT.check_sources()
    manifest = json.loads((ROOT / "source_manifest.json").read_bytes())
    for relative, expected in manifest.items():
        path = REPO / relative
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                "source digest " + relative)


def coherent_state(offset, *, qv=None):
    """Construct qv, temperature, Exner and moist density from one p,T relation."""
    base, forcing = PARENT.build_state()
    thermo = default_thermo_params()
    temperature = torch.full_like(base.th, T_K)
    pressure = torch.full_like(base.th, P_PA)
    qs_ice = compute_qs_ice(temperature, pressure, params=thermo)
    qs_water = compute_qs_water(temperature, pressure, params=thermo)
    vapor = qs_ice + offset if qv is None else qv
    pii = (pressure / 100000.0) ** (thermo.rd / thermo.cpd)
    rho = (pressure * (1.0 + vapor) /
           (thermo.rd * temperature * (1.0 + (thermo.rv / thermo.rd) * vapor)))
    state = base._replace(th=temperature / pii, qv=vapor)
    forcing = forcing._replace(rho=rho, pii=pii, p=pressure)
    require(bool((qs_water > qs_ice).all()) and bool((rho > 0).all()) and
            bool((vapor > 0).all()), "coherent subfreezing thermodynamics")
    return state, forcing, qs_ice, qs_water


def inspect_case(offset, *, normalized=False):
    state, forcing, _, _ = coherent_state(offset)
    probe = PARENT.ProducerCapture()
    output, trace, ice = probe.run(state, forcing, normalized=normalized)
    plain, _, _ = PARENT.run_plain(state, forcing, normalized=normalized)
    for name in State._fields:
        require(PARENT.bits_equal(getattr(output, name), getattr(plain, name)),
                "supply observer noninterference " + name)
    require(len(probe.records) == 1 and len(ice.records) == 1 and
            trace.subcycles[0]["ice_by_column"] == [1.0, 1.0],
            "supply full-runtime call topology")
    captured = PARENT.inspect_producer(probe.records[0])
    # C3 reads the saturation/RH fields staged at the microphysics ENTRY,
    # while the cold-rate state T may have changed after D2-D4 freezing.
    entry_state = trace.by_name("d1_melt")[0].state_in
    cold_state = trace.by_name("cold")[0].state_in
    thermo = default_thermo_params()
    qs_ice = compute_qs_ice(entry_state.t, forcing.p, params=thermo)
    qs_water = compute_qs_water(entry_state.t, forcing.p, params=thermo)
    ice_sup = torch.clamp(entry_state.qv, min=thermo.qmin) - qs_ice
    water_sup = torch.clamp(entry_state.qv, min=thermo.qmin) - qs_water
    dtcld = probe.records[0]["dtcld"]
    require(torch.allclose(ice_sup, captured["supsat_ice"], rtol=0, atol=2e-17),
            "producer ice supersaturation from actual state")
    require(torch.allclose(entry_state.qv / qs_ice, captured["rh_ice"],
                           rtol=2e-12, atol=0), "producer ice RH from actual state")
    require(bool((qs_water > qs_ice).all()) and
            bool((captured["prevp"] <= torch.maximum(torch.zeros_like(water_sup),
                                                       0.5 * water_sup / dtcld)).all()) and
            bool((captured["supice"] > captured["half_satdt"]).all()),
            "subfreezing remaining-supply bound on this state")
    require(bool(captured["outer"][0].all()) and
            bool(captured["inner"][0].all()), "supply C3 active")
    half = captured["half_satdt"][0]
    deficit = captured["deficit_mass_rate"][0]
    remaining = captured["supice"][0]
    cap = "half_satdt" if bool((half < deficit).all()) else "deficit_mass_rate"
    require(bool((remaining > half).all()) and
            (cap == "half_satdt" if offset == WEAK_OFFSET else
             bool((deficit < half).all())), "strict C3 supply/deficit selection")
    cold = trace.by_name("cold")[0].rates
    limited = trace.by_name("cold_limited")[0].rates
    require(PARENT.bits_equal(captured["pinud"], cold.pinud) and
            PARENT.bits_equal(captured["ninud"], cold.ninud) and
            PARENT.bits_equal(cold.pinud, limited.pinud) and
            PARENT.bits_equal(cold.ninud, limited.ninud),
            "supply C3 producer-to-applied rate")
    def first(value):
        return value[0].flip(-1).detach().tolist()

    return {
        "initial_qv_above_ice_saturation": offset,
        "normalized_first_handoff": normalized,
        "automatic_subcycles": trace.subcycles,
        "selected_cap_first_column": cap,
        "pre_c3_qv": first(entry_state.qv),
        "pre_c3_staged_t": first(entry_state.t),
        "cold_rate_state_t": first(cold_state.t),
        "pre_c3_qs_ice": first(qs_ice),
        "pre_c3_qs_water": first(qs_water),
        "pre_c3_rh_ice": first(captured["rh_ice"]),
        "C3_nid": first(captured["nid"]),
        "C3_ni_in": first(captured["ni_in"]),
        "C3_deficit_mass_rate": first(captured["deficit_mass_rate"]),
        "C3_half_satdt": first(captured["half_satdt"]),
        "C3_supice": first(captured["supice"]),
        "C3_prevp": first(captured["prevp"]),
        "C3_pinud": first(captured["pinud"]),
        "C3_ninud": first(captured["ninud"]),
        "C3_ifsat": first(captured["ifsat"]),
        "C3_margin_deficit_minus_half": (deficit - half).flip(-1).detach().tolist(),
        "C3_margin_remaining_minus_half": (remaining - half).flip(-1).detach().tolist(),
        "post_sed_qi": ice.records[0].qi_after[0].detach().tolist(),
        "post_sed_ni": ice.records[0].number.after[0].detach().tolist(),
        "final_qi": first(output.qi),
        "final_ni": first(output.ni),
    }


def weak_qv_direction():
    """Differentiate a coherent qv/rho family inside the strict half-cap branch."""
    base, forcing, _, _ = coherent_state(WEAK_OFFSET)
    direction = torch.zeros_like(base.qv)
    direction[0, 1] = WEAK_OFFSET
    step = 0.01

    def evaluate(qv, observed):
        state, updated_forcing, _, _ = coherent_state(WEAK_OFFSET, qv=qv)
        if observed:
            probe = PARENT.ProducerCapture()
            output, trace, _ = probe.run(state, updated_forcing, normalized=False)
            require(len(probe.records) == 1, "weak branch C3 producer call")
            captured = PARENT.inspect_producer(probe.records[0])
        else:
            output, trace, _ = PARENT.run_plain(state, updated_forcing,
                                                 normalized=False)
            captured = None
        packed = torch.cat((
            (output.qi * 1e8).reshape(-1), output.ni.reshape(-1),
            (output.qv * 1e3).reshape(-1), output.th.reshape(-1),
        ))
        return packed, trace, captured

    def value(qv, observed):
        return evaluate(qv, observed)[0]

    ordinary, jvp = torch.autograd.functional.jvp(
        lambda qv: value(qv, False), base.qv, direction)
    traced, jvp_traced = torch.autograd.functional.jvp(
        lambda qv: value(qv, True), base.qv, direction)
    require(PARENT.bits_equal(ordinary, traced) and
            PARENT.bits_equal(jvp, jvp_traced), "weak branch JVP noninterference")
    gradients = []
    weights = torch.arange(1, ordinary.numel() + 1, dtype=ordinary.dtype)
    weights[1::2] *= -1
    for observed in (False, True):
        qv = base.qv.clone().requires_grad_(True)
        result = value(qv, observed)
        gradients.append(torch.autograd.grad((weights * result).sum(), qv)[0])
    require(PARENT.bits_equal(gradients[0], gradients[1]),
            "weak branch VJP noninterference")
    require(torch.allclose((gradients[0] * direction).sum(), (weights * jvp).sum(),
                           rtol=2e-11, atol=1e-11), "weak branch JVP/VJP dot")
    baseline, base_trace, base_c3 = evaluate(base.qv, True)
    plus, plus_trace, plus_c3 = evaluate(base.qv + step * direction, True)
    minus, minus_trace, minus_c3 = evaluate(base.qv - step * direction, True)
    require(PARENT.bits_equal(baseline, ordinary) and
            base_trace.subcycles == plus_trace.subcycles == minus_trace.subcycles and
            base_trace.signature() == plus_trace.signature() == minus_trace.signature(),
            "weak branch captured topology")
    for captured in (base_c3, plus_c3, minus_c3):
        require(bool(captured["outer"][0].all()) and
                bool(captured["inner"][0].all()) and
                bool((captured["half_satdt"][0] <
                      captured["deficit_mass_rate"][0]).all()) and
                bool((captured["half_satdt"][0] < captured["supice"][0]).all()),
                "weak branch strict half cap at endpoints")
    fd = (plus - minus) / (2 * step)
    error = fd - jvp
    require(bool(torch.isfinite(fd).all()) and
            torch.linalg.vector_norm(jvp) > 0 and
            torch.allclose(fd, jvp, rtol=2e-5, atol=1e-6),
            "weak branch FD-JVP")
    ncell = base.qv.numel()
    fields = {}
    for index, field in enumerate(OUTPUT_FIELDS):
        selected = slice(index * ncell, (index + 1) * ncell)
        factor = OUTPUT_SCALES[field]
        field_jvp = (jvp[selected] / factor).reshape(base.qv.shape)
        field_fd = (fd[selected] / factor).reshape(base.qv.shape)
        fields[field] = {"jvp_wrf_bottom_first": field_jvp.detach().tolist(),
                         "fd_wrf_bottom_first": field_fd.detach().tolist(),
                         "max_abs_fd_minus_jvp": float((field_fd - field_jvp).abs().max())}
    return {
        "input_field": "qv", "column_zero_based": 0,
        "wrf_level_zero_based": 1, "baseline_qv": float(base.qv[0, 1]),
        "top_first_level_zero_based": base.qv.shape[-1] - 1 - 1,
        "direction_per_unit_parameter": WEAK_OFFSET,
        "fd_step_parameter": step,
        "actual_plus_qv": float(base.qv[0, 1] + step * direction[0, 1]),
        "actual_minus_qv": float(base.qv[0, 1] - step * direction[0, 1]),
        "max_abs_fd_minus_jvp_scaled": float(error.abs().max()),
        "relative_l2_fd_minus_jvp_scaled": float(torch.linalg.vector_norm(error) /
                                                 torch.linalg.vector_norm(jvp)),
        "output_scales": OUTPUT_SCALES,
        "outputs_by_field": fields,
        "captured_masks_equal": True,
    }


def saturation_boundary():
    """One-sided full-runtime observations around exact ice saturation."""
    cases = {}
    for offset in (-1e-12, 0.0, 1e-12):
        state, forcing, _, _ = coherent_state(offset)
        probe = PARENT.ProducerCapture()
        out, trace, _ = probe.run(state, forcing, normalized=False)
        captured = PARENT.inspect_producer(probe.records[0])
        cases[str(offset)] = {
            "actual_ice_supsat_top": float(captured["supsat_ice"][0, -1]),
            "C3_outer_top": bool(captured["outer"][0, -1]),
            "C3_pinud_top": float(captured["pinud"][0, -1]),
            "final_ni_top": float(out.ni[0, -1]),
            "subcycles": trace.subcycles,
        }
    require(not cases[str(-1e-12)]["C3_outer_top"] and
            not cases[str(0.0)]["C3_outer_top"] and
            cases[str(1e-12)]["C3_outer_top"],
            "one-sided ice saturation gate")
    return cases


def main():
    torch.set_num_threads(1)
    verify_sources()
    weak = inspect_case(WEAK_OFFSET)
    strong = inspect_case(STRONG_OFFSET)
    require(weak["selected_cap_first_column"] == "half_satdt" and
            strong["selected_cap_first_column"] == "deficit_mass_rate",
            "full-runtime supply versus deficit result")
    derivative = weak_qv_direction()
    boundary = saturation_boundary()
    spacing = float(torch.nextafter(
        torch.tensor(weak["pre_c3_qs_ice"][0], dtype=torch.float32),
        torch.tensor(float("inf"), dtype=torch.float32)) -
        torch.tensor(weak["pre_c3_qs_ice"][0], dtype=torch.float32))
    print(json.dumps({
        "status": "ICE_NUCLEATION_SUPPLY_REPLAY_PASSED",
        "scientific_status": "INCONCLUSIVE",
        "scope": "coherent idealized f64 public runtime at T=263.15 K, p=80 kPa, EOS moist density; no native host",
        "weak_half_supply": weak,
        "strong_target_deficit": strong,
        "weak_qv_direction": derivative,
        "ice_saturation_one_sided": boundary,
        "binary32_spacing_near_qs_ice": spacing,
        "remaining_supply_inference": (
            "For ordinary subfreezing default-control states with qs_water>=qs_ice and "
            "positive ice supersaturation, warm prevp<=max(0, water_supsat/(2dt)) "
            "<= ice_supsat/(2dt); hence supice>=half_satdt except rounding/ties. "
            "This is a conditional source inference, not global reachability proof."),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
