"""Reference-state enthalpy check for a synthetic fixed-pressure phase system.

All masses use one declared kg-species/kg-dry-air basis. Heat capacities are
constant in this pilot; pressure work and transported mass enthalpy are explicit
external ledger terms. This is not the KDM thermodynamic state equation.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from collections.abc import Mapping


COEFFICIENT_ATOL_J_PER_KG = 1e-8
ENERGY_ATOL_J_PER_KG_DRY = 1e-8


@dataclass(frozen=True)
class SpeciesEnthalpy:
    reference_j_per_kg: float
    heat_capacity_j_per_kg_k: float


@dataclass(frozen=True)
class EnthalpyModel:
    reference_temperature_k: float
    dry_heat_capacity_j_per_kg_k: float
    phases: Mapping[str, SpeciesEnthalpy]


@dataclass(frozen=True)
class PhaseThermoState:
    temperature_k: float
    mass_kg_per_kg_dry: Mapping[str, float]


@dataclass(frozen=True)
class LatentEdge:
    source: str
    destination: str
    coefficient_j_per_kg_at_reference: float


@dataclass(frozen=True)
class EnthalpyBudget:
    before_j_per_kg_dry: float
    after_j_per_kg_dry: float
    external_j_per_kg_dry: float
    residual_j_per_kg_dry: float


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite real quantity")
    return float(value)


def _validate_model(model: EnthalpyModel) -> None:
    if not isinstance(model, EnthalpyModel) or not model.phases:
        raise ValueError("declare a nonempty phase enthalpy model")
    if _finite(model.reference_temperature_k, "reference temperature") <= 0:
        raise ValueError("reference temperature must be positive K")
    if _finite(model.dry_heat_capacity_j_per_kg_k, "dry heat capacity") <= 0:
        raise ValueError("dry heat capacity must be positive")
    for name, phase in model.phases.items():
        if not isinstance(name, str) or not name or not isinstance(phase, SpeciesEnthalpy):
            raise ValueError("each phase needs a named enthalpy model")
        _finite(phase.reference_j_per_kg, f"{name} reference enthalpy")
        if _finite(phase.heat_capacity_j_per_kg_k, f"{name} heat capacity") <= 0:
            raise ValueError("phase heat capacities must be positive")


def phase_specific_enthalpy(model: EnthalpyModel, phase: str,
                            temperature_k: float) -> float:
    """h_phase(T) = h_ref + c_phase (T-T_ref), in J/kg species."""
    _validate_model(model)
    temperature = _finite(temperature_k, "temperature")
    if temperature <= 0 or phase not in model.phases:
        raise ValueError("positive temperature and declared phase required")
    params = model.phases[phase]
    value = params.reference_j_per_kg + params.heat_capacity_j_per_kg_k * (
        temperature - model.reference_temperature_k)
    return _finite(value, "specific enthalpy")


def latent_coefficient(model: EnthalpyModel, source: str, destination: str,
                       temperature_k: float) -> float:
    """Heat released per kg moved source→destination at the same T."""
    if source == destination:
        raise ValueError("latent edge needs distinct phases")
    return _finite(
        phase_specific_enthalpy(model, source, temperature_k)
        - phase_specific_enthalpy(model, destination, temperature_k),
        "latent coefficient",
    )


def check_closed_cycle(model: EnthalpyModel,
                       edges: tuple[LatentEdge, ...]) -> float:
    """Check each declared reference latent heat and its closed-cycle sum."""
    _validate_model(model)
    if (not isinstance(edges, tuple) or len(edges) < 2
            or any(not isinstance(edge, LatentEdge) for edge in edges)):
        raise ValueError("declare at least two latent edges forming one cycle")
    for index, edge in enumerate(edges):
        following = edges[(index + 1) % len(edges)]
        if edge.destination != following.source:
            raise ValueError("latent edges do not form a closed ordered cycle")
        supplied = _finite(edge.coefficient_j_per_kg_at_reference,
                           "declared latent coefficient")
        expected = latent_coefficient(
            model, edge.source, edge.destination, model.reference_temperature_k)
        if abs(supplied - expected) > COEFFICIENT_ATOL_J_PER_KG:
            raise ValueError("latent coefficient conflicts with phase state functions")
    total = math.fsum(edge.coefficient_j_per_kg_at_reference for edge in edges)
    if not math.isfinite(total) or abs(total) > COEFFICIENT_ATOL_J_PER_KG:
        raise ValueError("closed latent cycle leaves nonzero work")
    return total


def _enthalpy(model: EnthalpyModel, state: PhaseThermoState) -> float:
    _validate_model(model)
    if not isinstance(state, PhaseThermoState) or set(state.mass_kg_per_kg_dry) != set(model.phases):
        raise ValueError("state must declare every model phase")
    temperature = _finite(state.temperature_k, "state temperature")
    if temperature <= 0:
        raise ValueError("state temperature must be positive K")
    terms = [model.dry_heat_capacity_j_per_kg_k
             * (temperature - model.reference_temperature_k)]
    for name, amount in state.mass_kg_per_kg_dry.items():
        mass = _finite(amount, f"{name} mass")
        if mass < 0:
            raise ValueError("phase mass must be nonnegative")
        terms.append(mass * phase_specific_enthalpy(model, name, temperature))
    return _finite(math.fsum(terms), "total enthalpy")


def check_enthalpy_budget(
    model: EnthalpyModel,
    before: PhaseThermoState,
    after: PhaseThermoState,
    *,
    external_heat_j_per_kg_dry: float,
    declared_work_j_per_kg_dry: float,
    mass_exchange_energy_j_per_kg_dry: float,
) -> EnthalpyBudget:
    """Require H_after-H_before = heat + work + external mass enthalpy.

    The three external terms are separately named even when zero. The fixed
    f64 pilot threshold is energy-valued, not an observational tolerance.
    Water-mass conservation is checked by the separate applied-transfer audit.
    """
    initial, final = _enthalpy(model, before), _enthalpy(model, after)
    external = math.fsum((
        _finite(external_heat_j_per_kg_dry, "external heat"),
        _finite(declared_work_j_per_kg_dry, "declared work"),
        _finite(mass_exchange_energy_j_per_kg_dry, "mass exchange energy"),
    ))
    residual = math.fsum((final, -initial, -external))
    if not math.isfinite(residual) or abs(residual) > ENERGY_ATOL_J_PER_KG_DRY:
        raise ValueError("enthalpy state function does not close external budget")
    return EnthalpyBudget(initial, final, external, residual)
