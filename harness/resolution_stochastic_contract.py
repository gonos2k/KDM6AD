"""Synthetic nonlinear-moment, realization-wise exchange and correction gates.

Coarsening and stochastic representation are distinct from changing units.
This module neither defines a production subgrid closure nor runs KDM/DA.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real

import numpy as np

from observation_support_contract import analysis_inventory_increment


RTOL = 1e-12


@dataclass(frozen=True)
class MomentClaim:
    mean_radius_um: float
    third_moment_um3: float | None
    third_moment_basis: str  # "none", "retained", "declared_closure"
    closure_id: str | None = None


@dataclass(frozen=True)
class MomentAudit:
    fine_mean_radius_um: float
    fine_third_moment_um3: float
    cube_of_mean_um3: float
    lost_third_moment_um3: float
    third_moment_carried: bool


@dataclass(frozen=True)
class RealizationAudit:
    realizations: int
    mean_outgoing: float
    mean_incoming: float


@dataclass(frozen=True)
class ExternalCorrection:
    kind: str  # "analysis" or "ml"
    inventory_unit: str
    declared_increment: float


def _vector(value: object, label: str) -> np.ndarray:
    if (np.ma.isMaskedArray(value) or not isinstance(value, np.ndarray)
            or value.dtype != np.float64 or value.ndim != 1
            or not value.size or not np.isfinite(value).all()):
        raise ValueError(f"{label} must be a finite unmasked float64 vector")
    return value


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite real")
    return float(value)


def audit_coarse_radius_moment(
    fine_radii_um: np.ndarray,
    weights: np.ndarray,
    claim: MomentClaim,
) -> MomentAudit:
    """Require explicit M3 evidence before claiming a coarsened cubic moment."""
    radii = _vector(fine_radii_um, "fine radii")
    probability = _vector(weights, "subcell weights")
    if radii.shape != probability.shape or np.any(radii <= 0) or np.any(probability < 0):
        raise ValueError("positive radii and same-shaped nonnegative weights required")
    total_weight = math.fsum(float(x) for x in probability)
    if abs(total_weight - 1.) > RTOL:
        raise ValueError("subcell weights must sum to one")
    if not isinstance(claim, MomentClaim):
        raise ValueError("declare the coarse moment evidence")
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        cubes = radii * radii * radii
        weighted_cubes = probability * cubes
    if (not np.isfinite(cubes).all() or not np.isfinite(weighted_cubes).all()
            or np.any(cubes == 0)
            or np.any((probability > 0) & (weighted_cubes == 0))):
        raise ValueError("nonlinear moment overflowed or positive contribution underflowed")
    try:
        mean_radius = math.fsum(float(w) * float(r) for r, w in zip(radii, probability))
        third_moment = math.fsum(float(x) for x in weighted_cubes)
        cube_of_mean = mean_radius ** 3
    except OverflowError as exc:
        raise ValueError("nonlinear moment overflowed") from exc
    if (not all(map(math.isfinite, (mean_radius, third_moment, cube_of_mean)))
            or cube_of_mean == 0):
        raise ValueError("nonlinear moment overflowed or underflowed")
    reported_mean = _finite(claim.mean_radius_um, "coarse mean radius")
    if not math.isclose(reported_mean, mean_radius, rel_tol=RTOL, abs_tol=0.):
        raise ValueError("coarse mean radius differs from weighted fine state")
    if claim.third_moment_um3 is None:
        if claim.third_moment_basis != "none" or claim.closure_id is not None:
            raise ValueError("missing third moment cannot have a retained/closure claim")
        carried = False
    else:
        if (claim.third_moment_basis not in {"retained", "declared_closure"}
                or (claim.third_moment_basis == "retained" and claim.closure_id is not None)
                or (claim.third_moment_basis == "declared_closure"
                    and (not isinstance(claim.closure_id, str) or not claim.closure_id))):
            raise ValueError("third moment needs retained or named closure provenance")
        reported_third = _finite(claim.third_moment_um3, "coarse third moment")
        if not math.isclose(reported_third, third_moment, rel_tol=RTOL, abs_tol=0.):
            raise ValueError("coarse third moment does not represent the fine distribution")
        carried = True
    return MomentAudit(mean_radius, third_moment, cube_of_mean,
                       third_moment - cube_of_mean, carried)


def require_carried_third_moment(
    fine_radii_um: np.ndarray,
    weights: np.ndarray,
    claim: MomentClaim,
) -> MomentAudit:
    """Recheck source data; do not approve a caller-fabricated audit result."""
    audit = audit_coarse_radius_moment(fine_radii_um, weights, claim)
    if not audit.third_moment_carried:
        raise ValueError("third-moment equivalence needs retained moment or declared closure")
    return audit


def check_realization_exchange(
    outgoing: np.ndarray,
    incoming: np.ndarray,
    *,
    expected_ids: tuple[str, ...],
    outgoing_ids: tuple[str, ...],
    incoming_ids: tuple[str, ...],
) -> RealizationAudit:
    """Internal signed integrated Q must be paired in every realization."""
    outflow = _vector(outgoing, "outgoing realization amounts")
    inflow = _vector(incoming, "incoming realization amounts")
    if outflow.shape != inflow.shape:
        raise ValueError("realization sets differ")
    if (not isinstance(expected_ids, tuple) or len(expected_ids) != outflow.size
            or any(not isinstance(x, str) or not x for x in expected_ids)
            or len(set(expected_ids)) != len(expected_ids)
            or outgoing_ids != expected_ids or incoming_ids != expected_ids):
        raise ValueError("realization identities differ from independent plan")
    if not np.array_equal(outflow, inflow):
        raise ValueError("internal transfer is unpaired in at least one realization")
    mean_out = math.fsum(float(x) for x in outflow) / outflow.size
    mean_in = math.fsum(float(x) for x in inflow) / inflow.size
    return RealizationAudit(outflow.size, mean_out, mean_in)


def check_external_correction(before: np.ndarray, after: np.ndarray,
                              physical_measure: np.ndarray,
                              event: ExternalCorrection) -> float:
    """Label analysis/ML inventory change separately from internal flux."""
    if (not isinstance(event, ExternalCorrection)
            or event.kind not in {"analysis", "ml"}
            or not isinstance(event.inventory_unit, str)
            or not event.inventory_unit):
        raise ValueError("declare analysis or ML external correction and inventory unit")
    reported = _finite(event.declared_increment, "external correction")
    actual = analysis_inventory_increment(before, after, physical_measure)
    if not math.isclose(reported, actual, rel_tol=RTOL, abs_tol=0.):
        raise ValueError("external correction does not explain inventory change")
    return actual
