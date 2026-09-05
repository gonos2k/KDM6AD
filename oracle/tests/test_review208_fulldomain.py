"""Original-column auxiliary routing, frozen H, and execution-path provenance."""
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

import kdm6.da_fulldomain as fd
from kdm6.da_driver import OsseObsConfig
from kdm6.obs import allsky_shard as shard
from kdm6.obs.rttov_input_builder import RttovInputConfig
from kdm6.state import State, Forcing

F64 = dict(dtype=torch.float64)


def _state(n=4):
    a = torch.arange(n, **F64).reshape(n, 1).expand(n, 2).clone()
    return State(*(a.clone() for _ in State._fields))


def _forcing(n=4):
    return Forcing(*(torch.ones((n, 2), **F64) for _ in Forcing._fields))


def _geometry(i):
    return dict(zenangle=10.0+i, azangle=0.0, sunzenangle=45.0,
                sunazangle=0.0, latitude=30.0+i, longitude=120.0, elevation=0.1)


def _surface(i):
    return dict(skin=dict(surftype=1, watertype=1, t=290.0+i, salinity=35.0,
                         foam_fraction=0.0, snow_fraction=0.0,
                         fastem=[3.0, 5.0, 15.0, 0.1, 0.3]),
                near_surface=dict(t2m=280.0, q2m=10000.0, wind_u10m=1.0,
                                  wind_v10m=1.0, wind_fetch=1000.0))


def _clear_config():
    return OsseObsConfig(None, None, RttovInputConfig(
        coef_id='clear', channels=(7,),
        geometry=[_geometry(i) for i in range(4)],
        surface=[_surface(i) for i in range(4)]))


def test_auxiliary_selection_reorders_membership_caps_and_clear_chunks(monkeypatch):
    cfg = _clear_config()
    membership = torch.tensor([3, 1, 2])
    keep = torch.tensor([2, 0])
    selected = fd._take_clear_config(fd._take_clear_config(cfg, membership), keep)
    state = fd._take(fd._take(_state(), membership), keep)
    forcing = _forcing(2)
    seen = []

    def fake_clear(x, f, c):
        seen.append((x.th[:, 0].tolist(),
                     [g['latitude']-30 for g in c.input_cfg.geometry],
                     [s['skin']['t']-290 for s in c.input_cfg.surface]))
        return x.th[:, :1], torch.zeros((len(x.th), 1)), None

    monkeypatch.setattr(fd, '_K_INDEX_MAX', 1)
    monkeypatch.setattr(fd, 'batched_clear_bt', fake_clear)
    bt, _ = fd._clear_bt_chunked(state, forcing, selected, 1)
    assert seen == [([2.0], [2.0], [2.0]), ([3.0], [3.0], [3.0])]
    assert bt[:, 0].tolist() == [2.0, 3.0]
    assert len(cfg.input_cfg.geometry) == 4


def test_clear_partition_auxiliary_is_frozen_for_probe_and_gradient(monkeypatch):
    cfg = _clear_config()
    state, forcing = _state(), _forcing()
    seen = []

    def fake_clear(x, f, c):
        geo = torch.tensor([g['latitude'] for g in c.input_cfg.geometry], **F64)
        seen.append(geo.tolist())
        leaves = x._replace(th=x.th.detach().requires_grad_(),
                            qv=x.qv.detach().requires_grad_())
        return leaves.th[:, :1] + leaves.qv[:, :1] + geo[:, None], torch.zeros((len(geo), 1)), leaves

    def fake_cloud(x, f, pos, y, mask, xl, c, root, **kw):
        return dict(bt=torch.zeros((len(pos), 1)), rq=torch.zeros((len(pos), 1)),
                    j=0.0, adj=torch.zeros((12, len(pos), 2), **F64))

    monkeypatch.setattr(fd, 'batched_clear_bt', fake_clear)
    monkeypatch.setattr(fd, 'sharded_allsky', fake_cloud)
    y = torch.zeros((4, 1), **F64)
    evaluate = fd.make_fulldomain_obs_eval(
        state, forcing, y, y, torch.ones(4), torch.tensor([0, 2]),
        torch.tensor([3, 1]), cfg, {}, '/tmp/unused', n_workers=1, pool=object())
    cfg.input_cfg.geometry[3]['latitude'] = -20.0
    first = evaluate(1, state)
    second = evaluate(1, state)
    assert seen == [[33.0, 31.0]] * 3
    assert first.signature == second.signature
    assert first.adj.th[0].count_nonzero() == 0
    assert first.adj.th[3].count_nonzero() > 0


def test_allsky_auxiliary_reaches_each_actual_worker_column(monkeypatch):
    import kdm6.obs.model_profile_builder as builder
    import kdm6.obs.rttov_obs_operator as operator
    import kdm6.obs.rttov_case_writer as writer
    import kdm6.da_driver as driver
    seen = []

    def fake_profile(x, f, cfg, **kw):
        z = torch.ones(2, **F64)
        return SimpleNamespace(t_lay=z, q_lay=z, p_lay=z,
                               p_half=torch.ones(3), clw=z, ciw=z,
                               deff_liq=z, deff_ice=z, cfrac=z)

    def fake_apply(run, cfg, *args):
        seen.append((cfg.geometry[0]['latitude'], cfg.surface[0]['skin']['t']))
        return torch.tensor([cfg.geometry[0]['latitude']], **F64), torch.zeros(1)

    monkeypatch.setattr(builder, 'model_to_rttov_tensors', fake_profile)
    monkeypatch.setattr(operator.RttovObsOp, 'apply', fake_apply)
    monkeypatch.setattr(writer, 'make_live_run_k', lambda root: None)
    monkeypatch.setattr(driver, '_blend_above_model_top', lambda value, *a, **kw: value)
    class InlinePool:
        def map(self, fn, jobs):
            return [fn(job) for job in jobs]
    state, forcing = _state(), _forcing()
    from kdm6.rttov_bridge import freeze_dry_air_density
    config = dict(rho_d=freeze_dry_air_density(state, forcing).numpy(),
                  channels=(7,), coef_id='cloud', t_ref=[1, 1], q_ref=[1, 1],
                  p_lay=[1, 2], p_half=[0.5, 1.5, 2.5],
                  geometry=[_geometry(i) for i in range(4)],
                  surface=[_surface(i) for i in range(4)])
    out = shard.sharded_allsky(state, forcing, torch.tensor([3, 0, 2]),
        torch.zeros((4, 1)), torch.zeros((4, 1)), torch.ones(4), config,
        '/tmp/review208-no-case-created', n_workers=2, grad=False, pool=InlinePool())
    assert seen == [(33.0, 293.0), (30.0, 290.0), (32.0, 292.0)]
    assert out['bt'][:, 0].tolist() == [33.0, 30.0, 32.0]


@pytest.mark.parametrize('field', ['geometry', 'surface'])
def test_original_grid_auxiliary_cardinality_rejected_before_membership(monkeypatch, field):
    def forbidden(*args, **kwargs):
        pytest.fail('membership must follow auxiliary validation')
    monkeypatch.setattr(fd, 'select_membership', forbidden)
    value = [_geometry(0)] if field == 'geometry' else [_surface(0)]
    with pytest.raises(ValueError, match='nprofiles'):
        fd.run_fulldomain_analysis(SimpleNamespace(state=_state()), None, {},
                                  '/tmp/unused', **{field: value})


@pytest.mark.parametrize('exe_word', ['../bin/run.exe', "'../bin/run.exe'", '"../bin/run.exe"'])
def test_relative_rttov_assets_resolve_from_execution_directory(monkeypatch, tmp_path, exe_word):
    path = Path(__file__).resolve().parents[1] / 'scripts/run_fulldomain_lc05.py'
    spec = importlib.util.spec_from_file_location('review208_runner', path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    root = tmp_path / 'fixture'
    for part in ('out', 'in', 'bin', 'coefs'):
        (root / part).mkdir(parents=True)
    exe = root / 'bin/run.exe'
    exe.write_bytes(b'EXECUTED')
    (root / 'coefs/coef.dat').write_bytes(b'COEFFICIENT')
    (root / 'out/run.sh').write_text(f'{exe_word} > log\n# /ignored/comment.exe\n')
    (root / 'out/rttov_test.txt').write_text("defn%coef_prefix = '../coefs'\n")
    (root / 'in/coef.txt').write_text("defn%f_coef = 'coef.dat'\n")
    decoy = tmp_path / 'decoy/out'
    decoy.mkdir(parents=True)
    (decoy.parent / 'bin').mkdir()
    (decoy.parent / 'bin/run.exe').write_bytes(b'WRONG-CWD')
    monkeypatch.chdir(decoy)
    record = runner.rttov_provenance({'clear_fixture': root})['clear_fixture']
    assert record['exe']['path'] == str(exe.resolve())
    assert record['exe']['sha256'] == hashlib.sha256(b'EXECUTED').hexdigest()
    assert record['coef']['sha256'] == hashlib.sha256(b'COEFFICIENT').hexdigest()


def test_solar_coefficient_validation_uses_execution_directory(monkeypatch, tmp_path):
    from kdm6.obs.rttov_case_writer import _resolve_coef_path, _verify_solar_channel_types
    root = tmp_path / 'fixture'
    for part in ('out', 'in', 'coefs'):
        (root / part).mkdir(parents=True)
    coef = root / 'coefs/coef.dat'
    coef.write_text('SOLAR_SPECTRUM\n1 2\n\n')
    (root / 'out/rttov_test.txt').write_text("defn%coef_prefix = '../coefs'\n")
    (root / 'in/coef.txt').write_text("defn%f_coef = 'coef.dat'\n")
    decoy = tmp_path / 'decoy/out'
    decoy.mkdir(parents=True)
    (decoy.parent / 'coefs').mkdir()
    (decoy.parent / 'coefs/coef.dat').write_text('SOLAR_SPECTRUM\n1 0\n\n')
    monkeypatch.chdir(decoy)
    assert _resolve_coef_path(root) == coef.resolve()
    _verify_solar_channel_types(root, [1])
    coef.write_text('SOLAR_SPECTRUM\n1 0\n\n')
    with pytest.raises(ValueError, match='not pure-solar'):
        _verify_solar_channel_types(root, [1])


def test_driver_routes_original_auxiliary_through_membership_and_caps(monkeypatch):
    import multiprocessing as mp
    state = _state()._replace(qc=torch.tensor([[0., 0.], [0., 0.], [1e-4, 0.], [0., 0.]], **F64),
                             qi=torch.zeros((4, 2), **F64), qs=torch.zeros((4, 2), **F64))
    fr = SimpleNamespace(state=state, forcing=_forcing(), xland=torch.ones(4),
                         meta=dict(nx=4, ny=1, valid_time_utc='2025-07-19_00:00:00'))
    co = SimpleNamespace(bt=torch.ones((4, 16), **F64),
                         obs_quality=torch.zeros((4, 16)),
                         valid_time_utc='202507190000')
    monkeypatch.setattr(fd, 'select_membership', lambda *a, **kw: torch.tensor([3, 1, 2]))
    monkeypatch.setattr(fd, 'make_default_cvt', lambda *a, **kw: (None, None))
    class Pool:
        def close(self): pass
        def join(self): pass
    monkeypatch.setattr(mp, 'get_context', lambda method: SimpleNamespace(Pool=lambda n: Pool()))
    class ReachedEvaluator(Exception): pass
    def capture(x, f, y, rq, xl, cloudy, clear, clear_cfg, cloud_cfg, *args, **kw):
        assert x.th[:, 0].tolist() == [2.0, 3.0]
        assert [g['latitude'] for g in clear_cfg.input_cfg.geometry] == [32.0, 33.0]
        assert [g['latitude'] for g in cloud_cfg['geometry']] == [32.0, 33.0]
        assert [s['skin']['t'] for s in clear_cfg.input_cfg.surface] == [292.0, 293.0]
        assert [s['skin']['t'] for s in cloud_cfg['surface']] == [292.0, 293.0]
        assert cloudy.tolist() == [0] and clear.tolist() == [1]
        raise ReachedEvaluator
    monkeypatch.setattr(fd, 'make_fulldomain_obs_eval', capture)
    with pytest.raises(ReachedEvaluator):
        fd.run_fulldomain_analysis(fr, co, dict(p_lay=[500],p_half=[450,550],
            t_ref=[250],q_ref=[100]), '/tmp/unused', obs_time=0, dt=300,
            max_clear=1, qv_levels=1, channels=tuple(range(16)),
            geometry=[_geometry(i) for i in range(4)],
            surface=[_surface(i) for i in range(4)])
