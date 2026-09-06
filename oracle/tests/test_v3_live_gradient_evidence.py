"""V3 evidence inventory gate for the pinned private GK2A/KDM6 assets.

The live RTTOV derivative run is deliberately a command-line evidence action;
this test only checks the read-only real asset boundary.  Public clones skip
because these files are private.  RTTOV fixture tests remain wiring-only and
are not substituted for this geometry/collocation check.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import torch

from scripts.v3_live_gradient_evidence import (  # noqa: E402
    DEFAULT_CAL,
    DEFAULT_GK2A,
    DEFAULT_KDM,
    DEFAULT_STAMP,
    build_inventory,
    _direction_status,
    _relative_positive_direction,
    _select_columns,
)


_REAL_PRESENT = DEFAULT_KDM.is_file() and DEFAULT_GK2A.is_dir() and DEFAULT_CAL.is_file()


def test_explicit_column_selection_preserves_validated_candidate_boundary():
    ranked = [(9, 0.02), (3, 0.001)]
    assert _select_columns(ranked, 1) == [9]
    assert _select_columns(ranked, 1, 3) == [3]
    with pytest.raises(ValueError, match="not an assigned"):
        _select_columns(ranked, 1, 5)
    with pytest.raises(ValueError, match="max_profiles=1"):
        _select_columns(ranked, 2, 3)
    with pytest.raises(ValueError, match="positive"):
        _select_columns(ranked, 0)


def test_direction_evidence_requires_observations_signal_and_output_resolution():
    row = dict(same_mask=True, input_admissible=True,
               resolution_status="resolved", central_FD_J=2.0,
               relative_error_vs_AD=0.0, fd_output_rounding_bound=0.001)
    assert _direction_status(2.0, [row], 1) == "pass"
    assert _direction_status(2.0, [row], 0) == "unresolved"
    assert _direction_status(0.0, [row], 1) == "unresolved"
    assert _direction_status(float("nan"), [row], 1) == "unresolved"
    assert _direction_status(2.0, [], 1) == "unresolved"
    for change in ({"same_mask": False}, {"resolution_status": "unresolved"},
                   {"central_FD_J": float("inf")}, {"relative_error_vs_AD": 0.2},
                   {"fd_output_rounding_bound": 1.0},
                   {"fd_output_rounding_bound": None}):
        assert _direction_status(2.0, [{**row, **change}], 1) == "unresolved"
    assert _direction_status(2.0, [{k: v for k, v in row.items()
                                    if k != "input_admissible"}], 1) == "unresolved"
    assert _direction_status(2.0, [{**row, "input_admissible": False}], 1) == "unresolved"


def test_relative_positive_direction_rejects_invalid_fraction_or_reference():
    reference = torch.ones((2, 2), dtype=torch.float64)
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        _relative_positive_direction(reference, seed=1, fractional_max=1.1)
    with pytest.raises(ValueError, match="nonnegative"):
        _relative_positive_direction(-reference, seed=1, fractional_max=0.1)


@pytest.mark.skipif(not _REAL_PRESENT, reason="private GK2A/KDM/calibration assets unavailable")
def test_pinned_real_inventory_has_usable_collocated_ir_columns():
    report = build_inventory(DEFAULT_KDM, DEFAULT_GK2A, DEFAULT_CAL, DEFAULT_STAMP,
                             stride=8, max_dist_km=4.0)
    assert report["status"] == "inventory_ok"
    assert report["frame"]["valid_time_utc"] == "2025-07-19_00:00:00"
    assert report["observation"]["valid_time_utc"] == DEFAULT_STAMP
    assert report["frame"]["shape"] == [65988, 39]
    assert report["collocation"]["n_assigned"] > 0
    assert report["collocation"]["n_dropped_collision"] == 0
    assert report["collocation"]["assigned_usable_clean_ir"] > 0
    assert report["observation"]["bias_present"] is False
    assert report["observation"]["channel_gate_present"] is False


@pytest.mark.skipif(not _REAL_PRESENT, reason="private GK2A/KDM/calibration assets unavailable")
def test_pinned_real_kdm_step_is_finite_for_selected_columns():
    """Exercise the real-frame KDM map that the optional V3 live run composes."""
    from kdm6.io.frame_reader import read_wrfout_frame
    from kdm6.runtime import kdm6_step
    from scripts.v3_live_gradient_evidence import _state_subset

    frame = read_wrfout_frame(str(DEFAULT_KDM), 0, nccn_policy="init_profile")
    state, forcing, xland = _state_subset(frame, [470, 474])
    evolved, handle = kdm6_step(state, forcing, dt=20.0, value_only=True, xland=xland)
    handle.close()
    assert all(bool(field.isfinite().all()) for field in evolved)
    assert evolved.th.shape == state.th.shape
