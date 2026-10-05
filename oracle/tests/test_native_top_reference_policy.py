"""Check the consumed profile and native tangents, rather than only FD agreement."""
import numpy as np
import pytest
import torch

from kdm6.da_driver import OsseObsConfig, _blend_above_model_top, batched_clear_bt, batched_allsky_bt
from kdm6.obs.allsky_shard import _allsky_columns_worker
from kdm6.obs.model_profile_builder import RttovProfileConfig, qv_to_q_ppmv_moist
from kdm6.obs.rttov_input_builder import RttovInputConfig
from kdm6.rttov_bridge import freeze_dry_air_density
from test_allsky_shard_optin_modes import _column


def test_zero_width_preserves_native_values_and_tangents():
    p = torch.tensor([100., 500., 700., 900.], dtype=torch.float64)
    x = torch.tensor([[210., 250., 270., 290.]], dtype=torch.float64, requires_grad=True)
    ref = torch.tensor([220., 260., 280., 300.], dtype=torch.float64)
    out = _blend_above_model_top(x, ref, p, p[1:2], octaves=0.)
    assert torch.equal(out[:, 1:], x[:, 1:]) and out[0, 0] == ref[0]
    grad, = torch.autograd.grad(out.sum(), x)
    assert torch.equal(grad, torch.tensor([[0., 1., 1., 1.]], dtype=torch.float64))


@pytest.mark.parametrize('octaves', [1., 4.])
def test_positive_width_retains_historical_formula(octaves):
    p = torch.tensor([100., 500., 700., 900.], dtype=torch.float64)
    x, ref = p[None, :] * .1, p * .2
    w = ((torch.log(p)[None, :] - torch.log(p[1:2])[:, None]) /
         (octaves * torch.log(torch.tensor(2., dtype=p.dtype)))).clamp(0., 1.)
    expected = w * x + (1 - w) * ref[None, :]
    assert torch.equal(_blend_above_model_top(x, ref, p, p[1:2], octaves), expected)


def _profile_and_runner():
    state, forcing = _column()
    p = torch.tensor([100., 700., 900.], dtype=torch.float64)
    half = torch.tensor([50., 400., 800., 1000.], dtype=torch.float64)
    seen = []
    def run_k(rin):
        seen.append({k: v.copy() for k, v in rin.profile.items()})
        t, q = rin.profile['T'], rin.profile['Q']
        bt = np.repeat((t[:, 1] + .001 * q[:, 1])[:, None], 2, axis=1)
        k = {name: np.zeros((rin.nprofiles, 2, rin.nlayers))
             for name in ('T', 'Q', 'HYDRO6', 'HYDRO7', 'HYDRO_DEFF6', 'HYDRO_DEFF7')}
        k['T'][:, :, 1], k['Q'][:, :, 1] = 1., .001
        return bt, k, np.zeros_like(bt)
    cfg = RttovProfileConfig(2, 'mixing_ratio_kgkg_dry',
        rttov_layer_pressure=p, rttov_level_pressure=half,
        cloud=True, dry_number=True, rho_d=freeze_dry_air_density(state, forcing))
    return state, forcing, cfg, run_k, seen


@pytest.mark.parametrize('cloud', [False, True])
def test_serial_adapter_consumes_native_top_and_its_gradient(cloud):
    state, forcing, cfg, run_k, seen = _profile_and_runner()
    cfg = cfg._replace(cloud=cloud)
    obs = OsseObsConfig(run_k, cfg, RttovInputConfig('linear', (8, 13)),
        t_ref=torch.tensor([230., 222., 333.], dtype=torch.float64),
        q_ref=torch.tensor([1., 2., 3.], dtype=torch.float64),
        t_blend_octaves=0., q_blend_octaves=0.)
    bt, _, leaves = (batched_allsky_bt if cloud else batched_clear_bt)(state, forcing, obs)
    expected_q = qv_to_q_ppmv_moist(state.qv.flip(-1), gas_units=2,
                                   qv_convention='mixing_ratio_kgkg_dry')
    np.testing.assert_array_equal(seen[-1]['T'][0, 1:], (state.th * forcing.pii).flip(-1)[0].numpy())
    np.testing.assert_array_equal(seen[-1]['Q'][0, 1:], expected_q[0].numpy())
    gt, gq = torch.autograd.grad(bt.sum(), (leaves.th, leaves.qv))
    assert gt[0, -1] == 2. and gq[0, -1] > 0


def test_actual_allsky_worker_preserves_native_top(monkeypatch, tmp_path):
    import kdm6.obs.rttov_case_writer as writer
    state, forcing, cfg, run_k, seen = _profile_and_runner()
    monkeypatch.setattr(writer, 'make_live_run_k', lambda *a, **kw: run_k)
    args = dict(state=torch.stack(list(state)).numpy(), forcing=torch.stack(list(forcing)).numpy(),
        rho_d=cfg.rho_d.numpy(), xland=np.array([2.]), y_bt=np.zeros((1, 2)), mask=np.ones((1, 2)),
        t_ref=np.array([230., 222., 333.]), q_ref=np.array([1., 2., 3.]),
        p_lay=cfg.rttov_layer_pressure.numpy(), p_half=cfg.rttov_level_pressure.numpy(),
        channels=(8, 13), coef_id='linear', case_root=str(tmp_path), worker_id=0,
        grad=True, huber_delta=1., dry_number=True, ami_kma_bt=True,
        t_blend_octaves=0., q_blend_octaves=0.)
    out = _allsky_columns_worker(args)
    np.testing.assert_array_equal(seen[-1]['T'][0, 1:], state.th[0].flip(0).numpy())
    assert out['adj'][0, 0, -1] == 2. and out['adj'][1, 0, -1] > 0
