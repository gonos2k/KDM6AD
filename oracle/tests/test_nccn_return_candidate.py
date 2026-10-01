import json
import numpy as np
from pathlib import Path
import sys
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.nccn_return_candidate import (
    baseline_level10,
    delta_return,
    delta_return_with_direct_fallback,
    direct_return,
    exact_zero_return,
)


def t(value, requires_grad=False):
    return torch.tensor(value, dtype=torch.float64, requires_grad=requires_grad)


def test_zero_applied_volume_is_identity_for_delta_return():
    n, rho, applied = t(3.7e9), t(0.88731), t(0.0)
    assert delta_return(n, applied, rho).item() == n.item()
    assert direct_return(n, applied, rho).item() == n.item()


def test_exact_zero_selector_keeps_live_applied_amount_tangent():
    rho0 = 0.88731
    n0 = 3.7e9
    amount0 = 0.0

    def exact(n, amount, rho):
        nin = n * rho
        nout = nin - amount
        return exact_zero_return(n, nin, nout, rho)

    def direct(n, amount, rho):
        return direct_return(n, amount, rho)

    def naive_bzero(n, amount, rho):
        nin = n * rho
        nout = nin - amount
        delta = nout - nin
        # Counterexample only: this value-only zero branch erases the live
        # applied-amount derivative at amount == 0.
        return torch.where(delta == 0.0, n, nout / rho)

    args = (t(n0), t(amount0), t(rho0))
    tangents = (t(0.0), t(1.0), t(0.0))
    exact_value, exact_jvp = torch.func.jvp(exact, args, tangents)
    direct_value, direct_jvp = torch.func.jvp(direct, args, tangents)
    naive_value, naive_jvp = torch.func.jvp(naive_bzero, args, tangents)
    assert exact_value.item() == direct_value.item() == naive_value.item() == n0
    assert exact_jvp.item() == direct_jvp.item() == -1.0 / rho0
    assert naive_jvp.item() == 0.0


def test_positive_and_negative_applied_volume_match_closed_form():
    for applied_value in (2.3e8, -4.1e8):
        n, rho, applied = t(3.7e9), t(0.88731), t(applied_value)
        expected = n.item() - applied.item() / rho.item()
        assert abs(delta_return(n, applied, rho).item() - expected) <= np.spacing(expected)
        assert abs(direct_return(n, applied, rho).item() - expected) <= np.spacing(expected)


def test_delta_return_has_requested_analytic_jvp():
    n0, a0, rho0 = 7.0e8, 1.2e8, 0.91
    dn, da, drho = 2.5e4, -3.0e4, 1.7e-5

    def f(n, applied, rho):
        return delta_return(n, applied, rho)

    _, tangent = torch.func.jvp(
        f,
        (t(n0), t(a0), t(rho0)),
        (t(dn), t(da), t(drho)),
    )
    expected = dn - da / rho0 + a0 * drho / (rho0 * rho0)
    assert np.isclose(tangent.item(), expected, rtol=2e-15, atol=1e-10)


def test_delta_return_vjp_has_requested_partials_at_nonzero_applied_volume():
    n, applied, rho = t(7.0e8, True), t(1.2e8, True), t(0.91, True)
    output = delta_return(n, applied, rho)
    grad_n, grad_applied, grad_rho = torch.autograd.grad(output, (n, applied, rho))
    assert grad_n.item() == 1.0
    assert np.isclose(grad_applied.item(), -1.0 / rho.item(), rtol=2e-15)
    assert np.isclose(
        grad_rho.item(), applied.item() / (rho.item() ** 2), rtol=2e-15
    )


def test_complete_consumption_and_near_zero_cancellation():
    n, rho = t(2.4e9), t(0.875)
    applied_full = t(n.item() * rho.item())
    direct_full = direct_return(n, applied_full, rho).item()
    delta_full = delta_return(n, applied_full, rho).item()
    # Both are mathematically zero; record exact residuals rather than hide the
    # cancellation behavior behind a broad relative tolerance.
    assert direct_full == 0.0
    assert delta_full == 0.0
    assert delta_return_with_direct_fallback(n, applied_full, rho).item() == 0.0

    applied_near = t(np.nextafter(applied_full.item(), 0.0))
    expected_near = (n.item() * rho.item() - applied_near.item()) / rho.item()
    direct_near = direct_return(n, applied_near, rho).item()
    delta_near = delta_return(n, applied_near, rho).item()
    fallback_near = delta_return_with_direct_fallback(n, applied_near, rho).item()
    assert direct_near.hex() == expected_near.hex()
    assert delta_near.hex() == "0x1.0000000000000p-21"
    assert fallback_near == direct_near
    full_value, full_tangent = torch.func.jvp(
        lambda number, density: delta_return_with_direct_fallback(
            number, number * density, density),
        (n, rho), (t(1.0), t(0.01)),
    )
    assert full_value.item() == 0.0
    assert full_tangent.item() == 0.0
    assert (delta_near - expected_near).hex() == "0x1.b6db6db6db6dcp-23"


def test_large_change_fallback_uses_direct_when_delta_exceeds_half_input():
    n, rho = t(1.0e9), t(0.9)
    applied = t(0.8e9)
    expected = direct_return(n, applied, rho).item()
    assert delta_return_with_direct_fallback(n, applied, rho).item() == expected


def test_fallback_jvp_and_vjp_remain_correct_for_tiny_near_consumption_output():
    n0, rho0 = 2.4e9, 0.875
    applied0 = np.nextafter(n0 * rho0, 0.0)
    dn, da, drho = 1.5e4, -2.0e4, 2.0e-6

    def f(n, applied, rho):
        return delta_return_with_direct_fallback(n, applied, rho)

    args = (t(n0), t(applied0), t(rho0))
    tangents = (t(dn), t(da), t(drho))
    value, tangent = torch.func.jvp(f, args, tangents)
    expected_tangent = dn - da / rho0 + applied0 * drho / (rho0 * rho0)
    assert 0.0 < value.item() < 1.0e-6
    assert np.isclose(tangent.item(), expected_tangent, rtol=2e-15, atol=1e-10)

    n, applied, rho = t(n0, True), t(applied0, True), t(rho0, True)
    grad_n, grad_applied, grad_rho = torch.autograd.grad(
        f(n, applied, rho), (n, applied, rho)
    )
    assert grad_n.item() == 1.0
    assert np.isclose(grad_applied.item(), -1.0 / rho0, rtol=2e-15)
    assert np.isclose(grad_rho.item(), applied0 / (rho0 * rho0), rtol=2e-15)


def test_hybrid_jvp_vjp_match_independent_finite_differences_on_both_sides():
    rho0, n0 = 0.9, 1.0e9
    n_in_volume = n0 * rho0
    dn, da, drho = 2.0e3, -3.0e3, 1.0e-8
    fd_step = 1.0e-3

    for fraction in (0.49, 0.51):
        a0 = fraction * n_in_volume

        def f(n, applied, rho):
            return delta_return_with_direct_fallback(n, applied, rho)

        args = (t(n0), t(a0), t(rho0))
        tangents = (t(dn), t(da), t(drho))
        value, tangent = torch.func.jvp(f, args, tangents)
        plus = f(*(arg + fd_step * direction for arg, direction in zip(args, tangents)))
        minus = f(*(arg - fd_step * direction for arg, direction in zip(args, tangents)))
        finite_difference = (plus.item() - minus.item()) / (2.0 * fd_step)
        assert np.isclose(tangent.item(), finite_difference, rtol=2e-7, atol=2e-5)

        n, applied, rho = t(n0, True), t(a0, True), t(rho0, True)
        grad_n, grad_applied, grad_rho = torch.autograd.grad(
            f(n, applied, rho), (n, applied, rho)
        )
        for variable_index, (value0, grad0) in enumerate(
            ((n0, grad_n.item()), (a0, grad_applied.item()), (rho0, grad_rho.item()))
        ):
            steps = (1.0e3, 1.0e3, 1.0e-8)
            step = steps[variable_index]
            plus_args = [n0, a0, rho0]
            minus_args = [n0, a0, rho0]
            plus_args[variable_index] = value0 + step
            minus_args[variable_index] = value0 - step
            fd = (f(*(t(x) for x in plus_args)).item()
                  - f(*(t(x) for x in minus_args)).item()) / (2.0 * step)
            assert np.isclose(grad0, fd, rtol=3e-7, atol=2e-5)


def test_hybrid_at_exact_half_threshold_has_value_continuity():
    n, rho = t(4.0), t(1.0)
    applied = t(2.0)
    hybrid = delta_return_with_direct_fallback(n, applied, rho).item()
    assert hybrid == direct_return(n, applied, rho).item()
    assert hybrid == delta_return(n, applied, rho).item()


def test_hybrid_threshold_counterexample_records_crossing_fd_roundoff():
    # Independent review case: the computed fraction is one rounding step
    # below one half. The negative side of this centered FD crosses the strict
    # > 0.5 branch and switches the returned value by one float64 ULP.
    n = t(113.83098838095603)
    rho = t(21.01288810535036)
    n_in_volume = 2391.917821770466
    n_out_volume = 3587.876732655699
    applied = t(n_in_volume - n_out_volume)

    def f(a):
        return delta_return_with_direct_fallback(n, a, rho)

    returned = f(applied).item()
    direct = direct_return(n, applied, rho).item()
    plain = delta_return(n, applied, rho).item()
    assert abs(returned - plain) == 0.0  # this point selects the increment arm
    assert abs(direct - plain) == np.spacing(plain)

    _, jvp = torch.func.jvp(
        lambda a: f(a), (applied,), (t(1.0),)
    )
    step = 1.0e-12
    central_fd = (f(applied + t(step)).item() - f(applied - t(step)).item()) / (2.0 * step)
    formal = -1.0 / rho.item()
    assert np.isclose(jvp.item(), formal, rtol=2e-15)
    # This is a recorded nonsmooth rounding counterexample, not a relaxed FD
    # pass: the stencil straddles the arithmetic branch and misses the
    # branch-local derivative by more than five percent.
    assert abs(central_fd - formal) / abs(formal) > 0.05


def test_level10_extracted_fixture_replays_qv_endpoints():
    fixture = Path(__file__).resolve().parents[2] / "harness/evidence/nccn_return_level10_2026-10-01.json"
    result = baseline_level10(fixture)
    assert result["level"] == 10
    assert result["qv_direction"] != 0.0
    assert result["plus_rho_dry"] != result["minus_rho_dry"]
    # The direct conversion uses endpoint-specific rho_dry and endpoint-
    # specific N_in, reproducing the saved arithmetic at both endpoints.
    assert result["plus_direct_hex"] == result["plus_expected_hex"]
    assert result["minus_direct_hex"] == result["minus_expected_hex"]
    assert result["plus_direct_ulp_error"] == 0
    assert result["minus_direct_ulp_error"] == 0
    # The plain increment path preserves n at zero applied volume; endpoint
    # subtraction differs from the saved minus endpoint by one float64 ULP.
    assert result["plus_delta_ulp_error"] == 0
    assert result["minus_delta_ulp_error"] == 1


def test_exact_zero_fixture_replays_direct_plus_minus_endpoints():
    fixture = Path(__file__).resolve().parents[2] / "harness/evidence/nccn_return_level10_2026-10-01.json"
    result = baseline_level10(fixture)
    n_hex = float(json.loads(fixture.read_text())["n"]).hex()
    for side in ("plus", "minus"):
        assert result[f"{side}_direct_hex"] == result[f"{side}_expected_hex"]
        assert result[f"{side}_exact_zero_hex"] == n_hex
        assert result[f"{side}_hybrid_hex"] == n_hex


def test_extracted_endpoint_quantization_is_not_a_universal_fd_pass():
    fixture = Path(__file__).resolve().parents[2] / "harness/evidence/nccn_return_level10_2026-10-01.json"
    result = baseline_level10(fixture)
    # The saved direct endpoints differ by one binary64 ULP: their central FD
    # is nonzero although the zero-increment live JVP is zero. Exact-zero and
    # magnitude-hybrid values instead stay at n and have a zero endpoint FD.
    assert result["expected_fd"] == 0.002384185791015625
    assert result["exact_zero_fd"] == 0.0
    assert result["hybrid_fd"] == 0.0


def test_exact_zero_formula_is_bitwise_direct_for_nonzero_and_near_removal():
    n, rho = t(2.4e9), t(0.875)
    cases = (t(2.3e8), t(-4.1e8), t(np.nextafter(n.item() * rho.item(), 0.0)))
    for applied in cases:
        nin = n * rho
        nout = nin - applied
        assert (nout - nin).item() != 0.0
        assert torch.equal(
            exact_zero_return(n, nin, nout, rho),
            direct_return(n, applied, rho),
        )
