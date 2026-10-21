import math
import struct

import pytest
import torch

from kdm6.native_prep import (
    FrozenPrepGeometry,
    NativePrepConfig,
    NativePrepResult,
    NativePrepState,
    native_prep,
    native_prep_jvp,
    native_prep_vjp,
)


DTYPE = torch.float64
CONFIG = NativePrepConfig(
    ptop=5000.0,
    rd=287.0,
    p0=100000.0,
    t0=300.0,
    alpha=1.6083624362945557,
    gamma=struct.unpack(">f", bytes.fromhex("3FB33333"))[0],
    kappa=0.2857142984867096,
    g=struct.unpack(">f", bytes.fromhex("411CF5C3"))[0],
)


def state(thm_pert=None, qv=None, mu_total=50000.0, ph=None):
    return NativePrepState(
        torch.tensor([-20.0, -15.0, -10.0] if thm_pert is None else thm_pert, dtype=DTYPE),
        torch.tensor([0.001, 0.004, 0.01] if qv is None else qv, dtype=DTYPE),
        torch.tensor(mu_total, dtype=DTYPE),
        torch.tensor([0.0, 50000.0, 110000.0, 180000.0] if ph is None else ph, dtype=DTYPE),
    )


def geometry(*, phb=None, c3h=None, c4h=None, c3f=None, c4f=None):
    return FrozenPrepGeometry(
        torch.tensor([0.0, 0.0, 0.0, 0.0] if phb is None else phb, dtype=DTYPE),
        torch.tensor([0.85, 0.55, 0.25] if c3h is None else c3h, dtype=DTYPE),
        torch.tensor([0.0, 0.0, 0.0] if c4h is None else c4h, dtype=DTYPE),
        torch.tensor([1.0, 0.7, 0.4, 0.1] if c3f is None else c3f, dtype=DTYPE),
        torch.tensor([0.0, 0.0, 0.0, 0.0] if c4f is None else c4f, dtype=DTYPE),
    )


def add_scaled(a: NativePrepState, da: NativePrepState, scale: float):
    return NativePrepState(*(x + scale * dx for x, dx in zip(a, da)))


def dot_result(a: NativePrepResult, b: NativePrepResult):
    return sum((x * y).sum() for x, y in zip(a, b))


def dot_state(a: NativePrepState, b: NativePrepState):
    return sum((x * y).sum() for x, y in zip(a, b))


def test_forward_matches_independent_scalar_native_prep_equations():
    x = state()
    geom = geometry()
    result = native_prep(x, geom, CONFIG)
    expected = [[] for _ in range(5)]
    for k in range(3):
        tmoist = x.thm_pert[k].item() + CONFIG.t0
        dphi = (x.ph[k + 1].item() + geom.phb[k + 1].item()) - (
            x.ph[k].item() + geom.phb[k].item()
        )
        h = geom.c3h[k].item() * x.mu_total.item() + geom.c4h[k].item() + CONFIG.ptop
        p_d = geom.c3f[k].item() * x.mu_total.item() + geom.c4f[k].item() + CONFIG.ptop
        p_u = geom.c3f[k + 1].item() * x.mu_total.item() + geom.c4f[k + 1].item() + CONFIG.ptop
        ell = math.log(p_d / p_u)
        volume = dphi / h / ell
        pressure = CONFIG.p0 * (CONFIG.rd * tmoist / (CONFIG.p0 * volume)) ** CONFIG.gamma
        pii = (pressure / CONFIG.p0) ** CONFIG.kappa
        theta = tmoist / (1.0 + CONFIG.alpha * x.qv[k].item())
        expected[0].append(theta)
        expected[1].append(1.0 / volume)
        expected[2].append(pii)
        expected[3].append(pressure)  # full pressure, as passed as p_phy
        expected[4].append(dphi / CONFIG.g)
    for actual, values in zip(result, expected):
        torch.testing.assert_close(actual, torch.tensor(values, dtype=DTYPE), rtol=2e-13, atol=1e-12)


def test_jvp_matches_central_fd_and_vjp_is_its_adjoint():
    x = state()
    geom = geometry()
    direction = NativePrepState(
        torch.tensor([0.3, -0.2, 0.4], dtype=DTYPE),
        torch.tensor([1e-5, -2e-5, 3e-5], dtype=DTYPE),
        torch.tensor(3.0, dtype=DTYPE),
        torch.tensor([3.0, -1.0, 2.0, 4.0], dtype=DTYPE),
    )
    cotangent = NativePrepResult(
        torch.tensor([0.3, -0.2, 0.5], dtype=DTYPE),
        torch.tensor([0.7, -0.4, 1.1], dtype=DTYPE),
        torch.tensor([-0.2, 0.6, 0.8], dtype=DTYPE),
        torch.tensor([2.0, -1.0, 0.5], dtype=DTYPE),
        torch.tensor([0.4, 0.1, -0.3], dtype=DTYPE),
    )
    tangent = native_prep_jvp(x, geom, direction, CONFIG)
    eps = 1e-4
    plus = native_prep(add_scaled(x, direction, eps), geom, CONFIG)
    minus = native_prep(add_scaled(x, direction, -eps), geom, CONFIG)
    for actual, p, m in zip(tangent, plus, minus):
        torch.testing.assert_close(actual, (p - m) / (2 * eps), rtol=5e-7, atol=2e-9)

    grad = native_prep_vjp(x, geom, cotangent, CONFIG)
    torch.testing.assert_close(dot_result(tangent, cotangent), dot_state(direction, grad),
                               rtol=3e-13, atol=3e-13)


def test_analytic_vjp_matches_autograd_for_all_live_inputs():
    x = state()
    x = NativePrepState(*(value.clone().requires_grad_(True) for value in x))
    geom = geometry()  # geometry is intentionally fixed, never a grad leaf.
    cotangent = NativePrepResult(*(torch.tensor(values, dtype=DTYPE) for values in (
        [0.3, -0.2, 0.5], [0.7, -0.4, 1.1], [-0.2, 0.6, 0.8],
        [2.0, -1.0, 0.5], [0.4, 0.1, -0.3],
    )))
    output = native_prep(x, geom, CONFIG)
    objective = dot_result(output, cotangent)
    auto = torch.autograd.grad(objective, tuple(x))
    explicit = native_prep_vjp(x, geom, cotangent, CONFIG)
    for actual, expected in zip(auto, explicit):
        torch.testing.assert_close(actual, expected, rtol=3e-13, atol=3e-13)


def test_interface_pullback_signs_and_constant_phi_shift_gauge():
    x = state()
    geom = geometry()
    zero_state_direction = NativePrepState(
        torch.zeros_like(x.thm_pert), torch.zeros_like(x.qv), torch.zeros_like(x.mu_total),
        torch.ones_like(x.ph),
    )
    gauge_tangent = native_prep_jvp(x, geom, zero_state_direction, CONFIG)
    for value in gauge_tangent:
        torch.testing.assert_close(value, torch.zeros_like(value), rtol=0, atol=0)

    delz_cotangent = torch.tensor([1.0, -2.0, 3.0], dtype=DTYPE)
    zero_levels = torch.zeros_like(x.thm_pert)
    cotangent = NativePrepResult(zero_levels, zero_levels, zero_levels, zero_levels, delz_cotangent)
    grad = native_prep_vjp(x, geom, cotangent, CONFIG)
    expected_ph = torch.cat((
        -delz_cotangent[:1] / CONFIG.g,
        (delz_cotangent[:-1] - delz_cotangent[1:]) / CONFIG.g,
        delz_cotangent[-1:] / CONFIG.g,
    ))
    torch.testing.assert_close(grad.ph, expected_ph, rtol=0, atol=1e-15)
    assert torch.equal(grad.thm_pert, torch.zeros_like(grad.thm_pert))
    assert torch.equal(grad.qv, torch.zeros_like(grad.qv))
    assert grad.mu_total.item() == 0.0


def test_mu_and_temperature_change_eos_outputs_but_qv_does_not_change_pressure():
    x = state()
    geom = geometry()
    zeros_th = torch.zeros_like(x.thm_pert)
    zeros_qv = torch.zeros_like(x.qv)
    zeros_mu = torch.zeros_like(x.mu_total)
    zeros_ph = torch.zeros_like(x.ph)

    mu_direction = NativePrepState(zeros_th, zeros_qv, torch.ones_like(x.mu_total), zeros_ph)
    dmu = native_prep_jvp(x, geom, mu_direction, CONFIG)
    assert torch.all(dmu.rho != 0.0) and torch.all(dmu.pii != 0.0) and torch.all(dmu.p != 0.0)
    assert torch.equal(dmu.delz, torch.zeros_like(dmu.delz))

    t_direction = NativePrepState(torch.ones_like(x.thm_pert), zeros_qv, zeros_mu, zeros_ph)
    dt = native_prep_jvp(x, geom, t_direction, CONFIG)
    assert torch.all(dt.th != 0.0) and torch.all(dt.pii != 0.0) and torch.all(dt.p != 0.0)
    assert torch.equal(dt.rho, torch.zeros_like(dt.rho))
    assert torch.equal(dt.delz, torch.zeros_like(dt.delz))

    qv_direction = NativePrepState(zeros_th, torch.ones_like(x.qv), zeros_mu, zeros_ph)
    dqv = native_prep_jvp(x, geom, qv_direction, CONFIG)
    assert torch.all(dqv.th != 0.0)
    for field in (dqv.rho, dqv.pii, dqv.p, dqv.delz):
        assert torch.equal(field, torch.zeros_like(field))


def test_gamma_and_kappa_are_independent_fixed_constants():
    x = state()
    geom = geometry()
    other = NativePrepConfig(**{**CONFIG.__dict__, "kappa": 0.2})
    a = native_prep(x, geom, CONFIG)
    b = native_prep(x, geom, other)
    torch.testing.assert_close(a.p, b.p, rtol=0, atol=0)
    assert torch.all((a.pii != b.pii))


def test_bad_mass_or_interface_domain_rejected():
    geom = geometry()
    with pytest.raises(ValueError, match="positive"):
        native_prep(state(mu_total=-1.0), geom, CONFIG)
    with pytest.raises(ValueError, match="increase"):
        native_prep(state(ph=[0.0, 50000.0, 40000.0, 180000.0]), geom, CONFIG)
    with pytest.raises(ValueError, match="p_d > p_u"):
        bad_geom = geometry(c3f=[0.1, 0.4, 0.7, 1.0])
        native_prep(state(), bad_geom, CONFIG)


def test_geometry_must_be_frozen_and_shapes_are_native_39_40_style():
    x = state()
    frozen = geometry()
    live_phb = FrozenPrepGeometry(
        frozen.phb.clone().requires_grad_(True), frozen.c3h, frozen.c4h, frozen.c3f, frozen.c4f
    )
    with pytest.raises(ValueError, match="fixed"):
        native_prep(x, live_phb, CONFIG)
    bad_geom = geometry(phb=[0.0, 0.0, 0.0])
    with pytest.raises(ValueError, match="interface"):
        native_prep(x, bad_geom, CONFIG)

    levels = 39
    native_state = NativePrepState(
        torch.full((levels,), -10.0, dtype=DTYPE),
        torch.full((levels,), 0.004, dtype=DTYPE),
        torch.tensor(50000.0, dtype=DTYPE),
        torch.linspace(0.0, 180000.0, levels + 1, dtype=DTYPE),
    )
    native_geometry = FrozenPrepGeometry(
        torch.zeros(levels + 1, dtype=DTYPE),
        torch.linspace(0.95, 0.15, levels, dtype=DTYPE),
        torch.zeros(levels, dtype=DTYPE),
        torch.linspace(1.0, 0.1, levels + 1, dtype=DTYPE),
        torch.zeros(levels + 1, dtype=DTYPE),
    )
    native_result = native_prep(native_state, native_geometry, CONFIG)
    assert all(value.shape == (levels,) for value in native_result)


def test_fixed_scalar_tensor_parameters_rejected():
    x = state()
    config = NativePrepConfig(**{**CONFIG.__dict__, "alpha": torch.tensor(CONFIG.alpha)})
    with pytest.raises(TypeError, match="fixed real scalar"):
        native_prep(x, geometry(), config)
