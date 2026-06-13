"""P2 -- model column -> RTTOV-unit torch tensors (design 5, 14.3-units; M2 gate).

★ The whole leaves -> RTTOV-unit path must be PURE TORCH and differentiable
(gradient-propagation contract, design 14.3). A single numpy/.item() step severs
leaves -> RttovObsOp. The autograd-critical transforms here are:
  T   = th * pii            (differentiable in th)
  Q   = ppmv_moist(qv)      (differentiable in qv; gas_units=2)
both elementwise, then a CONSTANT log-pressure interpolation onto the RTTOV
profile grid (the interp weights are constant -- p is forcing -- so grad flows
through the interpolated field only, exactly the design's "W^T autograd auto-
compose").

Scope (P2): the clear-sky T/Q path. Cloud content/Deff (bridge -> reff->Deff x2)
is hydrotable-blocked (design 1.7/13) and appended in a later phase; surface /
geometry tensors likewise. RTTOV-14 AMI is layer-based: T/Q live on LAYERS, so
the interpolation target is the layer pressure grid (PHalf/levels is a constant
passthrough). Grid is NOT hard-coded -- the target pressures come from cfg
(derived upstream from coef/fixture, design 5).

Reference formulas (scalar): ``_rttov_reference/humidity_unit_conversion.py``.
Reimplemented here in torch so dQ/dqv is autograd-composed (do not call the
scalar reference on the differentiable path).
"""
from __future__ import annotations

from typing import NamedTuple

import torch

# Molar masses (kg/mol) -- mirror humidity_unit_conversion.py exactly.
_M_DRY_AIR = 28.9647e-3
_M_WATER_VAPOR = 18.01528e-3

# Supported qv conventions; gas_units MUST be 2 (ppmv over moist air, ami/501).
_SUPPORTED_QV_CONVENTIONS = ("mixing_ratio_kgkg_dry", "specific_humidity_kgkg_moist")
_REQUIRED_GAS_UNITS = 2

_PMIN = 1.0e-30  # log() floor; pressures are >0 so this only guards against junk.
_QMAX = 1.0 - 1.0e-12  # specific-humidity ceiling (q < 1 strictly).


class RttovProfileConfig(NamedTuple):
    """Config consumed by ``model_to_rttov_tensors`` (duck-typed; any object with
    these attributes works). Times/grids are derived upstream, not hard-coded.

    ``rttov_layer_pressure`` is the target layer grid (1-D, ascending in
    pressure) for T/Q; ``None`` skips interpolation (column already on grid).
    ``rttov_level_pressure`` (PHalf, 1-D ascending) is a constant passthrough.
    """
    gas_units: int                                 # must be _REQUIRED_GAS_UNITS (2)
    qv_convention: str                             # one of _SUPPORTED_QV_CONVENTIONS
    rttov_layer_pressure: "torch.Tensor | None" = None
    rttov_level_pressure: "torch.Tensor | None" = None


class RttovProfileTensors(NamedTuple):
    """RTTOV-unit profile tensors (design 5). ``t_lay``/``q_lay`` are
    differentiable in the model leaves; ``p_lay``/``p_half`` are constant grid.
    Cloud and surface tensors are appended by later phases (deferred here)."""
    t_lay: torch.Tensor                  # temperature on RTTOV layers [K]
    q_lay: torch.Tensor                  # water vapour, ppmv moist, on layers
    p_lay: "torch.Tensor | None" = None  # layer pressures (constant) or None
    p_half: "torch.Tensor | None" = None  # half-level pressures (constant) or None


def _require_qv_units(gas_units, qv_convention) -> None:
    """Fail unless the gas unit/convention are explicitly the supported ones.

    The design forbids relabelling qv as RTTOV Q: ``gas_units`` and
    ``qv_convention`` must be stated (design 5, 4.2; M2 ``test_units``).
    """
    if gas_units != _REQUIRED_GAS_UNITS:
        raise ValueError(
            f"gas_units must be {_REQUIRED_GAS_UNITS} (ppmv over moist air); got "
            f"{gas_units!r}. qv must not be relabelled as RTTOV Q (design 5/4.2).")
    if qv_convention not in _SUPPORTED_QV_CONVENTIONS:
        raise ValueError(
            f"qv_convention must be explicit, one of {_SUPPORTED_QV_CONVENTIONS}; "
            f"got {qv_convention!r} (design 5/4.2).")


def qv_to_q_ppmv_moist(qv: torch.Tensor, *, gas_units: int, qv_convention: str) -> torch.Tensor:
    """Convert model water vapour ``qv`` to RTTOV Q (ppmv over moist air), torch.

    ``mixing_ratio_kgkg_dry``: ``w`` = kg vapour / kg dry air; mole fraction
        ``x_v = (w/M_v) / (1/M_d + w/M_v)``; ``Q = 1e6 * x_v``.
    ``specific_humidity_kgkg_moist``: ``q`` = kg vapour / kg moist air;
        ``w = q/(1-q)`` then the same formula.
    Mirrors ``humidity_unit_conversion.py`` but in torch so dQ/dqv is autograd-
    composed. ``qv`` is clamped to its physical range (clip_positive: grad is 0
    for the unphysical qv<0 region -- the correct subgradient, not a graph break).
    """
    _require_qv_units(gas_units, qv_convention)
    if qv_convention == "specific_humidity_kgkg_moist":
        q = torch.clamp(qv, min=0.0, max=_QMAX)
        w = q / (1.0 - q)
    else:  # mixing_ratio_kgkg_dry
        w = torch.clamp(qv, min=0.0)
    numerator = w / _M_WATER_VAPOR
    denominator = (1.0 / _M_DRY_AIR) + numerator  # always > 0
    return 1.0e6 * numerator / denominator


def extract_model_columns(leaves, forcing):
    """Extract (T, qv, p) from the model column with torch ops (design 5).

    ``T = th * pii`` (matches runtime._state_to_coord t=th*pii); ``qv`` is the
    raw mixing ratio (converted by ``qv_to_q_ppmv_moist``); ``p`` is the model
    pressure (forcing, constant). Pure torch so grad flows to th and qv.
    """
    t = leaves.th * forcing.pii
    return t, leaves.qv, forcing.p


def interp_log_pressure(field: torch.Tensor, p_src: torch.Tensor, p_dst: torch.Tensor) -> torch.Tensor:
    """Linear-in-log-pressure interpolation of ``field`` from ``p_src`` to ``p_dst``.

    ``field`` is ``[..., n_src]`` (vertical = last axis); ``p_src`` ``[n_src]`` and
    ``p_dst`` ``[n_dst]`` are 1-D and STRICTLY ASCENDING in pressure (RTTOV order
    TOA->surface; the caller orders the column -- mis-ordering raises rather than
    interpolating silently wrong). No extrapolation: targets outside the source
    range clamp to the nearest endpoint. The interpolation weights are computed
    under ``no_grad`` (p is a forcing constant), so this is a constant linear
    operator and grad flows only through the gathered ``field`` -- the design's
    constant W with autograd-composed W^T.
    """
    if p_src.ndim != 1 or p_dst.ndim != 1:
        raise ValueError(
            f"interp grids must be 1-D (got p_src.ndim={p_src.ndim}, "
            f"p_dst.ndim={p_dst.ndim}); per-column pressure interp is a follow-up.")
    n_src = p_src.shape[0]
    if field.shape[-1] != n_src:
        raise ValueError(
            f"field last dim {field.shape[-1]} != len(p_src) {n_src}.")
    if n_src < 2:
        raise ValueError("p_src must have at least 2 levels to interpolate.")
    with torch.no_grad():
        xs = torch.log(torch.clamp(p_src, min=_PMIN))
        xd = torch.log(torch.clamp(p_dst, min=_PMIN))
        if not bool(torch.all(xs[1:] > xs[:-1])):
            raise ValueError("p_src must be strictly ascending in pressure (TOA->surface).")
        if not bool(torch.all(xd[1:] > xd[:-1])):
            raise ValueError("p_dst must be strictly ascending in pressure.")
        # Unit guard: interp is unit-agnostic (log-pressure ratios) ONLY if p_src and
        # p_dst share one unit. Fully-disjoint ranges (e.g. Pa src vs hPa target) would
        # otherwise be absorbed silently by the no-extrapolation endpoint clamp.
        if bool(xd.max() < xs.min()) or bool(xd.min() > xs.max()):
            raise ValueError(
                "p_dst range is disjoint from p_src -- likely a Pa/hPa unit mismatch; "
                "p_src and p_dst must share one pressure unit.")
        idx_right = torch.searchsorted(xs, xd, right=True).clamp(1, n_src - 1)
        idx_left = idx_right - 1
        x_left = xs[idx_left]
        x_right = xs[idx_right]
        w_right = ((xd - x_left) / (x_right - x_left)).clamp(0.0, 1.0)  # endpoint clamp
        w_left = 1.0 - w_right
    lead = field.shape[:-1]
    il = idx_left.expand(*lead, -1)
    ir = idx_right.expand(*lead, -1)
    f_left = torch.gather(field, -1, il)    # differentiable
    f_right = torch.gather(field, -1, ir)
    return w_left * f_left + w_right * f_right


def model_to_rttov_tensors(leaves, forcing, cfg, xland=None,
                           ncmin_land=0.0, ncmin_sea=0.0) -> RttovProfileTensors:
    """leaves(State) -> RTTOV-unit torch tensors for the clear-sky T/Q path.

    Pure-torch from ``leaves`` (design 14.3): extract T=th*pii and Q=ppmv(qv),
    then interpolate both onto the RTTOV layer grid (cfg.rttov_layer_pressure) if
    given. Returns ``RttovProfileTensors``; ``t_lay``/``q_lay`` carry grad to
    th/qv. Cloud and surface tensors are deferred (hydrotable-blocked, design
    1.7/13); ``xland``/``ncmin_*`` are accepted for signature parity with the
    cloud path and are unused on the clear-sky path.
    """
    t_model, qv_model, p_model = extract_model_columns(leaves, forcing)
    q_model = qv_to_q_ppmv_moist(qv_model, gas_units=cfg.gas_units,
                                 qv_convention=cfg.qv_convention)

    # Shared column-grid validation for BOTH the interp and passthrough paths.
    # The passthrough must fail as loudly as the interp branch: a silently
    # passed-through descending/multi-column profile is a wrong-grid footgun
    # (the interp branch raises on the same input -- keep them consistent).
    if p_model.ndim != 1:
        # Do NOT silently take column 0 of a multi-column p (wrong-interp / silent
        # data corruption). The obs operator processes one profile at a time;
        # batched per-column interp is a documented follow-up.
        raise ValueError(
            f"model pressure must be a 1-D column grid (got ndim={p_model.ndim}); "
            "process one profile at a time (batched per-column interp is a follow-up).")
    with torch.no_grad():
        if not bool(torch.all(p_model[1:] > p_model[:-1])):
            raise ValueError(
                "model pressure must be strictly ascending (TOA->surface); flip the "
                "WRF column before the obs operator (no silent wrong-grid passthrough).")

    p_target = getattr(cfg, "rttov_layer_pressure", None)
    if p_target is None:
        t_lay, q_lay, p_lay = t_model, q_model, None
    else:
        # detach: the grid is a constant (forcing), never a grad leaf (design 5).
        p_target = torch.as_tensor(
            p_target, dtype=t_model.dtype, device=t_model.device).detach()
        t_lay = interp_log_pressure(t_model, p_model, p_target)
        q_lay = interp_log_pressure(q_model, p_model, p_target)
        p_lay = p_target

    p_half = getattr(cfg, "rttov_level_pressure", None)
    if p_half is not None:
        p_half = torch.as_tensor(
            p_half, dtype=t_model.dtype, device=t_model.device).detach()
    # RTTOV-14 layer-based invariant: Nlayers = Nlevels - 1 (design 5; profile.py:124).
    if p_lay is not None and p_half is not None and p_half.shape[0] != p_lay.shape[0] + 1:
        raise ValueError(
            f"Nlayers must equal Nlevels-1: p_lay has {p_lay.shape[0]} layers but "
            f"p_half has {p_half.shape[0]} levels (design 5).")
    return RttovProfileTensors(t_lay=t_lay, q_lay=q_lay, p_lay=p_lay, p_half=p_half)
