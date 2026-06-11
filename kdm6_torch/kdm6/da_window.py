"""[DA Phase 4] Assimilation-window driver — checkpoint/recompute adjoint
(kdm6ad+da.md §8.3/§8.4) on the fp64 DA adjoint forward (§0.1.A).

Forward sweep (value-only, fp64): store a detached checkpoint per step and the
observation adjoints ∂J_obs/∂x_t supplied by a pluggable callback (the
RTTOV/GK2A bridge eventually; any covector source for now).

Backward sweep: re-build a LOCAL one-step graph from each checkpoint (fresh
requires_grad leaves — never InferenceMode tensors, §8.3), pull the running
adjoint through ``Handle.vjp``, close the handle, and accumulate the
observation adjoint of the step. No full-window graph is ever retained.

Cloud-active gate (§3): a step's VJP may be skipped (adjoint passes through
as identity) ONLY when J = I is PROVABLE on a neighborhood, not merely when
the VALUE is unchanged — a value-level no-op does NOT imply an identity
Jacobian (counterexample: exactly-saturated clear air has pcond = 0 with
∂pcond/∂qv != 0; Codex stop-review ×2). The provable condition implemented:
  (a) every hydrometeor field is exactly zero (the max(0,·) clamps sit in
      their flat interiors),
  (b) the column is STRICTLY sub-saturated by a margin (qv < (1-m)·qs(T,p)),
      so the condensation/activation gates are strictly off on a
      neighborhood, and
  (c) the forward step verifiably returned the state unchanged (all fields
      equal; th within the Exner round-trip ULP).
Under (a)+(b)+(c), M ≡ Id on an open neighborhood of x_t, hence J^T = I
EXACTLY — the skip is not an approximation. Marginal cases (saturation within
the margin, any nonzero hydrometeor) always take the real VJP. obs_active
still forces the VJP per §3.3 OR-semantics; obs_adj is accumulated regardless.

The driver is observation-operator agnostic: ``obs_adjoint(t, x_t)`` returns a
``State`` covector (already including any RTTOV-K / bridge VJP) or ``None``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

import torch

from .state import State, Forcing, map_state, zeros_like_state
from .runtime import kdm6_step, make_parameters, Parameters, _validate_state_shapes
from .thermo import compute_qs_water, default_thermo_params


def _to_f64(s):
    return type(s)(*(f.detach().to(torch.float64) for f in s))


def _add_states(a: State, b: State) -> State:
    return State(*(x + y for x, y in zip(a, b)))


def hydro_sum(s: State) -> torch.Tensor:
    """Total hydrometeor mass q_c+q_r+q_i+q_s+q_g (§3.1)."""
    return s.qc + s.qr + s.qi + s.qs + s.qg


def model_cloud_active(s: State, *, min_total_hydro: float = 1.0e-12) -> bool:
    """§3.1 model-side ENTRY heuristic (hydrometeor presence). NOTE: this alone
    is NOT a safe skip condition — a clear-but-supersaturated column has zero
    hydrometeors yet condenses. The driver skips only on a VERIFIED no-op
    (see step_is_noop); this heuristic remains exported for §3.1 diagnostics."""
    with torch.no_grad():
        return bool(hydro_sum(s).sum().item() > min_total_hydro)


def column_strictly_subsaturated(s: State, f: Forcing,
                                 *, margin: float = 1.0e-3) -> bool:
    """True iff qv < (1 - margin)·qs_water(T, p) EVERYWHERE — the condensation
    and CCN-activation gates are then strictly off on a neighborhood of s,
    which (with zero hydrometeors) makes M locally the identity. The margin
    keeps the exactly-saturated counterexample (value-noop with J != I) out."""
    with torch.no_grad():
        t = s.th * f.pii
        qs = compute_qs_water(t, f.p, params=default_thermo_params())
        return bool((s.qv < (1.0 - margin) * qs).all().item())


def hydro_exactly_zero(s: State) -> bool:
    """True iff every hydrometeor mass AND number field is exactly zero —
    the positivity clamps sit in their flat interiors (locally constant)."""
    with torch.no_grad():
        for fld in (s.qc, s.qr, s.qi, s.qs, s.qg, s.nc, s.ni, s.nr, s.bg):
            if (fld != 0).any():
                return False
    return True


def step_is_noop(x_in: State, x_out: State, *, th_rtol: float = 1.0e-12) -> bool:
    """True iff the forward step left the state unchanged: every field equal,
    except th which may wobble by the Exner round-trip (t = th*pii; th = t/pii)
    — a ~1-ULP value change whose Jacobian is still exactly the identity.
    This is the SAFE skip condition for the cloud gate: it is measured on the
    actual forward output, so a supersaturated clear column (condensation
    onset, J^T != I) can never be skipped."""
    with torch.no_grad():
        for name, a, b in zip(State._fields, x_in, x_out):
            if name == "th":
                if not torch.allclose(a, b, rtol=th_rtol, atol=0.0):
                    return False
            elif not torch.equal(a, b):
                return False
    return True


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
    min_total_hydro: float = 1.0e-12     # §3.1 diagnostic threshold (not the skip condition)
    subsat_margin: float = 1.0e-3        # strict sub-saturation margin for the provable skip
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

    step_noop: list[bool] = []
    for t in range(T):
        checkpoints.append(State(*(f.detach().clone() for f in x)))
        _grab_obs(t, checkpoints[t])
        out, h = kdm6_step(x, f64_forcings[t], params, config.dt,
                           value_only=True, xland=config.xland,
                           ncmin_land=config.ncmin_land, ncmin_sea=config.ncmin_sea)
        h.close()
        out_detached = State(*(f.detach() for f in out))
        step_noop.append(
            step_is_noop(x, out_detached)
            and hydro_exactly_zero(x)
            and column_strictly_subsaturated(x, f64_forcings[t],
                                             margin=config.subsat_margin))
        x = out_detached
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
            # skip ONLY when J = I is provable on a neighborhood: verified
            # value-noop AND all hydrometeors exactly zero AND strictly
            # sub-saturated (see module docstring — value-noop alone does NOT
            # imply an identity Jacobian). obs_active still forces the VJP.
            o_act = bool(config.obs_active(t)) if config.obs_active else False
            gate_on = (not step_noop[t]) or o_act
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
            # VERIFIED no-op step: J^T = I exactly — adjoint passes through (§3.3).
            skipped.append(t)
        if t in obs_adj:
            adj = _add_states(adj, obs_adj[t])

    return WindowResult(adj_x0=adj, checkpoints=checkpoints,
                        state_final=state_final,
                        vjp_steps=vjp_steps, skipped_steps=skipped,
                        grad_eta=grad_eta)
