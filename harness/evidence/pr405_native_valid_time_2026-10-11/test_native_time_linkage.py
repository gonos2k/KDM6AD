"""Boundary start/end and initialization/valid-time counterexamples."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("native_time_linkage", Path(__file__).with_name("native_time_linkage.py"))
link = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(link)


def test_last_record_start_is_not_boundary_interval_end():
    starts = ["2025-07-19_00:00:00", "2025-07-19_03:00:00", "2025-07-19_06:00:00", "2025-07-19_09:00:00"]
    ends = starts[1:] + ["2025-07-19_12:00:00"]
    intervals = link.boundary_intervals(starts, starts, ends)
    result = link.assess_window(starts[0], "2025-07-20_05:56:00", intervals)
    assert result["forecast_lead_seconds"] == 29 * 3600 + 56 * 60
    assert result["seconds_after_last_boundary_interval_end"] == 17 * 3600 + 56 * 60
    assert not result["boundary_supports_run_to_target"]


def test_earlier_initialization_can_support_later_valid_date():
    intervals = link.boundary_intervals(["2025-07-19_00:00:00"], ["2025-07-19_00:00:00"], ["2025-07-21_12:00:00"])
    result = link.assess_window("2025-07-19_00:00:00", "2025-07-20_05:56:00", intervals)
    assert result["boundary_supports_run_to_target"]
    assert result["boundary_supports_existing_8frame_intake"]
    assert not result["same_initialization_date_required"]
    assert result["local_background_valid_time_required"] == "2025-07-20_05:55:40"
    assert result["existing_8frame_intake_last_time_required"] == "2025-07-20_05:58:00"


def test_final_state_endpoint_does_not_certify_advance_from_endpoint():
    intervals = link.boundary_intervals(["2025-07-19_09:00:00"], ["2025-07-19_09:00:00"], ["2025-07-19_12:00:00"])
    result = link.assess_window("2025-07-19_09:00:00", "2025-07-19_12:00:00", intervals)
    assert result["boundary_supports_run_to_target"]
    assert not result["advance_from_target_supported_by_current_BC"]
    assert not result["boundary_supports_existing_8frame_intake"]


@pytest.mark.parametrize("times,starts,ends", [
    ([], [], []),
    (["2025-07-19_00:00:00"], ["2025-07-19_03:00:00"], ["2025-07-19_06:00:00"]),
    (["2025-07-19_00:00:00"], ["2025-07-19_00:00:00"], ["2025-07-19_00:00:00"]),
    (["2025-07-19_00:00:00", "2025-07-19_04:00:00"],
     ["2025-07-19_00:00:00", "2025-07-19_04:00:00"],
     ["2025-07-19_03:00:00", "2025-07-19_06:00:00"]),
])
def test_invalid_or_discontinuous_boundary_metadata_is_not_coverage(times, starts, ends):
    with pytest.raises(ValueError):
        link.boundary_intervals(times, starts, ends)


def test_target_before_initialization_is_rejected():
    intervals = link.boundary_intervals(["2025-07-20_00:00:00"], ["2025-07-20_00:00:00"], ["2025-07-21_00:00:00"])
    with pytest.raises(ValueError, match="precedes initialization"):
        link.assess_window("2025-07-20_00:00:00", "2025-07-19_05:56:00", intervals)
