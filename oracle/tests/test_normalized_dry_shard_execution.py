"""End-to-end normalized-dry shard execution with only RTTOV mocked."""
from pathlib import Path

import numpy as np
import pytest
import torch

from kdm6.da_parallel import (
    ShardSpec, _make_normalized_dry_obs_eval, _shard_worker, build_shard_specs,
)
from kdm6.da_window import WindowConfig, run_da_window
from kdm6.da_driver import OsseObsConfig
from kdm6.obs.model_profile_builder import RttovProfileConfig
from kdm6.obs.rttov_input_builder import RttovInputConfig
from kdm6.rttov_bridge import freeze_dry_air_density
from kdm6.state import Forcing, State

F64 = dict(dtype=torch.float64)
CHANNELS = tuple(range(8, 17))


def _inputs(case_root):
    truth = State(
        th=torch.tensor([[288.0, 281.0, 274.0]], **F64),
        qv=torch.tensor([[0.020, 0.014, 0.008]], **F64),
        qc=torch.full((1, 3), 1.0e-3, **F64),
        qr=torch.full((1, 3), 1.0e-4, **F64),
        qi=torch.full((1, 3), 1.0e-4, **F64),
        qs=torch.full((1, 3), 1.0e-4, **F64),
        qg=torch.zeros((1, 3), **F64),
        nccn=torch.full((1, 3), 1.0e8, **F64),
        nc=torch.full((1, 3), 1.0e8, **F64),
        ni=torch.full((1, 3), 1.0e6, **F64),
        nr=torch.full((1, 3), 1.0e4, **F64),
        bg=torch.zeros((1, 3), **F64))
    background = truth._replace(qv=truth.qv * 0.97)
    pressure = torch.tensor([[100000.0, 80000.0, 60000.0]], **F64)
    forcing = Forcing(
        rho=torch.tensor([[1.0, 0.8, 0.6]], **F64),
        pii=(pressure / 100000.0) ** 0.286,
        p=pressure, delz=torch.tensor([[400.0, 500.0, 600.0]], **F64))
    layer = torch.tensor([600.0, 800.0, 1000.0], **F64)
    level = torch.tensor([550.0, 700.0, 900.0, 1100.0], **F64)
    rho_d = freeze_dry_air_density(background, forcing)
    profile_kwargs = dict(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry", cloud=True,
        rttov_layer_pressure=layer, rttov_level_pressure=level, rho_d=rho_d)
    input_kwargs = dict(coef_id="analytic-KMA", channels=CHANNELS)
    spec = build_shard_specs(
        truth, background, forcing, [torch.tensor([0])], n_steps=1, dt=20.0,
        obs_times=[1], case_root=str(case_root),
        profile_kwargs=profile_kwargs, input_kwargs=input_kwargs,
        obs_sigma=1.0, t_ref=torch.tensor([250.0, 265.0, 280.0], **F64),
        q_ref=torch.tensor([5.0, 200.0, 4000.0], **F64),
        xland=torch.tensor([2.0], **F64), ncmin_land=10.0, ncmin_sea=10.0,
        normalized_dry=True, fixture_case_dir="/mock/ami-native")[0]
    return truth, background, forcing, profile_kwargs, input_kwargs, spec


def test_normalized_dry_worker_runs_allsky_dual_window_and_initial_qv_fd(monkeypatch, tmp_path):
    import kdm6.obs.rttov_case_writer as writer

    truth, background, forcing, profile_kwargs, input_kwargs, spec = _inputs(tmp_path)
    run_calls = []

    def fake_factory(case_dir, *, timeout, ami_kma_bt=False, fixture_case_dir=None):
        run_calls.append((Path(case_dir), timeout, ami_kma_bt, fixture_case_dir))

        def analytic_rttov(rin):
            profile = rin.profile
            q = np.asarray(profile["Q"], dtype=np.float64)
            nprof, nlay = q.shape
            nch = len(rin.config.channels)
            layer_weights = np.linspace(0.5, 1.5, nlay, dtype=np.float64)
            channel_slope = np.linspace(3.0e-5, 7.0e-5, nch, dtype=np.float64)
            qmean = (q * layer_weights[None, :]).sum(axis=1) / layer_weights.sum()
            bt = 270.0 + qmean[:, None] * channel_slope[None, :]
            kq = (channel_slope[None, :, None]
                  * layer_weights[None, None, :] / layer_weights.sum())
            zeros = np.zeros((nprof, nch, nlay), dtype=np.float64)
            k = {"T": zeros.copy(), "Q": np.broadcast_to(kq, (nprof, nch, nlay)).copy(),
                 "HYDRO6": zeros.copy(), "HYDRO7": zeros.copy(),
                 "HYDRO_DEFF6": zeros.copy(), "HYDRO_DEFF7": zeros.copy()}
            return bt, k, np.zeros((nprof, nch), dtype=np.float64)

        analytic_rttov.solar_channels = ()
        analytic_rttov.bt_coordinate = "kma_v3_0"
        return analytic_rttov

    monkeypatch.setattr(writer, "make_live_run_k", fake_factory)
    report = _shard_worker(spec)

    assert run_calls
    assert all(call[2:] == (True, "/mock/ami-native") for call in run_calls)
    assert report["n_obs_times"] == 1
    assert np.isfinite(report["j_obs"]) and report["j_obs"] > 0.0
    assert torch.isfinite(report["adj_x0"]["qv"]).all()
    assert report["adj_x0"]["qv"].count_nonzero() > 0

    # Rebuild the same theta-b truth observations and one frozen-background
    # callback. BASE's worker result must agree, and initial-qv +/- windows
    # independently check the full KDM -> all-sky -> loss derivative.
    profile_cfg = RttovProfileConfig(**spec.profile_kwargs)
    profile_cfg = profile_cfg._replace(dry_number=True)
    input_cfg = RttovInputConfig(**input_kwargs)
    obs_cfg = OsseObsConfig(
        run_k=fake_factory("/manual/analytic", timeout=spec.rttov_timeout,
                           ami_kma_bt=True, fixture_case_dir=spec.fixture_case_dir),
        profile_cfg=profile_cfg, input_cfg=input_cfg, obs_sigma=1.0,
        t_ref=spec.t_ref, q_ref=spec.q_ref,
        t_blend_octaves=0.0, q_blend_octaves=0.0)
    window_cfg = WindowConfig(dt=20.0, xland=spec.xland,
        ncmin_land=spec.ncmin_land, ncmin_sea=spec.ncmin_sea, normalized_dry=True)
    frozen_eval = _make_normalized_dry_obs_eval(
        spec, [forcing], window_cfg, obs_cfg)
    direction = 0.01 * background.qv
    costs = {}
    base_window = None
    for label, offset in (("base", 0.0), ("plus", 1.0e-4), ("minus", -1.0e-4)):
        x0 = background if label == "base" else background._replace(
            qv=background.qv + offset * direction)
        seen = []

        def callback(t, x_t):
            value = frozen_eval(t, x_t)
            if value is None:
                return None
            seen.append(value)
            return value.adj if label == "base" else None

        window = run_da_window(x0, [forcing], callback, window_cfg)
        assert len(seen) == 1 and seen[0].n_valid == len(CHANNELS)
        costs[label] = float(seen[0].j)
        if label == "base":
            base_window = window

    assert costs["base"] == pytest.approx(report["j_obs"], rel=0.0, abs=1e-12)
    assert torch.allclose(base_window.adj_x0.qv, report["adj_x0"]["qv"],
                          rtol=1e-12, atol=1e-12)
    ad = float((base_window.adj_x0.qv * direction).sum())
    fd = (costs["plus"] - costs["minus"]) / (2.0e-4)
    rel = abs(ad - fd) / max(abs(ad), abs(fd), 1.0e-30)
    assert np.isfinite([ad, fd, rel]).all() and rel < 1.0e-5


def test_normalized_dry_shard_rejects_subtop_center_within_old_tolerance(tmp_path):
    truth, background, forcing, profile_kwargs, input_kwargs, spec = _inputs(tmp_path)
    profile_kwargs = dict(spec.profile_kwargs)
    profile_kwargs["rttov_layer_pressure"] = profile_kwargs[
        "rttov_layer_pressure"].clone()
    profile_kwargs["rttov_layer_pressure"][0] -= 5.0e-11
    with pytest.raises(ValueError, match="retain every native center pressure"):
        build_shard_specs(
            truth, background, forcing, [torch.tensor([0])], n_steps=1,
            dt=20.0, obs_times=[1], case_root=str(tmp_path),
            profile_kwargs=profile_kwargs, input_kwargs=input_kwargs,
            obs_sigma=1.0, t_ref=spec.t_ref, q_ref=spec.q_ref,
            xland=spec.xland, ncmin_land=spec.ncmin_land,
            ncmin_sea=spec.ncmin_sea, normalized_dry=True,
            fixture_case_dir=spec.fixture_case_dir)
