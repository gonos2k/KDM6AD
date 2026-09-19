"""Regression evidence for the pinned clear-column positivity boundary."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.diagnose_clear_gradient_boundary import (
    DEFAULT_CAL,
    DEFAULT_GK2A,
    DEFAULT_KDM,
    DEFAULT_STAMP,
    _classify_observed_boundary,
    run_diagnostic,
)


_REAL_PRESENT = DEFAULT_KDM.is_file() and DEFAULT_GK2A.is_dir() and DEFAULT_CAL.is_file()


@pytest.mark.skipif(not _REAL_PRESENT, reason="private GK2A/KDM/calibration assets unavailable")
def test_pinned_clear_qv_probe_localizes_large_fd_to_positivity_branch(tmp_path: Path):
    report = run_diagnostic(
        DEFAULT_KDM, DEFAULT_GK2A, DEFAULT_CAL, DEFAULT_STAMP,
        column=20004, stride=8, max_dist_km=4.0, eps=(0.03, 0.1),
        out_path=tmp_path / "clear-boundary.json")

    assert report["conclusion"]["classification"] == "expected_nonsmooth_boundary"
    assert all(value is None for value in
               report["branch_trace"]["first_signature_difference_from_base"].values())
    rows = report["independent_profile"]["eps"]
    assert report["branch_trace"]["first_qv_zero_mask_boundary_from_base"]["plus-0.1"]["stage"] == "state_update"
    assert report["branch_trace"]["first_qv_zero_mask_boundary_from_base"]["minus-0.1"]["stage"] == "state_update"
    assert rows["0.03"]["plus"]["qv_out_zero_count"] == 0
    assert rows["0.03"]["minus"]["qv_out_zero_count"] == 0
    assert rows["0.1"]["plus"]["qv_out_zero_count"] > 0
    assert rows["0.1"]["minus"]["qv_out_zero_count"] > 0
    assert rows["0.03"]["abs_error"] < 0.02
    positive = report["independent_profile_positive_tangent"]["eps"]
    assert all(row["plus"]["qv_in_negative_count"] == 0 and
               row["minus"]["qv_in_negative_count"] == 0
               for row in positive.values())
    assert all(row["plus"]["qv_out_zero_count"] == 0 and
               row["minus"]["qv_out_zero_count"] == 0
               for row in positive.values())
    assert report["conclusion"]["source"].endswith(":1366")


def test_boundary_classifier_is_data_driven_for_stable_and_changed_traces():
    stable = {"plus-0.1": None, "minus-0.1": None}
    assert _classify_observed_boundary(stable)["classification"] == "cause_unresolved"
    changed = {"plus-0.1": {"stage": "test_stage", "side": "out",
                            "base_mask": [False], "candidate_mask": [True]}}
    result = _classify_observed_boundary(changed)
    assert result["classification"] == "observed_boundary_unattributed"
    assert result["first_changed_stage"] == "test_stage"
