"""Focused guardrails for normalized-dry dual callbacks and model windows."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import torch

import kdm6.da_dual as dual
import kdm6.da_driver as driver
import kdm6.da_window as window
from kdm6.da_dual import ObsGatePolicy, default_param_prior
from kdm6.da_window import WindowConfig, WindowResult
from kdm6.rttov_bridge import freeze_dry_air_density
from kdm6.state import Forcing, State, zeros_like_state

F64 = {"dtype": torch.float64}


def _inputs(*, dry_number=True, rho_delta=0.0, t_blend=0.0, q_blend=0.0,
            rho_requires_grad=False, n_forcings=1):
    z = torch.zeros((1, 2), **F64)
    xb = State(
        th=z + 290.0, qv=z + 0.01, qc=z + 1.0e-3, qr=z + 1.0e-5,
        qi=z + 2.0e-4, qs=z + 1.0e-4, qg=z, nccn=z + 1.0e8,
        nc=z + 1.0e7, ni=z + 1.0e6, nr=z + 1.0e4, bg=z)
    forcing = Forcing(
        rho=z + 1.0, pii=z + 0.97,
        p=torch.tensor([[90000.0, 70000.0]], **F64), delz=z + 500.0)
    rho = freeze_dry_air_density(xb, forcing) + rho_delta
    if rho_requires_grad:
        rho.requires_grad_()
    profile_cfg = SimpleNamespace(
        cloud=True, dry_number=dry_number, rho_d=rho,
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=torch.tensor([700.0, 900.0], **F64),
        rttov_level_pressure=torch.tensor([600.0, 800.0, 1000.0], **F64))

    def run_k(*args, **kwargs):
        raise AssertionError("test must not launch an RTTOV callback")

    run_k.solar_channels = ()
    run_k.bt_coordinate = "kma_v3_0"
    obs_cfg = SimpleNamespace(
        run_k=run_k, profile_cfg=profile_cfg,
        input_cfg=SimpleNamespace(channels=(8,)), obs_sigma=1.0,
        t_ref=None, q_ref=None, t_blend_octaves=t_blend,
        q_blend_octaves=q_blend)
    forcings = [forcing] * n_forcings
    return xb, forcing, obs_cfg, forcings


def _patch_probe(monkeypatch, calls):
    def collect(xb, forcings, cfg, wanted):
        calls.append(("trajectory", cfg.normalized_dry))
        return {t: xb for t in wanted}

    def fake_h(x_t, forcing, obs_cfg, **kwargs):
        calls.append(("H", obs_cfg.profile_cfg.rho_d.detach().clone()))
        leaves = State(*(x.detach().clone().requires_grad_(True) for x in x_t))
        bt = leaves.th[:, :1]
        # Keep every all-sky-connected field in the graph, including fields
        # with mathematically zero tangent in this tiny fake observation.
        for name in ("qv", "qc", "qi", "qs", "nc", "ni"):
            bt = bt + 0.0 * getattr(leaves, name)[:, :1]
        return bt, torch.zeros_like(bt), leaves

    monkeypatch.setattr(window, "collect_window_trajectory", collect)
    monkeypatch.setattr(driver, "batched_allsky_bt", fake_h)


def _build_callback(xb, forcings, obs_cfg, window_cfg):
    y = torch.full((1, 1), 290.0, **F64)
    y_rq = torch.zeros_like(y)
    return dual.make_dual_frozen_obs_eval(
        xb, forcings, {0: (y, y_rq)}, obs_cfg, window_cfg,
        default_param_prior(0.0), cloud=True,
        xland=torch.tensor([2.0], **F64), ncmin_land=10.0, ncmin_sea=10.0)


@pytest.mark.parametrize(
    "changes, n_forcings, message",
    [
        ({"dry_number": False}, 1, "profile_cfg.dry_number=True"),
        ({"rho_delta": 0.5}, 1, "background/forcing dry-air density"),
        ({"rho_requires_grad": True}, 1, "rho_d must be frozen"),
        ({"t_blend": 1.0}, 1, "t_blend_octaves=0"),
        ({"q_blend": 1.0}, 1, "q_blend_octaves=0"),
        ({}, 0, "initial forcing"),
    ],
)
def test_normalized_allsky_callback_rejects_mismatches_before_h(
        monkeypatch, changes, n_forcings, message):
    calls = []
    _patch_probe(monkeypatch, calls)
    xb, _, obs_cfg, forcings = _inputs(n_forcings=n_forcings, **changes)
    cfg = WindowConfig(dt=20.0, normalized_dry=True)

    with pytest.raises(ValueError, match=message):
        _build_callback(xb, forcings, obs_cfg, cfg)
    assert calls == []


def test_normalized_allsky_callback_rejects_forward_tangent_rho_before_h(monkeypatch):
    calls = []
    _patch_probe(monkeypatch, calls)
    xb, _, obs_cfg, forcings = _inputs()
    cfg = WindowConfig(dt=20.0, normalized_dry=True)
    rho = obs_cfg.profile_cfg.rho_d
    with torch.autograd.forward_ad.dual_level():
        obs_cfg.profile_cfg.rho_d = torch.autograd.forward_ad.make_dual(
            rho, torch.zeros_like(rho))
        with pytest.raises(ValueError, match="rho_d must be frozen"):
            _build_callback(xb, forcings, obs_cfg, cfg)
    assert calls == []


def test_normalized_dual_callback_snapshots_and_fingerprints_window_mode(monkeypatch):
    calls = []
    _patch_probe(monkeypatch, calls)
    xb, _, obs_cfg, forcings = _inputs()
    cfg = WindowConfig(dt=20.0, normalized_dry=True)
    callback = _build_callback(xb, forcings, obs_cfg, cfg)

    assert callback.normalized_dry is True
    result = callback(0, xb)
    assert result.n_valid == 1

    # The window policy is part of the frozen observation-trajectory
    # signature even when the synthetic quality mask happens to be identical.
    legacy_cfg = WindowConfig(dt=20.0, normalized_dry=False)
    legacy_callback = _build_callback(xb, forcings, obs_cfg, legacy_cfg)
    legacy_result = legacy_callback(0, xb)
    assert legacy_callback.normalized_dry is False
    assert legacy_result.signature != result.signature


def test_dual_minimizer_rejects_tagged_callback_mode_mismatch_before_closure():
    def callback(t, state):
        raise AssertionError("mismatched callback must be rejected before closure")

    callback.normalized_dry = True
    cfg = WindowConfig(dt=20.0, normalized_dry=False)
    with pytest.raises(ValueError, match="does not match WindowConfig"):
        dual.run_dual_minimizer(
            None, (), callback, cfg, None, None)


def test_dual_minimizer_snapshots_window_mode_and_allows_untagged_callback(
        monkeypatch):
    z = torch.zeros((1, 2), **F64)
    xb = State(*(z.clone() for _ in State._fields))
    b_sigma = zeros_like_state(xb)
    cfg = WindowConfig(dt=20.0, normalized_dry=True)
    seen = []

    def run_window(x0, forcings, obs_adjoint, cfg_i):
        seen.append(cfg_i.normalized_dry)
        if len(seen) == 1:
            # Mutating the caller-owned config after closure 1 must not change
            # the model mode used by the minimizer's remaining closures.
            cfg.normalized_dry = False
        return WindowResult(adj_x0=zeros_like_state(x0), checkpoints=[],
                            state_final=x0)

    monkeypatch.setattr(dual, "run_da_window", run_window)
    # A custom legacy callback has no mode tag and remains composable; the
    # minimizer snapshots its WindowConfig mode before entering the optimizer.
    def untagged_callback(t, state):
        return None

    dual.run_dual_minimizer(
        xb, (), untagged_callback, cfg, b_sigma,
        default_param_prior(0.0), max_iter=1,
        policy=ObsGatePolicy(allow_zero_valid_slots=True,
                             require_obs_slots=False))
    assert len(seen) >= 2
    assert set(seen) == {True}
