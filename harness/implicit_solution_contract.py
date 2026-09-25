"""Synthetic positive-root implicit-solve and derivative acceptance pilot.

The equation R(y,p)=y*y-p=0 is dimensionless. Differentiating a finite Newton
iteration gives the algorithmic derivative, not necessarily the implicit
solution derivative. No KDM implicit solver is modified or certified here.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real


RESIDUAL_REL_TOL = 1e-12
LINEARIZED_STATE_REL_TOL = 1e-12
TANGENT_RESIDUAL_TOL = 1e-10
MIN_JACOBIAN_ABS = 1e-8


@dataclass(frozen=True)
class NewtonResult:
    value: float
    algorithmic_tangent: float
    iterations: int
    solver_converged: bool
    initial_value: float
    active_set_changed: bool = False


@dataclass(frozen=True)
class ImplicitAudit:
    state_residual: float
    scaled_state_residual: float
    linearized_state_error: float
    scaled_linearized_error: float
    tangent_residual: float
    implicit_tangent: float


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite real")
    return float(value)


def newton_positive_sqrt(p: float, initial: float, iterations: int) -> NewtonResult:
    """Execute exactly the stated number of Newton steps with a true JVP.

    The tangent is d(iterate)/dp for fixed initial and fixed iteration count.
    This routine does not stop early or change its branch to force acceptance.
    """
    p = _finite(p, "parameter")
    value = _finite(initial, "initial iterate")
    if p <= 0 or value <= 0 or type(iterations) is not int or iterations < 0:
        raise ValueError("positive p/initial and nonnegative integer iteration count required")
    tangent = 0.0
    for _ in range(iterations):
        old_value, old_tangent = value, tangent
        value = 0.5 * (old_value + p / old_value)
        tangent = 0.5 * (old_tangent + 1.0 / old_value
                         - p * old_tangent / (old_value * old_value))
        _finite(value, "Newton iterate")
        _finite(tangent, "Newton algorithmic tangent")
        if value <= 0:
            raise ValueError("Newton iterate left the positive-root branch")
    residual = _finite(value * value - p, "Newton residual")
    converged = abs(residual) / max(1.0, p) <= RESIDUAL_REL_TOL
    return NewtonResult(value, tangent, iterations, converged, float(initial))


def audit_positive_sqrt(p: float, result: NewtonResult) -> ImplicitAudit:
    """Require state and tangent equations, conditioning and execution status.

    The linearized state-error estimate |R/R_y| is diagnostic, not a global
    mathematical error bound. Thresholds are fixed before the pilot runs.
    """
    p = _finite(p, "parameter")
    if p <= 0 or not isinstance(result, NewtonResult):
        raise ValueError("positive parameter and Newton result required")
    value = _finite(result.value, "result value")
    tangent = _finite(result.algorithmic_tangent, "result tangent")
    if (value <= 0 or type(result.iterations) is not int or result.iterations < 0
            or type(result.solver_converged) is not bool
            or type(result.active_set_changed) is not bool):
        raise ValueError("positive-root result needs valid branch/status fields")
    if result.active_set_changed:
        raise ValueError("active-set change needs a separate branch audit")
    replayed = newton_positive_sqrt(p, result.initial_value, result.iterations)
    if (value != replayed.value or tangent != replayed.algorithmic_tangent
            or result.solver_converged != replayed.solver_converged):
        raise ValueError("reported result does not match executed Newton iterations")
    residual = _finite(value * value - p, "state residual")
    jacobian = _finite(2.0 * value, "state Jacobian")
    if jacobian < MIN_JACOBIAN_ABS:
        raise ValueError("state Jacobian is too small for this conditioned pilot")
    scaled_residual = abs(residual) / max(1.0, p)
    linearized_error = abs(residual / jacobian)
    scaled_error = linearized_error / max(1.0, abs(value))
    tangent_residual = _finite(jacobian * tangent - 1.0, "tangent residual")
    if (not result.solver_converged or scaled_residual > RESIDUAL_REL_TOL
            or scaled_error > LINEARIZED_STATE_REL_TOL):
        raise ValueError("implicit state solve did not satisfy convergence gates")
    if abs(tangent_residual) > TANGENT_RESIDUAL_TOL:
        raise ValueError("implicit tangent equation did not close")
    return ImplicitAudit(residual, scaled_residual, linearized_error,
                         scaled_error, tangent_residual, 1.0 / jacobian)
