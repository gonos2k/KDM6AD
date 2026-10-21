"""Native dry-density and hydrometeor mapping tests for RTTOV cloud profiles."""
from __future__ import annotations

import numpy as np
import pytest
import torch

from kdm6.obs.native_cloud_profile import (
    NativeCloudState,
    native_to_rttov_cloud_profile,
)
from kdm6.obs.native_profile_builder import (
    FrozenNativeProfileGeometry,
    NativeObservationConfig,
    NativeObservationState,
    UpperReferenceProfile,
    native_to_rttov_profile,
)
from kdm6.obs.model_profile_builder import _DEFF_ICE_MIN, _DEFF_LIQ_MIN


DTYPE = torch.float64
LEVELS = 39
UPPER = 27
CONFIG = NativeObservationConfig(
    alpha=1.6083624362945557,
    t0=300.0,
    kappa=0.2857142984867096,
    p0=100000.0,
    g=9.8100004196167,
)


def native_state(*, requires_grad=False):
    fields = (
        torch.linspace(-22.0, 15.0, LEVELS, dtype=DTYPE),
        torch.linspace(0.001, 0.02, LEVELS, dtype=DTYPE),
        torch.logspace(np.log10(101000.0), np.log10(5100.0), LEVELS, dtype=DTYPE),
        torch.linspace(0.0, 400000.0, LEVELS + 1, dtype=DTYPE),
    )
    if requires_grad:
        fields = tuple(x.requires_grad_() for x in fields)
    return NativeObservationState(*fields)


def cloud_state(*, requires_grad=False, nc_zero=False, ni_zero=False):
    fields = (
        torch.full((LEVELS,), 1.0e-3, dtype=DTYPE),
        torch.full((LEVELS,), 2.0e-4, dtype=DTYPE),
        torch.full((LEVELS,), 1.0e-4, dtype=DTYPE),
        torch.full((LEVELS,), 1.0e8 if not nc_zero else 0.0, dtype=DTYPE),
        torch.full((LEVELS,), 5.0e5 if not ni_zero else 0.0, dtype=DTYPE),
    )
    if requires_grad:
        fields = tuple(x.requires_grad_() for x in fields)
    return NativeCloudState(*fields)


def geometry():
    return FrozenNativeProfileGeometry(
        fnm=torch.full((LEVELS,), 0.5, dtype=DTYPE),
        fnp=torch.full((LEVELS,), 0.5, dtype=DTYPE),
    )


def upper_reference():
    half = torch.cat((
        torch.logspace(-2.0, np.log10(40.0), UPPER, dtype=DTYPE),
        torch.logspace(np.log10(55.0), np.log10(1100.0), 70-UPPER, dtype=DTYPE),
    ))
    lay = torch.sqrt(half[:-1] * half[1:])
    temp = torch.linspace(205.0, 285.0, 69, dtype=DTYPE)
    q = torch.linspace(1.0, 9000.0, 69, dtype=DTYPE)
    return UpperReferenceProfile(lay, half, temp, q, UPPER)


def call(state, cloud, rho_d, *, upper=None, xland=2.0,
         ncmin_land=0.0, ncmin_sea=0.0):
    return native_to_rttov_cloud_profile(
        state, cloud, geometry(), CONFIG, upper,
        rho_d=rho_d, xland=xland, ncmin_land=ncmin_land, ncmin_sea=ncmin_sea)


def test_native_cloud_contents_use_live_dry_measure_and_species_mapping():
    state = native_state()
    clouds = cloud_state(requires_grad=True)
    rho_d = torch.linspace(0.9, 1.3, LEVELS, dtype=DTYPE, requires_grad=True)
    profile = call(state, clouds, rho_d)
    base = native_to_rttov_profile(state, geometry(), CONFIG)
    expected_clw = torch.flip(rho_d * clouds.qc * 1000.0, dims=(0,))
    expected_ciw = torch.flip(rho_d * (clouds.qi + clouds.qs) * 1000.0, dims=(0,))

    torch.testing.assert_close(profile.t_lay, base.t_lay, rtol=0, atol=0)
    torch.testing.assert_close(profile.q_lay, base.q_lay, rtol=0, atol=0)
    torch.testing.assert_close(profile.p_lay, base.p_lay, rtol=0, atol=0)
    torch.testing.assert_close(profile.p_half, base.p_half, rtol=0, atol=0)
    torch.testing.assert_close(profile.clw, expected_clw, rtol=0, atol=1e-13)
    torch.testing.assert_close(profile.ciw, expected_ciw, rtol=0, atol=1e-13)
    assert profile.clw.shape == profile.ciw.shape == (39,)
    assert profile.deff_liq.shape == profile.deff_ice.shape == (39,)
    assert profile.cfrac.shape == (39,) and not profile.cfrac.requires_grad
    assert bool(torch.isfinite(profile.deff_liq).all())
    assert bool(torch.isfinite(profile.deff_ice).all())
    assert bool(((profile.deff_liq >= _DEFF_LIQ_MIN) &
                 (profile.deff_liq <= 52.0)).all())
    assert bool(((profile.deff_ice >= _DEFF_ICE_MIN) &
                 (profile.deff_ice <= 120.0)).all())

    # Content is linear in native QC and in the explicit dry-air density. The
    # density leaf is independent: this operator does not synthesize it from P/T.
    k = 11
    rttov_k = LEVELS - 1 - k
    g_rho, g_qc = torch.autograd.grad(profile.clw[rttov_k], (rho_d, clouds.qc),
                                      retain_graph=True)
    torch.testing.assert_close(g_rho[k], 1000.0 * clouds.qc[k], rtol=0, atol=0)
    torch.testing.assert_close(g_qc[k], 1000.0 * rho_d[k], rtol=0, atol=0)


def test_native_number_moment_sensitivity_and_live_density_direction_fd():
    state = native_state(requires_grad=True)
    clouds = cloud_state(requires_grad=True)
    rho_d = torch.linspace(0.95, 1.2, LEVELS, dtype=DTYPE, requires_grad=True)
    profile = call(state, clouds, rho_d)
    k = 16
    rttov_k = LEVELS - 1 - k
    grad_nc = torch.autograd.grad(profile.deff_liq[rttov_k], clouds.nc,
                                  retain_graph=True)[0]
    grad_ni = torch.autograd.grad(profile.deff_ice[rttov_k], clouds.ni,
                                  retain_graph=True)[0]
    assert torch.isfinite(grad_nc[k]) and float(torch.abs(grad_nc[k])) > 0.0
    assert torch.isfinite(grad_ni[k]) and float(torch.abs(grad_ni[k])) > 0.0

    outputs = (profile.clw, profile.ciw, profile.deff_liq, profile.deff_ice)
    weights = tuple(torch.cos(torch.arange(x.numel(), dtype=DTYPE) * (i+1) * 0.17)
                    for i, x in enumerate(outputs))
    objective = sum((x*w).sum() for x, w in zip(outputs, weights))
    native_variables = (state.thm_pert, state.qv, state.p_center_Pa)
    cloud_variables = (clouds.qc, clouds.qi, clouds.qs, clouds.nc, clouds.ni)
    variables = (*native_variables, *cloud_variables, rho_d)
    grads = torch.autograd.grad(objective, variables)

    directions = (
        tuple(torch.sin(torch.arange(x.numel(), dtype=DTYPE) * (i+1) * 0.11)
              for i, x in enumerate(native_variables)),
        tuple(torch.sin(torch.arange(x.numel(), dtype=DTYPE) * (i+2) * 0.09) * x * 0.01
              for i, x in enumerate(cloud_variables)),
        0.01 * rho_d.detach(),
    )
    direction = (*directions[0], *directions[1], directions[2])
    lhs = sum((g*d).sum() for g, d in zip(grads, direction))
    eps = 2.0e-5

    def eval_obj(sign):
        state_t = NativeObservationState(
            native_variables[0].detach() + sign*eps*directions[0][0],
            native_variables[1].detach() + sign*eps*directions[0][1],
            native_variables[2].detach() + sign*eps*directions[0][2],
            state.phi_interfaces.detach(),
        )
        cloud_t = NativeCloudState(*(x.detach() + sign*eps*d
                                     for x, d in zip(cloud_variables, directions[1])))
        rho_t = rho_d.detach() + sign*eps*directions[2]
        out = call(state_t, cloud_t, rho_t)
        return sum((x*w).sum() for x, w in zip(
            (out.clw, out.ciw, out.deff_liq, out.deff_ice), weights))

    fd = (eval_obj(1.0) - eval_obj(-1.0)) / (2.0*eps)
    torch.testing.assert_close(lhs, fd, rtol=2.0e-5, atol=2.0e-6)


def test_cloud_upper_prefix_is_clear_with_valid_effective_diameter_floors():
    state, clouds = native_state(), cloud_state()
    rho_d = torch.ones(LEVELS, dtype=DTYPE)
    profile = call(state, clouds, rho_d, upper=upper_reference())
    assert profile.t_lay.shape == profile.q_lay.shape == (UPPER + LEVELS,)
    assert profile.p_lay.shape == (UPPER + LEVELS,)
    assert profile.p_half.shape == (UPPER + LEVELS + 1,)
    assert profile.clw.shape == profile.ciw.shape == profile.cfrac.shape == (UPPER+LEVELS,)
    assert torch.equal(profile.clw[:UPPER], torch.zeros(UPPER, dtype=DTYPE))
    assert torch.equal(profile.ciw[:UPPER], torch.zeros(UPPER, dtype=DTYPE))
    assert torch.equal(profile.cfrac[:UPPER], torch.zeros(UPPER, dtype=DTYPE))
    assert torch.equal(profile.deff_liq[:UPPER],
                       torch.full((UPPER,), _DEFF_LIQ_MIN, dtype=DTYPE))
    assert torch.equal(profile.deff_ice[:UPPER],
                       torch.full((UPPER,), _DEFF_ICE_MIN, dtype=DTYPE))
    # Native species keep the same 39-level order and live cloud values.
    native = call(state, clouds, rho_d)
    torch.testing.assert_close(profile.clw[-LEVELS:], native.clw, rtol=0, atol=0)
    torch.testing.assert_close(profile.ciw[-LEVELS:], native.ciw, rtol=0, atol=0)
    torch.testing.assert_close(profile.deff_liq[-LEVELS:], native.deff_liq, rtol=0, atol=0)
    torch.testing.assert_close(profile.deff_ice[-LEVELS:], native.deff_ice, rtol=0, atol=0)


@pytest.mark.parametrize("species", ["qc", "qi"])
def test_active_cloud_mass_requires_its_native_number_moment(species):
    state, clouds = native_state(), cloud_state(nc_zero=(species == "qc"),
                                                ni_zero=(species == "qi"))
    with pytest.raises(ValueError, match="active QC requires positive native NC|active QI requires positive native NI"):
        call(state, clouds, torch.ones(LEVELS, dtype=DTYPE))


@pytest.mark.parametrize("kwargs", [
    {"xland": 0.0}, {"xland": 3.0}, {"ncmin_land": -1.0},
])
def test_cloud_profile_refuses_invalid_discrete_inputs(kwargs):
    state, clouds = native_state(), cloud_state()
    rho_d = torch.ones(LEVELS, dtype=DTYPE)
    params = dict(xland=2.0, ncmin_land=0.0, ncmin_sea=0.0)
    params.update(kwargs)
    with pytest.raises((TypeError, ValueError)):
        native_to_rttov_cloud_profile(state, clouds, geometry(), CONFIG,
                                      rho_d=rho_d, **params)
