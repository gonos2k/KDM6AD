"""Focused regressions for the DA identity/publication audit resolutions."""
from __future__ import annotations

import importlib.util
import json
import os
import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from kdm6.da_fulldomain import make_fulldomain_obs_eval
from kdm6.state import Forcing, State


F64 = dict(dtype=torch.float64)


def _state(batch=1, levels=2):
    z = torch.ones((batch, levels), **F64)
    return State(*(z.clone() for _ in State._fields))


def _forcing(batch=1, levels=2):
    z = torch.ones((batch, levels), **F64)
    return Forcing(*(z.clone() for _ in Forcing._fields))


def _load_runner():
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_fulldomain_lc05.py"
    spec = importlib.util.spec_from_file_location("audit_run_fulldomain_lc05", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_full_domain_h_snapshot_copies_nested_arrays_and_keeps_signature(monkeypatch):
    """Mutating caller-owned pressure data cannot mutate the frozen H closure."""
    xb = _state()
    forcing = _forcing()
    y_bt = torch.zeros((1, 1), **F64)
    y_rq = torch.zeros((1, 1), **F64)
    xland = torch.ones(1, **F64)
    rttov_cfg = {
        "t_ref": np.array([250.0, 250.0]),
        "q_ref": np.array([100.0, 100.0]),
        "p_lay": np.array([1.0, 2.0]),
        "p_half": np.array([0.5, 1.5, 2.5]),
        "channels": (1,), "coef_id": "cloud", "oracle_root": "/tmp/oracle",
    }
    seen = []

    def fake_clear(_x, _f, _cfg, nch):
        return (torch.zeros((0, nch), **F64),
                torch.ones((0, nch), **F64))

    def fake_allsky(x_t, _f, pos, y, mask, _xl, cfg, _root, **kwargs):
        del kwargs
        bt = (x_t.th[pos, :1] + float(cfg["p_lay"][0])).expand(-1, y.shape[1])
        seen.append(bt.detach().clone())
        return {
            "bt": bt,
            "rq": torch.zeros((pos.numel(), y.shape[1]), dtype=torch.int64),
            "j": float(mask.sum()),
            "adj": [torch.zeros((pos.numel(), xb.th.shape[1]), **F64)
                    for _ in State._fields],
        }

    import kdm6.da_fulldomain as mod
    monkeypatch.setattr(mod, "_clear_bt_chunked", fake_clear)
    monkeypatch.setattr(mod, "sharded_allsky", fake_allsky)
    obs_eval = make_fulldomain_obs_eval(
        xb, forcing, y_bt, y_rq, xland,
        torch.tensor([0]), torch.empty(0, dtype=torch.int64),
        SimpleNamespace(), rttov_cfg, "/tmp/audit-h", n_workers=1, pool=object())

    first = obs_eval(1, xb)
    rttov_cfg["p_lay"][0] = 1.5
    second = obs_eval(1, xb)
    signature = first.signature
    obs_eval.mask.zero_()
    after_public_mutation = obs_eval(1, xb)

    assert torch.equal(seen[0], seen[1])
    assert first.j == second.j
    assert first.signature == second.signature
    assert after_public_mutation.j == first.j
    assert after_public_mutation.signature == signature


def test_sensitivity_worker_receives_land_sea_controls(monkeypatch, tmp_path):
    """ShardSpec carries per-shard xland and number floors into WindowConfig."""
    import kdm6.da_driver as driver
    import kdm6.da_parallel as parallel

    x = _state(batch=2, levels=1)
    f = _forcing(batch=2, levels=1)
    xland = torch.tensor([1.0, 2.0], **F64)
    captured = {}

    def fake_run(_truth, _background, _forcing, _times, cfg, _obs):
        captured["cfg"] = cfg
        zeros = State(*(torch.zeros_like(v) for v in x))
        return SimpleNamespace(j_obs=0.0, n_obs_times=1,
                               window=SimpleNamespace(adj_x0=zeros))

    monkeypatch.setattr(driver, "run_osse_sensitivity", fake_run)
    specs = parallel.build_shard_specs(
        x, x, f, [torch.tensor([1, 0])], n_steps=1, dt=300.0,
        obs_times=[1], case_root=str(tmp_path),
        profile_kwargs={"gas_units": 2, "qv_convention": "mixing_ratio_kgkg_dry"},
        input_kwargs={"coef_id": "audit", "channels": (1,)},
        xland=xland, ncmin_land=100.0, ncmin_sea=10.0)
    assert torch.equal(specs[0].xland, torch.tensor([2.0, 1.0], **F64))
    parallel._shard_worker(specs[0])
    assert torch.equal(captured["cfg"].xland, specs[0].xland)
    assert captured["cfg"].ncmin_land == 100.0
    assert captured["cfg"].ncmin_sea == 10.0


def test_finalize_uses_same_redacted_manifest_in_payload_and_sidecar(tmp_path):
    mod = _load_runner()
    staging = tmp_path / "audit.json.fields.npz.staging"
    staging.write_bytes(b"fields")
    out = str(tmp_path / "audit.json")
    os.mkdir(out + ".lock")
    raw = {
        "cwd": "/Users/alice/private/oracle",
        "argv": ["/Users/alice/.venv/bin/python", "--cfg=/root/private.cfg",
                 "https://example.test/root/path"],
        "command": "'/Users/alice/bin/python' '--cfg=/secret/private.cfg' "
                   "'https://example.test/root/path'",
        "inputs": {"/Users/alice/private/input.nc": "input-sha"},
        "rttov": {"cloud": {"path": "/Users/alice/private/rttov",
                              "url": "https://example.test/rt"}},
        "provenance_drift": {
            "odd": "prefix /secret/hidden path:/secret/other"},
    }
    rep = {"gates": {"ok": True, "accepted": True}, "wall_s": 1.0}
    drift = {"odd": "prefix /secret/hidden path:/secret/other"}
    assert mod.finalize_artifact(rep, raw, drift, out, str(staging)) is False

    final_out = out + ".rejected"
    report = json.loads(Path(final_out).read_text())
    embedded = report["manifest"]
    sidecar = json.loads(Path(out + ".manifest.json.rejected").read_text())
    assert embedded == sidecar
    assert "outputs" in embedded and embedded["outputs"]
    public_text = json.dumps(embedded)
    assert "/Users/" not in public_text
    assert "--cfg=/root/" not in public_text
    assert "--cfg=/secret/" not in public_text
    assert "prefix /secret/" not in public_text
    assert "path:/secret/" not in public_text
    assert "https://example.test/root/path" in public_text
    assert "https://example.test/rt" in public_text
    scope = json.loads(Path(final_out).read_text())
    scope["manifest"].pop("outputs")
    canonical = hashlib.sha256(json.dumps(
        scope, indent=1, sort_keys=True).encode("utf-8")).hexdigest()
    assert embedded["output_hash_scopes"]["npz"] == "sha256 of file bytes"
    assert embedded["outputs"][Path(final_out).name] == canonical
    assert raw["cwd"].startswith("/Users/")
    os.rmdir(out + ".lock")


def test_manifest_redaction_rejects_basename_collisions():
    mod = _load_runner()
    with pytest.raises(ValueError, match="redaction key collision"):
        mod.redact_manifest({"/root/a/hash": "one", "/secret/a/hash": "two"})


def test_impact_provenance_synthetic_mode_does_not_hash_private_inputs(monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts" / "p0_4b1_impact_comparison.py"
    spec = importlib.util.spec_from_file_location("audit_impact", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    seen = []
    original = mod._sha256

    def spy(path):
        seen.append(str(path))
        return original(path)

    monkeypatch.setattr(mod, "_sha256", spy)
    prov = mod.provenance(include_trajectory=False)
    assert prov["trajectory"] is None
    assert prov["trajectory_sha256"] is None
    assert str(mod.FCST) not in seen and str(mod.MANIFEST) not in seen


def test_clear_only_full_domain_reports_precise_connected_fields(monkeypatch):
    """Run-level union and per-position metadata agree for clear-only H."""
    xb = _state(batch=2, levels=1)
    forcing = _forcing(batch=2, levels=1)
    y_bt = torch.zeros((2, 1), **F64)
    y_rq = torch.zeros((2, 1), **F64)
    xland = torch.ones(2, **F64)

    def fake_clear(x, _f, _cfg, nch):
        leaves = State(*(v.detach().clone() for v in x))
        leaves = leaves._replace(
            th=leaves.th.requires_grad_(True), qv=leaves.qv.requires_grad_(True))
        result = (leaves.th[:, :nch] + leaves.qv[:, :nch],
                  torch.zeros((x.th.shape[0], nch), **F64))
        return result if not torch.is_grad_enabled() else (*result, leaves)

    def fake_allsky(_x, _f, pos, y, _mask, _xl, _cfg, _root, **kwargs):
        del kwargs
        return {"bt": torch.zeros((pos.numel(), y.shape[1]), **F64),
                "rq": torch.zeros((pos.numel(), y.shape[1]), dtype=torch.int64),
                "j": 0.0,
                "adj": [torch.zeros((pos.numel(), 1), **F64)
                        for _ in State._fields]}

    import kdm6.da_fulldomain as mod
    monkeypatch.setattr(mod, "_clear_bt_chunked", fake_clear)
    monkeypatch.setattr(mod, "batched_clear_bt",
                        lambda x, f, cfg: fake_clear(x, f, cfg, 1))
    monkeypatch.setattr(mod, "sharded_allsky", fake_allsky)
    obs_eval = make_fulldomain_obs_eval(
        xb, forcing, y_bt, y_rq, xland, torch.empty(0, dtype=torch.int64),
        torch.tensor([0, 1]), SimpleNamespace(), {"coef_id": "cloud"},
        "/tmp/audit-clear", n_workers=1, pool=object(), obs_time=0)
    out = obs_eval(0, xb)
    assert obs_eval.connected_fields == ("th", "qv")
    assert obs_eval.connected_fields_by_position == {
        0: ("th", "qv"), 1: ("th", "qv")}
    assert out.n_valid == 2


def test_dual_cloud_adapter_forwards_frozen_land_and_ncmin_controls(monkeypatch):
    """Cloud H sees the construction-time xland/floor values at its call seam."""
    import kdm6.da_dual as dual
    import kdm6.da_driver as driver
    import kdm6.da_window as window

    xb = _state(batch=1, levels=1)
    forcing = _forcing(batch=1, levels=1)
    xland = torch.tensor([1.0], **F64)
    cfg = SimpleNamespace(obs_sigma=1.0)
    cfg_window = window.WindowConfig(
        dt=300.0, xland=xland, ncmin_land=17.0, ncmin_sea=23.0)
    seen = []

    def fake_traj(_xb, _forcings, _cfg, wanted):
        return {int(t): xb for t in wanted}

    def fake_allsky(state, _forcing, _cfg, *, xland=None,
                    ncmin_land=0.0, ncmin_sea=0.0):
        seen.append((xland.detach().clone(), ncmin_land, ncmin_sea))
        leaves = State(*(v.detach().clone().requires_grad_(True) for v in state))
        live = sum(v.sum() for v in leaves)
        bt = torch.zeros((state.th.shape[0], 1), **F64) + 0.0 * live
        rq = torch.zeros((state.th.shape[0], 1), **F64)
        return bt, rq, leaves

    monkeypatch.setattr(window, "collect_window_trajectory", fake_traj)
    monkeypatch.setattr(driver, "batched_allsky_bt", fake_allsky)
    obs = dual.make_dual_frozen_obs_eval(
        xb, [forcing], {1: (torch.zeros((1, 1), **F64),
                            torch.zeros((1, 1), **F64))}, cfg, cfg_window,
        dual.default_param_prior(), cloud=True)
    xland[0] = 2.0
    cfg_window.ncmin_land = 99.0
    out = obs(1, xb)
    assert out.n_valid == 1
    assert seen and torch.equal(seen[-1][0], torch.tensor([1.0], **F64))
    assert seen[-1][1:] == (17.0, 23.0)


def test_connected_field_metadata_serializes_positions_as_json_values():
    """The report helper emits exact fields and integer positions, not tensors."""
    import kdm6.da_fulldomain as mod
    evaluator = SimpleNamespace(
        connected_fields=("th", "qv", "qc"),
        connected_fields_by_position={0: ("th", "qv"), 3: ("th", "qv", "qc")},
        connected_fields_by_partition={
            "allsky": ("th", "qv", "qc"),
            "clear": ("th", "qv"),
            "allsky_pos": torch.tensor([3]),
            "clear_pos": torch.tensor([0]),
        })
    result = mod._connected_fields_metadata(evaluator)
    json.dumps(result)
    assert result == {
        "connected_fields": ["th", "qv", "qc"],
        "connected_fields_by_position": {
            "0": ["th", "qv"], "3": ["th", "qv", "qc"]},
        "connected_fields_by_partition": {
            "allsky": {"fields": ["th", "qv", "qc"], "positions": [3]},
            "clear": {"fields": ["th", "qv"], "positions": [0]},
        },
    }
