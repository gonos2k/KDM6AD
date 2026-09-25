"""Synthetic power-dual intensive/force-density mapping on complete cells.

The supplied intensive map P is checked by X6's measure/constant contract.
With v_t=P v_s, the extensive source force must be P^T f_t. In density form
f=w*g, so g_s=W_s^-1 P^T W_t g_t. This is not a production mesh coupler.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from overlap_remap_contract import OverlapRemap, check_overlap_remap


RTOL = 1e-12


@dataclass(frozen=True)
class DualWorkAudit:
    source_power_w: float
    target_power_w: float
    power_residual_w: float
    source_total_force_n: float
    target_total_force_n: float


def _vector(value: object, label: str, length: int) -> np.ndarray:
    if (np.ma.isMaskedArray(value) or not isinstance(value, np.ndarray)
            or value.dtype != np.float64 or value.ndim != 1
            or value.shape != (length,) or not np.isfinite(value).all()):
        raise ValueError(f"{label} must be a finite unmasked float64 vector")
    return value


def _full_overlap(spec: OverlapRemap) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not isinstance(spec, OverlapRemap):
        raise ValueError("declare a checked conservative remap")
    check_overlap_remap(spec)
    if (spec.normalization != "covered_area"
            or np.any(spec.source_fraction != 1.)
            or np.any(spec.destination_fraction != 1.)):
        raise ValueError("dual pilot requires complete source/destination coverage")
    return spec.matrix, spec.source_measure, spec.destination_measure


def map_intensive_and_dual_density(
    spec: OverlapRemap,
    source_velocity_m_s: np.ndarray,
    target_force_density_n_m2: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Produce v_target [m/s] and g_source [N/m²] from declared P and w."""
    p, ws, wt = _full_overlap(spec)
    velocity = _vector(source_velocity_m_s, "source velocity", ws.size)
    density = _vector(target_force_density_n_m2, "target force density", wt.size)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        target_velocity = p @ velocity
        source_density = (p.T @ (wt * density)) / ws
    if not np.isfinite(target_velocity).all() or not np.isfinite(source_density).all():
        raise ValueError("mapped velocity or dual force overflowed")
    return target_velocity, source_density


def check_dual_work(
    spec: OverlapRemap,
    source_velocity_m_s: np.ndarray,
    target_velocity_m_s: np.ndarray,
    target_force_density_n_m2: np.ndarray,
    source_force_density_n_m2: np.ndarray,
) -> DualWorkAudit:
    """Require both map equations and their total-force/power consequences."""
    p, ws, wt = _full_overlap(spec)
    source_velocity = _vector(source_velocity_m_s, "source velocity", ws.size)
    target_velocity = _vector(target_velocity_m_s, "target velocity", wt.size)
    target_density = _vector(target_force_density_n_m2, "target force density", wt.size)
    source_density = _vector(source_force_density_n_m2, "source force density", ws.size)
    predicted_velocity, predicted_density = map_intensive_and_dual_density(
        spec, source_velocity, target_density)
    if not np.allclose(target_velocity, predicted_velocity, rtol=RTOL, atol=0.):
        raise ValueError("intensive target value differs from declared P")
    if not np.allclose(source_density, predicted_density, rtol=RTOL, atol=0.):
        raise ValueError("source force density differs from measure-aware dual P transpose")

    source_force = ws * source_density
    target_force = wt * target_density
    source_power_terms = source_velocity * source_force
    target_power_terms = target_velocity * target_force
    if not all(np.isfinite(x).all() for x in
               (source_force, target_force, source_power_terms, target_power_terms)):
        raise ValueError("extensive force or power overflowed")
    source_power = math.fsum(float(x) for x in source_power_terms)
    target_power = math.fsum(float(x) for x in target_power_terms)
    source_total = math.fsum(float(x) for x in source_force)
    target_total = math.fsum(float(x) for x in target_force)
    power_scale = math.fsum(abs(float(x)) for x in source_power_terms) + math.fsum(
        abs(float(x)) for x in target_power_terms)
    force_scale = math.fsum(abs(float(x)) for x in source_force) + math.fsum(
        abs(float(x)) for x in target_force)
    if not all(map(math.isfinite, (source_power, target_power, source_total,
                                   target_total, power_scale, force_scale))):
        raise ValueError("power/force budget overflowed")
    power_residual = source_power - target_power
    if (abs(power_residual) > RTOL * power_scale
            or abs(source_total - target_total) > RTOL * force_scale):
        raise ValueError("dual map fails total-force or power pairing")
    return DualWorkAudit(source_power, target_power, power_residual,
                         source_total, target_total)
