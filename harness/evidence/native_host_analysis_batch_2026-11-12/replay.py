#!/usr/bin/env python3
"""Recompute the saved-data and CI-log analysis batch without model calls."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST_SHA = '1db90ceacf35b6c08392714f73d135aa4f42c7046fc3e68fa2c8520d85791989'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def module(name):
    spec = importlib.util.spec_from_file_location('native_host_analysis_' + name, HERE / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def assets():
    raw = (HERE / 'manifest.json').read_bytes()
    need(hashlib.sha256(raw).hexdigest() == MANIFEST_SHA, 'batch manifest SHA')
    manifest = json.loads(raw)
    need(manifest['schema'] == 'kdm6.native_host_analysis_batch.v1'
         and manifest['parent_research_merge'] == '496f2879a943d09f265dd2a7a7425fe5ca87a8b7',
         'batch manifest identity')
    expected = {str(p.relative_to(HERE)) for p in (HERE / 'raw/ci_runs').iterdir() if p.is_file()}
    expected.update(('full_output_fd.py', 'full_output_fd.json.gz',
                     'f32_f64_diff.py', 'f32_f64_diff.json.gz',
                     'ci_timing.py', 'ci_timing.json',
                     'reviewed_source/verify_state_forcing_ad.py.gz'))
    need(set(manifest['files']) == expected, 'batch asset inventory')
    for name, digest in manifest['files'].items():
        need(hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest,
             'batch asset SHA: ' + name)


def replay():
    assets()
    fd = module('full_output_fd')
    full = fd.derive(fd.load_parent())
    saved_full = json.loads(gzip.decompress((HERE / 'full_output_fd.json.gz').read_bytes()))
    need(full == saved_full and len(full['rows']) == 2 * 3 * 468, 'full output FD saved result')

    diff = module('f32_f64_diff')
    selected_path = diff.F32 / 'selected_full.json'
    b1_path = diff.F32 / 'b1_replay.json'
    selected = json.loads(selected_path.read_bytes())
    b1 = json.loads(b1_path.read_bytes())
    f64 = json.loads(gzip.decompress(diff.F64.read_bytes()))
    comparison = diff.analyze(selected, b1, f64, diff.sha(selected_path))
    comparison['source_files'] = {
        'selected_full_sha256': diff.sha(selected_path),
        'b1_replay_sha256': diff.sha(b1_path),
        'baseline_probe_gzip_sha256': diff.sha(diff.F64),
    }
    saved_comparison = json.loads(gzip.decompress((HERE / 'f32_f64_diff.json.gz').read_bytes()))
    need(comparison == saved_comparison, 'f32/f64 saved comparison')

    timing = module('ci_timing')
    measured = timing.analyze()
    need(measured == json.loads((HERE / 'ci_timing.json').read_bytes()), 'CI timing saved result')

    h = 1e-5
    resolved = {}
    for center in ('lower', 'upper'):
        rows = [row for row in full['rows']
                if row['center'] == center and row['h_requested'] == h
                and row['signal'] == 'distinct_words']
        resolved[center] = {
            'count': len(rows),
            'fields_and_levels': [[row['field'], row['level_bottom_first']] for row in rows],
            'max_unit_scale_normalized_output_error': max(
                (row['unit_scale_normalized_output_error'] for row in rows), default=0.0),
            'max_field_scaled_absolute_derivative_error': max(
                (row['field_scaled_absolute_derivative_error'] for row in rows), default=0.0),
            'max_field_scaled_absolute_output_residual': max(
                (row['field_scaled_absolute_output_residual'] for row in rows), default=0.0),
            'max_output_ulp_residual': max((row['output_ulp_residual'] for row in rows), default=0.0),
        }
    return {
        'schema': 'kdm6.native_host_analysis_batch_replay.v1',
        'scope': 'saved #583 TH16 direction and #583 CI logs; no new KDM or RTTOV calls',
        'full_output_fd_rows': len(full['rows']),
        'resolved_at_h_1e_minus_5': resolved,
        'f32_f64_baseline_mismatch_count': comparison['summary']['rounded_mismatch_count'],
        'f32_f64_mismatches_by_field': comparison['summary']['mismatches_by_field'],
        'ci_oracle_wall_seconds': measured['critical_path_seconds'],
        'ci_evidence_wall_seconds': {
            mode: measured['evidence_modes'][mode]['wall_seconds']
            for mode in ('normal', 'optimized')},
        'ci_suites_per_mode': measured['evidence_modes']['normal']['suite_count'],
        'scientific_status': 'INCONCLUSIVE',
        'physical_unit_status': 'INCONCLUSIVE',
    }


if __name__ == '__main__':
    (HERE / 'results.json').write_text(json.dumps(replay(), indent=2, sort_keys=True) + '\n')
