"""[DA Phase 4] Assimilation-window driver — checkpoint/recompute adjoint
(kdm6ad+da.md §8.3/§8.4) on the fp64 DA adjoint forward (§0.1.A).

Forward sweep (value-only, fp64): store a detached checkpoint per step and the
observation adjoints ∂J_obs/∂x_t supplied by a pluggable callback (the
RTTOV/GK2A bridge eventually; any covector source for now).

Backward sweep: re-build a LOCAL one-step graph from each checkpoint (fresh
requires_grad leaves — never InferenceMode tensors, §8.3), pull the running
adjoint through ``Handle.vjp``, close the handle, and accumulate the
observation adjoint of the step. No full-window graph is ever retained.

Cloud-active gate (§3): on steps where neither the model state nor the
observations are cloud-active, the KDM6AD VJP is SKIPPED and the adjoint passes
through unchanged (the scheme is a near-no-op there; treating J^T as identity
is the documented gate semantics). The gate never silently drops an
observation adjoint — obs_adj is accumulated regardless.

The driver is observation-operator agnostic: ``obs_adjoint(t, x_t)`` returns a
``State`` covector (already including any RTTOV-K / bridge VJP) or ``None``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

import torch

from .state import State, Forcing, map_state, zeros_like_state
from .runtime import kdm6_step, make_parameters, Parameters, _validate_state_shapes


def _to_f64(s):
    return type(s)(*(f.detach().to(torch.float64) for f in s))


def _add_states(a: State, b: State) -> State:
    return State(*(x + y for x, y in zip(a, b)))


def hydro_sum(s: State) -> torch.Tensor:
    """Total hydrometeor mass q_c+q_r+q_i+q_s+q_g (§3.1)."""
    return s.qc + s.qr + s.qi + s.qs + s.qg


def model_cloud_active(s: State, *, min_total_hydro: float = 1.0e-12) -> bool:
    """§3.1 model-side gate (sum form; the column-fraction refinement is a
    driver-config concern once real tiles arrive)."""
    with torch.no_grad():
        return bool(hydro_sum(s).sum().item() > min_total_hydro)


@dataclass
class WindowConfig:
    dt: float
    params: Parameters | None = None
    xland: torch.Tensor | None = None
    ncmin_land: float = 0.0
    ncmin_sea: float = 0.0
    # §3 cloud-active gate. obs_active is owned by the obs side; the driver
    # combines `model_active or obs_active(t)` per §3.3.
    use_cloud_gate: bool = False
    min_total_hydro: float = 1.0e-12
    obs_active: Callable[[int], bool] | None = None
    # §8.2 hydrometeor-centric adjoint (None = all fields)
    active_fields: tuple[str, ...] | None = None
    # §5.1 weak-constraint post-physics increments: x_{t+1} = M(x_t) + η_t.
    # length-T sequence of State increments (or None). Driver-level — no kernel
    # change, so the operational bitwise lock is untouched. The returned
    # grad_eta[t] = ∂J/∂η_t is simply the running adjoint at x_{t+1}-space
    # (∂x_{t+1}/∂η_t = I) — the cheapest control the design defines.
    eta: "Sequence[State] | None" = None


@dataclass
class WindowResult:
    adj_x0: State                      # ∂J/∂x_0  (the window adjoint)
    checkpoints: list[State]           # fp64 detached x_t, t = 0..T-1 (entries)
    state_final: State                 # x_T (fp64, detached)
    vjp_steps: list[int] = field(default_factory=list)   # steps whose VJP ran
    skipped_steps: list[int] = field(default_factory=list)  # gate-skipped
    grad_eta: list[State] | None = None    # ∂J/∂η_t per step (§5.1), if eta given


def run_da_window(
    x0: State,
    forcings: Sequence[Forcing],
    obs_adjoint: Callable[[int, State], State | None],
    config: WindowConfig,
) -> WindowResult:
    """Run the §8.4 forward(value-only, fp64-checkpoint) + backward(local-graph
    recompute + vjp) sweeps.

    Parameters
    ----------
    x0 : State
        window-initial state (any dtype; cast to fp64 — §0.1.A DA default).
    forcings : sequence of Forcing, length T
        per-step forcing (cast to fp64).
    obs_adjoint : callable (t, x_t) -> State | None
        observation adjoint ∂J_obs/∂x_t at time index t = 0..T, evaluated on
        the fp64 trajectory (x_t = state BEFORE step t for t<T; x_T = final).
        Return None when there is no observation at t.
    config : WindowConfig

    Returns
    -------
    WindowResult — adj_x0 = Σ_t M_0^T ... M_{t-1}^T (∂J_obs/∂x_t).
    """
    params = config.params if config.params is not None else make_parameters()
    T = len(forcings)

    # ── forward sweep: fp64 value-only + checkpoints + obs adjoints ─────────
    x = _to_f64(x0)
    if config.eta is not None:
        if len(config.eta) != T:
            raise ValueError(f"eta length {len(config.eta)} != window length {T}")
        for t, e in enumerate(config.eta):
            _validate_state_shapes(e, x, arg=f"eta[{t}]", ref_name="state")
    f64_forcings = [_to_f64(f) for f in forcings]
    checkpoints: list[State] = []
    obs_adj: dict[int, State] = {}

    def _grab_obs(t: int, xt: State) -> None:
        u = obs_adjoint(t, xt)
        if u is not None:
            # broadcastable-but-wrong covector shapes would silently corrupt the
            # adjoint accumulation (_add_states broadcasts) — same F1-SHAPE class
            # as Handle.vjp/jvp; reject loudly before use (Codex stop-review).
            _validate_state_shapes(u, xt, arg=f"obs_adjoint(t={t})", ref_name="x_t")
            obs_adj[t] = State(*(g.detach().to(torch.float64) for g in u))

    for t in range(T):
        checkpoints.append(State(*(f.detach().clone() for f in x)))
        _grab_obs(t, checkpoints[t])
        out, h = kdm6_step(x, f64_forcings[t], params, config.dt,
                           value_only=True, xland=config.xland,
                           ncmin_land=config.ncmin_land, ncmin_sea=config.ncmin_sea)
        h.close()
        x = State(*(f.detach() for f in out))
        if config.eta is not None:                      # §5.1 x_{t+1} = M(x_t) + η_t
            x = _add_states(x, _to_f64(config.eta[t]))
    state_final = x
    _grab_obs(T, state_final)

    # ── backward sweep: local-graph recompute + vjp (§8.4) ──────────────────
    adj = obs_adj.get(T, zeros_like_state(state_final))
    vjp_steps: list[int] = []
    skipped: list[int] = []

    grad_eta: list[State] | None = [None] * T if config.eta is not None else None

    for t in reversed(range(T)):
        if grad_eta is not None:
            # ∂J/∂η_t = ∂J/∂x_{t+1} — the running adjoint right now (identity path).
            grad_eta[t] = State(*(g.clone() for g in adj))
        gate_on = True
        if config.use_cloud_gate:
            m_act = model_cloud_active(checkpoints[t],
                                       min_total_hydro=config.min_total_hydro)
            o_act = bool(config.obs_active(t)) if config.obs_active else False
            gate_on = m_act or o_act
        if gate_on:
            # fresh requires_grad leaves from the detached checkpoint — a local
            # graph OUTSIDE InferenceMode (§8.3); one step, then vjp, then close.
            leaves = State(*(f.detach().clone().requires_grad_(True)
                             for f in checkpoints[t]))
            _, handle = kdm6_step(leaves, f64_forcings[t], params, config.dt,
                                  value_only=False, xland=config.xland,
                                  ncmin_land=config.ncmin_land,
                                  ncmin_sea=config.ncmin_sea)
            adj = handle.vjp(adj, active_fields=config.active_fields)
            handle.close()
            vjp_steps.append(t)
        else:
            # clear-sky no-op step: J^T ≈ I — adjoint passes through (§3.3).
            skipped.append(t)
        if t in obs_adj:
            adj = _add_states(adj, obs_adj[t])

    return WindowResult(adj_x0=adj, checkpoints=checkpoints,
                        state_final=state_final,
                        vjp_steps=vjp_steps, skipped_steps=skipped,
                        grad_eta=grad_eta)
