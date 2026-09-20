#!/usr/bin/env python3
"""Replay finite-width optical contractions, not RTTOV or a new AD calculation."""
import argparse
from decimal import Decimal
import json
import math
from pathlib import Path

from replay_extinction_layers import EXPECTED_FILES

DEFAULT = Path(__file__).parent / 'evidence/radiance_boundary_2026-09-20.json'
NAMES = {'accretion-alpha0', 'accretion-minus-0.03', 'accretion-plus-0.03',
         'accretion-minus-0.1', 'accretion-plus-0.1'}


def replay(data):
    if not __debug__:
        raise RuntimeError('Run without -O: replay assertions must remain enabled')
    assert data['scope'] == 'finite_width_boundary_contraction'
    assert data['accepted_observation_cost'] is False
    assert data['channel_indices_1based'] == list(range(8, 17))
    assert data['epsilons'] == [.03, .1]
    tangents = data['retained_profile_tangents']['values']
    assert set(tangents) == {'T', 'Q', 'HYDRO6', 'HYDRO7', 'HYDRO_DEFF6', 'HYDRO_DEFF7'}
    assert all(len(v) == 39 and all(math.isfinite(x) for x in v) for v in tangents.values())
    assert all(all(x == 0 for x in tangents[k]) for k in ('T', 'Q', 'HYDRO7', 'HYDRO_DEFF7'))
    assert all({i+1 for i, x in enumerate(tangents[k]) if x != 0} == {25, 27, 28}
               for k in ('HYDRO6', 'HYDRO_DEFF6'))
    assert data['fields'] == ['channel', 'user_layer', 'ext_postcap', 'ssa_all',
                              'asm_all', 'lambda_ext', 'lambda_ssa', 'lambda_asm']
    expected = {(ch, k) for ch in range(8, 17) for k in range(1, 40)}
    base = {tuple(r[:2]): r[2:] for r in data['baseline_rows']}
    assert len(base) == len(data['baseline_rows']) == 351 and set(base) == expected
    assert all(len(v) == 6 and all(math.isfinite(x) for x in v) for v in base.values())
    assert set(data['compared_files']) == EXPECTED_FILES
    assert set(data['cases']) == NAMES
    cases = {}
    for name, case in data['cases'].items():
        assert set(case['raw_files']) == EXPECTED_FILES
        for f in case['raw_files'].values():
            assert f['byte_equal'] is True and f['original_sha256'] == f['diagnostic_sha256']
        rows = {tuple(r[:2]): r[2:] for r in case['replacement_rows']}
        assert len(rows) == len(case['replacement_rows']) and set(rows) <= expected
        assert all(len(v) == 3 and all(math.isfinite(x) for x in v) for v in rows.values())
        assert len(case['raw_BT_tokens']) == 9 and all(Decimal(v).is_finite() for v in case['raw_BT_tokens'])
        assert case['quality'] == [32768]*9
        cases[name] = {k: rows.get(k, v[:3]) for k, v in base.items()}
    assert cases['accretion-alpha0'] == {k: v[:3] for k, v in base.items()}
    refs = {r['channel_index_0_based']+1: r['forward_JVP_K_per_alpha'] for r in data['references']}
    assert len(data['references']) == len(refs) == 9 and set(refs) == set(range(8, 17))
    assert all(math.isfinite(x) and x != 0 for x in refs.values())
    assert set(data['summary']) == {'0.03', '0.1'}
    result = []
    for eps in data['epsilons']:
        plus_name, minus_name = f'accretion-plus-{eps}', f'accretion-minus-{eps}'
        plus, minus = cases[plus_name], cases[minus_name]
        reports = {r['ch']: r for r in data['summary'][str(eps)]}
        assert len(data['summary'][str(eps)]) == len(reports) == 9 and set(reports) == set(refs)
        for ch in range(8, 17):
            parts = [math.fsum(base[k][j+3]*(plus[k][j]-minus[k][j])/(2*eps)
                              for k in expected if k[0] == ch) for j in range(3)]
            total = math.fsum(parts)
            relative = abs(total-refs[ch])/max(abs(total), abs(refs[ch]))
            report = reports[ch]
            assert len(report['parts']) == 3 and report['JVP'] == refs[ch]
            for actual, recorded in zip(parts+[total, relative], report['parts']+[report['sum'], report['relative_error']]):
                assert math.isfinite(recorded) and math.isclose(actual, recorded, rel_tol=1e-13, abs_tol=0)
            bt_plus = Decimal(data['cases'][plus_name]['raw_BT_tokens'][ch-8])
            bt_minus = Decimal(data['cases'][minus_name]['raw_BT_tokens'][ch-8])
            direct_fd = float((bt_plus-bt_minus)/(2*Decimal(str(eps))))
            result.append({'epsilon': eps, 'channel': ch, 'contributions': parts,
                           'sum': total, 'relative_difference_from_JVP': relative,
                           'direct_BT_FD': direct_fd})
    return {'scope': 'arithmetic_replay_only', 'accepted_observation_cost': False,
            'comparisons': result}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path, default=DEFAULT)
    args = parser.parse_args()
    print(json.dumps(replay(json.loads(args.json.read_text())), indent=2))
