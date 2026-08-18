"""A residual is not a closure certificate (owner review §10).

`|R| < ulp(W_0)` compares the residual to the initial inventory's own
resolution. That is a useful SIZE indicator and says nothing about how many
operations produced the residual, so it cannot certify that the budget closed
to roundoff -- and a ratio of two residuals is a physical comparison only when
both are resolved above their own roundoff.
"""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_water_enthalpy_basis as wb  # noqa: E402


def test_gamma_is_the_standard_forward_error_factor():
    u = 2.0 ** -53
    assert wb._gamma(1) == pytest.approx(u / (1 - u), rel=1e-12)
    assert wb._gamma(48) == pytest.approx(48 * u / (1 - 48 * u), rel=1e-12)
    # n*u >= 1 has no bound to offer, and must not return a small number
    assert wb._gamma(2 ** 60) == math.inf


def _run(qv=0.0, water=1.0, prec=0.0, rho=1.0, dz=1.0, ks=(1, 2), col=1):
    """One column, `ks` levels, every species carrying `water`."""
    r = {}
    for k in ks:
        r[("forcing", "rho", col, k)] = rho
        r[("forcing", "delz", col, k)] = dz
        r[("initial", "qv", col, k)] = qv
        for s in wb.WATER:
            r[("initial", s, col, k)] = water
            r[("state", s, col, k)] = water
    r[("prec", 1, col)] = prec
    return r


def test_the_bound_carries_the_operation_count_and_the_magnitudes():
    """The budget is two column sums plus a surface term, so the bound has to
    grow with both the number of terms and what was summed -- cancellation is
    exactly what a residual near zero hides."""
    small = wb.water(_run(water=1.0))["1"]["operator"]
    large = wb.water(_run(water=1e6))["1"]["operator"]
    assert large["roundoff_bound"] > small["roundoff_bound"] * 1e5
    assert small["roundoff_ops"] == len(wb.WATER) * 2
    wide = wb.water(_run(water=1.0, ks=(1, 2, 3, 4)))["1"]["operator"]
    assert wide["roundoff_ops"] > small["roundoff_ops"]
    assert wide["roundoff_bound"] > small["roundoff_bound"]


def test_a_closed_budget_passes_screening_and_an_open_one_does_not():
    closed = wb.water(_run(water=1.0, prec=0.0))["1"]["operator"]
    assert closed["residual"] == 0.0
    assert closed["passes_roundoff_screening"] is True
    open_ = wb.water(_run(water=1.0, prec=1.0))["1"]["operator"]
    assert abs(open_["residual"]) > open_["roundoff_bound"]
    assert open_["passes_roundoff_screening"] is False


def test_the_sub_ulp_predicate_is_named_for_what_it_says():
    """It was `closes_within_one_initial_ulp`, which reads as a closure
    verdict. The closure verdict is `passes_roundoff_screening`; this one
    states a size relation and is named for it."""
    row = wb.water(_run(water=1.0))["1"]["operator"]
    assert "is_sub_ulp_of_initial_inventory" in row
    assert "closes_within_one_initial_ulp" not in row
    assert "passes_roundoff_screening" in row


def test_basis_factor_is_null_when_the_denominator_is_not_resolved():
    """A ratio of two residuals is arbitrarily large when the denominator is
    at roundoff -- correct as arithmetic, meaningless as a statement about the
    bases. Unresolved gets `null` AND a reason, never a number."""
    row = wb.water(_run(water=1.0, prec=0.0))["1"]        # residual exactly 0
    assert row["basis_factor"] is None
    assert "basis_factor_unresolved" in row
    # ...and a resolved pair still reports the comparison
    resolved = wb.water(_run(qv=0.5, water=1.0, prec=1.0))["1"]
    if resolved["basis_factor"] is not None:
        assert "basis_factor_unresolved" not in resolved
