#!/usr/bin/env python3
"""Read the one hash-bound Jul19 case; never call M, H or the optimizer.

The new calculation is endpoint/input equivalence. Existing BT/cost/physical
diagnostics are read from their original records, not rerun. Full arrays stay
private. An inferred identity-H value is not a new RTTOV callback.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
PACKET = Path(__file__).resolve().parent
PRIVATE = Path('/Users/yhlee/KDM6AD-k/host/research_evidence/pr397_native_tq_20261010')
CAPTURE = PRIVATE / 'accepted_final_3d2e97f159.npz'
RECEIPT = ROOT / 'harness/evidence/pr395_tq_state_capture_2026-10-10/RESULT_3d2e97f159.json'
DIAGNOSTIC = ROOT / 'harness/evidence/pr397_actual_native_results_2026-10-10/ACTUAL_ARRAY_CALCULATIONS.json'
FIELDS = ('th', 'qv', 'qc', 'qr', 'qi', 'qs', 'qg', 'nccn', 'nc', 'ni', 'nr', 'bg')
STATES = {'xb': ('background_initial_state', 'background_initial'),
          'xa': ('returned_analysis_initial_state', 'returned_analysis_initial'),
          'mb': ('background_slot_state', 'background_slot'),
          'ma': ('final_slot_state', 'final_slot')}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_sha(array):
    return hashlib.sha256(np.ascontiguousarray(array, dtype=np.float64).tobytes()).hexdigest()


def bits_equal(a, b):
    return bool(np.array_equal(a.view(np.uint64), b.view(np.uint64)))


def main():
    assert sha(CAPTURE) == '8cfe28df6ef336454cfa595cc70f7a4ddec2e5cd8cbd393c0c7ce8106c904c59'
    assert sha(RECEIPT) == 'c49808c0331754eeb9ab9f77a88083119d5834852281db890b2827f6acf6eeca'
    assert sha(DIAGNOSTIC) == '8dc83999f4759e16140ea3d943ef288bf16c0254554abfb5b663b58222bc35bf'
    r = json.loads(RECEIPT.read_text())
    d = json.loads(DIAGNOSTIC.read_text())
    with np.load(CAPTURE, allow_pickle=False) as archive:
        z = {k: archive[k].copy() for k in archive.files}
    states = {name: {f: z[f'{prefix}__{f}'] for f in FIELDS}
              for name, (prefix, _) in STATES.items()}
    for name, (_, recorded) in STATES.items():
        for f, arr in states[name].items():
            assert arr.dtype == np.float64 and arr.shape == (1, 39)
            assert np.isfinite(arr).all()
            assert array_sha(arr) == r['state_array_sha256'][recorded][f]
    forcing = {f: z[f'forcing_window_0__{f}'] for f in ('rho', 'pii', 'p', 'delz')}
    assert len(r['forcing_array_sha256']['forcing_window']) == 1
    forcing_sha = r['forcing_array_sha256']['forcing_window'][0]
    assert forcing_sha == r['forcing_array_sha256']['background_slot'] == r['forcing_array_sha256']['final_slot']
    for f, arr in forcing.items():
        assert arr.dtype == np.float64 and arr.shape == (1, 39)
        assert bits_equal(arr, z[f'final_slot_forcing__{f}'])
        assert array_sha(arr) == forcing_sha[f]
    assert array_sha(z['rho_d_native_bottomup_kg_m3']) == r['frozen_optical_rho_d']['sha256_f64']
    # These unchanged source files own theta->T, cloud inputs and fixed auxiliaries.
    sources = {p: digest for p, digest in r['production_source_sha256_before_after']['before'].items()}
    assert sources == r['production_source_sha256_before_after']['after']
    for p, digest in sources.items():
        assert sha(ROOT / p) == digest
    endpoint_pairs = []
    torch.set_num_threads(1)
    for first, last in (('xb', 'mb'), ('xa', 'ma')):
        a, b = states[first], states[last]
        diff = {f: {'bitwise_equal': bits_equal(a[f], b[f]),
                    'max_abs_difference': float(np.max(np.abs(b[f] - a[f])))} for f in FIELDS}
        # NumPy and Torch independently evaluate the executed T=theta*pii projection.
        t0, t1 = a['th'] * forcing['pii'], b['th'] * forcing['pii']
        tt0 = (torch.from_numpy(a['th']) * torch.from_numpy(forcing['pii'])).numpy()
        tt1 = (torch.from_numpy(b['th']) * torch.from_numpy(forcing['pii'])).numpy()
        assert bits_equal(t0, tt0) and bits_equal(t1, tt1)
        equivalent = bits_equal(t0, t1) and all(diff[f]['bitwise_equal'] for f in FIELDS[1:])
        endpoint_pairs.append({'states': [first, last], 'state_field_comparison': diff,
                               'physical_temperature_K': {'bitwise_equal': bits_equal(t0, t1),
                                  'max_abs_difference_K': float(np.max(np.abs(t1-t0))),
                                  'before_sha256_f64': array_sha(t0), 'after_sha256_f64': array_sha(t1),
                                  'numpy_matches_torch_projection': True},
                               'source_input_equivalence': equivalent})
    first = r['logical_h_calls'][r['objective']['initial_zero_control_closure']['first_grad_true_h_call_index']-1]
    final = r['logical_h_calls'][-1]
    for event, state in ((first, 'background_slot'), (final, 'final_slot')):
        assert event['returned'] and event['grad']
        assert event['state_sha256'] == r['state_array_sha256'][state]
        assert event['forcing_sha256'] == forcing_sha
        assert event['channels'] == list(range(10, 17))
        assert event['fixed_mask'] == event['frozen_mask'] == [[1.0]*7]
        assert event['rad_quality'] == [[0.0]*7]
    assert first['J_huber'] == d['objective']['Jo0']
    assert final['J_huber'] == d['objective']['Jo_final']
    measured = {'H_Mxb': {'call_index': first['call_index'], 'BT_K': first['BT_K'], 'Jo': first['J_huber']},
                'H_Mxa': {'call_index': final['call_index'], 'BT_K': final['BT_K'], 'Jo': final['J_huber']}}
    equivalent = all(p['source_input_equivalence'] for p in endpoint_pairs)
    result = {'schema': 'pr410_one_retained_case_claims_v1',
       'scope': 'One already executed Jul19 case; new retained-array comparison only',
       'source_main': '4ebe3d766cedfd6f85c8e20cb5dd2cae809a38af',
       'source_sha256': sha(__file__), 'executed_source_hashes_match_current_files': sources,
       'inputs': {'capture_sha256': sha(CAPTURE), 'receipt_sha256': sha(RECEIPT),
                  'existing_diagnostic_sha256': sha(DIAGNOSTIC)},
       'new_calls': {'native': 0, 'KDM_M': 0, 'RTTOV_H_K': 0, 'optimizer': 0},
       'environment': {'numpy': np.__version__, 'torch': torch.__version__, 'torch_threads': 1},
       'endpoint_pairs': endpoint_pairs, 'stored_actual_H_outputs': measured,
       'direct_initial_H_outputs': {'H_xb': 'NOT_EXECUTED_OR_STORED', 'H_xa': 'NOT_EXECUTED_OR_STORED'},
       'conditional_inference': {'status': 'SOURCE_INPUT_EQUIVALENCE' if equivalent else 'UNAVAILABLE',
          'assumption': 'Same fixed auxiliaries and deterministic unchanged executed H; inferred, not new H evaluations',
          'R_M_xb_K': [0.0]*7 if equivalent else None,
          'R_M_xa_K': [0.0]*7 if equivalent else None,
          'I_M_K': [0.0]*7 if equivalent else None,
          'G_M_measured': first['J_huber']-final['J_huber'],
          'G_0_inferred': first['J_huber']-final['J_huber'] if equivalent else None,
          'G_M_minus_G_0_inferred': 0.0 if equivalent else None,
          'not_established': ['M_x=I', 'zero internal process rates', 'named-process cause',
                              'reoptimized no-M performance', 'cloud truth', 'forecast skill']},
       'existing_state_diagnostics_read_not_rerun': {
          k: d[k] for k in ('objective', 'initial_increment', 'liquid_saturation_ratio',
                'four_state_condensate_positive_counts', 'fixed_host_mass_water_kg_m2',
                'native_host_20s_water_change_kg_m2', 'named_process_attribution')},
       'limits': ['No measured H(xb)/H(xa) output vectors are manufactured',
                  'PR398/399 host/neighbor H bindings do not fill the initial-state H gap',
                  'Original RTTOV executable/coefficient hashes are not recorded in this receipt',
                  'Original outer harness exit120, nominal time and finite-gradient limits remain',
                  'No independent date, score reassessment or raw private-array publication']}
    with (PACKET / 'RESULT.json').open('x') as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'input_equivalence': equivalent, 'new_model_H_optimizer_calls': 0,
                      'result': str(PACKET / 'RESULT.json')}))


if __name__ == '__main__':
    main()
