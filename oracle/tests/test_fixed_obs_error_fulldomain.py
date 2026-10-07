"""Fixed nuisance error assumptions, not calibrated R or scientific approval."""
from types import SimpleNamespace

import pytest
import torch

import kdm6.da_fulldomain as fd
from kdm6.da_driver import OsseObsConfig
from kdm6.obs.obs_loss import compute_obs_loss
from kdm6.obs.rttov_input_builder import RttovInputConfig
from kdm6.state import State, Forcing
from test_normalized_dry_fulldomain import inputs

F64 = dict(dtype=torch.float64)


def test_fixed_loss_sign_scaling_fd_and_legacy_equivalence():
    bt = torch.tensor([[2.0, 7.0, float('nan')]], requires_grad=True, **F64)
    y = torch.tensor([[1.0, 3.0, float('nan')]], **F64)
    mask = torch.tensor([[1.0, 1.0, 0.0]], **F64)
    sigma = torch.tensor([2.0, 0.5, 3.0], **F64)
    bias = torch.tensor([0.2, -0.1, 0.0], **F64)
    j = fd._part_loss(bt, y, mask, 1.0, obs_sigma=sigma, obs_bias=bias)
    gradient, = torch.autograd.grad(j, bt)
    torch.testing.assert_close(gradient, torch.tensor([[0.2, 2.0, 0.0]], **F64))
    direction = torch.tensor([[0.1, -0.3, 0.0]], **F64)
    h = 1e-5
    plus = fd._part_loss(bt.detach()+h*direction, y, mask, 1., obs_sigma=sigma, obs_bias=bias)
    minus = fd._part_loss(bt.detach()-h*direction, y, mask, 1., obs_sigma=sigma, obs_bias=bias)
    torch.testing.assert_close((plus-minus)/(2*h), (gradient*direction).sum(), rtol=1e-8, atol=1e-10)
    old = fd._part_loss(bt, y, mask, 1.0)
    new = fd._part_loss(bt, y, mask, 1.0, obs_sigma=torch.ones(3), obs_bias=torch.zeros(3))
    assert torch.equal(old, new)


@pytest.mark.parametrize('sigma', [True, [1., 2.], [[1., 2., 3.]], 0., -1., 1e-15, float('nan'), float('inf'), 1+1j])
def test_fixed_sigma_rejects_bad_policy(sigma):
    with pytest.raises(ValueError):
        fd._freeze_fixed_obs_errors(torch.zeros((2, 3)), sigma, None)


def test_fixed_inputs_preserve_python_precision_and_copy():
    y = torch.zeros((2, 3), **F64)
    sigma, bias = fd._freeze_fixed_obs_errors(y, 0.1, 0.2)
    assert sigma[0] == torch.tensor(0.1, **F64)
    assert bias[0, 0] == torch.tensor(0.2, **F64)
    supplied = torch.tensor([1., 2., 3.], **F64)
    correction = torch.ones((2, 3), **F64)
    sigma, bias = fd._freeze_fixed_obs_errors(y, supplied, correction)
    supplied.fill_(9.); correction.fill_(8.)
    assert sigma.tolist() == [1., 2., 3.]
    assert bias.tolist() == [[1., 1., 1.], [1., 1., 1.]]


def test_fixed_callback_freezes_and_signs_error_inputs_for_clear_route(monkeypatch):
    z = torch.ones((2, 2), **F64)
    state = State(*(z.clone() for _ in State._fields))._replace(th=z*280, qv=z*.01)
    forcing = Forcing(z, z, z*80000, z*500)
    cfg = OsseObsConfig(run_k=None, profile_cfg=None,
        input_cfg=RttovInputConfig(coef_id='test', channels=(8, 9)), obs_sigma=1.)
    def clear(x, f, c):
        leaves=x._replace(th=x.th.detach().clone().requires_grad_(), qv=x.qv.detach().clone().requires_grad_())
        bt=leaves.th+10*leaves.qv
        return bt, torch.zeros_like(bt), leaves
    monkeypatch.setattr(fd, 'batched_clear_bt', clear)
    monkeypatch.setattr(fd, 'sharded_allsky', lambda x,f,pos,*a,**kw: dict(rq=torch.zeros((0,2)),j=0.,adj=torch.zeros((12,0,2),**F64)))
    target=torch.full((2,2),279.,**F64); quality=torch.zeros_like(target)
    sigma=torch.tensor([1.,2.],**F64); bias=torch.tensor([[.1,.2],[.3,.4]],**F64)
    gate=torch.tensor([[1.,0.],[1.,1.]],**F64)
    def make(sig,correction):
        return fd.make_fulldomain_obs_eval(state,forcing,target,quality,torch.ones(2),
            torch.empty(0,dtype=torch.int64),torch.tensor([1,0]),cfg,{},'unused',
            n_workers=1,pool=None,huber_delta=1.,obs_sigma=sig,obs_bias=correction,channel_gate=gate)
    evaluate=make(sigma,bias); result=evaluate(1,state)
    expected=compute_obs_loss(state.th+10*state.qv,{'bt':target,'bias':bias},gate,sigma,delta=1.)
    assert result.j == float(expected)
    assert make(sigma*2,bias)(1,state).signature != result.signature
    assert make(sigma,bias+1)(1,state).signature != result.signature
    sigma.fill_(99);bias.fill_(99);target.fill_(99);gate.zero_()
    after=evaluate(1,state)
    assert after.j == result.j and after.signature == result.signature
    torch.testing.assert_close(after.adj.qv,result.adj.qv)


@pytest.mark.parametrize('nine_columns',[False,True])
def test_upper_fixed_errors_select_co_bias_and_explicit_sigma(monkeypatch,nine_columns):
    import multiprocessing as mp
    import kdm6.obs.rttov_case_writer as writer
    fr,co,grids=inputs();co.bias=torch.arange(16,dtype=torch.float64).reshape(1,16)*.1
    if nine_columns:
        for name in ('bt','obs_quality','channel_gate','bias'):
            setattr(co,name,getattr(co,name)[:,7:16])
    sigma=torch.arange(1,10,dtype=torch.float64)
    monkeypatch.setattr(writer,'make_live_run_k',lambda *a,**kw: None)
    monkeypatch.setattr(fd,'make_default_cvt',lambda *a,**kw:(None,None))
    monkeypatch.setattr(mp,'get_context',lambda _:SimpleNamespace(Pool=lambda _:SimpleNamespace(close=lambda:None,join=lambda:None)))
    class Captured(Exception): pass
    def capture(*args,**kwargs):
        assert kwargs['obs_sigma'].tolist()==sigma.tolist()
        torch.testing.assert_close(kwargs['obs_bias'],torch.arange(7,16,dtype=torch.float64).reshape(1,9)*.1)
        raise Captured
    monkeypatch.setattr(fd,'make_fulldomain_obs_eval',capture)
    with pytest.raises(Captured):
        fd.run_fulldomain_analysis(fr,co,grids,'unused',boundary=0,obs_time=0,
            channels=tuple(range(8,17)),huber_delta=1.,normalized_dry=True,
            observation_coordinate='kma_v3_0',fixed_obs_errors=True,
            obs_sigma=sigma,obs_error_source='synthetic fixed assumption')


@pytest.mark.parametrize('extra,message', [
    ({'fixed_obs_errors': 1}, 'boolean'),
    ({'fixed_obs_errors': True, 'normalized_dry': False}, 'requires normalized_dry'),
    ({'fixed_obs_errors': True, 'obs_error_source': ''}, 'assumption label'),
    ({'fixed_obs_errors': False, 'obs_sigma': 2.}, 'explicit fixed_obs_errors'),
    ({'fixed_obs_errors': True, 'obs_sigma': [1.]*16}, 'per configured channel'),
])
def test_upper_rejects_error_policy_before_membership(monkeypatch,extra,message):
    fr,co,grids=inputs()
    monkeypatch.setattr(fd,'select_membership',lambda *a,**kw:pytest.fail('must reject first'))
    opts=dict(normalized_dry=True,observation_coordinate='kma_v3_0',
        channels=tuple(range(8,17)),huber_delta=1.,obs_error_source='synthetic assumption',fixed_obs_errors=True)
    opts.update(extra)
    with pytest.raises(ValueError,match=message):
        fd.run_fulldomain_analysis(fr,co,grids,'unused',**opts)


def test_full_upper_report_keeps_raw_and_adds_corrected_metrics(monkeypatch,tmp_path):
    import multiprocessing as mp
    import numpy as np
    import kdm6.obs.rttov_case_writer as writer
    fr,co,grids=inputs();co.bias=torch.ones_like(co.bt)
    sigma=torch.full((9,),2.,**F64)
    monkeypatch.setattr(writer,'make_live_run_k',lambda *a,**kw:None)
    pool=SimpleNamespace(close=lambda:None,join=lambda:None)
    monkeypatch.setattr(mp,'get_context',lambda _:SimpleNamespace(Pool=lambda _:pool))
    def cloud(x,f,pos,y,mask,xland,cfg,path,**kw):
        bt=x.th[pos,:1].expand(-1,9)
        return dict(bt=bt,rq=torch.zeros_like(bt),j=0.,adj=torch.zeros((12,len(pos),2),**F64))
    monkeypatch.setattr(fd,'sharded_allsky',cloud)
    def minimize(x,forcings,evaluate,cfg,b_sigma,prior,**kw):
        evaluate(0,x)  # execute the fixed closure before final reporting
        return SimpleNamespace(x_analysis=x._replace(th=x.th+1),theta_analysis=prior.theta_b,
            grad_norm_final=0.,grad_theta_norm_final=0.,jb_final=0.,jtheta_final=0.,jobs_final=0.,
            n_window_evals=1,n_audit_evals=1,partition=None,grad_w_norm_final=None,
            j_trace=[],cvt={})
    monkeypatch.setattr(fd,'run_dual_minimizer',minimize)
    saved=tmp_path/'fields.npz'
    rep=fd.run_fulldomain_analysis(fr,co,grids,'unused',boundary=0,obs_time=0,
        channels=tuple(range(8,17)),huber_delta=1.,normalized_dry=True,
        observation_coordinate='kma_v3_0',fixed_obs_errors=True,obs_sigma=sigma,
        obs_error_source='synthetic test assumption',save_fields=str(saved))
    assert rep['omb']==10. and rep['oma']==11.
    assert rep['omb_corrected']==9. and rep['oma_corrected']==10.
    assert rep['omb_standardized']==4.5 and rep['oma_standardized']==5.
    assert rep['observation_error_is_calibrated'] is False
    assert rep['scientific_observation_approval'] is False
    assert rep['obs_sigma_K']==[2.]*9
    with np.load(saved,allow_pickle=False) as data:
        np.testing.assert_array_equal(data['obs_bias_K'],np.ones((1,9)))
        np.testing.assert_array_equal(data['y_bt_corrected'],data['y_bt']+1)
        np.testing.assert_array_equal(data['obs_sigma_K'],np.full(9,2.))
