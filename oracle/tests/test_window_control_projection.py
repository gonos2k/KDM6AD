"""Focused regressions for the window control-space projection boundary."""

from __future__ import annotations

import pytest
import torch

import kdm6.da_linearization as da_linearization
import kdm6.da_window as da_window
from kdm6.da_linearization import WindowLinearization
from kdm6.da_window import WindowConfig, run_da_window
from kdm6.runtime import Handle, kdm6_fn, make_parameters
from kdm6.state import Forcing, State, state_dot


F64 = {"dtype": torch.float64}
DT = 1.0


def _linear_state(qc=1.0, qi=0.0):
    z = torch.zeros((1, 1), **F64)
    return State(th=z, qv=z, qc=z + qc, qr=z, qi=z + qi, qs=z, qg=z,
                 nccn=z, nc=z, ni=z, nr=z, bg=z)


def _linear_forcing():
    z = torch.zeros((1, 1), **F64)
    return Forcing(rho=z + 1.0, pii=z + 1.0, p=z + 1.0e5, delz=z + 1.0)


def _linear_covector(qc=0.0, qi=0.0):
    z = torch.zeros((1, 1), **F64)
    return _linear_state(qc=qc, qi=qi)._replace(
        th=z, qv=z, qr=z, qs=z, qg=z, nccn=z, nc=z, ni=z, nr=z, bg=z)


def _linear_step(state, forcing, params=None, dt=0.0, *, value_only=False,
                 parameterized=False, **_kwargs):
    """Exact positive qc/qi mixing used only by these module tests."""
    if params is None:
        params = make_parameters()

    def map_state(x):
        # At the default PEAUT=.40, the parameterized model is exactly A.
        scale = (1.0 + (params.peaut - 0.40)) if parameterized else 1.0
        qc = scale * (0.75 * x.qc + 0.25 * x.qi)
        qi = scale * (0.25 * x.qc + 0.75 * x.qi)
        return x._replace(qc=qc, qi=qi)

    if value_only:
        with torch.no_grad():
            out = map_state(state)
        out = State(*(x.detach() for x in out))
        return out, Handle(state_in=state, state_out=out, forcing=forcing,
                           params=params, dt=dt, value_only=True)

    out = map_state(state)
    handle = Handle(state_in=state, state_out=out, forcing=forcing,
                    params=params, dt=dt, func=lambda s, f, p, d: map_state(s))
    return out, handle


def _install_linear_step(monkeypatch, *, parameterized=False):
    def step(*args, **kwargs):
        return _linear_step(*args, parameterized=parameterized, **kwargs)

    monkeypatch.setattr(da_window, "kdm6_step", step)
    monkeypatch.setattr(da_linearization, "kdm6_step", step)


@pytest.mark.parametrize("steps, expected_qc", [(2, 0.625), (3, 0.5625)])
def test_both_window_implementations_preserve_positive_qc_qi_mix(monkeypatch,
                                                                 steps,
                                                                 expected_qc):
    _install_linear_step(monkeypatch)
    x0 = _linear_state()
    forcings = [_linear_forcing()] * steps
    u = _linear_covector(qc=1.0)

    res = run_da_window(x0, forcings, lambda t, _: u if t == steps else None,
                        WindowConfig(dt=DT, active_fields=("qc",)))
    assert res.state_final.qc.item() == pytest.approx(expected_qc)
    assert res.state_final.qi.item() == pytest.approx(1.0 - expected_qc)
    assert res.adj_x0.qc.item() == pytest.approx(expected_qc)
    assert res.adj_x0.qi.item() == 0.0

    with WindowLinearization(x0, forcings, dt=DT) as lin:
        retained = lin.apply_adjoint({steps: u}, active_fields=("qc",))
        v_qc = _linear_covector(qc=1.0)
        tangent = lin.apply_tangent(v_qc)["final"]
    assert lin.state_final.qc.item() == pytest.approx(expected_qc)
    assert retained.qc.item() == pytest.approx(expected_qc)
    assert retained.qi.item() == 0.0
    analytic_adjoint = torch.matrix_power(
        torch.tensor([[0.75, 0.25], [0.25, 0.75]], **F64), steps
    ).T @ torch.tensor([1.0, 0.0], **F64)
    assert analytic_adjoint[0].item() == pytest.approx(expected_qc)
    assert state_dot(u, tangent).item() == pytest.approx(expected_qc)
    assert state_dot(retained, v_qc).item() == pytest.approx(expected_qc)
    assert state_dot(u, tangent).item() == pytest.approx(
        state_dot(retained, v_qc).item())

    def final_qc(qc):
        return run_da_window(
            _linear_state(qc=qc), forcings,
            lambda t, _: u if t == steps else None,
            WindowConfig(dt=DT),
        ).state_final.qc.item()

    h = 1.0e-6
    fd = (final_qc(1.0 + h) - final_qc(1.0 - h)) / (2.0 * h)
    assert fd == pytest.approx(analytic_adjoint[0].item(), rel=1.0e-9)


def test_window_projection_keeps_eta_eta_pre_and_parameter_covectors_full(monkeypatch):
    _install_linear_step(monkeypatch, parameterized=True)
    x0 = _linear_state()
    forcings = [_linear_forcing(), _linear_forcing()]
    u = _linear_covector(qc=1.0)
    z = _linear_state(qc=0.0, qi=0.0)

    eta0 = z._replace(qi=torch.ones_like(z.qi))
    res_eta = run_da_window(
        x0, forcings, lambda t, _: u if t == 2 else None,
        WindowConfig(dt=DT, active_fields=("qc",), eta=[eta0, z]),
    )
    assert res_eta.grad_eta is not None
    # The first post-step increment sees the full covector after step 1;
    # masking it at the intermediate VJP would erase the qi component.
    assert res_eta.grad_eta[0].qi.item() == pytest.approx(0.25)
    assert res_eta.adj_x0.qi.item() == 0.0

    eta_pre0 = z._replace(qi=torch.ones_like(z.qi))
    res_pre = run_da_window(
        x0, forcings, lambda t, _: u if t == 2 else None,
        WindowConfig(dt=DT, active_fields=("qc",), eta_pre=[eta_pre0, z]),
    )
    assert res_pre.grad_eta_pre is not None
    assert res_pre.grad_eta_pre[0].qi.item() == pytest.approx(0.375)
    assert res_pre.adj_x0.qi.item() == 0.0

    live = make_parameters(peaut_grad=True)
    active = run_da_window(
        x0, forcings, lambda t, _: u if t == 2 else None,
        WindowConfig(dt=DT, params=live, active_fields=("qc",),
                     param_grads=True),
    )
    full = run_da_window(
        x0, forcings, lambda t, _: u if t == 2 else None,
        WindowConfig(dt=DT, params=make_parameters(peaut_grad=True),
                     param_grads=True),
    )
    assert active.grad_params is not None and full.grad_params is not None
    assert active.grad_params["peaut"].item() == pytest.approx(1.25)
    assert torch.equal(active.grad_params["peaut"], full.grad_params["peaut"])


def test_retained_linearization_zero_step_uses_initial_state_for_tangent(monkeypatch):
    _install_linear_step(monkeypatch)
    x0 = _linear_state()
    v0 = _linear_covector(qc=2.0, qi=-3.0)
    u = _linear_covector(qc=1.0, qi=1.0)

    with WindowLinearization(x0, [], dt=DT) as lin:
        tangent = lin.apply_tangent(v0, obs_times=[0])
        adj = lin.apply_adjoint({0: u}, active_fields=("qc",))
    assert set(tangent) == {0, "final"}
    assert tangent[0].qc.item() == 2.0
    assert tangent[0].qi.item() == -3.0
    assert tangent["final"].qc.item() == 2.0
    assert tangent["final"].qi.item() == -3.0
    assert adj.qc.item() == 1.0
    assert adj.qi.item() == 0.0


def _real_state():
    def t(a, b):
        return torch.tensor([[a, b]], **F64)

    return State(
        th=t(296.8, 282.4), qv=t(1.40e-2, 2.0e-3),
        qc=t(1.0e-3, 5.0e-4), qr=t(1.0e-4, 1.0e-5),
        qi=t(2.0e-4, 1.0e-6), qs=t(0.0, 5.0e-5),
        qg=t(0.0, 1.0e-5), nccn=t(1.0e9, 1.0e9),
        nc=t(1.0e8, 1.0e8), ni=t(0.0, 1.0e8),
        nr=t(1.0e4, 1.0e3), bg=t(0.0, 0.0),
    )


def _real_forcing():
    def t(a, b):
        return torch.tensor([[a, b]], **F64)

    return Forcing(rho=t(1.089, 0.9567), pii=t(0.9704, 0.9031),
                   p=t(9.0e4, 7.0e4), delz=t(500.0, 500.0))


def _masked(state, active):
    return State(*(x if name in active else torch.zeros_like(x)
                   for name, x in zip(State._fields, state)))


def test_real_kdm6_partial_control_projection_matches_full_adjoint_jvp_fd():
    x0 = _real_state()
    forcings = [_real_forcing(), _real_forcing()]
    u = State(*(torch.ones_like(x) for x in x0))
    active = ("qc", "qi")

    result = run_da_window(
        x0, forcings, lambda t, _: u if t == 2 else None,
        WindowConfig(dt=20.0, active_fields=active),
    )

    x0_leaves = State(*(x.detach().clone().requires_grad_(True) for x in x0))
    params = make_parameters()
    x = x0_leaves
    for forcing in forcings:
        x = kdm6_fn(x, forcing, params, 20.0)
    grads = torch.autograd.grad(state_dot(x, u), tuple(x0_leaves),
                                allow_unused=True, materialize_grads=True)
    reference = _masked(State(*grads), active)
    for name in State._fields:
        assert torch.equal(getattr(result.adj_x0, name),
                           getattr(reference, name)), name

    v0 = State(*(torch.zeros_like(x) for x in x0))._replace(
        qc=torch.tensor([[2.0e-5, -1.0e-5]], **F64),
        qi=torch.tensor([[-1.0e-5, 3.0e-5]], **F64),
    )
    with WindowLinearization(x0, forcings, dt=20.0) as lin:
        tangent = lin.apply_tangent(v0)["final"]
        retained_adj = lin.apply_adjoint({2: u}, active_fields=active)
    lhs = state_dot(u, tangent)
    rhs = state_dot(retained_adj, v0)
    assert torch.allclose(lhs, rhs, rtol=2.0e-10, atol=1.0e-12)

    def objective(x_init):
        y = x_init
        for forcing in forcings:
            y = kdm6_fn(y, forcing, make_parameters(), 20.0)
        return state_dot(y, u)

    h = 1.0e-5
    plus = State(*(a + h * b for a, b in zip(x0, v0)))
    minus = State(*(a - h * b for a, b in zip(x0, v0)))
    fd = (objective(plus) - objective(minus)) / (2.0 * h)
    assert torch.allclose(rhs, fd, rtol=2.0e-5, atol=1.0e-10)
