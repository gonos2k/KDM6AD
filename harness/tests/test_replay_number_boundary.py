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


def test_three_layer_warm_accretion_map_preserves_conditional_budget_and_branches():
    """Exercise a live oracle producer under a conditional dry/volume map.

    The dry arm uses rho_d in the paired DSD moments; the volume arm uses the
    same moments as concentrations with den=1 as a coordinate adapter.  This
    checks warm cloud-rain accretion only.  It is not a selected physical
    interpretation or a host/native transport result.
    """
    import torch

    oracle = Path(__file__).resolve().parents[2] / 'oracle'
    sys.path.insert(0, str(oracle))
    from kdm6 import fconst as fc
    from kdm6.cloud_dsd import default_cloud_dsd_params
    from kdm6.warm import accretion_torch, default_warm_accretion_params
    from moment_representation_probe import (
        _compare,
        _fresh_dsd,
        _independent_volume_formula,
    )

    def t(values):
        return torch.tensor([values], dtype=torch.float64)

    rho_d = t((0.55, 0.90, 1.30))
    qv = t((0.002, 0.011, 0.025))
    rho_m = rho_d * (1.0 + qv)
    qc_d, qr_d, nc_d = t((2.0e-4,)*3), t((5.0e-5,)*3), t((1.2e9,)*3)
    cloud, params = default_cloud_dsd_params(), default_warm_accretion_params()
    directions = (0.85, 1.25, 1.25)
    diameters = t(tuple(scale * params.di100 for scale in directions))
    g_ratio = (params.g4pmr / params.g1pmr) ** (1.0 / 3.0)

    # Set the same physical starting moments in both coordinate systems.
    C, R = rho_d * qc_d, rho_d * qr_d
    Nc = rho_d * nc_d
    Nr = R * (g_ratio**3) / (fc.PIDNR * diameters**3)
    dsd_vol = _fresh_dsd(
        C, Nc, R, Nr, torch.ones_like(rho_d), cloud
    )
    dsd_dry = _fresh_dsd(qc_d, Nc, qr_d, Nr, rho_d, cloud)
    assert tuple((dsd_vol['avedia_r'] >= params.di100).tolist()[0]) == (
        False, True, True
    )
    torch.testing.assert_close(dsd_dry['rslope_r'], dsd_vol['rslope_r'],
                               rtol=3e-15, atol=0.0)

    # Deliberately make the incoming rain gate differ by layer, then map its
    # threshold with density so both arms select the same cells.
    gate_limit_vol = R * t((0.5, 2.0, 0.5))
    gate_limit_dry = gate_limit_vol / rho_d
    dt = 20.0
    dry_rates = accretion_torch(
        qc_d, Nc, qr_d, Nr, rho_d, dsd_dry['avedia_r'],
        dsd_dry['rslopec3'], dsd_dry['rslope3_r'], gate_limit_dry,
        params=params, dtcld=dt,
    )
    vol_rates = accretion_torch(
        C, Nc, R, Nr, torch.ones_like(rho_d), dsd_vol['avedia_r'],
        dsd_vol['rslopec3'], dsd_vol['rslope3_r'], gate_limit_vol,
        params=params, dtcld=dt,
    )
    assert tuple((R >= gate_limit_vol).tolist()[0]) == (True, False, True)
    # Density conversion is applied to water-mixing tendency; the number rate
    # already has volume units because nc/nr passed to this producer are N/m3.
    assert _compare(rho_d * dry_rates[0], vol_rates[0]) < 2e-14
    assert _compare(dry_rates[1], vol_rates[1]) < 2e-14
    torch.testing.assert_close(rho_d * dry_rates[0], vol_rates[0],
                               rtol=2e-14, atol=1e-20)
    torch.testing.assert_close(dry_rates[1], vol_rates[1],
                               rtol=2e-14, atol=1e-8)

    # Apply the producer rates to a synthetic state, including its per-cell
    # inventory caps, and check the conditional local amount ledger in both
    # coordinates. This does not execute coordinator update code.
    mass_amount = dt * vol_rates[0]
    number_amount = dt * vol_rates[1]
    qc_d_after = qc_d - mass_amount / rho_d
    qr_d_after = qr_d + mass_amount / rho_d
    nc_d_after = nc_d - number_amount / rho_d
    C_after, R_after = rho_d * qc_d_after, rho_d * qr_d_after
    Nc_after = rho_d * nc_d_after
    torch.testing.assert_close(C_after, C - mass_amount, rtol=3e-14, atol=1e-18)
    torch.testing.assert_close(R_after, R + mass_amount, rtol=3e-14, atol=1e-18)
    torch.testing.assert_close(C_after + R_after, C + R,
                               rtol=3e-14, atol=1e-18)
    torch.testing.assert_close(Nc_after, Nc - number_amount,
                               rtol=3e-14, atol=1e-7)
    dz = t((100.0, 250.0, 500.0))
    torch.testing.assert_close(
        torch.sum((C_after + R_after) * dz),
        torch.sum((C + R) * dz),
        rtol=3e-14, atol=1e-15,
    )
    torch.testing.assert_close(
        torch.sum(Nc_after * dz),
        torch.sum(Nc * dz) - torch.sum(number_amount * dz),
        rtol=3e-14, atol=1e-6,
    )
    assert bool(torch.all(qc_d_after >= 0.0))
    assert bool(torch.all(nc_d_after >= 0.0))

    # The host's current moist DEN paired with dry mass-specific q is a third
    # map. It changes the DSD slope even when QV is modest and nonuniform.
    dsd_moist_den = _fresh_dsd(qc_d, Nc, qr_d, Nr, rho_m, cloud)
    assert not torch.allclose(dsd_moist_den['rslope_r'], dsd_dry['rslope_r'],
                              rtol=0.0, atol=0.0)

    # The conditional source-rate equation independently identifies the
    # selected small/big-drop branch and both limiter states.
    _mass, _number, meta = _independent_volume_formula(
        C, Nc, R, Nr, dsd_vol['avedia_r'], gate_limit_vol,
        dsd_vol['rslopec'], dsd_vol['rslope_r'],
        params=params, cloud=cloud, dt=dt,
    )
    assert tuple(meta['big_drop'].tolist()[0]) == (False, True, True)
    assert tuple(meta['active'].tolist()[0]) == (True, False, True)
    assert bool(torch.all(meta['mass_raw'] <= meta['mass_cap']))
    assert bool(torch.all(meta['number_raw'] <= meta['number_cap']))


def test_three_layer_live_accretion_exercises_inventory_cap_in_both_maps():
    """The rate cap is a synthetic stress branch, checked in both coordinates."""
    import torch

    oracle = Path(__file__).resolve().parents[2] / 'oracle'
    sys.path.insert(0, str(oracle))
    from kdm6 import fconst as fc
    from kdm6.cloud_dsd import default_cloud_dsd_params
    from kdm6.warm import accretion_torch, default_warm_accretion_params
    from moment_representation_probe import _fresh_dsd

    def t(values):
        return torch.tensor([values], dtype=torch.float64)

    rho_d = t((0.55, 0.90, 1.30))
    qc_d, qr_d, nc_d = t((2e-4,)*3), t((5e-5,)*3), t((1.2e9,)*3)
    C, R, Nc = rho_d*qc_d, rho_d*qr_d, rho_d*nc_d
    params, cloud = default_warm_accretion_params(), default_cloud_dsd_params()
    diameter = t((0.85*params.di100, 1.25*params.di100, 1.25*params.di100))
    ratio = (params.g4pmr/params.g1pmr)**(1.0/3.0)
    Nr = R*(ratio**3)/(fc.PIDNR*diameter**3)
    threshold_v = R*0.5
    vol_dsd = _fresh_dsd(C, Nc, R, Nr, torch.ones_like(rho_d), cloud)
    dry_dsd = _fresh_dsd(qc_d, Nc, qr_d, Nr, rho_d, cloud)

    # Build an intentionally long synthetic step from uncapped raw rates so
    # both per-cell inventory ceilings bind. This does not model a timestep.
    dt = max(float(torch.max(C).item()), float(torch.max(Nc).item())) * 1e8
    dry = accretion_torch(
        qc_d, Nc, qr_d, Nr, rho_d, dry_dsd['avedia_r'],
        dry_dsd['rslopec3'], dry_dsd['rslope3_r'], threshold_v/rho_d,
        params=params, dtcld=dt,
    )
    vol = accretion_torch(
        C, Nc, R, Nr, torch.ones_like(rho_d), vol_dsd['avedia_r'],
        vol_dsd['rslopec3'], vol_dsd['rslope3_r'], threshold_v,
        params=params, dtcld=dt,
    )
    torch.testing.assert_close(rho_d*dry[0], vol[0], rtol=3e-14, atol=0.0)
    torch.testing.assert_close(dry[1], vol[1], rtol=3e-14, atol=0.0)
    torch.testing.assert_close(vol[0], C/dt, rtol=3e-14, atol=0.0)
    torch.testing.assert_close(vol[1], Nc/dt, rtol=3e-14, atol=0.0)


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
