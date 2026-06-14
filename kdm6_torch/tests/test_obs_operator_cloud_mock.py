"""Phase 2 (all-sky cloud) -- RttovObsOp + pack_rttov_input cloud expansion.

Closes the FULL cloud autograd loop offline (mock RTTOV): J_obs -> BT ->
RttovObsOp.backward(K^T·λ_BT over HYDRO6/7 + HYDRO_DEFF6/7) -> cloud tensors ->
model_to_rttov_tensors -> leaves. This is the all-sky equivalent of the clear-sky
mock acceptance gate. Mock K is constant (BT linear in T/Q/content/Deff) so the
cloud K contraction is checked EXACTLY; the leaves->tensors link is the Phase-1
gate, so the composition is correct by chain rule.
"""
from __future__ import annotations

import functools
import math

import numpy as np
import pytest
import torch

from kdm6.state import Forcing, State
from kdm6.da_window import WindowConfig, run_da_window
from kdm6.obs.model_profile_builder import RttovProfileConfig, model_to_rttov_tensors
from kdm6.obs.rttov_input_builder import RttovInputConfig
from kdm6.obs.obs_loss import compute_obs_loss
from kdm6.obs.model_rttov_scheduler import ObsSchedule
from kdm6.obs.rttov_obs_operator import (
    ALL_SKY_CONNECTED, ObsOperatorConfig, RttovObsOp,
    assemble_obs_covector, obs_adjoint_callback)

F64 = torch.float64
NCH = 3
A = [0.10, 0.20, 0.30]        # dBT/dΣT
B = [1.0e-4, 2.0e-4, 3.0e-4]  # dBT/dΣQ
G = [0.02, 0.05, 0.03]        # dBT/dΣclw    (HYDRO6)
H = [0.04, 0.01, 0.06]        # dBT/dΣciw    (HYDRO7)
U = [0.07, 0.05, 0.09]        # dBT/dΣdeff_liq (HYDRO_DEFF6)
V = [0.11, 0.08, 0.13]        # dBT/dΣdeff_ice (HYDRO_DEFF7)
_CLOUD_K = (("HYDRO6", G), ("HYDRO7", H), ("HYDRO_DEFF6", U), ("HYDRO_DEFF7", V))


# --- mock RTTOV: BT linear in T/Q (+ cloud content/Deff when present) ----------
def _mock_run_k(rin):
    """Handles clear (T/Q only) AND cloud (T/Q + HYDRO6/7 + HYDRO_DEFF6/7) inputs."""
    prof = rin.profile
    t, q = prof["T"], prof["Q"]
    nprof, nlay = t.shape
    bt = np.zeros((nprof, NCH))
    k = {}
    kt = np.zeros((nprof, NCH, nlay)); kq = np.zeros((nprof, NCH, nlay))
    for c in range(NCH):
        bt[:, c] += A[c] * t.sum(1) + B[c] * q.sum(1)
        kt[:, c, :] = A[c]; kq[:, c, :] = B[c]
    k["T"] = kt; k["Q"] = kq
    for key, coeff in _CLOUD_K:
        if key in prof:
            arr = prof[key]
            kk = np.zeros((nprof, NCH, nlay))
            for c in range(NCH):
                bt[:, c] += coeff[c] * arr.sum(1)
                kk[:, c, :] = coeff[c]
            k[key] = kk
    return bt, k, np.zeros((nprof, NCH), dtype=int)


def _bt_torch(prof):
    """Pure-torch BT mirror (cloud-aware) for finite-difference forward."""
    ts, qs = prof.t_lay.sum(), prof.q_lay.sum()
    bt = [A[c] * ts + B[c] * qs for c in range(NCH)]
    if prof.clw is not None:
        for c in range(NCH):
            bt[c] = (bt[c] + G[c] * prof.clw.sum() + H[c] * prof.ciw.sum()
                     + U[c] * prof.deff_liq.sum() + V[c] * prof.deff_ice.sum())
    return torch.stack(bt).reshape(1, NCH)


# --- cloudy column (interior ice-slope band -> live nc/ni grads) --------------
def _t2(a, b, rg=False):
    x = torch.tensor([[a, b]], dtype=F64)
    return x.requires_grad_(True) if rg else x


def _cloudy_state(rg=False):
    return State(th=_t2(238.0, 290.0, rg), qv=_t2(4.0e-4, 1.20e-2, rg),
                 qc=_t2(0.0, 1.2e-3, rg), qr=_t2(0.0, 1.0e-4, rg),
                 qi=_t2(8.0e-4, 0.0, rg), qs=_t2(3.0e-5, 0.0, rg),
                 qg=_t2(0.0, 0.0, rg), nccn=_t2(1.0e9, 1.0e9, rg),
                 nc=_t2(0.0, 6.0e7, rg), ni=_t2(5.0e5, 0.0, rg),
                 nr=_t2(0.0, 1.0e4, rg), bg=_t2(0.0, 0.0, rg))


def _forcing():
    return Forcing(rho=_t2(0.45, 1.05), pii=_t2(0.84, 0.97),
                   p=_t2(3.0e4, 9.0e4), delz=_t2(800.0, 500.0))


def _t1(a, b):
    return torch.tensor([a, b], dtype=F64)


def _cloudy_col():
    """1-D [2] mirror of _cloudy_state for DIRECT model_to_rttov_tensors calls
    (it requires a 1-D column; the callback squeezes the 2-D state internally)."""
    return State(th=_t1(238.0, 290.0), qv=_t1(4.0e-4, 1.20e-2),
                 qc=_t1(0.0, 1.2e-3), qr=_t1(0.0, 1.0e-4),
                 qi=_t1(8.0e-4, 0.0), qs=_t1(3.0e-5, 0.0),
                 qg=_t1(0.0, 0.0), nccn=_t1(1.0e9, 1.0e9),
                 nc=_t1(0.0, 6.0e7), ni=_t1(5.0e5, 0.0),
                 nr=_t1(0.0, 1.0e4), bg=_t1(0.0, 0.0))


def _forcing_col():
    return Forcing(rho=_t1(0.45, 1.05), pii=_t1(0.84, 0.97),
                   p=_t1(3.0e4, 9.0e4), delz=_t1(800.0, 500.0))


def _cloud_cfg():
    pc = RttovProfileConfig(gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
                            rttov_layer_pressure=None,
                            rttov_level_pressure=torch.tensor([2.0e4, 6.0e4, 9.5e4], dtype=F64),
                            cloud=True)
    return ObsOperatorConfig(profile_cfg=pc,
                             input_cfg=RttovInputConfig(coef_id="ami", channels=(1, 2, 3)),
                             sigma=20.0, connected_fields=ALL_SKY_CONNECTED)


# --- PART A: exact cloud K contraction (synthetic tensors) --------------------
def test_cloud_backward_exact_contraction():
    """RttovObsOp cloud backward = K^T·λ_BT exactly. With BT.sum() (λ_BT=ones), each
    field's grad per layer is Σ_c K[c]; cloud fields contract HYDRO6/7+HYDRO_DEFF6/7."""
    nlay = 4
    g = torch.Generator().manual_seed(7)
    mk = lambda: torch.rand(1, nlay, generator=g, dtype=F64).requires_grad_(True)
    t_lay, q_lay = mk(), mk()
    clw, ciw, deff_liq, deff_ice = mk(), mk(), mk(), mk()
    cfrac = torch.full((1, nlay), 0.999999, dtype=F64)           # detached passthrough
    cfg = RttovInputConfig(coef_id="ami", channels=(1, 2, 3))
    bt, rq = RttovObsOp.apply(_mock_run_k, cfg, t_lay, q_lay, None, None,
                              clw, ciw, deff_liq, deff_ice, cfrac)
    assert bt.shape == (1, NCH) and rq.requires_grad is False
    bt.sum().backward()
    for fld, coeff in ((t_lay, A), (q_lay, B), (clw, G), (ciw, H),
                       (deff_liq, U), (deff_ice, V)):
        expect = float(sum(coeff))
        assert torch.allclose(fld.grad, torch.full((1, nlay), expect, dtype=F64)), \
            f"grad {fld.grad} != Σ_c coeff {expect}"


def test_cloud_all_or_nothing_partial_raises():
    """Cloud inputs are all-or-nothing (avoids a half-specified profile)."""
    nlay = 4
    z = torch.zeros(1, nlay, dtype=F64, requires_grad=True)
    cfg = RttovInputConfig(coef_id="ami", channels=(1, 2, 3))
    with pytest.raises(ValueError, match="all-or-nothing"):
        RttovObsOp.apply(_mock_run_k, cfg, z, z, None, None, z)   # only clw passed


def test_cloud_none_among_inputs_raises():
    """A None among the 5 cloud args (vs all-tensor) is a partial profile -> reject
    (else grad_specs/pack silently skip the None field)."""
    nlay = 4
    z = torch.zeros(1, nlay, dtype=F64, requires_grad=True)
    cfg = RttovInputConfig(coef_id="ami", channels=(1, 2, 3))
    with pytest.raises(ValueError, match="partial profile"):
        RttovObsOp.apply(_mock_run_k, cfg, z, z, None, None, None, z, z, z, z)  # clw=None


def test_clear_sky_apply_still_6_arg():
    """Regression: the 6-arg clear-sky apply path is unchanged (backward returns 6)."""
    nlay = 4
    t_lay = torch.rand(1, nlay, dtype=F64, requires_grad=True)
    q_lay = torch.rand(1, nlay, dtype=F64, requires_grad=True)
    cfg = RttovInputConfig(coef_id="ami", channels=(1, 2, 3))
    bt, rq = RttovObsOp.apply(_mock_run_k, cfg, t_lay, q_lay, None, None)
    bt.sum().backward()
    assert torch.allclose(t_lay.grad, torch.full((1, nlay), float(sum(A)), dtype=F64))
    assert torch.allclose(q_lay.grad, torch.full((1, nlay), float(sum(B)), dtype=F64))


# --- PART B: full cloud closure through model leaves --------------------------
def _obs(cloudy_prof_bt):
    return {"bt": (cloudy_prof_bt - 1.0).detach(),
            "obs_quality": torch.zeros(1, NCH, dtype=F64)}


def test_full_cloud_closure_grad_anchor():
    """model leaves -> model_to_rttov(cloud) -> RttovObsOp(cloud) -> loss ->
    autograd.grad: connected leaves (th,qv,qc,qi,qs) finite+nonzero, nc/ni finite,
    qr/qg/nccn/nr/bg legitimate zero; FD anchor on qc (cloud content path)."""
    cfg = _cloud_cfg()
    base = model_to_rttov_tensors(_cloudy_col(), _forcing_col(), cfg.profile_cfg)
    o = _obs(_bt_torch(base))
    cov = obs_adjoint_callback(0, _cloudy_state(), schedule=ObsSchedule(by_step={0: [o]}),
                               cfg=cfg, forcings=[_forcing()], run_k=_mock_run_k)
    assert isinstance(cov, State) and cov.th.shape == (1, 2)
    for fld in ("th", "qv", "qc", "qi", "qs"):
        g = getattr(cov, fld)
        assert torch.isfinite(g).all() and float(g.abs().sum()) > 0.0, f"{fld} not live"
    # nc/ni reach BT only through Deff; this column is in the unclamped ice/liquid-slope
    # band, so the number-moment adjoint must be live+nonzero. (nc/ni are in
    # ALL_SKY_CONNECTED, so a structural sever -> None would have RAISED in the callback's
    # assemble, not reached here; this additionally asserts the value is actually live.)
    for fld in ("nc", "ni"):
        g = getattr(cov, fld)
        assert torch.isfinite(g).all() and float(g.abs().sum()) > 0.0, f"{fld} severed"
    for fld in ("qr", "qg", "nccn", "nr", "bg"):       # not connected -> legitimate zero
        assert float(getattr(cov, fld).abs().sum()) == 0.0

    # central-FD anchor on qc through the FULL cloud chain (content+Deff path).
    def forward_J(state):   # 1-D column (direct model_to_rttov_tensors)
        prof = model_to_rttov_tensors(state, _forcing_col(), cfg.profile_cfg)
        return compute_obs_loss(_bt_torch(prof), o, torch.ones(1, NCH, dtype=F64),
                                cfg.sigma, delta=cfg.huber_delta)

    # FD only at the ACTIVE liquid layer (qc>0). qc[0]=0 sits on the content
    # clamp_min(0) kink, where central FD straddles the clamp (invalid) and AD
    # correctly returns the one-sided subgradient (AD-rules: no central-FD at a kink).
    h = 1.0e-8
    k = 1                                                   # qc[1] = 1.2e-3 > 0 (smooth)
    vp = _cloudy_col().qc.detach().clone(); vp[k] += h
    vm = _cloudy_col().qc.detach().clone(); vm[k] -= h
    fd = (float(forward_J(_cloudy_col()._replace(qc=vp)))
          - float(forward_J(_cloudy_col()._replace(qc=vm)))) / (2.0 * h)
    assert math.isclose(float(cov.qc[0, k]), fd, rel_tol=1e-5, abs_tol=1e-10), \
        f"qc[{k}]: AD {float(cov.qc[0, k])} != FD {fd}"


def test_cloud_assemble_nc_ni_none_is_sever():
    """nc/ni are CONNECTED in cloud mode: the bridge keeps them in-graph (zero tensor,
    not None, when inactive), so a None can only be a structural sever -> raise, never
    silently zeroed. A non-connected field (nccn/qr/qg/nr/bg) None is the legit zero."""
    leaves = _cloudy_state()
    for severed in ("nc", "ni"):
        grads = [torch.ones(1, 2, dtype=F64) if f != severed else None for f in State._fields]
        with pytest.raises(RuntimeError, match="structural sever"):
            assemble_obs_covector(leaves, grads, connected_fields=ALL_SKY_CONNECTED)
    # non-connected None -> legitimate zero; connected present -> kept.
    grads2 = [torch.ones(1, 2, dtype=F64) if f in ALL_SKY_CONNECTED else None
              for f in State._fields]
    cov = assemble_obs_covector(leaves, grads2, connected_fields=ALL_SKY_CONNECTED)
    assert float(cov.nccn.abs().sum()) == 0.0 and float(cov.nc.abs().sum()) > 0.0


def test_callback_uses_symmetric_obs_error():
    """Phase 3 wiring: with cfg.error_model + obs['bt_clear'], the callback uses the
    CA-dependent sigma. A large cloud-amount (CA) inflates sigma -> the obs gradient
    on th is smaller than under the static clear-sky sigma (same residual)."""
    from kdm6.obs.obs_loss import SymmetricObsError
    cfg_static = _cloud_cfg()._replace(sigma=2.0)          # static clear-sky sigma
    base_bt = _bt_torch(model_to_rttov_tensors(_cloudy_col(), _forcing_col(),
                                               cfg_static.profile_cfg)).detach()
    o_static = {"bt": base_bt + 30.0, "obs_quality": torch.zeros(1, NCH, dtype=F64)}
    cov_static = obs_adjoint_callback(0, _cloudy_state(), schedule=ObsSchedule(by_step={0: [o_static]}),
                                      cfg=cfg_static, forcings=[_forcing()], run_k=_mock_run_k)
    # CA model: |O-Bclr|=30 -> CA~15 > ca_cld -> sigma=sigma_cld=20 (10x the static 2).
    model = SymmetricObsError(sigma_clr=2.0, sigma_cld=20.0, ca_clr=1.0, ca_cld=10.0)
    cfg_ca = cfg_static._replace(error_model=model)
    o_ca = {**o_static, "bt_clear": base_bt}
    cov_ca = obs_adjoint_callback(0, _cloudy_state(), schedule=ObsSchedule(by_step={0: [o_ca]}),
                                  cfg=cfg_ca, forcings=[_forcing()], run_k=_mock_run_k)
    assert torch.isfinite(cov_ca.th).all()
    assert 0.0 < float(cov_ca.th.abs().sum()) < float(cov_static.th.abs().sum())


def test_callback_rejects_inf_bt_clear_in_kept_channel():
    """Production path: error_model + an inf bt_clear in a KEPT channel must raise
    (it would otherwise be silently absorbed into sigma_cld). The callback passes the
    keep-mask to symmetric_obs_error so kept-channel finiteness is enforced."""
    from kdm6.obs.obs_loss import SymmetricObsError
    cfg = _cloud_cfg()._replace(error_model=SymmetricObsError(2.0, 20.0, 1.0, 10.0))
    bt_clear = torch.zeros(1, NCH, dtype=F64)
    bt_clear[0, 1] = float("inf")                          # inf in a kept channel
    o = {"bt": torch.zeros(1, NCH, dtype=F64), "obs_quality": torch.zeros(1, NCH, dtype=F64),
         "bt_clear": bt_clear}
    with pytest.raises(ValueError, match="KEPT channel"):
        obs_adjoint_callback(0, _cloudy_state(), schedule=ObsSchedule(by_step={0: [o]}),
                             cfg=cfg, forcings=[_forcing()], run_k=_mock_run_k)


def test_callback_error_model_requires_bt_clear():
    """error_model set but obs missing 'bt_clear' -> raise (no silent static fallback)."""
    from kdm6.obs.obs_loss import SymmetricObsError
    cfg = _cloud_cfg()._replace(error_model=SymmetricObsError(2.0, 20.0, 1.0, 10.0))
    o = {"bt": torch.zeros(1, NCH, dtype=F64), "obs_quality": torch.zeros(1, NCH, dtype=F64)}  # no bt_clear
    with pytest.raises(ValueError, match="bt_clear"):
        obs_adjoint_callback(0, _cloudy_state(), schedule=ObsSchedule(by_step={0: [o]}),
                             cfg=cfg, forcings=[_forcing()], run_k=_mock_run_k)


def test_da_window_cloud_integration():
    """run_da_window with a 2-D cloudy state + cloud obs_adjoint completes and yields
    a finite adj_x0 with the obs signal reaching x0 through the cloud chain."""
    cfg = _cloud_cfg()
    forcings = [_forcing()]
    base = model_to_rttov_tensors(_cloudy_col(), _forcing_col(), cfg.profile_cfg)
    o = _obs(_bt_torch(base))
    obs_adjoint = functools.partial(obs_adjoint_callback, schedule=ObsSchedule(by_step={0: [o]}),
                                    cfg=cfg, forcings=forcings, run_k=_mock_run_k)
    res = run_da_window(_cloudy_state(), forcings, obs_adjoint, WindowConfig(dt=6.0))
    for name in State._fields:
        g = getattr(res.adj_x0, name)
        assert g.shape == (1, 2) and torch.isfinite(g).all()
    assert float(res.adj_x0.th.abs().sum()) > 0.0       # obs signal propagated to x0


# --- Phase 7: mixed BT+REFL observable requires a per-channel sigma -------------
def test_callback_rejects_scalar_sigma_with_solar_channels():
    """A mixed BT+REFL observable (solar_channels set) with a SCALAR sigma is rejected
    -- a scalar mis-weights the BT (~250 K) vs REFL (~0.5) unit systems ~50x. A
    per-channel sigma is accepted (the guard passes)."""
    o = {"bt": torch.zeros(1, NCH, dtype=F64), "obs_quality": torch.zeros(1, NCH, dtype=F64)}
    sched = ObsSchedule(by_step={0: [o]})
    cfg_bad = _cloud_cfg()._replace(solar_channels=(1,))            # scalar sigma=20.0 + solar
    with pytest.raises(ValueError, match="per-channel sigma"):
        obs_adjoint_callback(0, _cloudy_state(), schedule=sched, cfg=cfg_bad,
                             forcings=[_forcing()], run_k=_mock_run_k)
    # per-channel sigma (length NCH) + solar -> guard passes (callback returns a covector).
    cfg_ok = _cloud_cfg()._replace(solar_channels=(1,), sigma=[5.0] * NCH)
    cov = obs_adjoint_callback(0, _cloudy_state(), schedule=sched, cfg=cfg_ok,
                               forcings=[_forcing()], run_k=_mock_run_k)
    assert isinstance(cov, State)


def test_callback_scalar_sigma_ok_without_solar():
    """No solar_channels (IR-only) -> a scalar sigma stays valid (back-compat)."""
    o = {"bt": torch.zeros(1, NCH, dtype=F64), "obs_quality": torch.zeros(1, NCH, dtype=F64)}
    cov = obs_adjoint_callback(0, _cloudy_state(), schedule=ObsSchedule(by_step={0: [o]}),
                               cfg=_cloud_cfg(), forcings=[_forcing()], run_k=_mock_run_k)
    assert isinstance(cov, State)


def test_callback_rejects_run_k_solar_mismatch():
    """The injected run_k's solar set and ObsOperatorConfig.solar_channels must AGREE --
    a tagged pure-BT run_k under a solar config (or vice versa) is a silent config-
    mismatch wrong gradient, so it is rejected (Phase 7 seam)."""
    o = {"bt": torch.zeros(1, NCH, dtype=F64), "obs_quality": torch.zeros(1, NCH, dtype=F64)}
    sched = ObsSchedule(by_step={0: [o]})

    def rk(rin):
        return _mock_run_k(rin)
    rk.solar_channels = ()                                   # pure-BT run_k
    cfg = _cloud_cfg()._replace(solar_channels=(1,), sigma=[5.0] * NCH)   # config says solar
    with pytest.raises(ValueError, match="solar_channels"):
        obs_adjoint_callback(0, _cloudy_state(), schedule=sched, cfg=cfg,
                             forcings=[_forcing()], run_k=rk)
    # matched tag -> no mismatch raise (callback returns a covector).
    rk.solar_channels = (1,)
    cov = obs_adjoint_callback(0, _cloudy_state(), schedule=sched, cfg=cfg,
                               forcings=[_forcing()], run_k=rk)
    assert isinstance(cov, State)
