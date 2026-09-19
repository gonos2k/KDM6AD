"""Picons reclassification branch, trace, and fixed-branch AD checks."""
from __future__ import annotations

import math

import pytest
import torch

from kdm6 import constants as c, fconst
from kdm6.coordinator import CoordinatorState, reclassify_large_ice_to_snow_torch
from kdm6.sensitivity_diagnostics import SensitivityTrace


def _state(*, qi=1.0e-3, ni=50.0, t=260.0, requires_grad=False):
    z = lambda x: torch.tensor([[x]], dtype=torch.float64)
    q = z(qi).requires_grad_(requires_grad)
    return CoordinatorState(
        qv=z(0.0), qc=z(0.0), qr=z(0.0), qs=z(0.0), qg=z(0.0), qi=q,
        nc=z(0.0), nr=z(0.0), ni=z(ni), brs=z(0.0), t=z(t),
    )


def _independent_mask(state, den, threshold=200.0e-6, t0c=273.15):
    factor = math.pow(6.0, 1.0 / 3.0)
    ni = max(float(state.ni.detach().item()), 0.0)
    qi_den = max(float((state.qi * den).detach().item()), 1.0e-30)
    lamda = (fconst.PIDNI * ni / qi_den) ** (1.0 / c.DMI)
    rslope = min(max(1.0 / max(lamda, 1.0e-30), 1.0 / c.LAMDAIMAX),
                 1.0 / c.LAMDAIMIN)
    avedia = rslope * factor
    return (float(state.qi.detach().item()) > 1.0e-15 and ni > 0.0 and
            float(den.detach().item()) > 0.0 and
            float(state.t.detach().item()) < t0c and avedia >= threshold)


def _run(state, *, den=1.0, threshold=200.0e-6):
    d = torch.full_like(state.qi, den)
    trace = SensitivityTrace()
    out = reclassify_large_ice_to_snow_torch(
        state, d, di_threshold=threshold, diagnostic_trace=trace,
        diagnostic_step=2, diagnostic_dtcld=20.0)
    return out, trace.by_name("picons")[0]


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (_state(qi=1.0e-3, ni=50.0, t=260.0, requires_grad=True), True),
        (_state(qi=1.0e-3, ni=1.0e6, t=260.0, requires_grad=True), False),
        (_state(qi=1.0e-3, ni=0.0, t=260.0, requires_grad=True), False),
        (_state(qi=1.0e-3, ni=50.0, t=280.0, requires_grad=True), False),
    ],
    ids=["active_cold", "inactive_cold_small_diameter",
         "inactive_invalid_moment", "inactive_warm"],
)
def test_picons_actual_trace_and_fixed_branch_jvp_vjp_fd(state, expected):
    out, record = _run(state)
    mask = record.branch[3]
    assert bool(mask.item()) is expected
    assert bool(mask.item()) is _independent_mask(state, torch.ones_like(state.qi))
    expected_qi = state.qi * (1.0 - mask.to(state.qi.dtype))
    expected_qs = state.qs + state.qi * mask.to(state.qi.dtype)
    expected_ni = state.ni * (1.0 - mask.to(state.ni.dtype))
    assert torch.equal(out.qi, expected_qi)
    assert torch.equal(out.qs, expected_qs)
    assert torch.equal(out.ni, expected_ni)

    vjp = torch.autograd.grad(out.qs.sum(), state.qi, retain_graph=True)[0]
    from torch.autograd import forward_ad
    with forward_ad.dual_level():
        qi_dual = forward_ad.make_dual(state.qi.detach(), torch.ones_like(state.qi))
        dual_state = state._replace(qi=qi_dual)
        dual_out, _ = _run(dual_state)
        primal, jvp = forward_ad.unpack_dual(dual_out.qs.sum())
    assert torch.equal(primal, out.qs.detach().sum())
    assert torch.isfinite(vjp).all() and torch.isfinite(jvp).all()
    scale = max(float(jvp.abs().item()), float(vjp.abs().item()), 1.0e-30)
    assert float((jvp - vjp).abs().item()) <= 1.0e-12 * scale

    eps = 1.0e-8
    plus, plus_record = _run(_state(qi=state.qi.item() + eps, ni=state.ni.item(), t=state.t.item()))
    minus, minus_record = _run(_state(qi=state.qi.item() - eps, ni=state.ni.item(), t=state.t.item()))
    assert torch.equal(plus_record.branch, record.branch)
    assert torch.equal(minus_record.branch, record.branch)
    fd = (plus.qs - minus.qs) / (2.0 * eps)
    assert torch.isfinite(fd).all()
    expected_derivative = torch.ones_like(fd) if expected else torch.zeros_like(fd)
    fd_bound = 1.0e-10 * max(float(expected_derivative.abs().item()), 1.0e-30)
    assert float((fd - expected_derivative).abs().item()) <= fd_bound
    torch.testing.assert_close(vjp, expected_derivative, rtol=1.0e-12, atol=1.0e-12)


def test_picons_threshold_equality_and_temperature_boundary_are_explicit():
    state = _state(qi=1.0e-3, ni=50.0, t=260.0)
    _, baseline = _run(state)
    executed_avedia = float(baseline.operands["avedia_i"].detach().item())
    _, active = _run(state, threshold=executed_avedia)
    assert bool(active.branch[2].item()) and bool(active.branch[3].item())
    _, above = _run(state, threshold=math.nextafter(executed_avedia, math.inf))
    assert not bool(above.branch[2].item()) and not bool(above.branch[3].item())
    _, warm = _run(state._replace(t=torch.full_like(state.t, 273.15)))
    assert not bool(warm.branch[1].item()) and not bool(warm.branch[3].item())
