"""Synthetic fp64 prep -> native all-sky profile -> RTTOV-K cost composition.

This test validates graph connectivity and chain-rule plumbing with an analytic
RTTOV mock. It is not evidence for a native model, live RTTOV, or observation fit.
"""
from __future__ import annotations

import math
import struct

import numpy as np
import torch

from kdm6.native_prep import (
    FrozenPrepGeometry, NativePrepConfig, NativePrepState, native_prep,
)
from kdm6.obs.native_cloud_profile import NativeCloudState, native_to_rttov_cloud_profile
from kdm6.obs.native_profile_builder import (
    FrozenNativeProfileGeometry, NativeObservationConfig, NativeObservationState,
)
from kdm6.obs.obs_loss import compute_obs_loss
from kdm6.obs.rttov_input_builder import RttovInputConfig, pack_rttov_input
from kdm6.obs.rttov_obs_operator import RttovObsOp


F64 = torch.float64
CHANNELS = tuple(range(10, 17))


def _f32_hex(value):
    return struct.unpack(">f", bytes.fromhex(value))[0]


def _case(*, requires_grad):
    levels = 3
    mu_value = 50000.0
    ptop = 5000.0
    c3h = torch.tensor([0.85, 0.55, 0.25], dtype=F64)
    c4h = torch.zeros(levels, dtype=F64)
    c3f = torch.tensor([1.0, 0.7, 0.4, 0.1], dtype=F64)
    c4f = torch.zeros(levels + 1, dtype=F64)
    h = c3h * mu_value + ptop
    p_down = c3f[:-1] * mu_value + ptop
    p_up = c3f[1:] * mu_value + ptop
    target_volume = torch.tensor([1.2, 1.6, 2.5], dtype=F64)
    dphi = target_volume * h * torch.log(p_down / p_up)
    ph = torch.cat((torch.zeros(1, dtype=F64), torch.cumsum(dphi, dim=0)))
    geometry = FrozenPrepGeometry(
        phb=torch.zeros(levels + 1, dtype=F64), c3h=c3h, c4h=c4h,
        c3f=c3f, c4f=c4f)
    constants = dict(
        ptop=ptop, rd=287.0, p0=100000.0, t0=300.0,
        alpha=_f32_hex("3FCDDED2"), gamma=_f32_hex("3FB33333"),
        kappa=_f32_hex("3E924925"), g=_f32_hex("411CF5C3"))
    config = NativePrepConfig(**constants)
    thm = torch.tensor([280.0, 290.0, 300.0], dtype=F64)
    qv = torch.tensor([0.005, 0.007, 0.009], dtype=F64)
    mu = torch.tensor(mu_value, dtype=F64)
    if requires_grad:
        thm = thm.requires_grad_()
        qv = qv.requires_grad_()
        mu = mu.requires_grad_()
        ph = ph.requires_grad_()
    state = NativePrepState(thm, qv, mu, ph)
    cloud = NativeCloudState(
        qc=torch.tensor([1.2e-3, 0.0, 0.0], dtype=F64, requires_grad=requires_grad),
        qi=torch.tensor([0.0, 0.0, 8.0e-4], dtype=F64, requires_grad=requires_grad),
        qs=torch.tensor([0.0, 0.0, 3.0e-5], dtype=F64, requires_grad=requires_grad),
        nc=torch.tensor([6.0e7, 0.0, 0.0], dtype=F64, requires_grad=requires_grad),
        ni=torch.tensor([0.0, 0.0, 5.0e5], dtype=F64, requires_grad=requires_grad),
    )
    obs_geom = FrozenNativeProfileGeometry(
        fnm=torch.full((levels,), 0.5, dtype=F64),
        fnp=torch.full((levels,), 0.5, dtype=F64))
    obs_config = NativeObservationConfig(
        alpha=constants["alpha"], t0=constants["t0"],
        kappa=constants["kappa"], p0=constants["p0"], g=constants["g"])
    return state, geometry, config, cloud, obs_geom, obs_config


def _profile(state, prep_geometry, prep_config, cloud, obs_geometry, obs_config):
    prepared = native_prep(state, prep_geometry, prep_config)
    native = NativeObservationState(
        thm_pert=state.thm_pert,
        qv=state.qv,
        p_center_Pa=prepared.p,
        phi_interfaces=state.ph + prep_geometry.phb,
    )
    profile = native_to_rttov_cloud_profile(
        native, cloud, obs_geometry, obs_config,
        rho_d=prepared.rho,
        xland=torch.tensor([2.0], dtype=F64),
        ncmin_land=1.0e8,
        ncmin_sea=1.0e7,
    )
    return prepared, profile


def _mock_run_k(rin):
    """Affine BT in all eight differentiable profile fields with exact K blocks."""
    profile_fields = (
        "T", "Q", "P", "P_HALF", "HYDRO6", "HYDRO7",
        "HYDRO_DEFF6", "HYDRO_DEFF7",
    )
    channel = np.arange(1, len(CHANNELS) + 1, dtype=np.float64)
    scales = {
        "T": 2.0e-3, "Q": 1.0e-4, "P": 2.0e-4, "P_HALF": 1.0e-4,
        "HYDRO6": 0.15, "HYDRO7": 0.11,
        "HYDRO_DEFF6": 6.0e-3, "HYDRO_DEFF7": 4.0e-3,
    }
    k = {}
    bt = np.zeros((rin.nprofiles, len(CHANNELS)), dtype=np.float64)
    for name in profile_fields:
        values = np.asarray(rin.profile[name], dtype=np.float64)
        kt = np.broadcast_to(
            scales[name] * channel.reshape(1, -1, 1),
            (rin.nprofiles, len(CHANNELS), values.shape[-1])).copy()
        k[name] = kt
        bt += np.einsum("pcl,pl->pc", kt, values)
    return bt, k, np.zeros((rin.nprofiles, len(CHANNELS)), dtype=np.int32)


def _cost(state, prep_geometry, prep_config, cloud, obs_geometry, obs_config, obs_bt):
    _, profile = _profile(state, prep_geometry, prep_config, cloud, obs_geometry, obs_config)
    rttov_config = RttovInputConfig(
        coef_id="analytic-native-cloud-test", channels=CHANNELS, pressure_gradients=True)
    bt, quality = RttovObsOp.apply(
        _mock_run_k, rttov_config,
        profile.t_lay, profile.q_lay, profile.p_lay, profile.p_half,
        profile.clw, profile.ciw, profile.deff_liq, profile.deff_ice, profile.cfrac)
    mask = (quality == 0).to(F64)
    return compute_obs_loss(
        bt, {"bt": obs_bt}, mask, sigma=5.0, delta=1.0), bt, profile


def test_native_prep_cloud_rttov_pressure_composition_matches_mixed_fd():
    state, prep_geometry, prep_config, cloud, obs_geometry, obs_config = _case(requires_grad=True)
    _, base_profile = _profile(state, prep_geometry, prep_config, cloud,
                               obs_geometry, obs_config)
    packed = pack_rttov_input(
        base_profile,
        RttovInputConfig(coef_id="analytic-native-cloud-test", channels=CHANNELS,
                         pressure_gradients=True))
    base_bt, _, _ = _mock_run_k(packed)
    obs_bt = torch.from_numpy(base_bt + 0.2)
    cost, bt, profile = _cost(state, prep_geometry, prep_config, cloud,
                              obs_geometry, obs_config, obs_bt)

    controls = (state.thm_pert, state.qv, state.mu_total, state.ph,
                cloud.qc, cloud.qi, cloud.qs, cloud.nc, cloud.ni)
    gradients = torch.autograd.grad(cost, controls)
    assert torch.isfinite(bt).all() and torch.isfinite(cost)
    for value, grad in zip(controls, gradients):
        assert grad is not None
        assert torch.isfinite(grad).all()
    # Every K-fed cloud quantity and the prep-derived density/pressure path is live.
    for name, grad in zip(("theta_m", "qv", "mu", "phi", "qc", "qi", "qs", "nc", "ni"), gradients):
        assert float(grad.abs().sum()) > 0.0, f"{name} path was severed or clamped flat"
    assert profile.p_lay.requires_grad and profile.p_half.requires_grad
    assert all(value.requires_grad for value in
               (profile.clw, profile.ciw, profile.deff_liq, profile.deff_ice))
    assert not profile.cfrac.requires_grad

    directions = (
        torch.tensor([0.2, -0.1, 0.3], dtype=F64),
        torch.tensor([1.0e-5, -2.0e-5, 1.5e-5], dtype=F64),
        torch.tensor(2.0, dtype=F64),
        torch.tensor([0.5, -0.4, 0.7, -0.3], dtype=F64),
    )
    mixed_grad = sum((grad * direction).sum()
                     for grad, direction in zip(gradients[:4], directions))

    def trial(scale):
        trial_state = NativePrepState(*(
            value.detach() + scale * direction
            for value, direction in zip(state, directions)))
        trial_cloud = NativeCloudState(*(getattr(cloud, name).detach()
                                          for name in ("qc", "qi", "qs", "nc", "ni")))
        value, _, _ = _cost(trial_state, prep_geometry, prep_config, trial_cloud,
                            obs_geometry, obs_config, obs_bt)
        return float(value)

    epsilon = 1.0e-2
    centered_fd = (trial(epsilon) - trial(-epsilon)) / (2.0 * epsilon)
    assert math.isclose(float(mixed_grad), centered_fd, rel_tol=1.0e-5, abs_tol=2.0e-8)
