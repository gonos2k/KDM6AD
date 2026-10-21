"""Native WRF-column pressure/profile builder for the first-order RTTOV path.

This module preserves the 39 WRF mass levels and their 40 ``P8W`` interfaces.
It does not interpolate the native column onto the historical RTTOV fixture
grid. A fixed upper-reference prefix can be prepended when the model top is
below the desired RTTOV user-profile top.

The pressure-interface equations follow ``moist_physics_prep_em`` in the active
host source. Native arrays use WRF bottom-to-top order; returned RTTOV arrays
are flipped to increasing pressure (TOA-to-surface). All model-column
thermodynamic and pressure inputs remain live Torch values. Eta interpolation
weights and optional upper-reference values are fixed geometry.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real

import torch

from .model_profile_builder import RttovProfileTensors, qv_to_q_ppmv_moist


@dataclass(frozen=True)
class NativeObservationState:
    """One WRF-native column, bottom-to-top.

    ``thm_pert`` is the perturbation total moist potential temperature carried
    by ``THM_2``; ``p_center_Pa`` is full mass-level pressure ``P+PB``; and
    ``phi_interfaces`` is full interface geopotential ``PH_2+PHB``.
    """

    thm_pert: torch.Tensor
    qv: torch.Tensor
    p_center_Pa: torch.Tensor
    phi_interfaces: torch.Tensor


@dataclass(frozen=True)
class FrozenNativeProfileGeometry:
    """Fixed WRF eta interpolation weights used for interior ``P8W`` levels."""

    fnm: torch.Tensor
    fnp: torch.Tensor


@dataclass(frozen=True)
class NativeObservationConfig:
    """Fixed thermodynamic constants promoted from the host's REAL values."""

    alpha: float
    t0: float
    kappa: float
    p0: float
    g: float


@dataclass(frozen=True)
class UpperReferenceProfile:
    """Full fixed RTTOV reference profile plus fixed upper-layer count.

    Pressure grids are in RTTOV order/units. For U=`fixed_upper_count`, the
    output retains `p_lay_hpa[:U-1]`/T/Q for complete upper reference layers,
    then constructs one live partial layer at the native model top. Its center
    pressure is the geometric mean of `p_half_hpa[U-1]` and the live native
    `P8W` top interface; T/Q are log-pressure interpolated on the fixed
    reference center grid. The native 39 centers and 40 interfaces follow
    unchanged. Reference values and U are fixed, never gradient leaves.
    """

    p_lay_hpa: torch.Tensor       # full reference layer-center grid
    p_half_hpa: torch.Tensor      # full reference interface grid (L+1)
    t_k: torch.Tensor             # full reference layer temperature
    q_ppmv: torch.Tensor          # full reference moist-air ppmv
    fixed_upper_count: int        # number of layers above the native model top


def _fixed_scalar(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a fixed real scalar")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _config_values(config: NativeObservationConfig) -> tuple[float, ...]:
    if not isinstance(config, NativeObservationConfig):
        raise TypeError("config must be NativeObservationConfig")
    values = tuple(_fixed_scalar(name, getattr(config, name)) for name in
                   ("alpha", "t0", "kappa", "p0", "g"))
    alpha, t0, kappa, p0, g = values
    if any(x <= 0.0 for x in values):
        raise ValueError("alpha, t0, kappa, p0 and g must be positive")
    return values


def _check_tensor(name: str, value: torch.Tensor, device: torch.device) -> None:
    if not isinstance(value, torch.Tensor):
        raise TypeError(f"{name} must be a torch.Tensor")
    if value.dtype != torch.float64 or value.layout != torch.strided:
        raise TypeError(f"{name} must be a strided torch.float64 tensor")
    if value.device != device:
        raise ValueError(f"{name} must be on the same device as the native state")


def _finite(name: str, value: torch.Tensor) -> None:
    # Domain-only preflight. The boolean is not used in any output or product;
    # the live computation below keeps the original Torch graph intact.
    if not bool(torch.isfinite(value).all().item()):
        raise ValueError(f"{name} must be finite")


def _validate_native_inputs(
    state: NativeObservationState,
    geometry: FrozenNativeProfileGeometry,
    config: NativeObservationConfig,
) -> tuple[int, tuple[float, ...]]:
    scalars = _config_values(config)
    if not isinstance(state, NativeObservationState):
        raise TypeError("state must be NativeObservationState")
    if not isinstance(geometry, FrozenNativeProfileGeometry):
        raise TypeError("geometry must be FrozenNativeProfileGeometry")

    if state.thm_pert.ndim != 1:
        raise ValueError("thm_pert must be a one-dimensional native mass column")
    levels = state.thm_pert.numel()
    if levels < 2:
        raise ValueError("native interface extrapolation requires at least two mass levels")
    device = state.thm_pert.device
    for name in ("thm_pert", "qv", "p_center_Pa"):
        value = getattr(state, name)
        _check_tensor(f"state.{name}", value, device)
        if value.shape != (levels,):
            raise ValueError(f"state.{name} must have shape ({levels},)")
        _finite(f"state.{name}", value)
    _check_tensor("state.phi_interfaces", state.phi_interfaces, device)
    if state.phi_interfaces.shape != (levels + 1,):
        raise ValueError(f"phi_interfaces must have shape ({levels + 1},)")
    _finite("state.phi_interfaces", state.phi_interfaces)

    for name in ("fnm", "fnp"):
        value = getattr(geometry, name)
        _check_tensor(f"geometry.{name}", value, device)
        if value.shape != (levels,):
            raise ValueError(f"geometry.{name} must have shape ({levels},)")
        if value.requires_grad:
            raise ValueError(f"geometry.{name} is fixed and must not require gradients")
        _finite(f"geometry.{name}", value)
    if not bool((state.thm_pert + scalars[1] > 0.0).all().item()):
        raise ValueError("THM_2 + T0 must be positive")
    if not bool((state.qv >= 0.0).all().item()):
        raise ValueError("QV must be nonnegative")
    if not bool((state.p_center_Pa > 0.0).all().item()):
        raise ValueError("full mass-level pressure must be positive")
    if not bool((state.p_center_Pa[:-1] > state.p_center_Pa[1:]).all().item()):
        raise ValueError("native mass pressure must decrease bottom-to-top")
    if not bool((state.phi_interfaces[1:] > state.phi_interfaces[:-1]).all().item()):
        raise ValueError("full interface geopotential must increase bottom-to-top")
    return levels, scalars


def native_interface_pressure(
    p_center_Pa: torch.Tensor,
    phi_interfaces: torch.Tensor,
    geometry: FrozenNativeProfileGeometry,
    config: NativeObservationConfig,
) -> torch.Tensor:
    """Return native ``P8W`` pressure in Pa, in WRF bottom-to-top order.

    Interior interface pressure uses the actual WRF ``FNM/FNP`` interpolation
    weights. Bottom pressure is the source's linear-in-height extrapolation from
    the first two mass levels; top pressure is its log-pressure extrapolation
    from the last two. It is an interface-pressure diagnostic, not ``P_HYD_W``
    and not a hybrid ``C3F/C4F`` auxiliary grid.
    """
    if not isinstance(p_center_Pa, torch.Tensor) or p_center_Pa.ndim != 1:
        raise TypeError("p_center_Pa must be a one-dimensional tensor")
    # Reuse the shared shape/domain validation with a finite dummy native state;
    # the public API still validates the actual pressure/geopotential/weights.
    if not isinstance(phi_interfaces, torch.Tensor) or phi_interfaces.ndim != 1:
        raise TypeError("phi_interfaces must be a one-dimensional tensor")
    dummy = NativeObservationState(
        torch.ones_like(p_center_Pa), torch.zeros_like(p_center_Pa),
        p_center_Pa, phi_interfaces)
    _validate_native_inputs(dummy, geometry, config)
    _, (_, _, _, _, g) = _validate_native_inputs(dummy, geometry, config)

    # P8W interior interpolation: Fortran k=2..L, zero-based interfaces 1..L-1.
    interior = (geometry.fnm[1:] * p_center_Pa[1:] +
                geometry.fnp[1:] * p_center_Pa[:-1])

    z_w = phi_interfaces / g
    z_m = 0.5 * (z_w[:-1] + z_w[1:])
    w_bottom = (z_w[0] - z_m[1]) / (z_m[0] - z_m[1])
    p_bottom = w_bottom * p_center_Pa[0] + (1.0 - w_bottom) * p_center_Pa[1]
    w_top = (z_w[-1] - z_m[-2]) / (z_m[-1] - z_m[-2])
    p_top = torch.exp(w_top * torch.log(p_center_Pa[-1]) +
                      (1.0 - w_top) * torch.log(p_center_Pa[-2]))
    result = torch.cat((p_bottom.reshape(1), interior, p_top.reshape(1)))
    _finite("P8W", result)
    if not bool((result > 0.0).all().item()):
        raise ValueError("P8W pressure must be positive")
    if not bool((result[:-1] > result[1:]).all().item()):
        raise ValueError("P8W pressure must decrease bottom-to-top")
    if not bool(((result[1:] < p_center_Pa) & (p_center_Pa < result[:-1])).all().item()):
        raise ValueError("mass-level pressure must interleave native P8W interfaces")
    return result


def _fixed_upper(
    upper: UpperReferenceProfile,
    *,
    device: torch.device,
    native_top_hPa: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    if not isinstance(upper, UpperReferenceProfile):
        raise TypeError("upper must be UpperReferenceProfile or None")
    values = []
    for name in ("p_lay_hpa", "p_half_hpa", "t_k", "q_ppmv"):
        value = getattr(upper, name)
        _check_tensor(f"upper.{name}", value, device)
        if value.ndim != 1:
            raise ValueError(f"upper.{name} must be a one-dimensional vector")
        if value.requires_grad:
            raise ValueError(f"upper.{name} is fixed reference data and must not require gradients")
        _finite(f"upper.{name}", value)
        values.append(value)
    p_lay_ref, p_half_ref, t_ref, q_ref = values
    n_ref_lay = p_lay_ref.numel()
    n_ref_half = p_half_ref.numel()
    if n_ref_lay < 2 or n_ref_half != n_ref_lay + 1 or \
            t_ref.numel() != n_ref_lay or q_ref.numel() != n_ref_lay:
        raise ValueError("reference P/T/Q need L centers and L+1 interfaces")
    if type(upper.fixed_upper_count) is not int:
        raise TypeError("fixed_upper_count must be an integer")
    n_upper = upper.fixed_upper_count
    if n_upper < 2 or n_upper >= n_ref_half:
        raise ValueError("fixed_upper_count must leave an upper half-level bracket and center")
    if not bool((p_half_ref >= 0.0).all().item()):
        raise ValueError("reference half-level pressure must be nonnegative")
    if not bool((p_half_ref[1:] > p_half_ref[:-1]).all().item()):
        raise ValueError("reference half-level pressure must increase TOA-to-surface")
    if not bool((p_lay_ref[1:] > p_lay_ref[:-1]).all().item()):
        raise ValueError("reference layer pressure must increase TOA-to-surface")
    if not bool(((p_lay_ref > p_half_ref[:-1]) &
                 (p_lay_ref < p_half_ref[1:])).all().item()):
        raise ValueError("reference layer pressure must interleave reference half levels")
    if not bool((t_ref > 0.0).all().item()):
        raise ValueError("upper reference temperature must be positive")
    if not bool((q_ref >= 0.0).all().item()):
        raise ValueError("upper reference Q must be nonnegative ppmv")
    lower_bound = p_half_ref[n_upper - 1]
    upper_bound = p_half_ref[n_upper]
    if not bool(((native_top_hPa > lower_bound) &
                 (native_top_hPa < upper_bound)).item()):
        raise ValueError(
            "native top pressure must be strictly inside the fixed upper-count "
            "half-level bracket; equality/outside changes the layer count")

    # The interpolation interval is discrete, so refuse an exact reference
    # center where the piecewise log-linear T/Q derivative changes branch.
    p_partial = torch.sqrt(lower_bound * native_top_hPa)
    if bool((p_partial == p_lay_ref).any().item()):
        raise ValueError("partial-layer pressure equals a reference center interpolation knot")
    hi = int(torch.searchsorted(p_lay_ref.contiguous(), p_partial.reshape(1),
                                right=False).item())
    if not 0 < hi < n_ref_lay:
        raise ValueError("partial-layer pressure lacks a two-point reference interpolation bracket")
    lo = hi - 1
    weight = ((torch.log(p_partial) - torch.log(p_lay_ref[lo])) /
              (torch.log(p_lay_ref[hi]) - torch.log(p_lay_ref[lo])))
    t_partial = t_ref[lo] + weight * (t_ref[hi] - t_ref[lo])
    q_partial = q_ref[lo] + weight * (q_ref[hi] - q_ref[lo])

    p_upper_lay = torch.cat((p_lay_ref[:n_upper - 1], p_partial.reshape(1)))
    p_upper_half = p_half_ref[:n_upper]
    t_upper = torch.cat((t_ref[:n_upper - 1], t_partial.reshape(1)))
    q_upper = torch.cat((q_ref[:n_upper - 1], q_partial.reshape(1)))
    return p_upper_lay, p_upper_half, t_upper, q_upper


def native_to_rttov_profile(
    state: NativeObservationState,
    geometry: FrozenNativeProfileGeometry,
    config: NativeObservationConfig,
    upper: UpperReferenceProfile | None = None,
) -> RttovProfileTensors:
    """Map one native column to RTTOV layers without pressure remapping.

    Native mass levels and ``P8W`` interfaces are reversed to RTTOV's increasing
    pressure order. If ``upper`` is supplied, those fixed RTTOV layers are
    prepended; native levels remain untouched. ``P`` and ``P_HALF`` are hPa,
    temperature is K, and humidity is ppmv over moist air (gas_units=2).
    The bottom ``P_HALF`` is the surface pressure used internally by RTTOV.
    """
    _, (alpha, t0, kappa, p0, _g) = _validate_native_inputs(state, geometry, config)
    p8w_bottom_to_top = native_interface_pressure(
        state.p_center_Pa, state.phi_interfaces, geometry, config)
    pii = (state.p_center_Pa / p0).pow(kappa)
    theta_dry = (state.thm_pert + t0) / (1.0 + alpha * state.qv)
    t_native = theta_dry * pii
    q_native = qv_to_q_ppmv_moist(
        state.qv, gas_units=2, qv_convention="mixing_ratio_kgkg_dry")
    p_native_hpa = torch.flip(state.p_center_Pa / 100.0, dims=(0,))
    p_half_native_hpa = torch.flip(p8w_bottom_to_top / 100.0, dims=(0,))
    t_native = torch.flip(t_native, dims=(0,))
    q_native = torch.flip(q_native, dims=(0,))

    if upper is None:
        p_lay = p_native_hpa
        p_half = p_half_native_hpa
        t_lay, q_lay = t_native, q_native
    else:
        p_lay_upper, p_half_upper, t_upper, q_upper = _fixed_upper(
            upper, device=state.thm_pert.device, native_top_hPa=p_half_native_hpa[0])
        p_lay = torch.cat((p_lay_upper, p_native_hpa))
        p_half = torch.cat((p_half_upper, p_half_native_hpa))
        t_lay = torch.cat((t_upper, t_native))
        q_lay = torch.cat((q_upper, q_native))

    # RTTOV order is top-to-surface: all pressures are positive/interleaved,
    # with a zero TOA half-level permitted by RTTOV's profile contract.
    if p_lay.numel() != p_half.numel() - 1:
        raise ValueError("RTTOV profile requires one more half level than layer")
    if not bool((p_half[1:] > p_half[:-1]).all().item()):
        raise ValueError("RTTOV P_HALF must increase strictly TOA-to-surface")
    if not bool(((p_lay > p_half[:-1]) & (p_lay < p_half[1:])).all().item()):
        raise ValueError("RTTOV layer P must strictly interleave P_HALF")
    for name, value in (("T", t_lay), ("Q", q_lay), ("P", p_lay), ("P_HALF", p_half)):
        _finite(name, value)
    return RttovProfileTensors(t_lay=t_lay, q_lay=q_lay,
                               p_lay=p_lay, p_half=p_half)
