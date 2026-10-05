"""Strict propagation and value-only parity tests for normalized-dry shards."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

import kdm6.da_driver as da_driver
import kdm6.obs.rttov_case_writer as case_writer
from kdm6.da_parallel import (
    _shard_worker, build_shard_specs, sharded_forward_window,
)
from kdm6.rttov_bridge import freeze_dry_air_density, rttov_cloud_profile
from kdm6.runtime import kdm6_step
from kdm6.state import Forcing, State, zeros_like_state

F64 = {"dtype": torch.float64}


def _batch():
    def full(value):
        return torch.full((2, 2), value, **F64)

    truth = State(
        th=full(281.0), qv=torch.tensor([[0.01, 0.02], [0.03, 0.04]], **F64),
        qc=full(1.0e-3), qr=full(1.0e-5), qi=full(2.0e-4),
        qs=full(1.0e-4), qg=full(0.0), nccn=full(1.0e8),
        nc=full(2.0e7), ni=full(1.0e6), nr=full(1.0e4), bg=full(0.0))
    background = truth._replace(qv=torch.tensor([[0.05, 0.06], [0.07, 0.08]], **F64))
    forcing = Forcing(
        rho=torch.tensor([[1.0, 0.9], [0.8, 0.7]], **F64),
        pii=full(0.98), p=torch.tensor([[9.0e4, 7.0e4], [9.0e4, 7.0e4]], **F64),
        delz=full(500.0))
    return truth, background, forcing


def _make_specs(tmp_path, *, normalized_dry, fixture=True, layer_pressure=None):
    truth, background, forcing = _batch()
    profile = {
        "gas_units": 2,
        "qv_convention": "mixing_ratio_kgkg_dry",
        "cloud": True,
    }
    if normalized_dry:
        profile["rttov_layer_pressure"] = torch.tensor(
            [700.0, 900.0] if layer_pressure is None else layer_pressure, **F64)
        profile["rttov_level_pressure"] = torch.tensor([600.0, 800.0, 1000.0], **F64)
    specs = build_shard_specs(
        truth, background, forcing, [torch.tensor([1, 0])],
        n_steps=1, dt=20.0, obs_times=[1], case_root=str(tmp_path),
        profile_kwargs=profile,
        input_kwargs={"coef_id": "fixture", "channels": tuple(range(8, 17))},
        obs_sigma=1.0, xland=torch.tensor([2.0, 1.0], **F64),
        ncmin_land=10.0, ncmin_sea=10.0,
        normalized_dry=normalized_dry,
        fixture_case_dir=(str(tmp_path / "native-grid-fixture")
                          if normalized_dry and fixture else None))
    return specs[0], truth, background, forcing


def test_shard_builder_freezes_background_density_and_worker_routes_kma_mode(
        monkeypatch, tmp_path):
    spec, _, background, forcing = _make_specs(tmp_path, normalized_dry=True)
    expected = freeze_dry_air_density(background, forcing).index_select(
        0, torch.tensor([1, 0]))
    assert spec.normalized_dry is True
    assert spec.profile_kwargs["dry_number"] is True
    assert torch.equal(spec.profile_kwargs["rho_d"], expected)
    assert spec.profile_kwargs["rho_d"].data_ptr() != expected.data_ptr()
    assert not torch.equal(spec.x_truth.qv, spec.x_background.qv)
    assert spec.fixture_case_dir == str(tmp_path / "native-grid-fixture")

    with pytest.raises(ValueError, match="explicit native-grid fixture"):
        _make_specs(tmp_path, normalized_dry=True, fixture=False)
    with pytest.raises(ValueError, match="native center pressure"):
        _make_specs(tmp_path, normalized_dry=True, layer_pressure=[700.0, 850.0])

    missing = object()
    run_k_marker = object()
    seen = {}

    def strict_make_live_run_k(case_root, *, timeout, ami_kma_bt=missing,
                               fixture_case_dir=missing):
        seen["factory"] = (Path(case_root), timeout, ami_kma_bt, fixture_case_dir)
        return run_k_marker

    def strict_run_osse_sensitivity(x_truth, x_background, forcings, obs_times,
                                    window_cfg, obs_cfg):
        assert window_cfg.normalized_dry is True
        assert obs_cfg.run_k is run_k_marker
        assert obs_cfg.input_cfg.channels == tuple(range(8, 17))
        assert obs_cfg.profile_cfg.cloud is True
        assert obs_cfg.profile_cfg.dry_number is True
        assert torch.equal(obs_cfg.profile_cfg.rho_d, expected)
        # The actual optics bridge consumes frozen background rho_d even though
        # the selected truth qv differs from the background qv.
        opt = rttov_cloud_profile(
            x_truth, forcings[0], xland=spec.xland,
            ncmin_land=10.0, ncmin_sea=10.0,
            rho_d=obs_cfg.profile_cfg.rho_d, dry_number=obs_cfg.profile_cfg.dry_number)
        torch.testing.assert_close(
            opt.clw, 1000.0 * expected * x_truth.qc, rtol=1.0e-15, atol=0.0)
        seen["profile"] = opt
        return SimpleNamespace(
            j_obs=0.0, n_obs_times=len(obs_times),
            window=SimpleNamespace(adj_x0=zeros_like_state(x_truth)))

    monkeypatch.setattr(case_writer, "make_live_run_k", strict_make_live_run_k)
    monkeypatch.setattr(da_driver, "run_osse_sensitivity", strict_run_osse_sensitivity)
    result = _shard_worker(spec)
    assert seen["factory"][0] == Path(spec.case_root)
    assert seen["factory"][2] is True
    assert seen["factory"][3] == spec.fixture_case_dir
    assert result["n_obs_times"] == 1
    assert torch.equal(result["col_idx"], torch.tensor([1, 0]))


def test_legacy_shard_worker_keeps_default_factory_and_window_contract(
        monkeypatch, tmp_path):
    spec, *_ = _make_specs(tmp_path, normalized_dry=False)
    missing = object()
    seen = {}

    def strict_make_live_run_k(case_root, *, timeout, ami_kma_bt=missing,
                               fixture_case_dir=missing):
        seen["factory"] = (case_root, ami_kma_bt, fixture_case_dir)
        return object()

    def strict_run_osse_sensitivity(x_truth, x_background, forcings, obs_times,
                                    window_cfg, obs_cfg):
        assert window_cfg.normalized_dry is False
        assert obs_cfg.profile_cfg.dry_number is False
        assert obs_cfg.profile_cfg.rho_d is None
        return SimpleNamespace(
            j_obs=0.0, n_obs_times=len(obs_times),
            window=SimpleNamespace(adj_x0=zeros_like_state(x_truth)))

    monkeypatch.setattr(case_writer, "make_live_run_k", strict_make_live_run_k)
    monkeypatch.setattr(da_driver, "run_osse_sensitivity", strict_run_osse_sensitivity)
    _shard_worker(spec)
    assert seen["factory"][1] is missing  # KMA keyword is omitted, not false-passed.
    assert seen["factory"][2] is missing


class _SynchronousPool:
    def map(self, function, jobs):
        return [function(job) for job in jobs]


def _forward_inputs():
    B, K = 4, 2

    def full(value):
        return torch.full((B, K), value, **F64)

    state = State(
        th=full(290.0), qv=full(1.4e-2), qc=full(1.0e-3), qr=full(1.0e-5),
        qi=full(0.0), qs=full(0.0), qg=full(0.0), nccn=full(1.0e8),
        nc=full(50.0), ni=full(0.0), nr=full(1.0e4), bg=full(0.0))
    forcing = Forcing(rho=full(1.0), pii=full(0.97), p=full(9.0e4),
                      delz=full(500.0))
    xland = torch.tensor([1.0, 2.0, 1.0, 2.0], **F64)
    return state, [forcing] * 3, xland


@pytest.mark.parametrize("normalized_dry", [False, True])
def test_sharded_forward_window_matches_serial_bitwise(normalized_dry):
    state, forcings, xland = _forward_inputs()
    kwargs = {"xland": xland, "ncmin_land": 100.0, "ncmin_sea": 10.0}
    mode_kwargs = {"normalized_dry": True} if normalized_dry else {}
    serial = state
    for forcing in forcings:
        serial, handle = kdm6_step(
            serial, forcing, dt=20.0, value_only=True, **kwargs, **mode_kwargs)
        handle.close()

    sharded = sharded_forward_window(
        state, forcings, 20.0, n_workers=2, pool=_SynchronousPool(),
        normalized_dry=normalized_dry, **kwargs)
    for name in State._fields:
        assert torch.equal(getattr(serial, name), getattr(sharded, name)), name
