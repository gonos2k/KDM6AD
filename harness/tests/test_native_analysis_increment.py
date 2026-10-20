from dataclasses import replace

import numpy as np
import pytest
try:
    import torch
except ImportError:
    torch = None

from harness.native_analysis_increment import (
    HOST_ALPHA,
    HOST_ALPHA_BITS,
    THETA_COORDINATE,
    AnalysisStamp,
    ThermodynamicState,
    encode_native_increment,
    theta_m_jvp,
    theta_m_total,
    theta_m_vjp,
)


def _state(theta, qv, *, checkpoint="bg-120", background=None, model="2025-07-19_00:02:00", analysis=None,
           geometry="native-234x282x39", layout="i,k,j", use_theta_m=True,
           theta_units="K", qv_units="kg kg-1 dry air"):
    stamp = AnalysisStamp(
        model_valid_time=model,
        analysis_valid_time=analysis or model,
        geometry_id=geometry,
        checkpoint_id=checkpoint,
        background_checkpoint_id=background,
        native_layout=layout,
        use_theta_m=use_theta_m,
        theta_dry_units=theta_units,
        qv_units=qv_units,
    )
    return ThermodynamicState(np.asarray(theta), np.asarray(qv), stamp)


def test_increment_maps_dry_theta_and_qv_posterior_to_native_theta_m_and_qv():
    theta_b = np.array([290.0, 301.0], dtype=np.float64)
    qv_b = np.array([0.003, 0.010], dtype=np.float64)
    theta_a = theta_b + np.array([0.2, -0.1])
    qv_a = qv_b + np.array([0.0001, -0.0002])
    bg = _state(theta_b, qv_b)
    post = _state(theta_a, qv_a, checkpoint="posterior-120", background="bg-120")

    encoded = encode_native_increment(bg, post)
    expected = theta_a * (1.0 + HOST_ALPHA * qv_a) - theta_b * (1.0 + HOST_ALPHA * qv_b)
    np.testing.assert_allclose(encoded.delta_theta_m, expected, rtol=0, atol=1e-13)
    np.testing.assert_array_equal(encoded.delta_t_2, encoded.delta_theta_m)
    np.testing.assert_array_equal(encoded.delta_qv, qv_a - qv_b)
    assert not encoded.unchanged_mask.any()
    assert encoded.model_valid_time == bg.stamp.model_valid_time
    assert encoded.background_checkpoint_id == "bg-120"


def test_exactly_unchanged_analysis_cells_are_zero_pairs_for_noop_transport():
    theta = np.array([290.0, 300.0, 310.0], dtype=np.float64)
    qv = np.array([0.001, 0.002, 0.003], dtype=np.float64)
    bg = _state(theta, qv)
    post = _state(theta.copy(), qv.copy(), checkpoint="post", background="bg-120")
    encoded = encode_native_increment(bg, post)
    assert np.array_equal(encoded.delta_theta_m, np.zeros_like(theta))
    assert np.array_equal(encoded.delta_qv, np.zeros_like(qv))
    assert encoded.unchanged_mask.all()
    np.testing.assert_array_equal(theta, bg.theta_dry)
    np.testing.assert_array_equal(qv, bg.qv)


def test_increment_refuses_analysis_at_a_different_model_valid_time():
    bg = _state([290.0], [0.001], model="2025-07-19_00:02:00")
    post = _state([290.1], [0.001], checkpoint="post", background="bg-120",
                  model="2025-07-19_00:02:00", analysis="2025-07-19_00:00:00")
    with pytest.raises(ValueError, match="model valid time must equal analysis valid time"):
        encode_native_increment(bg, post)


def test_increment_rejects_background_posterior_time_geometry_and_binding_mismatch():
    bg = _state([290.0], [0.001])
    wrong_time = _state([290.1], [0.001], checkpoint="post", background="bg-120",
                        model="2025-07-19_00:04:00")
    with pytest.raises(ValueError, match="model valid times differ"):
        encode_native_increment(bg, wrong_time)
    wrong_geometry = _state([290.1], [0.001], checkpoint="post", background="bg-120",
                            geometry="other-grid")
    with pytest.raises(ValueError, match="geometry identifiers differ"):
        encode_native_increment(bg, wrong_geometry)
    unbound = _state([290.1], [0.001], checkpoint="post", background="some-other-bg")
    with pytest.raises(ValueError, match="not bound"):
        encode_native_increment(bg, unbound)


def test_increment_refuses_shape_layout_and_unit_mismatches():
    bg = _state([290.0, 291.0], [0.001, 0.002])
    with pytest.raises(ValueError, match="profile shapes differ"):
        encode_native_increment(bg, _state([291.0], [0.002], checkpoint="post", background="bg-120"))
    wrong_layout = _state([290.1, 291.1], [0.001, 0.002], checkpoint="post", background="bg-120",
                          layout="k,j,i")
    with pytest.raises(ValueError, match="native_layout"):
        encode_native_increment(bg, wrong_layout)
    wrong_units = _state([290.1, 291.1], [0.001, 0.002], checkpoint="post", background="bg-120",
                         qv_units="kg kg-1 moist air")
    with pytest.raises(ValueError, match="qv_units"):
        encode_native_increment(bg, wrong_units)
    wrong_alpha = _state([290.1, 291.1], [0.001, 0.002], checkpoint="post", background="bg-120")
    wrong_alpha = ThermodynamicState(
        wrong_alpha.theta_dry, wrong_alpha.qv,
        replace(wrong_alpha.stamp, alpha_bits="3FCDDED1"),
    )
    with pytest.raises(ValueError, match="coefficient/coordinate"):
        encode_native_increment(bg, wrong_alpha)


def test_invalid_values_and_theta_coordinate_are_rejected():
    bg = _state([290.0], [0.001])
    for theta, qv, match in [([np.nan], [0.001], "finite"), ([290.0], [-0.001], "nonnegative"),
                             ([0.0], [0.001], "positive absolute")]:
        bad = _state(theta, qv, checkpoint="bad", background="bg-120")
        with pytest.raises(ValueError, match=match):
            encode_native_increment(bg, bad)
    unsupported = _state([290.1], [0.001], checkpoint="post", background="bg-120", use_theta_m=False)
    with pytest.raises(ValueError, match="USE_THETA_M=1"):
        encode_native_increment(bg, unsupported)


def test_dry_theta_to_moist_theta_jvp_matches_independent_central_difference():
    if torch is None:
        pytest.skip("Torch is optional for NumPy native-increment consumers")
    theta = torch.tensor([289.0, 305.0], dtype=torch.float64)
    qv = torch.tensor([0.002, 0.012], dtype=torch.float64)
    dtheta = torch.tensor([0.3, -0.2], dtype=torch.float64)
    dqv = torch.tensor([1.0e-4, -2.0e-4], dtype=torch.float64)
    tangent = theta_m_jvp(theta, qv, dtheta, dqv)
    eps = 1.0e-6
    plus = theta_m_total(theta + eps * dtheta, qv + eps * dqv)
    minus = theta_m_total(theta - eps * dtheta, qv - eps * dqv)
    fd = (plus - minus) / (2.0 * eps)
    torch.testing.assert_close(tangent, fd, rtol=5e-8, atol=1e-8)


def test_dry_theta_to_moist_theta_vjp_satisfies_dot_product_and_autograd():
    if torch is None:
        pytest.skip("Torch is optional for NumPy native-increment consumers")
    theta = torch.tensor([290.0, 300.0], dtype=torch.float64, requires_grad=True)
    qv = torch.tensor([0.004, 0.009], dtype=torch.float64, requires_grad=True)
    dtheta = torch.tensor([0.2, -0.4], dtype=torch.float64)
    dqv = torch.tensor([-0.0003, 0.0001], dtype=torch.float64)
    seed = torch.tensor([0.7, -1.2], dtype=torch.float64)
    jvp = theta_m_jvp(theta, qv, dtheta, dqv)
    bar_theta, bar_qv = theta_m_vjp(theta, qv, seed)
    lhs = torch.dot(seed, jvp)
    rhs = torch.dot(bar_theta, dtheta) + torch.dot(bar_qv, dqv)
    torch.testing.assert_close(lhs, rhs, rtol=1e-14, atol=1e-14)

    value = theta_m_total(theta, qv)
    auto_theta, auto_qv = torch.autograd.grad(value, (theta, qv), grad_outputs=seed)
    torch.testing.assert_close(auto_theta, bar_theta, rtol=0, atol=0)
    torch.testing.assert_close(auto_qv, bar_qv, rtol=1e-15, atol=1e-13)


def test_host_alpha_is_captured_binary32_quotient_and_stamped_coordinate():
    captured = np.float32(np.float32(461.6) / np.float32(287.0))
    assert int(np.asarray(captured).view(np.uint32)) == int(HOST_ALPHA_BITS, 16)
    assert HOST_ALPHA == float(captured)
    assert THETA_COORDINATE.endswith(HOST_ALPHA_BITS)


def test_derivative_contract_rejects_broadcasting_mismatches():
    if torch is None:
        pytest.skip("Torch is optional for Torch derivative contract tests")
    theta = torch.tensor([290.0, 300.0], dtype=torch.float64)
    qv = torch.tensor([0.004, 0.009], dtype=torch.float64)
    with pytest.raises(ValueError, match="match shape, device, and dtype"):
        theta_m_jvp(theta, qv, torch.tensor([1.0], dtype=torch.float64),
                    torch.tensor([0.0, 0.0], dtype=torch.float64))
