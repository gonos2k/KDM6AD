"""Exact components can conserve and stay positive yet fail coupled timing."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from coupled_transfer_contract import (  # noqa: E402
    Reservoirs, TransferRates, ordered_split, coupled_exact,
    compare_coupling, check_declared_order,
)


STATE = Reservoirs(1., 0.)
RATES = TransferRates(1., 2.)


def test_exact_components_remain_conservative_positive_but_order_changes_distribution():
    result = compare_coupling(STATE, RATES, .5)
    for state in (result.a_then_b, result.b_then_a, result.coupled_exact):
        assert state.left >= 0 and state.right >= 0
        assert state.total() == pytest.approx(STATE.total(), abs=1e-15)
    assert result.order_l1 > .1
    assert result.a_then_b_reference_l1 > 0
    assert result.b_then_a_reference_l1 > 0
    assert result.a_then_b != result.b_then_a


def test_swapped_order_is_rejected_even_when_total_and_signs_pass():
    ba = ordered_split(STATE, RATES, .5, order="BA")
    assert ba.total() == pytest.approx(1.)
    check_declared_order(STATE, RATES, .5, ba, declared_order="BA")
    with pytest.raises(ValueError, match="declared operator order"):
        check_declared_order(STATE, RATES, .5, ba, declared_order="AB")


def test_combined_equilibrium_is_separate_from_each_component_pass():
    equilibrium = Reservoirs(2 / 3, 1 / 3)
    joint = coupled_exact(equilibrium, RATES, .5)
    assert joint.left == pytest.approx(equilibrium.left, abs=1e-15)
    assert joint.right == pytest.approx(equilibrium.right, abs=1e-15)
    ab = ordered_split(equilibrium, RATES, .5, order="AB")
    assert ab.total() == pytest.approx(1.)
    assert ab.left != pytest.approx(equilibrium.left, abs=1e-3)


def test_zero_transfer_and_one_active_operator_have_no_order_confusion():
    for rates in (TransferRates(0., 0.), TransferRates(1., 0.)):
        ab = ordered_split(STATE, rates, .5, order="AB")
        ba = ordered_split(STATE, rates, .5, order="BA")
        joint = coupled_exact(STATE, rates, .5)
        assert ab.left == pytest.approx(ba.left, abs=1e-15)
        assert ab.left == pytest.approx(joint.left, abs=1e-15)
    assert coupled_exact(STATE, TransferRates(0., 0.), .5) is STATE


def test_large_finite_equilibrium_avoids_intermediate_overflow():
    # total*b overflows, whereas total*(b/(a+b)) is finite.
    state = Reservoirs(5e307, 5e307)
    rates = TransferRates(8e307, 8e307)
    ref = coupled_exact(state, rates, 1e-308)
    assert ref == state
    result = compare_coupling(state, rates, 1e-308)
    assert result.coupled_exact == state
    one_way = Reservoirs(1e308, 0.)
    one_way_rates = TransferRates(0., 1e308)
    assert coupled_exact(one_way, one_way_rates, 1e-308) == one_way


@pytest.mark.parametrize("state,rates,dt", [
    (Reservoirs(-1., 2.), RATES, .5),
    (STATE, TransferRates(-1., 2.), .5),
    (STATE, TransferRates(1., float("nan")), .5),
    (STATE, RATES, 0.),
    (STATE, RATES, True),
])
def test_invalid_declared_component_domain_is_rejected(state, rates, dt):
    with pytest.raises(ValueError):
        compare_coupling(state, rates, dt)


def test_unknown_order_and_boolean_tolerance_are_rejected():
    with pytest.raises(ValueError, match="AB or BA"):
        ordered_split(STATE, RATES, .5, order="unspecified")
    with pytest.raises(ValueError, match="finite real"):
        check_declared_order(STATE, RATES, .5, STATE, declared_order="AB", atol=True)
    with pytest.raises(ValueError, match="nonnegative"):
        check_declared_order(STATE, TransferRates(0., 0.), .5,
                             Reservoirs(-1e-13, 1.), declared_order="AB")
