"""Native all-sky cloud profile extension for the first-order RTTOV path.

This narrow stage maps native QC/QI/QS and NC/NI to the existing KDM6AD
cloud/DSD bridge using an explicit live dry-air density from native ``AL+ALB``.
It keeps the WRF 39-level/40-interface suffix from ``native_profile_builder``
unchanged. Rain, graupel and raw CCN remain outside the existing AMI VIS/IR
HYDRO6/7 mapping and are deliberately not represented here.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real

import torch

from ..state import Forcing, State
from .model_profile_builder import (
    RttovProfileTensors,
    _DEFF_ICE_MIN,
    _DEFF_LIQ_MIN,
    _cloud_profile_tensors,
)
from .native_profile_builder import (
    FrozenNativeProfileGeometry,
    NativeObservationConfig,
    NativeObservationState,
    UpperReferenceProfile,
    native_to_rttov_profile,
)


@dataclass(frozen=True)
class NativeCloudState:
    """Native dry-air-basis cloud water and number moments, bottom-to-top."""

    qc: torch.Tensor
    qi: torch.Tensor
    qs: torch.Tensor
    nc: torch.Tensor
    ni: torch.Tensor


def _fixed_nonnegative(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a fixed real scalar")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return result


def _xland_tensor(xland, *, device: torch.device) -> torch.Tensor:
    if isinstance(xland, bool):
        raise TypeError("xland must be WRF land/water value 1 or 2")
    if isinstance(xland, torch.Tensor):
        if xland.dtype != torch.float64 or xland.device != device:
            raise ValueError("xland tensor must be float64 on the native state device")
        if xland.numel() != 1 or xland.requires_grad:
            raise ValueError("xland must be one fixed single-column value")
        value = float(xland.item())
    elif isinstance(xland, Real):
        value = float(xland)
    else:
        raise TypeError("xland must be a fixed scalar or one-element float64 tensor")
    if not math.isfinite(value) or value not in (1.0, 2.0):
        raise ValueError("xland must equal WRF land/water code 1 or 2")
    return torch.tensor([value], dtype=torch.float64, device=device)


def _validate_cloud_state(cloud: NativeCloudState, native: NativeObservationState) -> int:
    if not isinstance(cloud, NativeCloudState):
        raise TypeError("cloud_state must be NativeCloudState")
    levels = native.thm_pert.numel()
    device = native.thm_pert.device
    for name in ("qc", "qi", "qs", "nc", "ni"):
        value = getattr(cloud, name)
        if not isinstance(value, torch.Tensor):
            raise TypeError(f"cloud_state.{name} must be a torch.Tensor")
        if value.dtype != torch.float64 or value.layout != torch.strided:
            raise TypeError(f"cloud_state.{name} must be a strided torch.float64 tensor")
        if value.device != device or value.shape != (levels,):
            raise ValueError(f"cloud_state.{name} must match the native {levels}-level column")
        if not bool(torch.isfinite(value).all().item()):
            raise ValueError(f"cloud_state.{name} must be finite")
        if not bool((value >= 0.0).all().item()):
            raise ValueError(f"cloud_state.{name} must be nonnegative")
    if bool(((cloud.qc > 0.0) & (cloud.nc <= 0.0)).any().item()):
        raise ValueError("active QC requires positive native NC")
    if bool(((cloud.qi > 0.0) & (cloud.ni <= 0.0)).any().item()):
        raise ValueError("active QI requires positive native NI")
    return levels


def native_to_rttov_cloud_profile(
    native_state: NativeObservationState,
    cloud_state: NativeCloudState,
    geometry: FrozenNativeProfileGeometry,
    config: NativeObservationConfig,
    upper: UpperReferenceProfile | None = None,
    *,
    rho_d: torch.Tensor,
    xland,
    ncmin_land: float,
    ncmin_sea: float,
) -> RttovProfileTensors:
    """Build a live native all-sky RTTOV profile with dry-air number transport.

    Native ``NC/NI`` and water species remain on their legacy per-kg-dry-air
    basis. The required live ``rho_d`` is the native ``1/(AL+ALB)`` density
    control; it is not reconstructed from EOS pressure/temperature. The bridge
    uses this same dry-air measure for number-to-volume conversion and content.
    The existing optical bridge's moist-air forcing coordinate is supplied as
    ``rho_d*(1+qv)``; native host ``DEN=1/(AL+ALB)`` remains the explicit dry
    mass measure. This does not relabel the operational host/kernel forcing.
    Thermodynamic
    and pressure profiles are built by ``native_to_rttov_profile``; native
    cloud outputs are flipped into RTTOV order and an optional upper prefix is
    padded clear with valid Deff floors.

    Only QC, QI+QS, NC and NI are mapped into the existing AMI VIS/IR cloud
    bridge (HYDRO6/7 and their Deff). Rain/rain number and graupel are not
    silently relabelled as cloud species; their optical mappings remain outside
    this operator.
    """
    levels = _validate_cloud_state(cloud_state, native_state)
    ncmin_land = _fixed_nonnegative("ncmin_land", ncmin_land)
    ncmin_sea = _fixed_nonnegative("ncmin_sea", ncmin_sea)
    xland_value = _xland_tensor(xland, device=native_state.thm_pert.device)
    if not isinstance(rho_d, torch.Tensor):
        raise TypeError("rho_d must be an explicit native dry-air density tensor")
    if rho_d.dtype != torch.float64 or rho_d.layout != torch.strided:
        raise TypeError("rho_d must be a strided torch.float64 tensor")
    if rho_d.device != native_state.thm_pert.device or rho_d.shape != (levels,):
        raise ValueError(f"rho_d must match the native {levels}-level column")
    if not bool(torch.isfinite(rho_d).all().item()) or not bool((rho_d > 0.0).all().item()):
        raise ValueError("rho_d must be finite and positive")

    base = native_to_rttov_profile(native_state, geometry, config, upper)
    alpha, t0, kappa, p0, g = (config.alpha, config.t0, config.kappa,
                               config.p0, config.g)
    pii = (native_state.p_center_Pa / p0).pow(kappa)
    theta_dry = (native_state.thm_pert + t0) / (1.0 + alpha * native_state.qv)
    rho_moist = rho_d * (1.0 + native_state.qv)
    delz = (native_state.phi_interfaces[1:] - native_state.phi_interfaces[:-1]) / g
    for name, value in (("theta_dry", theta_dry), ("pii", pii),
                        ("rho_moist", rho_moist),
                        ("delz", delz)):
        if not bool(torch.isfinite(value).all().item()):
            raise ValueError(f"native {name} must be finite")
    if not bool((rho_moist > 0.0).all().item()):
        raise ValueError("native moist density must be positive")
    if not bool((delz > 0.0).all().item()):
        raise ValueError("native layer thickness must be positive")

    zeros = torch.zeros_like(native_state.thm_pert)
    leaves = State(
        th=theta_dry,
        qv=native_state.qv,
        qc=cloud_state.qc,
        qr=zeros,
        qi=cloud_state.qi,
        qs=cloud_state.qs,
        qg=zeros,
        nccn=zeros,
        nc=cloud_state.nc,
        ni=cloud_state.ni,
        nr=zeros,
        bg=zeros,
    )
    forcing = Forcing(rho=rho_moist, pii=pii, p=native_state.p_center_Pa, delz=delz)
    # This is an explicitly live entry density, not the bridge's frozen-background
    # measure. It flows through both content and dry-number-to-volume conversions.
    clw, ciw, deff_liq, deff_ice, cfrac = _cloud_profile_tensors(
        leaves, forcing, native_state.p_center_Pa, None, xland_value,
        ncmin_land, ncmin_sea, rho_d, dry_number=True, live_density=True)
    clw = torch.flip(clw, dims=(0,))
    ciw = torch.flip(ciw, dims=(0,))  # QC -> liquid; QI+QS -> ice.
    deff_liq = torch.flip(deff_liq, dims=(0,))
    deff_ice = torch.flip(deff_ice, dims=(0,))
    cfrac = torch.flip(cfrac, dims=(0,))

    n_upper = base.t_lay.numel() - levels
    if n_upper < 0:
        raise ValueError("upper profile cannot remove native cloud layers")
    if n_upper:
        clear = torch.zeros(n_upper, dtype=clw.dtype, device=clw.device)
        liq_floor = torch.full_like(clear, _DEFF_LIQ_MIN)
        ice_floor = torch.full_like(clear, _DEFF_ICE_MIN)
        clw = torch.cat((clear, clw))
        ciw = torch.cat((clear, ciw))
        deff_liq = torch.cat((liq_floor, deff_liq))
        deff_ice = torch.cat((ice_floor, deff_ice))
        cfrac = torch.cat((clear, cfrac))

    if any(value.shape != base.t_lay.shape for value in
           (clw, ciw, deff_liq, deff_ice, cfrac)):
        raise ValueError("native cloud fields must ride the final RTTOV layer grid")
    for name, value in (("HYDRO6", clw), ("HYDRO7", ciw),
                        ("HYDRO_DEFF6", deff_liq), ("HYDRO_DEFF7", deff_ice),
                        ("CFRAC", cfrac)):
        if not bool(torch.isfinite(value).all().item()):
            raise ValueError(f"native {name} must be finite")
    return RttovProfileTensors(
        t_lay=base.t_lay, q_lay=base.q_lay, p_lay=base.p_lay, p_half=base.p_half,
        clw=clw, ciw=ciw, deff_liq=deff_liq, deff_ice=deff_ice, cfrac=cfrac)
