#!/usr/bin/env python3
"""Replay public cap arithmetic and column weights; does not execute RTTOV."""
import argparse
import json
import math
from pathlib import Path

DEFAULT = Path(__file__).parent / 'evidence/extinction_layers_2026-09-20.json'
EXPECTED_FILES = {
    'direct/radiance.txt', 'direct/transmission.txt',
    'k/radiance.txt', 'k/transmission.txt', 'k/profiles_k.txt',
}


def replay(data):
    if not __debug__:
        raise RuntimeError('Run without -O: replay assertions must remain enabled')
    fields = data['row_fields']
    assert fields == ['channel', 'combination', 'user_layer', 'clear_raw', 'clear_floored', 'liquid', 'ice', 'pre', 'post', 'active_boolean', 'margin']
    assert data['threshold'] == 20 and data['selected_observation_channels_1based'] == list(range(8, 17))
    expected = {(ch, h, k) for ch in range(7, 17) for h in (0, 1) for k in range(1, 40)}
    base = {tuple(r[:3]): r for r in data['baseline_rows']}
    assert len(data['baseline_rows']) == len(base) == 780 and set(base) == expected
    p, half = data['pressure_hpa'], data['half_pressure_hpa']
    assert len(p) == 39 and len(half) == 40
    assert all(math.isfinite(v) for v in p+half)
    assert all(half[k] < p[k] < half[k+1] for k in range(39))
    columns = {c['column']: c for c in data['cloud_columns']}
    assert len(columns) == len(data['cloud_columns']) == 19 and set(columns) == set(range(19))
    assert all(math.isfinite(c['weight']) and c['weight'] >= 0 for c in columns.values())
    assert math.isclose(math.fsum(c['weight'] for c in columns.values()), 1, abs_tol=1e-14, rel_tol=0)
    assert all(len(c['combination_by_user_layer']) == 39 and
               all(h in (0, 1) for h in c['combination_by_user_layer']) for c in columns.values())
    baseline_mask = None
    assert len(data['cases']) == 5 and len({c['name'] for c in data['cases']}) == 5
    for case in data['cases']:
        rows = dict(base)
        replacements = {tuple(r[:3]): r for r in case['replacement_rows']}
        assert len(replacements) == len(case['replacement_rows']) and set(replacements) <= expected
        assert case['unchanged_count'] == 780-len(replacements)
        rows.update(replacements)
        mask = set()
        for key, row in rows.items():
            assert len(row) == len(fields)
            r = dict(zip(fields, row))
            assert all(math.isfinite(x) for x in row)
            assert isinstance(r['active_boolean'], bool)
            assert r['active_boolean'] == (r['pre'] > data['threshold'])
            assert r['post'] == min(r['pre'], data['threshold'])
            assert r['margin'] == r['pre']-data['threshold']
            assert r['liquid'] >= 0 and r['ice'] >= 0
            assert math.isclose(r['pre'], math.fsum([r['clear_floored'], r['liquid'], r['ice']]),
                                rel_tol=1e-14, abs_tol=1e-14)
            if r['combination'] == 0:
                assert r['liquid'] == r['ice'] == 0
            if r['active_boolean']:
                mask.add(key)
        assert len(mask) == case['active_count'] == 62
        if baseline_mask is None:
            baseline_mask = mask
        assert mask == baseline_mask
        assert min(abs(r[-1]) for r in rows.values()) == case['minimum_absolute_margin']
        assert max(r[7] for r in rows.values()) == case['maximum_pre']
        rad = {(r[0], r[1]): r[2:] for r in case['radiance_rows']}
        assert len(rad) == len(case['radiance_rows']) == 190
        assert set(rad) == {(ch, q) for ch in range(7, 17) for q in columns}
        assert all(math.isfinite(v) for vals in rad.values() for v in vals)
        # Channel 7 also has a solar contribution; sum only the nine thermal IR targets.
        for ch in data['selected_observation_channels_1based']:
            totals = {rad[ch, q][1] for q in columns}
            assert len(totals) == 1
            summed = math.fsum(columns[q]['weight']*rad[ch, q][0] for q in columns)
            assert math.isclose(summed, totals.pop(), rel_tol=1e-14, abs_tol=1e-14)
    assert set(data['build_and_noninterference']['compared_files']) == EXPECTED_FILES, 'Incomplete compared_files'
    manifest = data['build_and_noninterference']['manifest']['cases']
    assert set(manifest) == {c['name'] for c in data['cases']}
    for case in manifest.values():
        assert case['returncode'] == 0
        assert case['quality_original'] == case['quality_diagnostic']
        assert len(case['quality_diagnostic']) == 16
        for ch in range(7, 17):
            assert bool(case['quality_diagnostic'][ch-1] & (1 << 15)) == any(k[0] == ch for k in baseline_mask)
        assert set(case['raw_files']) == EXPECTED_FILES, 'Incomplete raw_files'
        for entry in case['raw_files'].values():
            assert entry['byte_equal'] and entry['original_sha256'] == entry['diagnostic_sha256']
    return {'scope': 'arithmetic_replay_only', 'endpoints': 5,
            'unique_coefficients_per_endpoint': 780, 'active_per_endpoint': 62,
            'endpoint_masks_equal': True, 'accepted_observation_cost': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path, default=DEFAULT)
    args = parser.parse_args()
    print(json.dumps(replay(json.loads(args.json.read_text())), indent=2))
