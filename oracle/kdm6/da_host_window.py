"""Opt-in contract for a host-coupled MP137 assimilation window.

This is an orchestration interface, NOT a WRF implementation or a full-host
derivative certification. No native backend is installed by this module. The
legacy KDM-only ``da_window`` keeps its existing fixed-forcing contract.

A backend advances one COMPLETE host timestep, including the actual host RK
staging, KDM writeback, applied tendencies, and thermodynamic/geometry updates.
It derives KDM rho/pii/p/delz from the evolving host state inside that step.
Its checkpoint fields must contain every floating prognostic and memory field
needed for replay, including retained H_DIABATIC; the 12-field KDM State alone
is insufficient. Absolute step/time, configuration and prescribed inputs belong
to the backend/window specification, not a hidden evolving backend cache.

Forward checkpoints are explicit detached value boundaries. ``vjp`` and
``jvp`` must replay the ENTIRE transition from those values, rebuilding all
state-derived forcing on the live local graph. Supplying only a KDM partial
derivative at frozen forcing violates this interface. Observation cotangents
likewise include native center/interface pressure and profile construction.
RTTOV's existing fixed-pressure first-order wrapper does not meet that scope.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import math
from numbers import Real
from types import MappingProxyType
from typing import Callable, Generic, Mapping, Protocol, Sequence, TypeVar

import torch

FieldMap = Mapping[str, torch.Tensor]
StateT = TypeVar("StateT")
ExternalT = TypeVar("ExternalT")


class HostTransition(Protocol[StateT, ExternalT]):
    mp_physics: int
    derivative_scope: str  # "full_host" or "value_only"; local KDM is insufficient.
    required_state_fields: frozenset[str]

    def forward(self, step: int, state: StateT, external: ExternalT,
                dt: float) -> StateT: ...

    def vjp(self, step: int, state: StateT, external: ExternalT,
            dt: float, cotangent: FieldMap) -> FieldMap: ...

    def jvp(self, step: int, state: StateT, external: ExternalT,
            dt: float, direction: FieldMap) -> FieldMap: ...


@dataclass(frozen=True)
class FrozenSupport:
    n_valid: int
    signature: str


@dataclass(frozen=True)
class HostObservation:
    # Explicit value/cotangent boundary, matching a local observation replay.
    cost: float
    adjoint: FieldMap | None
    n_valid: int
    signature: str


@dataclass
class HostWindowResult:
    cost: float
    checkpoints: list[dict[str, torch.Tensor]]
    adjoint_initial: dict[str, torch.Tensor] | None


@dataclass
class HostForwardResult(Generic[StateT]):
    """Value-only full-window output; contains no cost or derivative claim."""

    checkpoints: list[StateT]


def _snapshot(fields: FieldMap, *, allow_empty: bool = False) -> dict[str, torch.Tensor]:
    if not isinstance(fields, Mapping) or (not fields and not allow_empty):
        raise ValueError("expected a nonempty host field mapping")
    out = {}
    for name, value in fields.items():
        if not isinstance(name, str) or not name or not isinstance(value, torch.Tensor):
            raise TypeError("host fields need named tensors")
        if not value.is_floating_point() or not bool(torch.isfinite(value).all()):
            raise ValueError(f"host field {name} must be finite floating point")
        # Full-step checkpoint/value boundary, never inside a live model replay.
        # Preserve dtype: operational f32 and an f64 research backend are distinct.
        out[name] = value.detach().clone()
    return out


def _matching(fields: FieldMap, reference: FieldMap, *, name: str) -> dict[str, torch.Tensor]:
    result = _snapshot(fields)
    if result.keys() != reference.keys():
        raise ValueError(f"{name} field keys differ from complete host state")
    for key, value in result.items():
        ref = reference[key]
        if value.shape != ref.shape or value.dtype != ref.dtype or value.device != ref.device:
            raise ValueError(f"{name}.{key} shape/dtype/device differs from host state")
    return result


class CoupledHostWindow:
    """One immutable prescribed-input/observation schedule, many fresh trials.

    Every ``evaluate`` starts from its supplied initial host state and executes
    every full-model step. Nothing is warm-started from the preceding trial's
    terminal state. Add J_b and the control-transform pullback in the optimizer
    closure; the returned adjoint is d(sum J_obs)/d(full initial host state).

    Supports are fixed BEFORE minimization, from bound observations/outer-loop
    QC. Step 0 is the initial state; step T is the terminal state. Mapping those
    steps to UTC and verifying pixel acquisition times is the caller's job.
    """

    def __init__(self, model: HostTransition[FieldMap, FieldMap], external_steps: Sequence[FieldMap], *,
                 dt: float, observe: Callable, supports: Mapping[int, FrozenSupport]):
        if model.mp_physics != 137:
            raise ValueError("this host-coupled contract requires MP_PHYSICS=137")
        if isinstance(dt, bool) or not isinstance(dt, Real) or not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be finite and positive")
        if not model.required_state_fields:
            raise ValueError("backend must declare its complete checkpoint fields")
        if not external_steps:
            raise ValueError("a host window needs at least one full timestep")
        self.model, self.dt, self.observe = model, float(dt), observe
        self._external = []
        for external in external_steps:
            if any(value.requires_grad for value in external.values()):
                raise ValueError("prescribed external inputs cannot be controls in this API")
            self._external.append(_snapshot(external, allow_empty=True))
        frozen = dict(supports)
        if not frozen:
            raise ValueError("an assimilation window needs declared observation slots")
        for step, support in frozen.items():
            if isinstance(step, bool) or not isinstance(step, int) or not 0 <= step <= len(self._external):
                raise ValueError("observation step is outside this window")
            if (type(support.n_valid) is not int or support.n_valid <= 0
                    or not isinstance(support.signature, str) or not support.signature):
                raise ValueError("observation support needs positive count and nonempty signature")
        self.supports = MappingProxyType(frozen)

    def _initial(self, state: FieldMap) -> dict[str, torch.Tensor]:
        fields = _snapshot(state)
        missing = set(self.model.required_state_fields) - fields.keys()
        if missing:
            raise ValueError(f"incomplete host checkpoint; missing {sorted(missing)}")
        return fields

    def _derivatives(self, *, observation: bool, tangent: bool = False) -> None:
        if self.model.derivative_scope != "full_host":
            raise RuntimeError("full-host derivatives required; value-only/local-KDM backend cannot optimize")
        method = "jvp" if tangent else "vjp"
        if not callable(getattr(self.model, method, None)):
            raise RuntimeError(f"full host-step {method} is unavailable")
        if observation and getattr(self.observe, "derivative_scope", None) != "full_host":
            raise RuntimeError("full-host observation adjoint including pressure/profile derivatives required")

    def _advance(self, step: int, state: FieldMap) -> dict[str, torch.Tensor]:
        # Value-only forward checkpoint contract. Backward uses a fresh LOCAL
        # graph inside backend.vjp, including forcing_provider(live_state).
        with torch.no_grad():
            result = self.model.forward(step, _snapshot(state),
                                        _snapshot(self._external[step], allow_empty=True), self.dt)
        return _matching(result, state, name="next_state")

    def evaluate(self, initial: FieldMap, *, need_gradient: bool = True) -> HostWindowResult:
        if need_gradient:
            # Reject incomplete derivatives before even starting a trial/model.
            self._derivatives(observation=True)
        current = self._initial(initial)
        checkpoints = [current]
        obs_adjoints = {}
        cost = 0.0
        for step in range(len(self._external) + 1):
            if step in self.supports:
                term = self.observe(step, _snapshot(current), need_gradient=need_gradient)
                if not isinstance(term, HostObservation):
                    raise TypeError("declared observation slot must return HostObservation")
                expected = self.supports[step]
                if (type(term.n_valid) is not int or term.n_valid != expected.n_valid
                        or term.signature != expected.signature):
                    raise RuntimeError("observation support/signature changed within the window")
                if isinstance(term.cost, bool) or not isinstance(term.cost, Real) or not math.isfinite(term.cost):
                    raise ValueError("observation cost must be a finite scalar value")
                cost += float(term.cost)
                if need_gradient:
                    if term.adjoint is None:
                        raise RuntimeError("observation returned no full-state cotangent")
                    obs_adjoints[step] = _matching(term.adjoint, current, name="observation_adjoint")
            if step < len(self._external):
                current = self._advance(step, current)
                checkpoints.append(current)
        if not math.isfinite(cost):
            raise ValueError("summed observation cost is nonfinite")
        adjoint = None
        if need_gradient:
            adjoint = {key: torch.zeros_like(value) for key, value in current.items()}
            for step in reversed(range(len(self._external) + 1)):
                if step in obs_adjoints:
                    adjoint = _matching(
                        {key: value + obs_adjoints[step][key] for key, value in adjoint.items()},
                        checkpoints[step], name="accumulated_observation_adjoint")
                if step:
                    adjoint = _matching(
                        self.model.vjp(step - 1, _snapshot(checkpoints[step - 1]),
                                       _snapshot(self._external[step - 1], allow_empty=True),
                                       self.dt, _snapshot(adjoint)),
                        checkpoints[step - 1], name="host_step_vjp")
        return HostWindowResult(cost, checkpoints, adjoint)

    def jvp(self, initial: FieldMap, direction: FieldMap) -> tuple[dict, dict]:
        """Full-model terminal tangent; no RTTOV HVP is implied."""
        self._derivatives(observation=False, tangent=True)
        current = self._initial(initial)
        tangent = _matching(direction, current, name="initial_direction")
        for step in range(len(self._external)):
            next_tangent = self.model.jvp(step, _snapshot(current),
                                          _snapshot(self._external[step], allow_empty=True),
                                          self.dt, _snapshot(tangent))
            current = self._advance(step, current)
            tangent = _matching(next_tangent, current, name="host_step_jvp")
        return current, tangent


class HostForwardWindow(Generic[StateT, ExternalT]):
    """Value-only full-host replay for opaque, explicitly validated states.

    The snapshot callback must validate the complete native checkpoint (for
    example, required fields, timestamp, and file identity/hash) and return an
    independent immutable snapshot.  The generic orchestrator deliberately
    does not coerce opaque checkpoint values into floating-point tensors.
    External inputs are deep-copied at construction and again for each call.
    Each ``evaluate`` restarts from its supplied initial checkpoint and invokes
    the same ``HostTransition.forward`` protocol used by the AD window.
    """

    def __init__(
        self,
        model: HostTransition[StateT, ExternalT],
        external_steps: Sequence[ExternalT],
        *,
        dt: float,
        snapshot: Callable[[StateT], StateT],
    ):
        mp_physics = getattr(model, "mp_physics", None)
        if isinstance(mp_physics, bool) or mp_physics != 137:
            raise ValueError("this host-coupled contract requires MP_PHYSICS=137")
        scope = getattr(model, "derivative_scope", None)
        if scope not in {"full_host", "value_only"}:
            raise ValueError("backend must declare derivative_scope as full_host or value_only")
        required = getattr(model, "required_state_fields", None)
        if (not isinstance(required, (set, frozenset)) or not required
                or any(not isinstance(field, str) or not field for field in required)):
            raise ValueError("backend must declare nonempty required checkpoint fields")
        if isinstance(dt, bool) or not isinstance(dt, Real) or not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be finite and positive")
        if not external_steps:
            raise ValueError("a host window needs at least one full timestep")
        if not callable(snapshot):
            raise TypeError("an explicit checkpoint snapshot/validation callback is required")

        self.model = model
        self.dt = float(dt)
        self.snapshot = snapshot
        # Own the schedule so caller mutations cannot steer a trial.
        self._external_steps = tuple(copy.deepcopy(value) for value in external_steps)

    def _state_snapshot(self, value: StateT) -> StateT:
        result = self.snapshot(value)
        if result is None:
            raise TypeError("checkpoint snapshot callback returned None")
        return result

    def evaluate(self, initial: StateT) -> HostForwardResult[StateT]:
        """Run every prescribed native step from a fresh initial snapshot."""
        current = self._state_snapshot(initial)
        checkpoints = [current]
        for step, external in enumerate(self._external_steps):
            step_input = self._state_snapshot(current)
            step_external = copy.deepcopy(external)
            output = self.model.forward(step, step_input, step_external, self.dt)
            current = self._state_snapshot(output)
            checkpoints.append(current)
        return HostForwardResult(checkpoints)
