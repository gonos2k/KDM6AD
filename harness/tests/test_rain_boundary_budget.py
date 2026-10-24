from fractions import Fraction

import numpy as np
import pytest

from harness.rain_boundary_budget import step_budget, reported_budget, surface_component


def test_conservative_nonuniform_measure_distinguishes_bottom_arrival_and_departure():
    before = np.array([[3.0, 3.0, 2.0]])
    out = np.array([[1.0, 0.4, 0.25]])
    incoming = np.array([[0.0, 2 / 3, 0.24]])
    after = before - out + incoming
    b = step_budget(
        before, after, out, incoming, np.array([[2.0, 3.0, 5.0]]), np.ones((1, 3))
    )
    assert b["actual_bottom_departure"][0] == 1.25
    assert b["actual_bottom_arrival"][0] == 1.2
    assert b["bottom_net_depletion"][0] == pytest.approx(0.05)
    assert abs(b["state_plus_bottom_plus_internal_residual"][0]) < b["roundoff_gate"][0]


def test_reported_overcount_and_internal_loss_are_separate_signed_terms():
    before = np.array([[1.0, 0.25]])
    out = np.array([[0.8, 0.25]])
    incoming = np.array([[0.0, 0.2]])
    b = step_budget(
        before,
        before - out + incoming,
        out,
        incoming,
        np.array([[2.0, 5.0]]),
        np.ones((1, 2)),
    )
    total = reported_budget([b], np.array([2.5]))
    assert b["actual_bottom_departure"][0] == 1.25
    assert b["actual_bottom_arrival"][0] == 1.0
    assert b["bottom_net_depletion"][0] == pytest.approx(0.25)
    assert total["internal_departure_minus_arrival"][0] == pytest.approx(0.6)
    assert total["reported_bottom_minus_applied"][0] == 1.25
    assert total["state_plus_reported"][0] == pytest.approx(0.65)
    assert abs(total["decomposition_residual"][0]) < total["roundoff_gate"][0]


def test_interface_excess_arrival_is_signed_not_assumed_a_sink():
    before = np.array([[2.0, 1.0]])
    out = np.array([[0.1, 0.1]])
    incoming = np.array([[0.0, 0.3]])
    b = step_budget(
        before, before - out + incoming, out, incoming, np.ones((1, 2)), np.ones((1, 2))
    )
    assert b["internal_departure_minus_arrival"][0] < 0
    assert abs(b["state_plus_bottom_plus_internal_residual"][0]) < b["roundoff_gate"][0]


def test_delta_product_sum_matches_exact_sum_of_already_rounded_products():
    before = np.array([[1e16, 1.0, 1e16]])
    after = np.array([[1e16 + 2, 2.0, 1e16 - 2]])
    w = np.array([[2.0, 3.0, 5.0]])
    # Arithmetic-only open ledger: test delta products, not a physical update.
    departure = np.maximum(before - after, 0.0)
    arrival = np.maximum(after - before, 0.0)
    arrival[0, 0] = 0.0
    b = step_budget(before, after, departure, arrival, w, np.ones((1, 3)))
    expected = float(
        sum(
            (
                Fraction.from_float(float(w[0, k] * (after[0, k] - before[0, k])))
                for k in range(3)
            ),
            Fraction(),
        )
    )
    assert b["state_change"][0] == expected


def test_surface_component_preserves_left_associated_source_conversion():
    rate = np.array([0.12345678901234567])
    depth = np.array([17.23456789012345])
    actual = surface_component(rate, depth, 20.0)
    expected = (((rate * depth) / 1000.0) * 20.0) * 1000.0
    np.testing.assert_array_equal(actual.view("u8"), expected.view("u8"))


@pytest.mark.parametrize("invalid", ["top_arrival", "bad_geometry", "nonfinite"])
def test_invalid_accounting_arrays_are_rejected(invalid):
    a = np.ones((1, 2))
    out = np.zeros_like(a)
    incoming = np.zeros_like(a)
    rho = a.copy()
    if invalid == "top_arrival":
        incoming[0, 0] = 1.0
    elif invalid == "bad_geometry":
        rho[0, 0] = 0.0
    else:
        out[0, 0] = np.nan
    with pytest.raises(ValueError):
        step_budget(a, a, out, incoming, rho, a)
