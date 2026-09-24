"""A non-sedimentation pilot for signed, capacity-limited face exchange."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from signed_face_exchange import (  # noqa: E402
    WaterCells, FaceEvent, check_face_exchange, two_cell_soil_head_step,
)


def _cells(left=.30, right=.10, *, porosity_left=.40, porosity_right=.40):
    return WaterCells(left, right, .10, .20, porosity_left, porosity_right)


def test_head_reversal_changes_donor_and_conserves_one_face_amount():
    before = _cells()
    forward, event = two_cell_soil_head_step(
        before, head_left_m=1., head_right_m=0.,
        conductivity_m_s=.001, face_distance_m=1., dt_s=5.)
    assert event.requested_m == pytest.approx(.005)
    assert event.applied_m > 0
    assert forward.theta_left < before.theta_left
    assert forward.theta_right > before.theta_right
    assert (before.theta_left - forward.theta_left) != pytest.approx(
        forward.theta_right - before.theta_right)
    assert sum(forward.inventories_m()) == pytest.approx(sum(before.inventories_m()))
    assert abs(check_face_exchange(before, forward, event).total_residual_m) < 1e-15

    reverse, backward = two_cell_soil_head_step(
        before, head_left_m=0., head_right_m=1.,
        conductivity_m_s=.001, face_distance_m=1., dt_s=5.)
    assert backward.applied_m < 0
    assert reverse.theta_left > before.theta_left
    assert reverse.theta_right < before.theta_right
    assert sum(reverse.inventories_m()) == pytest.approx(sum(before.inventories_m()))


def test_receiver_capacity_and_donor_availability_limit_requested_exchange():
    receiver_limited = _cells(right=.29, porosity_right=.30)
    after, event = two_cell_soil_head_step(
        receiver_limited, head_left_m=2., head_right_m=0.,
        conductivity_m_s=.01, face_distance_m=1., dt_s=5.)
    assert event.requested_m == pytest.approx(.1)
    assert event.applied_m == pytest.approx(.002)
    assert after.theta_right == pytest.approx(after.porosity_right)
    assert abs(check_face_exchange(receiver_limited, after, event).total_residual_m) < 1e-15

    donor_limited = _cells(left=.01, right=.1)
    after, event = two_cell_soil_head_step(
        donor_limited, head_left_m=2., head_right_m=0.,
        conductivity_m_s=.01, face_distance_m=1., dt_s=5.)
    assert event.applied_m == pytest.approx(.001)
    assert after.theta_left == pytest.approx(0.0)


def test_equal_head_is_stationary_even_with_unequal_water_contents():
    before = _cells(left=.3, right=.1)
    after, event = two_cell_soil_head_step(
        before, head_left_m=.7, head_right_m=.7,
        conductivity_m_s=.01, face_distance_m=.3, dt_s=20.)
    assert event == FaceEvent(0.0, 0.0)
    assert after == before


def test_external_supply_is_separate_from_internal_face_transfer():
    before = _cells()
    event = FaceEvent(requested_m=.004, applied_m=.004,
                      external_left_m=.001, external_right_m=-.002)
    left, right = before.inventories_m()
    after = WaterCells((left - .004 + .001) / .1,
                       (right + .004 - .002) / .2,
                       .1, .2, .4, .4)
    budget = check_face_exchange(before, after, event)
    assert abs(budget.total_residual_m) < 1e-15
    assert sum(after.inventories_m()) - sum(before.inventories_m()) == pytest.approx(-.001)


@pytest.mark.parametrize("after,event,error", [
    (_cells(left=.25, right=.125), FaceEvent(.005, -.005), "direction"),
    (_cells(), FaceEvent(0., 1e-13), "direction"),
    (_cells(left=.25, right=.125), FaceEvent(.004, .005), "bound"),
    (_cells(left=.24, right=.13), FaceEvent(.005, .005), "inventories"),
    (_cells(left=.3, right=.41), FaceEvent(.005, .005), "outside"),
    (_cells(left=.3, right=.1), FaceEvent(float("nan"), 0.), "finite"),
])
def test_checker_rejects_wrong_direction_overdraw_state_and_nan(after, event, error):
    with pytest.raises(ValueError, match=error):
        check_face_exchange(_cells(), after, event)


def test_variable_geometry_requires_a_different_inventory_contract():
    before = _cells()
    changed = WaterCells(.3, .1, .12, .2, .4, .4)
    with pytest.raises(ValueError, match="changing geometry"):
        check_face_exchange(before, changed, FaceEvent(0., 0.))


@pytest.mark.parametrize("theta_left", [-1e-12, .4 + 1e-12])
def test_admissibility_tolerance_is_water_depth_not_dimensionless_theta(theta_left):
    # A 1e-12 theta deviation in a 100 m layer is 1e-10 m of water,
    # exceeding the declared 1e-12 m inventory tolerance.
    invalid = WaterCells(theta_left, .1, 100., .2, .4, .4)
    with pytest.raises(ValueError, match="outside"):
        check_face_exchange(invalid, invalid, FaceEvent(0., 0.))
