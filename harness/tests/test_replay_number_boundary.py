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


def test_three_layer_dry_and_volume_number_q_br_s_moments_match():
    """Representation algebra only; this is not a KDM6 or WRF transport test."""
    rho_d = (0.5, 1.0, 2.0)
    qv = (0.02, 0.009, 0.001)
    rho_m = tuple(rho * (1.0 + vapor) for rho, vapor in zip(rho_d, qv))
    n_d = (0.015, 0.020, 0.008)
    q_d = (2.0e-4, 1.0e-4, 3.0e-5)
    b_d = (4.0e-7, 2.0e-7, 1.0e-7)
    dz = (100.0, 250.0, 500.0)

    # Independent defining map: volume moment = dry mass-specific moment × rho_d.
    n_v = tuple(rho*n for n, rho in zip(n_d, rho_d))
    q_v = tuple(rho*q for q, rho in zip(q_d, rho_d))
    b_v = tuple(rho*b for b, rho in zip(b_d, rho_d))

    # These moment ratios determine the same mean particle mass, graupel
    # volume, and bulk density under either representation.
    for i in range(3):
        assert q_v[i] / n_v[i] == pytest.approx(q_d[i] / n_d[i])
        assert b_v[i] / n_v[i] == pytest.approx(b_d[i] / n_d[i])
        assert q_v[i] / b_v[i] == pytest.approx(q_d[i] / b_d[i])

    # The KDM6 rain closure's concentration form and the transformed dry-mass
    # form give the same lambda^3 when the paired mass moment uses rho_d*q_d.
    pidnr = 4.0e-3
    for i in range(3):
        lambda3_v = pidnr * n_v[i] / q_v[i]
        lambda3_d = pidnr * n_d[i] / q_d[i]
        assert lambda3_v == pytest.approx(lambda3_d)
        # Current host DEN is rho_m, not the dry mass density paired with q_d.
        lambda3_with_current_den = pidnr * n_v[i] / (rho_m[i] * q_d[i])
        assert lambda3_with_current_den == pytest.approx(
            lambda3_d / (1.0 + qv[i]))
        assert lambda3_with_current_den != pytest.approx(lambda3_d)

    # A physical concentration threshold must transform with density. These
    # values intentionally make the raw per-kg and per-m^3 branch vectors differ.
    nrmin_v, nrmax_v = 1.0e-2, 1.8e-2
    volume_gate = tuple(n >= nrmin_v and n <= nrmax_v for n in n_v)
    dry_gate = tuple(n >= nrmin_v/rho and n <= nrmax_v/rho
                     for n, rho in zip(n_d, rho_d))
    raw_gate = tuple(n >= nrmin_v and n <= nrmax_v for n in n_d)
    assert volume_gate == dry_gate == (False, False, True)
    assert raw_gate != volume_gate

    # Prescribe the same two interface transfers F [#/m^2] in both forms.
    # This is a representation identity, not KDM6's fall-rate calculation.
    transfers = (0.3, 0.5)
    n_v_after = (
        n_v[0] - transfers[0]/dz[0],
        n_v[1] + transfers[0]/dz[1] - transfers[1]/dz[1],
        n_v[2] + transfers[1]/dz[2],
    )
    n_d_after = (
        n_d[0] - transfers[0]/(rho_d[0]*dz[0]),
        n_d[1] + transfers[0]/(rho_d[1]*dz[1])
        - transfers[1]/(rho_d[1]*dz[1]),
        n_d[2] + transfers[1]/(rho_d[2]*dz[2]),
    )
    assert n_v_after == pytest.approx(
        tuple(rho*n for rho, n in zip(rho_d, n_d_after)))
    volume_column = sum(n * z for n, z in zip(n_v, dz))
    dry_mass_column = sum(rho * n * z for n, rho, z in zip(n_d, rho_d, dz))
    assert volume_column == pytest.approx(dry_mass_column)
    volume_after = sum(n*z for n, z in zip(n_v_after, dz))
    dry_mass_after = sum(rho*n*z for n, rho, z in zip(n_d_after, rho_d, dz))
    assert volume_after == pytest.approx(dry_mass_after)
    assert volume_after == pytest.approx(volume_column)


@pytest.mark.parametrize('species', ['QNCCN', 'QNCLOUD', 'QNICE', 'QNRAIN'])
def test_synthetic_species_values_roundtrip_through_generic_density_map(species):
    """Probe representative values, not actual fields or ABI packing."""
    rho_d = (0.55, 0.90, 1.30)
    stored = {
        'QNCCN': (2.1e8, 1.8e8, 1.2e8),
        'QNCLOUD': (1.1e8, 8.0e7, 5.0e7),
        'QNICE': (4.0e6, 3.0e6, 2.0e6),
        'QNRAIN': (2.4e5, 1.7e5, 9.0e4),
    }[species]
    volume = tuple(to_volume(n, rho)[0] for n, rho in zip(stored, rho_d))
    returned = tuple(to_mass(n, rho)[0] for n, rho in zip(volume, rho_d))
    assert returned == pytest.approx(stored, rel=2e-15)
    assert tuple(n/rho for n, rho in zip(volume, rho_d)) == pytest.approx(stored)


def test_three_layer_number_q_br_s_density_jvp_and_vjp_duality():
    rho = (0.5, 1.0, 2.0)
    n = (0.015, 0.020, 0.008)
    q = (2.0e-4, 1.0e-4, 3.0e-5)
    b = (4.0e-7, 2.0e-7, 1.0e-7)
    drho = (0.02, -0.01, 0.03)
    dn = (0.001, 0.002, -0.001)
    dq = (1.0e-6, -2.0e-6, 1.0e-6)
    db = (1.0e-9, -2.0e-9, 1.0e-9)
    seed_n, seed_q, seed_b = (2.0, -3.0, 0.5), (1.5, 2.0, -1.0), (-2.0, 0.5, 4.0)

    dn_v = tuple(r*dx + x*dr for x, r, dx, dr in zip(n, rho, dn, drho))
    dq_v = tuple(r*dx + x*dr for x, r, dx, dr in zip(q, rho, dq, drho))
    db_v = tuple(r*dx + x*dr for x, r, dx, dr in zip(b, rho, db, drho))

    jvp = sum(a*x + c*y + e*z for a, c, e, x, y, z in
              zip(seed_n, seed_q, seed_b, dn_v, dq_v, db_v))
    vjp_dot = sum(
        (a*r)*dx + (c*r)*dy + (e*r)*dz + (a*x + c*y + e*z)*dr
        for a, c, e, x, y, z, r, dx, dy, dz, dr in
        zip(seed_n, seed_q, seed_b, n, q, b, rho, dn, dq, db, drho)
    )
    assert jvp == pytest.approx(vjp_dot, rel=0, abs=1e-14)

    # Independent central difference of the seeded physical-moment objective.
    h = 2.0**-12
    def objective(sign):
        total = 0.0
        for i in range(3):
            r = rho[i] + sign*h*drho[i]
            total += seed_n[i]*r*(n[i] + sign*h*dn[i])
            total += seed_q[i]*r*(q[i] + sign*h*dq[i])
            total += seed_b[i]*r*(b[i] + sign*h*db[i])
        return total

    fd = (objective(1.0) - objective(-1.0)) / (2.0*h)
    assert fd == pytest.approx(jvp, rel=2e-9, abs=1e-14)


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
