"""Tests for the opt-in fp64 QR actual-departure substep."""

import pytest
import torch

from oracle.kdm6 import constants
from oracle.kdm6.qr_actual_transport import actual_qr_substep


def test_nonuniform_metric_actual_departure_closes_without_ledger_and_preserves_fall_seed():
    # The top donor is capped at q=1.0. Its actual mass (rho*dz*q = 2)
    # reaches the thinner lower cell without a second donor-post-state cap.
    qr = torch.tensor([[1.0, 0.2]], dtype=torch.float64)
    fall_before = torch.tensor([[0.11, 0.23]], dtype=torch.float64)
    result = actual_qr_substep(
        qr,
        fall_before,
        torch.tensor([[1.5, 1.5]], dtype=torch.float64),
        torch.ones_like(qr),
        torch.tensor([[2.0, 1.0]], dtype=torch.float64),
        torch.ones(1, dtype=torch.float64),
        1,
        1.0,
    )

    torch.testing.assert_close(
        result.departure,
        torch.tensor([[1.0, 0.2]], dtype=torch.float64),
        rtol=0,
        atol=0,
    )
    torch.testing.assert_close(
        result.arrival, torch.tensor([[0.0, 2.0]], dtype=torch.float64), rtol=0, atol=0
    )
    torch.testing.assert_close(
        result.qr, torch.tensor([[0.0, 2.0]], dtype=torch.float64), rtol=0, atol=0
    )
    torch.testing.assert_close(
        result.fall_qr - fall_before, result.departure, rtol=0, atol=1e-15
    )

    measure = torch.tensor([[2.0, 1.0]], dtype=torch.float64)
    state_delta = torch.sum(measure * (result.qr - qr))
    actual_bottom_departure = measure[0, -1] * result.departure[0, -1]
    assert state_delta.item() == pytest.approx(-0.2, abs=1e-15)
    assert actual_bottom_departure.item() == pytest.approx(0.2, abs=1e-15)
    assert (state_delta + actual_bottom_departure).item() == pytest.approx(
        0.0, abs=1e-15
    )

    # The surface increment represented by the newly accumulated QR rate is
    # exactly the actual bottom departure (numerically mm == kg/m^2 here).
    surface_increment = (result.fall_qr[0, -1] - fall_before[0, -1]) * 1.0 * 1.0
    assert surface_increment.item() == pytest.approx(
        actual_bottom_departure.item(), abs=1e-15
    )


def test_local_count_gate_is_columnwise_and_noop_columns_keep_accumulators():
    qr = torch.tensor([[0.4, 0.1], [0.3, 0.2]], dtype=torch.float64)
    fall = torch.tensor([[0.03, 0.04], [0.05, 0.06]], dtype=torch.float64)
    work = torch.full_like(qr, 0.2)
    metric = torch.ones_like(qr)
    result = actual_qr_substep(
        qr,
        fall,
        work,
        metric,
        metric,
        torch.tensor([1.0, 2.0], dtype=torch.float64),
        2,
        1.0,
    )
    torch.testing.assert_close(result.qr[0], qr[0], rtol=0, atol=0)
    torch.testing.assert_close(result.fall_qr[0], fall[0], rtol=0, atol=0)
    torch.testing.assert_close(
        result.departure[0], torch.zeros_like(qr[0]), rtol=0, atol=0
    )
    torch.testing.assert_close(
        result.arrival[0], torch.zeros_like(qr[0]), rtol=0, atol=0
    )
    assert torch.any(result.departure[1] > 0)


def test_entry_cap_below_at_and_above_tie_and_framework_minimum_subgradient():
    qr = torch.ones((1, 3), dtype=torch.float64)
    work = torch.tensor([[0.99, 1.0, 1.01]], dtype=torch.float64, requires_grad=True)
    result = actual_qr_substep(
        qr,
        torch.zeros_like(qr),
        work,
        torch.ones_like(qr),
        torch.ones_like(qr),
        torch.ones(1, dtype=torch.float64),
        1,
        1.0,
    )
    torch.testing.assert_close(
        result.departure,
        torch.tensor([[0.99, 1.0, 1.0]], dtype=torch.float64),
        rtol=0,
        atol=0,
    )
    (tie_work_grad,) = torch.autograd.grad(result.departure[0, 1], work)
    assert tie_work_grad[0, 1].item() == pytest.approx(0.5, abs=0.0)
    # This pins the selected min subgradient at the tie; central FD across the
    # tie is intentionally not treated as a classical derivative test.


def test_shared_rho_dz_jvp_vjp_and_branch_stable_independent_finite_differences():
    inputs = (
        torch.tensor([[0.5, 0.15, 0.07], [0.35, 0.22, 0.11]], dtype=torch.float64),
        torch.tensor([[0.03, 0.02, 0.01], [0.04, 0.01, 0.05]], dtype=torch.float64),
        torch.tensor([[0.4, 0.8, 3.0], [0.3, 1.5, 0.6]], dtype=torch.float64),
        torch.tensor([[1.1, 0.9, 1.25], [0.85, 1.3, 0.95]], dtype=torch.float64),
        torch.tensor([[2.1, 1.2, 3.1], [1.4, 2.7, 1.1]], dtype=torch.float64),
    )
    directions = (
        torch.tensor([[0.02, -0.01, 0.03], [-0.03, 0.04, 0.02]], dtype=torch.float64),
        torch.tensor([[0.01, -0.02, 0.03], [0.04, 0.02, -0.01]], dtype=torch.float64),
        torch.tensor([[0.03, 0.01, -0.02], [-0.01, 0.04, 0.02]], dtype=torch.float64),
        torch.tensor([[0.01, -0.03, 0.02], [-0.02, 0.01, 0.04]], dtype=torch.float64),
        torch.tensor([[0.02, 0.01, -0.03], [0.01, -0.02, 0.03]], dtype=torch.float64),
    )
    counts = torch.tensor([2.0, 3.0], dtype=torch.float64)
    seed = torch.arange(1, 25, dtype=torch.float64).reshape(4, 2, 3) / 17.0

    def outputs(qr, fall, work, rho, dz):
        out = actual_qr_substep(qr, fall, work, rho, dz, counts, 1, 1.0)
        return torch.stack((out.qr, out.fall_qr, out.departure, out.arrival))

    _, tangent = torch.autograd.functional.jvp(outputs, inputs, directions)
    differentiable_inputs = tuple(
        value.detach().clone().requires_grad_() for value in inputs
    )
    value = outputs(*differentiable_inputs)
    gradients = torch.autograd.grad(value, differentiable_inputs, seed)
    lhs = torch.sum(tangent * seed)
    rhs = sum(
        torch.sum(gradient * direction)
        for gradient, direction in zip(gradients, directions)
    )
    torch.testing.assert_close(lhs, rhs, rtol=2e-13, atol=2e-13)
    assert (
        torch.count_nonzero(gradients[3]) > 0
    )  # rho affects both flux and shared interfaces.
    assert (
        torch.count_nonzero(gradients[4]) > 0
    )  # dz affects shared interface conversion.

    base = outputs(*inputs)
    for epsilon in (1.0e-4, 3.0e-5):
        plus = outputs(*(x + epsilon * dx for x, dx in zip(inputs, directions)))
        minus = outputs(*(x - epsilon * dx for x, dx in zip(inputs, directions)))
        # Keep the same min branch on both sides: one cap-active donor and all
        # other donors below their entry cap.
        for side in (plus, minus):
            assert torch.all(torch.isfinite(side))
        fd = (plus - minus) / (2.0 * epsilon)
        torch.testing.assert_close(fd, tangent, rtol=2e-6, atol=2e-9)
    assert torch.all(torch.isfinite(base))


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("qr", -0.1, "nonnegative"),
        ("fall", -0.1, "nonnegative"),
        ("work", -0.1, "nonnegative"),
        ("rho", constants.QCRMIN, "density and depth"),
        ("delz", constants.QCRMIN, "density and depth"),
        ("mstep", 1.5, "integer counts"),
    ],
)
def test_invalid_entry_values_are_rejected(field, value, match):
    qr = torch.tensor([[0.2, 0.1]], dtype=torch.float64)
    fall = torch.zeros_like(qr)
    work = torch.full_like(qr, 0.1)
    rho = torch.ones_like(qr)
    dz = torch.ones_like(qr)
    mstep = torch.ones((1,), dtype=torch.float64)
    args = {
        "qr": qr,
        "fall_qr": fall,
        "work": work,
        "rho_d": rho,
        "delz": dz,
        "mstep": mstep,
    }
    if field in ("qr", "fall", "work"):
        target = args[{"qr": "qr", "fall": "fall_qr", "work": "work"}[field]]
        target[0, 0] = value
    elif field == "rho":
        rho[0, 0] = value
    elif field == "delz":
        dz[0, 0] = value
    else:
        mstep[0] = value
    with pytest.raises(ValueError, match=match):
        actual_qr_substep(qr, fall, work, rho, dz, mstep, 1, 1.0)


def test_mstep_is_fixed_metadata_and_invalid_step_or_dt_is_rejected():
    qr = torch.ones((1, 1), dtype=torch.float64)
    one = torch.ones_like(qr)
    with pytest.raises(ValueError, match="must not require gradients"):
        actual_qr_substep(
            qr,
            torch.zeros_like(qr),
            one,
            one,
            one,
            torch.ones(1, dtype=torch.float64, requires_grad=True),
            1,
            1.0,
        )
    with pytest.raises(ValueError, match="positive integer"):
        actual_qr_substep(
            qr, torch.zeros_like(qr), one, one, one, torch.ones(1), True, 1.0
        )
    with pytest.raises(ValueError, match="finite and positive"):
        actual_qr_substep(
            qr, torch.zeros_like(qr), one, one, one, torch.ones(1), 1, 0.0
        )
