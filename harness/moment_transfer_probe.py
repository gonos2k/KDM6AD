"""Conditional dry-mass/volume representations of the existing ice kernel.

The density is explicitly declared dry density for this isolated experiment.
This does not establish that the native host currently supplies that basis.
"""

from __future__ import annotations

import torch

from kdm6.sed_conservative import conservative_ice_substep_advection_torch
from kdm6.sedimentation import IceSubstepState, default_substep_advection_params


def volume_moments(moments, rho, basis):
    if basis not in ("dry_mass", "volume"):
        raise ValueError("declare dry_mass or volume")
    return moments * rho.unsqueeze(0) if basis == "dry_mass" else moments


def transport(moments, rho, dz, velocity, *, dt=2.0, steps=1, basis="dry_mass"):
    """Return physical cell inventories and bottom export of both moments.

    Inputs: moments[2,B,K], rho/dz[B,K], velocity[2,B,K]. Mass and number
    velocities are independent. The real conservative kernel generates the
    limited departure; no prescribed transfer amount is injected. Inputs are
    prevalidated outside the differentiated map by ``validate``.
    """
    physical = volume_moments(moments, rho, basis)
    q, number = physical[0] / rho, physical[1]
    fall_q = torch.zeros_like(q)
    fall_n = torch.zeros_like(number)
    for _ in range(steps):
        out = conservative_ice_substep_advection_torch(
            IceSubstepState(qi=q, ni=number),
            fall_q,
            fall_n,
            velocity[0] / dz,
            velocity[1] / dz,
            dz,
            rho,
            dtcld=dt / steps,
            params=default_substep_advection_params(),
        )
        q, number = out.state
        fall_q, fall_n = out.fall_qi, out.fall_ni
    cells = torch.stack((rho * q * dz, number * dz))
    # fall stores a sum of per-substep rates, hence multiply by dt/steps.
    bottom = torch.stack((fall_q[:, -1], fall_n[:, -1])) * dz[:, -1] * (dt / steps)
    return torch.cat((cells, bottom.unsqueeze(-1)), dim=-1)


def inventory_reference(
    moments, rho, dz, velocity, *, dt=2.0, steps=1, basis="dry_mass"
):
    """Independent inventory-coordinate recurrence for the fixed velocities."""
    cells = volume_moments(moments, rho, basis) * dz.unsqueeze(0)
    bottom = torch.zeros_like(cells[..., 0])
    for _ in range(steps):
        offered = cells * velocity * (dt / steps) / dz.unsqueeze(0)
        outgoing = torch.minimum(offered, cells)
        incoming = torch.cat(
            (torch.zeros_like(outgoing[..., :1]), outgoing[..., :-1]), -1
        )
        cells = cells - outgoing + incoming
        bottom = bottom + outgoing[..., -1]
    return torch.cat((cells, bottom.unsqueeze(-1)), -1)


def validate(moments, rho, dz, velocity, *, dt, steps):
    """Value-only experimental domain: floors are inactive, moments nonnegative."""
    if (
        rho.ndim != 2
        or dz.shape != rho.shape
        or moments.shape != (2, *rho.shape)
        or velocity.shape != moments.shape
    ):
        raise ValueError("expected moments/velocity[2,B,K], rho/dz[B,K]")
    if type(steps) is not int or steps < 1 or not 0 < dt < float("inf"):
        raise ValueError("positive finite dt and positive integer steps required")
    if not all(bool(torch.isfinite(x).all()) for x in (moments, rho, dz, velocity)):
        raise ValueError("finite operands required")
    if not bool(
        (rho > 1e-9).all()
        and (dz > 1e-9).all()
        and (moments >= 0).all()
        and (velocity >= 0).all()
    ):
        raise ValueError(
            "positive geometry above kernel floors and nonnegative state/velocity required"
        )
