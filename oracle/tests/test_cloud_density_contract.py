"""Independent gates for the frozen dry-air measure used by cloudy RTTOV.

These tests exercise the bridge, profile builder, batched all-sky entry point,
and sharding boundary with an injected runK/pool.  No RTTOV binary or live
case is required.
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from kdm6.da_driver import OsseObsConfig, batched_allsky_bt
from kdm6.obs.allsky_shard import sharded_allsky
from kdm6.obs.model_profile_builder import RttovProfileConfig, model_to_rttov_tensors
from kdm6.obs.rttov_input_builder import RttovInputConfig
from kdm6.rttov_bridge import (
    dsd_diagnostics,
    freeze_dry_air_density,
    require_dry_air_density,
    rttov_cloud_profile,
)
from kdm6.state import Forcing, State


F64 = torch.float64


def _state(*, batch: int = 1, qv: float = 0.02, qc: float = 1.0e-3) -> State:
    """Two-level, cloudy positive IC with independent columns when batched."""
    def t(values):
        row = torch.tensor(values, dtype=F64)
        return row.unsqueeze(0).expand(batch, -1).clone()

    return State(
        th=t([296.0, 285.0]), qv=t([qv, qv]),
        qc=t([qc, qc]), qr=t([1.0e-4, 8.0e-5]),
        qi=t([2.0e-4, 1.0e-4]), qs=t([1.0e-4, 5.0e-5]),
        qg=t([0.0, 0.0]), nccn=t([1.0e9, 1.0e9]),
        nc=t([1.0e8, 1.0e8]), ni=t([1.0e7, 1.0e7]),
        nr=t([1.0e4, 1.0e4]), bg=t([0.0, 0.0]),
    )


def _forcing(*, batch: int = 1, rho=(1.02, 0.95)) -> Forcing:
    def t(values):
        row = torch.tensor(values, dtype=F64)
        return row.unsqueeze(0).expand(batch, -1).clone()

    return Forcing(rho=t(rho), pii=t([0.97, 0.94]),
                   p=t([9.0e4, 7.0e4]), delz=t([500.0, 600.0]))


def test_fixed_background_density_gives_dry_basis_content_and_derivatives():
    state = _state()
    forcing = _forcing()
    rho_d = torch.ones_like(state.qv)

    profile = rttov_cloud_profile(state, forcing, rho_d=rho_d)
    # forcing.rho=1.02 and qv=.02 imply rho_d=1.00.  qc=.001 therefore
    # produces exactly 1.00 g/m3 after the bridge's kg/m3 -> g/m3 conversion.
    assert float(profile.clw[0, 0]) == pytest.approx(1.0, abs=1.0e-12)

    qv_trial = torch.full_like(state.qv, 0.03, requires_grad=True)
    trial = state._replace(qv=qv_trial)
    profile_trial = rttov_cloud_profile(trial, forcing, rho_d=rho_d)
    assert torch.equal(profile.clw, profile_trial.clw)
    g_qv = torch.autograd.grad(profile_trial.clw.sum() + 0.0 * qv_trial.sum(), qv_trial,
                               allow_unused=True, materialize_grads=True)[0]
    assert torch.equal(g_qv, torch.zeros_like(qv_trial))

    qc_leaf = state.qc.detach().clone().requires_grad_(True)
    qc_profile = rttov_cloud_profile(state._replace(qc=qc_leaf), forcing,
                                     rho_d=rho_d)
    g_qc = torch.autograd.grad(qc_profile.clw.sum(), qc_leaf)[0]
    assert torch.equal(g_qc, torch.full_like(qc_leaf, 1000.0))


def test_freeze_density_is_value_only_background_measure():
    state = _state()
    forcing = _forcing()
    rho_d = freeze_dry_air_density(state, forcing)
    assert torch.equal(rho_d, forcing.rho / (1.0 + state.qv))
    assert not rho_d.requires_grad

    for bad_qv in (float("nan"), -0.1):
        with pytest.raises(ValueError, match="background qv"):
            freeze_dry_air_density(state._replace(qv=torch.full_like(state.qv, bad_qv)),
                                   forcing)


def test_density_validation_rejects_missing_nonfinite_negative_shape_and_live_grad():
    state = _state()
    ref = state.qv
    bad = [
        None,
        torch.full((1, 1), 1.0, dtype=F64),
        torch.full_like(ref, float("nan")),
        torch.full_like(ref, -1.0),
        torch.ones_like(ref, dtype=torch.float32),
        torch.ones_like(ref, requires_grad=True),
    ]
    for rho_d in bad:
        with pytest.raises(ValueError, match="rho_d"):
            require_dry_air_density(rho_d, ref)

    cfg = RttovProfileConfig(gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
                             cloud=True)
    col = State(*(f[0].flip(-1) for f in state))
    forc_col = Forcing(*(f[0].flip(-1) for f in _forcing()))
    with pytest.raises(ValueError, match="rho_d"):
        model_to_rttov_tensors(col, forc_col, cfg)


def _cloud_profile_cfg(rho_d):
    return RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry", cloud=True,
        rttov_layer_pressure=torch.tensor([700.0, 900.0], dtype=F64),
        rttov_level_pressure=torch.tensor([600.0, 800.0, 1000.0], dtype=F64),
        rho_d=rho_d)


def test_batched_allsky_selects_distinct_frozen_density_per_column():
    state = _state(batch=2)
    forcing = _forcing(batch=2)
    rho_d = torch.tensor([[1.0, 3.0], [2.0, 4.0]], dtype=F64)

    def run_k(rin):
        n, nch, nlay = rin.nprofiles, 2, rin.nlayers
        # Make the injected observable expose HYDRO6, so distinct rho_d is
        # visible at the actual batched_allsky_bt runK boundary.
        clw = rin.profile["HYDRO6"]
        bt = np.repeat(clw[:, :1], nch, axis=1)
        zeros = np.zeros((n, nch, nlay), dtype=np.float64)
        k = {name: zeros.copy() for name in
             ("T", "Q", "HYDRO6", "HYDRO7", "HYDRO_DEFF6", "HYDRO_DEFF7")}
        return bt, k, np.zeros((n, nch), dtype=np.float64)

    cfg = OsseObsConfig(
        run_k=run_k,
        profile_cfg=_cloud_profile_cfg(rho_d),
        input_cfg=RttovInputConfig(coef_id="density-test", channels=(1, 2)),
    )
    bt, rq, _ = batched_allsky_bt(state, forcing, cfg)
    assert bt.shape == (2, 2) and bool(torch.isfinite(bt).all())
    assert torch.equal(rq, torch.zeros_like(rq))
    # The first emitted layer is the original bottom layer after the actual
    # batched_allsky_bt vertical flip: rho_d [1,3] -> [3,1], [2,4] -> [4,2].
    assert float(bt[0, 0].detach()) == pytest.approx(3.0, rel=1.0e-12)
    assert float(bt[1, 0].detach()) == pytest.approx(4.0, rel=1.0e-12)


class _RecordingPool:
    def __init__(self):
        self.jobs = None

    def map(self, _worker, jobs):
        self.jobs = jobs
        out = []
        for job in jobs:
            n, nch = job["y_bt"].shape
            k = job["state"].shape[2]
            out.append(dict(
                j_cols=np.zeros(n), bt=np.zeros((n, nch)), rq=np.zeros((n, nch)),
                adj=np.zeros((12, n, k))))
        return out


def test_sharded_allsky_selects_distinct_density_rows_before_worker_boundary():
    state = _state(batch=3)
    forcing = _forcing(batch=3)
    rho_d = torch.tensor([[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]], dtype=F64)
    cidx = torch.tensor([2, 0], dtype=torch.int64)
    y_bt = torch.zeros((3, 2), dtype=F64)
    mask = torch.ones((3, 2), dtype=F64)
    xland = torch.full((3,), 2.0, dtype=F64)
    cfg = dict(
        rho_d=rho_d.numpy(), t_ref=np.array([250.0, 260.0]),
        q_ref=np.array([1.0, 2.0]), p_lay=np.array([1.0e4, 5.0e4]),
        p_half=np.array([5.0e3, 3.0e4, 8.0e4]), channels=(1, 2),
        coef_id="density-test", oracle_root=".")
    pool = _RecordingPool()
    sharded_allsky(state, forcing, cidx, y_bt, mask, xland, cfg, ".",
                   n_workers=2, grad=False, pool=pool)
    assert pool.jobs is not None and len(pool.jobs) == 2
    assert np.array_equal(pool.jobs[0]["rho_d"], np.array([[3.0, 30.0]]))
    assert np.array_equal(pool.jobs[1]["rho_d"], np.array([[1.0, 10.0]]))


def test_batched_allsky_clears_content_and_fraction_above_model_top():
    state, forcing = _state(), _forcing()
    seen = []

    def run_k(rin):
        seen.append(rin.profile)
        zeros = np.zeros((rin.nprofiles, 1, rin.nlayers))
        k = {name: zeros.copy() for name in
             ("T", "Q", "HYDRO6", "HYDRO7", "HYDRO_DEFF6", "HYDRO_DEFF7")}
        return np.zeros((rin.nprofiles, 1)), k, np.zeros((rin.nprofiles, 1))

    cfg = _cloud_profile_cfg(torch.ones_like(state.qv))._replace(
        rttov_layer_pressure=torch.tensor([500., 700., 900.], dtype=F64),
        rttov_level_pressure=torch.tensor([400., 600., 800., 1000.], dtype=F64))
    obs_cfg = OsseObsConfig(run_k=run_k, profile_cfg=cfg,
                            input_cfg=RttovInputConfig(coef_id="top-test", channels=(1,)))
    batched_allsky_bt(state, forcing, obs_cfg)
    for key in ("HYDRO6", "HYDRO7", "CFRAC"):
        assert seen[0][key][0, 0] == 0.
        assert seen[0][key][0, 1] > 0.
    with pytest.raises(ValueError, match="layer pressure"):
        batched_allsky_bt(state, forcing, obs_cfg.__class__(
            run_k=run_k, profile_cfg=cfg._replace(rttov_layer_pressure=None),
            input_cfg=obs_cfg.input_cfg))


def test_full_domain_rejects_density_from_another_background():
    from kdm6.da_fulldomain import make_fulldomain_obs_eval
    state, forcing = _state(), _forcing()
    # The owning boundary can check provenance before any RTTOV evaluation.
    with pytest.raises(ValueError, match="this window's background"):
        make_fulldomain_obs_eval(
            state, forcing, y_bt=torch.zeros((1, 1)), y_rq=None,
            xland_sub=None, cloudy_pos=None, clear_pos=None, clear_cfg=None,
            rttov_cfg={"rho_d": np.ones((1, 2))}, case_root=".", n_workers=1, pool=None)
