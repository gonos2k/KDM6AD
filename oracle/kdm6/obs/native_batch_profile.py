"""Batched native all-sky RTTOV profile wrapper.

This wrapper adds only a batch dimension. Each row is passed through the
validated single-column native pressure/cloud builders and the outputs are
stacked, preserving the live Torch graph and each column's own native pressure
centers/interfaces. No shared-grid or fixture pressure interpolation is done.
"""

from __future__ import annotations

import torch

from .model_profile_builder import RttovProfileTensors
from .native_cloud_profile import (
    NativeCloudState,
    native_to_rttov_cloud_profile,
)
from .native_profile_builder import (
    FrozenNativeProfileGeometry,
    NativeObservationConfig,
    NativeObservationState,
    UpperReferenceProfile,
)


def _validate_batch(native_state, cloud_state, rho_d, xland):
    if not isinstance(native_state, NativeObservationState):
        raise TypeError("native_state must be NativeObservationState")
    if not isinstance(cloud_state, NativeCloudState):
        raise TypeError("cloud_state must be NativeCloudState")
    reference = native_state.thm_pert
    if not isinstance(reference, torch.Tensor) or reference.ndim != 2:
        raise ValueError("batch thm_pert must have shape (B,L)")
    batch, levels = reference.shape
    if batch < 1 or levels < 2:
        raise ValueError("native batch requires B>=1 and L>=2")
    for name in ("thm_pert", "qv", "p_center_Pa"):
        value = getattr(native_state, name)
        if not isinstance(value, torch.Tensor) or value.shape != (batch, levels):
            raise ValueError(f"native_state.{name} must have shape ({batch},{levels})")
    phi = native_state.phi_interfaces
    if not isinstance(phi, torch.Tensor) or phi.shape != (batch, levels + 1):
        raise ValueError(
            f"native_state.phi_interfaces must have shape ({batch},{levels + 1})"
        )
    for name in ("qc", "qi", "qs", "nc", "ni"):
        value = getattr(cloud_state, name)
        if not isinstance(value, torch.Tensor) or value.shape != (batch, levels):
            raise ValueError(f"cloud_state.{name} must have shape ({batch},{levels})")
    if not isinstance(rho_d, torch.Tensor) or rho_d.shape != (batch, levels):
        raise ValueError(f"rho_d must have shape ({batch},{levels})")
    if rho_d.device != reference.device:
        raise ValueError("rho_d must be on the native state device")
    if not isinstance(xland, torch.Tensor) or xland.shape != (batch,):
        raise ValueError(
            f"xland must contain one fixed value per row, shape ({batch},)"
        )
    if (
        xland.dtype != torch.float64
        or xland.device != reference.device
        or xland.requires_grad
    ):
        raise ValueError(
            "xland must be fixed float64 metadata on the native state device"
        )
    return batch


def native_to_rttov_cloud_profile_batch(
    native_state: NativeObservationState,
    cloud_state: NativeCloudState,
    geometry: FrozenNativeProfileGeometry,
    config: NativeObservationConfig,
    upper: UpperReferenceProfile | None = None,
    *,
    rho_d: torch.Tensor,
    xland: torch.Tensor,
    ncmin_land: float,
    ncmin_sea: float,
) -> RttovProfileTensors:
    """Build all-sky RTTOV profiles from native ``(B,L)`` columns.

    Native centers/interfaces have shapes ``(B,L)``/``(B,L+1)`` and may vary
    across columns. Each row is sent through
    :func:`native_to_rttov_cloud_profile`, which preserves its 39 native levels
    and 40 native interfaces and applies the optional fixed upper-reference
    prefix separately at that row's model top. Fixed vertical geometry and
    reference data are shared; ``rho_d`` and ``xland`` are per-row controls.

    The per-column loop intentionally reuses the already validated scalar
    implementation. Stacking preserves autograd across columns and the shared
    geometry inputs; this is a correctness-first batch wrapper, not a vectorized
    performance claim.
    """
    batch = _validate_batch(native_state, cloud_state, rho_d, xland)
    if not isinstance(geometry, FrozenNativeProfileGeometry):
        raise TypeError("geometry must be FrozenNativeProfileGeometry")
    if not isinstance(config, NativeObservationConfig):
        raise TypeError("config must be NativeObservationConfig")

    columns = []
    for row in range(batch):
        native = NativeObservationState(
            native_state.thm_pert[row],
            native_state.qv[row],
            native_state.p_center_Pa[row],
            native_state.phi_interfaces[row],
        )
        cloud = NativeCloudState(
            cloud_state.qc[row],
            cloud_state.qi[row],
            cloud_state.qs[row],
            cloud_state.nc[row],
            cloud_state.ni[row],
        )
        columns.append(
            native_to_rttov_cloud_profile(
                native,
                cloud,
                geometry,
                config,
                upper,
                rho_d=rho_d[row],
                xland=xland[row],
                ncmin_land=ncmin_land,
                ncmin_sea=ncmin_sea,
            )
        )

    stacked = {}
    for name in RttovProfileTensors._fields:
        values = [getattr(profile, name) for profile in columns]
        if all(value is None for value in values):
            stacked[name] = None
        elif any(value is None for value in values):
            raise RuntimeError(f"single-column builders returned mixed {name} fields")
        else:
            stacked[name] = torch.stack(values, dim=0)
    return RttovProfileTensors(**stacked)
