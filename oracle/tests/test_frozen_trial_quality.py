"""Frozen-support RTTOV QC contract for full-domain callbacks."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import torch

import kdm6.da_fulldomain as fd
import kdm6.da_dual as dual
import kdm6.da_driver as driver
import kdm6.da_window as window
from kdm6.da_window import WindowConfig
from kdm6.rttov_bridge import freeze_dry_air_density
from kdm6.state import Forcing, State

F64 = {"dtype": torch.float64}


class InlinePool:
    def map(self, fn, jobs):
        return [fn(job) for job in jobs]


def _inputs():
    z = torch.zeros((1, 2), **F64)
    x = State(*(z.clone() for _ in State._fields))._replace(
        th=z + 290.0, qv=z + 0.01, qc=z + 1.0e-4, nc=z + 1.0e8)
    forcing = Forcing(
        rho=z + 1.0, pii=z + 0.97,
        p=torch.tensor([[90000.0, 70000.0]], **F64), delz=z + 500.0)
    return x, forcing


def _evaluator(monkeypatch, partition, quality_rows, *, strict=True,
               observation_quality=None):
    x, forcing = _inputs()
    y = torch.full((1, 3), 280.0, **F64)
    y_rq = (torch.tensor([[0.0, 0.0, 1.0]], **F64)
            if observation_quality is None else observation_quality)
    cloudy = torch.tensor([0]) if partition == "allsky" else torch.empty(0, dtype=torch.int64)
    clear = torch.tensor([0]) if partition == "clear" else torch.empty(0, dtype=torch.int64)
    calls = {"quality": iter(quality_rows)}

    def fake_allsky(state, _forcing, cidx, y_bt, mask, *_args, grad, **_kwargs):
        n = int(cidx.numel())
        rq = next(calls["quality"]) if n else torch.empty((0, 3), **F64)
        bt = torch.full((n, 3), 300.0, **F64)
        j = sum(float(fd._part_loss(bt[i], y_bt[int(pos)], mask[int(pos)], 1.0))
                for i, pos in enumerate(cidx.tolist())) if grad else 0.0
        adj = tuple(torch.zeros((n, 2), **F64) for _ in State._fields)
        return {"rq": rq, "bt": bt, "j": j, "adj": adj}

    def fake_clear(state, _forcing, _cfg):
        rq = next(calls["quality"])
        leaves = State(*(getattr(state, name).detach().clone().requires_grad_(
            name in ("th", "qv")) for name in State._fields))
        base = leaves.th[:, :1] + 0.0 * leaves.qv[:, :1]
        bt = base.expand(-1, 3)
        return bt, rq, leaves

    monkeypatch.setattr(fd, "sharded_allsky", fake_allsky)
    monkeypatch.setattr(fd, "batched_clear_bt", fake_clear)
    cfg = SimpleNamespace(input_cfg=SimpleNamespace())
    rttov_cfg = {"rho_d": freeze_dry_air_density(x, forcing)}
    obs_eval = fd.make_fulldomain_obs_eval(
        x, forcing, y, y_rq, torch.tensor([2.0]), cloudy, clear,
        cfg, rttov_cfg, "/tmp/frozen-quality-test", n_workers=1,
        pool=InlinePool(), huber_delta=1.0,
        require_frozen_quality=strict)
    return obs_eval, x


@pytest.mark.parametrize("partition", ["allsky", "clear"])
def test_trial_quality_rejects_same_count_support_replacement(monkeypatch, partition):
    clean = torch.zeros((1, 3), **F64)
    replacement = torch.tensor([[0.0, 32768.0, 0.0]], **F64)
    obs_eval, x = _evaluator(monkeypatch, partition, [clean, replacement])

    assert obs_eval.mask.tolist() == [[1.0, 1.0, 0.0]]
    assert obs_eval.require_frozen_quality is True
    with pytest.raises(ValueError, match="flags a frozen-support"):
        obs_eval(1, x)


@pytest.mark.parametrize("partition", ["allsky", "clear"])
def test_preflagged_background_channel_stays_excluded_when_trial_clears_it(
        monkeypatch, partition):
    background = torch.tensor([[0.0, 32768.0, 0.0]], **F64)
    trial = torch.zeros((1, 3), **F64)
    obs_quality = torch.tensor([[0.0, 0.0, 32768.0]], **F64)
    obs_eval, x = _evaluator(
        monkeypatch, partition, [background, trial],
        observation_quality=obs_quality)

    assert obs_eval.mask.tolist() == [[1.0, 0.0, 0.0]]
    result = obs_eval(1, x)
    assert result.n_valid == 1
    assert result.signature


@pytest.mark.parametrize("partition", ["allsky", "clear"])
def test_preflagged_background_channel_can_clear_while_frozen_channel_flags(
        monkeypatch, partition):
    background = torch.tensor([[0.0, 32768.0, 0.0]], **F64)
    trial = torch.tensor([[32768.0, 0.0, 0.0]], **F64)
    obs_quality = torch.tensor([[0.0, 0.0, 32768.0]], **F64)
    obs_eval, x = _evaluator(
        monkeypatch, partition, [background, trial],
        observation_quality=obs_quality)

    with pytest.raises(ValueError, match="flags a frozen-support"):
        obs_eval(1, x)


@pytest.mark.parametrize("partition", ["allsky", "clear"])
def test_excluded_quality_can_change_and_cost_uses_fixed_support(monkeypatch, partition):
    baseline = torch.zeros((1, 3), **F64)
    trial = torch.tensor([[0.0, 0.0, 32768.0]], **F64)
    obs_eval, x = _evaluator(monkeypatch, partition, [baseline, trial, trial])

    first = obs_eval(1, x)
    second = obs_eval(1, x)
    assert first.n_valid == second.n_valid == 2
    assert first.signature == second.signature
    assert float(first.j) == pytest.approx(float(second.j))


@pytest.mark.parametrize("bad_quality, message", [
    (torch.zeros((1, 2), **F64), "shape"),
    (torch.tensor([[0.0, float("nan"), 0.0]], **F64), "finite"),
])
@pytest.mark.parametrize("partition", ["allsky", "clear"])
def test_trial_quality_rejects_bad_shape_or_nonfinite(monkeypatch, partition,
                                                      bad_quality, message):
    clean = torch.zeros((1, 3), **F64)
    obs_eval, x = _evaluator(monkeypatch, partition, [clean, bad_quality])

    with pytest.raises(ValueError, match=message):
        obs_eval(1, x)


def test_legacy_default_keeps_trial_quality_opt_out(monkeypatch):
    clean = torch.zeros((1, 3), **F64)
    changed = torch.tensor([[0.0, 32768.0, 0.0]], **F64)
    obs_eval, x = _evaluator(monkeypatch, "allsky", [clean, changed], strict=False)

    assert obs_eval.require_frozen_quality is False
    assert obs_eval(1, x).n_valid == 2


def _dual_callback(monkeypatch, qualities, *, normalized_dry=True,
                   observation_quality=None):
    x, forcing = _inputs()
    profile = SimpleNamespace(
        cloud=True, dry_number=True, rho_d=freeze_dry_air_density(x, forcing),
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=torch.tensor([700.0, 900.0], **F64),
        rttov_level_pressure=torch.tensor([600.0, 800.0, 1000.0], **F64))
    def run_k(*_args, **_kwargs):
        raise AssertionError("fake all-sky callback should be used")
    run_k.solar_channels = ()
    run_k.bt_coordinate = "kma_v3_0"
    obs_cfg = SimpleNamespace(
        run_k=run_k, profile_cfg=profile,
        input_cfg=SimpleNamespace(channels=(8, 9, 10)), obs_sigma=1.0,
        t_ref=None, q_ref=None, t_blend_octaves=0.0, q_blend_octaves=0.0)
    monkeypatch.setattr(window, "collect_window_trajectory",
                        lambda xb, _f, _cfg, times: {t: xb for t in times})
    quality_rows = iter(qualities)

    def fake_allsky(state, _forcing, _cfg, **_kwargs):
        leaves = State(*(v.detach().clone().requires_grad_(True) for v in state))
        bt = leaves.th[:, :1].expand(-1, 3)
        for name in ("qv", "qc", "qi", "qs", "nc", "ni"):
            bt = bt + 0.0 * getattr(leaves, name)[:, :1]
        return bt, next(quality_rows), leaves

    monkeypatch.setattr(driver, "batched_allsky_bt", fake_allsky)
    cfg = WindowConfig(dt=20.0, normalized_dry=normalized_dry)
    y_rq = (torch.zeros((1, 3), **F64) if observation_quality is None
            else observation_quality)
    callback = dual.make_dual_frozen_obs_eval(
        x, [forcing], {0: (torch.full((1, 3), 290.0, **F64),
                           y_rq)},
        obs_cfg, cfg, dual.default_param_prior(0.0), cloud=True,
        xland=torch.tensor([2.0], **F64), ncmin_land=10.0, ncmin_sea=10.0)
    return callback, x


def test_normalized_dry_dual_companion_checks_trial_quality(monkeypatch):
    callback, x = _dual_callback(
        monkeypatch, [torch.zeros((1, 3), **F64),
                      torch.tensor([[0.0, 32768.0, 0.0]], **F64)])

    assert callback.require_frozen_quality is True
    with pytest.raises(ValueError, match="flags a frozen-support"):
        callback(0, x)


def test_normalized_dry_dual_allows_excluded_trial_quality_change(monkeypatch):
    background = torch.tensor([[0.0, 32768.0, 0.0]], **F64)
    trial = torch.zeros((1, 3), **F64)
    obs_quality = torch.tensor([[0.0, 0.0, 32768.0]], **F64)
    callback, x = _dual_callback(
        monkeypatch, [background, trial, trial], observation_quality=obs_quality)

    first = callback(0, x)
    second = callback(0, x)
    assert first.n_valid == second.n_valid == 1
    assert float(first.j) == pytest.approx(float(second.j))


@pytest.mark.parametrize("bad_quality, message", [
    (torch.zeros((1, 2), **F64), "shape"),
    (torch.tensor([[0.0, float("nan"), 0.0]], **F64), "finite"),
])
def test_normalized_dry_dual_rejects_malformed_trial_quality(
        monkeypatch, bad_quality, message):
    callback, x = _dual_callback(
        monkeypatch, [torch.zeros((1, 3), **F64), bad_quality])

    with pytest.raises(ValueError, match=message):
        callback(0, x)


def test_default_dual_companion_keeps_trial_quality_opt_out(monkeypatch):
    clean = torch.zeros((1, 3), **F64)
    changed = torch.tensor([[0.0, 32768.0, 0.0]], **F64)
    callback, x = _dual_callback(
        monkeypatch, [clean, changed], normalized_dry=False)

    assert callback.require_frozen_quality is False
    assert callback(0, x).n_valid == 3
