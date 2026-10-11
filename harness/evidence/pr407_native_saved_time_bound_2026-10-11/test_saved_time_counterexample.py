"""Exact reviewer counterexample; synthetic NetCDF, no private native helpers."""
import importlib.util
from pathlib import Path

import pytest


PACKET = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("exact_stop_counterexample_helpers", PACKET / "test_native_case_intake_v4.py")
helper = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(helper)


def test_july20_saved_state_rejected_after_july19_one_minute_run(tmp_path, monkeypatch):
    initial, background, slot = "2025-07-19_00:00:00", "2025-07-20_05:55:40", "2025-07-20_05:56:00"
    run = tmp_path / "one_minute_producer"
    helper.make_run_receipts(run, run_id=run.name, start_date=initial, minutes=1)
    helper.make_forecast(run / "klfs_lc05_fcst.202507190000", times=(background,))
    case = helper.case_template(run.name, run, initial, case_id="exact_july20_outside_producer_run",
                               output_dir=tmp_path / "outputs", background=background, slot=slot)
    helper.refresh_completion_receipt(run, case)
    path = helper.write_case(tmp_path / "CASE.json", case)
    gate = helper.intake._completion_gate(helper.intake.validate_case(case))
    assert gate["effective_stop_time"] == "2025-07-19_00:01:00"
    excess = (helper.intake.parse_time(background, "saved") -
              helper.intake.parse_time(gate["effective_stop_time"], "producer_stop")).total_seconds()
    assert excess == 107680
    monkeypatch.setattr(helper.intake, "_load_legacy", lambda: pytest.fail("invalid archive must fail before private helper loading"))
    with pytest.raises(ValueError, match="exceed effective production stop"):
        helper.intake.load_case(path)
    assert not Path(case["output"]["manifest_path"]).exists()
    assert not Path(case["output"]["private_npz_path"]).exists()
