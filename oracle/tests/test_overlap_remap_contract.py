"""Synthetic conservative remap with explicit overlap normalization."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from overlap_remap_contract import OverlapRemap, check_overlap_remap, remap_and_integrate  # noqa: E402


def _spec(normalization="covered_area"):
    return OverlapRemap(
        source_measure=np.array([1., 1.]),
        destination_measure=np.array([2.]),
        source_fraction=np.array([.5, 1.]),
        destination_fraction=np.array([.75]),
        matrix=(np.array([[1 / 3, 2 / 3]]) if normalization == "covered_area"
                else np.array([[.25, .5]])),
        normalization=normalization,
    )


@pytest.mark.parametrize("normalization,expected", [
    ("covered_area", 16.666666666666668),
    ("destination_area", 12.5),
])
def test_partial_overlap_preserves_integral_with_declared_normalization(normalization, expected):
    spec = _spec(normalization)
    audit = check_overlap_remap(spec)
    assert np.max(np.abs(audit.column_residual)) < 1e-15
    assert abs(audit.overlap_measure_residual) == 0
    values, source_total, destination_total = remap_and_integrate(spec, np.array([10., 20.]))
    assert values[0] == pytest.approx(expected)
    assert source_total == pytest.approx(25.)
    assert destination_total == pytest.approx(source_total)


def test_same_matrix_under_other_normalization_fails():
    spec = _spec("covered_area")
    wrong = OverlapRemap(spec.source_measure, spec.destination_measure,
                         spec.source_fraction, spec.destination_fraction,
                         spec.matrix, "destination_area")
    with pytest.raises(ValueError, match="does not conserve"):
        check_overlap_remap(wrong)


def test_boolean_tolerance_and_tiny_overlap_misallocation_are_rejected():
    bad_large = OverlapRemap(np.array([1.]), np.array([1.]),
                             np.array([1.]), np.array([1.]),
                             np.array([[.5]]), "destination_area")
    with pytest.raises(ValueError, match="tolerances"):
        check_overlap_remap(bad_large, atol=True)
    tiny = OverlapRemap(np.array([1., 1.]), np.array([2.]),
                        np.array([1e-20, 1e-20]), np.array([1e-20]),
                        np.array([[1., 0.]]), "covered_area")
    # Correct constant and total overlap, but all of the second source cell's
    # tiny coverage is incorrectly attributed to the first source cell.
    with pytest.raises(ValueError, match="does not conserve"):
        check_overlap_remap(tiny)
    # Red counterexample: default absolute 1e-12 used to accept 100% loss of
    # a 5e-16 overlap integral while both destination rows summed to one.
    tiny_two_dest = OverlapRemap(
        np.array([.5, .5]), np.array([.5, .5]),
        np.array([1e-15, 1e-15]), np.array([1e-15, 1e-15]),
        np.array([[1., 0.], [1., 0.]]), "covered_area",
    )
    with pytest.raises(ValueError, match="does not conserve"):
        remap_and_integrate(tiny_two_dest, np.array([0., 1.]))
    huge = OverlapRemap(np.array([1e308]), np.array([1e308]),
                        np.array([1.]), np.array([1.]),
                        np.array([[1.]]), "covered_area")
    with pytest.raises(ValueError, match="overflowed"):
        check_overlap_remap(huge, rtol=1e308)
    smallest = np.nextafter(0., 1.)
    unrepresentable = OverlapRemap(
        np.array([.5, .5]), np.array([.5, .5]),
        np.array([smallest, smallest]), np.array([smallest, smallest]),
        np.array([[1., 0.], [1., 0.]]), "covered_area",
    )
    with pytest.raises(ValueError, match="underflowed"):
        check_overlap_remap(unrepresentable)


def test_missing_or_extra_weight_is_detected_for_arbitrary_source_values():
    spec = _spec()
    altered = spec.matrix.copy()
    altered[0, 0] += .01
    with pytest.raises(ValueError, match="does not conserve"):
        check_overlap_remap(OverlapRemap(spec.source_measure, spec.destination_measure,
                                         spec.source_fraction, spec.destination_fraction,
                                         altered, spec.normalization))


def test_zero_overlap_source_and_destination_cannot_hide_transport():
    spec = OverlapRemap(
        np.array([1., 1.]), np.array([1.]),
        np.array([1., 0.]), np.array([1.]),
        np.array([[1., 0.]]), "covered_area",
    )
    check_overlap_remap(spec)
    p_bad = np.array([[1., 1e-3]])
    with pytest.raises(ValueError, match="masked source"):
        check_overlap_remap(OverlapRemap(spec.source_measure, spec.destination_measure,
                                         spec.source_fraction, spec.destination_fraction,
                                         p_bad, spec.normalization))

    empty_destination = OverlapRemap(np.array([1.]), np.array([1.]),
                                      np.array([0.]), np.array([0.]),
                                      np.array([[0.]]), "covered_area")
    check_overlap_remap(empty_destination)
    with pytest.raises(ValueError, match="masked source"):
        check_overlap_remap(OverlapRemap(np.array([1.]), np.array([1.]),
                                         np.array([0.]), np.array([0.]),
                                         np.array([[1.]]), "covered_area"))


@pytest.mark.parametrize("change,error", [
    (lambda s: OverlapRemap(s.source_measure, s.destination_measure,
                            np.array([.5, 1.1]), s.destination_fraction,
                            s.matrix, s.normalization), "fractions"),
    (lambda s: OverlapRemap(s.source_measure, s.destination_measure,
                            s.source_fraction, s.destination_fraction,
                            np.array([[-1., 2.]]), s.normalization), "nonnegative"),
    (lambda s: OverlapRemap(s.source_measure, s.destination_measure,
                            s.source_fraction, s.destination_fraction,
                            np.array([[np.nan, 1.]]), s.normalization), "finite"),
    (lambda s: OverlapRemap(s.source_measure, s.destination_measure,
                            s.source_fraction, s.destination_fraction,
                            s.matrix, "unspecified"), "normalization"),
])
def test_bad_geometry_matrix_or_normalization_is_rejected(change, error):
    with pytest.raises(ValueError, match=error):
        check_overlap_remap(change(_spec()))


def test_unmasked_binary64_values_are_required_at_consumer_boundary():
    spec = _spec()
    with pytest.raises(ValueError, match="unmasked float64"):
        remap_and_integrate(spec, np.ma.array([10., 20.], mask=[False, True]))
    with pytest.raises(ValueError, match="unmasked float64"):
        remap_and_integrate(spec, np.array([True, False]))
