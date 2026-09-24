"""Focused validation of the isolated mp237 velocity-normalization replay."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from replay_ice_normalization import (  # noqa: E402
    EVIDENCE,
    f32,
    mstep_candidate,
    validate,
)


@pytest.fixture(scope="module")
def evidence():
    return json.loads(EVIDENCE.read_text())


@pytest.fixture(scope="module")
def replay(evidence):
    return validate(evidence)


def test_retained_run_scope_stage_coverage_and_noninterference(replay):
    assert replay["records"] == 702
    assert replay["calls"] == [1, 2]
    assert replay["control_capture_noninterference"]
    assert replay["operational_fix_applied"] is False
    assert replay["physical_number_basis_resolved"] is False
    assert replay["accepted_observation_cost"] is False
    assert replay["first_negative_state_at_handoff"] is None
    assert replay["stage_counts"]["HANDOFF_INTERIOR_AFTER"] == 76
    assert replay["stage_counts"]["HANDOFF_TOP_AFTER"] == 2


def test_initial_main_and_later_coefficients_are_raw_velocity_over_dz(replay):
    assert replay["max_raw_mass_velocity_m_s"] > 0
    assert replay["max_raw_number_velocity_m_s"] > 0
    assert replay["max_mass_coefficient_s-1"] > 0
    assert replay["max_number_coefficient_s-1"] > 0
    assert replay["max_cfl_mstep_selection"] < 1
    assert replay["max_cfl_main_consumed"] < 1
    assert replay["max_cfl_later_prep_unconsumed"] > replay["max_cfl_main_consumed"]
    consumed = replay["main_consumed_cfl_by_call"]
    assert consumed[1]["mass"] == pytest.approx(0.1629175974)
    assert consumed[2]["mass"] == pytest.approx(0.06742497)
    assert consumed[1]["number"] == pytest.approx(0.0407294)
    assert consumed[2]["number"] == pytest.approx(0.0168562432)
    # Exact per-record raw/dz comparisons are made inside validate().
    assert replay["records"] == 702


def test_fortran_nint_plus_half_mstep_mapping_and_cumulative_selection(replay):
    assert [mstep_candidate(x) for x in (0.0, 0.49, 0.5, 0.999, 1.0, 1.01)] == [
        1,
        1,
        1,
        1,
        2,
        2,
    ]
    assert replay["mstep_max"] == 1


def test_handoff_is_checked_against_main_reslope_coefficients(evidence):
    # The retained trajectory happens to have equal initial and main numerical
    # coefficient values. This mutation proves the validator keys the handoff
    # to MAIN_NORMALIZED rather than silently falling back to initial values.
    changed = copy.deepcopy(evidence)
    raw = next(
        r
        for r in changed["records"]
        if r["tag"] == "RAW_MAIN" and r["call"] == 2 and r["native_k"] == 24
    )
    main = next(
        r
        for r in changed["records"]
        if r["tag"] == "MAIN_NORMALIZED" and r["call"] == 2 and r["native_k"] == 24
    )
    raw["raw_mass_velocity"] *= 2.0
    main["mass_coefficient"] = raw["raw_mass_velocity"] / raw["dz"]
    with pytest.raises(AssertionError, match="handoff mass uses main-normalized"):
        validate(changed)


def test_number_poststate_replays_f32_source_operation_order(replay, evidence):
    assert replay["number_update_rows"] == 78
    assert replay["max_abs_number_update_error"] == 0.0
    # Native levels are nonuniform, so the destination denominator must be its
    # own dz and the receiver must use the measured upper departure.
    before = next(
        r
        for r in evidence["records"]
        if r["tag"] == "HANDOFF_INTERIOR_BEFORE"
        and r["call"] == 2
        and r["native_k"] == 23
    )
    after = next(
        r
        for r in evidence["records"]
        if r["tag"] == "HANDOFF_INTERIOR_AFTER"
        and r["call"] == 2
        and r["native_k"] == 23
    )
    upper = next(
        r
        for r in evidence["records"]
        if r["tag"] == "HANDOFF_INTERIOR_AFTER"
        and r["call"] == 2
        and r["native_k"] == 24
    )
    arrival = f32(f32(upper["departure_ni"] * upper["dz"]) / before["dz"])
    expected = f32(f32(before["ni"] - after["departure_ni"]) + arrival)
    assert expected == after["post_ni"]
    assert before["dz"] != upper["dz"]


def test_binary32_rounding_helpers_round_each_operation():
    a, b, c = 0.1, 0.1, 0.3
    staged = f32(f32(a * b) / c)
    single_round = f32((a * b) / c)
    assert staged != single_round


def test_missing_stage_or_scope_flag_fails_closed(evidence):
    missing = copy.deepcopy(evidence)
    missing["records"] = [r for r in missing["records"] if r["tag"] != "RAW_MAIN"]
    with pytest.raises(AssertionError):
        validate(missing)

    mislabeled = copy.deepcopy(evidence)
    mislabeled["operational_fix_applied"] = True
    with pytest.raises(AssertionError, match="operational_fix_applied"):
        validate(mislabeled)


def test_consumed_substep_count_must_match_main_handoff(evidence):
    changed = copy.deepcopy(evidence)
    r = next(
        r
        for r in changed["records"]
        if r["tag"] == "HANDOFF_TOP_BEFORE" and r["call"] == 2
    )
    r["mstep"] = 2.0
    with pytest.raises(AssertionError, match="handoff time/substep mismatch"):
        validate(changed)
