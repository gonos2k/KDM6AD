"""Constant/intensive and measure-aware dual-force contracts differ."""

from dataclasses import replace
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from dual_work_mapping_contract import (  # noqa: E402
    check_dual_work, map_intensive_and_dual_density,
)
from overlap_remap_contract import OverlapRemap  # noqa: E402


def _spec():
    return OverlapRemap(
        source_measure=np.array([2.5, 1.5]),
        destination_measure=np.array([1., 3.]),
        source_fraction=np.ones(2),
        destination_fraction=np.ones(2),
        matrix=np.array([[1., 0.], [.5, .5]]),
        normalization="covered_area",
    )


def test_measure_aware_dual_preserves_28_watts_and_11_newtons():
    spec = _spec()
    vs = np.array([2., 4.])
    gt = np.array([5., 2.])  # target extensive force = [5,6] N
    vt, gs = map_intensive_and_dual_density(spec, vs, gt)
    np.testing.assert_array_equal(vt, np.array([2., 3.]))
    np.testing.assert_array_equal(gs, np.array([3.2, 2.]))
    result = check_dual_work(spec, vs, vt, gt, gs)
    assert result.source_power_w == 28.
    assert result.target_power_w == 28.
    assert result.source_total_force_n == result.target_total_force_n == 11.
    assert result.power_residual_w == 0.


def test_same_total_force_can_have_wrong_power_and_fail_dual_map():
    spec = _spec()
    vs = np.array([2., 4.])
    gt = np.array([5., 2.])
    vt, _ = map_intensive_and_dual_density(spec, vs, gt)
    wrong_gs = np.array([4., 2. / 3.])  # source force = [10,1] N
    source_force = spec.source_measure * wrong_gs
    target_force = spec.destination_measure * gt
    assert sum(source_force) == pytest.approx(sum(target_force)) == 11.
    assert float(vs @ source_force) == pytest.approx(24.)
    assert float(vt @ target_force) == pytest.approx(28.)
    with pytest.raises(ValueError, match="dual P transpose"):
        check_dual_work(spec, vs, vt, gt, wrong_gs)


def test_constant_intensive_and_density_fields_are_preserved():
    spec = _spec()
    vs = np.array([3., 3.])
    gt = np.ones(2)
    vt, gs = map_intensive_and_dual_density(spec, vs, gt)
    np.testing.assert_array_equal(vt, vs)
    np.testing.assert_array_equal(gs, gt)
    result = check_dual_work(spec, vs, vt, gt, gs)
    assert result.source_total_force_n == result.target_total_force_n == 4.
    assert result.source_power_w == result.target_power_w == 12.


def test_signed_vectors_keep_power_pairing():
    spec = _spec()
    vs = np.array([-2., 4.])
    gt = np.array([5., -2.])
    vt, gs = map_intensive_and_dual_density(spec, vs, gt)
    result = check_dual_work(spec, vs, vt, gt, gs)
    assert result.source_power_w == result.target_power_w == -16.


def test_inconsistent_measures_or_partial_overlap_are_not_certified():
    spec = _spec()
    vs = np.array([2., 4.])
    gt = np.array([5., 2.])
    with pytest.raises(ValueError, match="conserve overlap"):
        map_intensive_and_dual_density(
            replace(spec, source_measure=np.array([2., 1.])), vs, gt)
    with pytest.raises(ValueError, match="complete source/destination"):
        map_intensive_and_dual_density(
            replace(spec, source_measure=np.array([1.75, 1.5]),
                    source_fraction=np.array([1., .5]),
                    destination_fraction=np.array([1., .5])), vs, gt)


def test_masked_wrong_precision_and_zero_direction_are_rejected():
    spec = _spec()
    vs = np.array([0., 0.])
    gt = np.array([5., 2.])
    vt, gs = map_intensive_and_dual_density(spec, vs, gt)
    with pytest.raises(ValueError, match="intensive target"):
        check_dual_work(spec, vs, np.array([1e-30, 0.]), gt, gs)
    with pytest.raises(ValueError, match="float64"):
        map_intensive_and_dual_density(spec, vs.astype(np.float32), gt)
    with pytest.raises(ValueError, match="unmasked"):
        map_intensive_and_dual_density(spec, vs, np.ma.array(gt, mask=[False, True]))
