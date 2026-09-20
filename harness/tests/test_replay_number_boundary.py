"""Representation witnesses; synthetic transport is not a host transport run."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from replay_number_boundary import paired_transfer, to_mass, to_volume


def test_variable_density_tangent_roundtrip_and_dual_identity():
    n, rho, dn, drho = 8.0, 0.5, 3.0, 0.125
    value, tangent = to_volume(n, rho, dn, drho)
    assert (value, tangent) == (4.0, 2.5)
    assert to_volume(n, rho, dn, 0.0) == (4.0, 1.5)
    assert to_mass(value, rho, tangent, drho) == (n, dn)
    h = 2**-12
    fd = ((rho+h*drho)*(n+h*dn)-(rho-h*drho)*(n-h*dn))/(2*h)
    assert fd == tangent
    seed = 2.0
    assert seed*tangent == (rho*seed)*dn + (n*seed)*drho
    assert rho*dn != tangent  # omitted density term is observable


def test_threshold_and_applied_cap_convert_together():
    n, floor, rho, rate, dt = .02, .01, .25, .01, 2.0
    volume, _ = to_volume(n, rho)
    volume_floor, _ = to_volume(floor, rho)
    assert n > floor and volume > volume_floor
    assert not volume > floor  # the unconverted threshold changes the branch
    amount = min(dt*rate, n-floor)
    volume_amount = min(dt*rho*rate, volume-volume_floor)
    assert volume_amount == rho*amount
    assert to_mass(volume-volume_amount, rho)[0] == n-amount


def test_nonzero_prescribed_transfer_same_inventory_in_two_representations():
    number, density, thickness, amount = [8., 2.], [.5, 2.], [2., 4.], 4.
    direct, roundtrip = paired_transfer(number, density, thickness, amount)
    assert direct == roundtrip == [4., 2.5]
    before = sum(n*r*z for n, r, z in zip(number, density, thickness))
    after = sum(n*r*z for n, r, z in zip(direct, density, thickness))
    assert before == after == 24.


@pytest.mark.parametrize('density', [0.0, -1.0, math.inf, math.nan])
def test_invalid_density_rejected(density):
    for fn in (to_mass, to_volume):
        with pytest.raises(ValueError):
            fn(1., density)


def load_evidence():
    import json
    from replay_number_boundary import DEFAULT
    return json.loads(DEFAULT.read_text())


def test_measured_selected_budget():
    from replay_number_boundary import replay
    result = replay(load_evidence())
    assert result['full_nc_budget_replayed']
    assert not result['physical_number_basis_resolved']
    assert not result['native_transport_measured']
    assert not result['accepted_observation_cost']


@pytest.mark.parametrize('fault', ['missing_row','self_collection','amount','post',
                                  'density','producer','gate','approval'])
def test_corrupted_measured_evidence_rejected(fault):
    from replay_number_boundary import replay
    data = load_evidence()
    row = data['rows'][0]
    if fault == 'missing_row':
        data['rows'].pop()
    elif fault == 'self_collection':
        row['warm']['nccol'] = 0.0
    elif fault == 'amount':
        row['amounts']['ninuc'] = 100.
    elif fault == 'post':
        row['post']['nc'] += 1.
    elif fault == 'density':
        row['rho_d_frozen'] = math.nan
    elif fault == 'producer':
        row['producer_outputs']['nracw'] *= 1.01
    elif fault == 'gate':
        row['producer_gates']['big_drop_avedia_r_ge_di100'] = 0
    elif fault == 'approval':
        data['physical_number_basis_resolved'] = True
    with pytest.raises((AssertionError, ValueError)):
        replay(data)


def test_optimized_python_rejected():
    import subprocess
    from replay_number_boundary import __file__ as script
    result = subprocess.run([sys.executable, '-O', script], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'assertions must remain enabled' in result.stderr


def test_warm_layer_still_requires_twice_applied_naacw():
    from replay_number_boundary import replay
    data = load_evidence()
    row = data['rows'][2]
    assert row['supcol'] < 0 and row['cold']['naacw'] > 0
    row['cold']['naacw'] = 0.
    with pytest.raises(AssertionError):
        replay(data)
