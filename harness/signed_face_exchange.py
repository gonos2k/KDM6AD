"""Declared two-cell water-depth exchange; no KDM/soil production solver.

Positive signed amount crosses the single face left→right, negative right→left.
Inventory is water depth [m] per unit horizontal area, theta*layer_thickness.
The checker accepts an externally supplied applied amount; the separate toy
adapter below declares one particular hydraulic-head/capacity policy.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class WaterCells:
    theta_left: float
    theta_right: float
    thickness_left_m: float
    thickness_right_m: float
    porosity_left: float
    porosity_right: float

    def inventories_m(self) -> tuple[float, float]:
        return (self.theta_left * self.thickness_left_m,
                self.theta_right * self.thickness_right_m)


@dataclass(frozen=True)
class FaceEvent:
    requested_m: float
    applied_m: float
    external_left_m: float = 0.0
    external_right_m: float = 0.0


@dataclass(frozen=True)
class FaceBudget:
    left_residual_m: float
    right_residual_m: float
    total_residual_m: float


def _validate_state(state: WaterCells, tol: float) -> None:
    values = tuple(vars(state).values())
    if not all(math.isfinite(x) for x in values):
        raise ValueError("cell geometry and water state must be finite")
    if (state.thickness_left_m <= 0 or state.thickness_right_m <= 0
            or not 0 < state.porosity_left <= 1
            or not 0 < state.porosity_right <= 1):
        raise ValueError("positive thickness and porosity in (0,1] required")
    left, right = state.inventories_m()
    if (not -tol <= left <= state.porosity_left * state.thickness_left_m + tol
            or not -tol <= right <= state.porosity_right * state.thickness_right_m + tol):
        raise ValueError("accepted soil-water state is outside [0,porosity]")


def check_face_exchange(before: WaterCells, after: WaterCells,
                        event: FaceEvent, *, atol_m: float = 1e-12) -> FaceBudget:
    """Audit a supplied signed *integrated* face amount and external sources.

    This does not choose a diffusion law, limiter or source-application order.
    The two states have fixed geometry and capacities at this boundary. Later
    changing-geometry and time-varying-flux contracts are separate checklist
    items, not hidden assumptions of this check.
    """
    if not math.isfinite(atol_m) or atol_m < 0:
        raise ValueError("water-depth tolerance must be finite and nonnegative")
    _validate_state(before, atol_m)
    _validate_state(after, atol_m)
    if any(getattr(before, field) != getattr(after, field) for field in
           ("thickness_left_m", "thickness_right_m", "porosity_left", "porosity_right")):
        raise ValueError("changing geometry/capacity requires a separate contract")
    if not all(math.isfinite(x) for x in vars(event).values()):
        raise ValueError("face and external amounts must be finite")
    if ((event.requested_m == 0 and event.applied_m != 0)
            or (event.requested_m > 0 and event.applied_m < 0)
            or (event.requested_m < 0 and event.applied_m > 0)
            or abs(event.applied_m) > abs(event.requested_m) + atol_m):
        raise ValueError("applied face amount must retain request direction and bound")
    b_left, b_right = before.inventories_m()
    a_left, a_right = after.inventories_m()
    left_expected = b_left - event.applied_m + event.external_left_m
    right_expected = b_right + event.applied_m + event.external_right_m
    if not all(math.isfinite(x) for x in (left_expected, right_expected,
                                            b_left, b_right, a_left, a_right)):
        raise ValueError("integrated face budget overflowed")
    left_residual = a_left - left_expected
    right_residual = a_right - right_expected
    total_residual = ((a_left + a_right) - (b_left + b_right)
                      - event.external_left_m - event.external_right_m)
    if not all(math.isfinite(x) for x in (left_residual, right_residual,
                                           total_residual)):
        raise ValueError("integrated face residual is nonfinite")
    if max(abs(left_residual), abs(right_residual), abs(total_residual)) > atol_m:
        raise ValueError("applied face/external amounts do not match cell inventories")
    return FaceBudget(left_residual, right_residual, total_residual)


def two_cell_soil_head_step(before: WaterCells, *, head_left_m: float,
                            head_right_m: float, conductivity_m_s: float,
                            face_distance_m: float, dt_s: float) -> tuple[WaterCells, FaceEvent]:
    """A declared synthetic capacity-limited head-gradient pilot.

    ``K*(head_left-head_right)/distance`` is a signed m/s face flux in this
    toy law; integrating over dt gives a water depth. It is **not** a KDM or
    host land-surface parameterization and imports no sedimentation velocity.
    """
    _validate_state(before, 0.0)
    if (not all(math.isfinite(x) for x in (head_left_m, head_right_m,
                                            conductivity_m_s, face_distance_m,
                                            dt_s))
            or conductivity_m_s < 0 or face_distance_m <= 0 or dt_s <= 0):
        raise ValueError("finite heads, nonnegative K, positive distance/dt required")
    requested = conductivity_m_s * (head_left_m - head_right_m) * dt_s / face_distance_m
    if not math.isfinite(requested):
        raise ValueError("requested face exchange overflowed")
    left, right = before.inventories_m()
    cap_left = before.porosity_left * before.thickness_left_m - left
    cap_right = before.porosity_right * before.thickness_right_m - right
    if requested >= 0:
        applied = min(requested, left, cap_right)
    else:
        applied = -min(-requested, right, cap_left)
    # At equilibrium (or a fully blocked face), avoid a theta→inventory→theta
    # roundtrip that changes the last bit despite exactly zero transfer.
    after = before if applied == 0 else WaterCells(
        theta_left=(left - applied) / before.thickness_left_m,
        theta_right=(right + applied) / before.thickness_right_m,
        thickness_left_m=before.thickness_left_m,
        thickness_right_m=before.thickness_right_m,
        porosity_left=before.porosity_left,
        porosity_right=before.porosity_right,
    )
    event = FaceEvent(requested_m=requested, applied_m=applied)
    check_face_exchange(before, after, event)
    return after, event
