"""Strict validation-only adapter tests; no native data, M/H or optimizer call."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

PACKET=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('pr413_runner_guard_test',PACKET/'run_cloud_convergence.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
driver=runner.load(PACKET.parents[2]/'harness/evidence/pr407_native_saved_time_bound_2026-10-11/run_case_analysis.py','pr413_guard_existing_driver')


def inputs():
    cfg=SimpleNamespace(dt=20.,normalized_dry=True,eta=None,eta_pre=None,ncmin_land=10.,ncmin_sea=10.)
    manifest={'experiment_id':runner.EXPERIMENT,'protocol_precedent':runner.PRECEDENT,
        'optimizer_max_eval_policy':'pytorch_lbfgs_default_ceil_1.25_max_iter',
        'obs_time':1,'dt_s':20,'max_iter':8,'observation_sigma_K':1.,'observation_bias_K':0.,
        'huber_delta_K':1.,'th_sigma_K':.8,'qv_sigma_log':.08,'qv_levels_from_bottom':12,
        'non_tq_state_sigmas_zero':True,'parameter_prior_active':[],'partition_control':False,
        'pseudo_rh':False,'warm_start':False,'automatic_retry':False,'ncmin_land':10.,'ncmin_sea':10.}
    return cfg,manifest


def test_valid_new_identity_not_rewritten():
    cap=runner.capture_for_experiment(driver,{})
    cfg,m=inputs();before=dict(m)
    cap._validate_predeclared_run(cfg,m,obs_time=1,max_iter=8,forcings=(object(),))
    assert m==before and m['experiment_id']==runner.EXPERIMENT


@pytest.mark.parametrize('field,value',[('experiment_id',runner.PRECEDENT),('max_iter',3),
    ('observation_sigma_K',2.),('warm_start',True),('th_sigma_K',1.)])
def test_old_identity_wrong_budget_or_prior_is_rejected(field,value):
    cap=runner.capture_for_experiment(driver,{})
    cfg,m=inputs();m[field]=value
    with pytest.raises(ValueError):
        cap._validate_predeclared_run(cfg,m,obs_time=1,max_iter=m['max_iter'],forcings=(object(),))


def test_physical_window_change_is_rejected():
    cap=runner.capture_for_experiment(driver,{})
    cfg,m=inputs();cfg.dt=40.
    with pytest.raises(ValueError):
        cap._validate_predeclared_run(cfg,m,obs_time=1,max_iter=8,forcings=(object(),))


@pytest.mark.parametrize('key,value',[('PYTHONOPTIMIZE','1'),('OMP_THREAD_LIMIT','2')])
def test_launch_environment_mismatch_is_rejected(monkeypatch,key,value):
    expected={'environment':{'python_executable':sys.executable,
        'thread_environment':{k:'1' for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OMP_THREAD_LIMIT','VECLIB_MAXIMUM_THREADS')}}}
    for k,v in expected['environment']['thread_environment'].items():monkeypatch.setenv(k,v)
    monkeypatch.setenv('PYTHONOPTIMIZE','0');monkeypatch.setenv(key,value)
    with pytest.raises(ValueError):runner.check_environment_before_torch(expected)
