#!/usr/bin/env python3
"""Read saved window only; independent per-slot cost and fixed-mass diagnostics."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

PACKET = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def loss(bt, y):
    r = np.asarray(bt) - np.asarray(y)
    return float(np.where(abs(r) <= 1, 0.5 * r**2, abs(r) - 0.5).sum())


def main():
    plan = json.loads((PACKET / 'WINDOW_PREDECLARED.json').read_text())
    result_path = Path(plan['output_root']) / 'RESULT.json'
    result = json.loads(result_path.read_text())
    checkpoint = Path(result['checkpoint']['path'])
    if sha(checkpoint) != result['checkpoint']['sha256']:
        raise ValueError('private checkpoint mismatch')
    with np.load(checkpoint, allow_pickle=False) as z:
        a = {k: z[k] for k in z.files}
    with np.load(plan['intake_npz'], allow_pickle=False) as z:
        mass = z['host_dry_mass_background_kg_m2'].astype(np.float64)
    def water(label):
        return float(sum((a[label + '__' + f] * mass).sum() for f in ('qv', 'qc', 'qr', 'qi', 'qs', 'qg')))
    jb = 0.5 * float((a['control__v_state'] ** 2).sum())
    if not np.isclose(jb, result['final_J_b'], rtol=0, atol=1e-12):
        raise ValueError('saved control prior mismatch')
    rows, slot_results = [], []
    for scene, bg, accepted in zip(result['observations'], result['baseline'], result['accepted']):
        t = scene['step_index']
        y = a[f'observations_{t}__y_bt'].reshape(7)
        b, x = a[f'background_{t}__bt'], a[f'accepted_{t}__bt']
        if not np.isclose(loss(b, y), bg['J_o'], atol=1e-10) or not np.isclose(loss(x, y), accepted['J_o'], atol=1e-10):
            raise ValueError('checkpoint BT independent loss mismatch')
        for k, name in enumerate(('WV073', 'IR087', 'IR096', 'IR105', 'IR112', 'IR123', 'IR133')):
            rows.append([scene['nominal_slot_obt'], t, k + 10, name, y[k], b[k], x[k], y[k] - b[k], y[k] - x[k], 0, 0])
        slot_results.append({'nominal_slot_obt': scene['nominal_slot_obt'], 'step_index': t,
                             'J_o_background': loss(b, y), 'J_o_accepted': loss(x, y),
                             'MAE_background_K': float(abs(b - y).mean()), 'MAE_accepted_K': float(abs(x - y).mean()),
                             'background_QC_max': float(a[f'background_slot_{t}__qc'].max()),
                             'accepted_QC_max': float(a[f'accepted_slot_{t}__qc'].max()),
                             'background_water_fixed_mass_kg_m2': water(f'background_slot_{t}'),
                             'accepted_water_fixed_mass_kg_m2': water(f'accepted_slot_{t}')})
    summary = {'result_sha256': sha(result_path), 'checkpoint_sha256': sha(checkpoint), 'slots': slot_results,
               'initial_J': result['initial_J_o'], 'final_J': result['final_J'],
               'total_cost_reduction_percent': 100 * (result['initial_J_o'] - result['final_J']) / result['initial_J_o'],
               'analysis_initial_water_change_fixed_mass_kg_m2': water('accepted_initial') - water('background_initial'),
               'initial_T_increment_max_abs_K': float(abs((a['accepted_initial__th'] - a['background_initial__th']) * a['forcing__pii']).max()),
               'initial_qv_increment_max_abs_kg_kg_dry': float(abs(a['accepted_initial__qv'] - a['background_initial__qv']).max()),
               'gradient_Linf': float(abs(a['control__gradient_state']).max()),
               'gradient_L2': float(np.linalg.norm(a['control__gradient_state'])),
               'no_new_M_H_optimizer_calls': True, 'water_is_fixed_measure_not_external_flux_budget': True}
    with (PACKET / 'WINDOW_SUMMARY.json').open('x') as f:
        json.dump(summary, f, indent=2, allow_nan=False)
        f.write('\n')
    with (PACKET / 'WINDOW_CHANNELS.csv').open('x', newline='') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(['nominal_slot_obt', 'step_index', 'channel_id', 'name', 'observed_BT_K', 'background_local_BT_K', 'accepted_local_BT_K', 'O_minus_B_K', 'O_minus_A_K', 'reader_DQF', 'model_rad_quality'])
        writer.writerows(rows)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
