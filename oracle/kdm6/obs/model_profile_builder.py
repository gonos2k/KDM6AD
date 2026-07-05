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

# RTTOV cloudy VIS/IR effective-DIAMETER bounds [micron] (code-clipped; design 9.1,
# RTTOV UG 8.5): liquid 2-52, Baum ice 10-120. Deff = 2*reff.
_DEFF_LIQ_MIN, _DEFF_LIQ_MAX = 2.0, 52.0
_DEFF_ICE_MIN, _DEFF_ICE_MAX = 10.0, 120.0
# cfrac is non-differentiable at exactly 1.0 in RTTOV TL/AD/K (UG 8.5) -> clamp.
_CFRAC_MAX = 1.0 - 1.0e-6
# total cloud content [g/m^3] above which a layer is "cloudy" (binary cfrac).
_CFRAC_CONTENT_THRESHOLD = 1.0e-6
# blend denominator floor [g/m^3] for the content-weighted ice reff (avoid 0/0).
_ICE_BLEND_EPS = 1.0e-12


class RttovProfileConfig(NamedTuple):
    """Config consumed by ``model_to_rttov_tensors`` (duck-typed; any object with
    these attributes works). Times/grids are derived upstream, not hard-coded.

    ``rttov_layer_pressure`` is the target layer grid (1-D, ascending in
    pressure) for T/Q; ``None`` skips interpolation (column already on grid).
    ``rttov_level_pressure`` (PHalf, 1-D ascending) is a constant passthrough.
    ``cloud=True`` enables the all-sky cloud path (content + effective diameter
    via the hydrometeor bridge); the clear-sky default is unchanged.
    """
    gas_units: int                                 # must be _REQUIRED_GAS_UNITS (2)
    qv_convention: str                             # one of _SUPPORTED_QV_CONVENTIONS
    rttov_layer_pressure: "torch.Tensor | None" = None
    rttov_level_pressure: "torch.Tensor | None" = None
    cloud: bool = False                            # all-sky cloud path on/off


class RttovProfileTensors(NamedTuple):
    """RTTOV-unit profile tensors (design 5). ``t_lay``/``q_lay`` (and the cloud
    fields) are differentiable in the model leaves; ``p_lay``/``p_half`` are
    constant grid. Cloud fields are ``None`` on the clear-sky path (cfg.cloud=False);
    on the all-sky path they carry content [g/m^3] and effective DIAMETER [micron] on
    the same RTTOV layer grid. Surface tensors are a later phase (deferred here)."""
    t_lay: torch.Tensor                  # temperature on RTTOV layers [K]
    q_lay: torch.Tensor                  # water vapour, ppmv moist, on layers
    p_lay: "torch.Tensor | None" = None  # layer pressures (constant) or None
    p_half: "torch.Tensor | None" = None  # half-level pressures (constant) or None
    # all-sky cloud (design 9.1; HYDRO6/7 + HYDRO_DEFF6/7). None on clear-sky.
    clw: "torch.Tensor | None" = None       # cloud liquid content [g/m^3] (qc)
    ciw: "torch.Tensor | None" = None       # cloud ice content [g/m^3] (qi+qs)
    deff_liq: "torch.Tensor | None" = None  # liquid effective DIAMETER [micron]
    deff_ice: "torch.Tensor | None" = None  # ice effective DIAMETER [micron]
    cfrac: "torch.Tensor | None" = None     # cloud fraction [0, ~1] (detached)


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

    BATCHED form (T1-5): ``p_src`` ``[B, n_src]`` (per-column grids) with ``field``
    ``[B, n_src]`` and a SHARED 1-D ``p_dst`` -> ``[B, n_dst]``. Row-wise identical
    to the 1-D form (gate test: batched == per-column loop, exact).
    """
    if p_src.ndim == 2:
        # BATCHED per-column source grids (T1-5): p_src [B, n_src], field [B, n_src],
        # p_dst SHARED 1-D target (every column lands on the one fixture layer grid --
        # the batching design the precision review scoped). Same formulas per row;
        # the 1-D path below is byte-unchanged.
        if p_dst.ndim != 1:
            raise ValueError(
                f"batched interp needs a SHARED 1-D p_dst (got ndim={p_dst.ndim}).")
        if field.shape != p_src.shape:
            raise ValueError(
                f"batched interp needs field.shape == p_src.shape "
                f"(got {tuple(field.shape)} vs {tuple(p_src.shape)}).")
        n_src = p_src.shape[-1]
        if n_src < 2:
            raise ValueError("p_src must have at least 2 levels to interpolate.")
        with torch.no_grad():
            xs = torch.log(torch.clamp(p_src, min=_PMIN))                # [B, n_src]
            xd1 = torch.log(torch.clamp(p_dst, min=_PMIN))               # [n_dst]
            if not bool(torch.all(xs[:, 1:] > xs[:, :-1])):
                raise ValueError(
                    "every p_src column must be strictly ascending in pressure "
                    "(TOA->surface).")
            if not bool(torch.all(xd1[1:] > xd1[:-1])):
                raise ValueError("p_dst must be strictly ascending in pressure.")
            if bool((xd1.max() < xs.amin(dim=-1)).any()) or \
               bool((xd1.min() > xs.amax(dim=-1)).any()):
                raise ValueError(
                    "p_dst range is disjoint from some p_src column -- likely a "
                    "Pa/hPa unit mismatch; all grids must share one pressure unit.")
            xd = xd1.expand(p_src.shape[0], -1).contiguous()             # [B, n_dst]
            idx_right = torch.searchsorted(xs, xd, right=True).clamp(1, n_src - 1)
            idx_left = idx_right - 1
            x_left = torch.gather(xs, -1, idx_left)
            x_right = torch.gather(xs, -1, idx_right)
            w_right = ((xd - x_left) / (x_right - x_left)).clamp(0.0, 1.0)
            w_left = 1.0 - w_right
        f_left = torch.gather(field, -1, idx_left)   # differentiable
        f_right = torch.gather(field, -1, idx_right)
        return w_left * f_left + w_right * f_right

    if p_src.ndim != 1 or p_dst.ndim != 1:
        raise ValueError(
            f"interp grids must be 1-D or batched [B, n] p_src (got p_src.ndim="
            f"{p_src.ndim}, p_dst.ndim={p_dst.ndim}).")
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


def _cloud_profile_tensors(leaves, forcing, p_model, p_target, xland,
                           ncmin_land, ncmin_sea):
    """All-sky cloud fields on the RTTOV layer grid (pure-torch, differentiable).

    Wires the hydrometeor bridge (``rttov_cloud_profile``) into the obs path with the
    recommended species->slot mapping: qc -> HYDRO6 liquid; qi+qs -> HYDRO7 ice
    (content sum + content-weighted reff blend); rain/graupel dropped (no VIS/IR Deff
    item). Deff = 2*reff, re-clipped to the RTTOV diameter windows. ``cfrac`` is a
    DETACHED binary condensate gate clamped < 1.0 (RTTOV TL/AD/K is non-differentiable
    at cfrac=1.0, UG 8.5). The bridge runs on a 2-D [1,K] column (preamble_torch); the
    fields are squeezed back to the 1-D [K] obs convention and interpolated onto
    ``p_target`` with the SAME constant-W operator as T/Q (grad flows only through the
    gathered field). Returns (clw, ciw, deff_liq, deff_ice, cfrac) on the layer grid.
    """
    from ..rttov_bridge import rttov_cloud_profile   # lazy: pulls the coordinator chain
    # xland feeds the bridge's per-cell sea/land ncmin gate (xland.view(-1,1)); the obs
    # path is ONE column, so require a single value (reject a multi-column/scalar-float
    # xland that would silently mis-mask -- reject-don't-drop).
    if xland is not None:
        xland = torch.as_tensor(xland)
        if xland.numel() != 1:
            raise ValueError(
                f"xland must be a single-column value (numel 1) on the obs path; got "
                f"shape {tuple(xland.shape)} -- select the column before the obs operator.")
        xland = xland.reshape(1)
    # the bridge needs a [1, K] batch; model_to_rttov_tensors works on a [K] column.
    leaves2d = type(leaves)(*(f.unsqueeze(0) for f in leaves))
    forcing2d = type(forcing)(*(f.unsqueeze(0) for f in forcing))
    cp = rttov_cloud_profile(leaves2d, forcing2d, xland=xland,
                             ncmin_land=ncmin_land, ncmin_sea=ncmin_sea)

    # RTTOV content must be >= 0 (DA increments can drive q<0); clamp_min is the
    # clip_positive subgradient (0 in the unphysical region), not a graph break.
    clw = torch.clamp(cp.clw.squeeze(0), min=0.0)        # qc liquid content [g/m^3]
    ciw_only = torch.clamp(cp.ciw.squeeze(0), min=0.0)
    snow = torch.clamp(cp.snow.squeeze(0), min=0.0)
    ice_content = ciw_only + snow                        # qi + qs ice content [g/m^3]
    # content-weighted ice effective radius (preserves autograd; eps-guarded 0/0 at
    # zero ice -- the clamp's flat region gives a 0 subgradient there, kink-robust).
    denom = torch.clamp(ice_content, min=_ICE_BLEND_EPS)
    reff_ice_blend = (ciw_only * cp.reff_ice.squeeze(0)
                      + snow * cp.reff_snow.squeeze(0)) / denom
    # Deff = 2*reff re-clipped to RTTOV windows. NOTE (number-moment adjoint): reff is
    # ALSO clamped inside the bridge (ice-slope bounds), so dDeff/d(nc,ni)=0 wherever
    # either clamp is saturated -- a legitimate (size-pinned) zero, NOT a wiring break.
    # The live detector for an unintended all-zero number-moment adjoint is the Phase-6
    # getHydroDeffNK nonzero probe, not a Phase-1 assert (which would false-fail here).
    deff_liq = torch.clamp(2.0 * cp.reff_liq.squeeze(0), _DEFF_LIQ_MIN, _DEFF_LIQ_MAX)
    deff_ice = torch.clamp(2.0 * reff_ice_blend, _DEFF_ICE_MIN, _DEFF_ICE_MAX)

    def _interp(field):
        return field if p_target is None else interp_log_pressure(field, p_model, p_target)

    # v1 APPROXIMATION: content AND Deff are interpolated independently in log-pressure.
    # At a cloudy/clear interface the Deff interp is pulled toward the clear-layer floor,
    # so a cloud-edge layer can get undersized particles (small BT bias). The consistent
    # fix (interpolate DSD moments, recompute Deff post-interp) is deferred to the live
    # phase; acceptable for the mock autograd backbone.
    clw_lay = _interp(clw)
    ciw_lay = _interp(ice_content)
    deff_liq_lay = _interp(deff_liq)
    deff_ice_lay = _interp(deff_ice)

    # reject-don't-drop: a non-finite cloud field from a degenerate column would
    # otherwise be MASKED (NaN > thresh is False -> cfrac=0 hides NaN content). Reject
    # at the source rather than letting it reach the RTTOV interface as a silent NaN BT.
    for _nm, _f in (("clw", clw_lay), ("ciw", ciw_lay),
                    ("deff_liq", deff_liq_lay), ("deff_ice", deff_ice_lay)):
        if not bool(torch.isfinite(_f).all()):
            raise ValueError(
                f"cloud field {_nm!r} has non-finite values (degenerate column / bad "
                "bridge output) -- invalid RTTOV input (reject-don't-drop).")

    # cfrac: detached binary condensate gate on the LAYER grid (clamped < 1.0). It is
    # a weighting, not a differentiated input (Phase 1) -> detach so no ghost grad.
    total = (clw_lay + ciw_lay).detach()
    cfrac = torch.where(total > _CFRAC_CONTENT_THRESHOLD,
                        torch.full_like(total, _CFRAC_MAX),
                        torch.zeros_like(total))
    return clw_lay, ciw_lay, deff_liq_lay, deff_ice_lay, cfrac


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
    batched = p_model.ndim == 2
    if p_model.ndim not in (1, 2):
        raise ValueError(
            f"model pressure must be a 1-D column or a [B, nlev] batch "
            f"(got ndim={p_model.ndim}).")
    p_target = getattr(cfg, "rttov_layer_pressure", None)
    if batched:
        # BATCHED columns (T1-5): every column interpolates onto the ONE shared
        # target grid, so the interp branch is REQUIRED -- a batched passthrough
        # would silently pretend per-column grids are the fixture grid.
        if p_target is None:
            raise ValueError(
                "batched columns require cfg.rttov_layer_pressure (shared target "
                "grid); passthrough is single-column only.")
        if getattr(cfg, "cloud", False):
            # Deliberately deferred: all-sky batching's measured lever is only
            # ~1.3x (per-profile scattering dominates), and the cloud staging is
            # single-column. Loud reject beats a silent wrong-shape path.
            raise ValueError(
                "batched columns are clear-sky only for now (cloud staging is "
                "single-column; DA_REALTIME_PLAN T1-5 scope note).")
        with torch.no_grad():
            if not bool(torch.all(p_model[:, 1:] > p_model[:, :-1])):
                raise ValueError(
                    "every model pressure column must be strictly ascending "
                    "(TOA->surface); flip the WRF columns before the obs operator.")
    else:
        with torch.no_grad():
            if not bool(torch.all(p_model[1:] > p_model[:-1])):
                raise ValueError(
                    "model pressure must be strictly ascending (TOA->surface); flip the "
                    "WRF column before the obs operator (no silent wrong-grid passthrough).")

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
        if batched and p_half.ndim == 1:
            # pack_rttov_input requires per-profile P_HALF rows; the shared fixture
            # grid is identical for every column -> broadcast explicitly.
            p_half = p_half.unsqueeze(0).expand(t_lay.shape[0], -1)
    # RTTOV-14 layer-based invariant: Nlayers = Nlevels - 1 (design 5; profile.py:124).
    # Check the EMITTED layer count (t_lay's vertical axis) vs p_half so the
    # PASSTHROUGH path (p_lay is None) cannot silently emit an invalid
    # layer/half-level profile -- e.g. a model column of N levels paired with an
    # N-level p_half (needs N+1) would otherwise pass unchecked.
    if p_half is not None and t_lay.shape[-1] != p_half.shape[-1] - 1:
        raise ValueError(
            f"Nlayers must equal Nlevels-1: emitted profile has {t_lay.shape[-1]} "
            f"layers but p_half has {p_half.shape[-1]} levels (design 5).")

    # All-sky cloud path (design 9.1): append content + effective diameter on the
    # SAME layer grid. Clear-sky (cfg.cloud=False) is byte-unchanged (fields stay None).
    cloud = {}
    if getattr(cfg, "cloud", False):
        clw, ciw, deff_liq, deff_ice, cfrac = _cloud_profile_tensors(
            leaves, forcing, p_model, p_target, xland, ncmin_land, ncmin_sea)
        cloud = dict(clw=clw, ciw=ciw, deff_liq=deff_liq, deff_ice=deff_ice, cfrac=cfrac)
    return RttovProfileTensors(t_lay=t_lay, q_lay=q_lay, p_lay=p_lay, p_half=p_half, **cloud)
