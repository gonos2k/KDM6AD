from fractions import Fraction

import numpy as np
import pytest

from harness.analyze_saved_post_micro import (
    AttributionError,
    rounded_post_micro_products,
)


def _stages(delta):
    value = np.zeros((3, 6, *delta.shape[1:]), dtype=np.float64)
    value[2] = delta
    return value


def _repeat_measure(values):
    return np.broadcast_to(values[None, ...], (5, *values.shape)).copy()


def test_bottomfirst_measure_and_vapor_liquid_ice_exchange_are_explicit():
    delta = np.zeros((6, 1, 2), dtype=np.float64)
    delta[0, 0] = [-1.0, -0.25]  # QV
    delta[1, 0, 0] = 0.5  # QC
    delta[2, 0, 1] = 0.25  # QR
    delta[3, 0, 0] = 0.5  # QI
    rho = _repeat_measure(np.array([[2.0, 3.0]], dtype=np.float64))
    dz = _repeat_measure(np.array([[4.0, 5.0]], dtype=np.float64))

    out = rounded_post_micro_products(_stages(delta), rho, dz)

    # Trace measures are top-first [8,15]; state levels are bottom-first [15,8].
    np.testing.assert_array_equal(out["weights_bottomfirst"], [[15.0, 8.0]])
    np.testing.assert_array_equal(
        out["species_delta_kg_m2"][:, 0], [-17.0, 7.5, 2.0, 7.5, 0.0, 0.0]
    )
    assert out["net_total_kg_m2"][0] == 0.0
    assert out["group_delta_kg_m2"]["vapor"][0] == -17.0
    assert out["group_delta_kg_m2"]["liquid"][0] == 9.5
    assert out["group_delta_kg_m2"]["ice"][0] == 7.5
    assert out["gross_abs_species_delta_kg_m2"][0] == 34.0
    assert out["gross_abs_layer_products_kg_m2"][0] == 34.0
    assert out["net_over_gross_species"][0] == 0.0


def test_joint_net_is_flat_fsum_of_rounded_products_and_bounds_regrouping():
    delta = np.zeros((6, 1, 2), dtype=np.float64)
    delta[0, 0] = [1.0e16, 1.0]
    delta[1, 0] = [-1.0e16, 1.0]
    rho = _repeat_measure(np.ones((1, 2), dtype=np.float64))
    dz = _repeat_measure(np.ones((1, 2), dtype=np.float64))

    out = rounded_post_micro_products(_stages(delta), rho, dz)

    products = out["rounded_products_bottomfirst"][:, 0, :]
    exact_rounded_sum = float(
        sum((Fraction.from_float(float(x)) for x in products.reshape(-1)), Fraction())
    )
    assert out["net_total_kg_m2"][0] == exact_rounded_sum == 2.0
    # Summing independently rounded per-species subtotals loses the two small terms.
    assert out["species_regrouping_remainder_kg_m2"][0] == 2.0
    assert (
        abs(out["species_regrouping_remainder_kg_m2"][0])
        <= out["regrouping_arithmetic_bound_kg_m2"][0]
    )


def test_fixed_measure_and_profile_shapes_are_guarded():
    stages = _stages(np.zeros((6, 1, 2), dtype=np.float64))
    rho = _repeat_measure(np.ones((1, 2), dtype=np.float64))
    dz = _repeat_measure(np.ones((1, 2), dtype=np.float64))
    changed = dz.copy()
    changed[1, 0, 0] = 2.0
    with pytest.raises(AttributionError, match="dz changes"):
        rounded_post_micro_products(stages, rho, changed)

    nonpositive = dz.copy()
    nonpositive[:, 0, 0] = 0.0
    with pytest.raises(AttributionError, match="strictly positive"):
        rounded_post_micro_products(stages, rho, nonpositive)

    wrong_stage_shape = stages.transpose(0, 2, 1, 3)
    with pytest.raises(AttributionError, match="water_stages_bottomfirst"):
        rounded_post_micro_products(wrong_stage_shape, rho, dz)


def test_nonfinite_stage_values_are_rejected():
    stages = _stages(np.zeros((6, 1, 2), dtype=np.float64))
    stages[2, 0, 0, 0] = np.nan
    rho = _repeat_measure(np.ones((1, 2), dtype=np.float64))
    dz = _repeat_measure(np.ones((1, 2), dtype=np.float64))
    with pytest.raises(AttributionError, match="nonfinite"):
        rounded_post_micro_products(stages, rho, dz)
