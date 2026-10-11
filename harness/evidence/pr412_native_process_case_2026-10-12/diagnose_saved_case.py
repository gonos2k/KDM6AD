#!/usr/bin/env python3
"""Two value-only initial-state H calls and endpoint summaries of one saved case.

No M, KDM backward or optimizer is replayed. The existing RTTOV wrapper may
still generate K internally; its internal calls are not instrumented.
The bypassed-M values are diagnostic
counterparts, not host states at the later valid time or a reoptimized system.
"""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import torch

from select_native_column import load

PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[2]
sys.path.insert(0, str(ROOT/'oracle'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def loss(bt, y):
    r=np.asarray(bt)-np.asarray(y)  # supplied sigma1K, bias0
    return float(np.sum(np.where(np.abs(r)<=1., .5*r*r, np.abs(r)-.5)))


def check_assets(assets):
    for name, record in assets.items():
        path=Path(name)
        if (str(path.resolve())!=record['resolved_path'] or sha(path)!=record['sha256']
                or path.stat().st_size!=record['bytes']):
            raise ValueError('declared H execution asset changed: '+name)


def main():
    from kdm6.state import State
    from kdm6.obs.allsky_shard import sharded_allsky
    from kdm6.thermo import compute_qs_water, default_thermo_params

    plan_path=PACKET/'DIAGNOSTIC_PLAN.json';plan=json.loads(plan_path.read_text())
    plan_sha=sha(plan_path)
    if sha(__file__)!=plan['source_sha256']:
        raise ValueError('diagnostic source changed')
    for f,h in plan['bindings'].items():
        if sha(f)!=h:
            raise ValueError('diagnostic input/source binding changed: '+f)
    check_assets(plan['external_assets_before'])
    output=Path(plan['case_root'])
    output.mkdir(mode=0o700,exist_ok=False)
    with (output/'STARTED_ONCE.json').open('x') as f:
        f.write(json.dumps({'plan_sha256':sha(plan_path),'additional_H_max':2,'M_optimizer_calls':0})+'\n')
    capture=json.loads(Path(plan['capture_path']).read_text())
    if (Path(plan['checkpoint_path']).resolve()!=Path(capture['private_checkpoint']['path']).resolve()
            or sha(plan['checkpoint_path'])!=capture['private_checkpoint']['sha256']):
        raise ValueError('checkpoint is not paired to the saved capture')
    manifest=json.loads(Path(plan['intake_manifest']).read_text())
    with np.load(plan['intake_npz'],allow_pickle=False) as z:
        core={n:z[n] for n in z.files}
    with np.load(plan['checkpoint_path'],allow_pickle=False) as z:
        checkpoint={n:z[n] for n in z.files}
    driver=load(plan['driver_path'])
    legacy=driver.load_module(driver.LEGACY_DRIVER,'pr412_h_diagnostic_legacy_configuration')
    ctx=driver.build_inputs(manifest,core,Path(plan['fixture_case_dir']),Path(plan['template_fixture']),legacy)
    for field in ctx['forcing']._fields:
        if not np.array_equal(getattr(ctx['forcing'],field).numpy(),checkpoint['forcing_window_0__'+field]):
            raise ValueError('H forcing differs from saved analysis: '+field)
    for field in State._fields:
        if not np.array_equal(getattr(ctx['xb'],field).numpy(),checkpoint['background_initial_state__'+field]):
            raise ValueError('background differs from saved analysis: '+field)
    if (not np.array_equal(ctx['y_bt'].numpy(),checkpoint['observation_y_bt_K'])
            or not np.array_equal(ctx['y_rq'].numpy(),checkpoint['observation_y_dqf'])
            or not np.array_equal(ctx['xland'].numpy(),core['native_surface__xland'][0:1])):
        raise ValueError('H observation or ocean classification changed')
    capture_module=driver.prepare_capture_module()
    if capture_module._public_h_config_summary(ctx['rttov_cfg']) != capture['effective_h_configuration']:
        raise ValueError('effective H auxiliaries differ from saved analysis')
    for key in ('p_lay','p_half','t_ref','q_ref'):
        if not np.array_equal(ctx['rttov_cfg'][key],checkpoint['rttov_config__'+key]):
            raise ValueError('H reference coordinate changed: '+key)
    if not np.array_equal(ctx['rttov_cfg']['rho_d'],checkpoint['rho_d_native_bottomup_kg_m3']):
        raise ValueError('frozen optical density changed')
    states={label:State(*(torch.as_tensor(checkpoint[label+'_state__'+f],dtype=torch.float64) for f in State._fields))
            for label in ('background_initial','background_slot','returned_analysis_initial','final_slot')}
    for label,state in states.items():
        for field in State._fields:
            digest=hashlib.sha256(np.ascontiguousarray(getattr(state,field).numpy()).tobytes()).hexdigest()
            if digest!=capture['state_array_sha256'][label][field]:
                raise ValueError('State/capture endpoint mismatch: '+label+'/'+field)
    y=ctx['y_bt'].numpy(); mask=torch.ones_like(ctx['y_bt'])
    if not np.array_equal(mask.numpy(),checkpoint['final_slot_frozen_mask']):
        raise ValueError('diagnostic support differs from saved final support')
    first_index=capture['objective']['initial_zero_control_closure']['first_grad_true_h_call_index']
    first=next(x for x in capture['logical_h_calls'] if x['call_index']==first_index)
    last=capture['logical_h_calls'][-1]
    if (first.get('returned') is not True or np.any(np.asarray(first['rad_quality'])!=0)
            or not np.array_equal(np.asarray(first['fixed_mask']),mask.numpy())
            or first['state_sha256']!=capture['state_array_sha256']['background_slot']
            or last['state_sha256']!=capture['state_array_sha256']['final_slot']
            or last.get('returned') is not True
            or not np.array_equal(checkpoint['final_slot_rad_quality'],np.asarray(last['rad_quality']))
            or np.any(checkpoint['final_slot_rad_quality']!=0)
            or not np.array_equal(checkpoint['final_slot_frozen_mask'],np.asarray(last['fixed_mask']))
            or not np.array_equal(checkpoint['final_slot_bt_K'],np.asarray(last['BT_K']))):
        raise ValueError('stored seven-channel H values lack matching valid endpoint/support')
    missing={}
    for label in ('background_initial','returned_analysis_initial'):
        out=sharded_allsky(states[label],ctx['forcing'],torch.tensor([0]),ctx['y_bt'],mask,
            ctx['xland'],ctx['rttov_cfg'],str(output/label),n_workers=1,grad=False,
            huber_delta=1.,obs_sigma=torch.ones(7,dtype=torch.float64),obs_bias=torch.zeros_like(ctx['y_bt']))
        bt=out['bt'].numpy();quality=out['rq'].numpy()
        if not np.isfinite(bt).all() or np.any(quality!=0):
            raise ValueError('fixed seven-channel diagnostic quality lost; do not retry')
        missing[label]={'BT_K':bt.tolist(),'rad_quality':quality.tolist(),'Jo':loss(bt,y)}
    bm=np.asarray(first['BT_K'])
    am=checkpoint['final_slot_bt_K']; b0=np.asarray(missing['background_initial']['BT_K']);a0=np.asarray(missing['returned_analysis_initial']['BT_K'])
    rb=bm-b0;ra=am-a0
    mass=checkpoint['host_dry_mass_background_kg_m2'].astype(np.float64)
    pii=checkpoint['forcing_window_0__pii'];pressure=checkpoint['forcing_window_0__p']
    snapshots={}
    for label,state in states.items():
        t=state.th*torch.as_tensor(pii,dtype=torch.float64)
        ratio=100.*state.qv/compute_qs_water(t,torch.as_tensor(pressure,dtype=torch.float64),params=default_thermo_params())
        water=sum(getattr(state,f).numpy() for f in ('qv','qc','qr','qi','qs','qg'))
        snapshots[label]={'T_min_K':float(t.min()),'T_max_K':float(t.max()),'liquid_saturation_ratio_max_percent':float(ratio.max()),
            'water_fixed_host_dry_measure_kg_m2':float(np.sum(water*mass)),
            'qc_max_kg_kg_dry':float(state.qc.max()),'qc_fixed_host_dry_path_kg_m2':float(np.sum(state.qc.numpy()*mass)),
            'nc_max_recorded_model_coordinate':float(state.nc.max()),'qc_positive_layers':int((state.qc>0).sum())}
    changes={}
    for a,b in [('background_initial','background_slot'),('returned_analysis_initial','final_slot')]:
        changes[a+'__to__'+b]={
            'T_delta_min_K':float(((states[b].th-states[a].th)*torch.as_tensor(pii)).min()),
            'T_delta_max_K':float(((states[b].th-states[a].th)*torch.as_tensor(pii)).max()),
            'qv_delta_min_kg_kg_dry':float((states[b].qv-states[a].qv).min()),
            'qv_delta_max_kg_kg_dry':float((states[b].qv-states[a].qv).max()),
            'qc_delta_min_kg_kg_dry':float((states[b].qc-states[a].qc).min()),
            'qc_delta_max_kg_kg_dry':float((states[b].qc-states[a].qc).max()),
            'water_fixed_measure_delta_kg_m2':snapshots[b]['water_fixed_host_dry_measure_kg_m2']-snapshots[a]['water_fixed_host_dry_measure_kg_m2']}
    gm=loss(bm,y)-loss(am,y);g0=loss(b0,y)-loss(a0,y)
    result={'schema':'pr412_saved_process_response_v1','status':'RETURNED_TWO_VALUE_ONLY_H_DIAGNOSTICS',
        'plan_sha256':sha(plan_path),'missing_initial_H':missing,'stored_slot_H':{'background_BT_K':bm.tolist(),'analysis_BT_K':am.tolist()},
        'R_M_background_K':rb.tolist(),'R_M_analysis_K':ra.tolist(),'I_M_K':(ra-rb).tolist(),
        'fixed_state_pair_observation_cost_gains':{'G_M':gm,'G_0':g0,'G_M_minus_G_0':gm-g0},
        'state_snapshots':snapshots,'local_M_endpoint_changes':changes,
        'analysis_initial_water_delta_kg_m2':snapshots['returned_analysis_initial']['water_fixed_host_dry_measure_kg_m2']-snapshots['background_initial']['water_fixed_host_dry_measure_kg_m2'],
        'additional_logical_H_calls':2,'internal_RTTOV_direct_K_calls':None,'additional_M_optimizer_calls':0,
        'number_coordinate_note':'recorded native NC is used under the declared normalized-dry/dry_number=True runtime contract; independent native QN dry-vs-moist basis is not revalidated here; maxima are recorded coordinate values, not observed concentrations or a number budget',
        'named_process_rates_recorded':False,'external_flux_budget_closed':False,'same_valid_time_host_comparison':False,
        'reoptimized_no_M_system':False,'observed_cloud_phase_or_NC_truth':False,'new_dates':0,'science_accepted':False}
    for f,h in plan['bindings'].items():
        if sha(f)!=h:
            raise ValueError('diagnostic input/source changed after evaluations: '+f)
    if sha(plan_path)!=plan_sha or sha(__file__)!=plan['source_sha256']:
        raise ValueError('diagnostic plan/source changed after evaluations')
    check_assets(plan['external_assets_before'])
    serialized=json.dumps(result,indent=2,allow_nan=False)+'\n'
    with (PACKET/'PROCESS_RESPONSE.json').open('x') as f:f.write(serialized)
    print(json.dumps({'status':result['status'],'additional_logical_H_calls':2,'R_M_background_K':rb.tolist(),'R_M_analysis_K':ra.tolist(),'I_M_K':(ra-rb).tolist()}))


if __name__=='__main__':
    main()
