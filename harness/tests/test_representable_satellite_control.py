"""Actual-state/prior and flat/native layout checks, without model execution."""
import numpy as np
import pytest

from harness.native_analysis_control import apply_pair
from harness.native_satellite_objective import (
    finalize_objective,
    prepare_representable_control,
)


def fields():
    # Non-square horizontal layout distinguishes i and j; each layer differs.
    theta = np.arange(12, dtype=np.float32).reshape(6, 2) + np.float32(270)
    qv = (np.arange(12, dtype=np.float32).reshape(6, 2) + 1) / np.float32(1024)
    return np.stack((theta, qv)).astype(np.float64)


def test_effective_state_matches_independent_scalar_wire_application_and_prior():
    baseline = fields()
    active = np.ones_like(baseline, dtype=bool)
    z = np.zeros_like(baseline)
    z[0, 0, 0] = 1e-7  # requested nonzero, below half a native ULP
    z[0, 4, 1] = -0.35
    z[1, 1, 0] = 0.73
    saved_baseline, saved_z = baseline.copy(), z.copy()
    result = prepare_representable_control(baseline, z, active, horizontal_shape=(2, 3), background_checkpoint_id="b" * 64)
    expected = baseline.copy()
    expected[0, 4, 1], expected[1, 4, 1] = apply_pair(
        *baseline[:, 4, 1], -0.2 * 0.35, 0.0)
    expected[0, 1, 0], expected[1, 1, 0] = apply_pair(
        *baseline[:, 1, 0], 0.0, 0.02 * baseline[1, 1, 0] * 0.73)
    assert result["candidate"].tobytes() == expected.tobytes()
    assert result["counts"]["requested_points"] == 3
    assert result["counts"]["applied_points"] == 2
    assert result["counts"]["noop_points"] == 1
    assert result["wire_delta"][0, 0, 0] == 0.0
    scales = np.stack((np.full_like(baseline[0], 0.2), 0.02 * baseline[1]))
    expected_z = (expected - baseline) / scales
    assert result["z"].tobytes() == expected_z.tobytes()
    cost = finalize_objective([14.0, 3.0], 7.0, result["z"], active)
    assert cost["regularization_numerator"] == 0.5 * sum(x * x for x in expected_z.ravel())
    assert cost["regularization_numerator"] != 0.5 * sum(x * x for x in z.ravel())
    assert baseline.tobytes() == saved_baseline.tobytes()
    assert z.tobytes() == saved_z.tobytes()


def test_all_noop_and_frozen_zero_qv_remain_identity():
    baseline = fields()
    baseline[1, 5, 1] = 0.0
    active = np.ones_like(baseline, dtype=bool)
    active[:, 2] = False
    active[1, 5, 1] = False
    z = np.where(active, 1e-10, 0.0)
    result = prepare_representable_control(baseline, z, active, horizontal_shape=(2, 3), background_checkpoint_id="b" * 64)
    assert result["status"] == "no_applied_update"
    assert result["candidate"].tobytes() == baseline.tobytes()
    assert not np.any(result["z"])
    assert not np.any(result["wire_delta"])


def test_quantization_may_leave_requested_total_box_and_is_rejected():
    baseline = fields()
    # 270f + 0.2f rounds above the exact binary64 upper bound 270 + 0.2.
    z = np.zeros_like(baseline)
    z[0, 0, 0] = 1.0
    with pytest.raises(ValueError, match="total control box"):
        prepare_representable_control(baseline, z, np.ones_like(z, bool),
                                      horizontal_shape=(2, 3), background_checkpoint_id="b" * 64)


@pytest.mark.parametrize("kind", ["layout", "frozen", "qv0", "bounds", "not_native"])
def test_invalid_control_contract_rejected(kind):
    baseline = fields()
    active = np.ones_like(baseline, bool)
    z = np.zeros_like(baseline)
    shape = (2, 3)
    if kind == "layout":
        shape = (3, 3)
    elif kind == "frozen":
        active[0, 2, 1] = False
        z[0, 2, 1] = 0.2
    elif kind == "qv0":
        baseline[1, 2, 1] = 0.0
    elif kind == "bounds":
        z[0, 0, 0] = 1.01
    else:
        baseline[0, 0, 0] += 1e-7
    with pytest.raises(ValueError):
        prepare_representable_control(baseline, z, active, horizontal_shape=shape, background_checkpoint_id="b" * 64)


def test_evaluator_uses_effective_input_and_original_support_at_recorded_point(monkeypatch, tmp_path):
    from harness import run_native_satellite_case as runner
    from harness.native_satellite_objective import objective_chunk

    baseline = fields()
    baseline[0, 1, 0] = -0.0
    z = np.full_like(baseline, 0.37)
    z[0, 1, 0] = 0.0
    active = np.ones_like(z, bool)
    control = prepare_representable_control(baseline, z, active, horizontal_shape=(2, 3), background_checkpoint_id="b" * 64)
    flat = np.array([1, 4])
    block = {"flat_indices": flat, "theta_m": baseline[0, flat], "qv": baseline[1, flat]}
    support = {"m0": np.ones((2, 1), bool), "weights": np.ones((2, 1))}
    calls = []

    def existing_evaluator(config, block, workspace, *, record, baseline, delta, z, effective_input):
        assert record is True and baseline is support
        calls.append(1)
        theta, qv = effective_input
        cost = objective_chunk(theta[:, :1], np.full((2, 1), 272.0), baseline)
        return {"theta_m": theta, "qv": qv, "z": z}, {"observation_numerator": cost["numerator"]}

    monkeypatch.setattr(runner, "evaluate_block", existing_evaluator)
    arrays, metadata = runner.evaluate_representable_block(
        {"verified_sources": {"checkpoint": {"sha256": "b" * 64}}}, block, tmp_path, record=True, baseline=support, control=control)
    assert calls == [1]
    assert arrays["theta_m"].tobytes() == control["candidate"][0, flat].tobytes()
    assert np.signbit(arrays["theta_m"][0, 0])
    assert arrays["qv"].tobytes() == control["candidate"][1, flat].tobytes()
    assert arrays["z"].tobytes() == control["z"][:, flat].tobytes()
    effective = finalize_objective([metadata["observation_numerator"]], 2, arrays["z"], active[:, flat])
    requested = finalize_objective([metadata["observation_numerator"]], 2, z[:, flat], active[:, flat])
    assert effective["cost"] != requested["cost"]
    assert metadata["control_application"]["quantizer_differentiated"] is False


def test_evaluator_rejects_mismatched_effective_input_before_model(monkeypatch, tmp_path):
    from harness import run_native_satellite_case as runner
    baseline = fields()
    z = np.full_like(baseline, 0.37)
    control = prepare_representable_control(baseline, z, np.ones_like(z, bool), horizontal_shape=(2, 3), background_checkpoint_id="b" * 64)
    control["applied_delta"][0, 0, 0] += 0.01
    monkeypatch.setattr(runner, "evaluate_block", lambda *a, **k: pytest.fail("must reject before model"))
    block = {"flat_indices": np.arange(6), "theta_m": baseline[0], "qv": baseline[1]}
    with pytest.raises(ValueError, match="not reproducible"):
        runner.evaluate_representable_block({"verified_sources": {"checkpoint": {"sha256": "b" * 64}}}, block, tmp_path, record=False, baseline={}, control=control)


def test_evaluator_rejects_requested_z_substituted_for_effective_prior(monkeypatch, tmp_path):
    from harness import run_native_satellite_case as runner
    baseline = fields()
    z = np.full_like(baseline, 0.37)
    control = prepare_representable_control(baseline, z, np.ones_like(z, bool), horizontal_shape=(2, 3), background_checkpoint_id="b" * 64)
    control["z"] = z
    monkeypatch.setattr(runner, "evaluate_block", lambda *a, **k: pytest.fail("must reject before model"))
    block = {"flat_indices": np.arange(6), "theta_m": baseline[0], "qv": baseline[1]}
    with pytest.raises(ValueError, match="prior coordinate"):
        runner.evaluate_representable_block({"verified_sources": {"checkpoint": {"sha256": "b" * 64}}}, block, tmp_path, record=False, baseline={}, control=control)


def test_evaluator_cannot_change_full_background_with_identical_tq(monkeypatch, tmp_path):
    from harness import run_native_satellite_case as runner
    baseline = fields()
    z = np.full_like(baseline, 0.37)
    control = prepare_representable_control(baseline, z, np.ones_like(z, bool),
        horizontal_shape=(2, 3), background_checkpoint_id="b" * 64)
    monkeypatch.setattr(runner, "evaluate_block", lambda *a, **k: pytest.fail("must reject before model"))
    block = {"flat_indices": np.arange(6), "theta_m": baseline[0], "qv": baseline[1]}
    other_config = {"verified_sources": {"checkpoint": {"sha256": "c" * 64}}}
    with pytest.raises(ValueError, match="same complete background checkpoint"):
        runner.evaluate_representable_block(other_config, block, tmp_path,
                                            record=False, baseline={}, control=control)
