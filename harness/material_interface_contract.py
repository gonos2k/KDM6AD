"""Synthetic two-material heat-face conservation, law and entropy gates.

The cells are closed finite reservoirs per unit interface area. The series
resistance relation is one declared linear constitutive law, not a universal
soil/snow/road model. No operational KDM or land-surface solver is changed.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real


ENERGY_ATOL_J_M2 = 1e-8
FACE_ATOL_J_M2 = 0.0
FACE_RTOL = 1e-12
ENTROPY_ATOL_J_M2_K = 1e-10


@dataclass(frozen=True)
class ThermalCells:
    left_temperature_k: float
    right_temperature_k: float
    left_heat_capacity_j_m2_k: float
    right_heat_capacity_j_m2_k: float


@dataclass(frozen=True)
class IntegratedHeatFace:
    amount_left_to_right_j_m2: float
    duration_s: float


@dataclass(frozen=True)
class SeriesMaterial:
    left_conductivity_w_m_k: float
    right_conductivity_w_m_k: float
    left_center_to_face_m: float
    right_center_to_face_m: float


@dataclass(frozen=True)
class HeatFaceBudget:
    left_residual_j_m2: float
    right_residual_j_m2: float
    total_residual_j_m2: float


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite real")
    return float(value)


def _state(cells: ThermalCells) -> None:
    if not isinstance(cells, ThermalCells):
        raise ValueError("declare two thermal cells")
    if any(_finite(value, name) <= 0 for name, value in vars(cells).items()):
        raise ValueError("absolute temperatures and areal heat capacities must be positive")


def _event(event: IntegratedHeatFace) -> tuple[float, float]:
    if not isinstance(event, IntegratedHeatFace):
        raise ValueError("declare a signed integrated face amount")
    amount = _finite(event.amount_left_to_right_j_m2, "face amount")
    duration = _finite(event.duration_s, "face interval")
    if duration <= 0:
        raise ValueError("face interval must be positive")
    return amount, duration


def advance_declared_heat(before: ThermalCells,
                          event: IntegratedHeatFace) -> ThermalCells:
    """Apply a supplied signed Q once to both finite reservoirs."""
    _state(before)
    amount, _ = _event(event)
    after = ThermalCells(
        before.left_temperature_k - amount / before.left_heat_capacity_j_m2_k,
        before.right_temperature_k + amount / before.right_heat_capacity_j_m2_k,
        before.left_heat_capacity_j_m2_k,
        before.right_heat_capacity_j_m2_k,
    )
    _state(after)
    return after


def check_heat_face_budget(before: ThermalCells, after: ThermalCells,
                           event: IntegratedHeatFace) -> HeatFaceBudget:
    """Check only paired face accounting, not its law or passive direction."""
    _state(before)
    _state(after)
    amount, _ = _event(event)
    if (before.left_heat_capacity_j_m2_k != after.left_heat_capacity_j_m2_k
            or before.right_heat_capacity_j_m2_k != after.right_heat_capacity_j_m2_k):
        raise ValueError("changing heat capacity needs a separate energy contract")
    left = _finite(
        before.left_heat_capacity_j_m2_k
        * (after.left_temperature_k - before.left_temperature_k) + amount,
        "left energy residual")
    right = _finite(
        before.right_heat_capacity_j_m2_k
        * (after.right_temperature_k - before.right_temperature_k) - amount,
        "right energy residual")
    total = math.fsum((left, right))
    if max(abs(left), abs(right), abs(total)) > ENERGY_ATOL_J_M2:
        raise ValueError("paired face amount does not match cell energy changes")
    return HeatFaceBudget(left, right, total)


def series_resistance_flux(before: ThermalCells,
                           material: SeriesMaterial) -> float:
    """W/m² = (T_left-T_right)/(ell_left/K_left + ell_right/K_right)."""
    _state(before)
    if not isinstance(material, SeriesMaterial):
        raise ValueError("declare both material half-cells")
    values = tuple(_finite(value, name) for name, value in vars(material).items())
    if any(value <= 0 for value in values):
        raise ValueError("conductivities and center-to-face distances must be positive")
    kl, kr, dl, dr = values
    resistance = _finite(dl / kl + dr / kr, "series resistance")
    if resistance <= 0:
        raise ValueError("series resistance must be positive")
    return _finite((before.left_temperature_k - before.right_temperature_k)
                   / resistance, "series heat flux")


def check_series_face_law(before: ThermalCells, material: SeriesMaterial,
                          event: IntegratedHeatFace) -> float:
    """Check integrated Q against the independently declared face law."""
    flux = series_resistance_flux(before, material)
    amount, duration = _event(event)
    expected = _finite(flux * duration, "integrated series-law amount")
    if ((expected == 0 and amount != 0)
            or (expected > 0 and amount < 0)
            or (expected < 0 and amount > 0)):
        raise ValueError("face amount reverses or leaves series-law equilibrium")
    if not math.isclose(amount, expected, rel_tol=FACE_RTOL,
                        abs_tol=FACE_ATOL_J_M2):
        raise ValueError("face amount violates series-resistance law")
    return expected


def check_passive_entropy(before: ThermalCells, after: ThermalCells,
                          event: IntegratedHeatFace) -> float:
    """For the closed constant-C pair, require ΔS = Σ C ln(T_after/T_before) ≥ 0."""
    check_heat_face_budget(before, after, event)
    entropy = _finite(math.fsum((
        before.left_heat_capacity_j_m2_k
        * math.log(after.left_temperature_k / before.left_temperature_k),
        before.right_heat_capacity_j_m2_k
        * math.log(after.right_temperature_k / before.right_temperature_k),
    )), "entropy change")
    if entropy < -ENTROPY_ATOL_J_M2_K:
        raise ValueError("passive heat exchange decreases closed-pair entropy")
    return entropy
