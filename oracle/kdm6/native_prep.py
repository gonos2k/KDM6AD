"""Continuous fp64 lift of the selected native nonhydrostatic prep map.

The operator is restricted to ``non_hydrostatic=True``,
``hypsometric_opt=2``, and ``use_theta_m=1``. It maps one native column's
thermodynamic state and interfaces to ``th,rho,pii,p,delz``. Here ``p`` is
full pressure, matching solve_em's ``p_phy=p+pb`` passed to microphysics;
``p_d`` and ``p_u`` below are only internal hybrid mass-coordinate pressures.

The geometry and scalar configuration are fixed inputs, not AD controls. The
value-only preflight checks inspect domain values without altering tensors; the
forward map and its analytic JVP/VJP preserve the live Torch graph.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import NamedTuple

import torch


class NativePrepState(NamedTuple):
    """Live 1-D native column: theta_m perturbation, dry QV, MU total, PH."""

    thm_pert: torch.Tensor
    qv: torch.Tensor
    mu_total: torch.Tensor
    ph: torch.Tensor


@dataclass(frozen=True)
class FrozenPrepGeometry:
    """Fixed host geometry (all tensors are fp64 and must have grad disabled)."""

    phb: torch.Tensor
    c3h: torch.Tensor
    c4h: torch.Tensor
    c3f: torch.Tensor
    c4f: torch.Tensor


@dataclass(frozen=True)
class NativePrepConfig:
    """Fixed host constants promoted from the captured binary32 values."""

    ptop: float
    rd: float
    p0: float
    t0: float
    alpha: float
    gamma: float
    kappa: float
    g: float


class NativePrepResult(NamedTuple):
    """Native prep outputs; ``p`` is full pressure, not perturbation pressure."""

    th: torch.Tensor
    rho: torch.Tensor
    pii: torch.Tensor
    p: torch.Tensor
    delz: torch.Tensor


def _fixed_scalar(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a fixed real scalar")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _config_values(config: NativePrepConfig) -> tuple[float, ...]:
    if not isinstance(config, NativePrepConfig):
        raise TypeError("config must be NativePrepConfig")
    values = tuple(_fixed_scalar(name, getattr(config, name)) for name in (
        "ptop", "rd", "p0", "t0", "alpha", "gamma", "kappa", "g"
    ))
    ptop, rd, p0, t0, alpha, gamma, kappa, g = values
    if ptop < 0.0:
        raise ValueError("ptop must be nonnegative")
    if any(value <= 0.0 for value in (rd, p0, t0, alpha, gamma, kappa, g)):
        raise ValueError("rd, p0, t0, alpha, gamma, kappa, and g must be positive")
    # gamma and kappa stay independent captured constants. Do not impose an
    # exact reciprocal or thermodynamic identity between them.
    return values


def _tensor(name: str, value: torch.Tensor) -> None:
    if not isinstance(value, torch.Tensor):
        raise TypeError(f"{name} must be a torch.Tensor")
    if value.dtype != torch.float64:
        raise TypeError(f"{name} must have dtype torch.float64")
    if value.layout != torch.strided:
        raise TypeError(f"{name} must be a strided tensor")


def _finite(name: str, value: torch.Tensor) -> None:
    # Explicit value-only validation; the boolean is not used in any output or
    # derivative computation and no input tensor is detached or modified.
    if not bool(torch.isfinite(value).all().item()):
        raise ValueError(f"{name} must be finite")


def _validate_inputs(
    state: NativePrepState,
    geometry: FrozenPrepGeometry,
    config: NativePrepConfig,
    tangent: NativePrepState | None = None,
) -> tuple[float, ...]:
    scalars = _config_values(config)
    if not isinstance(state, NativePrepState):
        raise TypeError("state must be NativePrepState")
    if not isinstance(geometry, FrozenPrepGeometry):
        raise TypeError("geometry must be FrozenPrepGeometry")

    for name, value in zip(("thm_pert", "qv", "mu_total", "ph"), state):
        _tensor(f"state.{name}", value)
    if state.thm_pert.ndim != 1 or state.qv.shape != state.thm_pert.shape:
        raise ValueError("state thm_pert and qv must be matching one-dimensional level vectors")
    levels = state.thm_pert.numel()
    if levels <= 0:
        raise ValueError("native column must contain at least one mass level")
    if state.mu_total.ndim != 0:
        raise ValueError("state.mu_total must be a scalar 0-D tensor")
    if state.ph.shape != (levels + 1,):
        raise ValueError("state.ph must have one more element than the mass-level fields")
    state_device = state.thm_pert.device
    for name, value in zip(("qv", "mu_total", "ph"), (state.qv, state.mu_total, state.ph)):
        if value.device != state_device:
            raise ValueError(f"state.{name} must be on the same device as state.thm_pert")

    for name in ("phb", "c3h", "c4h", "c3f", "c4f"):
        value = getattr(geometry, name)
        _tensor(f"geometry.{name}", value)
        if value.device != state_device:
            raise ValueError(f"geometry.{name} must be on the state device")
        if value.requires_grad:
            raise ValueError(f"geometry.{name} is fixed and must not require gradients")
    if geometry.phb.shape != (levels + 1,):
        raise ValueError("geometry.phb interface vector must have one more element than mass-level fields")
    if geometry.c3h.shape != (levels,) or geometry.c4h.shape != (levels,):
        raise ValueError("geometry.c3h/c4h must match the mass-level fields")
    if geometry.c3f.shape != (levels + 1,) or geometry.c4f.shape != (levels + 1,):
        raise ValueError("geometry.c3f/c4f must match the interface fields")

    if tangent is not None:
        if not isinstance(tangent, NativePrepState):
            raise TypeError("tangent must be NativePrepState")
        refs = state
        for name, value, ref in zip(("thm_pert", "qv", "mu_total", "ph"), tangent, refs):
            _tensor(f"tangent.{name}", value)
            if value.shape != ref.shape or value.dtype != ref.dtype or value.device != ref.device:
                raise ValueError(f"tangent.{name} metadata must match corresponding state field")
            _finite(f"tangent.{name}", value)

    # Domain checks are a separate preflight value gate; negative tangents are
    # fine, while the primal state must describe a physical positive layer.
    for name, value in zip(("thm_pert", "qv", "mu_total", "ph"), state):
        _finite(f"state.{name}", value)
    for name in ("phb", "c3h", "c4h", "c3f", "c4f"):
        value = getattr(geometry, name)
        _finite(f"geometry.{name}", value)
    t_moist = state.thm_pert + scalars[3]
    if not bool((t_moist > 0.0).all().item()):
        raise ValueError("T_2 + T0 must be positive")
    if not bool((state.qv >= 0.0).all().item()):
        raise ValueError("QV must be nonnegative")
    if not bool((state.mu_total > 0.0).item()):
        raise ValueError("MU total must be positive")

    # Check exactly the denominators/log domain used by hypsometric_opt=2.
    dphi = (state.ph[1:] + geometry.phb[1:]) - (state.ph[:-1] + geometry.phb[:-1])
    h = geometry.c3h * state.mu_total + geometry.c4h + scalars[0]
    p_d = geometry.c3f[:-1] * state.mu_total + geometry.c4f[:-1] + scalars[0]
    p_u = geometry.c3f[1:] * state.mu_total + geometry.c4f[1:] + scalars[0]
    for name, value in (("layer geopotential thickness", dphi), ("phm", h),
                        ("p_d", p_d), ("p_u", p_u)):
        _finite(name, value)
    if not bool((dphi > 0.0).all().item()):
        raise ValueError("interface geopotential must increase with the native level order")
    if not bool((h > 0.0).all().item()):
        raise ValueError("hybrid mass phm must be positive")
    if not bool((p_d > p_u).all().item()) or not bool((p_u > 0.0).all().item()):
        raise ValueError("hybrid auxiliary pressure requires p_d > p_u > 0")
    ell = torch.log(p_d / p_u)
    if not bool((ell > 0.0).all().item()):
        raise ValueError("hybrid log pressure depth must be positive")
    volume = dphi / h / ell
    if not bool(torch.isfinite(volume).all().item()) or not bool((volume > 0.0).all().item()):
        raise ValueError("specific volume must be finite and positive")
    return scalars


def _intermediates(
    state: NativePrepState,
    geometry: FrozenPrepGeometry,
    config: NativePrepConfig,
):
    ptop, rd, p0, t0, alpha, gamma, kappa, g = _config_values(config)
    dphi = (state.ph[1:] + geometry.phb[1:]) - (state.ph[:-1] + geometry.phb[:-1])
    h = geometry.c3h * state.mu_total + geometry.c4h + ptop
    p_d = geometry.c3f[:-1] * state.mu_total + geometry.c4f[:-1] + ptop
    p_u = geometry.c3f[1:] * state.mu_total + geometry.c4f[1:] + ptop
    ell = torch.log(p_d / p_u)
    volume = dphi / h / ell
    temp_moist = state.thm_pert + t0
    pressure = p0 * (rd * temp_moist / (p0 * volume)).pow(gamma)
    pii = (pressure / p0).pow(kappa)
    a = 1.0 + alpha * state.qv
    theta_dry = temp_moist / a
    rho = 1.0 / volume
    delz = dphi / g
    return {
        "dphi": dphi, "h": h, "p_d": p_d, "p_u": p_u, "ell": ell,
        "volume": volume, "temp_moist": temp_moist, "pressure": pressure,
        "pii": pii, "a": a, "theta_dry": theta_dry, "rho": rho, "delz": delz,
    }


def native_prep(
    state: NativePrepState,
    geometry: FrozenPrepGeometry,
    config: NativePrepConfig,
) -> NativePrepResult:
    """Compute continuous fp64 theta, density, Exner, full P, and layer depth."""
    _validate_inputs(state, geometry, config)
    values = _intermediates(state, geometry, config)
    result = NativePrepResult(values["theta_dry"], values["rho"], values["pii"],
                              values["pressure"], values["delz"])
    for name, value in zip(NativePrepResult._fields, result):
        _finite(f"output.{name}", value)
    return result


def native_prep_jvp(
    state: NativePrepState,
    geometry: FrozenPrepGeometry,
    direction: NativePrepState,
    config: NativePrepConfig,
) -> NativePrepResult:
    """Analytic JVP over live state fields; geometry and scalars stay fixed."""
    _validate_inputs(state, geometry, config, tangent=direction)
    _, _, _, _, alpha, gamma, kappa, g = _config_values(config)
    v = _intermediates(state, geometry, config)
    dphi = v["dphi"]
    volume = v["volume"]
    temp_moist = v["temp_moist"]
    pressure = v["pressure"]
    pii = v["pii"]
    h = v["h"]
    p_d, p_u, ell = v["p_d"], v["p_u"], v["ell"]

    d_dphi = direction.ph[1:] - direction.ph[:-1]
    m_mu = -geometry.c3h / h - (geometry.c3f[:-1] / p_d - geometry.c3f[1:] / p_u) / ell
    d_volume = volume * (d_dphi / dphi + m_mu * direction.mu_total)
    d_temp = direction.thm_pert
    d_pressure = gamma * pressure * (d_temp / temp_moist - d_volume / volume)
    d_pii = kappa * pii * d_pressure / pressure
    d_theta = d_temp / v["a"] - alpha * temp_moist * direction.qv / (v["a"] * v["a"])
    d_rho = -d_volume / (volume * volume)
    d_delz = d_dphi / g
    return NativePrepResult(d_theta, d_rho, d_pii, d_pressure, d_delz)


def native_prep_vjp(
    state: NativePrepState,
    geometry: FrozenPrepGeometry,
    cotangent: NativePrepResult,
    config: NativePrepConfig,
) -> NativePrepState:
    """Analytic VJP for the live prep state; no geometry/parameter gradients."""
    _validate_inputs(state, geometry, config)
    if not isinstance(cotangent, NativePrepResult):
        raise TypeError("cotangent must be NativePrepResult")
    for name, value in zip(NativePrepResult._fields, cotangent):
        _tensor(f"cotangent.{name}", value)
        if value.shape != state.thm_pert.shape or value.device != state.thm_pert.device:
            raise ValueError(f"cotangent.{name} metadata must match native levels")
        _finite(f"cotangent.{name}", value)

    _, _, _, _, alpha, gamma, kappa, g = _config_values(config)
    v = _intermediates(state, geometry, config)
    dphi = v["dphi"]
    volume = v["volume"]
    temp_moist = v["temp_moist"]
    pressure = v["pressure"]
    pii = v["pii"]
    h = v["h"]
    p_d, p_u, ell = v["p_d"], v["p_u"], v["ell"]

    u_pressure = cotangent.p + cotangent.pii * kappa * pii / pressure
    u_temp = cotangent.th / v["a"] + u_pressure * gamma * pressure / temp_moist
    u_qv = -cotangent.th * alpha * temp_moist / (v["a"] * v["a"])
    u_volume = -cotangent.rho / (volume * volume) - u_pressure * gamma * pressure / volume
    u_dphi = u_volume * volume / dphi + cotangent.delz / g
    m_mu = -geometry.c3h / h - (geometry.c3f[:-1] / p_d - geometry.c3f[1:] / p_u) / ell
    u_mu = (u_volume * volume * m_mu).sum()
    u_ph = torch.cat((
        -u_dphi[:1],
        u_dphi[:-1] - u_dphi[1:],
        u_dphi[-1:],
    ))
    return NativePrepState(u_temp, u_qv, u_mu.reshape(()), u_ph)
