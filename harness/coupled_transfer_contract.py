"""Two exact one-way operators versus their coupled two-reservoir equation.

This is a synthetic noncommuting example, not a KDM or host process solver.
It separates each component's positivity/conservation from coupling order,
same-final-time distribution and the combined equilibrium.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real


@dataclass(frozen=True)
class Reservoirs:
    left: float
    right: float

    def total(self) -> float:
        return self.left + self.right


@dataclass(frozen=True)
class TransferRates:
    left_to_right_s_inv: float
    right_to_left_s_inv: float


@dataclass(frozen=True)
class CouplingComparison:
    a_then_b: Reservoirs
    b_then_a: Reservoirs
    coupled_exact: Reservoirs
    order_l1: float
    a_then_b_reference_l1: float
    b_then_a_reference_l1: float


def _real(value: object, label: str, *, nonnegative: bool = False) -> float:
    if (isinstance(value, bool) or not isinstance(value, Real)
            or not math.isfinite(value) or (nonnegative and value < 0)):
        raise ValueError(f"{label} must be finite real" + (" and nonnegative" if nonnegative else ""))
    return float(value)


def _validate(state: Reservoirs, rates: TransferRates, dt_s: float) -> float:
    left = _real(state.left, "left reservoir", nonnegative=True)
    right = _real(state.right, "right reservoir", nonnegative=True)
    a = _real(rates.left_to_right_s_inv, "A rate", nonnegative=True)
    b = _real(rates.right_to_left_s_inv, "B rate", nonnegative=True)
    dt = _real(dt_s, "duration")
    if dt <= 0 or not math.isfinite(left + right) or not math.isfinite((a + b) * dt):
        raise ValueError("positive finite duration and finite coupled scale required")
    return dt


def _a(state: Reservoirs, a: float, dt: float) -> Reservoirs:
    moved = state.left * -math.expm1(-a * dt)
    return Reservoirs(state.left - moved, state.right + moved)


def _b(state: Reservoirs, b: float, dt: float) -> Reservoirs:
    moved = state.right * -math.expm1(-b * dt)
    return Reservoirs(state.left + moved, state.right - moved)


def ordered_split(state: Reservoirs, rates: TransferRates, dt_s: float,
                  *, order: str) -> Reservoirs:
    """Apply both *exact* one-way maps for the same physical duration."""
    dt = _validate(state, rates, dt_s)
    if order == "AB":
        result = _b(_a(state, rates.left_to_right_s_inv, dt),
                    rates.right_to_left_s_inv, dt)
    elif order == "BA":
        result = _a(_b(state, rates.right_to_left_s_inv, dt),
                    rates.left_to_right_s_inv, dt)
    else:
        raise ValueError("declare AB or BA operator order")
    if not all(math.isfinite(x) and x >= 0 for x in (result.left, result.right)):
        raise ValueError("split state left the declared nonnegative domain")
    return result


def coupled_exact(state: Reservoirs, rates: TransferRates, dt_s: float) -> Reservoirs:
    """Analytic solution of dL/dt=-aL+bR, dR/dt=aL-bR."""
    dt = _validate(state, rates, dt_s)
    a, b = rates.left_to_right_s_inv, rates.right_to_left_s_inv
    if a + b == 0:
        return state
    total = state.total()
    # Form the bounded ratio first: total*b can overflow even when the
    # equilibrium and every declared input are finite.
    equilibrium_left = total * (b / (a + b))
    left = equilibrium_left + (state.left - equilibrium_left) * math.exp(-(a + b) * dt)
    result = Reservoirs(left, total - left)
    if not all(math.isfinite(x) and x >= 0 for x in (result.left, result.right)):
        raise ValueError("coupled reference left the finite nonnegative domain")
    return result


def compare_coupling(state: Reservoirs, rates: TransferRates, dt_s: float) -> CouplingComparison:
    ab = ordered_split(state, rates, dt_s, order="AB")
    ba = ordered_split(state, rates, dt_s, order="BA")
    ref = coupled_exact(state, rates, dt_s)
    l1 = lambda x, y: abs(x.left - y.left) + abs(x.right - y.right)
    distances = (l1(ab, ba), l1(ab, ref), l1(ba, ref))
    if not all(math.isfinite(d) for d in distances):
        raise ValueError("coupled comparison metric overflowed")
    return CouplingComparison(ab, ba, ref, *distances)


def check_declared_order(state: Reservoirs, rates: TransferRates, dt_s: float,
                         observed: Reservoirs, *, declared_order: str,
                         atol: float = 1e-12) -> None:
    """Reject a distinguishable swapped-order execution despite conserved sum."""
    tol = _real(atol, "state comparison tolerance", nonnegative=True)
    expected = ordered_split(state, rates, dt_s, order=declared_order)
    if not all(isinstance(x, Real) and not isinstance(x, bool)
               and math.isfinite(x) and x >= 0
               for x in (observed.left, observed.right)):
        raise ValueError("observed coupled state must be finite nonnegative real")
    if (abs(observed.left - expected.left) > tol
            or abs(observed.right - expected.right) > tol):
        raise ValueError("observed state does not match the declared operator order")
