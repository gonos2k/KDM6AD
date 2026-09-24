"""Continuous event time and discrete cap derivatives are separate claims."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from event_derivative_contract import (  # noqa: E402
    CoolingEvent, EventLocation, classify_cooling_event,
    cooling_event_sensitivity, discrete_cap, branch_changing_increment,
)


def _event(t0=274.15, rate=.02, start=0., end=100.):
    return CoolingEvent(t0, 273.15, rate, start, end)


def test_interior_cooling_event_time_and_independent_temperature_difference():
    event = _event()
    result = cooling_event_sensitivity(event)
    assert classify_cooling_event(event) is EventLocation.INTERIOR
    assert result.event_time_s == pytest.approx(50.)
    assert result.dtime_dinitial_temperature_s_per_k == pytest.approx(50.)
    assert result.dtime_dcooling_rate_s2_per_k == pytest.approx(-2500.)
    eps = 1e-4
    fd = (cooling_event_sensitivity(_event(t0=event.initial_temperature_k + eps)).event_time_s
          - cooling_event_sensitivity(_event(t0=event.initial_temperature_k - eps)).event_time_s
          ) / (2 * eps)
    assert fd == pytest.approx(50., rel=1e-9)


def test_event_window_boundary_and_outside_are_not_smooth_interior_sensitivities():
    assert classify_cooling_event(_event(t0=275.15)) is EventLocation.BOUNDARY
    assert classify_cooling_event(_event(t0=275.16)) is EventLocation.OUTSIDE
    for event in (_event(t0=275.15), _event(t0=275.16), _event(t0=273.15)):
        with pytest.raises(ValueError, match="interior transverse"):
            cooling_event_sensitivity(event)


def test_strict_cap_has_different_one_sided_differences_at_its_kink():
    epsilon = 1e-4
    exact = discrete_cap(20.)
    assert exact.value == 20 and not exact.active_cap
    assert exact.selected_tangent == 1.  # executed branch convention, not unique derivative
    left = (exact.value - discrete_cap(20. - epsilon).value) / epsilon
    right = (discrete_cap(20. + epsilon).value - exact.value) / epsilon
    symmetric = (discrete_cap(20. + epsilon).value
                 - discrete_cap(20. - epsilon).value) / (2 * epsilon)
    assert left == pytest.approx(1.)
    assert right == 0.
    assert symmetric == pytest.approx(.5)
    assert discrete_cap(19.).selected_tangent == 1.
    assert discrete_cap(21.).selected_tangent == 0.


def test_branch_crossing_finite_increment_is_not_local_jvp():
    start, end = 19.9, 20.1
    actual = branch_changing_increment(start, end)
    assert actual == pytest.approx(.1)
    assert actual != pytest.approx(discrete_cap(start).selected_tangent * (end - start))


@pytest.mark.parametrize("event", [
    _event(rate=0.),
    _event(rate=-.1),
    _event(start=100., end=0.),
    _event(t0=float("nan")),
    _event(rate=True),
])
def test_invalid_event_domain_is_rejected(event):
    with pytest.raises(ValueError):
        classify_cooling_event(event)


def test_underresolved_event_rate_derivative_is_refused():
    event = CoolingEvent(273.15 + 1e-150, 273.15, 1e-200, 0., 1e100)
    # T0 rounds to the threshold at this magnitude, so event is on the
    # boundary and no interior sensitivity can be reported.
    with pytest.raises(ValueError):
        cooling_event_sensitivity(event)
    square_underflows = CoolingEvent(1e-200, 0., 1e-200, 0., 2.)
    assert cooling_event_sensitivity(square_underflows).dtime_dcooling_rate_s2_per_k == pytest.approx(-1e200)
    square_overflows = CoolingEvent(373.15, 273.15, 1e155, 0., 1e-152)
    derivative = cooling_event_sensitivity(square_overflows).dtime_dcooling_rate_s2_per_k
    assert derivative != 0.0
    assert derivative / (-1e-308) == pytest.approx(1., rel=1e-12)
    unrepresentable = CoolingEvent(1e-320, 0., 1e-320, 0., 2.)
    with pytest.raises(ValueError, match="overflowed"):
        cooling_event_sensitivity(unrepresentable)
    rate_derivative_underflows = CoolingEvent(274.15, 273.15, 1e200, 0., 1e-199)
    assert classify_cooling_event(rate_derivative_underflows) is EventLocation.INTERIOR
    with pytest.raises(ValueError, match="below binary64 resolution"):
        cooling_event_sensitivity(rate_derivative_underflows)
    event_time_underflows = CoolingEvent(5e-324, 0., 1e308, -1., 1.)
    with pytest.raises(ValueError, match="below binary64 resolution"):
        classify_cooling_event(event_time_underflows)


@pytest.mark.parametrize("value,cap", [(True, 20.), (20., True),
                                        (float("inf"), 20.), (1., 0.)])
def test_invalid_cap_inputs_are_rejected(value, cap):
    with pytest.raises(ValueError):
        discrete_cap(value, cap=cap)
