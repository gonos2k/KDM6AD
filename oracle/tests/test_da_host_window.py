"""Toy-contract tests for the opt-in complete-host DA window.

These tests exercise only an analytic in-memory transition.  They make no
claim about a native WRF/MP137 derivative or about operational cycling.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pytest
import torch

from kdm6.da_host_window import (
    CoupledHostWindow,
    FrozenSupport,
    HostObservation,
)


FIELDS = ("th", "qv", "h_diabatic")
DT = 0.4
N_STEPS = 3


def _tensor(value: float, *, requires_grad: bool = False) -> torch.Tensor:
    return torch.tensor([value], dtype=torch.float64, requires_grad=requires_grad)


def _state(values=(299.0, 0.006, 0.15)) -> dict[str, torch.Tensor]:
    return {name: _tensor(value) for name, value in zip(FIELDS, values)}


def _external() -> list[dict[str, torch.Tensor]]:
    return [{"base": _tensor(value)} for value in (0.3, -0.2, 0.5)]


def _vector(fields: Mapping[str, torch.Tensor]) -> torch.Tensor:
    return torch.stack([fields[name].reshape(()) for name in FIELDS])


def _field_map(vector: torch.Tensor, reference: Mapping[str, torch.Tensor]):
    return {name: vector[i].reshape_as(reference[name]) for i, name in enumerate(FIELDS)}


def _jacobian(dt: float, *, detach_derived_forcing: bool = False) -> torch.Tensor:
    # The transition's forcing is f_t = external.base + 0.5 * h_t.
    # The alternative Jacobian deliberately drops only df/dh to model the
    # detached-forcing bug that a coupled adjoint must catch.
    h_to_forcing = 0.0 if detach_derived_forcing else 0.5
    return torch.tensor([
        [1.0, 0.11 * dt, 0.20 * h_to_forcing * dt],
        [-0.06 * dt, 1.0, 0.08 * h_to_forcing * dt],
        [0.02 * dt, 0.03 * dt, 0.55 + 0.10 * h_to_forcing * dt],
    ], dtype=torch.float64)


class SmoothHost137:
    """Small, smooth, analytic MP137-like host transition for orchestration."""

    mp_physics = 137
    derivative_scope = "full_host"
    required_state_fields = frozenset(FIELDS)

    def __init__(self, *, detach_derived_forcing: bool = False):
        self.detach_derived_forcing = detach_derived_forcing
        self.forward_steps: list[int] = []
        self.forward_inputs: list[dict[str, torch.Tensor]] = []
        self.derived_forcing: list[float] = []
        self.vjp_steps: list[int] = []
        self.jvp_steps: list[int] = []
        self.forward_grad_enabled: list[bool] = []

    def _matrix(self, dt: float) -> torch.Tensor:
        return _jacobian(dt, detach_derived_forcing=self.detach_derived_forcing)

    def forward(self, step: int, state, external, dt: float):
        self.forward_steps.append(step)
        self.forward_inputs.append({k: v.detach().clone() for k, v in state.items()})
        self.forward_grad_enabled.append(torch.is_grad_enabled())
        h = state["h_diabatic"]
        if self.detach_derived_forcing:
            h = h.detach()
        forcing = external["base"] + 0.5 * h
        self.derived_forcing.append(float(forcing.detach().reshape(())))
        th, qv, hdiag = (state[name] for name in FIELDS)
        out = {
            "th": th + dt * (0.11 * qv + 0.20 * forcing),
            "qv": qv + dt * (-0.06 * th + 0.08 * forcing),
            "h_diabatic": (0.55 * hdiag
                           + dt * (0.02 * th + 0.03 * qv + 0.10 * forcing)),
        }
        return out

    def vjp(self, step: int, state, external, dt: float, cotangent):
        self.vjp_steps.append(step)
        return _field_map(self._matrix(dt).T @ _vector(cotangent), state)

    def jvp(self, step: int, state, external, dt: float, direction):
        self.jvp_steps.append(step)
        return _field_map(self._matrix(dt) @ _vector(direction), state)


class QuadraticSlots:
    derivative_scope = "full_host"

    def __init__(self, slots):
        self.slots = slots
        self.calls: list[int] = []

    def __call__(self, step: int, state, *, need_gradient: bool):
        self.calls.append(step)
        if step not in self.slots:
            raise AssertionError(f"unexpected observation call at step {step}")
        weights, target, n_valid, signature = self.slots[step]
        residual = sum(float(weights[k]) * float(state[k].detach().reshape(()))
                       for k in FIELDS) - float(target)
        cost = 0.5 * residual * residual
        adjoint = None
        if need_gradient:
            adjoint = {k: _tensor(float(weights[k]) * residual) for k in FIELDS}
        return HostObservation(cost, adjoint, n_valid, signature)


def _quadratic_slots():
    return {
        1: ({"th": 0.8, "qv": -0.4, "h_diabatic": 0.7}, 238.0, 7, "slot-1-fixed"),
        3: ({"th": -0.3, "qv": 0.6, "h_diabatic": 0.9}, 241.0, 6, "slot-3-fixed"),
    }


def _supports(slots):
    return {step: FrozenSupport(n_valid, signature)
            for step, (_, _, n_valid, signature) in slots.items()}


def _manual_trajectory(x0, external, dt):
    a = _jacobian(dt).numpy()
    b = np.array([0.20 * dt, 0.08 * dt, 0.10 * dt], dtype=np.float64)
    x = np.asarray(x0, dtype=np.float64).copy()
    trajectory = [x.copy()]
    for entry in external:
        base = float(entry["base"].reshape(()))
        x = a @ x + b * base
        trajectory.append(x.copy())
    return trajectory, a


def _manual_cost_and_adjoint(x0, external, slots, dt):
    trajectory, a = _manual_trajectory(x0, external, dt)
    cost = 0.0
    obs_adj = {}
    for step, (weights_map, target, _n_valid, _signature) in slots.items():
        weights = np.asarray([weights_map[k] for k in FIELDS], dtype=np.float64)
        residual = float(weights @ trajectory[step] - target)
        cost += 0.5 * residual * residual
        obs_adj[step] = weights * residual
    lam = np.zeros(3, dtype=np.float64)
    for step in reversed(range(len(external) + 1)):
        if step in obs_adj:
            lam += obs_adj[step]
        if step:
            lam = a.T @ lam
    return cost, lam, trajectory


def test_coupled_window_matches_analytic_and_central_difference_with_memory_forcing():
    external = _external()
    external_before = [{k: v.clone() for k, v in f.items()} for f in external]
    slots = _quadratic_slots()
    observer = QuadraticSlots(slots)
    model = SmoothHost137()
    window = CoupledHostWindow(model, external, dt=DT, observe=observer,
                               supports=_supports(slots))
    x0 = _state()

    result = window.evaluate(x0, need_gradient=True)
    expected_cost, expected_gradient, expected_trajectory = _manual_cost_and_adjoint(
        [float(x0[k]) for k in FIELDS], external_before, slots, DT)
    assert result.cost == pytest.approx(expected_cost, rel=1e-12, abs=1e-12)
    for name, expected in zip(FIELDS, expected_gradient):
        assert float(result.adjoint_initial[name]) == pytest.approx(expected, rel=1e-12, abs=1e-12)
    assert len(result.checkpoints) == N_STEPS + 1
    for step, expected in enumerate(expected_trajectory):
        np.testing.assert_allclose(_vector(result.checkpoints[step]).numpy(), expected,
                                   rtol=1e-12, atol=1e-12)

    # Independent central differences of the total multi-slot objective.
    eps = 1.0e-6
    for index, name in enumerate(FIELDS):
        plus = [float(x0[k]) for k in FIELDS]
        minus = plus.copy()
        plus[index] += eps
        minus[index] -= eps
        j_plus = window.evaluate(dict(zip(FIELDS, map(_tensor, plus))),
                                 need_gradient=False).cost
        j_minus = window.evaluate(dict(zip(FIELDS, map(_tensor, minus))),
                                  need_gradient=False).cost
        finite_difference = (j_plus - j_minus) / (2.0 * eps)
        assert float(result.adjoint_initial[name]) == pytest.approx(
            finite_difference, rel=2e-7, abs=2e-8)

    # Every host step is replayed in increasing order; observations only occur
    # at the two declared times. H-memory affects both the next state and force.
    assert model.forward_steps[:N_STEPS] == list(range(N_STEPS))
    assert model.vjp_steps == list(reversed(range(N_STEPS)))
    assert observer.calls[:2] == [1, 3]
    assert model.forward_grad_enabled[:N_STEPS] == [False] * N_STEPS
    assert model.derived_forcing[0] == pytest.approx(0.3 + 0.5 * 0.15)
    assert not torch.equal(result.checkpoints[1]["h_diabatic"],
                           result.checkpoints[0]["h_diabatic"])
    for t, fields in enumerate(external):
        assert torch.equal(fields["base"], external_before[t]["base"])


class LinearTerminalSlot:
    derivative_scope = "full_host"

    def __init__(self, covector):
        self.covector = covector
        self.calls = []

    def __call__(self, step, state, *, need_gradient):
        self.calls.append(step)
        weight = _vector(self.covector)
        x = _vector(state)
        return HostObservation(float(torch.dot(weight, x)),
                               self.covector if need_gradient else None,
                               3, "terminal-linear")


def test_coupled_window_jvp_vjp_dot_product_and_trials_restart_from_x0():
    external = _external()
    model = SmoothHost137()
    observer = LinearTerminalSlot({k: _tensor(v) for k, v in
                                   zip(FIELDS, (0.4, -0.7, 1.2))})
    window = CoupledHostWindow(
        model, external, dt=DT, observe=observer,
        supports={N_STEPS: FrozenSupport(3, "terminal-linear")})
    x0 = _state()
    direction = {k: _tensor(v) for k, v in zip(FIELDS, (0.2, -0.3, 0.5))}

    result = window.evaluate(x0, need_gradient=True)
    final_state, final_tangent = window.jvp(x0, direction)
    lhs = sum(float(observer.covector[k] * final_tangent[k]) for k in FIELDS)
    rhs = sum(float(direction[k] * result.adjoint_initial[k]) for k in FIELDS)
    assert lhs == pytest.approx(rhs, rel=1e-12, abs=1e-12)
    assert model.jvp_steps == list(range(N_STEPS))
    assert observer.calls == [N_STEPS]

    # A new trial must begin at the supplied initial state, not the previous
    # trial's terminal checkpoint. Its state-derived forcing must be rebuilt.
    second = _state((300.1, 0.0065, 0.42))
    model.forward_steps.clear()
    model.forward_inputs.clear()
    model.derived_forcing.clear()
    result2 = window.evaluate(second, need_gradient=False)
    assert model.forward_steps[:N_STEPS] == list(range(N_STEPS))
    assert torch.equal(model.forward_inputs[0]["h_diabatic"], second["h_diabatic"])
    assert model.derived_forcing[0] == pytest.approx(
        float(external[0]["base"]) + 0.5 * float(second["h_diabatic"]))
    assert not torch.equal(final_state["h_diabatic"], result2.checkpoints[-1]["h_diabatic"])


def test_detached_state_derived_forcing_is_caught_by_finite_difference():
    external = _external()
    slots = _quadratic_slots()
    broken_model = SmoothHost137(detach_derived_forcing=True)
    window = CoupledHostWindow(broken_model, external, dt=DT,
                               observe=QuadraticSlots(slots), supports=_supports(slots))
    x0 = _state()
    result = window.evaluate(x0, need_gradient=True)
    eps = 1e-6
    q0 = float(x0["qv"])
    plus, minus = dict(x0), dict(x0)
    plus["qv"], minus["qv"] = _tensor(q0 + eps), _tensor(q0 - eps)
    fd = (window.evaluate(plus, need_gradient=False).cost
          - window.evaluate(minus, need_gradient=False).cost) / (2 * eps)
    assert abs(float(result.adjoint_initial["qv"]) - fd) > 1e-4


def test_input_external_schedule_is_snapshot_and_grad_controls_are_rejected():
    external = _external()
    saved_base = external[0]["base"].clone()
    slots = {N_STEPS: ({"th": 0.0, "qv": 0.0, "h_diabatic": 1.0}, 0.0, 1, "end")}
    model = SmoothHost137()
    window = CoupledHostWindow(model, external, dt=DT,
                               observe=QuadraticSlots(slots), supports=_supports(slots))
    # The constructor owns a detached value snapshot. Mutating the caller's
    # original schedule later cannot alter this experiment.
    external[0]["base"].add_(100.0)
    first = window.evaluate(_state(), need_gradient=False)
    second = window.evaluate(_state(), need_gradient=False)
    assert first.cost == second.cost
    assert model.derived_forcing[0] == pytest.approx(float(saved_base) + 0.5 * 0.15)

    with pytest.raises(ValueError, match="external|prescribed|control"):
        CoupledHostWindow(SmoothHost137(), [{"base": _tensor(1.0, requires_grad=True)}],
                          dt=DT, observe=QuadraticSlots(slots), supports=_supports(slots))


def test_gradient_requires_full_host_model_and_observation_before_any_step():
    slots = {0: ({"th": 1.0, "qv": 0.0, "h_diabatic": 0.0}, 0.0, 1, "start")}
    model = SmoothHost137()
    model.derivative_scope = "value_only"
    window = CoupledHostWindow(model, _external(), dt=DT,
                               observe=QuadraticSlots(slots), supports=_supports(slots))
    with pytest.raises(RuntimeError, match="full-host derivatives"):
        window.evaluate(_state(), need_gradient=True)
    assert model.forward_steps == []

    model = SmoothHost137()
    observer = QuadraticSlots(slots)
    observer.derivative_scope = "frozen_pressure"
    window = CoupledHostWindow(model, _external(), dt=DT,
                               observe=observer, supports=_supports(slots))
    with pytest.raises(RuntimeError, match="observation adjoint"):
        window.evaluate(_state(), need_gradient=True)
    assert model.forward_steps == []
    assert observer.calls == []


def test_host_checkpoint_requires_memory_field_and_valid_covector_shape():
    slots = {0: ({"th": 1.0, "qv": 0.0, "h_diabatic": 0.0}, 0.0, 1, "start")}
    model = SmoothHost137()
    window = CoupledHostWindow(model, _external(), dt=DT,
                               observe=QuadraticSlots(slots), supports=_supports(slots))
    with pytest.raises(ValueError, match="incomplete host checkpoint.*h_diabatic"):
        window.evaluate({"th": _tensor(1.0), "qv": _tensor(0.01)}, need_gradient=False)
    assert model.forward_steps == []

    class BadCovector(QuadraticSlots):
        def __call__(self, step, state, *, need_gradient):
            self.calls.append(step)
            return HostObservation(0.0,
                                  {"th": _tensor(1.0), "qv": torch.ones(2, dtype=torch.float64),
                                   "h_diabatic": _tensor(0.0)} if need_gradient else None,
                                  1, "start")

    model = SmoothHost137()
    window = CoupledHostWindow(model, _external(), dt=DT,
                               observe=BadCovector(slots), supports=_supports(slots))
    with pytest.raises(ValueError, match="observation_adjoint.*shape/dtype/device"):
        window.evaluate(_state(), need_gradient=True)
    assert model.forward_steps == []


def test_declared_observation_calls_and_frozen_support_are_enforced():
    slots = {0: ({"th": 1.0, "qv": 0.0, "h_diabatic": 0.0}, 0.0, 2, "frozen-0"),
             2: ({"th": 0.0, "qv": 1.0, "h_diabatic": 0.0}, 0.0, 3, "frozen-2")}

    class MissingSlot(QuadraticSlots):
        def __call__(self, step, state, *, need_gradient):
            if step == 2:
                self.calls.append(step)
                return None
            return super().__call__(step, state, need_gradient=need_gradient)

    observer = MissingSlot(slots)
    model = SmoothHost137()
    window = CoupledHostWindow(model, _external()[:2], dt=DT, observe=observer,
                               supports=_supports(slots))
    with pytest.raises(TypeError, match="declared observation slot"):
        window.evaluate(_state(), need_gradient=False)
    assert observer.calls == [0, 2]
    assert model.forward_steps == [0, 1]

    class DriftedSlot(QuadraticSlots):
        def __call__(self, step, state, *, need_gradient):
            result = super().__call__(step, state, need_gradient=need_gradient)
            if step == 0:
                return HostObservation(result.cost, result.adjoint, result.n_valid,
                                      "changed-signature")
            return result

    observer = DriftedSlot(slots)
    model = SmoothHost137()
    window = CoupledHostWindow(model, _external()[:2], dt=DT, observe=observer,
                               supports=_supports(slots))
    with pytest.raises(RuntimeError, match="support/signature changed"):
        window.evaluate(_state(), need_gradient=False)
    assert model.forward_steps == []
    assert observer.calls == [0]


def test_finite_endpoint_and_initial_cotangents_cannot_overflow_at_final_sum():
    class IdentityHost137:
        mp_physics = 137
        derivative_scope = "full_host"
        required_state_fields = frozenset(FIELDS)

        def __init__(self):
            self.vjp_steps = []

        def forward(self, step, state, external, dt):
            return {name: value.clone() for name, value in state.items()}

        def vjp(self, step, state, external, dt, cotangent):
            self.vjp_steps.append(step)
            return {name: value.clone() for name, value in cotangent.items()}

        def jvp(self, step, state, external, dt, direction):
            return {name: value.clone() for name, value in direction.items()}

    class HugeFiniteEndpointSlots:
        derivative_scope = "full_host"

        def __call__(self, step, state, *, need_gradient):
            return HostObservation(
                cost=1.0,
                adjoint=({name: _tensor(1.0e308) for name in FIELDS}
                         if need_gradient else None),
                n_valid=1,
                signature=f"finite-slot-{step}",
            )

    model = IdentityHost137()
    window = CoupledHostWindow(
        model,
        external_steps=[{"base": _tensor(0.0)}],
        dt=DT,
        observe=HugeFiniteEndpointSlots(),
        supports={0: FrozenSupport(1, "finite-slot-0"),
                  1: FrozenSupport(1, "finite-slot-1")},
    )

    # Both observation cotangents are finite individually and the identity
    # transition preserves the terminal one. Their final accumulation at t=0
    # overflows float64, which must raise instead of returning an Inf gradient.
    with pytest.raises(ValueError, match="host field th must be finite floating point"):
        window.evaluate(_state(), need_gradient=True)
    assert model.vjp_steps == [0]
