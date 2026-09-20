#!/usr/bin/env python3
"""Conditional boundary arithmetic, not a production number-unit adapter."""
import argparse
import json
import math
from pathlib import Path

DEFAULT = Path(__file__).parent / 'evidence/number_boundary_2026-09-20.json'


def to_volume(value, density, tangent=0.0, density_tangent=0.0):
    """Map one declared dry-mass quantity and its directional derivative."""
    if not all(math.isfinite(x) for x in (value, density, tangent, density_tangent)) or density <= 0:
        raise ValueError('finite operands and positive dry density required')
    result = density*value, density*tangent + value*density_tangent
    if not all(math.isfinite(x) for x in result):
        raise ValueError('nonfinite volume representation')
    return result


def to_mass(value, density, tangent=0.0, density_tangent=0.0):
    """Inverse map at the same density; no process generation is implied."""
    if not all(math.isfinite(x) for x in (value, density, tangent, density_tangent)) or density <= 0:
        raise ValueError('finite operands and positive dry density required')
    mass_value = value/density
    result = mass_value, (tangent-mass_value*density_tangent)/density
    if not all(math.isfinite(x) for x in result):
        raise ValueError('nonfinite mass representation')
    return result


def paired_transfer(number, density, thickness, amount):
    """Two-cell representation witness using a prescribed physical #/m2 transfer.

    This is not a KDM sedimentation calculation. The same amount leaves one
    cell and arrives in the other, without independent caps or bottom loss.
    """
    if not (len(number) == len(density) == len(thickness) == 2):
        raise ValueError('exactly two cells required')
    if not math.isfinite(amount) or amount < 0:
        raise ValueError('nonnegative finite transfer required')
    if any(not math.isfinite(z) or z <= 0 for z in thickness):
        raise ValueError('positive finite thickness required')
    volume = [to_volume(n, r)[0] for n, r in zip(number, density)]
    if any(n < 0 for n in number) or amount > volume[0]*thickness[0]:
        raise ValueError('transfer exceeds donor inventory')
    volume_after = [volume[0]-amount/thickness[0], volume[1]+amount/thickness[1]]
    mass_after = [number[0]-amount/(density[0]*thickness[0]),
                  number[1]+amount/(density[1]*thickness[1])]
    return mass_after, [to_mass(n, r)[0] for n, r in zip(volume_after, density)]


def _close(actual, expected):
    # A few binary64 rounding steps, not a physical relative tolerance.
    assert math.isfinite(actual) and math.isfinite(expected)
    assert abs(actual-expected) <= 8*max(math.ulp(actual), math.ulp(expected))


def replay(data):
    if not __debug__:
        raise RuntimeError('assertions must remain enabled')
    assert data['schema'] == 'number-boundary-v1'
    for flag in ('physical_number_basis_resolved', 'accepted_observation_cost',
                 'native_transport_measured'):
        assert data[flag] is False
    assert data['source_contract']['native_host_claim'] is False
    assert data['source_contract']['external_data'] is False
    assert data['scope']['column'] == 35711
    assert data['scope']['native_mass_levels'] == 39
    assert data['scope']['alpha_accretion'] == 0
    assert data['execution']['offline_kdm_baseline_steps'] == 1
    assert data['execution']['rttov_calls'] == 0
    assert data['execution']['wrapper_restored'] is True
    dt = data['execution']['dt_seconds']
    assert dt == 20
    assert [r['native_layer'] for r in data['rows']] == [11, 12, 14]
    p = data['accretion_params']
    for r in data['rows']:
        assert r['user_layer'] == 39-r['native_layer']
        assert math.isfinite(r['supcol']) and math.isfinite(r['dz_m']) and r['dz_m'] > 0
        a, gates = r['operands'], r['producer_gates']
        assert all(math.isfinite(x) for x in a.values())
        assert all(math.isfinite(x) for x in p.values())
        assert a['den'] > 0 and a['qc'] > 0 and a['nc'] > 0
        # These measured rows all use the large-drop branch. This replay does
        # not purport to validate the unselected small-drop expression.
        assert a['qr'] >= a['lenconcr'] and a['avedia_r'] >= p['di100']
        assert gates['rain_active_qr_ge_lenconcr'] == 1
        assert gates['big_drop_avedia_r_ge_di100'] == 1
        _close(gates['mass_cap_qc_over_dtcld'], a['qc']/dt)
        _close(gates['number_cap_nc_over_dtcld'], a['nc']/dt)
        raw_n = p['ncrk1']*a['nc']*a['nr']*(a['rslopec3']*p['g3pmc']+a['rslope3_r']*p['g4pmr']/p['g1pmr'])
        raw_q = p['cmc']/a['den']*p['ncrk1']*a['nc']*a['nr']*a['rslopec3']*(a['rslopec3']*p['g6pmc']+a['rslope3_r']*p['g3pmc']*p['g4pmr']/p['g1pmr'])
        for name, raw, cap, cap_flag in [('nracw',raw_n,a['nc']/dt,'output_equals_number_cap'),
                                         ('pracw',raw_q,a['qc']/dt,'output_equals_mass_cap')]:
            output = r['producer_outputs'][name]
            _close(output, min(raw,cap))
            assert gates[cap_flag] == (output == cap)
        w, c, m = r['warm'], r['cold'], r['amounts']
        assert all(math.isfinite(x) for block in (w,c,m,r['pre'],r['post'],r['initial'],r['final']) for x in block.values())
        cold = float(r['supcol'] >= 0)
        rate = dt*(-w['nraut']-w['nccol']-w['nracw']-c['niacw']*cold-c['naacw']-c['naacw'])
        amount = -m['ninuc']-m['nfrzdtc']+m['pimlt_ni']
        full = rate+amount
        _close(full, r['nc_full_amount'])
        _close(-dt*w['nracw'], r['nc_selected_accretion_amount'])
        _close(max(r['pre']['nc']+full,0), r['post']['nc'])
        assert r['post']['nc'] == r['final']['nc']  # measured selected rows only
        rho = r['rho_d_frozen']
        assert math.isfinite(r['pressure_hpa']) and r['pressure_hpa'] > 0
        _close(rho, r['rho_forcing_moist_kg_m3']/(1+r['qv_initial_kgkg_dry']))
        volume_before = to_volume(r['pre']['nc'],rho)[0]
        volume_delta = to_volume(full,rho)[0]
        inverse = to_mass(max(volume_before+volume_delta,0),rho)[0]
        _close(inverse,r['post']['nc'])
    return dict(scope='arithmetic_replay_only', measured_layers=3,
                full_nc_budget_replayed=True, physical_number_basis_resolved=False,
                native_transport_measured=False, accepted_observation_cost=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', nargs='?', type=Path, default=DEFAULT)
    args = parser.parse_args()
    print(json.dumps(replay(json.loads(args.evidence.read_text())),indent=2))


if __name__ == '__main__':
    main()
