"""
KDM6 warm rain processes — Lim & Hong / Cohard-Pinty 더블모멘트 직역.

원본: module_mp_kdm6.F: 1693-1801 (warm rain block 안의 5 process)

본 모듈은 Step B의 sub-step(B1–B4)을 순수함수로 구현한다.
  - B1:        autoconversion          — `autoconv_torch`        (1706-1717)
  - B2:        accretion (cloud→rain)  — `accretion_torch`       (1724-1742)
  - B3:        self-collection         — `self_collection_torch` (1747-1774)
  - B4:        rain evaporation         — `rain_evap_torch`       (1779-1801)
  - B5:        saturation adjustment    — 별도 모듈 `satadj.py`로 분리 예정

상위 호출자 `kdm62D`는 B1-B4를 같은 do-loop 안에서 호출하지만, 본 oracle은 각
process를 *순수함수*로 분리해 testability와 미분 가능성을 확보한다.

AD 가이드 (procedures/kdm62d-port-decomposition.md, branch-semantics-physical-vs-numerical):
  - 외부 게이트 `qc > qcr AND nc > ncmin` → branch zero
  - `min(rate, qc/dtcld)` 류 잘림 → `torch.minimum`(C^0, subgrad cliff에서만 nondiff)
  - `nc**(-1/3)` 류 음수 exponent → `safe_pow`로 base EPS clamp (외부 게이트로 보호되지만 안전)
"""
from __future__ import annotations

from math import exp, lgamma, pi as _pi
from typing import NamedTuple

import torch

from . import constants as c
from . import fconst as _fc
from .ops import safe_div_pos, safe_pow


def _rgmma(x: float) -> float:
    """Fortran `rgmma(x) = exp(GAMMLN(x)) = Γ(x)` 직역. review6 audit에서 부호 수정
    (이전 구현은 1/Γ였음 — Fortran rgmma는 Γ, 이름은 'reciprocal-gamma'와 무관)."""
    # Fortran rgmma = f32 expf(f32 gammln) — differs from exp(lgamma) at non-integer args (step-67 class)
    return _fc.rgmma_f(x)

# ─── physics constants (Fortran kdm6 module-level) ───────────────────────────

DEFAULT_DEN0 = c.DEN0    # Fortran kdm6init: den0 입력 기본 (1.28 kg m^-3)


# ─── Step B1: Autoconversion (praut + nraut) ─────────────────────────────────


class WarmAutoconvParams(NamedTuple):
    """Fortran kdm6init이 autoconv에 넘기는 시간불변 스칼라."""

    qck1: float       # .104 * 9.8 * peaut / denr^(1/3) / xmyu * den0^(4/3)
    nraut_coeff: float  # 3.5e9 (number autoconv coefficient)
    qcrmin: float
    ncmin: float
    # Per-cell ncmin override (operational xland path; injected by _kdm6_pure, mirrors C++
    # WarmAutoconvParams::ncmin_tensor / runtime.cpp:273). None → scalar `ncmin` fallback.
    ncmin_tensor: "torch.Tensor | None" = None


def default_warm_autoconv_params(*, den0: float = DEFAULT_DEN0,
                                 peaut=None) -> WarmAutoconvParams:
    """`kdm6init`의 qck1 + 운영 ncmin 기본값.

    Derivation (Fortran kdm6init line ~3106):
        qck1 = .104 * 9.8 * peaut / denr^(1/3) / xmyu * den0^(4/3)
    `den0`은 kdm6init의 INPUT 인자라 외부에서 들어옴 — 표준대기 1.28 fallback.
    """
    # STEP-91 SEED mirror: kdm6init F:3138 builds qck1 REAL(4) l2r with f32 powf.
    if peaut is None:
        qck1 = _fc._f32(_fc._f32(_fc._f32(_fc._f32(_fc._f32(_fc._f32(0.104) * _fc._f32(9.8)) * _fc._f32(c.PEAUT))
            / _fc.powf(c.DENR, 1.0 / 3.0)) / _fc._f32(c.XMYU)) * _fc.powf(den0, 4.0 / 3.0))
    else:
        # G4 파라미터 경로: 같은 f32-stepwise 체인을 텐서-안전 캐스트(_f32t)로 —
        # 값은 스칼라 경로와 IEEE 동일, grad는 peaut leaf까지 관통.
        qck1 = _fc._f32t(_fc._f32t(_fc._f32t(_fc._f32t(
            _fc._f32(_fc._f32(0.104) * _fc._f32(9.8)) * _fc._f32t(peaut))
            / _fc.powf(c.DENR, 1.0 / 3.0)) / _fc._f32(c.XMYU)) * _fc.powf(den0, 4.0 / 3.0))
    return WarmAutoconvParams(
        qck1=qck1,
        nraut_coeff=3.5e9,
        qcrmin=c.QCRMIN,
        ncmin=c.NCMIN,
    )


def autoconv_torch(
    qc: torch.Tensor,    # qci(:,:,1) cloud water mixing ratio [kg/kg]
    nc: torch.Tensor,    # nci(:,:,1) cloud number conc [#/m³ * scaling]
    qr: torch.Tensor,    # qrs(:,:,1) rain water mixing ratio
    nr: torch.Tensor,    # nrs(:,:,1) rain number conc
    den: torch.Tensor,
    qcr: torch.Tensor,   # critical cloud water threshold (sea/land 진단됨, 외부 입력)
    lenconcr: torch.Tensor,  # critical lencon (autoconv→accretion swap point)
    *,
    params: WarmAutoconvParams,
    dtcld: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Fortran 1706-1717 직역 — cloud→rain autoconversion (mass + number).

    Process
    -------
    if qc > qcr AND nc > ncmin:
        praut = qck1 * qc^(7/3) * nc^(-1/3)
        praut = min(praut, qc/dtcld)         # mass conservation
        nraut = nraut_coeff * den * praut    # default
        if qr > lenconcr:
            nraut = (nr/qr) * praut          # rain-pop-weighted
        nraut = min(nraut, nc/dtcld)
    else:
        praut, nraut = 0, 0

    Returns
    -------
    (praut, nraut) : (B, K) tensors. Mass and number autoconversion rates [kg/kg/s, #/s].
    """
    # ── 외부 게이트 ──────────────────────────────────────────────────────
    # per-cell ncmin (xland operational path) overrides the scalar when present (mirrors C++).
    nc_floor = params.ncmin_tensor if params.ncmin_tensor is not None else params.ncmin
    active = (qc > qcr) & (nc > nc_floor)
    zero = torch.zeros_like(qc)

    # ── praut: mass autoconversion ─────────────────────────────────────
    # qc^(7/3): 양수 power, base가 0이면 0 (안전). 그래도 EPS clamp.
    # nc^(-1/3): 음수 exponent — base 0에서 inf. 외부 게이트로 보호되지만 safe_pow.
    qc_term = safe_pow(qc, 7.0 / 3.0)
    nc_term = safe_pow(nc, -1.0 / 3.0)
    praut_raw = params.qck1 * qc_term * nc_term

    # min(praut, qc/dtcld): mass 보존
    qc_per_dt = qc / dtcld
    praut_capped = torch.minimum(praut_raw, qc_per_dt)
    praut = torch.where(active, praut_capped, zero)

    # ── nraut: number autoconversion ───────────────────────────────────
    nraut_default = params.nraut_coeff * den * praut
    # if qr > lenconcr: rain-population-weighted swap
    rain_swap = qr > lenconcr
    nraut_swap = safe_div_pos(nr, qr) * praut
    nraut_unswap = torch.where(rain_swap, nraut_swap, nraut_default)

    # min(nraut, nc/dtcld): number 보존
    nc_per_dt = nc / dtcld
    nraut_capped = torch.minimum(nraut_unswap, nc_per_dt)
    nraut = torch.where(active, nraut_capped, zero)

    return praut, nraut


# ─── Step B2: Accretion of cloud water by rain (pracw + nracw) ───────────────


class WarmAccretionParams(NamedTuple):
    """Fortran kdm6init이 accretion에 넘기는 시간불변 스칼라.

    Cloud DSD shape muc=2 ⇒ muc1=4/3, muc3=2, muc6=3, muc9=4.
    Rain DSD shape mur=1 ⇒ mur1=2, mur4=5, mur7=8.
    """

    ncrk1: float
    ncrk2: float
    cmc: float        # pi * denr / 6
    g3pmc: float      # rgmma(1 + 3/(muc+1))
    g6pmc: float      # rgmma(1 + 6/(muc+1))
    g9pmc: float      # rgmma(1 + 9/(muc+1))
    g1pmr: float      # rgmma(1 + mur)
    g4pmr: float      # rgmma(4 + mur)
    g7pmr: float      # rgmma(7 + mur)
    di100: float


def default_warm_accretion_params(*, ncrk1=None, ncrk2=None) -> WarmAccretionParams:
    """`kdm6init`의 cloud/rain gamma family 직역.

    원본 (Fortran kdm6init:3128-3149):
        muc1 = 1+1/(muc+1);  g1pmc = rgmma(muc1)
        muc3 = 1+3/(muc+1);  g3pmc = rgmma(muc3)   ...
        mur1 = 1+mur;        g1pmr = rgmma(mur1)
        mur4 = 4+mur;        g4pmr = rgmma(mur4)   ...
    """
    cmc = _pi * c.DENR / 6.0

    g3pmc = _rgmma(1.0 + 3.0 / (c.MUC + 1.0))
    g6pmc = _rgmma(1.0 + 6.0 / (c.MUC + 1.0))
    g9pmc = _rgmma(1.0 + 9.0 / (c.MUC + 1.0))

    g1pmr = _rgmma(1.0 + c.MUR)
    g4pmr = _rgmma(4.0 + c.MUR)
    g7pmr = _rgmma(7.0 + c.MUR)

    return WarmAccretionParams(
        ncrk1=c.NCRK1 if ncrk1 is None else ncrk1,
        ncrk2=c.NCRK2 if ncrk2 is None else ncrk2,
        cmc=cmc,
        g3pmc=g3pmc,
        g6pmc=g6pmc,
        g9pmc=g9pmc,
        g1pmr=g1pmr,
        g4pmr=g4pmr,
        g7pmr=g7pmr,
        di100=c.DI100,
    )


def accretion_torch(
    qc: torch.Tensor,
    nc: torch.Tensor,
    qr: torch.Tensor,
    nr: torch.Tensor,
    den: torch.Tensor,
    avedia_r: torch.Tensor,    # rain mean diameter [m] (외부 진단)
    rslopec3: torch.Tensor,    # cloud rslope^3 (외부 진단)
    rslope3_r: torch.Tensor,   # rain rslope^3 (slope_kdm6_torch.rslope3_r)
    lenconcr: torch.Tensor,    # critical lencon (외부 진단)
    *,
    params: WarmAccretionParams,
    dtcld: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Fortran 1724-1742 — accretion of cloud water by rain (mass + number).

    Two-mode collection kernel based on rain mean diameter (Cohard-Pinty 2000):
      - mode 1 (avedia_r >= di100=100 µm): big-drop kernel using ncrk1
      - mode 2 (avedia_r <  di100):        small-drop kernel using ncrk2

    Outer gate: qr >= lenconcr (rain not yet "swap point" → accretion off).

    Returns
    -------
    (pracw, nracw) : mass and number accretion rates [kg/kg/s, #/s].
    """
    rain_active = qr >= lenconcr
    zero = torch.zeros_like(qc)

    # 외부 게이트 안에서 분기. 분모 보호: den > 0 가정 (atmosphere physical).
    cmc_over_den = params.cmc / torch.clamp(den, min=c.QCRMIN)
    g4pmr_over_g1pmr = params.g4pmr / params.g1pmr
    g7pmr_over_g1pmr = params.g7pmr / params.g1pmr

    # Mode 1 (big drops): avedia_r >= di100
    pracw_mode1 = (
        cmc_over_den * params.ncrk1 * nc * nr * rslopec3
        * (rslopec3 * params.g6pmc + rslope3_r * params.g3pmc * g4pmr_over_g1pmr)
    )
    nracw_mode1 = (
        params.ncrk1 * nc * nr
        * (rslopec3 * params.g3pmc + rslope3_r * g4pmr_over_g1pmr)
    )

    # Mode 2 (small drops): avedia_r < di100
    pracw_mode2 = (
        cmc_over_den * params.ncrk2 * nc * nr * rslopec3
        * (rslopec3 * rslopec3 * params.g9pmc
           + rslope3_r * rslope3_r * params.g3pmc * g7pmr_over_g1pmr)
    )
    nracw_mode2 = (
        params.ncrk2 * nc * nr
        * (rslopec3 * rslopec3 * params.g6pmc + rslope3_r * rslope3_r)
        * g7pmr_over_g1pmr
    )

    # Mode branch: avedia_r >= di100 → mode1, else mode2.
    # 이건 *물리* 분기 (두 다른 collection regime). cliff at di100 — 향후 sigmoid
    # blend로 매끄럽게 할지 사용자 결정 (branch-semantics-physical-vs-numerical 참조).
    big_drop = avedia_r >= params.di100
    pracw_raw = torch.where(big_drop, pracw_mode1, pracw_mode2)
    nracw_raw = torch.where(big_drop, nracw_mode1, nracw_mode2)

    # Mass/number conservation cap
    pracw_capped = torch.minimum(pracw_raw, qc / dtcld)
    nracw_capped = torch.minimum(nracw_raw, nc / dtcld)

    pracw = torch.where(rain_active, pracw_capped, zero)
    nracw = torch.where(rain_active, nracw_capped, zero)

    return pracw, nracw


# ─── Step B3: Self-collection (nccol + nrcol) ────────────────────────────────


class WarmSelfCollectionParams(NamedTuple):
    """nccol/nrcol 분기에 필요한 시간불변 스칼라."""

    ncrk1: float
    ncrk2: float
    eccbrk: float
    g3pmc: float
    g6pmc: float
    g1pmr: float
    g4pmr: float
    g7pmr: float
    di100: float
    di600: float
    di2000: float


def default_warm_self_collection_params(*, ncrk1=None, ncrk2=None,
                                        eccbrk=None) -> WarmSelfCollectionParams:
    g3pmc = _rgmma(1.0 + 3.0 / (c.MUC + 1.0))
    g6pmc = _rgmma(1.0 + 6.0 / (c.MUC + 1.0))
    g1pmr = _rgmma(1.0 + c.MUR)
    g4pmr = _rgmma(4.0 + c.MUR)
    g7pmr = _rgmma(7.0 + c.MUR)

    return WarmSelfCollectionParams(
        ncrk1=c.NCRK1 if ncrk1 is None else ncrk1,
        ncrk2=c.NCRK2 if ncrk2 is None else ncrk2,
        eccbrk=c.ECCBRK if eccbrk is None else eccbrk,
        g3pmc=g3pmc,
        g6pmc=g6pmc,
        g1pmr=g1pmr,
        g4pmr=g4pmr,
        g7pmr=g7pmr,
        di100=c.DI100,
        di600=c.DI600,
        di2000=c.DI2000,
    )


def self_collection_torch(
    nc: torch.Tensor,
    nr: torch.Tensor,
    qr: torch.Tensor,
    avedia_c: torch.Tensor,    # cloud mean diameter (외부 진단)
    avedia_r: torch.Tensor,    # rain mean diameter (외부 진단)
    rslopec3: torch.Tensor,
    rslope3_r: torch.Tensor,
    lenconcr: torch.Tensor,
    *,
    params: WarmSelfCollectionParams,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Fortran 1747-1774 — cloud and rain self-collection.

    nccol (1747-1754): cloud self-collection — 2-mode by avedia_c >= di100.
    nrcol (1759-1774): rain self-collection + break-up — 4-mode by avedia_r:
      - avedia_r < di100              : ncrk2 small-drop kernel
      - di100 <= avedia_r < di600     : ncrk1 medium-drop kernel
      - di600 <= avedia_r < di2000    : exp(-2.5e3*eccbrk*(avedia_r-di600)) damping (break-up)
      - avedia_r >= di2000            : 0 (complete break-up)
    Outer gate for nrcol: qr >= lenconcr.

    Note: nccol is *unbounded* by qr; cloud self-collection happens whenever
    cloud water exists. nrcol gated by rain population.
    """
    zero = torch.zeros_like(nc)

    # ── nccol: cloud self-collection (2-mode) ───────────────────────────
    nccol_big = params.ncrk1 * nc * nc * rslopec3 * params.g3pmc
    nccol_small = params.ncrk2 * nc * nc * rslopec3 * rslopec3 * params.g6pmc
    big_cloud = avedia_c >= params.di100
    nccol = torch.where(big_cloud, nccol_big, nccol_small)

    # ── nrcol: rain self-collection + break-up (4-mode) ─────────────────
    g4pmr_over_g1pmr = params.g4pmr / params.g1pmr
    g7pmr_over_g1pmr = params.g7pmr / params.g1pmr

    # Mode small (avedia_r < di100)
    nrcol_small = (
        params.ncrk2 * nr * nr * rslope3_r * rslope3_r * g7pmr_over_g1pmr
    )
    # Mode medium (di100 <= avedia_r < di600)
    nrcol_medium = params.ncrk1 * nr * nr * rslope3_r * g4pmr_over_g1pmr
    # Mode breakup (di600 <= avedia_r < di2000)
    coecol = -2.5e3 * params.eccbrk * (avedia_r - params.di600)
    nrcol_breakup = torch.exp(coecol) * params.ncrk1 * nr * nr * rslope3_r * g4pmr_over_g1pmr

    # Nested where: small | medium | breakup | zero
    is_small = avedia_r < params.di100
    is_medium = (avedia_r >= params.di100) & (avedia_r < params.di600)
    is_breakup = (avedia_r >= params.di600) & (avedia_r < params.di2000)

    nrcol_raw = torch.where(
        is_small, nrcol_small,
        torch.where(
            is_medium, nrcol_medium,
            torch.where(is_breakup, nrcol_breakup, zero)
        )
    )

    rain_active = qr >= lenconcr
    nrcol = torch.where(rain_active, nrcol_raw, zero)

    return nccol, nrcol


# ─── Step B4: Rain evaporation / condensation (prevp) ────────────────────────


class WarmRainEvapParams(NamedTuple):
    """prevp 산출에 필요한 시간불변 스칼라.

    Derivations (Fortran kdm6init:3190-3200):
        g2pmr   = rgmma(2 + mur)              # rain gamma at 2+mur
        bvtr3o5 = 2.5 + 0.5*bvtr + mur
        g7pbro2 = rgmma(bvtr3o5)
        precr1  = 2*pi*0.78*g2pmr
        precr2  = 2*pi*0.31*sqrt(avtr)*g7pbro2
    """

    precr1: float
    precr2: float
    fac_evap: float


def default_warm_rain_evap_params(*, fac_evap: float = 1.0) -> WarmRainEvapParams:
    """Fortran kdm6init의 precr1/precr2 직역. fac_evap=1.0은 yhlee 변경값."""
    mur = c.MUR
    bvtr = c.BVTR
    avtr = c.AVTR

    g2pmr = _rgmma(2.0 + mur)
    g7pbro2 = _rgmma(2.5 + 0.5 * bvtr + mur)

    precr1 = 2.0 * _pi * 0.78 * g2pmr
    # Fortran F:3269 precr2 = 2.*pi*.31*avtr**.5*g7pbro2 REAL(f32-stepwise); avtr**.5 is REAL**REAL
    # => libm POWF (not f64 pow). f64 pow->f32 differs 1 ULP. f32-stepwise + _fc.powf (mirror C++).
    precr2 = _fc._f32(_fc._f32(_fc._f32(_fc._f32(2.0 * _fc._f32(_pi)) * 0.31) * _fc.powf(avtr, 0.5)) * g7pbro2)

    return WarmRainEvapParams(
        precr1=precr1,
        precr2=precr2,
        fac_evap=fac_evap,
    )


def rain_evap_torch(
    qr: torch.Tensor,
    rh_w: torch.Tensor,             # relative humidity w.r.t. water [-] (외부 진단)
    supsat: torch.Tensor,           # supsat = q - qs(:,:,1) [kg/kg] (외부 진단)
    n0r: torch.Tensor,              # rain intercept [m^-4] (외부 진단)
    work1_r: torch.Tensor,          # work1(:,:,1) (외부 진단)
    work2: torch.Tensor,            # ventilation factor venfac(p,t,den) (외부 진단)
    rslope_r: torch.Tensor,         # slope_kdm6_torch.rslope_r
    rslopeb_r: torch.Tensor,        # slope_kdm6_torch.rslopeb_r
    rslope2_r: torch.Tensor,        # slope_kdm6_torch.rslope2_r
    rslopemu_r: torch.Tensor,       # slope_kdm6_torch.rslopemu_r
    *,
    params: WarmRainEvapParams,
    dtcld: float,
    return_complete_evap: bool = False,
) -> "torch.Tensor | tuple[torch.Tensor, torch.Tensor]":
    """Fortran 1779-1801 — rain evaporation/condensation (mass rate).

    prevp < 0 (rh<1, evaporation): qr→qv. capped by -qr/dtcld and satdt/2.
    prevp > 0 (rh>1, rare condensation): qv→qr. capped by satdt/2.

    Note: nrevp(number rate) and complete-evap CCN transfer (Fortran 1794-1797)는
    *state mutation*이므로 caller가 mass-cap hit 검사 후 처리. 본 함수는 prevp만 산출.

    Returns
    -------
    prevp : (B, K) tensor [kg/kg/s]
    """
    zero = torch.zeros_like(qr)
    active = qr > 0.0

    # ── coeres = rslope2 * sqrt(rslope*rslopeb) * rslopemu ─────────────
    # rslope*rslopeb 양수 보장 (slope module). 안전상 EPS clamp.
    sqrt_arg = torch.clamp(rslope_r * rslopeb_r, min=c.QCRMIN)
    coeres = rslope2_r * torch.sqrt(sqrt_arg) * rslopemu_r

    # ── prevp_raw = (rh-1) * n0r * (precr1 * rslope2 * rslopemu
    #                                + precr2 * work2 * coeres) / work1
    # work1은 capacitance/conductance 합산. 양수 보장 (외부 진단). safe div.
    work1_safe = torch.clamp(work1_r, min=c.QCRMIN)
    bracket = params.precr1 * rslope2_r * rslopemu_r + params.precr2 * work2 * coeres
    prevp_raw = (rh_w - 1.0) * n0r * bracket / work1_safe
    prevp_raw = params.fac_evap * prevp_raw

    # ── 부호 분기: 음수(evap) vs 양수(cond) ────────────────────────────
    satdt = supsat / dtcld
    half_satdt = 0.5 * satdt

    # Evaporation path (prevp < 0):
    #   prevp = max(prevp, -qr/dtcld)   # cap by available mass
    #   prevp = max(prevp, satdt/2)     # cap by half saturation deficit
    qr_cap = -qr / dtcld
    prevp_evap = torch.maximum(prevp_raw, qr_cap)
    prevp_evap = torch.maximum(prevp_evap, half_satdt)

    # Condensation path (prevp >= 0):
    #   prevp = min(prevp, satdt/2)
    prevp_cond = torch.minimum(prevp_raw, half_satdt)

    is_evap = prevp_raw < 0
    prevp_capped = torch.where(is_evap, prevp_evap, prevp_cond)
    prevp = torch.where(active, prevp_capped, zero)
    if return_complete_evap:
        # Fortran 1794-1797 / C++ warm.cpp:281: rain fully evaporated (prevp hit -qr/dtcld
        # cap) ⇒ NR → NCCN. Mask = active & is_evap & (prevp == qr_cap).
        rain_complete_evap = active & is_evap & (prevp == qr_cap)
        return prevp, rain_complete_evap
    return prevp


__all__ = [
    "WarmAutoconvParams",
    "WarmAccretionParams",
    "WarmSelfCollectionParams",
    "WarmRainEvapParams",
    "default_warm_autoconv_params",
    "default_warm_accretion_params",
    "default_warm_self_collection_params",
    "default_warm_rain_evap_params",
    "autoconv_torch",
    "accretion_torch",
    "self_collection_torch",
    "rain_evap_torch",
]
