"""Phase 0/1 gates for the DA Handle.vjp / Handle.jvp (kdm6ad+da.md §10.1, §10.2, §8.4).

Implements the design-doc test set on the fp64 Python oracle (the DA adjoint
forward of §0.1.A — the operational f32 path is NOT exercised here):

  - test_handle_vjp_matches_autograd_grad       (§10.1)
  - test_vjp_fd_directional_derivative          (§10.1 / Phase 1.4)
  - test_custom_functions_double_backward_ready (§10.2 — Pearlmutter hidden premise)
  - test_pearlmutter_jvp_matches_fd             (§10.2 test set)
  - test_handle_jvp_inner_product               (§10.1/§10.2 — exact, not FD-bounded)
  - test_forward_determinism_value_vs_graph     (§8.4 gate — fp64 reproducibility)
  - test_checkpoint_recompute_one_step_vjp      (§10.1 / §8.4 backward skeleton)
  - test_vjp_active_field_mask                  (§8.2 active_field_mask)

IC policy: a fixed, well-conditioned mixed-phase 2-cell column (the
test_cpp_parity _G_BASE family) — away from clamp knife-edges so central FD is
valid (kink policy: an FD↔AD mismatch at a clamp is NOT auto a bug; these gates
must run on smooth points). Do NOT randomize.
"""
from __future__ import annotations

import math

import pytest
import torch

from kdm6.state import State, Forcing, state_dot
from kdm6.runtime import kdm6_step, make_parameters

DT = 20.0  # single sub-cycle (loops=1) — same smoothness rationale as test_autograd_endtoend


def _t2(a: float, b: float, requires_grad: bool = False) -> torch.Tensor:
    t = torch.tensor([[a, b]], dtype=torch.float64)
    return t.requires_grad_(True) if requires_grad else t


def _mk_state(requires_grad: bool) -> State:
    # mirrors the C++ g_base / test_cpp_parity _G_BASE mixed-phase IC
    # (k0 ≈ 288K warm, k1 ≈ 255K supercooled; tiny-crystal non-depleting ice).
    return State(
        th=_t2(296.8, 282.4, requires_grad),
        qv=_t2(1.40e-2, 2.0e-3, requires_grad),
        qc=_t2(1.0e-3, 5.0e-4, requires_grad),
        qr=_t2(1.0e-4, 1.0e-5, requires_grad),
        qi=_t2(0.0, 1.0e-6, requires_grad),
        qs=_t2(0.0, 5.0e-5, requires_grad),
        qg=_t2(0.0, 1.0e-5, requires_grad),
        nccn=_t2(1.0e9, 1.0e9, requires_grad),
        nc=_t2(1.0e8, 1.0e8, requires_grad),
        ni=_t2(0.0, 1.0e8, requires_grad),
        nr=_t2(1.0e4, 1.0e3, requires_grad),
        bg=_t2(0.0, 0.0, requires_grad),
    )


def _mk_forcing() -> Forcing:
    return Forcing(
        rho=_t2(1.089, 0.9567),
        pii=_t2(0.9704, 0.9031),
        p=_t2(9.0e4, 7.0e4),
        delz=_t2(500.0, 500.0),
    )


def _unit_state(seed: int) -> State:
    """Deterministic O(1)-magnitude direction/covector (fixed seed, NOT per-run random)."""
    g = torch.Generator().manual_seed(seed)
    return State(*(torch.randn((1, 2), generator=g, dtype=torch.float64) for _ in State._fields))


def _scaled_direction(state: State, seed: int, rel: float = 1.0e-4) -> State:
    """Per-field direction scaled to the field's magnitude so x±εv stays physical."""
    g = torch.Generator().manual_seed(seed)
    fields = []
    for f in state:
        scale = float(f.detach().abs().max()) or 1.0
        fields.append(torch.randn(f.shape, generator=g, dtype=torch.float64) * rel * scale)
    return State(*fields)


def _smooth_direction(state: State, seed: int, rel: float = 1.0e-4) -> State:
    """FD-probe direction restricted to the SMOOTH thermo subspace (th, qv, qc).

    A full 24-component random direction crosses hard microphysics gates
    (number-concentration thresholds, saturation/branch flips): the loss then has
    a JUMP inside x±εv and central FD diverges like Δ/(2ε) as ε shrinks (the
    C++ PART-B0 "S4 jump" class) — measured here: rel error DOUBLING per ε
    halving. Per the kink policy the fix is the probe, not the AD: FD validity
    gates use this smooth direction (verified O(ε²) convergent, rel→1e-8), while
    the EXACT gates (vjp==autograd.grad, <Jv,u>==<v,J^T u>) cover the full
    operator including non-smooth directions."""
    g = torch.Generator().manual_seed(seed)
    smooth = ("th", "qv", "qc")
    fields = []
    for name, f in zip(State._fields, state):
        if name in smooth:
            scale = float(f.detach().abs().max()) or 1.0
            fields.append(torch.randn(f.shape, generator=g, dtype=torch.float64) * rel * scale)
        else:
            fields.append(torch.zeros_like(f))
    return State(*fields)


def _state_to_vec(s: State) -> torch.Tensor:
    return torch.cat([f.reshape(-1) for f in s])


# ───────────────────────────── §10.1 core gates ─────────────────────────────


def test_handle_vjp_matches_autograd_grad():
    """vjp(u) must equal the leaf grads of <state_out, u>.backward() exactly."""
    state = _mk_state(requires_grad=True)
    out, handle = kdm6_step(state, _mk_forcing(), dt=DT)
    u = _unit_state(seed=11)

    g_vjp = handle.vjp(u, retain_graph=True)

    scalar = state_dot(out, u)
    grads_ref = torch.autograd.grad(scalar, tuple(state), allow_unused=True,
                                    materialize_grads=True)
    for name, gv, gr in zip(State._fields, g_vjp, grads_ref):
        assert torch.equal(gv, gr), f"vjp[{name}] != autograd.grad reference"
    handle.close()


def test_vjp_fd_directional_derivative():
    """<vjp(u), v> ≈ d/dε <M(x+εv), u> by central FD (smooth IC ⇒ FD valid)."""
    state = _mk_state(requires_grad=True)
    forcing = _mk_forcing()
    out, handle = kdm6_step(state, forcing, dt=DT)
    u = _unit_state(seed=13)
    v = _smooth_direction(state, seed=17)

    lhs = float(state_dot(handle.vjp(u), v))
    handle.close()

    def loss_at(eps: float) -> float:
        with torch.no_grad():
            xp = State(*(f + eps * vf for f, vf in zip(_mk_state(False), v)))
            yp, h = kdm6_step(xp, forcing, dt=DT, value_only=True)
            h.close()
            return float(state_dot(yp, u))

    fd = (loss_at(+1.0) - loss_at(-1.0)) / 2.0
    denom = max(abs(fd), abs(lhs), 1e-30)
    rel = abs(lhs - fd) / denom
    assert rel < 1e-6, f"directional FD mismatch: ad={lhs!r} fd={fd!r} rel={rel:.3e}"


# ───────────────────── §10.2 Pearlmutter hidden-premise gate ─────────────────────


def test_custom_functions_double_backward_ready():
    """The double-VJP route needs every custom autograd Function's backward to be
    differentiable again (no once_differentiable). Exercise the f32-only Python
    custom Function (_RgmmaF32) and the full fp64 oracle chain."""
    # (a) _RgmmaF32 (fires only on float32)
    from kdm6.progb import _rgmma_tensor

    x32 = torch.tensor([1.5, 2.5, 4.8], dtype=torch.float32, requires_grad=True)
    y = _rgmma_tensor(x32)
    (g,) = torch.autograd.grad(y.sum(), x32, create_graph=True)
    (gg,) = torch.autograd.grad(g.sum(), x32)
    assert torch.isfinite(gg).all() and (gg != 0).any(), "_RgmmaF32 double-backward broken"

    # (b) full fp64 oracle: first VJP with create_graph=True must yield a grad
    # that is itself connected and differentiable (the Pearlmutter prerequisite).
    state = _mk_state(requires_grad=True)
    out, handle = kdm6_step(state, _mk_forcing(), dt=DT)
    u = _unit_state(seed=19)
    g1 = handle.vjp(u, create_graph=True)
    probe = sum((f * f).sum() for f in g1)
    g2 = torch.autograd.grad(probe, tuple(state), allow_unused=True, materialize_grads=True)
    assert all(torch.isfinite(t).all() for t in g2), "oracle double-backward non-finite"
    assert any((t != 0).any() for t in g2), "oracle double-backward all-zero"
    handle.close()


def test_pearlmutter_jvp_matches_fd():
    """jvp(v) (double-VJP route) ≈ central FD tangent [M(x+v)-M(x-v)]/2 per field."""
    state = _mk_state(requires_grad=True)
    forcing = _mk_forcing()
    out, handle = kdm6_step(state, forcing, dt=DT)
    v = _smooth_direction(state, seed=23)

    tangent = handle.jvp(v)
    handle.close()

    with torch.no_grad():
        xp = State(*(f + vf for f, vf in zip(_mk_state(False), v)))
        xm = State(*(f - vf for f, vf in zip(_mk_state(False), v)))
        yp, hp = kdm6_step(xp, forcing, dt=DT, value_only=True); hp.close()
        ym, hm = kdm6_step(xm, forcing, dt=DT, value_only=True); hm.close()

    t_ad = _state_to_vec(tangent)
    t_fd = (_state_to_vec(yp) - _state_to_vec(ym)) / 2.0
    scale = float(t_fd.abs().max()) or 1.0
    rel = float((t_ad - t_fd).abs().max()) / scale
    assert rel < 1e-5, f"Pearlmutter JVP vs FD: max rel {rel:.3e}"


def test_handle_jvp_inner_product():
    """<Jv, u> == <v, J^T u> — EXACT (both sides reverse-mode; not FD-bounded)."""
    state = _mk_state(requires_grad=True)
    out, handle = kdm6_step(state, _mk_forcing(), dt=DT)
    u = _unit_state(seed=29)
    v = _scaled_direction(state, seed=31)

    jv = handle.jvp(v)
    jtu = handle.vjp(u, retain_graph=True)
    handle.close()

    lhs = float(state_dot(jv, u))
    rhs = float(state_dot(v, jtu))
    denom = max(abs(lhs), abs(rhs), 1e-30)
    assert abs(lhs - rhs) / denom < 1e-12, f"<Jv,u>={lhs!r} vs <v,J^T u>={rhs!r}"


# ───────────────────────── §8.4 determinism + recompute gates ─────────────────────────


def test_forward_determinism_value_vs_graph():
    """value_only forward and graph forward must produce the SAME point (fp64
    bitwise here): the custom-op dispatch (GradMode/InferenceMode/requires_grad)
    may switch implementations but not values — without this, checkpoint/recompute
    adjoints are not linearizations of the same trajectory."""
    forcing = _mk_forcing()
    y_value, h1 = kdm6_step(_mk_state(False), forcing, dt=DT, value_only=True)
    h1.close()
    y_graph, h2 = kdm6_step(_mk_state(True), forcing, dt=DT, value_only=False)
    h2.close()
    for name, a, b in zip(State._fields, y_value, y_graph):
        assert torch.equal(a.detach(), b.detach()), f"forward mismatch in {name}"


def test_checkpoint_recompute_one_step_vjp():
    """§8.4 backward skeleton: a vjp computed by RECOMPUTING from a detached
    checkpoint equals the vjp from the original graph-carrying step."""
    forcing = _mk_forcing()
    u = _unit_state(seed=37)

    # direct: graph kept from the start
    s_direct = _mk_state(requires_grad=True)
    _, h_direct = kdm6_step(s_direct, forcing, dt=DT)
    g_direct = h_direct.vjp(u)
    h_direct.close()

    # checkpoint/recompute: value-only forward, then rebuild a local graph
    # from the detached checkpoint (fresh requires_grad leaves)
    ckpt = State(*(f.detach().clone() for f in _mk_state(False)))
    leaves = State(*(f.detach().clone().requires_grad_(True) for f in ckpt))
    _, h_local = kdm6_step(leaves, forcing, dt=DT)
    g_recompute = h_local.vjp(u)
    h_local.close()

    for name, a, b in zip(State._fields, g_direct, g_recompute):
        assert torch.equal(a, b), f"recompute vjp mismatch in {name}"


# ───────────────────────────── §8.2 active mask ─────────────────────────────


def test_vjp_active_field_mask():
    """active_fields keeps listed fields and zeros the rest (hydrometeor-centric VJP)."""
    state = _mk_state(requires_grad=True)
    out, handle = kdm6_step(state, _mk_forcing(), dt=DT)
    u = _unit_state(seed=41)
    active = ("qc", "qr", "qi", "qs", "qg", "nc", "ni", "nr")

    g_full = handle.vjp(u, retain_graph=True)
    g_mask = handle.vjp(u, active_fields=active)
    handle.close()

    for name, gf, gm in zip(State._fields, g_full, g_mask):
        if name in active:
            assert torch.equal(gf, gm), f"active field {name} altered by mask"
        else:
            assert torch.all(gm == 0), f"inactive field {name} not zeroed"
    # the full vjp must actually be nonzero somewhere for this test to mean anything
    assert any((g != 0).any() for g in g_full)

    # invalid mask must fail BEFORE touching autograd (must not consume the
    # one-shot graph — Codex stop-review): a valid vjp must still succeed after.
    handle2 = kdm6_step(_mk_state(True), _mk_forcing(), dt=DT)[1]
    try:
        with pytest.raises(ValueError):
            handle2.vjp(u, active_fields=("not_a_field",))
        g_after = handle2.vjp(u)  # graph intact -> works
        assert any((g != 0).any() for g in g_after)
    finally:
        handle2.close()


def test_masked_jvp_vjp_adjoint_identity():
    """SAME active_fields on both sides must keep the TL/AD pair exactly adjoint:
    <J P v, u> == <v, P J^T u> (control-subspace semantics — jvp masks the INPUT
    direction, vjp masks the OUTPUT grad). Guards adversarial finding
    F1-MASK-ADJOINT-ASYM (output-space jvp mask broke adjointness at rel ~1e-9)."""
    state = _mk_state(requires_grad=True)
    out, handle = kdm6_step(state, _mk_forcing(), dt=DT)
    u = _unit_state(seed=43)
    v = _scaled_direction(state, seed=47)
    active = ("qc", "qr", "qi", "qs", "qg", "nc", "ni", "nr")

    jv = handle.jvp(v, active_fields=active)
    jtu = handle.vjp(u, active_fields=active, retain_graph=True)
    handle.close()

    lhs = float(state_dot(jv, u))
    rhs = float(state_dot(v, jtu))
    denom = max(abs(lhs), abs(rhs), 1e-30)
    assert abs(lhs - rhs) / denom < 1e-12, (
        f"masked adjoint identity broken: <JPv,u>={lhs!r} <v,PJ^Tu>={rhs!r}")


def test_vjp_jvp_reject_broadcast_shape_mismatch():
    """Broadcast-compatible but mismatched u/v shapes must raise BEFORE autograd —
    state_dot would silently broadcast (e.g. (2,1) vs (1,2) -> (2,2)) and return a
    plausible but WRONG adjoint/tangent (adversarial finding F1-SHAPE)."""
    state = _mk_state(requires_grad=True)
    out, handle = kdm6_step(state, _mk_forcing(), dt=DT)

    bad_u = State(*(torch.ones((2, 1), dtype=torch.float64) for _ in State._fields))
    with pytest.raises(ValueError, match="shape"):
        handle.vjp(bad_u)

    bad_v = State(*(torch.ones((2,), dtype=torch.float64) for _ in State._fields))
    with pytest.raises(ValueError, match="shape"):
        handle.jvp(bad_v)

    # the failed validations must NOT have consumed the graph
    g = handle.vjp(_unit_state(seed=53))
    assert any((f != 0).any() for f in g)
    handle.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
