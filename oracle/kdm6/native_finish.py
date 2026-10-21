"""Continuous fp64 lift of the bounded ``use_theta_m`` host finish expression.

This is a pure pointwise map on an already paired before/after KDM state. It
models the selected host options ``use_theta_m=1`` and ``no_mp_heating=0``;
it is not the complete WRF timestep or a native-host derivative certificate.
The separate f32 value replay preserves captured rounding/FMA behavior; this
module differentiates the continuous expression, not binary32 quantization.
The preflight finite/domain checks are value-only gates and do not modify or
replace input tensors. The map and its explicit tangent/adjoint contain no
scalar extraction or graph detachment.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import NamedTuple

import torch


class ThermoState(NamedTuple):
    """Finish-map state in one fixed coordinate: dry theta and dry-mass Qs."""

    th: torch.Tensor
    qv: torch.Tensor
    qc: torch.Tensor


@dataclass(frozen=True)
class FinishConfig:
    """Fixed scalar parameters for one finish evaluation.

    ``dt`` is seconds, ``alpha`` is Rv/Rd, ``t0`` is K, and
    ``mp_tend_lim`` is the configured K/s bound on the raw theta increment.
    """

    dt: float
    alpha: float
    t0: float
    mp_tend_lim: float


class NativeFinishResult(NamedTuple):
    """The five finish outputs, in host field order."""

    t_new_after: torch.Tensor
    h_rate: torch.Tensor
    qv_rate: torch.Tensor
    qc_rate: torch.Tensor
    th_phy_m_t0: torch.Tensor


# A cotangent has the same named output layout as NativeFinishResult.
NativeFinishCotangent = NativeFinishResult


@dataclass(frozen=True)
class ZeroOutConfig:
    """The host's ``mp_zero_out`` mode and condensate threshold."""

    mode: int
    threshold: float


def _finite_scalar(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real scalar")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _validate_config(config: FinishConfig) -> tuple[float, float, float, float]:
    if not isinstance(config, FinishConfig):
        raise TypeError("config must be FinishConfig")
    dt = _finite_scalar("dt", config.dt)
    alpha = _finite_scalar("alpha", config.alpha)
    t0 = _finite_scalar("t0", config.t0)
    limit = _finite_scalar("mp_tend_lim", config.mp_tend_lim)
    if dt <= 0.0:
        raise ValueError("dt must be positive")
    if alpha <= 0.0:
        raise ValueError("alpha must be positive")
    if t0 <= 0.0:
        raise ValueError("t0 must be positive")
    if limit < 0.0:
        raise ValueError("mp_tend_lim must be nonnegative")
    return dt, alpha, t0, limit


def _validate_state_metadata(state: ThermoState, *, name: str) -> None:
    if not isinstance(state, ThermoState):
        raise TypeError(f"{name} must be ThermoState")
    fields = state
    for field_name, value in zip(("th", "qv", "qc"), fields):
        if not isinstance(value, torch.Tensor):
            raise TypeError(f"{name}.{field_name} must be a torch.Tensor")
        if value.dtype != torch.float64:
            raise TypeError(f"{name}.{field_name} must have dtype torch.float64")
        if value.layout != torch.strided:
            raise TypeError(f"{name}.{field_name} must be a strided tensor")
    reference = state.th
    for field_name, value in zip(("qv", "qc"), (state.qv, state.qc)):
        if value.shape != reference.shape:
            raise ValueError(f"{name}.{field_name} shape must equal {name}.th")
        if value.device != reference.device:
            raise ValueError(f"{name}.{field_name} device must equal {name}.th")


def _preflight_values(state: ThermoState, *, name: str) -> None:
    """Value-only validation gate; tensors are inspected but never modified."""
    for field_name, value in zip(("th", "qv", "qc"), state):
        # .item() is deliberately confined to this explicit input-validation
        # boundary. It does not supply a value to any output or derivative.
        if not bool(torch.isfinite(value).all().item()):
            raise ValueError(f"{name}.{field_name} must be finite")
    if not bool((state.th > 0.0).all().item()):
        raise ValueError(f"{name}.th must be positive")
    if not bool((state.qv >= 0.0).all().item()):
        raise ValueError(f"{name}.qv must be nonnegative")
    if not bool((state.qc >= 0.0).all().item()):
        raise ValueError(f"{name}.qc must be nonnegative")


def _validate_pair(
    before: ThermoState,
    after: ThermoState,
    config: FinishConfig,
) -> tuple[float, float, float, float]:
    params = _validate_config(config)
    _validate_state_metadata(before, name="before")
    _validate_state_metadata(after, name="after")
    for field_name, old, new in zip(("th", "qv", "qc"), before, after):
        if old.shape != new.shape:
            raise ValueError(f"before.{field_name} and after.{field_name} shapes differ")
        if old.device != new.device:
            raise ValueError(f"before.{field_name} and after.{field_name} devices differ")
    _preflight_values(before, name="before")
    _preflight_values(after, name="after")
    return params


def _clipped_increment(
    before: ThermoState,
    after: ThermoState,
    *,
    dt: float,
    limit_rate: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Return m and its strict-interior branch mask g (clipped side at ties)."""
    raw = after.th - before.th
    bound = limit_rate * dt
    interior = (limit_rate > 0.0) & (raw > -bound) & (raw < bound)
    m = torch.where(
        raw >= bound,
        torch.full_like(raw, bound),
        torch.where(raw <= -bound, torch.full_like(raw, -bound), raw),
    )
    # At zero limit every point is on the clipped side, including raw == 0.
    g = interior.to(dtype=raw.dtype)
    return m, g


def native_finish(
    before: ThermoState,
    after: ThermoState,
    config: FinishConfig,
) -> NativeFinishResult:
    """Evaluate the bounded moist-theta finish map in fp64.

    With ``m=clip(th1-th0, ±mp_tend_lim*dt)``, ``D=qv1-qv0``,
    ``A=1+alpha*qv0``, and ``B=1+alpha*qv1``, define
    ``N=m*B + alpha*D*th1`` and ``Tfull=th0*A+N``. Return
    ``(Tfull-t0, N/dt, D/dt, (qc1-qc0)/dt, Tfull/B-t0)``.
    The clip is constant on its clipped side; exact ties use that side.
    """
    dt, alpha, t0, limit_rate = _validate_pair(before, after, config)
    m, _ = _clipped_increment(before, after, dt=dt, limit_rate=limit_rate)
    delta_qv = after.qv - before.qv
    a = 1.0 + alpha * before.qv
    b = 1.0 + alpha * after.qv
    n = m * b + alpha * delta_qv * after.th
    full = before.th * a + n
    return NativeFinishResult(
        full - t0,
        n / dt,
        delta_qv / dt,
        (after.qc - before.qc) / dt,
        full / b - t0,
    )


def native_finish_jvp(
    before: ThermoState,
    after: ThermoState,
    d_before: ThermoState,
    d_after: ThermoState,
    config: FinishConfig,
) -> NativeFinishResult:
    """Analytic JVP of ``native_finish`` for fixed scalar configuration."""
    dt, alpha, _, limit_rate = _validate_pair(before, after, config)
    _validate_state_metadata(d_before, name="d_before")
    _validate_state_metadata(d_after, name="d_after")
    for name, direction, reference in (
        ("d_before", d_before, before), ("d_after", d_after, after)
    ):
        for field_name, value, ref in zip(("th", "qv", "qc"), direction, reference):
            if value.shape != ref.shape or value.device != ref.device or value.dtype != ref.dtype:
                raise ValueError(f"{name}.{field_name} metadata must match corresponding state field")
            _preflight_tangent(value, name=f"{name}.{field_name}")

    m, g = _clipped_increment(before, after, dt=dt, limit_rate=limit_rate)
    delta_qv = after.qv - before.qv
    a = 1.0 + alpha * before.qv
    b = 1.0 + alpha * after.qv
    n = m * b + alpha * delta_qv * after.th
    full = before.th * a + n

    dm = g * (d_after.th - d_before.th)
    ddelta_qv = d_after.qv - d_before.qv
    dn = (
        dm * b
        + alpha * m * d_after.qv
        + alpha * ddelta_qv * after.th
        + alpha * delta_qv * d_after.th
    )
    dfull = (
        d_before.th * a
        + alpha * before.th * d_before.qv
        + dn
    )
    return NativeFinishResult(
        dfull,
        dn / dt,
        ddelta_qv / dt,
        (d_after.qc - d_before.qc) / dt,
        dfull / b - full * alpha * d_after.qv / (b * b),
    )


def _preflight_tangent(value: torch.Tensor, *, name: str) -> None:
    """Explicit value-only finite check for a direction/cotangent tensor."""
    if not bool(torch.isfinite(value).all().item()):
        raise ValueError(f"{name} must be finite")


def native_finish_vjp(
    before: ThermoState,
    after: ThermoState,
    cotangent: NativeFinishCotangent,
    config: FinishConfig,
) -> tuple[ThermoState, ThermoState]:
    """Analytic VJP returning cotangents for ``before`` and ``after`` states."""
    dt, alpha, _, limit_rate = _validate_pair(before, after, config)
    if not isinstance(cotangent, NativeFinishResult):
        raise TypeError("cotangent must be NativeFinishResult")
    for name, value in zip(cotangent._fields, cotangent):
        if not isinstance(value, torch.Tensor) or value.dtype != torch.float64:
            raise TypeError(f"cotangent.{name} must be a torch.float64 tensor")
        if value.shape != before.th.shape or value.device != before.th.device:
            raise ValueError(f"cotangent.{name} metadata must match finish output")
        _preflight_tangent(value, name=f"cotangent.{name}")

    m, g = _clipped_increment(before, after, dt=dt, limit_rate=limit_rate)
    delta_qv = after.qv - before.qv
    a = 1.0 + alpha * before.qv
    b = 1.0 + alpha * after.qv
    n = m * b + alpha * delta_qv * after.th
    full = before.th * a + n

    u_full = cotangent.t_new_after + cotangent.th_phy_m_t0 / b
    u_n = u_full + cotangent.h_rate / dt
    grad_before = ThermoState(
        u_full * a - u_n * g * b,
        u_full * alpha * before.th - u_n * alpha * after.th - cotangent.qv_rate / dt,
        -cotangent.qc_rate / dt,
    )
    grad_after = ThermoState(
        u_n * (g * b + alpha * delta_qv),
        u_n * alpha * (m + after.th) + cotangent.qv_rate / dt
        - cotangent.th_phy_m_t0 * full * alpha / (b * b),
        cotangent.qc_rate / dt,
    )
    return grad_before, grad_after


def _validate_zero_out_config(config: ZeroOutConfig) -> tuple[int, float]:
    if not isinstance(config, ZeroOutConfig):
        raise TypeError("config must be ZeroOutConfig")
    if isinstance(config.mode, bool) or not isinstance(config.mode, int):
        raise TypeError("mode must be an integer 0, 1, or 2")
    if config.mode not in (0, 1, 2):
        raise ValueError("mode must be 0, 1, or 2")
    threshold = _finite_scalar("threshold", config.threshold)
    if threshold < 0.0:
        raise ValueError("threshold must be nonnegative")
    return config.mode, threshold


def _validate_zero_out_state(raw_after: ThermoState, *, name: str) -> None:
    _validate_state_metadata(raw_after, name=name)
    for field_name, value in zip(("th", "qv", "qc"), raw_after):
        # Explicit value-only preflight. Negative qv/qc are valid raw inputs to
        # this cleanup map because clamping them is part of the map itself.
        if not bool(torch.isfinite(value).all().item()):
            raise ValueError(f"{name}.{field_name} must be finite")
    if not bool((raw_after.th > 0.0).all().item()):
        raise ValueError(f"{name}.th must be positive")


def _validate_zero_out_vector(
    vector: ThermoState, reference: ThermoState, *, name: str
) -> None:
    _validate_state_metadata(vector, name=name)
    for field_name, value, ref in zip(("th", "qv", "qc"), vector, reference):
        if value.shape != ref.shape or value.device != ref.device or value.dtype != ref.dtype:
            raise ValueError(f"{name}.{field_name} metadata must match raw_after")
        if not bool(torch.isfinite(value).all().item()):
            raise ValueError(f"{name}.{field_name} must be finite")


def _zero_out_branches(
    raw_after: ThermoState, mode: int, threshold: float
) -> tuple[torch.Tensor, torch.Tensor]:
    if mode == 0:
        return torch.ones_like(raw_after.qv, dtype=torch.bool), torch.ones_like(
            raw_after.qc, dtype=torch.bool
        )
    # QV uses the clipped-side derivative at zero in mode 2. In mode 1 QV is
    # untouched, even when the raw value is negative.
    qv_active = raw_after.qv > 0.0 if mode == 2 else torch.ones_like(
        raw_after.qv, dtype=torch.bool
    )
    # For threshold > 0, equality is a discontinuity of the strict host test
    # qc < threshold and derivative methods reject it separately. For a zero
    # threshold, select the clipped side at qc == 0.
    qc_active = raw_after.qc > threshold
    return qv_active, qc_active


def post_microphysics_thermo(
    raw_after: ThermoState,
    config: ZeroOutConfig,
) -> ThermoState:
    """Apply the thermodynamic fields of host ``microphysics_zero_outa``.

    Mode 0 passes through. Mode 1 zeros QC below threshold and leaves QV alone.
    Mode 2 does the same QC thresholding and clamps QV to nonnegative values.
    Other moist/tracer fields and the separate boundary-only ``zero_outb`` are
    intentionally outside this three-field map.
    """
    mode, threshold = _validate_zero_out_config(config)
    _validate_zero_out_state(raw_after, name="raw_after")
    if mode == 0:
        return raw_after
    if mode == 1:
        qv = raw_after.qv
    else:
        qv = torch.where(raw_after.qv > 0.0, raw_after.qv, torch.zeros_like(raw_after.qv))
    if threshold == 0.0:
        # Values are identical to strict host cleanup, but spelling the zero
        # threshold as max(qc, 0) selects the clipped-side subgradient at qc=0.
        qc = torch.where(raw_after.qc > 0.0, raw_after.qc, torch.zeros_like(raw_after.qc))
    else:
        # The host uses a strict less-than test for positive thresholds.
        qc = torch.where(
            raw_after.qc < threshold,
            torch.zeros_like(raw_after.qc),
            raw_after.qc,
        )
    return ThermoState(raw_after.th, qv, qc)


def post_microphysics_jvp(
    raw_after: ThermoState,
    d_raw_after: ThermoState,
    config: ZeroOutConfig,
) -> ThermoState:
    """Analytic local JVP of the thermodynamic zero-out map.

    At positive QC-threshold equality the map is discontinuous, so this method
    rejects that input rather than selecting a generalized derivative. At a
    zero threshold, QC and mode-2 QV ties use the clipped-side derivative 0.
    """
    mode, threshold = _validate_zero_out_config(config)
    _validate_zero_out_state(raw_after, name="raw_after")
    _validate_zero_out_vector(d_raw_after, raw_after, name="d_raw_after")
    if mode != 0 and threshold > 0.0 and bool((raw_after.qc == threshold).any().item()):
        raise ValueError("QC equals positive zero-out threshold; derivative is discontinuous")
    if mode == 0:
        return d_raw_after
    qv_active, qc_active = _zero_out_branches(raw_after, mode, threshold)
    return ThermoState(
        d_raw_after.th,
        d_raw_after.qv * qv_active.to(dtype=raw_after.qv.dtype),
        d_raw_after.qc * qc_active.to(dtype=raw_after.qc.dtype),
    )


def post_microphysics_vjp(
    raw_after: ThermoState,
    cotangent: ThermoState,
    config: ZeroOutConfig,
) -> ThermoState:
    """Analytic local VJP of the thermodynamic zero-out map."""
    mode, threshold = _validate_zero_out_config(config)
    _validate_zero_out_state(raw_after, name="raw_after")
    _validate_zero_out_vector(cotangent, raw_after, name="cotangent")
    if mode != 0 and threshold > 0.0 and bool((raw_after.qc == threshold).any().item()):
        raise ValueError("QC equals positive zero-out threshold; derivative is discontinuous")
    if mode == 0:
        return cotangent
    qv_active, qc_active = _zero_out_branches(raw_after, mode, threshold)
    return ThermoState(
        cotangent.th,
        cotangent.qv * qv_active.to(dtype=raw_after.qv.dtype),
        cotangent.qc * qc_active.to(dtype=raw_after.qc.dtype),
    )
