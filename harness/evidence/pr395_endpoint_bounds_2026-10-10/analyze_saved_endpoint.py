#!/usr/bin/env python3
"""Bounded arithmetic/known-zero identity from public historical receipts only."""
from pathlib import Path
import hashlib
import importlib.util
import json
import math

ROOT = Path(__file__).resolve().parents[3]
REAL = ROOT / 'harness/evidence/pr394_real_tq_diagnostic_2026-10-10/RESULT.json'
BOUND = ROOT / 'harness/evidence/pr394_prior_boundary_2026-10-10/RESULT.json'
MATH = BOUND.with_name('analyze_boundary.py')


def analyze() -> dict:
    real = json.loads(REAL.read_text())
    boundary = json.loads(BOUND.read_text())
    a = real['analysis']
    shape = a['callback_metadata']['native_state_shape']
    if shape != [1, 39]:
        raise ValueError('known-zero identity is restricted to the recorded [1,39] f64 shape')
    digest = hashlib.sha256(bytes(39 * 8)).hexdigest()
    fields = ('qc', 'qr', 'qi', 'qs', 'qg', 'nc', 'ni', 'nr', 'bg')
    final = a['callback_trace'][-1]
    matching = {f: final['input_state_sha256'][f] == digest for f in fields}
    if not all(matching.values()):
        raise ValueError('final callback does not match the declared positive-zero arrays')
    th_sigma, q_sigma = 0.8, 0.08
    th_norm = a['state_increment_norms']['th']
    u_norm = th_norm / th_sigma
    w_norm = math.sqrt(2 * a['Jb_state'] - u_norm * u_norm)
    if not math.isclose(math.sqrt(2 * a['Jb_state']), a['v_state_norm'], abs_tol=1e-14):
        raise ValueError('recorded prior and control norms disagree')
    base = boundary['selected_baseline']
    delta_t_bound = base['Exner_from_saved_delta_T_over_delta_theta'] * th_norm
    spec = importlib.util.spec_from_file_location('saved_boundary_math', MATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    qs, slope, _ = module.water_qs_and_log_derivative(
        base['T_b_K'] - delta_t_bound, base['p_Pa'],
        boundary['thermo_constants_from_clear_receipt'])
    if slope <= 0:
        raise ValueError('water saturation monotonicity assumption failed')
    water_ratio_bound = base['q_b_dry_kgkg'] * math.exp(q_sigma * w_norm) / qs
    return {
        'schema': 'pr395_saved_endpoint_bounds_v1',
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (REAL, BOUND, MATH, Path(__file__))},
        'scope': 'Historical failed-native checkpoint diagnostic; no new native, M or RTTOV execution',
        'known_zero_endpoint': {'shape': shape, 'dtype': 'float64', 'positive_zero_bytes': 312,
                               'sha256': digest, 'matching_fields': matching,
                               'interpretation': 'Final H callback has zero condensate and these particle fields under the recorded serialization/shape and conventional SHA identity assumption; not hash inversion or direct private-array read',
                               'transient_intermediate_cloud_excluded': False},
        'prior_coordinate_bounds': {
            'control_norm': math.sqrt(2 * a['Jb_state']), 'th_block_norm': u_norm,
            'qv_block_norm': w_norm,
            'qv_relative_lower_percent': 100 * math.expm1(-q_sigma * w_norm),
            'qv_relative_upper_percent': 100 * math.expm1(q_sigma * w_norm),
            'selected_k3_initial_delta_T_abs_upper_K': delta_t_bound,
            'selected_k3_initial_water_ratio_upper': water_ratio_bound,
            'actual_layer_increment_vector_recovered': False,
            'applies_to_model_endpoint_or_all_39_layer_RH': False},
        'management_score': {'points': 54, 'denominator': 75, 'percent': 72},
    }


if __name__ == '__main__':
    output = Path(__file__).with_name('RESULT.json')
    with output.open('x') as stream:
        json.dump(analyze(), stream, indent=2, allow_nan=False)
        stream.write('\n')
