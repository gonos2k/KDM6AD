"""Explicit validity contract for volume-basis two-moment DSD inputs.

This diagnostic helper requires callers to declare mass concentration C in
kg m^-3, number concentration N in m^-3, and floors/bounds in the same basis.
It does not select a production host/kernel number-unit conversion.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MomentValidity:
    """Cellwise states for a caller-declared volume-moment pair."""

    inactive: np.ndarray
    active: np.ndarray
    admissible: np.ndarray
    mean_particle_mass_kg: np.ndarray
    reason: np.ndarray


def classify_volume_moments(
    mass_concentration_kg_m3,
    number_concentration_m3,
    *,
    mass_floor_kg_m3: float,
    number_floor_m3: float,
    mean_particle_mass_bounds_kg: tuple[float, float],
    basis: str,
) -> MomentValidity:
    """Classify a declared volume C,N pair without ratio checks below floors.

    Both moments below (or at) their own floors means ``inactive``; their ratio
    is left undefined and is not screened. A pair with only one moment above
    its floor is ``active`` but inadmissible. Pairs with both moments above
    floors are admissible only when C/N falls inside the caller's explicit
    species-specific mean-particle-mass interval.
    """
    if basis != "volume":
        raise ValueError("declare volume basis; convert moments and floors together")
    try:
        c = np.asarray(mass_concentration_kg_m3, dtype=np.float64)
        n = np.asarray(number_concentration_m3, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("C and N must be numeric arrays") from exc
    if c.shape != n.shape:
        raise ValueError("C and N must have the same shape")
    if (
        not np.isfinite(c).all()
        or not np.isfinite(n).all()
        or np.any(c < 0.0)
        or np.any(n < 0.0)
    ):
        raise ValueError("C and N must be finite and nonnegative")
    if (
        not np.isfinite(mass_floor_kg_m3)
        or mass_floor_kg_m3 <= 0.0
        or not np.isfinite(number_floor_m3)
        or number_floor_m3 <= 0.0
    ):
        raise ValueError("declared volume floors must be finite and positive")
    if len(mean_particle_mass_bounds_kg) != 2:
        raise ValueError("declare lower and upper mean particle mass bounds")
    lower, upper = mean_particle_mass_bounds_kg
    if (
        not np.isfinite(lower)
        or not np.isfinite(upper)
        or lower <= 0.0
        or upper < lower
    ):
        raise ValueError("mean particle mass bounds must be finite, positive, ordered")

    c_active = c > mass_floor_kg_m3
    n_active = n > number_floor_m3
    inactive = ~c_active & ~n_active
    both_active = c_active & n_active
    mean_mass = np.full(c.shape, np.nan, dtype=np.float64)
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        mean_mass[both_active] = c[both_active] / n[both_active]
    mass_ok = both_active & np.isfinite(mean_mass)
    admissible = mass_ok & (mean_mass >= lower) & (mean_mass <= upper)
    active = ~inactive
    reason = np.full(c.shape, "inactive_below_floor", dtype="U32")
    reason[active & ~both_active] = "one_moment_below_floor"
    reason[both_active & ~np.isfinite(mean_mass)] = "nonfinite_mean_mass"
    reason[both_active & np.isfinite(mean_mass) & ~admissible] = (
        "mean_mass_out_of_range"
    )
    reason[admissible] = "admissible"

    outputs = []
    for array in (inactive, active, admissible, mean_mass, reason):
        value = np.array(array, copy=True)
        value.setflags(write=False)
        outputs.append(value)
    return MomentValidity(*outputs)


def mask_admissible_output(validity: MomentValidity, output) -> np.ndarray:
    """Copy only admissible-cell outputs; inactive values are never inspected.

    Active but inadmissible pairs are refused explicitly. For inactive cells,
    the producer output may be undefined; this consumer leaves the result at
    zero without converting, checking, or otherwise reading that element.
    """
    if np.any(validity.active & ~validity.admissible):
        bad = np.argwhere(validity.active & ~validity.admissible)
        raise ValueError(f"active C,N pair is inadmissible at {bad[:8].tolist()}")
    raw = np.asarray(output)
    if raw.shape != validity.admissible.shape:
        raise ValueError("producer output shape must match the C,N validity mask")
    result = np.zeros(validity.admissible.shape, dtype=np.float64)
    selected = np.asarray(raw[validity.admissible], dtype=np.float64)
    if not np.isfinite(selected).all():
        raise ValueError("producer output must be finite on admissible cells")
    result[validity.admissible] = selected
    return result
