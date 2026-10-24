"""Value-only accounting of executed QR transfers, in top-first order.

No source equation or AD path is changed. Weights are the fixed request's
binary64 DEND*DELZ, followed by rounded products and math.fsum. Signed
interface gaps and diagnostic-vs-applied bottom flow are kept separate.
"""

from __future__ import annotations

import math

import numpy as np


def _finite(values, name):
    array = np.asarray(values)
    if array.dtype != np.float64 or not np.isfinite(array).all():
        raise ValueError(f"{name} must be finite binary64")
    return array


def surface_component(rate, depth, dt, denr=1000.0):
    """Reconstruct one component in the source's left-associated order."""
    rate, depth = (
        np.asarray(rate, dtype=np.float64),
        np.asarray(depth, dtype=np.float64),
    )
    if (
        rate.ndim != 1
        or rate.shape != depth.shape
        or not rate.size
        or not np.isfinite(rate).all()
        or not np.isfinite(depth).all()
        or np.any(depth <= 0)
    ):
        raise ValueError(
            "finite matching column-rate/depth vectors with positive depth required"
        )
    if not math.isfinite(dt) or dt <= 0 or not math.isfinite(denr) or denr <= 0:
        raise ValueError("positive finite dt/water density required")
    return np.maximum(rate, 0.0) * depth / denr * dt * 1000.0


def step_budget(before, after, departure, arrival, density, depth):
    """Return per-column transfer accounting for one executed main substep.

    Arrays have (B,L), top-first; departure and arrival are the actual operands
    of the state update. Top departure may instead be observed before-after
    because its source expression has no named min-cap operand.
    """
    arrays = [
        _finite(v, n)
        for v, n in zip(
            (before, after, departure, arrival, density, depth),
            ("before", "after", "departure", "arrival", "density", "depth"),
        )
    ]
    before, after, departure, arrival, density, depth = arrays
    if (
        before.ndim != 2
        or not before.size
        or any(a.shape != before.shape for a in arrays)
    ):
        raise ValueError("nonempty matching (B,L) arrays required")
    if (
        any(np.any(a < 0) for a in arrays[:4])
        or np.any(density <= 0)
        or np.any(depth <= 0)
    ):
        raise ValueError("nonnegative water/transfers and positive geometry required")
    if np.any(arrival[:, 0] != 0):
        raise ValueError("top arrival must be zero")
    weights = density * depth
    if not np.isfinite(weights).all():
        raise ValueError("finite layer measure required")
    D, A = departure * weights, arrival * weights
    gaps = D[:, :-1] - A[:, 1:]
    result = {
        name: np.empty(before.shape[0], dtype=np.float64)
        for name in (
            "state_change",
            "actual_bottom_departure",
            "actual_bottom_arrival",
            "bottom_net_depletion",
            "internal_departure_minus_arrival",
            "state_plus_bottom_plus_internal_residual",
            "roundoff_gate",
        )
    }
    for b in range(before.shape[0]):
        delta = math.fsum(float(x) for x in (weights[b] * (after[b] - before[b])))
        bottom = float(D[b, -1])
        gap = math.fsum(float(x) for x in gaps[b])
        result["state_change"][b] = delta
        result["actual_bottom_departure"][b] = bottom
        result["actual_bottom_arrival"][b] = A[b, -1]
        result["bottom_net_depletion"][b] = float(
            weights[b, -1] * (before[b, -1] - after[b, -1])
        )
        result["internal_departure_minus_arrival"][b] = gap
        result["state_plus_bottom_plus_internal_residual"][b] = math.fsum(
            (delta, bottom, gap)
        )
        scale = math.fsum(
            float(x)
            for x in np.r_[
                weights[b] * (abs(before[b]) + abs(after[b])), abs(D[b]), abs(A[b])
            ]
        )
        result["roundoff_gate"][b] = 256 * np.finfo(float).eps * max(1.0, scale)
    result["interface_gaps"] = gaps
    return result


def reported_budget(step_results, qr_reported):
    """Aggregate one chain call and split its reported QR residual.

    delta+P = (P-bottom_actual) - sum(internal departure-arrival) + rounding.
    P is the QR-only reconstructed component; the returned total precipitation
    is a distinct multi-species quantity validated by the trace reader.
    """
    if not step_results:
        raise ValueError("at least one substep required")
    qr_reported = _finite(qr_reported, "reported QR component")
    batch = step_results[0]["state_change"].size
    if qr_reported.shape != (batch,):
        raise ValueError("one reported value per column required")
    result = {
        name: np.empty(batch, dtype=np.float64)
        for name in (
            "state_change",
            "actual_bottom_departure",
            "internal_departure_minus_arrival",
            "reported_bottom_minus_applied",
            "state_plus_reported",
            "decomposition_residual",
            "roundoff_gate",
        )
    }
    for b in range(batch):
        delta = math.fsum(float(s["state_change"][b]) for s in step_results)
        bottom = math.fsum(float(s["actual_bottom_departure"][b]) for s in step_results)
        gap = math.fsum(
            float(s["internal_departure_minus_arrival"][b]) for s in step_results
        )
        excess = float(qr_reported[b] - bottom)
        raw = math.fsum((delta, float(qr_reported[b])))
        result["state_change"][b] = delta
        result["actual_bottom_departure"][b] = bottom
        result["internal_departure_minus_arrival"][b] = gap
        result["reported_bottom_minus_applied"][b] = excess
        result["state_plus_reported"][b] = raw
        result["decomposition_residual"][b] = math.fsum((raw, -excess, gap))
        result["roundoff_gate"][b] = math.fsum(
            float(s["roundoff_gate"][b]) for s in step_results
        )
    return result
