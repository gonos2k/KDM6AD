#!/usr/bin/env python3
"""Read saved CSV/receipt only; changes at moving native eta levels, not tendencies."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

PACKET = Path(__file__).resolve().parent


def main():
    summary = json.loads((PACKET / 'SUMMARY.json').read_text())
    csv_path = PACKET / 'PROFILE.csv'
    if hashlib.sha256(csv_path.read_bytes()).hexdigest() != summary['profile_csv']['sha256']:
        raise ValueError('saved profile changed')
    rows = list(csv.DictReader(csv_path.open()))
    times = summary['times']
    groups = {t: [r for r in rows if r['time'] == t] for t in times}
    if len(rows) != 117 or any(len(g) != 39 for g in groups.values()):
        raise ValueError('expected three39-level profiles')
    fields = ['temperature_K', 'theta_dry_K', 'QVAPOR', 'QCLOUD', 'pressure_center_Pa',
              'z_center_m', 'delz_m', 'rho_d_kg_m3', 'rho_m_kg_m3', 'U_east_ms', 'V_north_ms']
    pairs = []
    for a, b in zip(times, times[1:]):
        if [r['model_k'] for r in groups[a]] != [r['model_k'] for r in groups[b]]:
            raise ValueError('native level index order changed')
        changes = {}
        for field in fields:
            delta = np.array([float(r[field]) for r in groups[b]]) - np.array([float(r[field]) for r in groups[a]])
            k = int(np.argmax(abs(delta)))
            changes[field] = {'max_abs_change': float(abs(delta[k])), 'signed_change_at_max': float(delta[k]),
                              'native_model_k': int(groups[a][k]['model_k']), 'RMS_change': float(np.sqrt(np.mean(delta**2)))}
        pairs.append({'from': a, 'to': b, 'elapsed_s': 3600, 'changes_at_same_native_eta_index': changes})
    result = {'schema': 'pr416_saved_hourly_changes_v1', 'source_summary_sha256': hashlib.sha256((PACKET/'SUMMARY.json').read_bytes()).hexdigest(),
              'source_csv_sha256': summary['profile_csv']['sha256'], 'hour_pairs': pairs,
              'samples': [{'time':s['time'], 'QCLOUD_path_g_m2':1000*s['hydrometeor_column_mass_kg_m2']['QCLOUD'],
                          'QRAIN_path_g_m2':1000*s['hydrometeor_column_mass_kg_m2']['QRAIN'],
                          'host_dry_column_mass_kg_m2':s['host_dry_mass_sum_kg_m2'], 'surface':s['surface']} for s in summary['samples']],
              'comparison_coordinates':'same native eta index; pressure and geometric height change; not fixed-height/isobaric tendency',
              'no_forecast_reopen_or_new_model_H_calls':True, 'not_current_retained_case_equivalence':True,
              'no_interpolated_host_state_0606_0616':True, 'no_individual_process_or_closed_flux_budget_claim':True}
    with (PACKET/'CHANGES.json').open('x') as f:
        json.dump(result,f,indent=2,allow_nan=False)
        f.write('\n')
    print(json.dumps({'status':'SAVED_HOURLY_CHANGES_ONLY','pairs':len(pairs)}))


if __name__ == '__main__':
    main()
