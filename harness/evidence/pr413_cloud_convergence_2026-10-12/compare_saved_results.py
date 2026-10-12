#!/usr/bin/env python3
"""Read the two bounded captures/checkpoints; no M/H/optimizer evaluation."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

PACKET=Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def loss(bt,y):
    r=np.asarray(bt)-np.asarray(y)
    return float(np.sum(np.where(np.abs(r)<=1.,.5*r*r,np.abs(r)-.5)))


def load_capture(path):
    c=json.loads(Path(path).read_text());cp=Path(c['private_checkpoint']['path'])
    if sha(cp)!=c['private_checkpoint']['sha256']:raise ValueError('checkpoint/capture hash mismatch')
    with np.load(cp,allow_pickle=False) as z:arrays={k:z[k] for k in z.files}
    for label,fields in c['state_array_sha256'].items():
        for f,h in fields.items():
            a=np.ascontiguousarray(arrays[label+'_state__'+f])
            if hashlib.sha256(a.tobytes()).hexdigest()!=h:raise ValueError('endpoint State hash mismatch')
    return c,arrays


def values(c,arrays):
    obj=c['objective'];opt=c['optimization'];g=c['final_control_gradient']
    if obj['n_valid']!=7 or np.any(arrays['final_slot_frozen_mask']!=1) or np.any(arrays['final_slot_rad_quality']!=0):
        raise ValueError('final fixed seven-channel support/quality not valid')
    y=np.asarray(c['observations']['y_bt_K']);bt=arrays['final_slot_bt_K']
    if not np.isclose(loss(bt,y),obj['Jo'],rtol=0,atol=1e-11):raise ValueError('saved BT cost mismatch')
    prior=np.sqrt(2.*obj['Jb_state'])
    if not np.isclose(np.linalg.norm(arrays['control__optimizer_v_state_control']),prior,rtol=0,atol=1e-12):
        raise ValueError('prior/control norm mismatch')
    grad=arrays['control__optimizer_final_gradient_combined']
    if not np.isclose(np.linalg.norm(grad),g['combined_l2_norm'],rtol=0,atol=1e-12):
        raise ValueError('full gradient norm mismatch')
    return {'Jo_initial':obj['initial_zero_control_closure']['Jo'],'Jo_final':obj['Jo'],
        'Jb_final':obj['Jb_state'],'J_final':obj['Jtotal'],'gradient_linf':g['combined_linf_norm'],
        'gradient_l2':g['combined_l2_norm'],'prior_gradient_l2':float(prior),
        'full_gradient_to_prior_ratio':float(g['combined_l2_norm']/prior),
        'strict_gradient_convergence':opt['final_audit_gradient_within_tolerance_grad'],
        'termination':opt['termination_status'],'max_iter':opt['max_iter'],'max_eval':opt['max_eval'],
        'iterations':opt['actual_n_iter'],'function_evals':opt['actual_func_evals'],
        'window_evals':opt['n_window_evals'],'audit_evals':opt['n_audit_evals'],
        'logical_H_callbacks':len(c['logical_h_calls']),
        'final_slot_qc_max':float(arrays['final_slot_state__qc'].max()),
        'final_slot_nc_max_recorded_coordinate':float(arrays['final_slot_state__nc'].max())}


def main():
    plan=json.loads((PACKET/'PREDECLARED.json').read_text())
    old,oa=load_capture(plan['baseline_capture']);new,na=load_capture(PACKET/'CAPTURE.json')
    for name in oa:
        if name.startswith(('background_initial_state__','background_slot_state__','forcing_window_0__','control__b_sigma__')):
            if not np.array_equal(oa[name],na[name]):raise ValueError('same-problem field differs: '+name)
    for key in ['observation_y_bt_K','observation_y_dqf','host_dry_mass_background_kg_m2','rho_d_native_bottomup_kg_m3',
                'rttov_config__p_lay','rttov_config__p_half','rttov_config__t_ref','rttov_config__q_ref']:
        if not np.array_equal(oa[key],na[key]):raise ValueError('same-problem auxiliary differs: '+key)
    old_v,new_v=values(old,oa),values(new,na)
    pii=na['forcing_window_0__pii'];mass=na['host_dry_mass_background_kg_m2'].astype(np.float64)
    water=lambda a,lab:float(np.sum(sum(a[lab+'_state__'+f] for f in ('qv','qc','qr','qi','qs','qg'))*mass))
    t_delta=(na['returned_analysis_initial_state__th']-oa['returned_analysis_initial_state__th'])*pii
    q_delta=na['returned_analysis_initial_state__qv']-oa['returned_analysis_initial_state__qv']
    summary={'schema':'pr413_saved_budget_comparison_v1','old_capture_sha256':sha(plan['baseline_capture']),
        'new_capture_sha256':sha(PACKET/'CAPTURE.json'),'old_checkpoint_sha256':old['private_checkpoint']['sha256'],
        'new_checkpoint_sha256':new['private_checkpoint']['sha256'],'old_3_iteration_budget':old_v,'new_8_iteration_budget':new_v,
        'objective_delta_new_minus_old':{k:new_v[k]-old_v[k] for k in ['Jo_final','Jb_final','J_final']},
        'same_background_forcing_priors_observations_and_H_aux_arrays':True,
        'accepted_initial_state_change_8_vs_3':{'T_max_abs_K':float(np.max(np.abs(t_delta))),
            'qv_max_abs_kg_kg_dry':float(np.max(np.abs(q_delta))),
            'control_l2_difference':float(np.linalg.norm(na['control__optimizer_v_state_control']-oa['control__optimizer_v_state_control']))},
        'new_fixed_host_dry_mass_water_diagnostics':{lab:water(na,lab) for lab in ['background_initial','background_slot','returned_analysis_initial','final_slot']},
        'cloud_loss_endpoint_persists_at_both_budgets':new_v['final_slot_qc_max']==old_v['final_slot_qc_max']==0.,
        'strict_convergence_claim':False,'actual_termination_explanation':'UNKNOWN retained; observed counts are not an exposed termination cause',
        'M_H_optimizer_calls_for_comparison':0,'new_dates_or_native_integrations':0,'score_change':False,
        'old_R_M_I_M_contrasts_not_recomputed_or_transferred_to_new_accepted_point':True,
        'native_number_basis_not_revalidated':True,'process_rates_or_external_flux_budget_closed':False}
    with (PACKET/'COMPARISON.json').open('x') as f:f.write(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    names=['WV073','IR087','IR096','IR105','IR112','IR123','IR133']
    first=new['objective']['initial_zero_control_closure']['first_grad_true_h_call_index']
    bg=np.asarray(next(x['BT_K'] for x in new['logical_h_calls'] if x['call_index']==first))[0]
    y=np.asarray(new['observations']['y_bt_K'])[0];old_bt=oa['final_slot_bt_K'][0];new_bt=na['final_slot_bt_K'][0]
    with (PACKET/'CHANNEL_COMPARISON.csv').open('x',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['channel_id','name','observed_BT_K','background_slot_BT_K','old_analysis_slot_BT_K','new_analysis_slot_BT_K','O_minus_B_K','O_minus_A_3_K','O_minus_A_8_K','observation_dqf','old_model_rad_quality','new_model_rad_quality'])
        for k,name in enumerate(names):w.writerow([10+k,name,y[k],bg[k],old_bt[k],new_bt[k],y[k]-bg[k],y[k]-old_bt[k],y[k]-new_bt[k],0,0,0])
    print(json.dumps({'old':old_v,'new':new_v,'delta_J':summary['objective_delta_new_minus_old']}))


if __name__=='__main__':main()
