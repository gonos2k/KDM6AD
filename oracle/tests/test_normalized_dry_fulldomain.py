"""The upper caller must pass one policy across model, optics and loss."""
from types import SimpleNamespace

import pytest
import torch

import kdm6.da_fulldomain as fd
from kdm6.da_driver import OsseObsConfig
from kdm6.obs.rttov_input_builder import RttovInputConfig
from kdm6.rttov_bridge import freeze_dry_air_density
from kdm6.state import State, Forcing
from test_review208_fulldomain import _surface


def inputs():
    z = torch.zeros((1, 2), dtype=torch.float64)
    x = State(*(z.clone() for _ in State._fields))._replace(
        th=z + 290, qv=z + .01, qc=z + 1e-4, nc=z + 1e8, nccn=z + 1e9)
    f = Forcing(z + 1, z + .95, torch.tensor([[90000., 70000.]], dtype=torch.float64), z + 500)
    fr = SimpleNamespace(state=x, forcing=f, xland=torch.tensor([2.]),
                         meta=dict(nx=1, ny=1, valid_time_utc='2025-07-19_00:00:00'))
    co = SimpleNamespace(bt=torch.full((1, 16), 280., dtype=torch.float64),
                         obs_quality=torch.zeros((1, 16)), valid_time_utc='202507190000',
                         bias=None, channel_gate=torch.tensor([[0.]*7 + [0., 0.] + [1.]*7]))
    grids = dict(p_lay=[700., 900.], p_half=[600., 800., 1000.],
                 t_ref=[250., 290.], q_ref=[100., 10000.], cloud_fixture_case_dir='native-cloud')
    return fr, co, grids


@pytest.mark.parametrize('nine_columns', [False, True])
def test_upper_research_policy_reaches_evaluator(monkeypatch, nine_columns):
    import multiprocessing as mp
    import kdm6.da_window as window
    import kdm6.obs.rttov_case_writer as writer
    fr, co, grids = inputs()
    surface = _surface(0)
    surface['near_surface']['wind_fetch'] = 0.0
    if nine_columns:
        co.bt, co.obs_quality, co.channel_gate = (v[:, 7:] for v in (co.bt, co.obs_quality, co.channel_gate))
    calls = []
    def factory(path, *, timeout, ami_kma_bt, fixture_case_dir=None):
        assert ami_kma_bt is True
        return SimpleNamespace(bt_coordinate='kma_v3_0')
    monkeypatch.setattr(writer, 'make_live_run_k', factory)
    def collect(x, forcing, cfg, times):
        calls.append(cfg.normalized_dry)
        assert cfg.normalized_dry is True
        return {1: x}
    monkeypatch.setattr(window, 'collect_window_trajectory', collect)
    monkeypatch.setattr(fd, 'make_default_cvt', lambda *a, **kw: (None, None))
    pool = SimpleNamespace(close=lambda: None, join=lambda: None)
    monkeypatch.setattr(mp, 'get_context', lambda _: SimpleNamespace(Pool=lambda _: pool))
    class Reached(Exception): pass
    def capture(x, f, y, rq, xl, cloudy, clear, cc, rc, *a, **kw):
        assert y.shape == (1, 9) and kw['channel_gate'].sum() == 7
        assert cloudy.tolist() == [0] and clear.numel() == 0
        assert rc['dry_number'] is True and rc['ami_kma_bt'] is True
        assert rc['fixture_case_dir'] == 'native-cloud'
        assert (cc.t_blend_octaves, cc.q_blend_octaves) == (0.0, 0.0)
        assert (rc['t_blend_octaves'], rc['q_blend_octaves']) == (0.0, 0.0)
        assert torch.equal(torch.as_tensor(rc['rho_d']), f.rho / (1 + x.qv))
        assert cc.run_k.bt_coordinate == 'kma_v3_0'
        raise Reached
    monkeypatch.setattr(fd, 'make_fulldomain_obs_eval', capture)
    with pytest.raises(Reached):
        fd.run_fulldomain_analysis(fr, co, grids, 'unused', boundary=0,
            channels=tuple(range(8, 17)), dt=20., huber_delta=1., qv_levels=2,
            normalized_dry=True, observation_coordinate='kma_v3_0', surface=surface)
    assert calls == [True]


def test_legacy_surface_validation_keeps_solar_fetch_rule(monkeypatch):
    fr, co, grids = inputs()
    surface = _surface(0)
    surface['near_surface']['wind_fetch'] = 0.0
    monkeypatch.setattr(fd, 'select_membership', lambda *a, **kw: pytest.fail('too late'))
    with pytest.raises(ValueError, match='wind_fetch'):
        fd.run_fulldomain_analysis(fr, co, grids, 'unused', surface=surface)


@pytest.mark.parametrize('change, message', [
    ({'observation_coordinate': None}, 'explicitly declared'),
    ({'huber_delta': 3.}, 'diagnostic Huber'),
    ({'pseudo_rh': True}, 'pseudo-RH'),
])
def test_unsupported_research_policy_fails_before_membership(monkeypatch, change, message):
    fr, co, grids = inputs()
    monkeypatch.setattr(fd, 'select_membership', lambda *a, **kw: pytest.fail('too late'))
    args = dict(normalized_dry=True, observation_coordinate='kma_v3_0',
                channels=tuple(range(8, 17)), huber_delta=1.)
    args.update(change)
    with pytest.raises(ValueError, match=message):
        fd.run_fulldomain_analysis(fr, co, grids, 'unused', **args)


@pytest.mark.parametrize('clear', [False, True])
def test_native_grid_and_clear_fixture_fail_before_pool(monkeypatch, clear):
    import multiprocessing as mp
    import kdm6.obs.rttov_case_writer as writer
    fr, co, grids = inputs()
    if clear:
        fr.state = fr.state._replace(qc=torch.zeros_like(fr.state.qc))
        message = 'clear columns require'
    else:
        grids['p_lay'] = [700., 901.]
        message = 'every native center'
    monkeypatch.setattr(writer, 'make_live_run_k', lambda *a, **kw: None)
    monkeypatch.setattr(mp, 'get_context', lambda _: pytest.fail('must reject before pool'))
    with pytest.raises(ValueError, match=message):
        fd.run_fulldomain_analysis(fr, co, grids, 'unused', boundary=0,
            obs_time=0, channels=tuple(range(8, 17)), huber_delta=1.,
            normalized_dry=True, observation_coordinate='kma_v3_0')


def test_fractional_cost_support_rejected_before_probe(monkeypatch):
    fr, co, _ = inputs()
    monkeypatch.setattr(fd, 'sharded_allsky', lambda *a, **kw: pytest.fail('invalid gate reached probe'))
    with pytest.raises(ValueError, match='binary support'):
        fd.make_fulldomain_obs_eval(fr.state, fr.forcing, co.bt, co.obs_quality,
            fr.xland, torch.tensor([0]), torch.tensor([], dtype=torch.int64),
            None, {}, 'unused', n_workers=1, pool=None,
            channel_gate=torch.full_like(co.bt, .5))


def test_missing_channel_gate_uses_all_qc_valid_channels_but_explicit_gate_limits_support(
        monkeypatch):
    """None means the frozen raw-QC mask; an explicit binary gate narrows it."""
    fr, co, _ = inputs()
    y_bt = co.bt[:, 7:16]
    y_rq = co.obs_quality[:, 7:16]
    channels = tuple(range(8, 17))
    clear_cfg = OsseObsConfig(
        run_k=None, profile_cfg=None,
        input_cfg=RttovInputConfig(coef_id='fixture', channels=channels),
        obs_sigma=1.0)
    rho_d = freeze_dry_air_density(fr.state, fr.forcing)
    rttov_cfg = dict(rho_d=rho_d.numpy(), dry_number=True,
                     ami_kma_bt=True, channels=channels)

    def mock_rttov_probe(state, forcing, positions, target, mask, xland,
                         cfg, case_root, **kwargs):
        n = positions.numel()
        return {
            "rq": torch.zeros((n, 9), dtype=torch.float64),
            "j": 0.0,
            "adj": torch.stack([
                torch.zeros_like(getattr(state, name)[positions])
                for name in State._fields]),
        }

    monkeypatch.setattr(fd, 'sharded_allsky', mock_rttov_probe)
    gates = (
        (None, 9),
        (torch.tensor([[0., 0., 1., 1., 1., 1., 1., 1., 1.]], dtype=torch.float64), 7),
    )
    for gate, expected_nvalid in gates:
        obs_eval = fd.make_fulldomain_obs_eval(
            fr.state, fr.forcing, y_bt, y_rq, fr.xland,
            torch.tensor([0]), torch.empty(0, dtype=torch.int64),
            clear_cfg, rttov_cfg, 'unused', n_workers=1, pool=None,
            obs_time=1, huber_delta=1.0, x_slot_bg=fr.state,
            channel_gate=gate)
        result = obs_eval(1, fr.state)
        assert result.n_valid == expected_nvalid
        assert int(obs_eval.mask.sum()) == expected_nvalid
