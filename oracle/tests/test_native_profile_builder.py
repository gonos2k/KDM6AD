"""Source-map and derivative tests for the native P8W -> RTTOV profile map."""
from __future__ import annotations

import numpy as np
import pytest
import torch

from kdm6.obs.native_profile_builder import (
    FrozenNativeProfileGeometry,
    NativeObservationConfig,
    NativeObservationState,
    UpperReferenceProfile,
    native_interface_pressure,
    native_to_rttov_profile,
)


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


def make_state(*, requires_grad=False):
    values = (
        torch.linspace(-22.0, 15.0, LEVELS, dtype=DTYPE),
        torch.linspace(0.001, 0.02, LEVELS, dtype=DTYPE),
        torch.logspace(np.log10(101000.0), np.log10(5100.0), LEVELS, dtype=DTYPE),
        torch.linspace(0.0, 400000.0, LEVELS + 1, dtype=DTYPE),
    )
    if requires_grad:
        values = tuple(x.requires_grad_() for x in values)
    return NativeObservationState(*values)


def make_geometry(*, requires_grad=False):
    fnm = torch.full((LEVELS,), 0.5, dtype=DTYPE)
    fnp = torch.full((LEVELS,), 0.5, dtype=DTYPE)
    if requires_grad:
        fnm.requires_grad_()
    return FrozenNativeProfileGeometry(fnm=fnm, fnp=fnp)


def make_upper(*, top_bracket=None, requires_grad=False):
    # U=27 gives a fixed half-level just below the native model top and a
    # reference half-level just above it, matching the saved upper-prefix map.
    lower = 40.0
    higher = 55.0
    if top_bracket is not None:
        lower, higher = top_bracket
    p_half = torch.cat((
        torch.logspace(-2.0, np.log10(lower), UPPER, dtype=DTYPE),
        torch.logspace(np.log10(higher), np.log10(1100.0), 70 - UPPER, dtype=DTYPE),
    ))
    p_lay = torch.sqrt(p_half[:-1] * p_half[1:])
    t = torch.linspace(205.0, 285.0, 69, dtype=DTYPE)
    q = torch.linspace(1.0, 9000.0, 69, dtype=DTYPE)
    if requires_grad:
        t.requires_grad_()
    return UpperReferenceProfile(p_lay, p_half, t, q, UPPER)


def source_p8w_scalar(p_center, phi, fnm, fnp, g):
    """Independent scalar transcription of moist_physics_prep_em P8W order."""
    p_center = np.asarray(p_center, dtype=np.float64)
    phi = np.asarray(phi, dtype=np.float64)
    fnm = np.asarray(fnm, dtype=np.float64)
    fnp = np.asarray(fnp, dtype=np.float64)
    zw = phi / g
    zm = 0.5 * (zw[:-1] + zw[1:])
    result = np.empty(p_center.size + 1, dtype=np.float64)
    wb = (zw[0] - zm[1]) / (zm[0] - zm[1])
    result[0] = wb * p_center[0] + (1.0 - wb) * p_center[1]
    for k in range(1, p_center.size):
        result[k] = fnm[k] * p_center[k] + fnp[k] * p_center[k - 1]
    wt = (zw[-1] - zm[-2]) / (zm[-1] - zm[-2])
    result[-1] = np.exp(wt * np.log(p_center[-1]) +
                        (1.0 - wt) * np.log(p_center[-2]))
    return result


def test_p8w_matches_independent_source_formula_and_has_39_40_layout():
    state = make_state()
    geometry = make_geometry()
    actual = native_interface_pressure(state.p_center_Pa, state.phi_interfaces,
                                       geometry, CONFIG)
    expected = source_p8w_scalar(state.p_center_Pa.numpy(), state.phi_interfaces.numpy(),
                                 geometry.fnm.numpy(), geometry.fnp.numpy(), CONFIG.g)
    np.testing.assert_allclose(actual.numpy(), expected, rtol=2e-14, atol=2e-10)
    assert actual.shape == (40,)
    assert bool(torch.all(actual[:-1] > actual[1:]))  # WRF bottom->top


def test_native_profile_preserves_all_mass_and_interface_levels_and_surface_pressure():
    state, geometry = make_state(), make_geometry()
    profile = native_to_rttov_profile(state, geometry, CONFIG)
    p8w = native_interface_pressure(state.p_center_Pa, state.phi_interfaces,
                                    geometry, CONFIG)
    assert profile.t_lay.shape == profile.q_lay.shape == profile.p_lay.shape == (39,)
    assert profile.p_half.shape == (40,)
    # RTTOV ordering is top-to-surface; the native 39/40 suffix is untouched
    # except for the Pa -> hPa unit conversion.
    torch.testing.assert_close(profile.p_lay, torch.flip(state.p_center_Pa / 100., (0,)),
                               rtol=0, atol=0)
    torch.testing.assert_close(profile.p_half, torch.flip(p8w / 100., (0,)),
                               rtol=0, atol=0)
    assert profile.p_half[-1] == pytest.approx(float(p8w[0] / 100.))
    assert profile.p_half[-1] > profile.p_lay[-1]
    assert profile.p_half[0] < profile.p_lay[0]

    expected_t = ((state.thm_pert + CONFIG.t0) /
                  (1. + CONFIG.alpha * state.qv) *
                  (state.p_center_Pa / CONFIG.p0).pow(CONFIG.kappa))
    torch.testing.assert_close(profile.t_lay, torch.flip(expected_t, (0,)), rtol=0, atol=0)


def test_native_and_partial_upper_profiles_keep_native_suffix_and_live_boundary():
    state = make_state(requires_grad=True)
    geometry = make_geometry()
    upper = make_upper()
    profile = native_to_rttov_profile(state, geometry, CONFIG, upper)
    p8w = native_interface_pressure(state.p_center_Pa, state.phi_interfaces,
                                    geometry, CONFIG)
    ptop_hpa = p8w[-1] / 100.0
    expected_partial = torch.sqrt(upper.p_half_hpa[UPPER - 1] * ptop_hpa)
    assert profile.t_lay.shape == profile.q_lay.shape == profile.p_lay.shape == (66,)
    assert profile.p_half.shape == (67,)
    torch.testing.assert_close(profile.p_lay[:UPPER-1], upper.p_lay_hpa[:UPPER-1], rtol=0, atol=0)
    torch.testing.assert_close(profile.p_half[:UPPER], upper.p_half_hpa[:UPPER], rtol=0, atol=0)
    torch.testing.assert_close(profile.p_lay[UPPER-1], expected_partial, rtol=0, atol=0)
    torch.testing.assert_close(profile.p_half[UPPER], ptop_hpa, rtol=0, atol=0)
    torch.testing.assert_close(profile.p_lay[-39:], torch.flip(state.p_center_Pa / 100., dims=(0,)),
                               rtol=0, atol=0)
    torch.testing.assert_close(profile.p_half[-40:], torch.flip(p8w / 100., dims=(0,)),
                               rtol=0, atol=0)

    # The partial full pressure is live: d sqrt(p_ref * ptop) / d ptop =
    # p_partial / (2*ptop). The fixed reference arrays remain nondifferentiable.
    gp = torch.autograd.grad(profile.p_lay[UPPER-1], state.p_center_Pa,
                             retain_graph=True)[0]
    gphi = torch.autograd.grad(profile.p_lay[UPPER-1], state.phi_interfaces)[0]
    gptop_p = torch.autograd.grad(ptop_hpa, state.p_center_Pa, retain_graph=True)[0]
    gptop_phi = torch.autograd.grad(ptop_hpa, state.phi_interfaces)[0]
    factor = expected_partial / (2.0 * ptop_hpa)
    torch.testing.assert_close(gp, factor * gptop_p, rtol=2e-13, atol=1e-13)
    torch.testing.assert_close(gphi, factor * gptop_phi, rtol=2e-13, atol=1e-13)

    # Log-pressure interpolation for the partial reference T/Q also follows the
    # moving boundary. Their native suffix remains the original 39-level data.
    assert profile.t_lay[UPPER-1].requires_grad
    assert profile.q_lay[UPPER-1].requires_grad
    assert not upper.t_k.requires_grad and not upper.q_ppmv.requires_grad
    torch.testing.assert_close(profile.t_lay[-39:], torch.flip(
        ((state.thm_pert + CONFIG.t0) / (1 + CONFIG.alpha*state.qv) *
         (state.p_center_Pa/CONFIG.p0).pow(CONFIG.kappa)), dims=(0,)), rtol=0, atol=0)


def test_native_pressure_exner_and_qv_pullbacks_are_distinct():
    state, geometry = make_state(requires_grad=True), make_geometry()
    profile = native_to_rttov_profile(state, geometry, CONFIG)
    # RTTOV top level 0 corresponds to WRF native level L-1. At fixed state
    # temperature and QV, dT/dP = kappa*T/P through Exner.
    grad_t_p = torch.autograd.grad(profile.t_lay[0], state.p_center_Pa,
                                   retain_graph=True)[0]
    expected = CONFIG.kappa * profile.t_lay[0] / state.p_center_Pa[-1]
    torch.testing.assert_close(grad_t_p[-1], expected, rtol=2e-13, atol=2e-13)
    assert torch.count_nonzero(grad_t_p[:-1]) == 0

    grad_q_p = torch.autograd.grad(profile.q_lay.sum(), state.p_center_Pa,
                                   retain_graph=True, allow_unused=True)[0]
    assert grad_q_p is None
    grad_p_phi = torch.autograd.grad(profile.p_lay.sum(), state.phi_interfaces,
                                     retain_graph=True, allow_unused=True)[0]
    assert grad_p_phi is None or torch.count_nonzero(grad_p_phi) == 0

    # Interior P8W levels use fixed FNM/FNP only; PH affects bottom/top
    # extrapolations, and a common full-geopotential shift is a gauge.
    dp8w = torch.autograd.grad(profile.p_half.sum(), state.phi_interfaces)[0]
    torch.testing.assert_close(dp8w.sum(), torch.zeros((), dtype=DTYPE), rtol=0, atol=2e-12)
    assert torch.count_nonzero(dp8w[3:-3]) == 0


def test_profile_combined_vjp_matches_directional_difference_with_upper_layer():
    state, geometry = make_state(requires_grad=True), make_geometry()
    upper = make_upper()
    profile = native_to_rttov_profile(state, geometry, CONFIG, upper)
    outputs = (profile.t_lay, profile.q_lay, profile.p_lay, profile.p_half)
    weights = tuple(torch.cos(torch.arange(x.numel(), dtype=DTYPE) * (i + 1) * 0.13)
                    for i, x in enumerate(outputs))
    objective = sum((x*w).sum() for x, w in zip(outputs, weights))
    state_tensors = (state.thm_pert, state.qv, state.p_center_Pa, state.phi_interfaces)
    grads = torch.autograd.grad(objective, state_tensors)
    direction = tuple(torch.sin(torch.arange(x.numel(), dtype=DTYPE) * (i + 2) * 0.17)
                      for i, x in enumerate(state_tensors))
    lhs = sum((g*d).sum() for g, d in zip(grads, direction))
    eps = 1e-5
    plus_state = NativeObservationState(*(x.detach() + eps*d
                                         for x, d in zip(state_tensors, direction)))
    minus_state = NativeObservationState(*(x.detach() - eps*d
                                          for x, d in zip(state_tensors, direction)))
    plus = native_to_rttov_profile(plus_state, geometry, CONFIG, upper)
    minus = native_to_rttov_profile(minus_state, geometry, CONFIG, upper)
    plus_obj = sum((x*w).sum() for x, w in zip(
        (plus.t_lay, plus.q_lay, plus.p_lay, plus.p_half), weights))
    minus_obj = sum((x*w).sum() for x, w in zip(
        (minus.t_lay, minus.q_lay, minus.p_lay, minus.p_half), weights))
    fd = (plus_obj - minus_obj) / (2*eps)
    torch.testing.assert_close(lhs, fd, rtol=2e-7, atol=2e-7)


def test_upper_count_boundary_and_reference_interpolation_knot_refuse():
    state, geometry = make_state(), make_geometry()
    base = make_upper()
    native_top = native_interface_pressure(state.p_center_Pa, state.phi_interfaces,
                                           geometry, CONFIG)[-1] / 100.0
    # Put the fixed count boundary above the live native top: count U would
    # change, so fail rather than silently changing layer cardinality.
    bad_half = base.p_half_hpa.clone()
    bad_half[UPPER - 1] = native_top * 1.01
    bad_half[UPPER] = native_top * 1.02
    bad_lay = torch.sqrt(bad_half[:-1] * bad_half[1:])
    bad = UpperReferenceProfile(bad_lay, bad_half, base.t_k, base.q_ppmv, UPPER)
    with pytest.raises(ValueError, match="fixed upper-count half-level bracket"):
        native_to_rttov_profile(state, geometry, CONFIG, bad)

    # A fixed reference layer center exactly at the moving partial pressure is
    # a kink in the piecewise log-pressure interpolation slope.
    knot_half = base.p_half_hpa.clone()
    knot_ref = torch.sqrt(knot_half[UPPER-1] * native_top)
    ref_lay = base.p_lay_hpa.clone()
    ref_lay[UPPER-1] = knot_ref
    knot = UpperReferenceProfile(ref_lay, knot_half, base.t_k, base.q_ppmv, UPPER)
    with pytest.raises(ValueError, match="reference center interpolation knot"):
        native_to_rttov_profile(state, geometry, CONFIG, knot)


def test_requires_fixed_geometry_and_fixed_upper_reference():
    state = make_state()
    bad_geometry = FrozenNativeProfileGeometry(
        fnm=torch.full((LEVELS,), 0.5, dtype=DTYPE, requires_grad=True),
        fnp=torch.full((LEVELS,), 0.5, dtype=DTYPE),
    )
    with pytest.raises(ValueError, match="fixed and must not require gradients"):
        native_to_rttov_profile(state, bad_geometry, CONFIG)
    with pytest.raises(ValueError, match="fixed reference data"):
        native_to_rttov_profile(state, make_geometry(), CONFIG, make_upper(requires_grad=True))
