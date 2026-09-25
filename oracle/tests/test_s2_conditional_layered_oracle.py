"""Conditional three-layer oracle witness for the S2 number-basis map."""
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from moment_representation_probe import (  # noqa: E402
    _compare,
    _fresh_dsd,
    _independent_volume_formula,
)
from kdm6 import fconst as fc  # noqa: E402
from kdm6.cloud_dsd import default_cloud_dsd_params  # noqa: E402
from kdm6.warm import accretion_torch, default_warm_accretion_params  # noqa: E402


def test_three_layer_warm_accretion_map_preserves_conditional_budget_and_branches():
    """Exercise a live oracle producer under a conditional dry/volume map.

    The dry arm uses rho_d in the paired DSD moments; the volume arm uses the
    same moments as concentrations with den=1 as a coordinate adapter.  This
    checks warm cloud-rain accretion only.  It is not a selected physical
    interpretation or a host/native transport result.
    """
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
