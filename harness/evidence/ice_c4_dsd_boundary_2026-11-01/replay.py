#!/usr/bin/env python3
"""Bind saturation-boundary C3/C4 operands to final ice-number DSD states."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from unittest.mock import patch

import torch

from oracle.kdm6 import cold as cold_module
from oracle.kdm6.state import State

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
SUPPLY = importlib.import_module("harness.evidence.ice_nucleation_supply_2026-10-31.replay")
PARENT = SUPPLY.PARENT
POST = importlib.import_module("harness.evidence.ice_post_sed_fate_2026-10-31.replay")
SATURATION_OFFSETS = (-1e-12, 0.0, 1e-12)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_sources():
    SUPPLY.verify_sources()
    manifest = json.loads((ROOT / "source_manifest.json").read_bytes())
    for relative, expected in manifest.items():
        path = REPO / relative
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                "source digest " + relative)


def first_top(value):
    return value[0].flip(-1).detach().tolist()


def _copy(value):
    return value.detach().clone() if isinstance(value, torch.Tensor) else value


class C4Capture:
    """Scoped single-thread observer; its return value is the original C4 graph."""

    def __init__(self):
        self.records = []

    def run(self, state, forcing):
        original = cold_module.dep_sub_torch

        def intercept(*args, **kwargs):
            result = original(*args, **kwargs)
            self.records.append({
                "args": tuple(_copy(value) for value in args),
                "kwargs": {name: _copy(value) for name, value in kwargs.items()},
                "output": type(result)(*(_copy(value) for value in result)),
            })
            return result

        c3 = PARENT.ProducerCapture()
        with patch.object(cold_module, "dep_sub_torch", intercept):
            output, trace, ice = c3.run(state, forcing, normalized=False)
        return output, trace, ice, c3.records, self.records


def reconstruct_pidep(captured):
    """Re-evaluate C4's signed ice cap from the actual consumed arguments."""
    args, kwargs, output = captured["args"], captured["kwargs"], captured["output"]
    require(len(args) == 15, "C4 positional input inventory")
    qi, rh, supcol, supsat, prevp, pinud, ifsat, n0i, work1 = (
        args[0], args[3], args[4], args[5], args[6], args[7], args[8],
        args[9], args[13])
    params, dt = kwargs["params"], float(kwargs["dtcld"])
    active = (supcol > 0) & (qi > 0) & (~ifsat)
    work1_safe = torch.clamp(work1, min=params.qcrmin)
    raw = (4.0 * n0i * params.g2pmi * kwargs["rslopemu_i"] * kwargs["rslope2_i"] *
           (rh - 1.0) / work1_safe)
    satdt = supsat / dt
    half = 0.5 * satdt
    remaining = satdt - prevp - pinud
    qi_floor = -qi / dt
    sub_path = torch.maximum(raw, qi_floor)
    sub_path = torch.maximum(torch.maximum(sub_path, half), remaining)
    dep_path = torch.minimum(torch.minimum(raw, half), remaining)
    capped = torch.where(raw < 0, sub_path, dep_path)
    actual = torch.where(active, capped, torch.zeros_like(capped))
    complete_sublim = active & (raw == qi_floor) & (raw < 0)
    require(PARENT.bits_equal(actual, output.pidep) and
            torch.equal(complete_sublim, output.ice_complete_sublim),
            "C4 signed pidep replay")
    return {"active": active, "raw": raw, "qi_floor": qi_floor,
            "half_satdt": half, "remaining": remaining,
            "capped": capped, "pidep": output.pidep,
            "ifsat_in": ifsat, "ifsat_out": output.ifsat,
            "complete_sublim": output.ice_complete_sublim}


def cap_selection(c4):
    """Report all equal winners; exact zero can tie raw and half caps."""
    k = -1  # top level in WRF order
    if not bool(c4["active"][0, k]):
        return ["inactive_ifsat" if bool(c4["ifsat_in"][0, k]) else "inactive_other"]
    raw = float(c4["raw"][0, k])
    candidates = {"raw": raw, "half_satdt": float(c4["half_satdt"][0, k]),
                  "remaining": float(c4["remaining"][0, k])}
    if raw < 0:
        candidates["negative_mass_floor"] = float(c4["qi_floor"][0, k])
        selected = max(candidates.values())
    else:
        selected = min(candidates.values())
    require(selected == float(c4["pidep"][0, k]), "C4 selected cap value")
    return [name for name, value in candidates.items() if value == selected]


def dsd_ice(trace):
    stage = trace.by_name("dsd_limiter")[0]
    labels = stage.metadata["branch_labels"]
    masks = {
        name: stage.branch[index, 0, -1].detach().item()
        for index, name in enumerate(labels) if name.startswith("ice_")
    }
    before, after = stage.state_in.ni[0, -1], stage.state_out.ni[0, -1]
    q_before, q_after = stage.state_in.qi[0, -1], stage.state_out.qi[0, -1]
    require(PARENT.bits_equal(q_before.reshape(1), q_after.reshape(1)),
            "DSD ice mass unchanged")
    if masks["ice_active"] and masks["ice_final_ncmin_gate"] and masks["ice_too_large"]:
        expected = stage.operands["ice_n_at_max"][0, -1]
    elif masks["ice_active"] and masks["ice_final_ncmin_gate"] and masks["ice_too_small"]:
        expected = stage.operands["ice_n_at_min"][0, -1]
    else:
        expected = before
    require(PARENT.bits_equal(after.reshape(1), expected.reshape(1)),
            "DSD applied NI bound")
    return {"masks": masks, "ni_before": float(before), "ni_after": float(after),
            "qi_before": float(q_before), "qi_after": float(q_after),
            "ice_n_at_min": float(stage.operands["ice_n_at_min"][0, -1]),
            "ice_n_at_max": float(stage.operands["ice_n_at_max"][0, -1]),
            "ice_lamda": float(stage.operands["ice_lamda"][0, -1])}


def inspect_boundary(offset, *, temperature_k=263.15):
    state, forcing, qs_ice, _ = SUPPLY.coherent_state(offset, temperature_k=temperature_k)
    capture = C4Capture()
    output, trace, _ice, c3_records, c4_records = capture.run(state, forcing)
    plain, _, _ = PARENT.run_plain(state, forcing, normalized=False)
    for name in State._fields:
        require(PARENT.bits_equal(getattr(output, name), getattr(plain, name)),
                "C3/C4 observer noninterference " + name)
    require(len(c3_records) == len(c4_records) == 1 and
            trace.subcycles[0]["main_by_column"] == [1.0, 1.0] and
            trace.subcycles[0]["ice_by_column"] == [1.0, 1.0],
            "boundary runtime topology")
    c3 = PARENT.inspect_producer(c3_records[0])
    c4 = reconstruct_pidep(c4_records[0])
    args = c4_records[0]["args"]
    require(PARENT.bits_equal(args[7], c3["pinud"]) and
            torch.equal(args[8], c3["ifsat"]), "C3 output into actual C4 call")
    cold = trace.by_name("cold")[0].rates
    limited = trace.by_name("cold_limited")[0].rates
    require(PARENT.bits_equal(c4["pidep"], cold.pidep) and
            PARENT.bits_equal(cold.pidep, limited.pidep),
            "C4 producer to applied cold rate in this fixture")
    dsd = dsd_ice(trace)
    update = trace.by_name("state_update")[0]
    rate_accounting = POST.check_rate_accounting(trace)
    require(PARENT.bits_equal(output.qi[0, -1].reshape(1),
                              trace.by_name("dsd_limiter")[0].state_out.qi[0, -1].reshape(1)) and
            PARENT.bits_equal(output.ni[0, -1].reshape(1),
                              trace.by_name("dsd_limiter")[0].state_out.ni[0, -1].reshape(1)),
            "last ice stage to runtime output")
    return {
        "initial_offset": offset, "temperature_k": temperature_k,
        "qs_ice_initial": float(qs_ice[0, -1]),
        "subcycles": trace.subcycles,
        "C3": {"outer": bool(c3["outer"][0, -1]),
               "inner": bool(c3["inner"][0, -1]),
               "ifsat": bool(c3["ifsat"][0, -1]),
               "nid": float(c3["nid"][0, -1]),
               "ni_in": float(c3["ni_in"][0, -1]),
               "deficit_mass_rate": float(c3["deficit_mass_rate"][0, -1]),
               "half_satdt": float(c3["half_satdt"][0, -1]),
               "supice": float(c3["supice"][0, -1]),
               "pinud": float(c3["pinud"][0, -1]),
               "ninud": float(c3["ninud"][0, -1])},
        "C4": {"active": bool(c4["active"][0, -1]),
               "raw_pidep": float(c4["raw"][0, -1]),
               "negative_qi_floor": float(c4["qi_floor"][0, -1]),
               "half_satdt": float(c4["half_satdt"][0, -1]),
               "remaining_supply": float(c4["remaining"][0, -1]),
               "winning_candidates": cap_selection(c4),
               "producer_pidep": float(c4["pidep"][0, -1]),
               "limited_pidep": float(limited.pidep[0, -1]),
               "ifsat_out": bool(c4["ifsat_out"][0, -1]),
               "complete_sublimation": bool(c4["complete_sublim"][0, -1])},
        "state_update": {"qi_before": float(update.state_in.qi[0, -1]),
                         "qi_after": float(update.state_out.qi[0, -1]),
                         "ni_before": float(update.state_in.ni[0, -1]),
                         "ni_after": float(update.state_out.ni[0, -1])},
        "state_update_rate_accounting": {
            name: values[0] for name, values in rate_accounting.items()
            if name != "complete_sublimation"},
        "DSD": dsd,
        "final": {"qi": float(output.qi[0, -1]),
                  "ni": float(output.ni[0, -1])},
    }


def main():
    torch.set_num_threads(1)
    verify_sources()
    boundary = {str(offset): inspect_boundary(offset) for offset in SATURATION_OFFSETS}
    below, exact, above = (boundary[str(offset)] for offset in SATURATION_OFFSETS)
    require(not below["C3"]["outer"] and below["C4"]["active"] and
            below["C4"]["winning_candidates"] == ["remaining"] and
            below["C4"]["raw_pidep"] < 0 < below["C4"]["producer_pidep"],
            "below-saturation signed C4 cap")
    require(not exact["C3"]["outer"] and exact["C4"]["active"] and
            set(exact["C4"]["winning_candidates"]) == {"raw", "half_satdt"} and
            exact["C4"]["producer_pidep"] == 0.0 and
            exact["DSD"]["masks"]["ice_too_large"] and
            exact["DSD"]["ni_after"] == exact["DSD"]["ice_n_at_max"],
            "exact-saturation C4 tie and final DSD snap")
    require(above["C3"]["outer"] and above["C3"]["ifsat"] and
            not above["C4"]["active"] and above["C4"]["producer_pidep"] == 0.0 and
            above["DSD"]["ni_after"] == above["DSD"]["ni_before"],
            "above-saturation C3 block of C4")
    low_temp = {str(offset): inspect_boundary(offset, temperature_k=253.15)
                for offset in (1e-10, 1e-9)}
    low_supply = low_temp[str(1e-9)]
    require(all(case["C3"]["outer"] for case in low_temp.values()) and
            all(case["subcycles"][0]["ice_by_column"] == [1.0, 1.0]
                for case in low_temp.values()), "low-temperature topology")
    for offset in (1e-10, 1e-9):
        state, forcing, _, _ = SUPPLY.coherent_state(offset, temperature_k=253.15)
        probe = PARENT.ProducerCapture()
        _, _, _ = probe.run(state, forcing, normalized=False)
        c3 = PARENT.inspect_producer(probe.records[0])
        require(bool((c3["half_satdt"][0] < c3["deficit_mass_rate"][0]).all()) and
                bool((c3["half_satdt"][0] < c3["supice"][0]).all()),
                "low-temperature strict C3 half cap")
    qs_float = torch.tensor(low_supply["qs_ice_initial"], dtype=torch.float32)
    spacing = float(torch.nextafter(qs_float, torch.tensor(float("inf"), dtype=torch.float32)) -
                    qs_float)
    require(1e-9 / spacing > 10.0, "low-temperature multi-ULP input contrast")
    print(json.dumps({
        "status": "ICE_C4_DSD_BOUNDARY_REPLAY_PASSED",
        "scientific_status": "INCONCLUSIVE",
        "scope": "synthetic f64 public runtime; actual C3/C4 producer calls and final DSD trace; no private host/RTTOV",
        "saturation_boundary": boundary,
        "low_temperature_supply": low_temp,
        "low_temperature_f32_qv_spacing": spacing,
        "low_temperature_offset_over_spacing": 1e-9 / spacing,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
