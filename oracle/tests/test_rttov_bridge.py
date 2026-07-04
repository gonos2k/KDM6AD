"""[DA §9.3] independent gates for the KDM6AD DSD/optical bridge.

The design's bridge contract: (1) DSD values must be the SCHEME'S OWN (no
re-derivation with different constants/eval-forms); (2) the operator must
independently pass VJP/JVP inner-product and FD verification.
"""
from __future__ import annotations

import pytest
import torch

from kdm6 import constants as c
from kdm6 import coordinator as _coord
from kdm6.runtime import _state_to_coord, _build_coord_forcing
from kdm6.rttov_bridge import dsd_diagnostics, rttov_cloud_profile, RttovCloudProfile
from kdm6.state import State, Forcing


def _t2(a, b, rg=False):
    t = torch.tensor([[a, b]], dtype=torch.float64)
    return t.requires_grad_(True) if rg else t


def _mk_state(rg=False):
    return State(
        th=_t2(296.8, 282.4, rg), qv=_t2(1.40e-2, 2.0e-3, rg),
        qc=_t2(1.0e-3, 5.0e-4, rg), qr=_t2(1.0e-4, 1.0e-5, rg),
        qi=_t2(0.0, 5.0e-5, rg), qs=_t2(0.0, 1.0e-4, rg),
        qg=_t2(0.0, 5.0e-5, rg), nccn=_t2(1.0e9, 1.0e9, rg),
        nc=_t2(1.0e8, 1.0e8, rg), ni=_t2(0.0, 1.0e8, rg),
        nr=_t2(1.0e4, 1.0e3, rg), bg=_t2(0.0, 0.0, rg),
    )


def _mk_forcing():
    return Forcing(rho=_t2(1.089, 0.9567), pii=_t2(0.9704, 0.9031),
                   p=_t2(9.0e4, 7.0e4), delz=_t2(500.0, 500.0))


def _profile_vec(p: RttovCloudProfile) -> torch.Tensor:
    return torch.cat([f.reshape(-1) for f in p])


def test_bridge_slopes_are_schemes_own():
    """§9.3 consistency: bridge rslopes/avedia must be BITWISE the values the
    scheme's own preamble computes — the bridge re-derives nothing."""
    state, forcing = _mk_state(), _mk_forcing()
    d = dsd_diagnostics(state, forcing)

    cs = _state_to_coord(state, forcing)
    cf = _build_coord_forcing(forcing)
    sea = torch.ones_like(cs.qc, dtype=torch.bool)
    pre = _coord.preamble_torch(cs, cf, sea,
                                params=_coord.default_coordinator_params())
    assert torch.equal(d.rslope_c, pre.rslopec)
    assert torch.equal(d.rslope_r, pre.slope.rslope_r)
    assert torch.equal(d.rslope_s, pre.slope.rslope_s)
    assert torch.equal(d.rslope_g, pre.slope.rslope_g)
    assert torch.equal(d.rslope_i, pre.slope.rslope_i)
    assert torch.equal(d.avedia_c, pre.avedia_c)
    assert torch.equal(d.avedia_r, pre.avedia_r)


def test_reff_matches_fortran_effectrad():
    """Reff must be the SCHEME'S OWN effectRad_kdm6 formulas (F:4117-4143),
    NOT the naive standard-gamma (mu+3)/2 ratio — KDM6's cloud DSD is a
    Cohard-Pinty GENERALIZED gamma; the naive 2.5·rslopec overestimated cloud
    Reff by 4.51x (adversarial review F2; host: re_qc = Γ(2)/(2Γ(5/3))·rslopec
    ≈ 0.5539·rslopec)."""
    import math
    d = dsd_diagnostics(_mk_state(), _mk_forcing())
    cdm2 = math.gamma(2.0 / (c.MUC + 1.0) + 1.0)   # Γ(5/3)
    cdm3 = math.gamma(3.0 / (c.MUC + 1.0) + 1.0)   # Γ(2) = 1
    pref_c = cdm3 / (2.0 * cdm2)
    assert abs(pref_c - 0.5539) < 5e-4              # the host's own prefactor
    assert torch.equal(d.reff_c,
                       torch.clamp(pref_c * d.rslope_c, min=2.51e-6, max=50.0e-6))
    idm3, idm4 = math.gamma(3.0 + c.MUI), math.gamma(4.0 + c.MUI)
    assert torch.equal(d.reff_i,
                       torch.clamp(d.rslope_i * idm3 / (2.0 * idm4),
                                   min=10.01e-6, max=125.0e-6))
    assert torch.equal(d.reff_s,
                       torch.clamp(0.5 * d.rslope_s, min=25.0e-6, max=999.0e-6))
    # the naive prefactor must NOT be what we ship
    assert not torch.allclose(d.reff_c, 2.5 * d.rslope_c)


def test_profile_carries_nr_and_bg_adjoints():
    """§9.3 example demands rain-size and graupel-density proxies — without
    them λ_nr and λ_bg are identically zero (review finding 2)."""
    state = _mk_state(rg=True)
    state = state._replace(bg=torch.tensor([[1.0e-6, 2.0e-6]],
                                           dtype=torch.float64, requires_grad=True))
    p = rttov_cloud_profile(state, _mk_forcing())
    loss = (p.rain_dm * p.rain_dm).sum() + (p.graupel_rime_frac ** 2).sum()
    grads = torch.autograd.grad(loss, (state.nr, state.bg), allow_unused=True,
                                materialize_grads=True)
    assert (grads[0] != 0).any(), "λ_nr still zero — rain Dm proxy not wired"
    assert (grads[1] != 0).any(), "λ_bg still zero — graupel density proxy not wired"


def test_rime_frac_inactive_graupel_gate():
    """(qg=0, bg>0) is reachable at the DA boundary — bg is prognostic and
    analysis increments need not keep the qg/bg pair coupled. The bare ratio
    bg/clamp(qg, 1e-15) returned ~1e9 garbage with an explosive
    ∂/∂bg = 1e15 adjoint (Codex adversarial review 2026-06-13, finding 2);
    the bridge must gate the frac to 0 with a ZERO adjoint where graupel is
    inactive, and keep the plain ratio (bitwise) where it is active."""
    state = _mk_state(rg=True)
    state = state._replace(
        qg=torch.tensor([[0.0, 5.0e-5]], dtype=torch.float64,
                        requires_grad=True),
        bg=torch.tensor([[1.0e-6, 2.0e-6]], dtype=torch.float64,
                        requires_grad=True))
    d = dsd_diagnostics(state, _mk_forcing())
    # value: exactly 0 in the inactive cell, the plain ratio in the active one
    frac = d.graupel_rime_frac.detach()
    assert float(frac[0, 0]) == 0.0
    assert torch.equal(frac[:, 1:],
                       (state.bg[:, 1:] / state.qg[:, 1:]).detach())
    assert float(frac.abs().max()) < 1.0, \
        "bg/1e-15 garbage leaked through the inactive-graupel gate"
    # adjoint: zero w.r.t. bg AND qg in the inactive cell, finite everywhere,
    # nonzero in the active cell (the λ_bg carrier must survive the gate)
    g_bg, g_qg = torch.autograd.grad(d.graupel_rime_frac.sum(),
                                     (state.bg, state.qg))
    assert float(g_bg[0, 0]) == 0.0 and float(g_qg[0, 0]) == 0.0
    assert torch.isfinite(g_bg).all() and torch.isfinite(g_qg).all()
    assert float(g_bg[0, 1]) != 0.0


def test_bridge_autograd_flows():
    """Gradients flow from every profile variable back to the hydrometeor
    state leaves, finite, and hit the expected leaves (qc&nc for reff_liq)."""
    state = _mk_state(rg=True)
    p = rttov_cloud_profile(state, _mk_forcing())
    loss = sum((f * f).sum() for f in p)
    grads = torch.autograd.grad(loss, tuple(state), allow_unused=True,
                                materialize_grads=True)
    gmap = dict(zip(State._fields, grads))
    for name, g in gmap.items():
        assert torch.isfinite(g).all(), f"non-finite grad in {name}"
    for name in ("qc", "nc", "qr", "qi"):
        assert (gmap[name] != 0).any(), f"no gradient reaches {name}"


def test_bridge_vjp_fd_directional():
    """independent FD verification (§9.3): <J^T u, v> vs central FD of
    <profile(x+eps v), u> on a smooth direction (qc/nc/qv subspace)."""
    forcing = _mk_forcing()
    state = _mk_state(rg=True)
    p = rttov_cloud_profile(state, forcing)
    gen = torch.Generator().manual_seed(137)
    u = [torch.randn_like(f) for f in p]

    scalar = sum((f * uf).sum() for f, uf in zip(p, u))
    grads = torch.autograd.grad(scalar, tuple(state), allow_unused=True,
                                materialize_grads=True)

    # smooth direction: perturb qc/nc/qv only (rain/ice slopes have active
    # clamp boundaries at this IC — kink policy: probe the smooth subspace)
    v = []
    for name, f in zip(State._fields, _mk_state()):
        if name in ("qc", "nc", "qv"):
            scale = float(f.abs().max()) or 1.0
            v.append(torch.randn(f.shape, generator=gen, dtype=torch.float64)
                     * 1e-5 * scale)
        else:
            v.append(torch.zeros_like(f))
    lhs = float(sum((g * vf).sum() for g, vf in zip(grads, v)).detach())

    def loss_at(eps):
        with torch.no_grad():
            xs = State(*(f + eps * vf for f, vf in zip(_mk_state(), v)))
            pp = rttov_cloud_profile(xs, forcing)
            return float(sum((f * uf).sum() for f, uf in zip(pp, u)))

    fd = (loss_at(1.0) - loss_at(-1.0)) / 2.0
    rel = abs(lhs - fd) / max(abs(lhs), abs(fd), 1e-30)
    assert rel < 1e-6, f"bridge FD mismatch: ad={lhs!r} fd={fd!r} rel={rel:.3e}"


def test_bridge_jvp_vjp_inner_product_exact():
    """<Jv,u> == <v,J^T u> via the Pearlmutter double-VJP route on the bridge
    operator alone (independent of the KDM6AD Handle)."""
    forcing = _mk_forcing()
    state = _mk_state(rg=True)
    p = rttov_cloud_profile(state, forcing)
    gen = torch.Generator().manual_seed(139)
    u = [torch.randn_like(f) for f in p]
    v = [torch.randn(f.shape, generator=gen, dtype=torch.float64) * 1e-6
         for f in state]

    # J^T u
    scalar = sum((f * uf).sum() for f, uf in zip(p, u))
    jtu = torch.autograd.grad(scalar, tuple(state), create_graph=True,
                              allow_unused=True, materialize_grads=True)
    rhs = float(sum((g * vf).sum() for g, vf in zip(jtu, v)).detach())

    # Jv via Pearlmutter: dummy adjoint w leaves, w-linear graph
    w = [torch.zeros_like(f).requires_grad_(True) for f in p]
    scalar2 = sum((f * wf).sum() for f, wf in zip(p, w))
    g2 = torch.autograd.grad(scalar2, tuple(state), create_graph=True,
                             retain_graph=True, allow_unused=True,
                             materialize_grads=True)
    inner = sum((gf * vf).sum() for gf, vf in zip(g2, v))
    jv = torch.autograd.grad(inner, w, allow_unused=True, materialize_grads=True)
    lhs = float(sum((jvf * uf).sum() for jvf, uf in zip(jv, u)))

    denom = max(abs(lhs), abs(rhs), 1e-30)
    assert abs(lhs - rhs) / denom < 1e-12, f"bridge adjoint identity: {lhs!r} vs {rhs!r}"


def test_bridge_clear_state_finite():
    """zero-hydrometeor state: contents are exactly 0, slopes sit at the
    scheme's inactive-clamp values, everything finite (no NaN at the corner)."""
    z = State(
        th=_t2(300.0, 295.0), qv=_t2(2.0e-3, 1.0e-3),
        qc=_t2(0.0, 0.0), qr=_t2(0.0, 0.0), qi=_t2(0.0, 0.0),
        qs=_t2(0.0, 0.0), qg=_t2(0.0, 0.0), nccn=_t2(1.0e9, 1.0e9),
        nc=_t2(0.0, 0.0), ni=_t2(0.0, 0.0), nr=_t2(0.0, 0.0),
        bg=_t2(0.0, 0.0),
    )
    p = rttov_cloud_profile(z, _mk_forcing())
    for name, f in zip(RttovCloudProfile._fields, p):
        assert torch.isfinite(f).all(), f"non-finite {name} on clear state"
    for name in ("clw", "ciw", "rain", "snow", "graupel"):
        assert torch.all(getattr(p, name) == 0), f"{name} != 0 on clear state"


def test_bridge_honors_xland_ncmin_gate():
    """Codex stop-review: the per-cell ncmin (xland) feeds the cloud-slope
    INACTIVE gate inside the preamble — the bridge must thread it exactly like
    the runtime, or its rslopec diverges from the scheme's own on land cells."""
    import torch as _t
    from kdm6 import constants as _c

    # nc between the sea floor (10e6) and land floor (100e6): the cloud-slope
    # gate trips on LAND only — a bridge that drops ncmin can't see this.
    state = _mk_state()
    state = state._replace(nc=_t.tensor([[5.0e7, 5.0e7]], dtype=_t.float64))
    forcing = _mk_forcing()
    xland = _t.tensor([1.0], dtype=_t.float64)      # LAND column
    ncmin_land, ncmin_sea = 100.0e6, 10.0e6

    d_land = dsd_diagnostics(state, forcing, xland, ncmin_land, ncmin_sea)
    d_def = dsd_diagnostics(state, forcing)          # no xland → scalar NCMIN

    # reference: preamble with the runtime-identical ncmin_tensor
    cs = _state_to_coord(state, forcing)
    cf = _build_coord_forcing(forcing)
    sea = _t.zeros_like(cs.qc, dtype=_t.bool)        # land everywhere
    ncmin_t = _t.clamp(_t.where(sea, _t.full_like(cs.qc, ncmin_sea),
                                _t.full_like(cs.qc, ncmin_land)), min=_c.NCMIN)
    pre = _coord.preamble_torch(cs, cf, sea,
                                params=_coord.default_coordinator_params(),
                                ncmin_tensor=ncmin_t)
    assert torch.equal(d_land.rslope_c, pre.rslopec), \
        "bridge rslopec != scheme's own under xland/ncmin"
    assert not torch.equal(d_land.rslope_c, d_def.rslope_c), \
        "gate did not trip — IC no longer discriminates (fix the test IC)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
