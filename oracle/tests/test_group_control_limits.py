"""Finite f64 control budgets: full consumers, signed sums and AD duality."""
import math

import pytest
import torch

from kdm6 import coordinator as c
from kdm6.process_controls import ProcessControls, apply_warm_controls

F64 = dict(dtype=torch.float64)


def _zero(cls, shape=(1, 1)):
    z = torch.zeros(shape, **F64)
    return cls(*(z for _ in cls._fields))


def _limit(warm, *, state=None, dt=1., supcol=None):
    z = torch.zeros_like(warm.praut)
    if state is None:
        state = _zero(c.CoordinatorState, z.shape)._replace(qc=z+.001, nc=z+1e8)
    return c.scale_rates_for_conservation_torch(
        state, z-1 if supcol is None else supcol, warm,
        _zero(c.ColdPhaseOutputs, z.shape), _zero(c.MeltFreezePhaseOutputs, z.shape),
        dtcld=dt)[0]


@pytest.mark.parametrize('alpha_value', [500., 680., 700.])
def test_extreme_capped_control_has_zero_normalized_derivative(alpha_value):
    z = torch.zeros((1, 1), **F64)
    warm = _zero(c.WarmPhaseOutputs)._replace(praut=z+1e-6, nraut=z+1000.)
    a = torch.tensor(alpha_value, requires_grad=True, **F64)

    def draw(a):
        w = _limit(apply_warm_controls(warm, ProcessControls(alpha_autoconv=a)))
        # Dimensionless budget fractions give the two derivatives the same scale.
        return torch.cat((w.praut/.001, w.nraut/1e8)).flatten()

    value, jvp = torch.func.jvp(draw, (a,), (torch.ones_like(a),))
    vjp, = torch.autograd.grad(value.sum(), a, create_graph=True)
    second, = torch.autograd.grad(vjp, a)
    torch.testing.assert_close(value, torch.ones_like(value), rtol=4e-16, atol=0)
    # Independent saturated solution is identically one in each component.
    eps = torch.finfo(torch.float64).eps
    assert abs(vjp.item()) <= 8*eps
    assert bool((jvp.abs() <= 8*eps).all())
    assert abs(second.item()) <= 16*eps


def test_distinct_controls_keep_competing_rate_derivatives():
    z = torch.zeros((1, 1), **F64)
    warm = _zero(c.WarmPhaseOutputs)._replace(praut=z+1e-6, pracw=z+2e-6)
    a = torch.tensor([500., 501.], requires_grad=True, **F64)

    def share(a):
        w = _limit(apply_warm_controls(
            warm, ProcessControls(alpha_autoconv=a[0], alpha_accretion=a[1])))
        return (w.praut/.001).sum()

    value = share(a)
    grad, = torch.autograd.grad(value, a, create_graph=True)
    p = 1/(1+2*math.e)
    assert value.item() == pytest.approx(p, rel=1e-14)
    expected = torch.tensor([p*(1-p), -p*(1-p)], **F64)
    torch.testing.assert_close(grad, expected, rtol=1e-14, atol=0)
    direction = torch.tensor([.3, -.7], **F64)
    _, jvp = torch.func.jvp(share, (a,), (direction,))
    torch.testing.assert_close(jvp, grad@direction, rtol=1e-14, atol=0)
    assert torch.autograd.gradcheck(share, (a,), eps=1e-4, atol=1e-9, rtol=1e-7)
    assert torch.autograd.gradgradcheck(share, (a,), eps=1e-4, atol=1e-9, rtol=1e-7)


def test_signed_source_retains_production_and_sink_derivatives():
    z = torch.zeros((1, 1), **F64)
    state = _zero(c.CoordinatorState)._replace(qc=z+4e200, qr=z+1e199)
    a = torch.tensor([1., 2.], requires_grad=True, **F64)

    def production_share(a):
        # Rain source is -praut-prevp = (a[1]-a[0])*1e200.
        warm = _zero(c.WarmPhaseOutputs)._replace(
            praut=z+a[0]*1e200, prevp=z-a[1]*1e200)
        bounded = _limit(warm, state=state)
        return (bounded.praut/1e199).sum()

    value = production_share(a)
    grad, = torch.autograd.grad(value, a)
    assert value.item() == pytest.approx(1., rel=1e-14)
    # a/(b-a): at (a,b)=(1,2), d/da=2 and d/db=-1.
    torch.testing.assert_close(grad, torch.tensor([2., -1.], **F64), rtol=1e-14, atol=0)
    assert torch.autograd.gradcheck(production_share, (a,), eps=1e-5, atol=1e-9, rtol=1e-7)


@pytest.mark.parametrize('kind', ['sum', 'amount'])
def test_group_source_overflow_is_refused_after_finite_products(kind):
    z = torch.zeros((1, 1), **F64)
    if kind == 'sum':
        warm = _zero(c.WarmPhaseOutputs)._replace(
            praut=z+1e-6, pracw=z+1e-6, nraut=z+10000., nracw=z+10000.)
        a = torch.tensor(700., **F64)
        warm = apply_warm_controls(
            warm, ProcessControls(alpha_autoconv=a, alpha_accretion=a))
        dt = 1.
    else:
        warm = _zero(c.WarmPhaseOutputs)._replace(nraut=z+1e308)
        dt = 2.
    assert bool(torch.isfinite(warm.nraut).all())
    assert bool(torch.isfinite(warm.nracw).all())
    with pytest.raises(ValueError, match=f'conservation source {kind} must be finite'):
        _limit(warm, dt=dt)


def test_large_source_keeps_representable_tiny_rate_and_unbound_cells():
    z = torch.zeros((1, 2), **F64)
    state = _zero(c.CoordinatorState, z.shape)._replace(
        qc=torch.tensor([[1e299, .001]], **F64), nc=z+1e8)
    tiny_rate = torch.tensor([[1e-300, 1e-6]], requires_grad=True, **F64)
    warm = _zero(c.WarmPhaseOutputs, z.shape)._replace(
        praut=tiny_rate, pracw=torch.tensor([[1e300, 0.]], **F64))
    out = _limit(warm, state=state)
    # First quotient r/source underflows, but r*budget/source is representable.
    torch.testing.assert_close(out.praut, torch.tensor([[1e-301, 1e-6]], **F64),
                               rtol=5e-16, atol=0)
    grad, = torch.autograd.grad(out.praut.sum(), tiny_rate)
    torch.testing.assert_close(grad, torch.tensor([[.1, 1.]], **F64), rtol=1e-14, atol=0)


def test_full_step_extreme_autoconversion_matches_tangent_and_difference():
    from test_process_controls import _mk_state, _mk_forcing
    from kdm6.runtime import kdm6_fn, make_parameters
    a = torch.tensor(680., requires_grad=True, **F64)

    def final_cloud_number(a):
        out = kdm6_fn(_mk_state(), _mk_forcing(), make_parameters(), 20.,
                       controls=ProcessControls(alpha_autoconv=a))
        return out.nc[0, 0]/1e8

    value, jvp = torch.func.jvp(final_cloud_number, (a,), (torch.ones_like(a),))
    vjp, = torch.autograd.grad(value, a)
    fd = (final_cloud_number(a+1e-4)-final_cloud_number(a-1e-4))/2e-4
    assert torch.isfinite(value)
    torch.testing.assert_close(vjp, jvp, rtol=0, atol=8*torch.finfo(torch.float64).eps)
    torch.testing.assert_close(vjp, fd, rtol=0, atol=8*torch.finfo(torch.float64).eps)


def test_large_source_preserves_representable_source_derivative():
    z = torch.zeros((1, 1), **F64)
    source = torch.tensor(1e300, requires_grad=True, **F64)
    warm = _zero(c.WarmPhaseOutputs)._replace(praut=z+1e200, pracw=z+source)
    state = _zero(c.CoordinatorState)._replace(qc=z+1e200)
    y = _limit(warm, state=state).praut.sum()
    grad, = torch.autograd.grad(y, source)
    assert y.item() == pytest.approx(1e100, rel=1e-14)
    assert grad.item() == pytest.approx(-1e-200, rel=1e-14, abs=0)


@pytest.mark.parametrize("tiny_rate", [1e-16, 1e-15, 3.0])
def test_small_normalized_numerator_keeps_value_and_rate_control_derivatives(tiny_rate):
    # r/S is subnormal or zero, but r*B/S is representable. At r=3,
    # evaluating r*B first would overflow, so this also checks the other order.
    z = torch.zeros((1, 1), **F64)
    state = _zero(c.CoordinatorState)._replace(qc=z+1e308)
    a = torch.zeros((), requires_grad=True, **F64)

    def output(a):
        warm = _zero(c.WarmPhaseOutputs)._replace(
            praut=z+tiny_rate*torch.exp(a), pracw=z+1.6e308)
        return _limit(warm, state=state).praut.sum()

    y = output(a)
    expected = tiny_rate/1.6
    assert y.item() == pytest.approx(expected, rel=1e-14)
    g, = torch.autograd.grad(y, a, create_graph=True)
    assert g.item() == pytest.approx(expected, rel=1e-14)
    h, = torch.autograd.grad(g, a)
    assert h.item() == pytest.approx(expected, rel=1e-14)
