"""Independent freeze-share witnesses for extreme finite f64 caps."""

from __future__ import annotations

from decimal import Decimal, localcontext
import math

import pytest
import torch

from kdm6.coordinator import MeltFreezePhaseOutputs
from kdm6.process_controls import ProcessControls, apply_freeze_controls


F64 = {"dtype": torch.float64}


def _number_cap(a1, a2, budget, alpha):
    a1 = torch.as_tensor(a1, **F64)
    a2 = torch.as_tensor(a2, **F64)
    budget = torch.as_tensor(budget, **F64)
    z = torch.zeros_like(a1)
    mf = MeltFreezePhaseOutputs(*(z for _ in MeltFreezePhaseOutputs._fields))
    mf = mf._replace(ninuc=a1, nfrzdtc=a2)
    controls = ProcessControls(alpha_freeze=torch.as_tensor(alpha, **F64))
    return apply_freeze_controls(mf, controls, z, budget)


def _decimal_share(a1: str, a2: str, budget: str) -> float:
    # Match the actual f64 tensors passed to the module, while retaining more
    # precision than a binary-float expectation for the subnormal witnesses.
    with localcontext() as ctx:
        ctx.prec = 80
        a1f = Decimal.from_float(float(a1))
        a2f = Decimal.from_float(float(a2))
        bf = Decimal.from_float(float(budget))
        return float(bf * a1f / (a1f + a2f))


def _assert_decimal_close(actual: float, expected: float):
    # For subnormal witnesses the relative tolerance itself rounds to zero;
    # allow one f64 minimum-subnormal step in addition to the relative check.
    min_subnormal = 5.0e-324
    tolerance = max(abs(expected) * 1.0e-12, min_subnormal)
    assert abs(actual - expected) <= tolerance


@pytest.mark.parametrize(
    ("a1", "a2", "budget"),
    [("1e-300", "1e300", "1e301"),
     ("1e-320", "1e8", "1e9")],
)
def test_extreme_number_share_keeps_tiny_first_amount(a1, a2, budget):
    """The binding share B*a1/(a1+a2) remains representable."""
    out = _number_cap(float(a1), float(a2), float(budget), 3.0)
    expected = _decimal_share(a1, a2, budget)
    _assert_decimal_close(out.ninuc.item(), expected)


def test_mixed_binding_unbound_tie_zero_and_none_identity():
    a1 = torch.tensor([[1e-320, .2, 1., 0.]], **F64)
    a2 = torch.tensor([[1e8, .3, 1., 0.]], **F64)
    budget = torch.tensor([[1e9, 100., 4., 1.]], **F64)
    # Cell 0 binds, cell 1 is unbound, cell 2 is exact draw=budget tie,
    # and cell 3 is zero. Per-cell alpha exercises all branches together.
    alpha = torch.tensor([[3., 3., math.log(2.), 3.]],
                         requires_grad=True, **F64)
    z = torch.zeros_like(a1)
    mf = MeltFreezePhaseOutputs(*(z for _ in MeltFreezePhaseOutputs._fields))
    mf = mf._replace(ninuc=a1, nfrzdtc=a2,
                     pfrzdtr=torch.full_like(a1, 7.0))
    before = {name: getattr(mf, name).clone()
              for name in ("ninuc", "nfrzdtc", "pfrzdtr")}
    out = apply_freeze_controls(
        mf, ProcessControls(alpha_freeze=alpha), z, budget)
    _assert_decimal_close(out.ninuc[0, 0].item(),
                          _decimal_share("1e-320", "1e8", "1e9"))
    assert out.ninuc[0, 1].item() == pytest.approx(.2 * math.exp(3.0),
                                                    rel=1e-14)
    assert out.ninuc[0, 2].item() == pytest.approx(2.0, rel=1e-14)
    assert out.ninuc[0, 3].item() == 0.0
    assert torch.equal(out.pfrzdtr, mf.pfrzdtr)
    alpha_grad, = torch.autograd.grad(out.ninuc.sum(), alpha)
    assert alpha_grad[0, 0].item() == pytest.approx(0.0, abs=0.0)
    assert alpha_grad[0, 1].item() == pytest.approx(.2 * math.exp(3.0),
                                                     rel=1e-14)
    # Exact draw=budget follows the documented unbound branch at the kink.
    assert alpha_grad[0, 2].item() == pytest.approx(2.0, rel=1e-14)
    assert alpha_grad[0, 3].item() == pytest.approx(0.0, abs=0.0)
    for name, original in before.items():
        assert torch.equal(getattr(mf, name), original)

    same = apply_freeze_controls(mf, None, z, budget)
    assert same is mf


def _raw_share(a2):
    one = torch.ones((1, 1), **F64)
    z = torch.zeros_like(one)
    a2 = a2.expand_as(one)
    mf = MeltFreezePhaseOutputs(*(z for _ in MeltFreezePhaseOutputs._fields))
    mf = mf._replace(ninuc=one, nfrzdtc=a2)
    controls = ProcessControls(
        alpha_freeze=torch.tensor(.5, requires_grad=False, **F64))
    return apply_freeze_controls(
        mf, controls, z, torch.full_like(one, 1.5e200)).ninuc.sum()


def test_binding_share_raw_rate_and_log_parameter_ad_are_stable():
    a2 = torch.tensor(1e200, requires_grad=True, **F64)
    y = _raw_share(a2)
    raw_grad, = torch.autograd.grad(y, a2)
    expected_raw = float(-Decimal("1.5e200") /
                        (Decimal("1e200") + Decimal(1))**2)
    assert raw_grad.item() == pytest.approx(expected_raw, rel=1e-12, abs=0.0)

    def beta_output(beta):
        return _raw_share(torch.tensor(1e200, **F64) * torch.exp(beta))

    beta = torch.tensor(0.0, requires_grad=True, **F64)
    value, jvp = torch.func.jvp(
        beta_output, (beta,), (torch.ones_like(beta),))
    vjp, = torch.autograd.grad(value, beta, create_graph=True)
    second, = torch.autograd.grad(vjp, beta)
    h = 1e-5
    fd = (beta_output(torch.tensor(h, **F64))
          - beta_output(torch.tensor(-h, **F64))) / (2.0 * h)

    assert value.item() == pytest.approx(1.5, rel=1e-14)
    assert jvp.item() == pytest.approx(-1.5, rel=1e-14)
    assert vjp.item() == pytest.approx(-1.5, rel=1e-14)
    assert second.item() == pytest.approx(1.5, rel=1e-14)
    assert fd.item() == pytest.approx(-1.5, rel=1e-10)


def test_larger_share_keeps_its_small_self_derivative():
    # The larger output rounds to B, but dY_large/da2 = B*a1/S**2 is
    # representable. Complementing the small share avoids cancellation.
    a2 = torch.tensor(1e200, requires_grad=True, **F64)
    y = _number_cap(1., a2, 1.5e200, .5).nfrzdtc
    grad, = torch.autograd.grad(y, a2)
    assert grad.item() == pytest.approx(1.5e-200, rel=1e-14, abs=0.)

    def output(beta):
        return _number_cap(1., 1e200*torch.exp(beta), 1.5e200, .5).nfrzdtc

    beta = torch.zeros((), requires_grad=True, **F64)
    y, tangent = torch.func.jvp(output, (beta,), (torch.ones_like(beta),))
    adj, = torch.autograd.grad(y, beta, create_graph=True)
    second, = torch.autograd.grad(adj, beta)
    assert y.item() == pytest.approx(1.5e200, rel=1e-14)
    assert tangent.item() == pytest.approx(1.5, rel=1e-14)
    assert adj.item() == pytest.approx(1.5, rel=1e-14)
    assert second.item() == pytest.approx(-1.5, rel=1e-14)
