"""Phase 4 (all-sky) -- FD/VJP hardening of the COMPOSED cloud path.

The Phase-1/2 gates check shapes, the bridge-vs-builder mapping, and that grad flows.
Phase 4 is the regression net: the composed model_to_rttov_tensors cloud output
(content + Deff) must be adjoint-consistent (exact JVP/VJP inner-product) AND match
central finite differences in the smooth (active-species) regime, and the xland/ncmin
per-cell gate must thread through the obs builder into the bridge. No production code
change is expected here -- a failure means a Phase-1/2 regression.
"""
import math

import torch

from kdm6.state import Forcing, State
from kdm6.obs.model_profile_builder import (
    RttovProfileConfig, model_to_rttov_tensors, _DEFF_LIQ_MIN, _DEFF_LIQ_MAX)
from kdm6.rttov_bridge import rttov_cloud_profile

F64 = torch.float64


def _t(vals, rg=False):
    x = torch.tensor(vals, dtype=F64)
    return x.requires_grad_(True) if rg else x


def _mk_col(rg=False):
    """2-layer mixed-phase column in the unclamped ice/liquid-slope band (so nc/ni ->
    Deff gradients are live and the active species sit away from the content clamps)."""
    return State(th=_t([238.0, 290.0], rg), qv=_t([4.0e-4, 1.20e-2], rg),
                 qc=_t([0.0, 1.2e-3], rg), qr=_t([0.0, 1.0e-4], rg),
                 qi=_t([8.0e-4, 0.0], rg), qs=_t([3.0e-5, 0.0], rg),
                 qg=_t([0.0, 0.0], rg), nccn=_t([1.0e9, 1.0e9], rg),
                 nc=_t([0.0, 6.0e7], rg), ni=_t([5.0e5, 0.0], rg),
                 nr=_t([0.0, 1.0e4], rg), bg=_t([0.0, 0.0], rg))


def _mk_forcing():
    return Forcing(rho=_t([0.45, 1.05]), pii=_t([0.84, 0.97]),
                   p=_t([3.0e4, 9.0e4]), delz=_t([800.0, 500.0]))


def _cfg():
    return RttovProfileConfig(gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
                              rttov_layer_pressure=None, cloud=True)


def _cloud_vec(state, forcing, cfg, xland=None, ncl=0.0, ncs=0.0):
    p = model_to_rttov_tensors(state, forcing, cfg, xland=xland, ncmin_land=ncl, ncmin_sea=ncs)
    return torch.cat([p.clw, p.ciw, p.deff_liq, p.deff_ice])     # [4*K], differentiable


_LEAF_NAMES = ("th", "qv", "qc", "qi", "qs", "nc", "ni")


def test_cloud_path_jvp_vjp_inner_product():
    """Exact adjoint consistency on the composed cloud output: <J v, w> == <v, J^T w>
    (double-backward; fp64; kink-immune -- no FD). Catches any graph break / detach in
    model_to_rttov_tensors' cloud path that a nonzero-grad check would miss."""
    col, f, cfg = _mk_col(rg=True), _mk_forcing(), _cfg()
    leaves = tuple(getattr(col, n) for n in _LEAF_NAMES)
    out = _cloud_vec(col, f, cfg)
    gen = torch.Generator().manual_seed(11)
    w = torch.randn(out.shape, generator=gen, dtype=F64).requires_grad_(True)  # diff'd in JVP step
    jtw = torch.autograd.grad(out, leaves, grad_outputs=w, create_graph=True,
                              allow_unused=True, materialize_grads=True)
    # per-cloud-leaf non-vacuity: each cloud-driving species must actually reach the
    # output (a partial graph break on e.g. nc/ni would pass an aggregate-only check).
    jtw_by = dict(zip(_LEAF_NAMES, jtw))
    for n in ("qc", "qi", "qs", "nc", "ni"):
        assert float(jtw_by[n].detach().abs().sum()) > 0.0, f"{n} severed from cloud output"
    v = [torch.randn(l.shape, generator=gen, dtype=F64) for l in leaves]
    inner_vjp = sum((a * b).sum() for a, b in zip(jtw, v))       # <v, J^T w> = w^T J v
    jv = torch.autograd.grad(inner_vjp, w, retain_graph=True)[0]  # J v
    lhs = float((jv.detach() * w.detach()).sum())               # <J v, w> = w^T J v
    assert abs(lhs) > 1.0e-3, "vacuous (J ~ 0): the cloud Jacobian must be nontrivial"
    assert math.isclose(lhs, float(inner_vjp.detach()), rel_tol=1e-9, abs_tol=1e-12)


def test_cloud_path_fd_matches_autograd_active_components():
    """Composed cloud-path gradient VALUE matches central-FD for the ACTIVE species
    (qc>0, qi/qs>0, nc/ni in the unclamped band, th/qv) -- the smooth regime where
    central FD is valid (clamp/blend kinks at qc[0]=0 etc. are excluded, AD-rules §12)."""
    col, f, cfg = _mk_col(rg=True), _mk_forcing(), _cfg()
    leaves = tuple(getattr(col, n) for n in _LEAF_NAMES)
    out = _cloud_vec(col, f, cfg)
    gen = torch.Generator().manual_seed(7)
    w = torch.randn(out.shape, generator=gen, dtype=F64)
    grads = dict(zip(_LEAF_NAMES, torch.autograd.grad((w * out).sum(), leaves,
                                                      allow_unused=True, materialize_grads=True)))

    def J(state):
        return float((w * _cloud_vec(state, f, cfg)).sum())

    active = [("th", 0), ("th", 1), ("qv", 1), ("qc", 1), ("qi", 0), ("qs", 0), ("nc", 1), ("ni", 0)]
    base = _mk_col()
    nonzero = 0
    for name, idx in active:
        v0 = float(getattr(base, name)[idx])
        eps = max(abs(v0), 1.0) * 1.0e-7                          # scale eps to the component
        vp = getattr(base, name).clone(); vp[idx] += eps
        vm = getattr(base, name).clone(); vm[idx] -= eps
        fd = (J(base._replace(**{name: vp})) - J(base._replace(**{name: vm}))) / (2.0 * eps)
        ad = float(grads[name][idx].detach())
        assert math.isclose(ad, fd, rel_tol=1e-4, abs_tol=1e-7), \
            f"{name}[{idx}]: AD {ad} != FD {fd}"
        nonzero += int(abs(ad) > 1.0e-9)
    assert nonzero >= 5, "vacuous: most active components must have a nonzero gradient"


def test_cloud_xland_ncmin_threads_to_obs():
    """The per-cell sea/land ncmin gate (1:1 fix #18) must thread through the obs
    builder into the bridge: (1) land vs sea give DIFFERENT Deff (the gate bites), and
    (2) the builder's Deff == clamp(2*bridge.reff, ...) with the SAME xland/ncmin."""
    f, cfg = _mk_forcing(), _cfg()
    ncl, ncs = 1.0e8, 1.0e6                                       # nc=6e7 < land thresh, > sea thresh
    sea = model_to_rttov_tensors(_mk_col(), f, cfg, xland=_t([2.0]), ncmin_land=ncl, ncmin_sea=ncs)
    land = model_to_rttov_tensors(_mk_col(), f, cfg, xland=_t([0.0]), ncmin_land=ncl, ncmin_sea=ncs)
    assert not torch.allclose(sea.deff_liq, land.deff_liq)        # the ncmin gate bites

    # consistency BOTH cases: builder Deff == clamp(2*bridge reff) with the SAME
    # xland/ncmin -- this isolates the cause to the bridge's per-cell gate (not some
    # other xland-sensitive branch) for sea AND land.
    col2 = State(*(x.unsqueeze(0) for x in _mk_col()))
    f2 = Forcing(*(x.unsqueeze(0) for x in f))
    for xl in (2.0, 0.0):
        cp = rttov_cloud_profile(col2, f2, xland=_t([xl]), ncmin_land=ncl, ncmin_sea=ncs)
        expect = torch.clamp(2.0 * cp.reff_liq.squeeze(0), _DEFF_LIQ_MIN, _DEFF_LIQ_MAX)
        got = (sea if xl == 2.0 else land).deff_liq
        assert torch.allclose(got, expect)


def test_cloud_content_oracle_and_precip_excluded():
    """Non-AD formula oracle (not self-referential): clw == rho*qc*1e3 and
    ciw == rho*(qi+qs)*1e3 [g/m^3]. And rain/graupel (qr, qg) are NOT in the cloud
    output graph (no VIS/IR Deff item -> dropped from the obs path)."""
    col, f, cfg = _mk_col(rg=True), _mk_forcing(), _cfg()
    p = model_to_rttov_tensors(col, f, cfg)
    assert torch.allclose(p.clw, f.rho * col.qc.detach() * 1.0e3)
    assert torch.allclose(p.ciw, f.rho * (col.qi.detach() + col.qs.detach()) * 1.0e3)
    out = torch.cat([p.clw, p.ciw, p.deff_liq, p.deff_ice])
    g_qr, g_qg = torch.autograd.grad(out.sum(), (col.qr, col.qg), allow_unused=True)
    assert g_qr is None and g_qg is None        # precip has no VIS/IR Deff item -> not connected


def test_cloud_interp_path_grad_flows():
    """The INTERPOLATION branch (cfg.rttov_layer_pressure set) -- not just passthrough
    -- emits cloud fields on the target layer grid with grad still flowing to leaves."""
    col, f = _mk_col(rg=True), _mk_forcing()
    cfg = RttovProfileConfig(gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
                             rttov_layer_pressure=_t([4.0e4, 6.0e4, 8.0e4]), cloud=True)
    p = model_to_rttov_tensors(col, f, cfg)
    for fld in (p.clw, p.ciw, p.deff_liq, p.deff_ice, p.cfrac):
        assert fld.shape == (3,)                                # all on the 3-layer target grid
    # Include nc/ni: they reach the output ONLY through Deff, so a detach/regression in
    # the INTERPOLATED deff_liq/deff_ice path would zero their grad and fail here (the
    # qc/qi/qs grads alone are satisfied by content and would not catch a Deff-interp break).
    g = torch.autograd.grad((p.clw + p.ciw + p.deff_liq + p.deff_ice).sum(),
                            (col.qc, col.qi, col.qs, col.nc, col.ni),
                            allow_unused=True, materialize_grads=True)
    for nm, x in zip(("qc", "qi", "qs", "nc", "ni"), g):
        assert torch.isfinite(x).all() and float(x.abs().sum()) > 0.0, f"{nm} severed in interp path"
