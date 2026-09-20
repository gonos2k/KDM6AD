#!/usr/bin/env python3
"""Replay fixed-column size arithmetic; does not certify number units or RTTOV."""
import argparse
import json
import math
from pathlib import Path

DEFAULT = Path(__file__).parent / 'evidence/number_size_2026-09-20.json'
PIDNC = 523.5988159179688  # retained scheme f32 constant, not ideal pi*rho_w/6
INV_THREE = 0.3333333432674408  # scheme f32 reciprocal
RADIUS_FACTOR = math.gamma(2.0) / (2 * math.gamma(5.0 / 3.0))


def cloud_size(q, number, mass_density, number_floor):
    """Mirror executed scalar arithmetic, including inactive and optical gates."""
    assert all(math.isfinite(x) for x in (q, number, mass_density, number_floor))
    assert q >= 0 and number >= 0 and mass_density > 0 and number_floor >= 0.01
    active = q > 1e-15 and number > number_floor
    ratio = PIDNC * number / max(q * mass_density, 1e-30)
    slope_inverse = 1 / math.exp(math.log(max(ratio, 1e-30)) * INV_THREE)
    if not active:
        slope_inverse = 1 / 5e5
    raw_radius = slope_inverse * RADIUS_FACTOR * 1e6
    radius = min(50.0, max(2.51, raw_radius))
    return {'active': active, 'rslope_m': slope_inverse,
            'raw_radius_um': raw_radius, 'radius_um': radius,
            'diameter_um': min(52.0, max(2.0, 2 * radius))}


def ideal_dry_radius(q, n):
    """Positive dry-mass moment pair; no empirical gates or f32 constants."""
    assert all(math.isfinite(x) and x > 0 for x in (q, n))
    return RADIUS_FACTOR * (q / ((math.pi * 1000 / 6) * n)) ** (1 / 3) * 1e6


def replay(data):
    if not __debug__:
        raise RuntimeError('Run without -O: replay assertions must remain enabled')
    assert data['scope'] == 'conditional_number_size_arithmetic'
    assert data['accepted_observation_cost'] is False
    assert data['physical_number_contract_resolved'] is False
    rows = data['rows']
    assert len(rows) == 39 and [r['user_layer'] for r in rows] == list(range(1, 40))
    assert all(rows[i]['pressure_hpa'] < rows[i+1]['pressure_hpa'] for i in range(38))
    assert set(data['retained_input']) == {'P', 'P_HALF', 'HYDRO6', 'HYDRO_DEFF6'}
    retained = {k: [float(x) for x in v['tokens']] for k, v in data['retained_input'].items()}
    for name, values in retained.items():
        assert len(values) == (40 if name == 'P_HALF' else 39)
        assert all(math.isfinite(x) for x in values)
    assert [r['pressure_hpa'] for r in rows] == retained['P']
    assert all(retained['P_HALF'][i] < retained['P'][i] < retained['P_HALF'][i+1]
               for i in range(39))
    result = []
    for row in rows:
        assert row['native_layer_0based'] == 39-row['user_layer']
        q, n, rho, dry, qv = (row[k] for k in ('qc', 'nc', 'rho', 'rho_d', 'background_qv'))
        assert all(math.isfinite(x) for x in (q, n, rho, dry, qv, row['pressure_hpa']))
        assert dry > 0 and qv >= 0 and row['pressure_hpa'] > 0
        assert math.isclose(rho, dry*(1+qv), rel_tol=2e-15, abs_tol=0)
        ideal = ideal_dry_radius(q, n) if q > 0 and n > 0 else None
        if ideal is None:
            assert row['ideal_dry_raw_radius_um'] is None
        else:
            assert math.isclose(row['ideal_dry_raw_radius_um'], ideal, rel_tol=2e-13, abs_tol=0)
        modes = {'legacy': (q, n, rho), 'number_only': (q, dry*n, rho),
                 'coherent_dry': (dry*q, dry*n, 1.0)}
        assert set(row['diagnostics']) == set(modes)
        evaluated = {}
        for name, (mass_operand, number, mass_density) in modes.items():
            actual = cloud_size(mass_operand, number, mass_density, data['number_floor'])
            recorded = row['diagnostics'][name]
            assert set(recorded) == set(actual)
            assert recorded['active'] is actual['active']
            for key in set(actual)-{'active'}:
                assert math.isfinite(recorded[key])
                assert math.isclose(actual[key], recorded[key], rel_tol=2e-13, abs_tol=0)
            evaluated[name] = actual
        i = row['user_layer'] - 1
        assert math.isclose(1000*dry*q, retained['HYDRO6'][i], rel_tol=2e-15, abs_tol=0)
        assert math.isclose(evaluated['legacy']['diameter_um'], retained['HYDRO_DEFF6'][i],
                            rel_tol=2e-13, abs_tol=0)
        result.append({'user_layer': row['user_layer'], 'diagnostics': evaluated})
    return {'scope': 'arithmetic_replay_only', 'physical_number_contract_resolved': False,
            'accepted_observation_cost': False, 'layers': result}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path, default=DEFAULT)
    args = parser.parse_args()
    print(json.dumps(replay(json.loads(args.json.read_text())), indent=2))
