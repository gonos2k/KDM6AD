"""M6 gates for P6 RttovObsOp + obs_adjoint_callback + obs_loss (design 9.1/10/14.3).

The ACCEPTANCE GATE (the headline): an end-to-end gradient anchor through the full
obs chain  J_obs -> BT -> RttovObsOp.backward(K^T·λ_BT) -> rttov tensors ->
model_to_rttov_tensors -> leaves, verified against finite differences with a MOCK
RTTOV (analytic BT + exact K, no live RTTOV / file I/O). This is the obs-operator
equivalent of the microphysics test_autograd_endtoend, and closes the
"differentiable obs operator verified piecewise only" gap.
"""
from __future__ import annotations

import functools
import math
import warnings

import pytest
import torch

from kdm6.state import State, Forcing
from kdm6.da_window import WindowConfig, run_da_window
from kdm6.runtime import make_parameters
from kdm6.obs.model_profile_builder import RttovProfileConfig, model_to_rttov_tensors
from kdm6.obs.rttov_input_builder import RttovInputConfig
from kdm6.obs.obs_loss import compute_obs_loss
from kdm6.obs.model_rttov_scheduler import ObsSchedule
from kdm6.obs.rttov_obs_operator import (
    CLEAR_SKY_CONNECTED,
    ObsOperatorConfig,
    RttovObsOp,
    assemble_obs_covector,
    obs_adjoint_callback,
)

F64 = torch.float64
NLEV_MODEL = 5
NCH = 3
A = [0.10, 0.20, 0.30]            # per-channel dBT/dT_sum
B = [1.0e-4, 2.0e-4, 3.0e-4]      # per-channel dBT/dQ_sum
P_LAYER = torch.tensor([200.0, 400.0, 600.0, 800.0], dtype=F64)   # 4 RTTOV layers
P_LEVEL = torch.tensor([150.0, 300.0, 500.0, 700.0, 900.0], dtype=F64)  # 5 levels


def _leaves(requires_grad=False):
    n = NLEV_MODEL
    th = torch.linspace(295.0, 300.0, n, dtype=F64).clone().requires_grad_(requires_grad)
    qv = torch.linspace(0.001, 0.01, n, dtype=F64).clone().requires_grad_(requires_grad)
    z = torch.zeros(n, dtype=F64)
    return State(th=th, qv=qv, qc=z, qr=z, qi=z, qs=z, qg=z, nccn=z, nc=z, ni=z, nr=z, bg=z)


def _forcing():
    n = NLEV_MODEL
    return Forcing(rho=torch.ones(n, dtype=F64), pii=torch.linspace(0.9, 1.0, n, dtype=F64),
                   p=torch.linspace(100.0, 900.0, n, dtype=F64), delz=torch.ones(n, dtype=F64))


def _profile_cfg():
    return RttovProfileConfig(gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
                              rttov_layer_pressure=P_LAYER, rttov_level_pressure=P_LEVEL)


def _input_cfg():
    return RttovInputConfig(coef_id="rtcoef_test_ami", channels=tuple(range(1, NCH + 1)))


def _mock_bt_np(t_np, q_np):
    """Analytic BT[p,c] = a_c·Σ_l T + b_c·Σ_l Q (linear -> exact constant K)."""
    import numpy as np
    nprof = t_np.shape[0]
    bt = np.zeros((nprof, NCH))
    for p in range(nprof):
        ts, qs = t_np[p].sum(), q_np[p].sum()
        for c in range(NCH):
            bt[p, c] = A[c] * ts + B[c] * qs
    return bt


def _mock_run_k(rttov_input):
    """RttovInput -> (bt, K, rad_quality). K is the exact ∂BT/∂(T,Q): constant a_c/b_c."""
    import numpy as np
    t = rttov_input.profile["T"]; q = rttov_input.profile["Q"]
    nprof, nlay = t.shape
    bt = _mock_bt_np(t, q)
    kt = np.zeros((nprof, NCH, nlay)); kq = np.zeros((nprof, NCH, nlay))
    for c in range(NCH):
        kt[:, c, :] = A[c]
        kq[:, c, :] = B[c]
    rad_quality = np.zeros((nprof, NCH), dtype=int)
    return bt, {"T": kt, "Q": kq}, rad_quality


def _mock_bt_torch(prof):
    """Pure-torch mirror of the mock BT for FD forward (same a_c/b_c)."""
    ts, qs = prof.t_lay.sum(), prof.q_lay.sum()
    return torch.stack([A[c] * ts + B[c] * qs for c in range(NCH)]).reshape(1, NCH)


def _cfg(sigma=50.0):
    return ObsOperatorConfig(profile_cfg=_profile_cfg(), input_cfg=_input_cfg(),
                             sigma=sigma, huber_delta=1.0)


def _obs_target():
    """obs BT near the base forward so the residual sits in the smooth Huber region."""
    base = model_to_rttov_tensors(_leaves(), _forcing(), _profile_cfg())
    bt = _mock_bt_torch(base).detach()
    return {"bt": (bt - 2.0), "obs_quality": torch.ones(1, NCH, dtype=F64)}


# --- ACCEPTANCE GATE: end-to-end grad anchor (J_obs -> leaves) ---------------

def test_grad_anchor_end_to_end_vs_fd():
    """autograd covector (via RttovObsOp K^T·λ_BT) == finite-difference of the full
    forward, for th AND qv — the obs-operator test_autograd_endtoend equivalent."""
    o = _obs_target()
    cfg = _cfg()
    x_t = _leaves()  # detached state the window would pass
    cov = obs_adjoint_callback(0, x_t, schedule=ObsSchedule(by_step={0: [o]}),
                               cfg=cfg, forcings=[_forcing()], run_k=_mock_run_k)
    assert isinstance(cov, State)
    assert torch.isfinite(cov.th).all() and torch.isfinite(cov.qv).all()
    assert float(cov.th.abs().sum()) > 0 and float(cov.qv.abs().sum()) > 0

    def forward_J(leaves):
        prof = model_to_rttov_tensors(leaves, _forcing(), _profile_cfg())
        bt = _mock_bt_torch(prof)
        mask = torch.ones(1, NCH, dtype=F64)
        return compute_obs_loss(bt, o, mask, cfg.sigma, delta=cfg.huber_delta)

    def J_with(fld, k, delta):
        pert = _leaves()
        v = getattr(pert, fld).detach().clone()
        v[k] += delta
        return float(forward_J(pert._replace(**{fld: v})))

    # central difference (O(h^2)) — the residual sits in the smooth quadratic Huber
    # region (no kink), and qv->Q(ppmv) is nonlinear so a one-sided FD's O(h*f'')
    # truncation would dominate (AD-rules §12: central FD is the valid reference here).
    for fld, h in (("th", 1.0e-5), ("qv", 1.0e-7)):
        cov_g = getattr(cov, fld)
        for k in range(NLEV_MODEL):
            fd = (J_with(fld, k, h) - J_with(fld, k, -h)) / (2.0 * h)
            assert math.isclose(float(cov_g[k]), fd, rel_tol=1e-6, abs_tol=1e-10), \
                f"{fld}[{k}]: AD {float(cov_g[k])} != FD {fd}"


def test_clear_sky_cloud_fields_are_zero():
    """Clear-sky: only th/qv connect; cloud/number fields are legitimate 0 (NOT severs)."""
    cov = obs_adjoint_callback(0, _leaves(), schedule=ObsSchedule(by_step={0: [_obs_target()]}),
                               cfg=_cfg(), forcings=[_forcing()], run_k=_mock_run_k)
    for fld in ("qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg"):
        assert float(getattr(cov, fld).abs().sum()) == 0.0


# --- rad_quality mask (design 8): clipped channel contributes 0 --------------

def test_rad_quality_excludes_clipped_channel():
    """A channel with rad_quality != 0 must contribute 0 to J_obs and λ_state."""
    import numpy as np

    def run_k_clip(rin):
        bt, k, rq = _mock_run_k(rin)
        rq = rq.copy(); rq[:, 1] = 10        # flag channel 1 (qflag)
        return bt, k, rq

    o = _obs_target()
    o = {**o, "bt": o["bt"] + 30.0}          # large residual on all channels...
    cov_all = obs_adjoint_callback(0, _leaves(), schedule=ObsSchedule(by_step={0: [o]}),
                                   cfg=_cfg(), forcings=[_forcing()], run_k=_mock_run_k)
    cov_clip = obs_adjoint_callback(0, _leaves(), schedule=ObsSchedule(by_step={0: [o]}),
                                    cfg=_cfg(), forcings=[_forcing()], run_k=run_k_clip)
    # clipping a contributing channel must REDUCE the gradient magnitude (its term dropped)
    assert float(cov_clip.th.abs().sum()) < float(cov_all.th.abs().sum())


# --- RttovObsOp shape + assemble_obs_covector --------------------------------

def test_rttovobsop_backward_shape_matches_input():
    leaves = _leaves(requires_grad=True)
    prof = model_to_rttov_tensors(leaves, _forcing(), _profile_cfg())
    bt, rq = RttovObsOp.apply(_mock_run_k, _input_cfg(), prof.t_lay, prof.q_lay, prof.p_lay, prof.p_half)
    assert bt.shape == (1, NCH)
    assert rq.requires_grad is False     # non-differentiable
    bt.sum().backward()
    assert leaves.th.grad is not None and torch.isfinite(leaves.th.grad).all()


def test_assemble_covector_sever_raises_on_connected_none():
    leaves = _leaves()
    grads = [None] * len(State._fields)   # th is connected but None -> sever
    with pytest.raises(RuntimeError, match="structural sever"):
        assemble_obs_covector(leaves, grads, connected_fields=CLEAR_SKY_CONNECTED)


def test_assemble_covector_qv_sever_raises():
    """qv is connected (clear-sky): a None qv grad (with th present) is a sever."""
    leaves = _leaves()
    grads = [torch.ones(NLEV_MODEL, dtype=F64) if f == "th" else None for f in State._fields]
    with pytest.raises(RuntimeError, match=r"λ_qv=None|structural sever"):
        assemble_obs_covector(leaves, grads, connected_fields=CLEAR_SKY_CONNECTED)


def test_assemble_covector_nonconnected_none_is_zero():
    leaves = _leaves()
    grads = [torch.ones(NLEV_MODEL, dtype=F64) if f in CLEAR_SKY_CONNECTED else None
             for f in State._fields]
    cov = assemble_obs_covector(leaves, grads, connected_fields=CLEAR_SKY_CONNECTED)
    assert float(cov.qc.abs().sum()) == 0.0 and float(cov.th.abs().sum()) > 0.0


def test_callback_returns_none_when_no_obs():
    cov = obs_adjoint_callback(5, _leaves(), schedule=ObsSchedule(by_step={0: [_obs_target()]}),
                               cfg=_cfg(), forcings=[_forcing()], run_k=_mock_run_k)
    assert cov is None


def test_final_time_obs_does_not_crash():
    """da_window calls obs_adjoint at the final time t == T (= len(forcings)); the
    scheduler binds obs to k=N=T (boundary), so forcings[T] would be out of range.
    The final-time obs must reuse the last forcing, not IndexError (Codex stop-review)."""
    forcings = [_forcing()]            # T = 1 step -> indices [0]; final time t = 1
    o = _obs_target()
    cov = obs_adjoint_callback(1, _leaves(), schedule=ObsSchedule(by_step={1: [o]}),
                               cfg=_cfg(), forcings=forcings, run_k=_mock_run_k)
    assert isinstance(cov, State)
    assert float(cov.th.abs().sum()) > 0.0 and float(cov.qv.abs().sum()) > 0.0


def test_empty_forcings_raises():
    o = _obs_target()
    with pytest.raises(ValueError, match="forcings is empty"):
        obs_adjoint_callback(0, _leaves(), schedule=ObsSchedule(by_step={0: [o]}),
                             cfg=_cfg(), forcings=[], run_k=_mock_run_k)


# --- run_k contract guards (review #5 missing-K, #4 transposed-K) -------------

def test_missing_k_field_raises_at_forward():
    """run_k omitting a required K field fails FAST at forward (not a deferred
    KeyError inside autograd)."""
    def run_k_no_q(rin):
        bt, k, rq = _mock_run_k(rin)
        return bt, {"T": k["T"]}, rq      # drop 'Q'
    leaves = _leaves(requires_grad=True)
    prof = model_to_rttov_tensors(leaves, _forcing(), _profile_cfg())
    with pytest.raises(KeyError, match="missing required K field"):
        RttovObsOp.apply(run_k_no_q, _input_cfg(), prof.t_lay, prof.q_lay, prof.p_lay, prof.p_half)


def test_transposed_k_shape_guard_raises():
    """A transposed (non-square) K -> wrong-but-finite grad without a shape guard
    (nch=3 != nlay=4 here, so the transpose is detectable; design F1-SHAPE)."""
    def run_k_transposed(rin):
        bt, k, rq = _mock_run_k(rin)
        kt_bad = k["T"].transpose(0, 2, 1)    # numpy: [1,nlay,nch] instead of [1,nch,nlay]
        return bt, {"T": kt_bad, "Q": k["Q"]}, rq
    leaves = _leaves(requires_grad=True)
    prof = model_to_rttov_tensors(leaves, _forcing(), _profile_cfg())
    bt, rq = RttovObsOp.apply(run_k_transposed, _input_cfg(),
                              prof.t_lay, prof.q_lay, prof.p_lay, prof.p_half)
    with pytest.raises(ValueError, match="expected"):
        bt.sum().backward()


def test_all_obs_clipped_warns():
    """Every channel rad_quality-flagged -> J=0/grad=0 but warn (not silent)."""
    def run_k_all_clip(rin):
        bt, k, rq = _mock_run_k(rin)
        rq = rq.copy(); rq[:] = 7
        return bt, k, rq
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cov = obs_adjoint_callback(0, _leaves(), schedule=ObsSchedule(by_step={0: [_obs_target()]}),
                                   cfg=_cfg(), forcings=[_forcing()], run_k=run_k_all_clip)
    assert any("masked out" in str(x.message) for x in w)
    assert float(cov.th.abs().sum()) == 0.0   # all clipped -> zero obs gradient


# --- INTEGRATION (review #4 HIGH): 2-D da_window state through the callback ----

_NCH2 = 2
_A2 = [0.10, 0.20]
_B2 = [1.0e-4, 2.0e-4]


def _state_2d():
    """2-D [1,2] single-column microphysics state (kdm6_step-valid; toy column)."""
    def t2(a, b): return torch.tensor([[a, b]], dtype=F64)
    return State(th=t2(296.8, 282.4), qv=t2(1.40e-2, 2.0e-3), qc=t2(1.0e-3, 5.0e-4),
                 qr=t2(1.0e-4, 1.0e-5), qi=t2(0.0, 1.0e-6), qs=t2(0.0, 5.0e-5),
                 qg=t2(0.0, 1.0e-5), nccn=t2(1.0e9, 1.0e9), nc=t2(1.0e8, 1.0e8),
                 ni=t2(0.0, 1.0e8), nr=t2(1.0e4, 1.0e3), bg=t2(0.0, 0.0))


def _forcing_2d_asc():
    """2-D forcing with ASCENDING p (obs path requires it; kdm6_step is p-order agnostic)."""
    def t2(a, b): return torch.tensor([[a, b]], dtype=F64)
    return Forcing(rho=t2(0.9567, 1.089), pii=t2(0.9031, 0.9704),
                   p=t2(7.0e4, 9.0e4), delz=t2(500.0, 500.0))


def _cfg_2d():
    # passthrough obs (2 model levels -> 2 layers, 3 half-levels)
    pc = RttovProfileConfig(gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
                            rttov_layer_pressure=None,
                            rttov_level_pressure=torch.tensor([6.5e4, 8.0e4, 9.5e4], dtype=F64))
    return ObsOperatorConfig(profile_cfg=pc, input_cfg=RttovInputConfig(coef_id="x", channels=(1, 2)),
                             sigma=50.0)


def _mock_run_k_2d(rin):
    import numpy as np
    t = rin.profile["T"]; q = rin.profile["Q"]; nprof, nlay = t.shape
    bt = np.zeros((nprof, _NCH2))
    for c in range(_NCH2):
        bt[:, c] = _A2[c] * t.sum(axis=1) + _B2[c] * q.sum(axis=1)
    kt = np.zeros((nprof, _NCH2, nlay)); kq = np.zeros((nprof, _NCH2, nlay))
    for c in range(_NCH2):
        kt[:, c, :] = _A2[c]; kq[:, c, :] = _B2[c]
    return bt, {"T": kt, "Q": kq}, np.zeros((nprof, _NCH2), dtype=int)


def test_rank_adapter_2d_covector():
    """obs_adjoint_callback on a 2-D [1,nlev] state (as da_window passes) returns a
    2-D covector with th/qv nonzero and cloud zero -- the 1-D/2-D rank seam."""
    o = {"bt": torch.zeros(1, _NCH2, dtype=F64), "obs_quality": torch.ones(1, _NCH2, dtype=F64)}
    cov = obs_adjoint_callback(0, _state_2d(), schedule=ObsSchedule(by_step={0: [o]}),
                               cfg=_cfg_2d(), forcings=[_forcing_2d_asc()], run_k=_mock_run_k_2d)
    assert cov.th.shape == (1, 2) and cov.qv.shape == (1, 2)   # covector keeps 2-D rank
    assert float(cov.th.abs().sum()) > 0 and float(cov.qv.abs().sum()) > 0
    for fld in ("qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg"):
        assert float(getattr(cov, fld).abs().sum()) == 0.0


def test_integration_da_window_end_to_end():
    """run_da_window with a 2-D state + obs_adjoint_callback completes (rank seam +
    da_window integration) and yields a finite, correctly-shaped adj_x0 with the
    obs signal on th/qv -- the integrated 4D-Var window gate (review #4)."""
    o = {"bt": torch.zeros(1, _NCH2, dtype=F64), "obs_quality": torch.ones(1, _NCH2, dtype=F64)}
    forcings = [_forcing_2d_asc()]
    obs_adjoint = functools.partial(
        obs_adjoint_callback, schedule=ObsSchedule(by_step={0: [o]}),
        cfg=_cfg_2d(), forcings=forcings, run_k=_mock_run_k_2d)
    res = run_da_window(_state_2d(), forcings, obs_adjoint, WindowConfig(dt=6.0))
    for name in State._fields:
        g = getattr(res.adj_x0, name)
        assert g.shape == (1, 2) and torch.isfinite(g).all()
    assert float(res.adj_x0.th.abs().sum()) > 0.0   # obs signal propagated to x0
