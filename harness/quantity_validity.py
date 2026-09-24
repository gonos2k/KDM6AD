"""Small, declared validity adapters; not a universal physics solver.

Population moments, producer output validity and observation availability are
separate contracts. Inactive/undefined producer slots and absent observations
are never read or silently promoted to physical zeros.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

import numpy as np

from moment_validity import MomentValidity, classify_volume_moments


@dataclass(frozen=True)
class MomentInput:
    population_id: str
    phase: str
    moment_id: str
    basis: str
    unit: str
    values: object


@dataclass(frozen=True)
class PopulationSpec:
    population_id: str
    phase: str
    mass_floor_kg_m3: float
    number_floor_m3: float
    mean_particle_mass_bounds_kg: tuple[float, float]
    distribution_id: str | None = None


@dataclass(frozen=True)
class PopulationValidity:
    spec: PopulationSpec
    cells: MomentValidity


def classify_population_pair(spec: PopulationSpec, mass: MomentInput,
                             number: MomentInput) -> PopulationValidity:
    """Require same physical particle population before calling G3's C/N check."""
    if (not isinstance(spec.population_id, str) or not spec.population_id
            or not isinstance(spec.phase, str) or not spec.phase
            or mass.population_id != spec.population_id
            or number.population_id != spec.population_id
            or mass.phase != spec.phase or number.phase != spec.phase
            or (mass.moment_id, number.moment_id) != ("mass", "number")
            or (mass.basis, number.basis) != ("volume", "volume")
            or (mass.unit, number.unit) != ("kg/m3", "#/m3")):
        raise ValueError("declare matching population, mass/number IDs, volume basis and units")
    if np.ma.isMaskedArray(mass.values) or np.ma.isMaskedArray(number.values):
        raise ValueError("masked population moments need an explicit missing-data contract")
    mass_array, number_array = np.asarray(mass.values), np.asarray(number.values)
    if mass_array.size == 0 or number_array.size == 0:
        raise ValueError("population moment arrays must be nonempty")
    if mass_array.dtype.kind in "bO" or number_array.dtype.kind in "bO":
        raise ValueError("population moments cannot be boolean or object masks")
    return PopulationValidity(
        spec,
        classify_volume_moments(
            mass.values, number.values,
            mass_floor_kg_m3=spec.mass_floor_kg_m3,
            number_floor_m3=spec.number_floor_m3,
            mean_particle_mass_bounds_kg=spec.mean_particle_mass_bounds_kg,
            basis="volume",
        ),
    )


class ProducerStatus(str, Enum):
    INACTIVE = "inactive"
    UNDEFINED = "undefined"
    INADMISSIBLE = "inadmissible"
    VALID_ZERO = "valid_zero"
    VALID = "valid"
    CONDITIONAL_VALID = "conditional_valid"


@dataclass(frozen=True)
class SampleSpec:
    quantity_id: str
    unit: str
    lower: float
    upper: float
    zero_valid: bool
    conditional_assumption: str | None = None


@dataclass(frozen=True)
class SampleAssessment:
    status: ProducerStatus
    value: float | None
    zero: bool | None
    assumption: str | None


def classify_producer_sample(spec: SampleSpec, value: object, *,
                             process_active: bool, output_defined: bool) -> SampleAssessment:
    """Classify one producer output without touching inactive/undefined slots."""
    if (not isinstance(spec.quantity_id, str) or not spec.quantity_id
            or not isinstance(spec.unit, str) or not spec.unit
            or type(spec.zero_valid) is not bool
            or (spec.conditional_assumption is not None
                and (not isinstance(spec.conditional_assumption, str)
                     or not spec.conditional_assumption))
            or not math.isfinite(spec.lower)
            or not math.isfinite(spec.upper) or spec.lower > spec.upper):
        raise ValueError("declare a finite, ordered quantity domain and unit")
    if type(process_active) is not bool or type(output_defined) is not bool:
        raise ValueError("producer activity and definition flags must be booleans")
    if not process_active:
        return SampleAssessment(ProducerStatus.INACTIVE, None, None, None)
    if not output_defined:
        return SampleAssessment(ProducerStatus.UNDEFINED, None, None, None)
    if np.ma.isMaskedArray(value):
        raise ValueError("masked producer output needs an explicit validity state")
    if isinstance(value, (bool, np.bool_)) or (isinstance(value, np.ndarray)
                                               and value.dtype.kind in "bO"):
        raise ValueError("boolean producer mask cannot be a physical output")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("active defined producer output must be numeric") from exc
    if not math.isfinite(numeric) or not spec.lower <= numeric <= spec.upper:
        return SampleAssessment(ProducerStatus.INADMISSIBLE, numeric, None, None)
    zero = numeric == 0
    if zero and not spec.zero_valid:
        return SampleAssessment(ProducerStatus.INADMISSIBLE, numeric, True, None)
    if spec.conditional_assumption:
        return SampleAssessment(ProducerStatus.CONDITIONAL_VALID, numeric,
                                zero, spec.conditional_assumption)
    return SampleAssessment(ProducerStatus.VALID_ZERO if zero else ProducerStatus.VALID,
                            numeric, zero, None)


class ObservationStatus(str, Enum):
    MISSING = "missing_observation"
    QUALITY_REJECTED = "quality_rejected"
    ACCEPTED = "accepted"


def classify_observation(value: object, *, present: bool,
                         quality_passed: bool) -> ObservationStatus:
    """Keep observation support separate from producer activity and actual zero."""
    if type(present) is not bool or type(quality_passed) is not bool:
        raise ValueError("observation support and quality flags must be booleans")
    if not present and quality_passed:
        raise ValueError("missing observation cannot have passed quality")
    if not present:
        return ObservationStatus.MISSING
    if not quality_passed:
        return ObservationStatus.QUALITY_REJECTED
    if np.ma.isMaskedArray(value):
        raise ValueError("masked observation cannot be silently accepted")
    if isinstance(value, (bool, np.bool_)) or (isinstance(value, np.ndarray)
                                               and value.dtype.kind in "bO"):
        raise ValueError("boolean quality mask cannot be an observation value")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("accepted observation must be numeric") from exc
    if not math.isfinite(numeric):
        raise ValueError("accepted observation must be finite")
    return ObservationStatus.ACCEPTED


def check_nonnegative_m012(spec: PopulationSpec, m0: MomentInput,
                           m1: MomentInput, m2: MomentInput) -> np.ndarray:
    """Necessary M0*M2 >= M1² condition for a declared nonnegative D spectrum.

    A passing inequality is not sufficient to certify the full distribution.
    This deliberately does not apply a guessed DSD or support bound.
    """
    if (not isinstance(spec.population_id, str) or not spec.population_id
            or not isinstance(spec.phase, str) or not spec.phase
            or not isinstance(spec.distribution_id, str) or not spec.distribution_id
            or len({m.population_id for m in (m0, m1, m2)}) != 1
            or m0.population_id != spec.population_id
            or len({m.phase for m in (m0, m1, m2)}) != 1
            or m0.phase != spec.phase
            or tuple(m.moment_id for m in (m0, m1, m2)) != ("M0", "M1", "M2")
            or len({m.basis for m in (m0, m1, m2)}) != 1
            or m0.basis != "volume"
            or tuple(m.unit for m in (m0, m1, m2)) != ("#/m3", "#/m2", "#/m")):
        raise ValueError("declare one population, M0/M1/M2, volume basis and diameter-moment units")
    if any(np.ma.isMaskedArray(m.values) for m in (m0, m1, m2)):
        raise ValueError("masked higher moments need an explicit missing-data contract")
    raw_arrays = tuple(np.asarray(m.values) for m in (m0, m1, m2))
    if any(a.dtype.kind in "bO" for a in raw_arrays):
        raise ValueError("moment values cannot be boolean or object masks")
    arrays = tuple(np.asarray(a, dtype=np.float64) for a in raw_arrays)
    if (not arrays[0].size or len({a.shape for a in arrays}) != 1
            or any(not np.isfinite(a).all() or np.any(a < 0) for a in arrays)):
        raise ValueError("finite nonnegative same-shape moment arrays required")
    # A rounded float product can hide a strict violation even when frexp
    # scaling avoids overflow/underflow. Each stored binary64 value is an
    # exact power-of-two rational; compare integer cross-products instead of
    # rounding M0*M2 and M1². This is diagnostic-only, not a hot solver path.
    def exact_necessary(a: np.float64, b: np.float64, c: np.float64) -> bool:
        na, da = float(a).as_integer_ratio()
        nb, db = float(b).as_integer_ratio()
        nc, dc = float(c).as_integer_ratio()
        return na * nc * db * db >= nb * nb * da * dc

    result = np.array(
        [exact_necessary(a, b, c) for a, b, c in
         zip(*(array.flat for array in arrays))], dtype=bool,
    ).reshape(arrays[0].shape)
    result.setflags(write=False)
    return result
