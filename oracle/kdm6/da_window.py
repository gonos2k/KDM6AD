"""[DA Phase 4] Assimilation-window driver — checkpoint/recompute adjoint
(kdm6ad+da.md §8.3/§8.4) on the fp64 DA adjoint forward (§0.1.A).

Forward sweep (value-only, fp64): store a detached checkpoint per step and the
observation adjoints ∂J_obs/∂x_t supplied by a pluggable callback (the
RTTOV/GK2A bridge eventually; any covector source for now).

Backward sweep: re-build a LOCAL one-step graph from each checkpoint (fresh
requires_grad leaves — never InferenceMode tensors, §8.3), pull the running
adjoint through ``Handle.vjp``, close the handle, and accumulate the
observation adjoint of the step. No full-window graph is ever retained.

Cloud-active gate (§3) — VJP-skip REMOVED (three adversarial rounds, Codex):
the driver always runs the real per-step VJP. The attempted identity-skip
conditions each had a counterexample:
  1. entry-hydrometeor heuristic  → supersaturated clear air condenses
     (J != I with zero hydrometeors);
  2. measured value-noop          → exactly-saturated air has pcond = 0 with
     ∂pcond/∂qv != 0 (value fixed point, non-identity Jacobian);
  3. value-noop + hydro==0 + strict sub-saturation margin → zero-hydrometeor
     states sit EXACTLY ON the clamp/where kinks (e.g. the sediment vt gate
     fires for ANY qi = +ε with no protective threshold), so the AD Jacobian
     at those points is a SUBGRADIENT, not the identity.
Conclusion: there is no cheaply-provable J = I condition at the AD level;
correctness wins over the optimization. `use_cloud_gate`/`model_cloud_active`
remain as §3 DIAGNOSTICS (and for obs-side loss gating — not evaluating
cloud losses on clear pixels is the obs operator's business); they no longer
alter the adjoint path. step_is_noop / column_strictly_subsaturated /
hydro_exactly_zero are kept as exported diagnostics for the same reason.

The driver is observation-operator agnostic: ``obs_adjoint(t, x_t)`` returns a
``State`` covector (already including any RTTOV-K / bridge VJP) or ``None``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

import torch

from .state import State, Forcing, map_state, zeros_like_state
from .runtime import kdm6_step, make_parameters, Parameters, _validate_state_shapes
from .thermo import compute_qs_water, compute_xl, compute_cpm, default_thermo_params


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
    # [G4] True → backward 스윕에서 스텝별 ∂⟨M(x_t,θ), λ_{t+1}⟩/∂θ 를 누적해
    # WindowResult.grad_params 로 반환 (config.params 에 live leaf 필요).
    param_grads: bool = False
    # §5.2 PRE-state increments: the step consumes x_t' = x_t + η_pre_t.
    # ∂J/∂η_pre_t = ∂J/∂x_t' = the OUTPUT of step-t's vjp (before adding
    # obs_adj[t]) — returned as grad_eta_pre. Driver-level, kernel untouched.
    eta_pre: "Sequence[State] | None" = None
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
    skipped_steps: list[int] = field(default_factory=list)  # DIAGNOSTIC: value-inert steps (VJP still ran)
    grad_eta: list[State] | None = None    # ∂J/∂η_t per step (§5.1), if eta given
    grad_eta_pre: list[State] | None = None  # ∂J/∂η_pre_t per step (§5.2)
    grad_params: "dict[str, torch.Tensor] | None" = None  # [G4] Σ_t 파라미터 수반


def collect_window_trajectory(x0: State, forcings: Sequence[Forcing],
                              config: WindowConfig,
                              wanted_times: "set[int] | Sequence[int]",
                              ) -> "dict[int, State]":
    """전방-전용 궤적 수집기 — run_da_window의 forward 의미론(η/η_pre 적용,
    관측 시점 규약: 슬롯 상태 = η_pre 적용 **전**의 x_t, t=T는 최종 상태)을
    그대로 미러하되 backward 스윕이 없다 (적대 검토: 동결-mask 프로브가
    run_da_window를 쓰면 전 스텝 VJP 비용을 낸다 — 수집만 하는 데 부당).
    run_da_window 프로브와의 bitwise 동일성은 게이트 테스트로 고정.
    """
    params = config.params if config.params is not None else make_parameters()
    T = len(forcings)
    wanted = set(int(w) for w in wanted_times)
    x = _to_f64(x0)
    if config.eta is not None:
        if len(config.eta) != T:
            raise ValueError(f"eta length {len(config.eta)} != window length {T}")
        for t, e in enumerate(config.eta):              # shape 가드 — run_da_window와
            _validate_state_shapes(e, x, arg=f"eta[{t}]", ref_name="state")
    if config.eta_pre is not None:
        if len(config.eta_pre) != T:
            raise ValueError(f"eta_pre length {len(config.eta_pre)} != window length {T}")
        for t, e in enumerate(config.eta_pre):          # 동일 (broadcast 침묵 오염 차단)
            _validate_state_shapes(e, x, arg=f"eta_pre[{t}]", ref_name="state")
    f64_forcings = [_to_f64(f) for f in forcings]
    out_traj: dict[int, State] = {}
    for t in range(T):
        if t in wanted:
            out_traj[t] = State(*(f.detach().clone() for f in x))
        if config.eta_pre is not None:
            x = _add_states(x, _to_f64(config.eta_pre[t]))
        out, h = kdm6_step(x, f64_forcings[t], params, config.dt,
                           value_only=True, xland=config.xland,
                           ncmin_land=config.ncmin_land, ncmin_sea=config.ncmin_sea)
        h.close()
        x = State(*(f.detach() for f in out))
        if config.eta is not None:
            x = _add_states(x, _to_f64(config.eta[t]))
    if T in wanted:
        out_traj[T] = State(*(f.detach().clone() for f in x))
    missing = wanted - set(out_traj)
    if missing:
        raise ValueError(f"wanted times {sorted(missing)} outside window [0, {T}]")
    return out_traj


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
    if config.eta_pre is not None:
        if len(config.eta_pre) != T:
            raise ValueError(f"eta_pre length {len(config.eta_pre)} != window length {T}")
        for t, e in enumerate(config.eta_pre):
            _validate_state_shapes(e, x, arg=f"eta_pre[{t}]", ref_name="state")
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
        xt = State(*(f.detach().clone() for f in x))
        _grab_obs(t, xt)                                        # obs sees x_t (pre η_pre)
        if config.eta_pre is not None:                          # §5.2 x_t' = x_t + η_pre_t
            x = _add_states(x, _to_f64(config.eta_pre[t]))
            checkpoints.append(State(*(f.detach().clone() for f in x)))  # checkpoint x_t'
        else:
            checkpoints.append(xt)   # reuse — one clone per step (review DP-5)
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
    grad_eta_pre: list[State] | None = [None] * T if config.eta_pre is not None else None
    grad_params_acc: "dict[str, torch.Tensor] | None" = None

    for t in reversed(range(T)):
        if grad_eta is not None:
            # ∂J/∂η_t = ∂J/∂x_{t+1} — the running adjoint right now (identity path).
            grad_eta[t] = State(*(g.clone() for g in adj))
        # ALWAYS run the real per-step VJP (no identity-skip — see module
        # docstring: zero-hydrometeor states sit on clamp/where kinks, so the
        # AD Jacobian is a subgradient there, not the identity). The gate
        # fields below are diagnostics only.
        if config.use_cloud_gate and step_noop[t]:
            skipped.append(t)   # diagnostic: "provably value-inert step" tally
        leaves = State(*(f.detach().clone().requires_grad_(True)
                         for f in checkpoints[t]))
        _, handle = kdm6_step(leaves, f64_forcings[t], params, config.dt,
                              value_only=False, xland=config.xland,
                              ncmin_land=config.ncmin_land,
                              ncmin_sea=config.ncmin_sea)
        if config.param_grads:
            # [G4] 파라미터 수반 기여는 이 스텝의 INCOMING adjoint(λ_{t+1})와의
            # 내적으로 — state vjp(그래프 해제) *이전*에 계산해야 한다.
            pg = handle.param_vjp(adj)
            if grad_params_acc is None:
                grad_params_acc = {k: g.clone() for k, g in pg.items()}
            else:
                for k, g in pg.items():
                    grad_params_acc[k] = grad_params_acc[k] + g
        adj = handle.vjp(adj, active_fields=config.active_fields)
        handle.close()
        vjp_steps.append(t)
        if grad_eta_pre is not None:
            # ∂J/∂η_pre_t = ∂J/∂x_t' — the vjp output, before obs_adj[t]
            # (the obs at t reads x_t, NOT x_t' = x_t + η_pre).
            grad_eta_pre[t] = State(*(g.clone() for g in adj))
        if t in obs_adj:
            adj = _add_states(adj, obs_adj[t])

    return WindowResult(adj_x0=adj, checkpoints=checkpoints,
                        state_final=state_final,
                        vjp_steps=vjp_steps, skipped_steps=skipped,
                        grad_eta=grad_eta, grad_eta_pre=grad_eta_pre,
                        grad_params=grad_params_acc)


# ── §5.4 partition control: conserve-by-construction ────────────────────────

def apply_partition_liq2ice(state: State, forcing: Forcing,
                            delta: torch.Tensor) -> State:
    """Δ_liquid→ice partition control (kdm6ad+da.md §5.3/§5.4):

        qc' = qc − Δ;  qi' = qi + Δ;  θ' = θ + (L_f(T)/(cpm·π))·Δ

    Mass AND latent heating conserved BY CONSTRUCTION (no soft penalty). The
    latent heat uses the FREEZE-branch constant L_f(T) = xls − xl(T) — KDM6's
    per-process convention (melt terms use xlf0; freeze terms use xls−xl(T) —
    the §37 branch-conditional-constant lesson). Differentiable: pure tensor
    ops; Δ is the control leaf. Positivity of qc' is the optimizer's business
    (couple with J_pos or a bounded parameterization); this operator itself
    does not clamp — a clamp here would put the control on a kink.

    NOTE (operational bitwise lock): this is a DRIVER-level operator applied
    BETWEEN steps on the fp64 DA path; the operational mp137 forward never
    sees these ops (design §5.3 partition_control_enabled semantics).
    """
    if delta.shape != state.qc.shape:
        raise ValueError(f"delta shape {tuple(delta.shape)} != state shape "
                         f"{tuple(state.qc.shape)}")
    tp = default_thermo_params()
    t = state.th * forcing.pii
    xl = compute_xl(t, params=tp)              # T-dependent vaporization heat
    lf = tp.xls - xl                           # freeze-branch latent heat (§37)
    cpm = compute_cpm(state.qv, params=tp)
    dth = lf / (cpm * forcing.pii) * delta
    return state._replace(
        qc=state.qc - delta,
        qi=state.qi + delta,
        th=state.th + dth,
    )


def apply_partition_cloud2rain(state: State, delta: torch.Tensor) -> State:
    """Δ_cloud→precip(rain) partition control (design §5.3 list): same-phase
    liquid→liquid — mass-only move, NO latent-heat term. Conserving by
    construction; no clamp (positivity belongs to the optimizer, §5.4)."""
    if delta.shape != state.qc.shape:
        raise ValueError(f"delta shape {tuple(delta.shape)} != state shape "
                         f"{tuple(state.qc.shape)}")
    return state._replace(qc=state.qc - delta, qr=state.qr + delta)


def apply_partition_snow2graupel(state: State, delta: torch.Tensor) -> State:
    """Δ_snow→graupel partition control (design §5.3 list): same-phase
    ice→ice — mass-only move, NO latent-heat term. The graupel rime-mass
    bookkeeping (bg) is deliberately untouched: converted snow carries no
    rime by definition; the bg/qg density proxy shifts accordingly."""
    if delta.shape != state.qs.shape:
        raise ValueError(f"delta shape {tuple(delta.shape)} != state shape "
                         f"{tuple(state.qs.shape)}")
    return state._replace(qs=state.qs - delta, qg=state.qg + delta)


def apply_partition_ice2liq(state: State, forcing: Forcing,
                            delta: torch.Tensor) -> State:
    """Δ_ice→liquid (melting-direction) partition control.

    SEPARATE operator from apply_partition_liq2ice rather than a sign branch:
    KDM6's per-process latent-heat convention is BRANCH-CONDITIONAL (§37 —
    melt terms use the constant xlf0, freeze terms use xls−xl(T)), and a
    torch.where on sign(Δ) would put a kink exactly at the optimizer's Δ=0
    starting point. Use this operator for melt-direction increments:

        qi' = qi − Δ;  qc' = qc + Δ;  θ' = θ − (xlf0/(cpm·π))·Δ
    """
    if delta.shape != state.qi.shape:
        raise ValueError(f"delta shape {tuple(delta.shape)} != state shape "
                         f"{tuple(state.qi.shape)}")
    from .melt_freeze import DEFAULT_XLF   # xlf0 = 3.5e5 (Fortran F:1275 melt branch)
    tp = default_thermo_params()
    cpm = compute_cpm(state.qv, params=tp)
    dth = DEFAULT_XLF / (cpm * forcing.pii) * delta
    return state._replace(
        qi=state.qi - delta,
        qc=state.qc + delta,
        th=state.th - dth,
    )
