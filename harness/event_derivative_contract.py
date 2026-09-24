"""Separate smooth branch derivatives, kink differences and event timing.

These are analytic synthetic examples. They do not change KDM's discrete
branch AD convention or implement a saltation/reset model in the host.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from numbers import Real


class EventLocation(str, Enum):
    OUTSIDE = "outside_window"
    BOUNDARY = "window_boundary"
    INTERIOR = "interior_transverse_crossing"


@dataclass(frozen=True)
class CoolingEvent:
    initial_temperature_k: float
    threshold_temperature_k: float
    cooling_rate_k_s: float
    window_start_s: float
    window_end_s: float


@dataclass(frozen=True)
class EventSensitivity:
    event_time_s: float
    dtime_dinitial_temperature_s_per_k: float
    dtime_dcooling_rate_s2_per_k: float


def _real(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite real")
    return float(value)


def classify_cooling_event(event: CoolingEvent) -> EventLocation:
    """T(t)=T0-a*t reaches T* only where the declared window contains it."""
    t0 = _real(event.initial_temperature_k, "initial temperature")
    threshold = _real(event.threshold_temperature_k, "threshold")
    a = _real(event.cooling_rate_k_s, "cooling rate")
    start = _real(event.window_start_s, "window start")
    end = _real(event.window_end_s, "window end")
    if a <= 0 or end <= start:
        raise ValueError("positive transverse cooling and ordered window required")
    crossing = (t0 - threshold) / a
    if not math.isfinite(crossing):
        raise ValueError("event time is not finite")
    if crossing == 0 and t0 != threshold:
        raise ValueError("nonzero event time is below binary64 resolution")
    if crossing < start or crossing > end:
        return EventLocation.OUTSIDE
    if crossing == start or crossing == end:
        return EventLocation.BOUNDARY
    return EventLocation.INTERIOR


def cooling_event_sensitivity(event: CoolingEvent) -> EventSensitivity:
    """Only an interior transverse event has the stated smooth event-time JVP."""
    if classify_cooling_event(event) is not EventLocation.INTERIOR:
        raise ValueError("event-time derivative requires an interior transverse crossing")
    a = event.cooling_rate_k_s
    delta = event.initial_temperature_k - event.threshold_temperature_k
    time = delta / a
    # -delta/a² = -time/a. The latter avoids an intermediate a² overflow or
    # underflow that can erase a finite, representable event-time derivative.
    result = EventSensitivity(time, 1. / a, -time / a)
    if not all(math.isfinite(x) for x in vars(result).values()):
        raise ValueError("event-time sensitivity overflowed")
    if time != 0 and result.dtime_dcooling_rate_s2_per_k == 0:
        raise ValueError("nonzero event-time rate sensitivity is below binary64 resolution")
    return result


@dataclass(frozen=True)
class CapPoint:
    value: float
    active_cap: bool
    selected_tangent: float


def discrete_cap(value: float, *, cap: float = 20.) -> CapPoint:
    """Executed strict `>cap` branch; equality selects tangent one."""
    x, bound = _real(value, "cap input"), _real(cap, "cap threshold")
    if bound <= 0:
        raise ValueError("positive cap required")
    active = x > bound
    return CapPoint(bound if active else x, active, 0. if active else 1.)


def branch_changing_increment(start: float, end: float, *, cap: float = 20.) -> float:
    """Finite operator response, not a local derivative across a kink."""
    return discrete_cap(end, cap=cap).value - discrete_cap(start, cap=cap).value
