"""[DA Phase 4] gates for the assimilation-window driver (kdm6ad+da.md §8.4, §3).

The load-bearing gate: the checkpoint/recompute adjoint must equal the
full-window-graph autograd gradient EXACTLY (fp64; the forward-determinism
gate guarantees recompute hits the same point bitwise, so the two adjoints are
the same linearization).
"""
from __future__ import annotations

import pytest
import torch

from kdm6.state import State, Forcing, state_dot, zeros_like_state
from kdm6.runtime import kdm6_step, kdm6_fn, make_parameters
from kdm6.da_window import WindowConfig, run_da_window, model_cloud_active

DT = 20.0
T_STEPS = 3


def _t2(a, b, rg=False):
    t = torch.tensor([[a, b]], dtype=torch.float64)
    return t.requires_grad_(True) if rg else t


def _mk_state(rg=False):
    return State(
        th=_t2(296.8, 282.4, rg), qv=_t2(1.40e-2, 2.0e-3, rg),
        qc=_t2(1.0e-3, 5.0e-4, rg), qr=_t2(1.0e-4, 1.0e-5, rg),
        qi=_t2(0.0, 1.0e-6, rg), qs=_t2(0.0, 5.0e-5, rg),
        qg=_t2(0.0, 1.0e-5, rg), nccn=_t2(1.0e9, 1.0e9, rg),
        nc=_t2(1.0e8, 1.0e8, rg), ni=_t2(0.0, 1.0e8, rg),
        nr=_t2(1.0e4, 1.0e3, rg), bg=_t2(0.0, 0.0, rg),
    )


def _mk_forcing():
    return Forcing(rho=_t2(1.089, 0.9567), pii=_t2(0.9704, 0.9031),
                   p=_t2(9.0e4, 7.0e4), delz=_t2(500.0, 500.0))


def _unit_state(seed):
    g = torch.Generator().manual_seed(seed)
    return State(*(torch.randn((1, 2), generator=g, dtype=torch.float64)
                   for _ in State._fields))


def _full_graph_adjoint(x0_leaves: State, forcings, obs_us: dict[int, State]):
    """Reference: build the WHOLE window graph once; J = Σ_t <x_t, u_t>."""
    params = make_parameters()
    x = x0_leaves
    loss = torch.zeros((), dtype=torch.float64)
    if 0 in obs_us:
        loss = loss + state_dot(x, obs_us[0])
    for t, f in enumerate(forcings):
        x = kdm6_fn(x, f, params, DT)
        if (t + 1) in obs_us:
            loss = loss + state_dot(x, obs_us[t + 1])
    grads = torch.autograd.grad(loss, tuple(x0_leaves), allow_unused=True,
                                materialize_grads=True)
    return State(*grads)


def test_window_single_terminal_obs_matches_full_graph():
    """One observation at t=T: driver adjoint == full-graph gradient exactly."""
    forcings = [_mk_forcing() for _ in range(T_STEPS)]
    u_T = _unit_state(seed=61)
    obs = {T_STEPS: u_T}

    res = run_da_window(_mk_state(), forcings,
                        lambda t, x: obs.get(t), WindowConfig(dt=DT))
    ref = _full_graph_adjoint(_mk_state(rg=True), forcings, obs)

    for name, a, b in zip(State._fields, res.adj_x0, ref):
        assert torch.equal(a, b), f"window adjoint != full graph in {name}"
    assert res.vjp_steps == [2, 1, 0] and not res.skipped_steps


def test_window_multi_obs_accumulation_matches_full_graph():
    """Observations at several times: J = Σ_t <x_t, u_t> — exact equality."""
    forcings = [_mk_forcing() for _ in range(T_STEPS)]
    obs = {0: _unit_state(67), 2: _unit_state(71), T_STEPS: _unit_state(73)}

    res = run_da_window(_mk_state(), forcings,
                        lambda t, x: obs.get(t), WindowConfig(dt=DT))
    ref = _full_graph_adjoint(_mk_state(rg=True), forcings, obs)

    for name, a, b in zip(State._fields, res.adj_x0, ref):
        assert torch.equal(a, b), f"multi-obs adjoint != full graph in {name}"


def test_window_active_field_mask_threads_through():
    """active_fields restricts each per-step vjp to the control subspace —
    equivalent to a full-graph reference whose per-step adjoints are projected.
    (Single-step window keeps the projector semantics exact and simple.)"""
    forcings = [_mk_forcing()]
    active = ("qc", "qr", "qi", "qs", "qg", "nc", "ni", "nr")
    u = _unit_state(79)
    obs = {1: u}

    res = run_da_window(_mk_state(), forcings, lambda t, x: obs.get(t),
                        WindowConfig(dt=DT, active_fields=active))

    # reference: P · J^T u on a single step
    leaves = _mk_state(rg=True)
    out, handle = kdm6_step(leaves, forcings[0], dt=DT)
    ref = handle.vjp(u, active_fields=active)
    handle.close()
    for name, a, b in zip(State._fields, res.adj_x0, ref):
        assert torch.equal(a, b), f"masked window adjoint mismatch in {name}"
    for name, g in zip(State._fields, res.adj_x0):
        if name not in active:
            assert torch.all(g == 0), f"inactive field {name} leaked"


def _clear_sky_state():
    """Sub-saturated, hydrometeor-free column — the microphysics no-op regime."""
    return State(
        th=_t2(300.0, 295.0), qv=_t2(2.0e-3, 1.0e-3),
        qc=_t2(0.0, 0.0), qr=_t2(0.0, 0.0), qi=_t2(0.0, 0.0),
        qs=_t2(0.0, 0.0), qg=_t2(0.0, 0.0), nccn=_t2(1.0e9, 1.0e9),
        nc=_t2(0.0, 0.0), ni=_t2(0.0, 0.0), nr=_t2(0.0, 0.0),
        bg=_t2(0.0, 0.0),
    )


def test_cloud_active_gate_clear_state_diagnostic_only():
    """§3 endpoint after three adversarial rounds: the gate NEVER skips a VJP
    (zero-hydrometeor states sit on clamp/where kinks — the AD Jacobian there
    is a subgradient, not the identity). On a clear window the gate only
    TALLIES value-inert steps; the adjoint must equal the full-window-graph
    gradient exactly — the strongest correctness statement, kink subgradients
    included."""
    state = _clear_sky_state()
    assert not model_cloud_active(state)

    forcings = [_mk_forcing() for _ in range(2)]
    u = _unit_state(83)
    obs = {2: u}
    cfg = WindowConfig(dt=DT, use_cloud_gate=True)
    res = run_da_window(state, forcings, lambda t, x: obs.get(t), cfg)

    # VJP ran on every step; the inert steps are tallied as diagnostics
    assert res.vjp_steps == [1, 0]
    assert res.skipped_steps == [1, 0]
    ref = _full_graph_adjoint(
        State(*(f.detach().clone().to(torch.float64).requires_grad_(True)
                for f in state)), forcings, obs)
    for name, a, b in zip(State._fields, res.adj_x0, ref):
        assert torch.equal(a, b), f"clear-sky adjoint != full graph in {name}"

    # sanity: the no-op claim is real — the clear-sky forward leaves the state
    # unchanged except the th -> T -> th Exner round-trip (t = th*pii; th = t/pii),
    # a ~1-ULP value wobble whose JACOBIAN is still exactly the identity. So the
    # gate's J^T = I passthrough is exact, not an approximation, on this window.
    out, h = kdm6_step(State(*(f.to(torch.float64) for f in state)),
                       forcings[0], dt=DT, value_only=True)
    h.close()
    for name, a, b in zip(State._fields, out, state):
        b64 = b.to(torch.float64)
        if name == "th":
            assert torch.allclose(a, b64, rtol=1e-12, atol=0), \
                f"clear-sky th beyond the Exner round-trip ULP"
        else:
            assert torch.equal(a, b64), \
                f"clear-sky step not a no-op in {name} — gate premise broken"


def test_cloudy_state_not_tallied_inert():
    """A cloud-active step is never tallied as value-inert; VJP always runs."""
    assert model_cloud_active(_mk_state())
    cfg = WindowConfig(dt=DT, use_cloud_gate=True)
    forcings = [_mk_forcing()]
    u = _unit_state(89)
    res = run_da_window(_mk_state(), forcings, lambda t, x: u if t == 1 else None, cfg)
    assert res.vjp_steps == [0] and not res.skipped_steps


def test_window_handles_closed_no_leak():
    """§8.4 memory stability: every recompute handle is closed; repeated windows
    do not grow the live-tensor population."""
    import gc

    forcings = [_mk_forcing() for _ in range(T_STEPS)]
    u = _unit_state(97)
    cfg = WindowConfig(dt=DT)

    def live_tensors():
        gc.collect()
        return sum(1 for o in gc.get_objects() if torch.is_tensor(o))

    run_da_window(_mk_state(), forcings, lambda t, x: u if t == T_STEPS else None, cfg)
    n1 = live_tensors()
    for _ in range(3):
        run_da_window(_mk_state(), forcings, lambda t, x: u if t == T_STEPS else None, cfg)
    n2 = live_tensors()
    assert n2 - n1 < 50, f"tensor population grew {n1} -> {n2} (handle leak?)"


def test_eta_control_grad_matches_full_graph():
    """§5.1 weak-constraint η: x_{t+1} = M(x_t) + η_t. The driver's grad_eta
    must equal the full-graph autograd gradient w.r.t. η leaves exactly, and
    adj_x0 must equal the η-perturbed full-graph x0-gradient."""
    forcings = [_mk_forcing() for _ in range(T_STEPS)]
    g = torch.Generator().manual_seed(101)

    def small_eta(rg=False):
        fields = []
        for f in _mk_state():
            scale = float(f.abs().max()) or 1.0
            t = torch.randn(f.shape, generator=g, dtype=torch.float64) * 1e-6 * scale
            fields.append(t.requires_grad_(True) if rg else t)
        return State(*fields)

    etas = [small_eta() for _ in range(T_STEPS)]
    u_T = _unit_state(seed=103)
    obs = {T_STEPS: u_T}

    cfg = WindowConfig(dt=DT, eta=etas)
    res = run_da_window(_mk_state(), forcings, lambda t, x: obs.get(t), cfg)
    assert res.grad_eta is not None and len(res.grad_eta) == T_STEPS

    # full-graph reference with η leaves
    eta_leaves = [State(*(f.detach().clone().requires_grad_(True) for f in e))
                  for e in etas]
    x = _mk_state(rg=True)
    params = make_parameters()
    for t, f in enumerate(forcings):
        x = kdm6_fn(x, f, params, DT)
        x = State(*(a + b for a, b in zip(x, eta_leaves[t])))
    loss = state_dot(x, u_T)
    all_leaves = tuple(_x for e in eta_leaves for _x in e)
    grads = torch.autograd.grad(loss, all_leaves, allow_unused=True,
                                materialize_grads=True)
    for t in range(T_STEPS):
        ref_t = grads[t * 12:(t + 1) * 12]
        for name, a, b in zip(State._fields, res.grad_eta[t], ref_t):
            assert torch.equal(a, b), f"grad_eta[{t}].{name} != full graph"


def test_window_rejects_broadcastable_shape_mismatch():
    """Driver-level F1-SHAPE guard: a broadcastable-but-wrong obs covector or
    η increment must raise, not silently corrupt the adjoint accumulation."""
    forcings = [_mk_forcing()]
    bad = State(*(torch.ones((2, 1), dtype=torch.float64) for _ in State._fields))

    with pytest.raises(ValueError, match="shape"):
        run_da_window(_mk_state(), forcings,
                      lambda t, x: bad if t == 1 else None, WindowConfig(dt=DT))

    with pytest.raises(ValueError, match="shape"):
        run_da_window(_mk_state(), forcings, lambda t, x: None,
                      WindowConfig(dt=DT, eta=[bad]))

    with pytest.raises(ValueError, match="length"):
        run_da_window(_mk_state(), forcings, lambda t, x: None,
                      WindowConfig(dt=DT, eta=[]))


def test_supersaturated_clear_air_is_not_skipped():
    """Codex stop-review counterexample: zero hydrometeors but SUPERSATURATED —
    condensation fires (J^T != I), so the gate must NOT skip the step, and the
    driver adjoint must still equal the full-graph gradient exactly."""
    sup = State(
        th=_t2(296.8, 290.0), qv=_t2(2.5e-2, 1.8e-2),   # well above saturation
        qc=_t2(0.0, 0.0), qr=_t2(0.0, 0.0), qi=_t2(0.0, 0.0),
        qs=_t2(0.0, 0.0), qg=_t2(0.0, 0.0), nccn=_t2(1.0e9, 1.0e9),
        nc=_t2(0.0, 0.0), ni=_t2(0.0, 0.0), nr=_t2(0.0, 0.0),
        bg=_t2(0.0, 0.0),
    )
    # entry-hydro heuristic says "clear" — the OLD gate would have skipped
    from kdm6.da_window import model_cloud_active as _mca
    assert not _mca(sup)

    forcings = [_mk_forcing()]
    # sanity: the step really acts (condensation onset)
    out, h = kdm6_step(State(*(f.to(torch.float64) for f in sup)), forcings[0],
                       dt=DT, value_only=True)
    h.close()
    assert (out.qc > 0).any(), "supersaturated column did not condense — IC too weak"

    u = _unit_state(seed=107)
    obs = {1: u}
    cfg = WindowConfig(dt=DT, use_cloud_gate=True)
    res = run_da_window(sup, forcings, lambda t, x: obs.get(t), cfg)

    assert res.vjp_steps == [0] and not res.skipped_steps, \
        "condensing clear-air step wrongly tallied inert / VJP missing"

    sup_leaves = State(*(f.detach().clone().to(torch.float64).requires_grad_(True)
                         for f in sup))
    ref = _full_graph_adjoint(sup_leaves, forcings, obs)
    for name, a, b in zip(State._fields, res.adj_x0, ref):
        assert torch.equal(a, b), f"supersat adjoint != full graph in {name}"


def test_near_saturated_value_noop_is_not_skipped():
    """value-noop alone does NOT imply J = I (Codex stop-review ×2): at/near
    exact saturation pcond = 0 with ∂pcond/∂qv != 0. A clear column with qv
    INSIDE the sub-saturation margin must take the real VJP even though the
    forward step changes nothing — the skip requires PROVABLE neighborhood
    identity (strictly sub-saturated by the margin), not value equality."""
    import torch as _t
    from kdm6.thermo import compute_qs_water, default_thermo_params
    from kdm6.da_window import step_is_noop, hydro_exactly_zero, \
        column_strictly_subsaturated

    th = _t2(300.0, 295.0)
    f = _mk_forcing()
    t_abs = th * f.pii
    qs = compute_qs_water(t_abs.to(_t.float64), f.p.to(_t.float64),
                          params=default_thermo_params())
    qv = (0.9995 * qs)                      # inside the 1e-3 margin band
    near_sat = State(
        th=th, qv=qv,
        qc=_t2(0.0, 0.0), qr=_t2(0.0, 0.0), qi=_t2(0.0, 0.0),
        qs=_t2(0.0, 0.0), qg=_t2(0.0, 0.0), nccn=_t2(1.0e9, 1.0e9),
        nc=_t2(0.0, 0.0), ni=_t2(0.0, 0.0), nr=_t2(0.0, 0.0),
        bg=_t2(0.0, 0.0),
    )
    # premise checks: hydro zero, NOT strictly subsaturated at the margin,
    # and the forward step is a VALUE no-op — the dangerous combination.
    assert hydro_exactly_zero(near_sat)
    assert not column_strictly_subsaturated(near_sat, f, margin=1.0e-3)
    x64 = State(*(t.to(_t.float64) for t in near_sat))
    out, h = kdm6_step(x64, f, dt=DT, value_only=True)
    h.close()
    assert step_is_noop(x64, State(*(t.detach() for t in out))), \
        "IC drifted — pick qv closer below qs"

    u = _unit_state(seed=109)
    obs = {1: u}
    cfg = WindowConfig(dt=DT, use_cloud_gate=True)
    res = run_da_window(near_sat, [f], lambda t, x: obs.get(t), cfg)
    assert res.vjp_steps == [0] and not res.skipped_steps, \
        "near-saturated value-noop wrongly tallied as provably inert"

    ref = _full_graph_adjoint(State(*(t.detach().clone().to(_t.float64)
                                      .requires_grad_(True) for t in near_sat)),
                              [f], obs)
    for name, a, b in zip(State._fields, res.adj_x0, ref):
        assert torch.equal(a, b), f"near-sat adjoint != full graph in {name}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
