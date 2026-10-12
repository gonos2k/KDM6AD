#!/usr/bin/env python3
"""Read immutable old/new window checkpoints; no new model/H/optimizer calls."""
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np

PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[2]
OLD = ROOT / 'harness/evidence/pr414_ami_window_2026-10-12'
FIELDS = ('th', 'qv', 'qc', 'qr', 'qi', 'qs', 'qg', 'nccn', 'nc', 'ni', 'nr', 'bg')
NAMES = ('WV073', 'IR087', 'IR096', 'IR105', 'IR112', 'IR123', 'IR133')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def loss(bt, y):
    r = np.asarray(bt) - np.asarray(y)
    return float(np.where(abs(r) <= 1, .5 * r**2, abs(r) - .5).sum())


def read(path):
    result = json.loads(Path(path).read_text())
    checkpoint = Path(result['checkpoint']['path'])
    if sha(checkpoint) != result['checkpoint']['sha256']:
        raise ValueError('result/checkpoint hash mismatch')
    with np.load(checkpoint, allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    return result, arrays


def exact(a, b):
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def verify(result, a):
    jo = 0.0
    for t, event in zip((1, 31, 61), result['accepted']):
        target = a[f'observations_{t}__y_bt'].reshape(7)
        bt = a[f'accepted_{t}__bt']
        if (event['step_index'] != t or np.any(a[f'observations_{t}__mask'] != 1) or
                np.any(a[f'accepted_{t}__rq'] != 0)):
            raise ValueError('support/time/model quality changed')
        cost = loss(bt, target)
        if not np.isclose(cost, event['J_o'], rtol=0, atol=1e-10):
            raise ValueError('saved slot cost mismatch')
        jo += cost
    jb = .5 * float((a['control__v_state']**2).sum())
    gradient = a['control__gradient_state']
    for expected, actual in [(result['final_J_o'], jo), (result['final_J_b'], jb),
                             (result['final_J'], jb + jo),
                             (result['gradient_Linf'], float(abs(gradient).max())),
                             (result['gradient_L2'], float(np.linalg.norm(gradient)))]:
        if not np.isclose(expected, actual, rtol=0, atol=1e-10):
            raise ValueError('saved objective or full gradient differs')
    if np.any(a['control__v_theta'] != 0) or np.any(a['control__gradient_parameters'] != 0):
        raise ValueError('physical parameter controls changed')
    norm = float(np.linalg.norm(a['control__v_state']))
    return {'Jo': jo, 'Jb': jb, 'J': jo + jb, 'gradient_Linf': result['gradient_Linf'],
            'gradient_L2': result['gradient_L2'], 'control_L2': norm,
            'full_gradient_to_prior_ratio': result['gradient_L2']/norm if norm else None,
            'strict_converged': result['strict_gradient_converged'],
            'termination': result['termination_reason'], 'optimizer': result['optimizer'],
            'window_evaluations': result['window_evaluations'], 'audit_evaluations': result['audit_evaluations'],
            'logical_H_calls': result['logical_H_calls']}


def main():
    old, oa = read(OLD / 'RESULT.json')
    new, na = read(PACKET / 'RESULT.json')
    for key in oa:
        if key.startswith(('background_', 'forcing__', 'b_sigma__', 'observations_')) or key in ('p_lay', 'p_half', 'fixed_optical_rho_d'):
            if not exact(oa[key], na[key]):
                raise ValueError('same-problem retained array differs: ' + key)
    old_values, new_values = verify(old, oa), verify(new, na)
    v0, v1 = oa['control__v_state'], na['control__v_state']
    delta = float(np.linalg.norm(v1 - v0))
    denom = old_values['control_L2'] * new_values['control_L2']
    angle = math.degrees(math.acos(float(np.clip(np.vdot(v0, v1) / denom, -1, 1)))) if denom else None
    plan = json.loads((PACKET / 'WINDOW_PREDECLARED.json').read_text())
    with np.load(plan['intake_npz'], allow_pickle=False) as z:
        mass = z['host_dry_mass_background_kg_m2'].astype(np.float64)
    def water(a, prefix):
        return float(sum((a[prefix + '__' + f] * mass).sum() for f in ('qv', 'qc', 'qr', 'qi', 'qs', 'qg')))
    rows, slots = [], []
    for t in (1, 31, 61):
        y = na[f'observations_{t}__y_bt'].reshape(7)
        bg, ob, nb = na[f'background_{t}__bt'], oa[f'accepted_{t}__bt'], na[f'accepted_{t}__bt']
        for k, name in enumerate(NAMES):
            rows.append([t, k+10, name, y[k], bg[k], ob[k], nb[k], y[k]-bg[k], y[k]-ob[k], y[k]-nb[k], 0, 0, 0])
        slots.append({'step_index': t, 'old_Jo': loss(ob, y), 'new_Jo': loss(nb, y),
                      'new_huber_quadratic_channel_ids': [10+k for k in range(7) if abs(nb[k]-y[k]) <= 1],
                      'new_QC_max': float(na[f'accepted_slot_{t}__qc'].max()),
                      'new_recorded_NC_max': float(na[f'accepted_slot_{t}__nc'].max()),
                      'new_water_fixed_mass_kg_m2': water(na, f'accepted_slot_{t}')})
    new_bts = np.stack([na[f'accepted_{t}__bt'] for t in (1, 31, 61)])
    state_equal = all(exact(na['accepted_slot_1__'+f], na[f'accepted_slot_{t}__{f}']) for f in FIELDS for t in (31, 61))
    summary = {'schema': 'pr415_same_window_saved_comparison_v1', 'old_result_sha256': sha(OLD/'RESULT.json'),
               'new_result_sha256': sha(PACKET/'RESULT.json'), 'old': old_values, 'new': new_values,
               'same_original_background_forcing_H_aux_control_sigmas_observations': True,
               'initial_J': new['initial_J_o'],
               'cost_delta_new_minus_old': {k: new_values[k]-old_values[k] for k in ('Jo', 'Jb', 'J')},
               'accepted_initial_change': {'control_delta_L2': delta, 'control_angle_degrees': angle,
                   'delta_relative_to_new_control_norm': delta/new_values['control_L2'] if new_values['control_L2'] else None,
                   'T_max_abs_K': float(abs((na['accepted_initial__th']-oa['accepted_initial__th'])*na['forcing__pii']).max()),
                   'qv_max_abs_kg_kg_dry': float(abs(na['accepted_initial__qv']-oa['accepted_initial__qv']).max())},
               'slots': slots, 'new_sampled_states_exactly_equal': state_equal,
               'new_simulated_temporal_range_K_by_channel': dict(zip(NAMES, np.ptp(new_bts, axis=0).tolist())),
               'old_to_new_BT_max_abs_K': float(max(abs(na[f'accepted_{t}__bt']-oa[f'accepted_{t}__bt']).max() for t in (1,31,61))),
               'new_analysis_initial_water_change_fixed_mass_kg_m2': water(na,'accepted_initial')-water(na,'background_initial'),
               'M_H_optimizer_calls_for_comparison': 0, 'new_dates_or_native_integrations': 0,
               'no_process_rate_or_external_flux_budget_claim': True,
               'old_PR412_R_M_I_M_not_transferred': True}
    with (PACKET/'COMPARISON.json').open('x') as f:
        json.dump(summary, f, indent=2, allow_nan=False)
        f.write('\n')
    with (PACKET/'CHANNEL_COMPARISON.csv').open('x',newline='') as f:
        w=csv.writer(f,lineterminator='\n')
        w.writerow(['step_index','channel_id','name','observed_BT_K','background_BT_K','old_3budget_BT_K','new_8budget_BT_K','O_minus_B_K','O_minus_A3_K','O_minus_A8_K','source_DQF','old_rq','new_rq'])
        w.writerows(rows)
    print(json.dumps(summary, allow_nan=False))


if __name__ == '__main__':
    main()
