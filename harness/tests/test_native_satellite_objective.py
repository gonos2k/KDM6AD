"""Tests for the fixed-mask, streamed satellite cost and native control step."""

from __future__ import annotations

import numpy as np
import pytest

from harness.native_satellite_objective import (
    active_control_mask,
    build_fixed_support,
    bounded_control_step,
    check_trial_support,
    cost_decreased,
    finalize_objective,
    global_normalizer,
    objective_chunk,
    restrict_control_blocks,
    slice_fixed_support,
)


def test_restricted_step_keeps_original_norm_when_maximum_block_is_frozen():
    baseline = np.zeros((2, 4, 1), dtype=np.float64)
    gradient = np.array([10.0, 5.0, 2.0, 1.0] * 2).reshape(2, 4, 1)
    unit = bounded_control_step(baseline, gradient, np.ones_like(baseline),
                                np.ones_like(baseline, dtype=bool), 1.0)
    original = unit["z"].copy()
    z = restrict_control_blocks(original, np.arange(4), [0], chunk_columns=2)
    assert np.max(np.abs(z)) == 0.2  # It must not become one after projection.
    assert not np.any(z[:, :2])
    assert z[:, 2:].tobytes() == original[:, 2:].tobytes()
    assert unit["z"].tobytes() == original.tobytes()


def test_restricted_blocks_keep_tail_and_full_observation_normalizer():
    z = np.full((2, 7, 2), 0.25, dtype=np.float64)
    support = _support(7)
    old_mask, old_weights = support["m0"].copy(), support["weights"].copy()
    projected = restrict_control_blocks(z, np.arange(7), [1], chunk_columns=3)
    assert not np.any(projected[:, 3:6])
    assert projected[:, 6:].tobytes() == z[:, 6:].tobytes()  # unpadded tail
    objective = finalize_objective([14.0], support["Z_partial"], projected,
                                   np.ones_like(z, dtype=bool))
    assert objective["Z"] == 14.0
    assert objective["regularization_numerator"] == 0.5 * (2 * 4 * 2) * 0.25**2
    assert np.array_equal(support["m0"], old_mask)
    assert np.array_equal(support["weights"], old_weights)


@pytest.mark.parametrize("blocks", [[0, 0], [-1], [3], [True]])
def test_restricted_step_refuses_ambiguous_or_out_of_range_blocks(blocks):
    with pytest.raises(ValueError, match="frozen_blocks"):
        restrict_control_blocks(np.zeros((2, 7, 2)), np.arange(7), blocks,
                                chunk_columns=3)


def test_restricted_step_refuses_reordered_native_rows():
    with pytest.raises(ValueError, match="flat_indices"):
        restrict_control_blocks(np.zeros((2, 3, 2)), np.array([1, 0, 2]), [0])


def test_restricted_projection_preserves_signed_zero_outside_frozen_blocks():
    direction = -np.zeros((2, 4, 1), dtype=np.float64)
    direction[:, 3, :] = -0.25
    projected = restrict_control_blocks(direction, np.arange(4), [0], chunk_columns=2)
    assert not np.signbit(projected[:, :2]).any()  # Explicit frozen +0.0.
    assert np.signbit(projected[:, 2]).all()  # Retain the declared d0's -0.0.
    assert projected[:, 2:].tobytes() == direction[:, 2:].tobytes()


def _support(n, *, baseline_bad=None, owner_ids=None, bt=None):
    dqf = np.zeros((n, 2), dtype=np.int16)
    qc = np.zeros_like(dqf)
    quality = np.zeros_like(dqf)
    if baseline_bad:
        for row, channel in baseline_bad:
            quality[row, channel] = 1
    obs = np.zeros((n, 2), dtype=np.float64) if bt is None else bt
    return build_fixed_support(
        dqf,
        qc,
        np.ones(n, dtype=np.bool_),
        quality,
        obs,
        owner_ids=owner_ids,
    )


def test_duplicate_source_owner_is_weighted_before_model_quality():
    owners = np.array([["pixel-1"], ["pixel-1"], ["pixel-2"]], dtype=object)
    support = build_fixed_support(
        np.zeros((3, 1), dtype=np.uint8),
        np.zeros((3, 1), dtype=np.uint8),
        np.ones(3, dtype=np.bool_),
        np.array([[0], [1], [0]], dtype=np.uint8),
        np.zeros((3, 1), dtype=np.float64),
        owner_ids=owners,
    )
    np.testing.assert_array_equal(support["owner_weight"], [[0.5], [0.5], [1.0]])
    np.testing.assert_array_equal(support["weights"], [[0.5], [0.0], [1.0]])
    assert support["Z_partial"] == 1.5


def test_owner_weights_are_frozen_globally_before_chunk_slicing():
    support = build_fixed_support(
        np.zeros((3, 1), dtype=np.uint8),
        np.zeros((3, 1), dtype=np.uint8),
        np.ones(3, dtype=np.bool_),
        np.zeros((3, 1), dtype=np.uint8),
        np.zeros((3, 1), dtype=np.float64),
        owner_ids=np.array([[91], [91], [92]], dtype=np.int64),
    )
    blocks = [slice_fixed_support(support, 0, 1), slice_fixed_support(support, 1, 3)]
    np.testing.assert_array_equal(blocks[0]["weights"], [[0.5]])
    np.testing.assert_array_equal(blocks[1]["weights"], [[0.5], [1.0]])
    assert global_normalizer(blocks) == support["Z_partial"] == 2.0


def test_trial_must_keep_baseline_support_but_new_quality_entries_are_ignored():
    support = _support(2, baseline_bad=[(1, 0)])
    trial_quality = np.array([[0, 0], [0, 0]], dtype=np.int16)
    trial_bt = np.ones((2, 2), dtype=np.float64)
    result = check_trial_support(support, trial_quality, trial_bt)
    np.testing.assert_array_equal(result["m0"], support["m0"])
    assert result["newly_valid_ignored"] == 1

    lost = trial_quality.copy()
    lost[0, 1] = 4
    with pytest.raises(ValueError, match="loses 1 baseline-supported"):
        check_trial_support(support, lost, trial_bt)


def test_nonfinite_trial_values_are_allowed_only_outside_frozen_support():
    support = _support(1, baseline_bad=[(0, 1)])
    trial_quality = np.array([[0, 1]], dtype=np.int16)
    trial_bt = np.array([[280.0, np.nan]], dtype=np.float64)
    check_trial_support(support, trial_quality, trial_bt)
    trial_bt[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite on all baseline-supported"):
        check_trial_support(support, trial_quality, trial_bt)


def test_all_zero_baseline_support_is_rejected():
    with pytest.raises(ValueError, match="no fixed-support"):
        build_fixed_support(
            np.zeros((2, 1), dtype=np.uint8),
            np.zeros((2, 1), dtype=np.uint8),
            np.ones(2, dtype=np.bool_),
            np.ones((2, 1), dtype=np.uint8),
            np.zeros((2, 1), dtype=np.float64),
        )


def test_empty_model_quality_block_contributes_zero_but_global_support_remains_valid():
    dqf = np.zeros((3, 1), dtype=np.uint8)
    qc = np.zeros_like(dqf)
    quality = np.array([[0], [1], [0]], dtype=np.uint8)
    whole = build_fixed_support(
        dqf,
        qc,
        np.ones(3, dtype=np.bool_),
        quality,
        np.zeros((3, 1), dtype=np.float64),
    )
    empty = build_fixed_support(
        dqf[1:2],
        qc[1:2],
        np.ones(1, dtype=np.bool_),
        quality[1:2],
        np.zeros((1, 1), dtype=np.float64),
        allow_empty=True,
    )
    empty_part = objective_chunk(
        np.array([[np.nan]], dtype=np.float64),
        np.array([[np.nan]], dtype=np.float64),
        empty,
    )
    assert empty["Z_partial"] == 0.0
    assert empty_part["numerator"] == 0.0
    np.testing.assert_array_equal(empty_part["bt_cotangent_numerator"], [[0.0]])
    assert (
        global_normalizer(
            [slice_fixed_support(whole, 0, 1), empty, slice_fixed_support(whole, 2, 3)]
        )
        == 2.0
    )


def test_finite_observations_are_required_only_on_fixed_support():
    obs = np.array([[0.0, np.nan]], dtype=np.float64)
    support = build_fixed_support(
        np.array([[0, 1]], dtype=np.uint8),
        np.zeros((1, 2), dtype=np.uint8),
        np.ones(1, dtype=np.bool_),
        np.zeros((1, 2), dtype=np.uint8),
        obs,
    )
    assert support["Z_partial"] == 1.0


def test_objective_chunk_returns_unnormalized_huber_numerator_and_cotangent():
    support = _support(2)
    pred = np.array([[0.5, 2.0], [-0.5, -3.0]], dtype=np.float64)
    obs = np.zeros_like(pred)
    part = objective_chunk(pred, obs, support)
    # Huber(0.5)=0.125; Huber(2)=1.5; Huber(-0.5)=0.125; Huber(-3)=2.5.
    assert part["numerator"] == 4.25
    np.testing.assert_array_equal(
        part["bt_cotangent_numerator"], [[0.5, 1.0], [-0.5, -1.0]]
    )


def test_chunk_tail_452_sums_with_512_without_per_chunk_averaging():
    full = _support(512)
    tail = _support(452)
    full_part = objective_chunk(np.full((512, 2), 0.5), np.zeros((512, 2)), full)
    tail_part = objective_chunk(np.full((452, 2), 0.5), np.zeros((452, 2)), tail)
    Z = global_normalizer([full, tail])
    result = finalize_objective(
        [tail_part["numerator"], full_part["numerator"]],
        Z,
        np.zeros((1,)),
        np.ones((1,), dtype=np.bool_),
    )
    assert full_part["numerator"] == 128.0
    assert tail_part["numerator"] == 113.0
    assert Z == 2.0 * (512 + 452)
    assert result["cost"] == 0.125


def test_regularization_is_added_once_before_single_global_division():
    support = _support(2)
    part = objective_chunk(np.ones((2, 2)), np.zeros((2, 2)), support)
    result = finalize_objective(
        [part["numerator"], 0.0], 4.0, np.array([3.0, 0.0]), np.array([True, False])
    )
    assert part["numerator"] == 2.0
    assert result["regularization_numerator"] == 4.5
    assert result["numerator"] == 6.5
    assert result["cost"] == 1.625


def test_active_controls_include_admitted_t_and_positive_qv_only():
    m0 = np.array([[True, False], [False, False], [True, True]])
    qv = np.array([[0.0, 1e-4], [2e-4, 0.0], [0.0, 3e-4]])
    active = active_control_mask(m0, qv)
    np.testing.assert_array_equal(
        active[0], [[True, True], [False, False], [True, True]]
    )
    np.testing.assert_array_equal(
        active[1], [[False, True], [False, False], [False, True]]
    )


def test_bounded_control_trials_scale_gradient_freeze_zero_and_start_at_baseline():
    baseline = np.array([10.0, 0.0, 20.0], dtype=np.float64)
    gradient = np.array([2.0, -99.0, -1.0], dtype=np.float64)
    scale = np.array([0.5, 3.0, 2.0], dtype=np.float64)
    active = np.array([True, False, True])
    one = bounded_control_step(baseline, gradient, scale, active, 1.0)
    half = bounded_control_step(baseline, gradient, scale, active, 0.5)
    quarter = bounded_control_step(baseline, gradient, scale, active, 0.25)
    np.testing.assert_array_equal(one["scaled_gradient"], [1.0, 0.0, -2.0])
    np.testing.assert_array_equal(one["direction_z"], [-0.5, 0.0, 1.0])
    np.testing.assert_array_equal(one["candidate"], [9.75, 0.0, 22.0])
    np.testing.assert_array_equal(half["candidate"], [9.875, 0.0, 21.0])
    np.testing.assert_array_equal(quarter["candidate"], [9.9375, 0.0, 20.5])
    np.testing.assert_array_equal(
        half["candidate"] - baseline, 0.5 * (one["candidate"] - baseline)
    )
    assert np.array_equal(one["z"][~active], [0.0])


def test_cost_acceptance_uses_explicit_absolute_and_relative_tolerance():
    base = 2.0
    threshold = 1e-10 + 1e-12 * abs(base)
    assert not cost_decreased(base, base - threshold / 2)["decreased"]
    accepted = cost_decreased(base, base - 2 * threshold)
    assert accepted["decreased"]
    assert accepted["required_decrease"] == threshold


def test_support_and_control_helpers_reject_invalid_shapes_or_frozen_updates():
    support = _support(1)
    with pytest.raises(ValueError, match="matching 2-D shape"):
        objective_chunk(np.zeros((1, 1)), np.zeros((1, 1)), support)
    with pytest.raises(ValueError, match="exactly zero in frozen"):
        finalize_objective([0.0], 2.0, np.array([1.0, 2.0]), np.array([True, False]))
    with pytest.raises(ValueError, match="positive scale"):
        bounded_control_step(
            np.zeros(1), np.ones(1), np.zeros(1), np.ones(1, bool), 1.0
        )
