"""Nonlinear observation mixing, fixed QC support and analysis increments."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from observation_support_contract import (  # noqa: E402
    planck_radiance, brightness_temperature, mixed_brightness_temperature,
    mixed_brightness_directional, quadratic_cost_on_support,
    compare_cost_same_support, analysis_inventory_increment,
)


WAVELENGTH = 10.8e-6  # monochromatic synthetic example, not an RTTOV channel


def _columns():
    return np.array([planck_radiance(260., WAVELENGTH),
                     planck_radiance(300., WAVELENGTH)], dtype=np.float64)


def test_mix_radiance_then_planck_inverse_not_average_of_bt():
    l = _columns()
    weights = np.array([.5, .5], dtype=np.float64)
    for temp, radiance in ((260., l[0]), (300., l[1])):
        assert brightness_temperature(radiance, WAVELENGTH) == pytest.approx(temp, abs=1e-12)
    combined = mixed_brightness_temperature(l, weights, WAVELENGTH)
    assert 280. < combined < 300.
    assert combined != pytest.approx(280., abs=.1)


def test_bt_direction_includes_weight_and_radiance_directions_once():
    l = _columns()
    w = np.array([.6, .4], dtype=np.float64)
    dl = np.array([.01 * l[0], -.02 * l[1]])
    dw = np.array([.001, -.001])
    analytic = mixed_brightness_directional(l, w, dl, dw, WAVELENGTH)
    h = 1e-4
    fd = (mixed_brightness_temperature(l + h * dl, w + h * dw, WAVELENGTH)
          - mixed_brightness_temperature(l - h * dl, w - h * dw, WAVELENGTH)) / (2 * h)
    assert analytic == pytest.approx(fd, rel=1e-8, abs=1e-8)
    without_weight_direction = mixed_brightness_directional(
        l, w, dl, np.zeros_like(dw), WAVELENGTH)
    assert analytic != pytest.approx(without_weight_direction, abs=1e-3)


def test_qc_support_change_cannot_be_reported_as_state_improvement():
    prediction = np.array([280., 290.])
    observation = np.array([280., 300.])
    sigma = np.array([1., 1.])
    direction = np.array([1., 2.])
    both = np.array([True, True])
    first_only = np.array([True, False])
    full = quadratic_cost_on_support(prediction, observation, sigma, direction, both)
    filtered = quadratic_cost_on_support(prediction, observation, sigma, direction,
                                         first_only)
    assert full.value == pytest.approx(50.) and full.directional == pytest.approx(-20.)
    assert filtered.value == 0. and filtered.directional == 0.
    assert full.accepted and filtered.accepted
    with pytest.raises(ValueError, match="identical declared channel support"):
        compare_cost_same_support(prediction, prediction, observation, sigma, both,
                                  first_only)
    assert compare_cost_same_support(prediction, prediction, observation, sigma,
                                     both, both) == 0.


def test_large_finite_sigma_does_not_erase_representable_cost_direction():
    result = quadratic_cost_on_support(
        np.array([1e308]), np.array([5e307]), np.array([1e308]),
        np.array([1e308]), np.array([True]),
    )
    assert result.value == pytest.approx(.125)
    assert result.directional == pytest.approx(.5)


def test_empty_mask_is_diagnostic_zero_not_accepted_observation_cost():
    mask = np.array([False, False])
    missing = np.array([np.nan, np.nan])
    empty = quadratic_cost_on_support(missing, missing, missing, missing, mask)
    assert (empty.value, empty.directional, empty.usable_channels, empty.accepted) == (
        0., 0., 0, False)
    with pytest.raises(ValueError, match="empty support"):
        compare_cost_same_support(missing, missing, missing, missing, mask, mask)


def test_masked_out_nan_is_unread_but_kept_nan_rejects():
    mask = np.array([True, False])
    pred = np.array([280., np.nan])
    obs = np.array([280., np.nan])
    sigma = np.array([1., np.nan])
    tangent = np.array([0., np.nan])
    assert quadratic_cost_on_support(pred, obs, sigma, tangent, mask).accepted
    with pytest.raises(ValueError, match="kept channels"):
        quadratic_cost_on_support(pred, obs, sigma, tangent,
                                  np.array([True, True]))
    with pytest.raises(ValueError, match="brightness temperatures"):
        quadratic_cost_on_support(np.array([-9999., np.nan]), obs, sigma,
                                  tangent, mask)
    masked = np.ma.array([280., 999.], mask=[False, True])
    assert quadratic_cost_on_support(masked, obs, sigma, tangent, mask).accepted
    with pytest.raises(ValueError, match="kept channel cannot be masked"):
        quadratic_cost_on_support(masked, obs, sigma, tangent,
                                  np.array([True, True]))
    with pytest.raises(ValueError, match="kept boolean mask"):
        quadratic_cost_on_support([True, 999.], obs, sigma, tangent, mask)
    assert quadratic_cost_on_support([280., True], obs, sigma, tangent, mask).accepted
    with pytest.raises(ValueError, match="kept complex"):
        quadratic_cost_on_support([280. + 0j, 999.], obs, sigma, tangent, mask)


def test_analysis_increment_is_recorded_without_requiring_forecast_conservation():
    before = np.array([.01, .02])
    after = np.array([.012, .018])
    measure = np.array([1., 2.])
    assert analysis_inventory_increment(before, after, measure) == pytest.approx(-.002)
    with pytest.raises(ValueError, match="nonnegative"):
        analysis_inventory_increment(before, np.array([.012, -.001]), measure)
    assert analysis_inventory_increment(np.array([0., 0., 1e16]),
                                        np.array([1e16, 1., 0.]),
                                        np.array([1., 1., 1.])) == 1.
    assert analysis_inventory_increment(np.array([0., 0., 1e308]),
                                        np.array([1e308, 1., 0.]),
                                        np.array([1., 1., 1.])) == 1.


@pytest.mark.parametrize("weights", [np.array([.8, .1]),
                                      np.array([1.1, -.1]),
                                      np.array([np.nan, 1.])])
def test_invalid_radiance_weights_are_rejected(weights):
    with pytest.raises(ValueError):
        mixed_brightness_temperature(_columns(), weights, WAVELENGTH)


def test_invalid_channel_direction_and_boolean_support_are_rejected():
    l = _columns()
    w = np.array([.5, .5])
    with pytest.raises(ValueError, match="normalized"):
        mixed_brightness_directional(l, w, np.zeros_like(l), np.array([1., 0.]),
                                     WAVELENGTH)
    with pytest.raises(ValueError, match="boolean channel support"):
        quadratic_cost_on_support(np.array([280.]), np.array([280.]),
                                  np.array([1.]), np.array([0.]), np.array([1.]))
    with pytest.raises(ValueError, match="boolean mask"):
        mixed_brightness_temperature(l, [True, .5], WAVELENGTH)
    with pytest.raises(ValueError, match="temperature"):
        planck_radiance(np.bool_(True), WAVELENGTH)
    with pytest.raises(ValueError, match="leaves the simplex"):
        mixed_brightness_directional(l, np.array([1., 0.]), np.zeros_like(l),
                                     np.array([1., -1.]), WAVELENGTH)
