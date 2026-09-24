"""Population, producer and observation states must remain distinct."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from quantity_validity import (  # noqa: E402
    MomentInput, PopulationSpec, ProducerStatus, SampleSpec,
    ObservationStatus, classify_population_pair, classify_producer_sample,
    classify_observation, check_nonnegative_m012,
)


def _pair(mass_population="cloud_drops", number_population="cloud_drops"):
    spec = PopulationSpec("cloud_drops", "liquid", 1e-12, 1e-8, (1e-12, 1e-6),
                          distribution_id="gamma_cloud")
    mass = MomentInput(mass_population, "liquid", "mass", "volume", "kg/m3", [1e-4, 0.0])
    number = MomentInput(number_population, "liquid", "number", "volume", "#/m3", [1e5, 0.0])
    return spec, mass, number


def test_declared_same_population_pair_is_admissible_but_inactive_pair_is_not_zero_radius():
    result = classify_population_pair(*_pair())
    assert result.spec.population_id == "cloud_drops"
    assert result.cells.admissible.tolist() == [True, False]
    assert result.cells.inactive.tolist() == [False, True]
    assert np.isnan(result.cells.mean_particle_mass_kg[1])


def test_cloud_mass_cannot_be_paired_with_dry_aerosol_number():
    with pytest.raises(ValueError, match="matching population"):
        classify_population_pair(*_pair(number_population="dry_aerosol"))


def test_moment_ids_basis_and_units_are_not_inferred_from_array_shape():
    spec, mass, number = _pair()
    for bad in (MomentInput("cloud_drops", "liquid", "M2", "volume", "kg/m3", number.values),
                MomentInput("cloud_drops", "liquid", "number", "dry_mass", "#/m3", number.values),
                MomentInput("cloud_drops", "liquid", "number", "volume", "#/kg", number.values),
                MomentInput("cloud_drops", "ice", "number", "volume", "#/m3", number.values)):
        with pytest.raises(ValueError, match="matching population"):
            classify_population_pair(spec, mass, bad)
    with pytest.raises(ValueError, match="nonempty"):
        classify_population_pair(spec,
                                 MomentInput("cloud_drops", "liquid", "mass", "volume", "kg/m3", []),
                                 MomentInput("cloud_drops", "liquid", "number", "volume", "#/m3", []))
    with pytest.raises(ValueError, match="real numeric"):
        classify_population_pair(spec,
                                 MomentInput("cloud_drops", "liquid", "mass", "volume", "kg/m3", [True]),
                                 MomentInput("cloud_drops", "liquid", "number", "volume", "#/m3", [True]))
    with pytest.raises(ValueError, match="masked population"):
        classify_population_pair(spec,
                                 MomentInput("cloud_drops", "liquid", "mass", "volume", "kg/m3",
                                             np.ma.array([1e-4], mask=[True])),
                                 MomentInput("cloud_drops", "liquid", "number", "volume", "#/m3", [1e5]))
    with pytest.raises(ValueError, match="boolean.*masks"):
        classify_population_pair(spec,
                                 MomentInput("cloud_drops", "liquid", "mass", "volume", "kg/m3",
                                             [True, 1e-4]),
                                 MomentInput("cloud_drops", "liquid", "number", "volume", "#/m3",
                                             [1e6, 1e6]))
    with pytest.raises(ValueError, match="real numeric"):
        classify_population_pair(spec,
                                 MomentInput("cloud_drops", "liquid", "mass", "volume", "kg/m3",
                                             np.array([True], dtype=object)),
                                 MomentInput("cloud_drops", "liquid", "number", "volume", "#/m3", [1e5]))
    with pytest.raises(ValueError, match="real numeric"):
        classify_population_pair(spec,
                                 MomentInput("cloud_drops", "liquid", "mass", "volume", "kg/m3",
                                             np.array([1e-4 + 100j])),
                                 MomentInput("cloud_drops", "liquid", "number", "volume", "#/m3", [1e5]))


class Unreadable:
    def __float__(self):
        raise AssertionError("an inactive, undefined or absent value was inspected")


def test_actual_zero_inactive_and_undefined_are_different_producer_states():
    spec = SampleSpec("condensation_flux", "kg/m2/s", 0., 1., True)
    zero = classify_producer_sample(spec, 0., process_active=True, output_defined=True)
    assert zero.status is ProducerStatus.VALID_ZERO and zero.zero is True
    inactive = classify_producer_sample(spec, Unreadable(),
                                        process_active=False, output_defined=False)
    assert inactive.status is ProducerStatus.INACTIVE and inactive.value is None
    undefined = classify_producer_sample(spec, Unreadable(),
                                         process_active=True, output_defined=False)
    assert undefined.status is ProducerStatus.UNDEFINED and undefined.value is None
    with pytest.raises(ValueError, match="booleans"):
        classify_producer_sample(spec, 0., process_active="False", output_defined=True)
    with pytest.raises(ValueError, match="real numeric"):
        classify_producer_sample(spec, True, process_active=True, output_defined=True)
    with pytest.raises(ValueError, match="real numeric"):
        classify_producer_sample(spec, np.array(True), process_active=True, output_defined=True)
    with pytest.raises(ValueError, match="real numeric"):
        classify_producer_sample(spec, np.array(True, dtype=object),
                                 process_active=True, output_defined=True)
    with pytest.raises(ValueError, match="real numeric"):
        classify_producer_sample(spec, 1.0 + 0j,
                                 process_active=True, output_defined=True)
    with pytest.raises(ValueError, match="masked producer"):
        classify_producer_sample(spec, np.ma.array(0., mask=True),
                                 process_active=True, output_defined=True)


def test_conditional_validity_and_inadmissibility_do_not_become_approval():
    spec = SampleSpec("cloud_number", "#/m3", 0., 1e10, True,
                      conditional_assumption="host number basis is volume")
    conditional = classify_producer_sample(spec, 4e7,
                                           process_active=True, output_defined=True)
    assert conditional.status is ProducerStatus.CONDITIONAL_VALID
    assert conditional.assumption == spec.conditional_assumption
    assert classify_producer_sample(spec, -1., process_active=True,
                                    output_defined=True).status is ProducerStatus.INADMISSIBLE
    assert classify_producer_sample(spec, float("nan"), process_active=True,
                                    output_defined=True).status is ProducerStatus.INADMISSIBLE


def test_observation_support_is_independent_of_process_and_real_zero():
    assert classify_observation(Unreadable(), present=False,
                                quality_passed=False) is ObservationStatus.MISSING
    assert classify_observation(Unreadable(), present=True,
                                quality_passed=False) is ObservationStatus.QUALITY_REJECTED
    assert classify_observation(0.0, present=True,
                                quality_passed=True) is ObservationStatus.ACCEPTED
    with pytest.raises(ValueError, match="finite"):
        classify_observation(float("nan"), present=True, quality_passed=True)
    with pytest.raises(ValueError, match="missing observation"):
        classify_observation(None, present=False, quality_passed=True)
    with pytest.raises(ValueError, match="booleans"):
        classify_observation(0., present=True, quality_passed="False")
    with pytest.raises(ValueError, match="real numeric"):
        classify_observation(np.bool_(True), present=True, quality_passed=True)
    with pytest.raises(ValueError, match="real numeric"):
        classify_observation(np.array(True), present=True, quality_passed=True)
    with pytest.raises(ValueError, match="real numeric"):
        classify_observation(np.array(True, dtype=object),
                             present=True, quality_passed=True)
    with pytest.raises(ValueError, match="real numeric"):
        classify_observation(1.0 + 0j, present=True, quality_passed=True)
    with pytest.raises(ValueError, match="masked observation"):
        classify_observation(np.ma.array(0., mask=True),
                             present=True, quality_passed=True)
    assert classify_observation(np.ma.array(0., mask=True),
                                present=False, quality_passed=False) is ObservationStatus.MISSING


def _m012(a, b, c):
    return (MomentInput("cloud_drops", "liquid", "M0", "volume", "#/m3", [a]),
            MomentInput("cloud_drops", "liquid", "M1", "volume", "#/m2", [b]),
            MomentInput("cloud_drops", "liquid", "M2", "volume", "#/m", [c]))


def _distribution():
    return PopulationSpec("cloud_drops", "liquid", 1e-12, 1e-8,
                          (1e-12, 1e-6), distribution_id="nonnegative_diameter")


def test_positive_moments_can_fail_distribution_necessary_condition():
    assert not check_nonnegative_m012(_distribution(), *_m012(1., 2., 1.))[0]
    assert check_nonnegative_m012(_distribution(), *_m012(1., 1., 1.))[0]


def test_higher_moments_require_matching_population_and_declared_distribution():
    m0, m1, m2 = _m012(1., 1., 1.)
    with pytest.raises(ValueError, match="declare one population"):
        check_nonnegative_m012(PopulationSpec("cloud_drops", "liquid", 1e-12, 1e-8,
                                             (1e-12, 1e-6)), m0, m1, m2)
    with pytest.raises(ValueError, match="declare one population"):
        check_nonnegative_m012(PopulationSpec("", "liquid", 1e-12, 1e-8,
                                             (1e-12, 1e-6), "nonnegative_diameter"),
                               MomentInput("", "liquid", "M0", "volume", "#/m3", [1.]),
                               MomentInput("", "liquid", "M1", "volume", "#/m2", [1.]),
                               MomentInput("", "liquid", "M2", "volume", "#/m", [1.]))
    with pytest.raises(ValueError, match="declare one population"):
        check_nonnegative_m012(_distribution(), m0, m1,
                               MomentInput("dry_aerosol", "liquid", "M2", "volume", "#/m", [1.]))
    with pytest.raises(ValueError, match="real numeric"):
        check_nonnegative_m012(
            _distribution(),
            MomentInput("cloud_drops", "liquid", "M0", "volume", "#/m3", [True]),
            m1, m2,
        )
    with pytest.raises(ValueError, match="masked higher moments"):
        check_nonnegative_m012(
            _distribution(),
            MomentInput("cloud_drops", "liquid", "M0", "volume", "#/m3",
                        np.ma.array([1.], mask=[True])),
            m1, m2,
        )
    with pytest.raises(ValueError, match="boolean.*masks"):
        check_nonnegative_m012(
            _distribution(),
            MomentInput("cloud_drops", "liquid", "M0", "volume", "#/m3", [True, 1.]),
            MomentInput("cloud_drops", "liquid", "M1", "volume", "#/m2", [1., 1.]),
            MomentInput("cloud_drops", "liquid", "M2", "volume", "#/m", [1., 1.]),
        )
    with pytest.raises(ValueError, match="real numeric"):
        check_nonnegative_m012(
            _distribution(),
            MomentInput("cloud_drops", "liquid", "M0", "volume", "#/m3",
                        np.array([True], dtype=object)),
            m1, m2,
        )
    with pytest.raises(ValueError, match="real numeric"):
        check_nonnegative_m012(
            _distribution(),
            MomentInput("cloud_drops", "liquid", "M0", "volume", "#/m3",
                        np.array([1. + 100j])),
            m1, m2,
        )
    assert check_nonnegative_m012(_distribution(), *_m012(1e308, 1e308, 1e308))[0]
    assert not check_nonnegative_m012(_distribution(), *_m012(1e308, 1e308, 1e307))[0]
    assert not check_nonnegative_m012(_distribution(), *_m012(1e-200, 2e-200, 1e-200))[0]
    assert check_nonnegative_m012(_distribution(), *_m012(0., 0., 1.))[0]
    assert not check_nonnegative_m012(_distribution(), *_m012(0., 1., 1.))[0]
    # The two float products round equal, but the exact binary64 rational
    # values violate M0*M2 >= M1² (Red counterexample).
    assert not check_nonnegative_m012(
        _distribution(),
        *_m012(59908975.61088765, 1.5266470819457723, 3.890320755860123e-08),
    )[0]
