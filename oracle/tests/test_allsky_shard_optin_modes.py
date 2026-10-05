"""Focused propagation tests for normalized-dry/KMA all-sky shard modes."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from kdm6.obs import allsky_shard as shard
from kdm6.rttov_bridge import freeze_dry_air_density
from kdm6.state import Forcing, State

F64 = dict(dtype=torch.float64)


def _column():
    state = State(
        th=torch.tensor([[280.0, 281.0]], **F64),
        qv=torch.tensor([[0.01, 0.02]], **F64),
        qc=torch.tensor([[4.0e-3, 1.0e-3]], **F64),
        qr=torch.full((1, 2), 1.0e-4, **F64),
        qi=torch.full((1, 2), 2.0e-4, **F64),
        qs=torch.full((1, 2), 1.0e-4, **F64),
        qg=torch.zeros((1, 2), **F64),
        nccn=torch.full((1, 2), 1.0e8, **F64),
        nc=torch.tensor([[3.0, 4.0]], **F64),
        ni=torch.tensor([[5.0, 6.0]], **F64),
        nr=torch.full((1, 2), 1.0e4, **F64),
        bg=torch.zeros((1, 2), **F64),
    )
    forcing = Forcing(
        rho=torch.ones((1, 2), **F64), pii=torch.ones((1, 2), **F64),
        p=torch.tensor([[90000.0, 70000.0]], **F64),
        delz=torch.full((1, 2), 500.0, **F64))
    return state, forcing


def _worker_args(case_root, *, modes=True):
    state, forcing = _column()
    rho_d = torch.tensor([[0.5, 1.0]], **F64)
    return dict(
        state=torch.stack(list(state)).numpy(),
        forcing=torch.stack(list(forcing)).numpy(),
        rho_d=rho_d.numpy(), xland=np.array([2.0]),
        y_bt=np.array([[0.75, 1.0]]), mask=np.ones((1, 2)),
        t_ref=np.array([280.0, 281.0]), q_ref=np.array([1000.0, 2000.0]),
        p_lay=np.array([700.0, 900.0]), p_half=np.array([600.0, 800.0, 1000.0]),
        channels=(8, 13), coef_id="fixture", case_root=str(case_root), worker_id=0,
        grad=True, huber_delta=0.5, rttov_timeout=12.0,
        **({"dry_number": True, "ami_kma_bt": True,
            "fixture_case_dir": "/fixtures/ami-native"} if modes else {}))


def _patch_worker(monkeypatch, seen):
    import kdm6.da_driver as driver
    import kdm6.obs.model_profile_builder as builder
    import kdm6.obs.rttov_case_writer as writer
    import kdm6.obs.rttov_obs_operator as operator

    def fake_profile(leaves, forcing, cfg, **kwargs):
        seen["profile_cfg"] = cfg
        seen["profile_kwargs"] = kwargs
        rho = cfg.rho_d.unsqueeze(0)
        z = torch.zeros_like(leaves.qc)
        return SimpleNamespace(
            t_lay=leaves.th, q_lay=leaves.qv,
            p_lay=torch.tensor([700.0, 900.0], **F64),
            p_half=torch.tensor([600.0, 800.0, 1000.0], **F64),
            clw=1000.0 * rho * leaves.qc,
            ciw=rho * (leaves.qi + leaves.qs),
            deff_liq=leaves.nc, deff_ice=leaves.ni,
            cfrac=torch.ones_like(leaves.qc))

    def fake_blend(value, *args, **kwargs):
        return value

    def fake_live(case_dir, *, timeout, ami_kma_bt=False, fixture_case_dir=None):
        seen["factory"] = (Path(case_dir), {
            "timeout": timeout,
            **({"ami_kma_bt": ami_kma_bt} if ami_kma_bt else {}),
            **({"fixture_case_dir": fixture_case_dir}
               if fixture_case_dir is not None else {}),
        })
        return object()

    def fake_apply(run_k, cfg, t, q, p_lay, p_half, clw, ciw,
                   deff_liq, deff_ice, cfrac):
        # The zero-weight terms keep the worker's expected connected fields in
        # the graph while the analytic observable responds only to cloud water.
        bt = (clw.reshape(-1) + 0.0 * (t + q + ciw + deff_liq + deff_ice).reshape(-1))
        return bt, torch.zeros_like(bt)

    monkeypatch.setattr(builder, "model_to_rttov_tensors", fake_profile)
    monkeypatch.setattr(driver, "_blend_above_model_top", fake_blend)
    monkeypatch.setattr(writer, "make_live_run_k", fake_live)
    monkeypatch.setattr(operator.RttovObsOp, "apply", fake_apply)


def test_worker_consumes_optin_flags_with_frozen_density_and_huber_gradient(
        monkeypatch, tmp_path):
    seen = {}
    _patch_worker(monkeypatch, seen)
    root = tmp_path / "cases"
    root.mkdir()
    out = shard._allsky_columns_worker(_worker_args(root))

    assert seen["profile_cfg"].dry_number is True
    # The shard flips the supplied fixed background measure into profile order;
    # it does not derive a new density from trial/output qv.
    torch.testing.assert_close(seen["profile_cfg"].rho_d,
                               torch.tensor([1.0, 0.5], **F64), rtol=0.0, atol=0.0)
    assert "entry_qv" not in seen["profile_kwargs"]
    case_path, factory_kwargs = seen["factory"]
    assert case_path.name == "case"
    assert factory_kwargs == {
        "timeout": 12.0, "ami_kma_bt": True,
        "fixture_case_dir": "/fixtures/ami-native"}

    # L=[1,2], y=[.75,1], sigma=1 K and Huber delta=.5:
    # J=.5*.25^2 + .5*(1-.25) = .40625; dJ/dL=[.25,.5].
    assert out["j_cols"].tolist() == pytest.approx([0.40625], abs=1e-14)
    assert out["adj"][2, 0].tolist() == pytest.approx([250.0, 250.0], abs=1e-12)
    assert out["bt"].tolist() == [[1.0, 2.0]]
    assert out["rq"].tolist() == [[0.0, 0.0]]


def test_default_worker_keeps_legacy_factory_kwargs(monkeypatch, tmp_path):
    seen = {}
    _patch_worker(monkeypatch, seen)
    root = tmp_path / "cases"
    root.mkdir()
    args = _worker_args(root, modes=False)
    args["channels"] = (7, 8)  # native mode has no KMA channel restriction
    out = shard._allsky_columns_worker(args)
    assert seen["profile_cfg"].dry_number is False
    assert seen["factory"][1] == {"timeout": 12.0}
    assert out["bt"].shape == (1, 2)


@pytest.mark.parametrize("bad_cfg", [
    {"dry_number": 1}, {"ami_kma_bt": np.bool_(True)},
    {"ami_kma_bt": True, "channels": (7, 8)},
])
def test_sharded_flags_fail_before_pool_or_case_root_creation(bad_cfg, tmp_path):
    state, forcing = _column()
    rho_d = freeze_dry_air_density(state, forcing).numpy()
    cfg = dict(rho_d=rho_d, t_ref=[280.0, 281.0], q_ref=[1000.0, 2000.0],
               p_lay=[700.0, 900.0], p_half=[600.0, 800.0, 1000.0],
               channels=(8, 13), coef_id="fixture")
    cfg.update(bad_cfg)
    root = tmp_path / "never-created"

    class ForbiddenPool:
        def map(self, *args, **kwargs):
            pytest.fail("invalid mode must be rejected before worker dispatch")

    with pytest.raises(ValueError):
        shard.sharded_allsky(
            state, forcing, torch.tensor([0]), torch.zeros((1, 2), **F64),
            torch.ones((1, 2), **F64), torch.ones(1, **F64), cfg, str(root),
            n_workers=1, grad=False, pool=ForbiddenPool())
    assert not root.exists()


def test_sharded_job_preserves_flags_fixture_and_column_order(monkeypatch, tmp_path):
    state, forcing = _column()
    state = State(*(torch.cat((field, field + 1.0), dim=0) for field in state))
    forcing = Forcing(*(torch.cat((field, field), dim=0) for field in forcing))
    cfg = dict(
        rho_d=freeze_dry_air_density(state, forcing).numpy(),
        t_ref=[280.0, 281.0], q_ref=[1000.0, 2000.0],
        p_lay=[700.0, 900.0], p_half=[600.0, 800.0, 1000.0],
        channels=(8, 13), coef_id="fixture", dry_number=True, ami_kma_bt=True,
        fixture_case_dir="/fixtures/ami-native")
    seen = []

    def fake_worker(job):
        seen.append((job["dry_number"], job["ami_kma_bt"], job["fixture_case_dir"],
                     job["state"][0, 0, 0]))
        n = job["state"].shape[1]
        return dict(j_cols=np.zeros(n), bt=np.repeat(job["state"][0, :, :1], 2, axis=1),
                    rq=np.zeros((n, 2)))

    class InlinePool:
        def map(self, fn, jobs):
            return [fn(job) for job in jobs]

    monkeypatch.setattr(shard, "_allsky_columns_worker", fake_worker)
    out = shard.sharded_allsky(
        state, forcing, torch.tensor([1, 0]), torch.zeros((2, 2), **F64),
        torch.ones((2, 2), **F64), torch.ones(2, **F64), cfg,
        str(tmp_path / "jobs"), n_workers=2, grad=False, pool=InlinePool())
    assert seen == [(True, True, "/fixtures/ami-native", 281.0),
                    (True, True, "/fixtures/ami-native", 280.0)]
    assert out["bt"][:, 0].tolist() == [281.0, 280.0]
