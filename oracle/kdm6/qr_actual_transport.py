"""QR-only actual-departure map; opt-in research oracle, not runtime default."""

from __future__ import annotations

import math
from typing import NamedTuple

import torch

from . import constants


class ActualQROutputs(NamedTuple):
    qr: torch.Tensor
    fall_qr: torch.Tensor
    departure: torch.Tensor
    arrival: torch.Tensor


def actual_qr_substep(qr, fall_qr, work, rho_d, delz, mstep, n: int, dt: float):
    """Advance top-first QR on positive native dry-density/depth geometry.

    QR/moments use the fixed original B512 main schedule. Input validation is
    a value-only boundary; every physical arithmetic operation below remains
    live to autograd. Other species and number fields are not arguments.
    """
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError("n must be a positive integer")
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("dt must be finite and positive")
    if qr.ndim != 2 or min(qr.shape) < 1:
        raise ValueError("QR must have positive (B,L) shape")
    if any(
        v.shape != qr.shape or v.dtype != torch.float64 or v.device != qr.device
        for v in (qr, fall_qr, work, rho_d, delz)
    ):
        raise ValueError("QR/fall/work/rho/depth require matching fp64 tensors")
    if mstep.requires_grad:
        raise ValueError("mstep is fixed metadata and must not require gradients")
    if mstep.shape != qr.shape[:1] or mstep.device != qr.device:
        raise ValueError("mstep requires matching (B,) metadata")
    with torch.no_grad():
        if any(
            not bool(torch.isfinite(v).all())
            for v in (qr, fall_qr, work, rho_d, delz, mstep)
        ):
            raise ValueError("all entry values must be finite")
        if bool((qr < 0).any()) or bool((work < 0).any()) or bool((fall_qr < 0).any()):
            raise ValueError("QR, work and fall accumulator must be nonnegative")
        if bool((rho_d <= constants.QCRMIN).any()) or bool(
            (delz <= constants.QCRMIN).any()
        ):
            raise ValueError("native dry density and depth must exceed QCRMIN")
        if bool((mstep < 1).any()) or bool((mstep != torch.floor(mstep)).any()):
            raise ValueError("mstep must contain positive integer counts")
    count = torch.clamp(mstep.to(qr.dtype), min=1.0)
    gate = (count >= float(n)).to(qr.dtype)
    new_qr, new_fall, departures, arrivals = [], [], [], []
    for k in range(qr.shape[1]):
        entry = qr[:, k]
        falk = rho_d[:, k] * entry * work[:, k] / count * gate
        departure = torch.minimum(falk * dt / rho_d[:, k], entry)
        if k == 0:
            arrival = torch.zeros_like(departure)
        else:
            arrival = (
                departures[-1]
                * (rho_d[:, k - 1] * delz[:, k - 1])
                / (rho_d[:, k] * delz[:, k])
            )
        new_qr.append(entry - departure + arrival)
        new_fall.append(fall_qr[:, k] + departure * rho_d[:, k] / dt)
        departures.append(departure)
        arrivals.append(arrival)
    return ActualQROutputs(
        *(torch.stack(v, dim=-1) for v in (new_qr, new_fall, departures, arrivals))
    )
