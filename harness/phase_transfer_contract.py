"""Local applied-transfer audit for an isolated phase-change boundary.

This checks a declared water-mass mixing-ratio basis and a fixed heat-capacity
temperature update. It neither allocates competing requests nor certifies the
full model's enthalpy budget. Callers must isolate other process contributions.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class PhaseTransfer:
    name: str
    source: str
    destination: str
    requested: np.ndarray
    applied: np.ndarray
    heat_j_per_kg: float


@dataclass(frozen=True)
class PhaseBudget:
    mass_residual: Mapping[str, np.ndarray]
    heat_residual_j_per_kg: np.ndarray


def check_phase_budget(
    before: Mapping[str, np.ndarray],
    after: Mapping[str, np.ndarray],
    temperature_before: np.ndarray,
    temperature_after: np.ndarray,
    heat_capacity_j_per_kg_k: np.ndarray,
    transfers: Sequence[PhaseTransfer],
    *,
    mass_atol: float = 1e-14,
    heat_atol_j_per_kg: float = 1e-8,
) -> PhaseBudget:
    """Check shared source capacity, applied mass and local latent-temperature work.

    Positive ``applied`` is a source-to-destination mixing-ratio amount, not a
    rate. Signed heat is positive for warming and negative for cooling. The
    heat test is ``cpm * (T_after-T_before) = sum(L_i * applied_i)``; this is
    only the declared local temperature equation, not a full energy law.
    """
    if not transfers or set(before) != set(after) or not before:
        raise ValueError("declare transfers and matching before/after reservoirs")
    if not np.isfinite(mass_atol) or mass_atol < 0 or not np.isfinite(heat_atol_j_per_kg) or heat_atol_j_per_kg < 0:
        raise ValueError("tolerances must be finite and nonnegative")
    tb, ta, cpm = (np.asarray(x, dtype=np.float64) for x in
                   (temperature_before, temperature_after, heat_capacity_j_per_kg_k))
    shape = tb.shape
    if tb.size == 0 or any(x.shape != shape or not np.isfinite(x).all() for x in (tb, ta, cpm)) or np.any(cpm <= 0):
        raise ValueError("temperature and positive heat capacity must be finite on a nonempty grid")
    initial = {key: np.asarray(value, dtype=np.float64) for key, value in before.items()}
    final = {key: np.asarray(value, dtype=np.float64) for key, value in after.items()}
    for key in initial:
        if any(x.shape != shape or not np.isfinite(x).all() for x in (initial[key], final[key])):
            raise ValueError(f"reservoir {key} must be finite on the declared grid")
        if np.any(initial[key] < -mass_atol) or np.any(final[key] < -mass_atol):
            raise ValueError(f"reservoir {key} is outside the nonnegative accepted state")
    delta = {key: np.zeros(shape) for key in initial}
    draws = {key: np.zeros(shape) for key in initial}
    heat = np.zeros(shape)
    for tr in transfers:
        if not tr.name or tr.source == tr.destination or tr.source not in initial or tr.destination not in initial:
            raise ValueError("each transfer needs a name and distinct declared reservoirs")
        requested, applied = (np.asarray(x, dtype=np.float64) for x in (tr.requested, tr.applied))
        if any(x.shape != shape or not np.isfinite(x).all() or np.any(x < 0) for x in (requested, applied)):
            raise ValueError(f"{tr.name}: requested and applied amounts must be finite and nonnegative")
        if not np.isfinite(tr.heat_j_per_kg) or np.any(applied > requested + mass_atol):
            raise ValueError(f"{tr.name}: invalid latent heat or applied amount exceeds request")
        with np.errstate(over="ignore", invalid="ignore"):
            delta[tr.source] -= applied
            delta[tr.destination] += applied
            draws[tr.source] += applied
            heat += tr.heat_j_per_kg * applied
    if (not np.isfinite(heat).all()
            or any(not np.isfinite(value).all() for value in (*delta.values(), *draws.values()))):
        raise ValueError("applied mass or latent work overflowed")
    for key in initial:
        if np.any(draws[key] > initial[key] + mass_atol):
            raise ValueError(f"{key}: combined applied draw exceeds the shared reservoir")
    with np.errstate(over="ignore", invalid="ignore"):
        mass_residual = {key: final[key] - initial[key] - delta[key] for key in initial}
        heat_residual = cpm * (ta - tb) - heat
    if (not np.isfinite(heat_residual).all()
            or any(not np.isfinite(value).all() for value in mass_residual.values())):
        raise ValueError("computed mass or latent-temperature residual is nonfinite")
    if any(np.any(np.abs(value) > mass_atol) for value in mass_residual.values()):
        raise ValueError("applied transfer does not match reservoir changes")
    if np.any(np.abs(heat_residual) > heat_atol_j_per_kg):
        raise ValueError("latent-temperature update does not use the applied amounts")
    return PhaseBudget(mass_residual, heat_residual)
