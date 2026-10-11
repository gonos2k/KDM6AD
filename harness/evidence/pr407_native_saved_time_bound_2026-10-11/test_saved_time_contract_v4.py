"""Public-friendly time-window tests for the case-specific v4 WRF intake."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import pytest


SOURCE = Path(__file__).with_name("intake_native_case_v4.py")
spec = importlib.util.spec_from_file_location("pr407_saved_time_intake", SOURCE)
intake = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(intake)

PORTABLE_TIME_TEST_NAMES = (
    "test_run_duration_components_combine_and_take_priority_over_end_date",
    "test_all_zero_run_duration_falls_back_to_numeric_end_components",
    "test_all_zero_duration_without_supported_end_time_fails_closed",
    "test_end_date_alias_cannot_replace_missing_numeric_producer_fields",
    "test_start_date_alias_cannot_replace_missing_numeric_producer_fields",
    "test_start_date_alias_must_agree_with_numeric_producer_fields",
    "test_end_date_alias_must_agree_with_numeric_producer_fields",
    "test_unsupported_ambiguous_run_or_multidomain_end_assignment_fails",
    "test_earlier_initialization_with_long_enough_duration_accepts_saved_background",
    "test_saved_times_after_effective_stop_are_rejected_inclusive_at_stop",
    "test_terminal_background_allows_local_observation_slot_beyond_saved_stop",
)


def test_run_duration_components_combine_and_take_priority_over_end_date():
    start = "2025-07-19_00:00:00"
    text = """&time_control
 run_days = 1,
 run_hours = 2,
 run_minutes = 3,
 run_seconds = 4,
 end_date = '2025-07-19_01:00:00',
/
"""
    window = intake.effective_production_window(text, start)
    assert window["effective_start_time"] == start
    assert window["effective_stop_time"] == "2025-07-20_02:03:04"
    assert window["effective_duration_seconds"] == 93784
    assert window["effective_stop_basis"] == "wrf_run_duration_components"


def test_all_zero_run_duration_falls_back_to_numeric_end_components():
    start = "2025-07-19_05:54:40"
    text = """&time_control
 run_days = 0,
 run_hours = 0,
 run_minutes = 0,
 run_seconds = 0,
 end_year = 2025,
 end_month = 7,
 end_day = 19,
 end_hour = 5,
 end_minute = 56,
 end_second = 40,
/
"""
    window = intake.effective_production_window(text, start)
    assert window["effective_stop_time"] == "2025-07-19_05:56:40"
    assert window["effective_duration_seconds"] == 120
    assert window["effective_stop_basis"] == "numeric end_year/month/day/hour/minute/second fields"


def test_all_zero_duration_without_supported_end_time_fails_closed():
    with pytest.raises(ValueError, match=r"no numeric end_\* producer clock"):
        intake.effective_production_window("run_minutes = 0,\n", "2025-07-19_00:00:00")


def test_end_date_alias_cannot_replace_missing_numeric_producer_fields():
    with pytest.raises(ValueError, match="end_date alias cannot replace"):
        intake.effective_production_window(
            "run_minutes = 0,\nend_date = '2025-07-19_05:56:40',\n",
            "2025-07-19_05:54:40")


def test_start_date_alias_cannot_replace_missing_numeric_producer_fields(tmp_path):
    run = tmp_path / "alias_start_only"
    run.mkdir()
    (run / "namelist.input").write_text("start_date = '2025-07-19_00:00:00',\n")
    with pytest.raises(ValueError, match="missing numeric start_year producer clock field"):
        intake._archived_initial_time(run, {}, {})


def test_start_date_alias_must_agree_with_numeric_producer_fields(tmp_path):
    run = tmp_path / "mismatched_start_alias"
    run.mkdir()
    (run / "namelist.input").write_text(
        "start_year = 2025,\nstart_month = 7,\nstart_day = 19,\nstart_hour = 0,\n"
        "start_minute = 0,\nstart_second = 0,\nstart_date = '2025-07-19_00:00:01',\n")
    with pytest.raises(ValueError, match="start_date alias conflicts"):
        intake._archived_initial_time(run, {}, {})


def test_end_date_alias_must_agree_with_numeric_producer_fields():
    text = """run_minutes = 0,
end_year = 2025,
end_month = 7,
end_day = 19,
end_hour = 5,
end_minute = 56,
end_second = 40,
end_date = '2025-07-19_05:56:41',
"""
    with pytest.raises(ValueError, match="end_date alias conflicts"):
        intake.effective_production_window(text, "2025-07-19_05:54:40")


@pytest.mark.parametrize("text", [
    "run_hours = 1, 2,\n",
    "run_seconds = -1,\n",
    "run_days = 0,\nend_date = '2025-07-19_00:00:00',\n",
    "run_minutes = 0,\nend_year = 2025, 2025,\nend_month = 7, 7,\nend_day = 19, 19,\nend_hour = 6, 7,\n",
])
def test_unsupported_ambiguous_run_or_multidomain_end_assignment_fails(text):
    with pytest.raises(ValueError):
        intake.effective_production_window(text, "2025-07-19_00:00:00")


def test_earlier_initialization_with_long_enough_duration_accepts_saved_background():
    start = "2025-07-19_05:54:40"
    window = intake.effective_production_window(
        "run_days = 0,\nrun_hours = 0,\nrun_minutes = 2,\nrun_seconds = 0,\n", start)
    assert window["effective_stop_time"] == "2025-07-19_05:56:40"
    intake.assert_saved_times_within_production_window(
        ["2025-07-19_05:55:40", "2025-07-19_05:56:40"],
        window["effective_start_time"], window["effective_stop_time"])


def test_saved_times_after_effective_stop_are_rejected_inclusive_at_stop():
    start = "2025-07-19_05:54:40"
    window = intake.effective_production_window(
        "run_minutes = 2,\nrun_seconds = 0,\n", start)
    intake.assert_saved_times_within_production_window(
        ["2025-07-19_05:56:40"], window["effective_start_time"], window["effective_stop_time"])
    with pytest.raises(ValueError, match="exceed effective production stop"):
        intake.assert_saved_times_within_production_window(
            ["2025-07-19_05:56:41"], window["effective_start_time"], window["effective_stop_time"])


def test_terminal_background_allows_local_observation_slot_beyond_saved_stop():
    background = "2025-07-19_05:55:40"
    local_slot = datetime.strptime(background, intake.TIME_FORMAT) + timedelta(seconds=20)
    window = intake.effective_production_window(
        "run_days = 0,\nrun_hours = 0,\nrun_minutes = 0,\nrun_seconds = 0,\n"
        "end_year = 2025,\nend_month = 7,\nend_day = 19,\nend_hour = 5,\n"
        "end_minute = 55,\nend_second = 40,\n", background)
    assert window["effective_stop_time"] == background
    assert local_slot.strftime(intake.TIME_FORMAT) == "2025-07-19_05:56:00"
    assert local_slot > datetime.strptime(window["effective_stop_time"], intake.TIME_FORMAT)
    intake.assert_saved_times_within_production_window(
        [background], window["effective_start_time"], window["effective_stop_time"])


def test_full_run_case_rejects_post_stop_saved_time_before_loading_private_helpers(tmp_path, monkeypatch):
    """Integration guard: Times metadata is checked before P8W/native reader loading."""
    helper_path = (Path(__file__).resolve().parents[1]
                   / "pr407_native_saved_time_bound_2026-10-11/test_native_case_intake_v4.py")
    helper_spec = importlib.util.spec_from_file_location("pr407_v3_synthetic_helpers", helper_path)
    helper = importlib.util.module_from_spec(helper_spec)
    assert helper_spec.loader is not None
    helper_spec.loader.exec_module(helper)
    helper.intake = intake
    case, case_path, _ = helper.make_case_and_run(
        tmp_path, times=(helper.BG, "2025-07-19_05:56:41"),
        case_id="post_stop_saved_time", start=helper.BG)
    monkeypatch.setattr(intake, "_load_legacy", lambda: pytest.fail("invalid Times must fail before private helper load"))
    with pytest.raises(ValueError, match="exceed effective production stop"):
        intake.load_case(case_path)
    assert not Path(case["output"]["private_npz_path"]).exists()
    assert not Path(case["output"]["manifest_path"]).exists()
