import pytest
import torch

from kdm6.native_finish import (
    FinishConfig,
    NativeFinishResult,
    ThermoState,
    ZeroOutConfig,
    native_finish,
    native_finish_jvp,
    native_finish_vjp,
    post_microphysics_thermo,
    post_microphysics_jvp,
    post_microphysics_vjp,
)


DTYPE = torch.float64
CONFIG = FinishConfig(dt=20.0, alpha=461.6 / 287.0, t0=300.0, mp_tend_lim=0.1)


def state(th, qv, qc):
    return ThermoState(
        torch.tensor(th, dtype=DTYPE),
        torch.tensor(qv, dtype=DTYPE),
        torch.tensor(qc, dtype=DTYPE),
    )


def add_scaled(x, dx, scale):
    return ThermoState(*(a + scale * b for a, b in zip(x, dx)))


def dot_result(a: NativeFinishResult, b: NativeFinishResult):
    return sum((x * y).sum() for x, y in zip(a, b))


def dot_state(a: ThermoState, b: ThermoState):
    return sum((x * y).sum() for x, y in zip(a, b))


def test_forward_matches_independent_scalar_equations():
    before = state([[280.0, 282.0], [285.0, 288.0]],
                   [[0.001, 0.002], [0.003, 0.004]],
                   [[1.0e-4, 2.0e-4], [3.0e-4, 4.0e-4]])
    after = state([[280.5, 281.7], [285.9, 287.0]],
                  [[0.0012, 0.0017], [0.0034, 0.0036]],
                  [[1.1e-4, 1.8e-4], [3.4e-4, 3.2e-4]])
    result = native_finish(before, after, CONFIG)

    alpha, dt, t0 = CONFIG.alpha, CONFIG.dt, CONFIG.t0
    expected = [[] for _ in range(5)]
    for index in range(before.th.numel()):
        th0 = before.th.flatten()[index].item()
        qv0 = before.qv.flatten()[index].item()
        qc0 = before.qc.flatten()[index].item()
        th1 = after.th.flatten()[index].item()
        qv1 = after.qv.flatten()[index].item()
        qc1 = after.qc.flatten()[index].item()
        m = min(CONFIG.mp_tend_lim * dt, max(-CONFIG.mp_tend_lim * dt, th1 - th0))
        delta_qv = qv1 - qv0
        b = 1.0 + alpha * qv1
        n = m * b + alpha * delta_qv * th1
        full = th0 * (1.0 + alpha * qv0) + n
        expected[0].append(full - t0)
        expected[1].append(n / dt)
        expected[2].append(delta_qv / dt)
        expected[3].append((qc1 - qc0) / dt)
        expected[4].append(full / b - t0)

    for got, values in zip(result, expected):
        torch.testing.assert_close(got.flatten(), torch.tensor(values, dtype=DTYPE), rtol=0, atol=1e-12)


def test_jvp_matches_central_difference_and_vjp_is_its_adjoint():
    before = state([280.0, 282.0, 285.0], [0.001, 0.002, 0.003], [1e-4, 2e-4, 3e-4])
    after = state([280.5, 281.7, 285.9], [0.0012, 0.0017, 0.0034], [1.1e-4, 1.8e-4, 3.4e-4])
    d_before = state([0.02, -0.01, 0.03], [2e-5, -1e-5, 3e-5], [1e-6, -2e-6, 3e-6])
    d_after = state([-0.01, 0.04, 0.02], [-1e-5, 4e-5, 2e-5], [-3e-6, 2e-6, 1e-6])
    cotangent = NativeFinishResult(*(torch.tensor(v, dtype=DTYPE) for v in (
        [0.3, -0.2, 0.5], [1.2, -0.7, 0.4], [-2.0, 1.0, 0.5],
        [0.2, 0.4, -0.3], [0.7, -0.6, 0.9],
    )))

    tangent = native_finish_jvp(before, after, d_before, d_after, CONFIG)
    # A moderate central step keeps subtraction/rounding small relative to the
    # tiny tendency outputs while remaining inside the same smooth clip branch.
    eps = 1.0e-2
    plus = native_finish(add_scaled(before, d_before, eps), add_scaled(after, d_after, eps), CONFIG)
    minus = native_finish(add_scaled(before, d_before, -eps), add_scaled(after, d_after, -eps), CONFIG)
    for actual, p, m in zip(tangent, plus, minus):
        fd = (p - m) / (2.0 * eps)
        torch.testing.assert_close(actual, fd, rtol=1e-9, atol=1e-11)

    grad_before, grad_after = native_finish_vjp(before, after, cotangent, CONFIG)
    lhs = dot_result(tangent, cotangent)
    rhs = dot_state(d_before, grad_before) + dot_state(d_after, grad_after)
    torch.testing.assert_close(lhs, rhs, rtol=2e-13, atol=2e-13)


def test_explicit_jvp_vjp_match_torch_autograd_inside_clip_branch():
    before = state([280.0, 281.0], [0.001, 0.002], [1e-4, 2e-4])
    after = state([280.5, 281.7], [0.0012, 0.0017], [1.1e-4, 1.8e-4])
    before = ThermoState(*(x.clone().requires_grad_(True) for x in before))
    after = ThermoState(*(x.clone().requires_grad_(True) for x in after))
    cotangent = NativeFinishResult(*(torch.tensor(v, dtype=DTYPE) for v in (
        [0.2, -0.3], [0.7, 0.1], [-0.5, 0.9], [0.4, -0.8], [0.3, 0.6]
    )))
    result = native_finish(before, after, CONFIG)
    scalar = dot_result(result, cotangent)
    auto = torch.autograd.grad(scalar, (*before, *after))
    explicit = native_finish_vjp(before, after, cotangent, CONFIG)
    expected = (*explicit[0], *explicit[1])
    for actual, want in zip(auto, expected):
        torch.testing.assert_close(actual, want, rtol=2e-13, atol=2e-13)


def test_same_state_with_same_direction_has_zero_rate_tangents():
    same = state([280.0, 282.0], [0.001, 0.002], [1e-4, 2e-4])
    direction = state([0.3, -0.2], [2e-5, -1e-5], [3e-6, -2e-6])
    tangent = native_finish_jvp(same, same, direction, direction, CONFIG)
    for name in ("h_rate", "qv_rate", "qc_rate"):
        assert torch.equal(getattr(tangent, name), torch.zeros_like(same.th))


def test_qc_rate_has_negative_before_and_positive_after_identity():
    before = state([280.0], [0.001], [2e-4])
    after = state([280.0], [0.001], [3e-4])
    zero = state([0.0], [0.0], [0.0])
    tangent_before = native_finish_jvp(before, after, zero, state([0.0], [0.0], [1.0]), CONFIG)
    tangent_after = native_finish_jvp(before, after, state([0.0], [0.0], [1.0]), zero, CONFIG)
    torch.testing.assert_close(tangent_before.qc_rate, torch.tensor([1.0 / CONFIG.dt], dtype=DTYPE))
    torch.testing.assert_close(tangent_after.qc_rate, torch.tensor([-1.0 / CONFIG.dt], dtype=DTYPE))


def test_clip_interior_ties_and_exterior_choose_expected_derivative():
    # Bound is 2 K: only the first point is strictly interior. Exact +/-2 ties
    # take the clipped-side derivative, as do points outside the bound.
    before = state([280.0] * 5, [0.001] * 5, [0.0] * 5)
    after = state([280.5, 282.0, 278.0, 283.0, 277.0], [0.001] * 5, [0.0] * 5)
    zero = state([0.0] * 5, [0.0] * 5, [0.0] * 5)
    d_after = state([1.0] * 5, [0.0] * 5, [0.0] * 5)
    result = native_finish_jvp(before, after, zero, d_after, CONFIG)
    expected_g = torch.tensor([1.0, 0.0, 0.0, 0.0, 0.0], dtype=DTYPE)
    expected_h = expected_g * (1.0 + CONFIG.alpha * after.qv) / CONFIG.dt
    torch.testing.assert_close(result.h_rate, expected_h, rtol=0, atol=0)

    zero_bound = FinishConfig(dt=CONFIG.dt, alpha=CONFIG.alpha, t0=CONFIG.t0, mp_tend_lim=0.0)
    all_clipped = native_finish_jvp(before, after, zero, d_after, zero_bound)
    torch.testing.assert_close(all_clipped.h_rate, torch.zeros_like(after.th), rtol=0, atol=0)


def test_upper_and_lower_clipped_branches_match_finite_difference_away_from_ties():
    config = FinishConfig(dt=10.0, alpha=CONFIG.alpha, t0=300.0, mp_tend_lim=0.1)
    before = state([280.0, 281.0], [0.001, 0.002], [1e-4, 2e-4])
    # The cap is 1 K. Both raw increments are clipped with a 1 K margin.
    after = state([282.0, 279.0], [0.0013, 0.0016], [1.2e-4, 1.7e-4])
    d_before = state([0.02, -0.03], [1e-5, -2e-5], [2e-6, -1e-6])
    d_after = state([-0.01, 0.04], [-2e-5, 3e-5], [-1e-6, 4e-6])

    tangent = native_finish_jvp(before, after, d_before, d_after, config)
    eps = 1.0e-3  # small enough to stay in the same upper/lower clipped branches
    plus = native_finish(add_scaled(before, d_before, eps), add_scaled(after, d_after, eps), config)
    minus = native_finish(add_scaled(before, d_before, -eps), add_scaled(after, d_after, -eps), config)
    for actual, p, m in zip(tangent, plus, minus):
        torch.testing.assert_close(actual, (p - m) / (2.0 * eps), rtol=1e-8, atol=2e-10)


def test_exact_upper_tie_uses_outward_clipped_one_sided_derivative():
    before = state([280.0], [0.001], [1e-4])
    after = state([282.0], [0.001], [1e-4])  # raw == +limit*dt
    outward = state([1.0], [0.0], [0.0])
    zero = state([0.0], [0.0], [0.0])
    tangent = native_finish_jvp(before, after, zero, outward, CONFIG)
    # The selected clipped side has zero derivative at the exact tie.
    for value in tangent:
        torch.testing.assert_close(value, torch.zeros_like(value), rtol=0, atol=0)

    eps = 1.0e-4
    outward_value = native_finish(before, add_scaled(after, outward, eps), CONFIG)
    at_tie = native_finish(before, after, CONFIG)
    for value, base in zip(outward_value, at_tie):
        torch.testing.assert_close(value, base, rtol=0, atol=0)


def test_clip_tie_autograd_uses_clipped_side():
    before = state([280.0], [0.001], [0.0])
    after = state([282.0], [0.001], [0.0])
    after = ThermoState(after.th.clone().requires_grad_(True), after.qv, after.qc)
    result = native_finish(before, after, CONFIG)
    grad = torch.autograd.grad(result.h_rate.sum(), after.th)[0]
    torch.testing.assert_close(grad, torch.zeros_like(grad), rtol=0, atol=0)


def test_vjp_keeps_old_theta_and_humidity_difference_terms():
    before = state([280.0], [0.001], [1e-4])
    after = state([280.5], [0.0012], [1.1e-4])
    zeros = torch.zeros_like(before.th)
    # T_NEW cotangent exposes old theta's A-B coefficient when m is interior.
    t_seed = NativeFinishResult(torch.ones_like(zeros), zeros, zeros, zeros, zeros)
    grad_before, _ = native_finish_vjp(before, after, t_seed, CONFIG)
    expected_old_theta = (1.0 + CONFIG.alpha * before.qv) - (1.0 + CONFIG.alpha * after.qv)
    torch.testing.assert_close(grad_before.th, expected_old_theta, rtol=0, atol=1e-15)
    assert grad_before.th.item() < 0.0

    # QV_RATE contains the explicit negative old-state identity.
    qv_seed = NativeFinishResult(zeros, zeros, torch.ones_like(zeros), zeros, zeros)
    grad_before, grad_after = native_finish_vjp(before, after, qv_seed, CONFIG)
    torch.testing.assert_close(grad_before.qv, torch.tensor([-1.0 / CONFIG.dt], dtype=DTYPE))
    torch.testing.assert_close(grad_after.qv, torch.tensor([1.0 / CONFIG.dt], dtype=DTYPE))


@pytest.mark.parametrize("config", [
    FinishConfig(dt=0.0, alpha=1.6, t0=300.0, mp_tend_lim=0.1),
    FinishConfig(dt=20.0, alpha=0.0, t0=300.0, mp_tend_lim=0.1),
    FinishConfig(dt=20.0, alpha=1.6, t0=300.0, mp_tend_lim=-0.1),
])
def test_config_rejects_invalid_domain(config):
    sample = state([280.0], [0.001], [1e-4])
    with pytest.raises(ValueError):
        native_finish(sample, sample, config)


def test_state_rejects_nonfinite_and_nonphysical_values():
    good = state([280.0], [0.001], [1e-4])
    bad = ThermoState(torch.tensor([280.0], dtype=DTYPE), torch.tensor([float("nan")], dtype=DTYPE), good.qc)
    with pytest.raises(ValueError, match="finite"):
        native_finish(bad, good, CONFIG)
    bad_q = ThermoState(good.th, torch.tensor([-1e-5], dtype=DTYPE), good.qc)
    with pytest.raises(ValueError, match="nonnegative"):
        native_finish(bad_q, good, CONFIG)


def test_state_requires_exact_fp64_metadata():
    before = state([280.0], [0.001], [1e-4])
    after = ThermoState(before.th.float(), before.qv, before.qc)
    with pytest.raises(TypeError, match="float64"):
        native_finish(before, after, CONFIG)


def test_tangent_and_cotangent_metadata_are_validated():
    before = state([280.0], [0.001], [1e-4])
    after = state([280.5], [0.0012], [1.1e-4])
    bad_direction = state([0.1, 0.2], [0.0, 0.0], [0.0, 0.0])
    good_direction = state([0.0], [0.0], [0.0])
    with pytest.raises(ValueError, match="metadata"):
        native_finish_jvp(before, after, bad_direction, good_direction, CONFIG)

    bad_cotangent = NativeFinishResult(*(torch.zeros(2, dtype=DTYPE) for _ in range(5)))
    with pytest.raises(ValueError, match="metadata"):
        native_finish_vjp(before, after, bad_cotangent, CONFIG)


def test_config_requires_fixed_python_scalars():
    before = state([280.0], [0.001], [1e-4])
    config = FinishConfig(dt=torch.tensor(20.0), alpha=CONFIG.alpha,
                          t0=CONFIG.t0, mp_tend_lim=CONFIG.mp_tend_lim)
    with pytest.raises(TypeError, match="real scalar"):
        native_finish(before, before, config)


def test_post_microphysics_zero_out_modes_match_host_thermo_fields():
    threshold = 1.0e-8
    raw = state([280.0] * 4, [-1.0e-4, 0.0, 2.0e-4, 3.0e-4],
                [0.0, 0.5 * threshold, threshold, 2.0 * threshold])
    mode0 = post_microphysics_thermo(raw, ZeroOutConfig(0, threshold))
    assert mode0 is raw
    torch.testing.assert_close(mode0.qv, raw.qv, rtol=0, atol=0)
    torch.testing.assert_close(mode0.qc, raw.qc, rtol=0, atol=0)

    mode1 = post_microphysics_thermo(raw, ZeroOutConfig(1, threshold))
    torch.testing.assert_close(mode1.qv, raw.qv, rtol=0, atol=0)
    torch.testing.assert_close(mode1.qc, torch.tensor([0.0, 0.0, threshold, 2*threshold], dtype=DTYPE), rtol=0, atol=0)

    mode2 = post_microphysics_thermo(raw, ZeroOutConfig(2, threshold))
    torch.testing.assert_close(mode2.qv, torch.tensor([0.0, 0.0, 2e-4, 3e-4], dtype=DTYPE), rtol=0, atol=0)
    torch.testing.assert_close(mode2.qc, mode1.qc, rtol=0, atol=0)
    torch.testing.assert_close(mode2.th, raw.th, rtol=0, atol=0)


def test_post_microphysics_jvp_vjp_and_central_difference_away_from_switches():
    threshold = 1.0e-8
    config = ZeroOutConfig(2, threshold)
    raw = state([280.0, 281.0, 282.0], [-1.0e-4, 1.0e-4, 2.0e-4],
                [0.5*threshold, 2.0*threshold, 4.0*threshold])
    direction = state([0.2, -0.1, 0.3], [1e-5, -2e-5, 3e-5],
                       [2e-9, -1e-9, 4e-9])
    cotangent = state([0.7, -0.3, 0.5], [2.0, -1.0, 0.4], [-0.8, 0.2, 1.1])
    tangent = post_microphysics_jvp(raw, direction, config)
    adjoint = post_microphysics_vjp(raw, cotangent, config)

    eps = 1.0e-2
    plus = post_microphysics_thermo(add_scaled(raw, direction, eps), config)
    minus = post_microphysics_thermo(add_scaled(raw, direction, -eps), config)
    for actual, p, m in zip(tangent, plus, minus):
        torch.testing.assert_close(actual, (p - m) / (2.0 * eps), rtol=1e-10, atol=1e-12)

    torch.testing.assert_close(dot_state(tangent, cotangent), dot_state(direction, adjoint),
                               rtol=1e-14, atol=1e-14)
    # Explicit branch anchors: the negative/zero QV lanes are clipped; mode 2
    # preserves the positive lane. QC below threshold is zeroed, above is passed.
    torch.testing.assert_close(tangent.qv, torch.tensor([0.0, -2e-5, 3e-5], dtype=DTYPE), rtol=0, atol=0)
    torch.testing.assert_close(tangent.qc, torch.tensor([0.0, -1e-9, 4e-9], dtype=DTYPE), rtol=0, atol=0)


@pytest.mark.parametrize("mode", [1, 2])
def test_positive_qc_threshold_tie_rejects_jvp_and_vjp(mode):
    threshold = 1.0e-8
    raw = state([280.0], [1e-4], [threshold])
    vector = state([0.0], [0.0], [1.0])
    config = ZeroOutConfig(mode, threshold)
    with pytest.raises(ValueError, match="discontinuous"):
        post_microphysics_jvp(raw, vector, config)
    with pytest.raises(ValueError, match="discontinuous"):
        post_microphysics_vjp(raw, vector, config)


def test_zero_threshold_qc_and_mode2_qv_ties_choose_clipped_side():
    raw = state([280.0, 281.0], [0.0, -1e-4], [0.0, -1e-4])
    vector = state([1.0, 1.0], [1.0, 1.0], [1.0, 1.0])
    for mode in (1, 2):
        result = post_microphysics_jvp(raw, vector, ZeroOutConfig(mode, 0.0))
        torch.testing.assert_close(result.qc, torch.zeros_like(raw.qc), rtol=0, atol=0)
        if mode == 2:
            torch.testing.assert_close(result.qv, torch.zeros_like(raw.qv), rtol=0, atol=0)
        else:
            torch.testing.assert_close(result.qv, vector.qv, rtol=0, atol=0)

    qv = torch.tensor([0.0, -1e-4, 1e-4], dtype=DTYPE, requires_grad=True)
    qc = torch.tensor([0.0, -1e-4, 1e-4], dtype=DTYPE, requires_grad=True)
    raw_graph = ThermoState(torch.tensor([280.0, 281.0, 282.0], dtype=DTYPE), qv, qc)
    mapped = post_microphysics_thermo(raw_graph, ZeroOutConfig(2, 0.0))
    grad_qv, grad_qc = torch.autograd.grad(mapped.qv.sum() + mapped.qc.sum(), (qv, qc))
    torch.testing.assert_close(grad_qv, torch.tensor([0.0, 0.0, 1.0], dtype=DTYPE), rtol=0, atol=0)
    torch.testing.assert_close(grad_qc, torch.tensor([0.0, 0.0, 1.0], dtype=DTYPE), rtol=0, atol=0)


def test_post_microphysics_config_mode_is_strict_and_domain_checked():
    raw = state([280.0], [-1e-4], [-1e-4])
    for mode in (-1, 3):
        with pytest.raises(ValueError, match="mode"):
            post_microphysics_thermo(raw, ZeroOutConfig(mode, 1e-8))
    with pytest.raises(TypeError, match="integer"):
        post_microphysics_thermo(raw, ZeroOutConfig(True, 1e-8))
    with pytest.raises(ValueError, match="threshold"):
        post_microphysics_thermo(raw, ZeroOutConfig(2, -1e-8))
