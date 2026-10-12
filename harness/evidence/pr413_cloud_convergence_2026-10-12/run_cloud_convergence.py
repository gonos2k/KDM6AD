#!/usr/bin/env python3
"""One declared 8-iteration check of the unchanged PR412 cloudy-column problem.

Default invocation prepares only. --execute consumes that reviewed preflight.
The isolated validation adapter maps only the new experiment identity to the
existing eight-iteration guard; M/H, priors, solver and input gates are reused.
"""
import argparse
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys

PACKET=Path(__file__).resolve().parent
ROOT=PACKET.parents[2]
sys.path.insert(0,str(ROOT/'oracle'))
EXPERIMENT='PR413_CLOUD_CONVERGENCE_8ITER_20261012'
PRECEDENT='PR398_CONVERGENCE_8ITER_20261010'
MAX_ITER=8


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def write(path,value):
    serialized=json.dumps(value,indent=2,allow_nan=False)+'\n'
    with Path(path).open('x') as f:f.write(serialized)


def check_bindings(plan):
    import torch
    if sha(__file__)!=plan['runner_sha256']:
        raise ValueError('runner changed after declaration')
    for path,h in plan['bindings'].items():
        if sha(path)!=h:raise ValueError('bound input/source changed: '+path)
    for path,a in plan['external_assets'].items():
        if str(Path(path).resolve())!=a['resolved_path'] or sha(path)!=a['sha256'] or Path(path).stat().st_size!=a['bytes']:
            raise ValueError('execution asset changed: '+path)
    if str(torch.__version__)!=plan['torch_version'] or plan['torch_version']!='2.13.0':
        raise ValueError('pinned optimizer version changed')


def check_environment_before_torch(plan):
    expected=plan['environment']
    actual={'python_executable':sys.executable,'PYTHONOPTIMIZE':os.environ.get('PYTHONOPTIMIZE'),
            'thread_environment':{k:os.environ.get(k) for k in expected['thread_environment']},
            'python_assertions_enabled':__debug__}
    if (actual['python_executable']!=expected['python_executable']
            or actual['PYTHONOPTIMIZE']!='0' or not __debug__
            or actual['thread_environment']!=expected['thread_environment']):
        raise ValueError('launch with the exact declared interpreter, PYTHONOPTIMIZE=0 and thread environment')
    return actual


def make_preflight(plan,plan_sha,capture,files,fp,environment):
    return {'schema':'pr413_cloud_convergence_preflight_v1','status':'PREPARED_NO_ANALYSIS_EXECUTED',
            'plan_sha256':plan_sha,'experiment_id':EXPERIMENT,'input_case_id':plan['input_case_id'],
            'fingerprints':fp,'fixture_hashes':files,'source_snapshot':capture._source_snapshot(),
            'zero_initialized_original_background':True,'expected_default_nominal_max_eval':10,
            'no_explicit_max_eval_kwarg':True,'analysis_executed':False,'observed_environment':environment}


def capture_for_experiment(driver,plan):
    capture=driver.prepare_capture_module()
    original_guard=capture._validate_predeclared_run
    original_snapshot=capture._source_snapshot
    def guard(config,manifest,*,obs_time,max_iter,forcings):
        if (manifest.get('experiment_id')!=EXPERIMENT or max_iter!=MAX_ITER
                or manifest.get('protocol_precedent')!=PRECEDENT):
            raise ValueError('only the single declared PR413 eight-iteration experiment is supported')
        # Validation-only identity translation. The original manifest, which
        # is passed to capture/storage, keeps its truthful PR413 identity.
        validation_copy={**manifest,'experiment_id':PRECEDENT}
        original_guard(config,validation_copy,obs_time=obs_time,max_iter=max_iter,forcings=forcings)
    def snapshot():
        check_bindings(plan)
        return {**original_snapshot(),str(Path(__file__).resolve()):sha(__file__)}
    capture._validate_predeclared_run=guard
    capture._source_snapshot=snapshot
    return capture


def build_context(plan,prepare):
    driver=load(plan['v4_driver_path'],'pr413_existing_v4_builder')
    intake=driver.load_module(driver.INTAKE_SOURCE,'pr413_bound_v4_intake')
    manifest,arrays=intake.load_bound_intake(Path(plan['intake_manifest']),Path(plan['intake_npz']))
    legacy=driver.load_module(driver.LEGACY_DRIVER,'pr413_existing_fixture_primitives')
    output=Path(plan['output_root']);fixture=output/'rttov_fixture'
    if prepare:
        output.mkdir(mode=0o700,exist_ok=False)
        legacy._prepare_fixture_copy(Path(plan['template_fixture']),fixture,arrays)
    ctx=driver.build_inputs(manifest,arrays,fixture,Path(plan['template_fixture']),legacy)
    baseline=json.loads(Path(plan['baseline_capture']).read_text())
    capture=capture_for_experiment(driver,plan)
    if (capture.state_sha256(ctx['xb'])!=baseline['state_array_sha256']['background_initial']
            or capture.forcing_sha256(ctx['forcing'])!=baseline['forcing_array_sha256']['forcing_window'][0]
            or capture.array_sha256(ctx['y_bt'])!=capture.array_sha256(baseline['observations']['y_bt_K'])
            or capture.array_sha256(ctx['y_rq'])!=capture.array_sha256(baseline['observations']['observation_dqf'])):
        raise ValueError('background, forcing or observations differ from PR412')
    now=capture._public_h_config_summary(ctx['rttov_cfg']);prior=dict(baseline['effective_h_configuration'])
    now.pop('fixture_case_dir');prior.pop('fixture_case_dir')
    if now!=prior:raise ValueError('effective H changed beyond fresh fixture path')
    old_manifest=json.loads(Path(plan['baseline_preflight']).read_text())['run_contract']
    if ctx['run_manifest']!=old_manifest:
        raise ValueError('original V4 problem/settings differ from PR412')
    ctx['run_manifest']={**ctx['run_manifest'],'max_iter':MAX_ITER,'experiment_id':EXPERIMENT,
        'protocol_precedent':PRECEDENT,'optimizer_max_eval_policy':'pytorch_lbfgs_default_ceil_1.25_max_iter'}
    capture._validate_predeclared_run(ctx['window_config'],ctx['run_manifest'],obs_time=1,max_iter=MAX_ITER,forcings=(ctx['forcing'],))
    old_driver=json.loads(Path(plan['baseline_driver']).read_text())
    fixture_hashes={}
    old_fixture=Path(plan['baseline_fixture'])
    for name,h in old_driver['execution_assets_after'].items():
        path=Path(name)
        if path.is_relative_to(old_fixture):
            target=fixture/path.relative_to(old_fixture)
            if sha(target)!=h:raise ValueError('copied fixture differs from actual PR412 file: '+str(target))
            fixture_hashes[str(target)]=h
    fingerprints={'initial_state':capture.state_sha256(ctx['xb']),'forcing':capture.forcing_sha256(ctx['forcing']),
        'y_bt':capture.array_sha256(ctx['y_bt']),'y_dqf':capture.array_sha256(ctx['y_rq']),
        'xland':capture.array_sha256(ctx['xland']),'H':capture._public_h_config_summary(ctx['rttov_cfg']),
        'window':capture._jsonable(ctx['window_config']),'run_manifest':ctx['run_manifest']}
    return driver,legacy,capture,ctx,fixture_hashes,fingerprints


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    plan_path=PACKET/'PREDECLARED.json';plan_sha=sha(plan_path);plan=json.loads(plan_path.read_text())
    environment=check_environment_before_torch(plan)
    import torch
    torch.set_num_threads(1)
    environment.update(torch_version=str(torch.__version__),torch_num_threads=torch.get_num_threads())
    check_bindings(plan)
    preflight_path=PACKET/'PREFLIGHT.json'
    if not args.execute:
        if preflight_path.exists():raise FileExistsError('preflight already prepared; no replacement')
        _,_,capture,ctx,files,fp=build_context(plan,True)
        pre=make_preflight(plan,plan_sha,capture,files,fp,environment)
        write(preflight_path,pre);print(json.dumps({'status':pre['status'],'experiment_id':EXPERIMENT}));return
    pre=json.loads(preflight_path.read_text())
    if pre['plan_sha256']!=plan_sha or pre['status']!='PREPARED_NO_ANALYSIS_EXECUTED':raise ValueError('preflight does not bind declaration')
    if pre['observed_environment']!=environment:raise ValueError('observed environment differs from prepared runtime')
    driver,legacy,capture,ctx,files,fp=build_context(plan,False)
    before=capture._source_snapshot()
    if fp!=pre['fingerprints'] or files!=pre['fixture_hashes'] or before!=pre['source_snapshot']:
        raise ValueError('prepared context changed before execution')
    output=Path(plan['output_root'])
    write(output/'RUN_STARTED_ONCE.json',{'experiment_id':EXPERIMENT,'preflight_sha256':sha(preflight_path),'plan_sha256':plan_sha})
    with mp.get_context('spawn').Pool(1) as pool:
        result=capture.run_capture(xb=ctx['xb'],forcings=(ctx['forcing'],),y_bt=ctx['y_bt'],y_rq=ctx['y_rq'],
            xland=ctx['xland'],clear_cfg=ctx['clear_cfg'],rttov_cfg=ctx['rttov_cfg'],window_config=ctx['window_config'],
            obs_time=1,pool=pool,max_iter=MAX_ITER,n_workers=1,
            private_checkpoint=output/'private/accepted_state.npz',public_receipt=output/'CAPTURE.json',case_root=output/'h_cases',
            native_intake_context_path=Path(plan['intake_manifest']),native_intake_context_sha256=sha(plan['intake_manifest']),
            native_intake_npz_path=Path(plan['intake_npz']),native_intake_npz_sha256=sha(plan['intake_npz']),run_manifest=ctx['run_manifest'])
    audit=legacy._audit_initial_objectives(result,ctx['y_bt'])
    after=capture._source_snapshot();check_bindings(plan)
    if sha(plan_path)!=plan_sha or any(sha(path)!=h for path,h in files.items()):raise ValueError('declaration/fixture changed after run')
    passed=result.get('status')=='RETURNED_DIAGNOSTIC_ONLY' and audit['status']=='CROSSCHECKED' and before==after
    driver_result={'schema':'pr413_cloud_convergence_driver_v1','experiment_id':EXPERIMENT,'input_case_id':plan['input_case_id'],
        'status':'RETURNED_CLOUD_CONVERGENCE_DIAGNOSTIC' if passed else 'FAILED_AUDIT','objective_audit':audit,
        'source_snapshot_before':before,'source_snapshot_after':after,'fixture_hashes':files,
        'run_manifest':ctx['run_manifest'],'capture_path':str(output/'CAPTURE.json'),'capture_sha256':sha(output/'CAPTURE.json'),
        'max_iter':MAX_ITER,'max_eval_explicitly_passed':False,'native_integrations':0,'automatic_retry':False,
        'new_dates':0,'science_accepted':False}
    write(output/'DRIVER_RESULT.json',driver_result)
    print(json.dumps({'status':driver_result['status'],'experiment_id':EXPERIMENT}))
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
