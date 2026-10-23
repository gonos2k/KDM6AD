"""Independent reservoirs and protocol corruption checks; no KDM required."""
import struct
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from harness import same_call_water_budget as budget


def fixture():
    state = np.zeros((12, 2))
    state[0] = 300.
    state[1] = [.01, .02]
    state[3] = [.002, .004]
    forcing = np.array([[.5, 2.], [1., 1.], [1e5, 8e4], [10., 20.]])
    return state, forcing


def response(state, forcing, raw, flux):
    return budget.RESPONSE.pack(b"K6BOUT1\0", 1, state.shape[1]) + np.concatenate(
        (state.ravel(), forcing.ravel(), raw.ravel(), flux)).astype("<f8").tobytes()


def test_total_export_closes_analytic_reservoir_without_summing_subsets_or_dt():
    state, f = fixture()
    raw = state.copy()
    raw[3] -= .001
    # Weights are [5,40]; total removal .045, of which snow=.01, graupel=.02.
    out = budget.ledger(state, f, raw, raw, np.array([.045, .01, .02]), 20.)
    assert out["balance"]["kernel_change_kg_m2"] == pytest.approx(-.045)
    assert out["balance"]["within_numerical_gate"]
    assert abs(out["balance"]["kernel_plus_export_residual_kg_m2"]) < 1e-16
    assert out["weight_contract"]["column_dry_mass_kg_m2"] == 45.
    assert not out["closed_water_budget_certified"]  # local gate is no universal proof


def test_unclosed_raw_and_cleanup_are_separate_not_compensated():
    state, f = fixture()
    raw = state.copy()
    raw[3] -= .001
    clean = raw.copy()
    clean[3, 0] = 0.
    out = budget.ledger(state, f, raw, clean, np.array([.04, .01, .02]), 20.)
    assert out["diagnostic_complete"]
    assert not out["balance"]["within_numerical_gate"]
    assert out["balance"]["kernel_plus_export_residual_kg_m2"] == pytest.approx(-.005)
    assert out["balance"]["cleanup_change_kg_m2"] == pytest.approx(-.005)
    assert out["balance"]["applied_plus_export_residual_kg_m2"] == pytest.approx(-.01)


def test_echo_and_header_protocol_roundtrip():
    s, f = fixture()
    req = budget.request_bytes(s, f, 20., 2., 10., 10.)
    assert budget.REQUEST.unpack_from(req) == (b"K6BUDG1\0", 1, 2, 20., 2., 10., 10.)
    parsed = budget.read_response(response(s, f, s, [0., 0., 0.]), s, f)
    for actual, expected in zip(parsed, (s, f, s, np.zeros(3))):
        assert budget.same_bits(actual, expected)


@pytest.mark.parametrize("kind", ["truncated", "trailing", "magic", "version", "levels", "nan", "echo", "flux"])
def test_response_corruption_is_refused(kind):
    s, f = fixture()
    data = bytearray(response(s, f, s, [0., 0., 0.]))
    if kind == "truncated":
        data = data[:-1]
    elif kind == "trailing":
        data += b"x"
    elif kind == "magic":
        data[0] = 0
    elif kind == "version":
        struct.pack_into("<I", data, 8, 2)
    elif kind == "levels":
        struct.pack_into("<I", data, 12, 0)
    elif kind == "nan":
        struct.pack_into("<d", data, 16, np.nan)
    elif kind == "echo":
        struct.pack_into("<d", data, 16, 301.)
    else:
        struct.pack_into("<d", data, len(data)-8, 1.)
    with pytest.raises(ValueError):
        budget.read_response(data, s, f)


@pytest.mark.parametrize("forcing_bad,dt", [(True, 20.), (False, 0.), (False, np.nan)])
def test_request_metadata_refused_before_run(forcing_bad, dt):
    s, f = fixture()
    if forcing_bad:
        f[0, 0] = 0.
    with pytest.raises(ValueError):
        budget.request_bytes(s, f, dt, 2., 10., 10.)


def test_signed_zero_echo_is_not_silently_accepted():
    s, f = fixture()
    other = s.copy()
    other[2, 0] = -0.
    with pytest.raises(ValueError, match="bits"):
        budget.read_response(response(other, f, s, [0., 0., 0.]), s, f)


@pytest.mark.parametrize("changed", [None, "dt_seconds", "xland", "ncmin_land_sea", "namelist", "indices"])
def test_native_scalar_controls_bound_before_run(changed):
    source = Path(__file__).parents[1]/"evidence/native_number_boundary_2026-10-22/native39_dry_boundary_cost.json"
    report = json.loads(source.read_text())
    receipt = copy.deepcopy(report["number_boundary"]["admission"])
    nml = {"time_step": ["20"], "time_step_fract_num": ["0"], "time_step_fract_den": ["1"],
           "ncmin_land": ["10"], "ncmin_sea": ["10"]}
    if changed == "dt_seconds":
        report["kernel_contract"][changed] = 40.
    elif changed == "xland":
        report["kernel_contract"][changed] = 1.
    elif changed == "ncmin_land_sea":
        report["kernel_contract"][changed] = [100., 10.]
    elif changed == "namelist":
        report["input_sha256"][changed] = "0"*64
    elif changed == "indices":
        report["native_snapshot"]["native_indices_1based"] = [1, 1]
    if changed is None:
        budget.validate_controls(report, receipt, nml, 2.)
    else:
        with pytest.raises(ValueError):
            budget.validate_controls(report, receipt, nml, 2.)


def test_public_same_call_ledger_recomputed_without_private_execution():
    evidence = Path(__file__).parents[1]/"evidence"
    source = evidence/"same_call_water_budget_2026-10-22/native39_same_call.json"
    saved = json.loads(source.read_text())  # immutable historical v1 capture
    v2 = json.loads((evidence/"ice_boundary_attribution_2026-10-23/same_call_deterministic_reduction_v2.json").read_text())
    call, precip = saved["same_call"], saved["precipitation"]
    flux = [precip["total_precip_mm"], precip["snow_ice_subset_mm"], precip["graupel_subset_mm"]]
    actual = budget.ledger(call["state_in"], call["forcing_in"], call["state_out"],
                           call["clean_after"], flux, saved["dt_seconds"])
    assert saved["schema"] == "kdm6.same_call_water_budget.v1"
    assert budget.SCHEMA == actual["schema"] == v2["schema"] == "kdm6.same_call_water_budget.v2"
    assert v2["historical_source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert actual["weight_contract"] == v2["weight_contract"]
    assert actual["water"] == v2["water"]
    for key in ("initial_water_kg_m2", "raw_final_water_kg_m2", "kernel_change_kg_m2",
                "cleanup_change_kg_m2", "applied_change_kg_m2", "kernel_plus_export_residual_kg_m2"):
        assert actual["balance"][key] == v2["balance"][key], key
    assert saved["diagnostic_complete"]
    assert not saved["balance"]["within_numerical_gate"]
    assert saved["comparison_to_prior"]["state_out_raw_bit_equal"]
    json.dumps(actual, allow_nan=False)  # includes genuine Python bools


def test_public_stage_trace_replays_with_orientation_and_rejects_mixed_records():
    directory = Path(__file__).parents[1]/"evidence/same_call_water_budget_2026-10-22"
    trace = (directory/"native39_stage_trace.txt").read_text()
    saved = json.loads((directory/"native39_stage_localization.json").read_text())
    actual = budget.stage_changes(trace, 39, 20.)
    for name, value in actual.items():
        assert value == saved["stage_deltas_recomputed_from_per_level_binary64"][name]
    for changed in (trace+trace, "\n".join(trace.splitlines()[:-1]), trace.replace("dt_call=20", "dt_call=40", 1)):
        with pytest.raises(ValueError):
            budget.stage_changes(changed, 39, 20.)
