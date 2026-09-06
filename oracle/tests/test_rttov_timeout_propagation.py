"""Portable caller-side RTTOV timeout and case-workspace contracts.

These tests stop at the Python policy boundaries.  They use doubles for the
external runner and the multiprocessing pool; no RTTOV fixture or host data is
needed.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from kdm6.da_parallel import build_shard_specs
from kdm6.state import Forcing, State

F64 = dict(dtype=torch.float64)


def _state(batch=1, levels=2):
    return State(*(torch.ones((batch, levels), **F64)
                   for _ in State._fields))


def _forcing(batch=1, levels=2):
    return Forcing(*(torch.ones((batch, levels), **F64)
                     for _ in Forcing._fields))


def _load_lc05_runner():
    path = Path(__file__).resolve().parents[1] / "scripts/run_fulldomain_lc05.py"
    spec = importlib.util.spec_from_file_location("timeout_lc05_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lc05_parser_exposes_finite_per_call_timeout():
    runner = _load_lc05_runner()
    default = runner._build_arg_parser().parse_args(["out.json", "cases"])
    explicit = runner._build_arg_parser().parse_args(
        ["out.json", "cases", "--rttov-timeout", "12.5"])
    assert default.rttov_timeout == 300.0
    assert explicit.rttov_timeout == 12.5
    for bad in ("0", "-1", "nan", "inf"):
        with pytest.raises(SystemExit):
            runner._build_arg_parser().parse_args(
                ["out.json", "cases", "--rttov-timeout", bad])


def test_lc05_main_validates_timeout_before_output_lock(monkeypatch):
    runner = _load_lc05_runner()

    def touched(*args, **kwargs):
        raise AssertionError("output lock must not be reached for invalid policy")

    monkeypatch.setattr(runner, "_assert_fresh_outputs", touched)
    with pytest.raises(ValueError, match="positive finite"):
        runner.main("out.json", "cases", rttov_timeout=None)


def test_lc05_reader_failure_retains_distinct_run_namespaces(monkeypatch, tmp_path):
    """A failed reader run keeps its private namespace and releases OUT locks."""
    runner = _load_lc05_runner()
    import kdm6.io.frame_reader as frame_reader
    import kdm6.obs.gk2a_l1b as gk2a

    class ReachedReader(Exception):
        pass

    monkeypatch.setattr(runner, "snapshot_provenance",
                        lambda *args, **kwargs: {"rttov": {}, "inputs": {}})
    monkeypatch.setattr(gk2a, "slot_files", lambda *args, **kwargs: [])
    monkeypatch.setattr(frame_reader, "read_wrfout_frame",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            ReachedReader("stop at frame reader")))

    case_root = tmp_path / "cases"
    out_paths = [tmp_path / "first.json", tmp_path / "second.json"]
    for out_json in out_paths:
        with pytest.raises(ReachedReader, match="stop at frame reader"):
            runner.main(str(out_json), str(case_root), rttov_timeout=0.5)
        assert not Path(str(out_json) + ".lock").exists()

    run_roots = sorted(case_root.glob("run-*"))
    assert len(run_roots) == 2
    assert all(path.is_dir() for path in run_roots)
    assert run_roots[0].name != run_roots[1].name


def test_full_domain_routes_timeout_to_clear_and_allsky_boundary(monkeypatch, tmp_path):
    import multiprocessing as mp
    import kdm6.da_fulldomain as fd
    import kdm6.obs.rttov_case_writer as writer

    state = _state(batch=4, levels=2)
    forcing = _forcing(batch=4, levels=2)
    frame = SimpleNamespace(
        state=state, forcing=forcing, xland=torch.ones(4),
        meta=dict(nx=4, ny=1, valid_time_utc="2025-07-19_00:00:00"))
    obs = SimpleNamespace(
        bt=torch.ones((4, 1), **F64), obs_quality=torch.zeros((4, 1)),
        valid_time_utc="2025-07-19_00:00:00")
    seen = {}

    monkeypatch.setattr(fd, "select_membership",
                        lambda *args, **kwargs: torch.arange(4))
    monkeypatch.setattr(fd, "make_default_cvt",
                        lambda *args, **kwargs: (None, None))

    def fake_live(root, **kwargs):
        seen.setdefault("live", []).append((str(root), kwargs))
        return "fake-run-k"

    monkeypatch.setattr(writer, "make_live_run_k", fake_live)

    class Pool:
        def close(self):
            pass

        def join(self):
            pass

    monkeypatch.setattr(mp, "get_context",
                        lambda method: SimpleNamespace(Pool=lambda n: Pool()))

    class Reached(Exception):
        pass

    def fake_eval(*args, **kwargs):
        seen["eval_timeout"] = kwargs["rttov_timeout"]
        seen["eval_case_root"] = args[9]
        seen["config_has_timeout"] = "rttov_timeout" in args[8]
        raise Reached

    monkeypatch.setattr(fd, "make_fulldomain_obs_eval", fake_eval)
    with pytest.raises(Reached):
        fd.run_fulldomain_analysis(
            frame, obs,
            dict(p_lay=[500.0], p_half=[450.0, 550.0],
                 t_ref=[250.0], q_ref=[100.0]),
            str(tmp_path / "cases"), channels=(7,), obs_time=0,
            obs_offset_s=0.0, rttov_timeout=12.5)

    assert seen["eval_timeout"] == 12.5
    assert seen["config_has_timeout"] is False
    assert seen["live"] == [(str(tmp_path / "cases" / "clear"),
                              {"timeout": 12.5})]
    assert seen["eval_case_root"] == str(tmp_path / "cases")


def test_full_domain_rejects_invalid_timeout_before_membership(monkeypatch, tmp_path):
    import kdm6.da_fulldomain as fd

    monkeypatch.setattr(fd, "select_membership",
                        lambda *args, **kwargs: pytest.fail("membership reached"))
    with pytest.raises(ValueError, match="positive finite"):
        fd.run_fulldomain_analysis(
            SimpleNamespace(state=_state(batch=1), forcing=_forcing(batch=1),
                            xland=torch.ones(1), meta={}),
            SimpleNamespace(), {}, str(tmp_path / "never-created"),
            rttov_timeout=float("inf"))
    assert not (tmp_path / "never-created").exists()


def _allsky_args(case_root, timeout=17.5):
    state = _state(batch=1, levels=2)
    forcing = _forcing(batch=1, levels=2)
    return dict(
        state=torch.stack(list(state)).numpy(),
        forcing=torch.stack(list(forcing)).numpy(),
        rho_d=np.ones((1, 2)), xland=np.ones(1),
        y_bt=np.zeros((1, 1)), mask=np.zeros((1, 1)),
        t_ref=np.ones(2), q_ref=np.ones(2), p_lay=np.ones(2),
        p_half=np.ones(3), channels=(7,), coef_id="cloud",
        geometry=[dict(zenangle=10.0, azangle=0.0, sunzenangle=40.0,
                       sunazangle=0.0, latitude=30.0, longitude=120.0,
                       elevation=0.1)],
        surface=[dict(skin=dict(surftype=1, watertype=1, t=290.0,
                                salinity=35.0, foam_fraction=0.0,
                                snow_fraction=0.0,
                                fastem=[3.0, 5.0, 15.0, 0.1, 0.3]),
                      near_surface=dict(t2m=280.0, q2m=10000.0,
                                        wind_u10m=1.0, wind_v10m=1.0,
                                        wind_fetch=1000.0))],
        case_root=str(case_root), worker_id=0, grad=False,
        huber_delta=None, rttov_timeout=timeout)


def _patch_allsky_doubles(monkeypatch, seen, *, fail=False):
    import kdm6.da_driver as driver
    import kdm6.obs.model_profile_builder as builder
    import kdm6.obs.rttov_case_writer as writer
    import kdm6.obs.rttov_obs_operator as operator

    def fake_profile(*args, **kwargs):
        z = torch.ones(2, **F64)
        return SimpleNamespace(t_lay=z, q_lay=z, p_lay=z,
                               p_half=torch.ones(3, **F64), clw=z, ciw=z,
                               deff_liq=z, deff_ice=z, cfrac=z)

    def fake_blend(value, *args, **kwargs):
        return value

    def fake_live(case_dir, **kwargs):
        seen["run_k"] = (Path(case_dir), kwargs)
        return "fake-run-k"

    def fake_apply(run_k, cfg, *args):
        case_dir = seen["run_k"][0]
        seen["case_during_apply"] = case_dir
        if fail:
            (case_dir / "out").mkdir(parents=True, exist_ok=True)
            (case_dir / "out" / "run.failure.txt").write_text(
                "synthetic RTTOV tail\n", encoding="utf-8")
            raise RuntimeError("synthetic RTTOV failure")
        return torch.ones(1, **F64), torch.zeros(1, **F64)

    monkeypatch.setattr(builder, "model_to_rttov_tensors", fake_profile)
    monkeypatch.setattr(driver, "_blend_above_model_top", fake_blend)
    monkeypatch.setattr(writer, "make_live_run_k", fake_live)
    monkeypatch.setattr(operator.RttovObsOp, "apply", fake_apply)


@pytest.mark.parametrize("fail", [False, True])
def test_allsky_worker_uses_inner_case_and_preserves_failure_tail(
        monkeypatch, tmp_path, fail):
    import kdm6.obs.allsky_shard as shard

    root = tmp_path / "allsky"
    root.mkdir()
    seen = {}
    _patch_allsky_doubles(monkeypatch, seen, fail=fail)
    args = _allsky_args(root)

    if fail:
        with pytest.raises(RuntimeError, match="synthetic RTTOV failure"):
            shard._allsky_columns_worker(args)
        preserved = list((root / "failures").glob("*.txt"))
        assert len(preserved) == 1
        assert preserved[0].read_text(encoding="utf-8") == "synthetic RTTOV tail\n"
    else:
        out = shard._allsky_columns_worker(args)
        assert out["bt"].shape == (1, 1)

    assert seen["run_k"][1] == {"timeout": 17.5}
    assert seen["case_during_apply"].name == "case"
    assert seen["case_during_apply"].parent.parent == root
    remaining = [p for p in root.iterdir() if p.name != "failures"]
    assert remaining == []


def test_sharded_allsky_routes_timeout_to_each_worker(monkeypatch, tmp_path):
    import kdm6.obs.allsky_shard as shard
    from kdm6.rttov_bridge import freeze_dry_air_density

    state = _state(batch=2, levels=1)
    forcing = _forcing(batch=2, levels=1)
    root = tmp_path / "jobs"
    seen = []

    def fake_worker(args):
        seen.append(args["rttov_timeout"])
        n = args["state"].shape[1]
        return dict(j_cols=np.zeros(n), bt=np.zeros((n, 1)),
                    rq=np.zeros((n, 1)))

    class InlinePool:
        def map(self, fn, jobs):
            return [fn(job) for job in jobs]

    monkeypatch.setattr(shard, "_allsky_columns_worker", fake_worker)
    cfg = dict(rho_d=freeze_dry_air_density(state, forcing).numpy(),
               t_ref=np.ones(1), q_ref=np.ones(1), p_lay=np.ones(1),
               p_half=np.ones(2), channels=(7,), coef_id="cloud")
    out = shard.sharded_allsky(
        state, forcing, torch.tensor([0, 1]), torch.zeros((2, 1)),
        torch.zeros((2, 1)), torch.ones(2), cfg, str(root),
        n_workers=2, grad=False, pool=InlinePool(), rttov_timeout=23.0)
    assert seen == [23.0, 23.0]
    assert out["bt"].shape == (2, 1)
    assert root.is_dir()


def test_shard_builder_and_worker_route_timeout(monkeypatch, tmp_path):
    import kdm6.da_driver as driver
    import kdm6.da_parallel as parallel
    import kdm6.obs.rttov_case_writer as writer

    x = _state(batch=2, levels=1)
    f = _forcing(batch=2, levels=1)
    seen = {}

    def fake_live(case_dir, **kwargs):
        seen["live"] = (Path(case_dir), kwargs)
        return "fake-run-k"

    def fake_run(x_truth, *args):
        seen["worker_state"] = x_truth
        return SimpleNamespace(
            j_obs=2.0, n_obs_times=1,
            window=SimpleNamespace(adj_x0=x_truth))

    monkeypatch.setattr(writer, "make_live_run_k", fake_live)
    monkeypatch.setattr(driver, "run_osse_sensitivity", fake_run)
    specs = build_shard_specs(
        x, x, f, [torch.tensor([1])], n_steps=1, dt=20.0, obs_times=[],
        case_root=str(tmp_path / "shards"),
        profile_kwargs=dict(gas_units=2,
                            qv_convention="mixing_ratio_kgkg_dry"),
        input_kwargs=dict(coef_id="clear", channels=(7,)),
        rttov_timeout=31.25)
    assert specs[0].rttov_timeout == 31.25
    out = parallel._shard_worker(specs[0])
    assert seen["live"][1] == {"timeout": 31.25}
    assert out["j_obs"] == 2.0
    assert torch.equal(out["adj_x0"]["th"], x.th[1:2])


def test_shard_builder_rejects_invalid_timeout_before_case_policy(tmp_path):
    x = _state(batch=1, levels=1)
    with pytest.raises(ValueError, match="positive finite"):
        build_shard_specs(
            x, x, _forcing(batch=1, levels=1), [torch.tensor([0])],
            n_steps=1, dt=20.0, obs_times=[],
            case_root=str(tmp_path / "never-created"), profile_kwargs={},
            input_kwargs={}, rttov_timeout=None)
    assert not (tmp_path / "never-created").exists()
