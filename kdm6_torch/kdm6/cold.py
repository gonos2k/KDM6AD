"""
KDM6 cold rain processes — ice phase microphysics oracle.

원본: module_mp_kdm6.F: 1843-2440 (Step C 영역)

본 모듈은 Step C의 sub-step을 누적 추가한다 (warm.py 패턴 답습):
  - C1 (현재): ice mass accretion         — `ice_accretion_torch`        (1843-1862)
  - C2:        ice→snow/graupel mass      — `ice_to_snow_graupel_torch`  (1868-1890)
  - C2b:       number accretion           — `ice_number_accretion_torch` (1897-1944)
  - C2c:       cloud water riming         — `cloud_water_riming_torch`   (1951-2031)
  - C2d:       rain-snow-graupel coll     — `rain_snow_graupel_coll_torch` (2051-2150)
  - C2e:       Hallett-Mossop mult        — `halmos_multiplication_torch` (2154-2248)
  - C3:        ice nucleation (pinud)     — `ice_nucleation_torch`       (2309-2326)
  - C4:        deposition/sublimation     — `dep_sub_torch`              (2334-2390)
  - C5:        aggregation (psaut)        — `ice_aggregation_torch`      (2393-2406)
  - C6:        snow evap (psevp)          — `snow_evap_torch`            (2424-2429)
  - C6':       graupel evap (pgevp)       — `graupel_evap_torch`         (2435-2440)

상위 호출자 `kdm62D`는 C1-C6 + B series를 같은 do-loop 안에서 호출하지만, 본
oracle은 *순수함수*로 분리해 testability와 미분 가능성을 확보한다.

AD 가이드:
  - 외부 게이트 `qci > qmin AND qrs > qcrmin` (또는 유사) → branch zero
  - `min(rate, mass/dtcld)` 류 잘림 → torch.minimum (mass conservation)
  - Wilt collection efficiency reduction `min(max(0, ratio), 1)²` → 매끄러운 product
  - `abs(vt2 - vt2)` → 미분가능 (subgradient cliff at equality, 일반 관측 X)
"""
from __future__ import annotations

from math import exp, lgamma, pi as _pi
from typing import NamedTuple

import torch

from . import constants as c
from . import fconst as _fc


def _rgmma(x: float) -> float:
    """Fortran `rgmma(x) = exp(GAMMLN(x)) = Γ(x)` 직역. review6 audit에서 부호 수정."""
    # Fortran rgmma = f32 expf(f32 gammln) — differs from exp(lgamma) at non-integer args (step-67 class)
    return _fc.rgmma_f(x)


# ─── Step C1: Ice mass accretion (praci + piacr) ─────────────────────────────


class IceAccretionParams(NamedTuple):
    """Fortran kdm6init이 ice accretion에 넘기는 시간불변 스칼라.

    Rain shape (mur=1):
        g1pmr = rgmma(2),  g2pmr = rgmma(3),  g3pmr = rgmma(4)
        g1pdrmr = rgmma(1+dmr+mur),  g2pdrmr = rgmma(2+dmr+mur),  g3pdrmr = rgmma(3+dmr+mur)
    Ice shape (mui=0):
        g1pmi = rgmma(1),  g2pmi = rgmma(2),  g3pmi = rgmma(3)
        g1pdimi = rgmma(1+dmi+mui), g2pdimi = rgmma(2+dmi+mui), g3pdimi = rgmma(3+dmi+mui)
    """

    cmi: float    # pi * deni / 6
    cmr: float    # pi * denr / 6
    g1pmr: float
    g2pmr: float
    g3pmr: float
    g1pdimi: float
    g2pdimi: float
    g3pdimi: float
    g1pmi: float
    g2pmi: float
    g3pmi: float
    g1pdrmr: float
    g2pdrmr: float
    g3pdrmr: float
    eacri: float
    eacir: float
    qmin: float
    qcrmin: float


def default_ice_accretion_params() -> IceAccretionParams:
    cmi = _pi * c.DENI / 6.0
    cmr = _pi * c.DENR / 6.0

    # Rain gamma family (mur=1)
    g1pmr = _rgmma(1.0 + c.MUR)
    g2pmr = _rgmma(2.0 + c.MUR)
    g3pmr = _rgmma(3.0 + c.MUR)
    g1pdrmr = _rgmma(1.0 + c.DMR + c.MUR)
    g2pdrmr = _rgmma(2.0 + c.DMR + c.MUR)
    g3pdrmr = _rgmma(3.0 + c.DMR + c.MUR)

    # Ice gamma family (mui=0)
    g1pmi = 1.0 if c.MUI == 0.0 else _rgmma(1.0 + c.MUI)
    g2pmi = _rgmma(2.0 + c.MUI)
    g3pmi = _rgmma(3.0 + c.MUI)
    g1pdimi = _rgmma(1.0 + c.DMI + c.MUI)
    g2pdimi = _rgmma(2.0 + c.DMI + c.MUI)
    g3pdimi = _rgmma(3.0 + c.DMI + c.MUI)

    return IceAccretionParams(
        cmi=cmi, cmr=cmr,
        g1pmr=g1pmr, g2pmr=g2pmr, g3pmr=g3pmr,
        g1pdimi=g1pdimi, g2pdimi=g2pdimi, g3pdimi=g3pdimi,
        g1pmi=g1pmi, g2pmi=g2pmi, g3pmi=g3pmi,
        g1pdrmr=g1pdrmr, g2pdrmr=g2pdrmr, g3pdrmr=g3pdrmr,
        eacri=c.EACRI,
        eacir=c.EACIR,
        qmin=c.EPS,          # GATE threshold = Fortran qmin=1e-15; div-safety clamps use qcrmin. 1:1 fix #13-17
        qcrmin=c.QCRMIN,
    )


def _wilt_reduction(ratio: torch.Tensor) -> torch.Tensor:
    """Wilt collection efficiency reduction: `min(max(0, ratio), 1)²`.

    Fortran 1846/1861 — collected/collector mass-ratio 의존 감쇠. 매끄러운 product
    이므로 `torch.clamp(min=0, max=1)`로 단순 직역. AD 안전.
    """
    return torch.clamp(ratio, min=0.0, max=1.0) ** 2


def ice_accretion_torch(
    qi: torch.Tensor,           # qci(:,:,2) cloud ice mixing ratio
    qr: torch.Tensor,           # qrs(:,:,1) rain mixing ratio
    den: torch.Tensor,
    n0i: torch.Tensor,          # ice intercept (외부 진단)
    n0r: torch.Tensor,          # rain intercept (외부 진단)
    vt2r: torch.Tensor,         # rain terminal velocity (slope * denfac)
    vt2i: torch.Tensor,         # ice  terminal velocity
    rslope_r: torch.Tensor,     # slope_kdm6_torch.rslope_r
    rslope2_r: torch.Tensor,
    rslope3_r: torch.Tensor,
    rslopemu_r: torch.Tensor,
    rsloped_r: torch.Tensor,
    rslope_i: torch.Tensor,     # ice (slope_kdm6_torch.rslope_i)
    rslope2_i: torch.Tensor,
    rslope3_i: torch.Tensor,
    rslopemu_i: torch.Tensor,
    rsloped_i: torch.Tensor,
    *,
    params: IceAccretionParams,
    dtcld: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Fortran 1843-1862 — ice ↔ rain mass accretion.

    praci: Cloud ice + rain → rain (HL A15, LFO 25). T<T0.
    piacr: Rain + cloud ice → snow/graupel (HL A19, LFO 26). T<T0.

    Outer gate (Fortran 1837): qi > qmin AND qr > qcrmin.
    Wilt collection eff reduction (1846, 1861): min(max(0, ratio), 1)².
    Mass cap (1847, 1862): min(rate, source_mass/dtcld).

    Returns
    -------
    (praci, piacr) : (B, K) tensors [kg/kg/s].
    """
    active = (qi > params.qmin) & (qr > params.qcrmin)
    zero = torch.zeros_like(qi)

    # 분기 안에서 division 보호 (실제론 active mask 안에서만 의미있음)
    den_safe = torch.clamp(den, min=params.qcrmin)
    qi_safe = torch.clamp(qi, min=params.qcrmin)
    qr_safe = torch.clamp(qr, min=params.qcrmin)

    # ── praci: Cloud ice collected by rain ──────────────────────────────
    # acrfac = g3pmr·rslopemu_r·rslope3_r·g1pdimi·rsloped_i·rslopemu_i·rslope_i
    #        + 2·g2pmr·rslopemu_r·rslope2_r·g2pdimi·rsloped_i·rslopemu_i·rslope2_i
    #        + g1pmr·rslopemu_r·rslope_r ·g3pdimi·rsloped_i·rslopemu_i·rslope3_i
    common_i = rsloped_i * rslopemu_i  # 공통 ice factor
    acrfac_pr = (
        params.g3pmr * rslopemu_r * rslope3_r * params.g1pdimi * common_i * rslope_i
        + 2.0 * params.g2pmr * rslopemu_r * rslope2_r * params.g2pdimi * common_i * rslope2_i
        + params.g1pmr * rslopemu_r * rslope_r * params.g3pdimi * common_i * rslope3_i
    )
    praci_raw = (
        _pi * params.cmi * n0i * n0r * torch.abs(vt2r - vt2i) / (4.0 * den_safe)
        * acrfac_pr * params.eacri
    )
    praci_wilt = praci_raw * _wilt_reduction(qr_safe / qi_safe)
    praci_capped = torch.minimum(praci_wilt, qi / dtcld)
    praci = torch.where(active, praci_capped, zero)

    # ── piacr: Rain collected by cloud ice ──────────────────────────────
    common_r = rsloped_r * rslopemu_r  # 공통 rain factor
    acrfac_pi = (
        params.g3pmi * rslopemu_i * rslope3_i * params.g1pdrmr * common_r * rslope_r
        + 2.0 * params.g2pmi * rslopemu_i * rslope2_i * params.g2pdrmr * common_r * rslope2_r
        + params.g1pmi * rslopemu_i * rslope_i * params.g3pdrmr * common_r * rslope3_r
    )
    piacr_raw = (
        _pi * params.cmr * n0i * n0r * torch.abs(vt2i - vt2r) / (4.0 * den_safe)
        * acrfac_pi * params.eacir
    )
    piacr_wilt = piacr_raw * _wilt_reduction(qi_safe / qr_safe)
    piacr_capped = torch.minimum(piacr_wilt, qr / dtcld)
    piacr = torch.where(active, piacr_capped, zero)

    return praci, piacr


# ─── Step C2: Ice → snow / graupel mass accretion (psaci + pgaci) ────────────


class IceToSnowGraupelParams(NamedTuple):
    """psaci + pgaci 계산에 필요한 시간불변 스칼라.

    Snow shape (mus=0):  g1pms=1 (short-circuit), g2pms=rgmma(2)=1, g3pms=rgmma(3)=0.5
    Graupel shape (mug=0): g1pmg=1, g2pmg=1, g3pmg=0.5
    Ice shape (mui=0):   g1pdimi=rgmma(1+dmi+mui), etc.

    Note: `eacsi` (snow→ice) and `eacgi` (graupel→ice) collection efficiencies
    are *runtime supcol-dependent* in Fortran (1826, 1882) — both share the
    same formula `exp(clamp(0.07·(-supcol), [-80, 80]))`. Computed via
    `_exp_eac_from_supcol` helper, NOT in params.
    """

    cmi: float
    g1pms: float
    g2pms: float
    g3pms: float
    g1pmg: float
    g2pmg: float
    g3pmg: float
    g1pdimi: float
    g2pdimi: float
    g3pdimi: float
    qmin: float
    qcrmin: float


def default_ice_to_snow_graupel_params() -> IceToSnowGraupelParams:
    g1pms = 1.0 if c.MUS == 0.0 else _rgmma(1.0 + c.MUS)
    g2pms = _rgmma(2.0 + c.MUS)
    g3pms = _rgmma(3.0 + c.MUS)
    g1pmg = 1.0 if c.MUG == 0.0 else _rgmma(1.0 + c.MUG)
    g2pmg = _rgmma(2.0 + c.MUG)
    g3pmg = _rgmma(3.0 + c.MUG)
    g1pdimi = _rgmma(1.0 + c.DMI + c.MUI)
    g2pdimi = _rgmma(2.0 + c.DMI + c.MUI)
    g3pdimi = _rgmma(3.0 + c.DMI + c.MUI)
    cmi = _pi * c.DENI / 6.0

    return IceToSnowGraupelParams(
        cmi=cmi,
        g1pms=g1pms, g2pms=g2pms, g3pms=g3pms,
        g1pmg=g1pmg, g2pmg=g2pmg, g3pmg=g3pmg,
        g1pdimi=g1pdimi, g2pdimi=g2pdimi, g3pdimi=g3pdimi,
        qmin=c.EPS,          # GATE threshold = Fortran qmin=1e-15; div-safety clamps use qcrmin. 1:1 fix #13-17
        qcrmin=c.QCRMIN,
    )


def _exp_eac_from_supcol(supcol: torch.Tensor) -> torch.Tensor:
    """Fortran 1826 (eacsi) / 1882 (eacgi): `exp(clamp(0.07·(-supcol), [-80, 80]))`.

    Note (counter-intuitive direction): supcol > 0 (cold) → arg < 0 → eacXi < 1.
    Warm (supcol → 0) → eacXi → 1. Very cold limit → eacXi → 0. This is
    Fortran 산식의 *그대로의 직역*; 물리 직관(cold일수록 sticky ice → 큰 eff)과 반대.
    운영 시 의도가 다르면 사용자 검증 필요.
    """
    arg = torch.clamp(0.07 * (-supcol), min=-80.0, max=80.0)
    return torch.exp(arg)


def ice_to_snow_graupel_torch(
    qi: torch.Tensor,
    qs: torch.Tensor,           # qrs(:,:,2) snow
    qg: torch.Tensor,           # qrs(:,:,3) graupel
    den: torch.Tensor,
    n0i: torch.Tensor,
    n0so: torch.Tensor,         # snow intercept (외부 진단)
    n0go: torch.Tensor,         # graupel intercept (외부 진단)
    n0sfac: torch.Tensor,       # T-dependent snow intercept multiplier
    supcol: torch.Tensor,       # T0c - T (cold positive)
    vt2s: torch.Tensor,
    vt2g: torch.Tensor,
    vt2i: torch.Tensor,
    rslope_s: torch.Tensor,
    rslope2_s: torch.Tensor,
    rslope3_s: torch.Tensor,
    rslopemu_s: torch.Tensor,
    rslope_g: torch.Tensor,
    rslope2_g: torch.Tensor,
    rslope3_g: torch.Tensor,
    rslopemu_g: torch.Tensor,
    rslope_i: torch.Tensor,
    rslope2_i: torch.Tensor,
    rslope3_i: torch.Tensor,
    rslopemu_i: torch.Tensor,
    rsloped_i: torch.Tensor,
    *,
    params: IceToSnowGraupelParams,
    dtcld: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Fortran 1868-1890 — cloud ice ←collected by→ snow & graupel.

    psaci (HDC 10): qs > qcrmin AND qi > qmin → ice → snow
    pgaci (HL A17, LFO 41): qg > qcrmin AND qi > qmin → ice → graupel
    pgaci uses runtime `eacgi = exp(clamp(0.07·(-supcol), [-80, 80]))`.

    Returns
    -------
    (psaci, pgaci) : (B, K) tensors [kg/kg/s].
    """
    zero = torch.zeros_like(qi)
    den_safe = torch.clamp(den, min=params.qcrmin)
    qi_safe = torch.clamp(qi, min=params.qcrmin)
    qs_safe = torch.clamp(qs, min=params.qcrmin)
    qg_safe = torch.clamp(qg, min=params.qcrmin)
    common_i = rsloped_i * rslopemu_i

    eac_temp = _exp_eac_from_supcol(supcol)  # Fortran 1826/1882 공통

    # ── psaci: snow collects cloud ice ──────────────────────────────────
    active_s = (qs > params.qcrmin) & (qi > params.qmin)
    acrfac_s = (
        params.g3pms * rslopemu_s * rslope3_s * params.g1pdimi * common_i * rslope_i
        + 2.0 * params.g2pms * rslopemu_s * rslope2_s * params.g2pdimi * common_i * rslope2_i
        + params.g1pms * rslopemu_s * rslope_s * params.g3pdimi * common_i * rslope3_i
    )
    psaci_raw = (
        _pi * params.cmi * n0i * n0so * n0sfac * torch.abs(vt2s - vt2i)
        / (4.0 * den_safe) * acrfac_s * eac_temp
    )
    psaci_wilt = psaci_raw * _wilt_reduction(qs_safe / qi_safe)
    psaci_capped = torch.minimum(psaci_wilt, qi / dtcld)
    psaci = torch.where(active_s, psaci_capped, zero)

    # ── pgaci: graupel collects cloud ice ───────────────────────────────
    active_g = (qg > params.qcrmin) & (qi > params.qmin)
    eacgi = eac_temp  # Fortran 1882 — same formula as eacsi
    acrfac_g = (
        params.g3pmg * rslopemu_g * rslope3_g * params.g1pdimi * common_i * rslope_i
        + 2.0 * params.g2pmg * rslopemu_g * rslope2_g * params.g2pdimi * common_i * rslope2_i
        + params.g1pmg * rslopemu_g * rslope_g * params.g3pdimi * common_i * rslope3_i
    )
    pgaci_raw = (
        _pi * params.cmi * n0i * n0go * torch.abs(vt2g - vt2i)
        / (4.0 * den_safe) * acrfac_g * eacgi
    )
    pgaci_wilt = pgaci_raw * _wilt_reduction(qg_safe / qi_safe)
    pgaci_capped = torch.minimum(pgaci_wilt, qi / dtcld)
    pgaci = torch.where(active_g, pgaci_capped, zero)

    return psaci, pgaci


# ─── Step C2b: Number accretion (nraci + niacr + nsaci + ngaci) ──────────────


class NumberAccretionParams(NamedTuple):
    """C2b 4 process 공유 시간불변 스칼라.

    각 process의 acrfac 3-term은 collection-direction의 species rslope*g_pm 곱과
    target의 g_pm·rslope^k의 합. 즉 mass-side(C1/C2) 와 달리 *_dimi/dimr factor가
    빠짐 — number kernel.
    """

    g1pmr: float
    g2pmr: float
    g3pmr: float
    g1pmi: float
    g2pmi: float
    g3pmi: float
    g1pms: float
    g2pms: float
    g3pms: float
    g1pmg: float
    g2pmg: float
    g3pmg: float
    eacri: float
    eacir: float
    n0s_const: float    # N0S (Fortran nsaci uses n0s, not n0so)
    n0g_const: float    # N0G (Fortran ngaci uses n0g, not n0go)
    ncmin: float
    nrmin: float
    qcrmin: float
    # per-cell ncmin override (operational xland path; injected by _kdm6_pure, mirrors C++). None → scalar.
    ncmin_tensor: "torch.Tensor | None" = None


def default_number_accretion_params() -> NumberAccretionParams:
    g1pmr = _rgmma(1.0 + c.MUR)
    g2pmr = _rgmma(2.0 + c.MUR)
    g3pmr = _rgmma(3.0 + c.MUR)
    g1pmi = 1.0 if c.MUI == 0.0 else _rgmma(1.0 + c.MUI)
    g2pmi = _rgmma(2.0 + c.MUI)
    g3pmi = _rgmma(3.0 + c.MUI)
    g1pms = 1.0 if c.MUS == 0.0 else _rgmma(1.0 + c.MUS)
    g2pms = _rgmma(2.0 + c.MUS)
    g3pms = _rgmma(3.0 + c.MUS)
    g1pmg = 1.0 if c.MUG == 0.0 else _rgmma(1.0 + c.MUG)
    g2pmg = _rgmma(2.0 + c.MUG)
    g3pmg = _rgmma(3.0 + c.MUG)
    return NumberAccretionParams(
        g1pmr=g1pmr, g2pmr=g2pmr, g3pmr=g3pmr,
        g1pmi=g1pmi, g2pmi=g2pmi, g3pmi=g3pmi,
        g1pms=g1pms, g2pms=g2pms, g3pms=g3pms,
        g1pmg=g1pmg, g2pmg=g2pmg, g3pmg=g3pmg,
        eacri=c.EACRI, eacir=c.EACIR,
        n0s_const=c.N0S, n0g_const=c.N0G,
        ncmin=c.NCMIN, nrmin=c.NRMIN, qcrmin=c.QCRMIN,
    )


def number_accretion_torch(
    qi: torch.Tensor,
    qs: torch.Tensor,
    qg: torch.Tensor,
    qr: torch.Tensor,
    ni: torch.Tensor,
    nr: torch.Tensor,
    den: torch.Tensor,
    n0i: torch.Tensor,
    n0r: torch.Tensor,
    n0sfac: torch.Tensor,        # T-dependent multiplier for snow
    supcol: torch.Tensor,
    vt2r: torch.Tensor,
    vt2s: torch.Tensor,
    vt2g: torch.Tensor,
    vt2i: torch.Tensor,
    rslope_r: torch.Tensor,
    rslope2_r: torch.Tensor,
    rslope3_r: torch.Tensor,
    rslopemu_r: torch.Tensor,
    rslope_s: torch.Tensor,
    rslope2_s: torch.Tensor,
    rslope3_s: torch.Tensor,
    rslopemu_s: torch.Tensor,
    rslope_g: torch.Tensor,
    rslope2_g: torch.Tensor,
    rslope3_g: torch.Tensor,
    rslopemu_g: torch.Tensor,
    rslope_i: torch.Tensor,
    rslope2_i: torch.Tensor,
    rslope3_i: torch.Tensor,
    rslopemu_i: torch.Tensor,
    *,
    params: NumberAccretionParams,
    dtcld: float,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Fortran 1897-1944 — 4 number accretion processes.

    Outer gate (1897): supcol > 0 AND ni > ncmin (cold + sufficient ice number).
    Sub-gates:
      nraci/niacr: nr > nrmin
      nsaci:       qs > qcrmin
      ngaci:       qg > qcrmin

    eacsi/eacgi share `exp(clamp(0.07·(-supcol), [-80,80]))` (Fortran 1826/1937).

    Returns
    -------
    (nraci, niacr, nsaci, ngaci) : (B, K) tensors [#/s].
    """
    zero = torch.zeros_like(qi)

    # 공통 cold gate — per-cell ncmin (xland operational path) overrides scalar when present (C++ parity)
    nc_floor = params.ncmin_tensor if params.ncmin_tensor is not None else params.ncmin
    cold_active = (supcol > 0) & (ni > nc_floor)

    qi_safe = torch.clamp(qi, min=params.qcrmin)
    qr_safe = torch.clamp(qr, min=params.qcrmin)
    qs_safe = torch.clamp(qs, min=params.qcrmin)
    qg_safe = torch.clamp(qg, min=params.qcrmin)

    eac_temp = _exp_eac_from_supcol(supcol)

    # ── nraci: rain collects cloud ice (number) ─────────────────────────
    # acrfac: rain side (g_pmr, rslope*) × ice side (g_pmi, rslope^k_i)
    acrfac_nra = (
        params.g3pmr * rslopemu_r * rslope3_r * params.g1pmi * rslopemu_i * rslope_i
        + 2.0 * params.g2pmr * rslopemu_r * rslope2_r * params.g2pmi * rslopemu_i * rslope2_i
        + params.g1pmr * rslopemu_r * rslope_r * params.g3pmi * rslopemu_i * rslope3_i
    )
    nraci_raw = _pi * n0i * n0r * params.eacri * torch.abs(vt2r - vt2i) * acrfac_nra / 4.0
    nraci_wilt = nraci_raw * _wilt_reduction(qr_safe / qi_safe)
    nraci_capped = torch.minimum(nraci_wilt, ni / dtcld)
    rain_active = nr > params.nrmin
    nraci = torch.where(cold_active & rain_active, nraci_capped, zero)

    # ── niacr: cloud ice collects rain (number) ─────────────────────────
    acrfac_nia = (
        params.g3pmi * rslopemu_i * rslope3_i * params.g1pmr * rslopemu_r * rslope_r
        + 2.0 * params.g2pmi * rslopemu_i * rslope2_i * params.g2pmr * rslopemu_r * rslope2_r
        + params.g1pmi * rslopemu_i * rslope_i * params.g3pmr * rslopemu_r * rslope3_r
    )
    niacr_raw = _pi * n0i * n0r * params.eacir * torch.abs(vt2i - vt2r) * acrfac_nia / 4.0
    niacr_wilt = niacr_raw * _wilt_reduction(qi_safe / qr_safe)
    niacr_capped = torch.minimum(niacr_wilt, nr / dtcld)
    niacr = torch.where(cold_active & rain_active, niacr_capped, zero)

    # ── nsaci: snow collects cloud ice (number) ─────────────────────────
    acrfac_nsa = (
        params.g3pms * rslopemu_s * rslope3_s * params.g1pmi * rslopemu_i * rslope_i
        + 2.0 * params.g2pms * rslopemu_s * rslope2_s * params.g2pmi * rslopemu_i * rslope2_i
        + params.g1pms * rslopemu_s * rslope_s * params.g3pmi * rslopemu_i * rslope3_i
    )
    nsaci_raw = (
        _pi * n0i * params.n0s_const * n0sfac * eac_temp
        * torch.abs(vt2s - vt2i) * acrfac_nsa / 4.0
    )
    nsaci_wilt = nsaci_raw * _wilt_reduction(qs_safe / qi_safe)
    nsaci_capped = torch.minimum(nsaci_wilt, ni / dtcld)
    snow_active = qs > params.qcrmin
    nsaci = torch.where(cold_active & snow_active, nsaci_capped, zero)

    # ── ngaci: graupel collects cloud ice (number) ──────────────────────
    acrfac_nga = (
        params.g3pmg * rslopemu_g * rslope3_g * params.g1pmi * rslopemu_i * rslope_i
        + 2.0 * params.g2pmg * rslopemu_g * rslope2_g * params.g2pmi * rslopemu_i * rslope2_i
        + params.g1pmg * rslopemu_g * rslope_g * params.g3pmi * rslopemu_i * rslope3_i
    )
    ngaci_raw = (
        _pi * n0i * params.n0g_const * eac_temp
        * torch.abs(vt2g - vt2i) * acrfac_nga / 4.0
    )
    ngaci_wilt = ngaci_raw * _wilt_reduction(qg_safe / qi_safe)
    ngaci_capped = torch.minimum(ngaci_wilt, ni / dtcld)
    graupel_active = qg > params.qcrmin
    ngaci = torch.where(cold_active & graupel_active, ngaci_capped, zero)

    return nraci, niacr, nsaci, ngaci


# ─── Step C2c: Cloud water riming (8 processes) ──────────────────────────────


class CloudWaterRimingParams(NamedTuple):
    """psacw/nsacw/pgacw/ngacw/paacw/naacw/piacw/niacw 공유 시간불변 스칼라.

    bvts/bvti/bvtg는 species terminal-velocity exponent. avts/avti는 coefficient.
    `g3pbs = rgmma(3+bvts+mus)`, `g3pbi = rgmma(3+bvti+mui)`. graupel side는
    `g3pbg`이 *runtime tensor* (ProgB_param 출력) 이므로 params 외.
    """

    avts: float
    avti: float
    g3pbs: float
    g3pbi: float
    eacsc: float
    eacgc: float
    eacic: float
    muc: float
    di50: float
    qmin: float
    qcrmin: float
    ncmin: float
    qsum_floor: float
    # per-cell ncmin override (operational xland path; injected by _kdm6_pure, mirrors C++). None → scalar.
    ncmin_tensor: "torch.Tensor | None" = None


def default_cloud_water_riming_params() -> CloudWaterRimingParams:
    g3pbs = _rgmma(3.0 + c.BVTS + c.MUS)
    g3pbi = _rgmma(3.0 + c.BVTI + c.MUI)
    return CloudWaterRimingParams(
        avts=c.AVTS,
        avti=c.AVTI,
        g3pbs=g3pbs,
        g3pbi=g3pbi,
        eacsc=c.EACSC,
        eacgc=c.EACGC,
        eacic=c.EACIC,
        muc=c.MUC,
        di50=c.DI50,
        qmin=c.EPS,          # GATE threshold = Fortran qmin=1e-15; div-safety clamps use qcrmin. 1:1 fix #13-17
        qcrmin=c.QCRMIN,
        ncmin=c.NCMIN,
        qsum_floor=1.0e-15,
    )


class CloudWaterRimingOutputs(NamedTuple):
    """8 cloud water riming process rates."""
    psacw: torch.Tensor   # qc → qs (T<T0) or qc → qr (T>=T0)
    nsacw: torch.Tensor   # nc →
    pgacw: torch.Tensor   # qc → qg (T<T0) or qc → qr
    ngacw: torch.Tensor   # nc →
    paacw: torch.Tensor   # weighted average of psacw + pgacw
    naacw: torch.Tensor   # weighted average of nsacw + ngacw
    piacw: torch.Tensor   # qc → qi (T<T0, ice diameter ≥ di50)
    niacw: torch.Tensor   # nc → ni


def cloud_water_riming_torch(
    qc: torch.Tensor,
    nc: torch.Tensor,
    qs: torch.Tensor,
    qg: torch.Tensor,
    qi: torch.Tensor,
    den: torch.Tensor,
    denfac: torch.Tensor,
    n0so: torch.Tensor,
    n0go: torch.Tensor,
    n0i: torch.Tensor,
    n0c: torch.Tensor,
    n0sfac: torch.Tensor,
    avtg: torch.Tensor,           # graupel terminal-velocity coefficient (ProgB output)
    g3pbg: torch.Tensor,          # graupel rgmma(3+bvtg+mug) (ProgB output, runtime)
    avedia_i: torch.Tensor,       # ice mean diameter (avedia(:,:,3))
    supcol: torch.Tensor,
    rslope3_s: torch.Tensor,
    rslopeb_s: torch.Tensor,
    rslopemu_s: torch.Tensor,
    rslope3_g: torch.Tensor,
    rslopeb_g: torch.Tensor,
    rslopemu_g: torch.Tensor,
    rslope3_i: torch.Tensor,
    rslopeb_i: torch.Tensor,
    rslopemu_i: torch.Tensor,
    rslopec: torch.Tensor,
    rslopecmu: torch.Tensor,
    *,
    params: CloudWaterRimingParams,
    dtcld: float,
) -> CloudWaterRimingOutputs:
    """Fortran 1951-2031 — 8 cloud water riming processes.

    Process map:
      psacw, nsacw — snow rimes cloud water (mass + number)
      pgacw, ngacw — graupel rimes cloud water
      paacw, naacw — mass-weighted average of (psacw, pgacw) and (nsacw, ngacw)
      piacw, niacw — ice rimes cloud water (only if avedia_i >= di50, supcol > 0)

    Note: T-branch (T<T0 vs T>=T0) determines downstream destination (qs/qg vs qr),
    but the *rate* itself is computed identically. Caller handles T-branch routing.
    """
    zero = torch.zeros_like(qc)

    # qc-protective div-safety floor stays 1e-9 (NOT the 1e-15 gate qmin); lowering
    # THIS is the documented flush cause (wilt-ratio blow-up for tiny qc). 1:1 fix #16/#17.
    qc_safe = torch.clamp(qc, min=params.qcrmin)

    # ── psacw ──────────────────────────────────────────────────────────
    snow_active = (qs > params.qcrmin) & (qi > params.qmin)  # qci(:,:,1) is qc here
    snow_active_qc = (qs > params.qcrmin) & (qc > params.qmin)
    psacw_raw = (
        rslope3_s * rslopeb_s * rslopemu_s
        * _pi * n0so * n0sfac * params.avts * params.g3pbs * 0.25 * params.eacsc
        * _wilt_reduction(qs / qc_safe)
        * qc * denfac
    )
    psacw_capped = torch.minimum(psacw_raw, qc / dtcld)
    psacw = torch.where(snow_active_qc, psacw_capped, zero)

    # ── nsacw ──────────────────────────────────────────────────────────
    # per-cell ncmin (xland operational path) overrides scalar when present (C++ parity)
    _nc_floor = params.ncmin_tensor if params.ncmin_tensor is not None else params.ncmin
    snow_active_nc = (qs > params.qcrmin) & (nc > _nc_floor)
    nsacw_raw = (
        _pi * params.avts * 0.25 * params.eacsc * n0so * n0sfac * n0c / (params.muc + 1.0)
        * params.g3pbs
        * rslope3_s * rslopeb_s * rslopemu_s
        * rslopec * rslopecmu
        * _wilt_reduction(qs / qc_safe)
        * denfac
    )
    nsacw_capped = torch.minimum(nsacw_raw, nc / dtcld)
    nsacw = torch.where(snow_active_nc, nsacw_capped, zero)

    # ── pgacw ──────────────────────────────────────────────────────────
    graupel_active_qc = (qg > params.qcrmin) & (qc > params.qmin)
    pgacw_raw = (
        rslope3_g * rslopeb_g * rslopemu_g
        * qc * _pi * n0go * avtg * g3pbg * 0.25 * params.eacgc
        * _wilt_reduction(qg / qc_safe)
        * denfac
    )
    pgacw_capped = torch.minimum(pgacw_raw, qc / dtcld)
    pgacw = torch.where(graupel_active_qc, pgacw_capped, zero)

    # ── ngacw ──────────────────────────────────────────────────────────
    graupel_active_nc = (qg > params.qcrmin) & (nc > _nc_floor)  # per-cell ncmin (see nsacw)
    ngacw_raw = (
        _pi * avtg * 0.25 * params.eacgc * n0go * n0c / (params.muc + 1.0)
        * g3pbg
        * rslope3_g * rslopeb_g * rslopemu_g
        * rslopec * rslopecmu
        * _wilt_reduction(qg / qc_safe)
        * denfac
    )
    ngacw_capped = torch.minimum(ngacw_raw, nc / dtcld)
    ngacw = torch.where(graupel_active_nc, ngacw_capped, zero)

    # ── paacw (mass-weighted avg) and naacw ────────────────────────────
    qsum_safe = torch.clamp(qs + qg, min=params.qsum_floor)
    qsum_active = (qs + qg) > params.qsum_floor
    paacw_raw = (qs * psacw + qg * pgacw) / qsum_safe
    paacw = torch.where(qsum_active, paacw_raw, zero)
    naacw_raw = (qs * nsacw + qg * ngacw) / qsum_safe
    naacw = torch.where(qsum_active, naacw_raw, zero)

    # ── piacw / niacw (PK97: only if avedia_i >= di50, cold) ───────────
    cold_ice = (supcol > 0) & (qi > params.qcrmin) & (avedia_i >= params.di50)

    piacw_active = cold_ice & (qc > params.qmin)
    piacw_raw = (
        rslope3_i * rslopeb_i * rslopemu_i
        * _pi * n0i * params.avti * params.g3pbi * 0.25 * params.eacic
        * _wilt_reduction(qi / qc_safe)
        * qc * denfac
    )
    piacw_capped = torch.minimum(piacw_raw, qc / dtcld)
    piacw = torch.where(piacw_active, piacw_capped, zero)

    niacw_active = cold_ice & (nc > _nc_floor)  # per-cell xland ncmin (see nsacw; round-6 fix of round-5 miss)
    niacw_raw = (
        _pi * params.avti * 0.25 * params.eacic * n0i * n0c / (params.muc + 1.0)
        * params.g3pbi
        * rslope3_i * rslopeb_i * rslopemu_i
        * rslopec * rslopecmu
        * _wilt_reduction(qi / qc_safe)
        * denfac
    )
    niacw_capped = torch.minimum(niacw_raw, nc / dtcld)
    niacw = torch.where(niacw_active, niacw_capped, zero)

    return CloudWaterRimingOutputs(
        psacw=psacw, nsacw=nsacw,
        pgacw=pgacw, ngacw=ngacw,
        paacw=paacw, naacw=naacw,
        piacw=piacw, niacw=niacw,
    )


# ─── Step C2d: Rain-snow-graupel collection (6 processes) ────────────────────


class RainSnowGraupelCollectionParams(NamedTuple):
    """C2d 시간불변 스칼라.

    Mass kernels:
      g_pdsms = rgmma(k+dms+mus) for rain ←collected by→ snow
      g_pdrmr = rgmma(k+dmr+mur) for snow/graupel ←collected by→ rain
    Number kernels:
      g_pms, g_pmr, g_pmg as in C2b
    """

    cms: float       # pi * dens / 6
    cmr: float       # pi * denr / 6
    g1pms: float
    g2pms: float
    g3pms: float
    g1pmr: float
    g2pmr: float
    g3pmr: float
    g1pmg: float
    g2pmg: float
    g3pmg: float
    g1pdsms: float
    g2pdsms: float
    g3pdsms: float
    g1pdrmr: float
    g2pdrmr: float
    g3pdrmr: float
    eacrs: float
    eacsr: float
    eacgr: float
    qcrmin: float
    nrmin: float


def default_rain_snow_graupel_collection_params() -> RainSnowGraupelCollectionParams:
    cms = _pi * c.DENS / 6.0
    cmr = _pi * c.DENR / 6.0
    g1pms = 1.0 if c.MUS == 0.0 else _rgmma(1.0 + c.MUS)
    g2pms = _rgmma(2.0 + c.MUS)
    g3pms = _rgmma(3.0 + c.MUS)
    g1pmr = _rgmma(1.0 + c.MUR)
    g2pmr = _rgmma(2.0 + c.MUR)
    g3pmr = _rgmma(3.0 + c.MUR)
    g1pmg = 1.0 if c.MUG == 0.0 else _rgmma(1.0 + c.MUG)
    g2pmg = _rgmma(2.0 + c.MUG)
    g3pmg = _rgmma(3.0 + c.MUG)
    g1pdsms = _rgmma(1.0 + c.DMS + c.MUS)
    g2pdsms = _rgmma(2.0 + c.DMS + c.MUS)
    g3pdsms = _rgmma(3.0 + c.DMS + c.MUS)
    g1pdrmr = _rgmma(1.0 + c.DMR + c.MUR)
    g2pdrmr = _rgmma(2.0 + c.DMR + c.MUR)
    g3pdrmr = _rgmma(3.0 + c.DMR + c.MUR)
    return RainSnowGraupelCollectionParams(
        cms=cms, cmr=cmr,
        g1pms=g1pms, g2pms=g2pms, g3pms=g3pms,
        g1pmr=g1pmr, g2pmr=g2pmr, g3pmr=g3pmr,
        g1pmg=g1pmg, g2pmg=g2pmg, g3pmg=g3pmg,
        g1pdsms=g1pdsms, g2pdsms=g2pdsms, g3pdsms=g3pdsms,
        g1pdrmr=g1pdrmr, g2pdrmr=g2pdrmr, g3pdrmr=g3pdrmr,
        eacrs=c.EACRS, eacsr=c.EACSR, eacgr=c.EACGR,
        qcrmin=c.QCRMIN, nrmin=c.NRMIN,
    )


class RainSnowGraupelCollectionOutputs(NamedTuple):
    """6 collection process rates."""
    pracs: torch.Tensor   # qs←rain (T<T0: QS→QG)
    nracs: torch.Tensor   # NS← (Fortran commented out → 항상 0)
    psacr: torch.Tensor   # qr←snow
    nsacr: torch.Tensor   # NR←snow
    pgacr: torch.Tensor   # qr←graupel
    ngacr: torch.Tensor   # NR←graupel


def rain_snow_graupel_collection_torch(
    qr: torch.Tensor,
    qs: torch.Tensor,
    qg: torch.Tensor,
    nr: torch.Tensor,
    den: torch.Tensor,
    n0r: torch.Tensor,
    n0so: torch.Tensor,
    n0go: torch.Tensor,
    n0sfac: torch.Tensor,
    supcol: torch.Tensor,
    vt2r: torch.Tensor,
    vt2s: torch.Tensor,
    vt2g: torch.Tensor,
    rslope_r: torch.Tensor,
    rslope2_r: torch.Tensor,
    rslope3_r: torch.Tensor,
    rslopemu_r: torch.Tensor,
    rsloped_r: torch.Tensor,
    rslope_s: torch.Tensor,
    rslope2_s: torch.Tensor,
    rslope3_s: torch.Tensor,
    rslopemu_s: torch.Tensor,
    rsloped_s: torch.Tensor,
    rslope_g: torch.Tensor,
    rslope2_g: torch.Tensor,
    rslope3_g: torch.Tensor,
    rslopemu_g: torch.Tensor,
    *,
    params: RainSnowGraupelCollectionParams,
    dtcld: float,
) -> RainSnowGraupelCollectionOutputs:
    """Fortran 2051-2150 — rain-snow & rain-graupel mass + number collection.

    Active gates per process:
      pracs : qs > qcrmin AND qr > qcrmin AND supcol > 0   (cold-only)
      nracs : commented out in Fortran → always 0
      psacr : qs > qcrmin AND qr > qcrmin (cold/warm both)
      nsacr : qs > qcrmin AND nr > nrmin
      pgacr : qg > qcrmin AND qr > qcrmin
      ngacr : qg > qcrmin AND nr > nrmin
    """
    zero = torch.zeros_like(qr)
    den_safe = torch.clamp(den, min=params.qcrmin)
    qr_safe = torch.clamp(qr, min=params.qcrmin)
    qs_safe = torch.clamp(qs, min=params.qcrmin)
    qg_safe = torch.clamp(qg, min=params.qcrmin)

    # Common factors
    common_r_d = rsloped_r * rslopemu_r           # rain side: rsloped·rslopemu (mass kernel)
    common_s_d = rsloped_s * rslopemu_s           # snow side: rsloped·rslopemu (mass kernel)
    snow_r_active = (qs > params.qcrmin) & (qr > params.qcrmin)

    # ── pracs (mass): rain collects snow, cold-only ─────────────────────
    cold = supcol > 0
    acrfac_pracs = (
        params.g3pmr * params.g1pdsms * rslope3_r * rslopemu_r * common_s_d * rslope_s
        + 2.0 * params.g2pmr * params.g2pdsms * rslope2_r * rslopemu_r * common_s_d * rslope2_s
        + params.g1pmr * params.g3pdsms * rslope_r * rslopemu_r * common_s_d * rslope3_s
    )
    pracs_raw = (
        _pi * params.cms * n0so * n0sfac * n0r * torch.abs(vt2r - vt2s)
        / (4.0 * den_safe) * acrfac_pracs * params.eacrs
    )
    pracs_wilt = pracs_raw * _wilt_reduction(qr_safe / qs_safe)
    pracs_capped = torch.minimum(pracs_wilt, qs / dtcld)
    pracs = torch.where(snow_r_active & cold, pracs_capped, zero)

    # ── nracs : commented out in Fortran → 0 ────────────────────────────
    nracs = zero.clone()

    # ── psacr (mass): snow collects rain ────────────────────────────────
    acrfac_psacr = (
        params.g3pms * params.g1pdrmr * rslope3_s * rslopemu_s * common_r_d * rslope_r
        + 2.0 * params.g2pms * params.g2pdrmr * rslope2_s * rslopemu_s * common_r_d * rslope2_r
        + params.g1pms * params.g3pdrmr * rslope_s * rslopemu_s * common_r_d * rslope3_r
    )
    psacr_raw = (
        _pi * params.cmr * n0r * n0so * n0sfac * torch.abs(vt2s - vt2r)
        / (4.0 * den_safe) * acrfac_psacr * params.eacsr
    )
    psacr_wilt = psacr_raw * _wilt_reduction(qs_safe / qr_safe)
    psacr_capped = torch.minimum(psacr_wilt, qr / dtcld)
    psacr = torch.where(snow_r_active, psacr_capped, zero)

    # ── nsacr (number): snow collects rain ──────────────────────────────
    snow_nr_active = (qs > params.qcrmin) & (nr > params.nrmin)
    acrfac_nsacr = (
        params.g3pms * params.g1pmr * rslope3_s * rslopemu_s * rslope_r * rslopemu_r
        + 2.0 * params.g2pms * params.g2pmr * rslope2_s * rslopemu_s * rslope2_r * rslopemu_r
        + params.g1pms * params.g3pmr * rslope_s * rslopemu_s * rslope3_r * rslopemu_r
    )
    nsacr_raw = (
        _pi / 4.0 * n0r * n0so * n0sfac * torch.abs(vt2s - vt2r)
        * acrfac_nsacr * params.eacsr
    )
    nsacr_wilt = nsacr_raw * _wilt_reduction(qs_safe / qr_safe)
    nsacr_capped = torch.minimum(nsacr_wilt, nr / dtcld)
    nsacr = torch.where(snow_nr_active, nsacr_capped, zero)

    # ── pgacr (mass): graupel collects rain ─────────────────────────────
    graupel_r_active = (qg > params.qcrmin) & (qr > params.qcrmin)
    acrfac_pgacr = (
        params.g3pmg * params.g1pdrmr * rslope3_g * rslopemu_g * common_r_d * rslope_r
        + 2.0 * params.g2pmg * params.g2pdrmr * rslope2_g * rslopemu_g * common_r_d * rslope2_r
        + params.g1pmg * params.g3pdrmr * rslope_g * rslopemu_g * common_r_d * rslope3_r
    )
    pgacr_raw = (
        _pi * params.cmr * n0r * n0go * torch.abs(vt2g - vt2r)
        / (4.0 * den_safe) * acrfac_pgacr * params.eacgr
    )
    pgacr_wilt = pgacr_raw * _wilt_reduction(qg_safe / qr_safe)
    pgacr_capped = torch.minimum(pgacr_wilt, qr / dtcld)
    pgacr = torch.where(graupel_r_active, pgacr_capped, zero)

    # ── ngacr (number): graupel collects rain ───────────────────────────
    graupel_nr_active = (qg > params.qcrmin) & (nr > params.nrmin)
    acrfac_ngacr = (
        params.g3pmg * params.g1pmr * rslope3_g * rslopemu_g * rslope_r * rslopemu_r
        + 2.0 * params.g2pmg * params.g2pmr * rslope2_g * rslopemu_g * rslope2_r * rslopemu_r
        + params.g1pmg * params.g3pmr * rslope_g * rslopemu_g * rslope3_r * rslopemu_r
    )
    ngacr_raw = (
        _pi / 4.0 * n0r * n0go * torch.abs(vt2g - vt2r) * acrfac_ngacr * params.eacgr
    )
    ngacr_wilt = ngacr_raw * _wilt_reduction(qg_safe / qr_safe)
    ngacr_capped = torch.minimum(ngacr_wilt, nr / dtcld)
    ngacr = torch.where(graupel_nr_active, ngacr_capped, zero)

    return RainSnowGraupelCollectionOutputs(
        pracs=pracs, nracs=nracs,
        psacr=psacr, nsacr=nsacr,
        pgacr=pgacr, ngacr=ngacr,
    )


# ─── Step C2e: Hallett-Mossop ice multiplication ─────────────────────────────


class HallettMossopParams(NamedTuple):
    """HM multiplication 시간불변 스칼라.

    Fortran constants (line 128, 2158):
      Rispl = 5e-6 m  (splinter radius)
      Mispl = (4/3)·π·deni·Rispl³
    HM active range: 265.16 < t < 270.16 K. Peak fmul=1 at t=268.16.
    Mass thresholds (Fortran 2160-2161):
      qs >= 0.1e-3, qg >= 0.1e-3, qc >= 0.5e-3, qr >= 0.1e-3
    """

    rispl: float        # 5e-6 m, splinter radius
    deni: float         # ice density
    qs_threshold: float # 0.1e-3
    qg_threshold: float # 0.1e-3
    qc_threshold: float # 0.5e-3
    qr_threshold: float # 0.1e-3
    t_lo: float         # 265.16
    t_hi: float         # 270.16
    t_mid: float        # 268.16


def default_hallett_mossop_params() -> HallettMossopParams:
    return HallettMossopParams(
        rispl=5.0e-6,
        deni=c.DENI,
        qs_threshold=0.1e-3,
        qg_threshold=0.1e-3,
        qc_threshold=0.5e-3,
        qr_threshold=0.1e-3,
        t_lo=265.16,
        t_hi=270.16,
        t_mid=268.16,
    )


def _hm_fmul(t: torch.Tensor, params: HallettMossopParams) -> torch.Tensor:
    """Triangular hat function — peak fmul=1 at t=t_mid (268.16), zero outside [t_lo, t_hi].

    Fortran 2166-2172 (and identical 2217-2223):
      t > t_hi             → 0
      t_mid < t <= t_hi    → (t_hi - t) / 2
      t_lo <= t <= t_mid   → (t - t_lo) / 3
      t < t_lo             → 0
    """
    fmul_upper = (params.t_hi - t) / 2.0
    fmul_lower = (t - params.t_lo) / 3.0
    in_upper = (t > params.t_mid) & (t <= params.t_hi)
    in_lower = (t >= params.t_lo) & (t <= params.t_mid)
    zero = torch.zeros_like(t)
    return torch.where(in_upper, fmul_upper, torch.where(in_lower, fmul_lower, zero))


class HallettMossopOutputs(NamedTuple):
    pmulcs: torch.Tensor   # ice multiplication mass from droplets accreted onto snow
    pmulrs: torch.Tensor   # ice multiplication mass from rain accreted onto snow
    pmulcg: torch.Tensor   # ice mult mass from droplets accreted onto graupel
    pmulrg: torch.Tensor   # ice mult mass from rain accreted onto graupel
    nmulcs: torch.Tensor
    nmulrs: torch.Tensor
    nmulcg: torch.Tensor
    nmulrg: torch.Tensor
    paacw_adj: torch.Tensor  # paacw - pmulcs - pmulcg (mass conservation)
    psacr_adj: torch.Tensor  # psacr - pmulrs
    pgacr_adj: torch.Tensor  # pgacr - pmulrg


def hallett_mossop_torch(
    paacw: torch.Tensor,
    psacr: torch.Tensor,
    pgacr: torch.Tensor,
    qc: torch.Tensor,
    qr: torch.Tensor,
    qs: torch.Tensor,
    qg: torch.Tensor,
    t: torch.Tensor,
    den: torch.Tensor,
    *,
    params: HallettMossopParams,
) -> HallettMossopOutputs:
    """Fortran 2154-2248 — Hallett & Mossop 1974 ice multiplication via splintering.

    *State-mutation* in Fortran (paacw/psacr/pgacr 차감)을 oracle은 `*_adj` 출력으로 표현 —
    caller가 mass-conservation을 명시적으로 사용. snow → graupel sequential processing은
    Fortran 직역 (graupel side는 paacw_after_snow 사용).
    """
    zero = torch.zeros_like(paacw)
    # STEP-86 class: REAL(4),save constants evaluated f32-stepwise in gfortran.
    _piF = _fc._f32(_fc.PI)
    _ri = _fc._f32(params.rispl)
    Mispl = _fc._f32(_fc._f32(_fc._f32(_fc._f32(4.0 / 3.0) * _piF) * _fc._f32(params.deni)) * _fc._f32(_fc._f32(_ri * _ri) * _ri))
    fmul = _hm_fmul(t, params)

    # Common gates
    droplet_mass = (qc >= params.qc_threshold) | (qr >= params.qr_threshold)
    t_in_band = (t > params.t_lo) & (t < params.t_hi)

    # ── Snow side ──────────────────────────────────────────────────────
    snow_outer = (
        (qs >= params.qs_threshold)
        & droplet_mass
        & ((paacw > 0) | (psacr > 0))
        & t_in_band
    )

    # pmulcs / nmulcs (from paacw)
    paacw_branch = snow_outer & (paacw > 0)
    nmul_pre_cs = 35.0e4 * paacw * fmul * 1000.0  # [#/kg/s], pre-density scaling
    pmulcs_raw = nmul_pre_cs * Mispl
    pmulcs_capped = torch.minimum(pmulcs_raw, paacw)  # mass cap
    pmulcs = torch.where(paacw_branch, pmulcs_capped, zero)
    nmulcs = torch.where(paacw_branch, nmul_pre_cs * den, zero)

    # pmulrs / nmulrs (from psacr)
    psacr_branch = snow_outer & (psacr > 0)
    nmul_pre_rs = 35.0e4 * psacr * fmul * 1000.0
    pmulrs_raw = nmul_pre_rs * Mispl
    pmulrs_capped = torch.minimum(pmulrs_raw, psacr)
    pmulrs = torch.where(psacr_branch, pmulrs_capped, zero)
    nmulrs = torch.where(psacr_branch, nmul_pre_rs * den, zero)

    # ── Graupel side ───────────────────────────────────────────────────
    # Fortran 직역: graupel side에서 사용된 paacw는 *snow side에서 이미 pmulcs만큼 차감된 값*
    paacw_after_snow = paacw - pmulcs

    graupel_outer = (
        (qg >= params.qg_threshold)
        & droplet_mass
        & ((paacw > 0) | (pgacr > 0))
        & t_in_band
    )

    # pmulcg / nmulcg (from adjusted paacw)
    paacw_branch_g = graupel_outer & (paacw_after_snow > 0)
    nmul_pre_cg = 35.0e4 * paacw_after_snow * fmul * 1000.0
    pmulcg_raw = nmul_pre_cg * Mispl
    pmulcg_capped = torch.minimum(pmulcg_raw, paacw_after_snow)
    pmulcg = torch.where(paacw_branch_g, pmulcg_capped, zero)
    nmulcg = torch.where(paacw_branch_g, nmul_pre_cg * den, zero)

    # pmulrg / nmulrg (from pgacr)
    pgacr_branch = graupel_outer & (pgacr > 0)
    nmul_pre_rg = 35.0e4 * pgacr * fmul * 1000.0
    pmulrg_raw = nmul_pre_rg * Mispl
    pmulrg_capped = torch.minimum(pmulrg_raw, pgacr)
    pmulrg = torch.where(pgacr_branch, pmulrg_capped, zero)
    nmulrg = torch.where(pgacr_branch, nmul_pre_rg * den, zero)

    # Adjusted rates (mass conservation)
    paacw_adj = paacw - pmulcs - pmulcg
    psacr_adj = psacr - pmulrs
    pgacr_adj = pgacr - pmulrg

    return HallettMossopOutputs(
        pmulcs=pmulcs, pmulrs=pmulrs, pmulcg=pmulcg, pmulrg=pmulrg,
        nmulcs=nmulcs, nmulrs=nmulrs, nmulcg=nmulcg, nmulrg=nmulrg,
        paacw_adj=paacw_adj, psacr_adj=psacr_adj, pgacr_adj=pgacr_adj,
    )


# ─── Step C3: Ice nucleation from vapor (pinud + ninud) ──────────────────────


class IceNucleationParams(NamedTuple):
    """Ice nucleation 시간불변 스칼라.

    Cooper (1986) curve: Nid = 0.005 · exp(0.304·supcol) · 1000 [m⁻³]
    Capped to 500 cm⁻³ at very cold temperatures.
    Outer gate: `(supcol > 8 AND supsat > 0) OR rh_ice > 1.08`.
    """

    rinud: float            # 10e-6 m, ice nucleus radius
    deni: float
    cooper_a: float         # 0.005
    cooper_b: float         # 0.304
    cooper_unit: float      # 1000 (1/L → 1/m³)
    nid_max: float          # 500e3 m⁻³
    supcol_threshold: float # 8.0 K
    rh_ice_threshold: float # 1.08


def default_ice_nucleation_params() -> IceNucleationParams:
    return IceNucleationParams(
        rinud=10.0e-6,
        deni=c.DENI,
        cooper_a=0.005,
        cooper_b=0.304,
        cooper_unit=1000.0,
        nid_max=500.0e3,
        supcol_threshold=8.0,
        rh_ice_threshold=1.08,
    )


class IceNucleationOutputs(NamedTuple):
    pinud: torch.Tensor   # mass nucleation rate [kg/kg/s]
    ninud: torch.Tensor   # number nucleation rate [#/kg/s]
    ifsat: torch.Tensor   # boolean: |prevp + pinud| >= |satdt| (deposition saturation flag)


def ice_nucleation_torch(
    supcol: torch.Tensor,
    supsat: torch.Tensor,
    rh_ice: torch.Tensor,    # rh(:,:,2), w.r.t. ice
    prevp: torch.Tensor,     # B4 output (rain evap rate)
    nci_ice: torch.Tensor,   # nci(:,:,2), current ice number conc
    den: torch.Tensor,
    *,
    params: IceNucleationParams,
    dtcld: float,
) -> IceNucleationOutputs:
    """Fortran 2309-2326 — ice nucleation from vapor.

    Returns
    -------
    pinud, ninud  : mass and number nucleation rates (active region only)
    ifsat         : (B, K) boolean. True where |prevp + pinud| >= |satdt|. Caller
                    uses this to disable subsequent deposition processes.
    """
    zero = torch.zeros_like(supcol)
    _piN = _fc._f32(_fc.PI)
    _rn = _fc._f32(params.rinud)
    Minud = _fc._f32(_fc._f32(_fc._f32(_fc._f32(4.0 / 3.0) * _piN) * _fc._f32(params.deni)) * _fc._f32(_fc._f32(_rn * _rn) * _rn))  # STEP-86 SEED (F:2344)

    # Outer gate
    cold_super = (supcol > params.supcol_threshold) & (supsat > 0)
    high_rh = rh_ice > params.rh_ice_threshold
    nuc_active = cold_super | high_rh

    # supice = satdt - prevp (available ice supersaturation rate)
    satdt = supsat / dtcld
    supice = satdt - prevp

    # Cooper curve, clamp to [0, nid_max]
    nid_raw = params.cooper_a * torch.exp(params.cooper_b * supcol) * params.cooper_unit
    nid = torch.clamp(nid_raw, min=0.0, max=params.nid_max)

    # Inner condition: only if Nid > current ice number conc
    inner_active = nid > nci_ice

    # ninud (initial guess): number deficit / dt
    den_safe = torch.clamp(den, min=c.QCRMIN)
    ninud_raw = (nid - nci_ice) / dtcld
    pinud_raw = ninud_raw / den_safe * Minud

    # Double min cap: pinud <= satdt/2  AND  pinud <= supice
    half_satdt = 0.5 * satdt
    pinud_capped = torch.minimum(torch.minimum(pinud_raw, half_satdt), supice)

    # Recompute ninud from capped pinud
    ninud_capped = pinud_capped * den_safe / Minud

    # Apply gates
    active = nuc_active & inner_active
    pinud = torch.where(active, pinud_capped, zero)
    ninud = torch.where(active, ninud_capped, zero)

    # ifsat: deposition saturation flag (used by caller for downstream dep/sub)
    ifsat = torch.abs(prevp + pinud) >= torch.abs(satdt)

    return IceNucleationOutputs(pinud=pinud, ninud=ninud, ifsat=ifsat)


# ─── Step C4: Deposition/Sublimation (pidep + psdep + pgdep) ─────────────────


class DepSubParams(NamedTuple):
    """C4 시간불변 스칼라.

    Derivations (Fortran kdm6init):
      g2pmi = rgmma(2+mui)
      g2pms = rgmma(2+mus); precs1 = 4·0.65·g2pms
      bvts2 = 2.5+0.5·bvts+mus; g5pbso2 = rgmma(bvts2)
      precs2 = 4·0.44·sqrt(avts)·g5pbso2
      precg1 = 4·0.78·g2pmg
      (precg2 is runtime, ProgB output)
    """

    g2pmi: float
    precs1: float
    precs2: float
    precg1: float
    qcrmin: float


def default_dep_sub_params() -> DepSubParams:
    g2pmi = _rgmma(2.0 + c.MUI)
    g2pms = _rgmma(2.0 + c.MUS)
    g2pmg = _rgmma(2.0 + c.MUG)
    bvts2 = 2.5 + 0.5 * c.BVTS + c.MUS
    g5pbso2 = _rgmma(bvts2)
    precs1 = 4.0 * 0.65 * g2pms
    precs2 = 4.0 * 0.44 * (c.AVTS ** 0.5) * g5pbso2
    precg1 = 4.0 * 0.78 * g2pmg
    return DepSubParams(
        g2pmi=g2pmi, precs1=precs1, precs2=precs2, precg1=precg1,
        qcrmin=c.QCRMIN,
    )


class DepSubOutputs(NamedTuple):
    pidep: torch.Tensor
    psdep: torch.Tensor
    pgdep: torch.Tensor
    ifsat: torch.Tensor   # bool, cumulative through 3 processes
    ice_complete_sublim: torch.Tensor  # bool, pidep == -qi/dtcld (caller handles nci=0)


def _dep_sub_capped(rate_raw: torch.Tensor, source_mass: torch.Tensor,
                    half_satdt: torch.Tensor, supice: torch.Tensor,
                    dtcld: float) -> torch.Tensor:
    """Sub-branch on rate sign:
        rate < 0 (sublimation): max(max(rate, -source/dtcld), half_satdt, supice)
        rate >= 0 (deposition): min(min(rate, half_satdt), supice)
    """
    # Sublimation path
    sub_path = torch.maximum(rate_raw, -source_mass / dtcld)
    sub_path = torch.maximum(torch.maximum(sub_path, half_satdt), supice)
    # Deposition path
    dep_path = torch.minimum(torch.minimum(rate_raw, half_satdt), supice)
    return torch.where(rate_raw < 0, sub_path, dep_path)


def dep_sub_torch(
    qi: torch.Tensor,            # nci(:,:,2) ice mass mixing ratio
    qs: torch.Tensor,
    qg: torch.Tensor,
    rh_ice: torch.Tensor,        # rh(:,:,2)
    supcol: torch.Tensor,
    supsat: torch.Tensor,
    prevp: torch.Tensor,         # B4 output
    pinud: torch.Tensor,         # C3 output
    ifsat_in: torch.Tensor,      # C3 output (bool)
    n0i: torch.Tensor,
    n0so: torch.Tensor,
    n0go: torch.Tensor,
    n0sfac: torch.Tensor,
    work1_ice: torch.Tensor,     # work1(:,:,2)
    work2: torch.Tensor,
    precg2: torch.Tensor,        # ProgB output (runtime)
    rslope_s: torch.Tensor,
    rslope2_s: torch.Tensor,
    rslopeb_s: torch.Tensor,
    rslopemu_s: torch.Tensor,
    rslope_g: torch.Tensor,
    rslope2_g: torch.Tensor,
    rslopeb_g: torch.Tensor,
    rslopemu_g: torch.Tensor,
    rslope2_i: torch.Tensor,
    rslopemu_i: torch.Tensor,
    *,
    params: DepSubParams,
    dtcld: float,
) -> DepSubOutputs:
    """Fortran 2334-2390 — sequential pidep → psdep → pgdep with cumulative ifsat.

    Note (Fortran direct translation, counter-intuitive):
        sublimation cap uses `max(rate, satdt/2)` where `satdt = supsat/dtcld`.
        If supsat > 0 (vapor super-saturated), satdt/2 > 0 acts as a *positive*
        floor for the negative rate. So rate_raw < 0 may emerge POSITIVE after
        capping. This is Fortran 2347 verbatim. Caller's mass-balance unwinds.

    Outer gate: `supcol > 0` (cold).
    Each process: skip if ifsat (cumulative) already triggered.

    *State mutation*: Fortran 2343-2345 sets `nci(:,:,2) = 0` when pidep hits the
    complete-sublimation cap (`pidep == -qi/dtcld`). Oracle returns this as a
    boolean mask `ice_complete_sublim`; caller applies the nci zero-out.

    Returns
    -------
    pidep, psdep, pgdep : (B, K) tensors [kg/kg/s]
    ifsat              : (B, K) bool, cumulative saturation flag after C3+C4
    ice_complete_sublim: (B, K) bool, pidep at -qi/dtcld cap (sublimation hit floor)
    """
    zero = torch.zeros_like(qi)
    cold = supcol > 0
    satdt = supsat / dtcld
    half_satdt = 0.5 * satdt
    work1_safe = torch.clamp(work1_ice, min=params.qcrmin)

    # ── pidep (ice deposition/sublimation) ──────────────────────────────
    pidep_active = cold & (qi > 0) & (~ifsat_in)
    pidep_raw = (
        4.0 * n0i * params.g2pmi * rslopemu_i * rslope2_i * (rh_ice - 1.0)
        / work1_safe
    )
    supice_pidep = satdt - prevp - pinud
    pidep_capped = _dep_sub_capped(pidep_raw, qi, half_satdt, supice_pidep, dtcld)
    pidep = torch.where(pidep_active, pidep_capped, zero)

    # complete-sublim signal: pidep == -qi/dtcld (within active region)
    qi_cap = -qi / dtcld
    ice_complete_sublim = pidep_active & (pidep <= qi_cap + 1.0e-30) & (pidep < 0)

    # Update ifsat after pidep
    ifsat_after_pidep = ifsat_in | (
        torch.abs(prevp + pinud + pidep) >= torch.abs(satdt)
    )

    # ── psdep (snow deposition/sublimation) ─────────────────────────────
    psdep_active = cold & (qs > 0) & (~ifsat_after_pidep)
    coeres_s = rslope2_s * torch.sqrt(torch.clamp(rslope_s * rslopeb_s, min=params.qcrmin)) * rslopemu_s
    psdep_raw = (
        (rh_ice - 1.0) * n0sfac
        * (params.precs1 * n0so * rslope2_s * rslopemu_s
           + params.precs2 * n0so * work2 * coeres_s)
        / work1_safe
    )
    supice_psdep = satdt - prevp - pinud - pidep
    psdep_capped = _dep_sub_capped(psdep_raw, qs, half_satdt, supice_psdep, dtcld)
    psdep = torch.where(psdep_active, psdep_capped, zero)

    ifsat_after_psdep = ifsat_after_pidep | (
        torch.abs(prevp + pinud + pidep + psdep) >= torch.abs(satdt)
    )

    # ── pgdep (graupel deposition/sublimation) ──────────────────────────
    pgdep_active = cold & (qg > 0) & (~ifsat_after_psdep)
    coeres_g = rslope2_g * torch.sqrt(torch.clamp(rslope_g * rslopeb_g, min=params.qcrmin)) * rslopemu_g
    pgdep_raw = (
        (rh_ice - 1.0)
        * (params.precg1 * n0go * rslope2_g * rslopemu_g
           + precg2 * n0go * work2 * coeres_g)
        / work1_safe
    )
    supice_pgdep = satdt - prevp - pinud - pidep - psdep
    pgdep_capped = _dep_sub_capped(pgdep_raw, qg, half_satdt, supice_pgdep, dtcld)
    pgdep = torch.where(pgdep_active, pgdep_capped, zero)

    ifsat_final = ifsat_after_psdep | (
        torch.abs(prevp + pinud + pidep + psdep + pgdep) >= torch.abs(satdt)
    )

    return DepSubOutputs(
        pidep=pidep, psdep=psdep, pgdep=pgdep,
        ifsat=ifsat_final,
        ice_complete_sublim=ice_complete_sublim,
    )


# ─── Step C5: Aggregation (psaut + nsaut) ────────────────────────────────────


class IceAggregationParams(NamedTuple):
    """psaut/nsaut 시간불변 스칼라.

    Ryan et al. 2010 qi0 piecewise (T > 255.66 vs T ≤ 255.66).
    Miaut = π·deni·di125³/6 — ice → snow aggregation cutoff mass.
    """

    deni: float
    di125: float
    t_split: float    # 255.66
    qcrmin: float


def default_ice_aggregation_params() -> IceAggregationParams:
    return IceAggregationParams(
        deni=c.DENI,
        di125=c.DI125,
        t_split=255.66,
        qcrmin=c.QCRMIN,
    )


def ice_aggregation_torch(
    qi: torch.Tensor,
    ni: torch.Tensor,
    t: torch.Tensor,
    den: torch.Tensor,
    supcol: torch.Tensor,
    *,
    params: IceAggregationParams,
    dtcld: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Fortran 2393-2406 — psaut + nsaut (ice → snow aggregation).

    Ryan et al. 2010 qi0:
        T > 255.66:  qi0 = 0.4632·10^(-6 - 0.0413·(-supcol))·den
        T ≤ 255.66:  qi0 = 0.2316·10^(-4 + 0.0519·(-supcol))·den
    Rate:
        psaut = min(max(0, α₁·(qi-qi0)), qi/dt)   where α₁ = 0.005·exp(0.025·(-supcol))
        nsaut = min(psaut·den/Miaut, ni/dt)
    Outer gate: qi > 0 AND ni > 0 (and supcol > 0 from cold-rain block).
    """
    zero = torch.zeros_like(qi)
    cold = supcol > 0
    active = cold & (qi > 0) & (ni > 0)

    # Ryan 2010 piecewise qi0
    neg_supcol = -supcol
    qi0_warm = 0.4632 * torch.pow(torch.full_like(t, 10.0),
                                   -6.0 - 0.0413 * neg_supcol) * den
    qi0_cold = 0.2316 * torch.pow(torch.full_like(t, 10.0),
                                   -4.0 + 0.0519 * neg_supcol) * den
    qi0 = torch.where(t > params.t_split, qi0_warm, qi0_cold)

    alpha1 = 0.005 * torch.exp(0.025 * neg_supcol)
    _piA = _fc._f32(_fc.PI)
    _d3 = _fc._f32(params.di125)
    Miaut = _fc._f32(_fc._f32(_fc._f32(_piA * _fc._f32(params.deni)) * _fc._f32(_fc._f32(_d3 * _d3) * _d3)) / _fc._f32(6.0))  # STEP-86 class (F:2436)

    # psaut = min(max(0, α₁·(qi-qi0)), qi/dt)
    psaut_raw = alpha1 * (qi - qi0)
    psaut_pos = torch.clamp(psaut_raw, min=0.0)
    psaut_capped = torch.minimum(psaut_pos, qi / dtcld)
    psaut = torch.where(active, psaut_capped, zero)

    # nsaut = min(psaut·den/Miaut, ni/dt)
    nsaut_raw = psaut * den / Miaut
    nsaut_capped = torch.minimum(nsaut_raw, ni / dtcld)
    nsaut = torch.where(active, nsaut_capped, zero)

    return psaut, nsaut


# ─── Step C6: Snow evaporation (psevp) ───────────────────────────────────────


class SnowEvapParams(NamedTuple):
    """psevp 시간불변 스칼라. precs1/precs2는 dep_sub와 동일."""

    precs1: float
    precs2: float
    qcrmin: float


def default_snow_evap_params() -> SnowEvapParams:
    g2pms = _rgmma(2.0 + c.MUS)
    bvts2 = 2.5 + 0.5 * c.BVTS + c.MUS
    g5pbso2 = _rgmma(bvts2)
    precs1 = 4.0 * 0.65 * g2pms
    precs2 = 4.0 * 0.44 * (c.AVTS ** 0.5) * g5pbso2
    return SnowEvapParams(precs1=precs1, precs2=precs2, qcrmin=c.QCRMIN)


def snow_evap_torch(
    qs: torch.Tensor,
    rh_w: torch.Tensor,        # rh(:,:,1) — w.r.t. water
    supcol: torch.Tensor,
    n0so: torch.Tensor,
    n0sfac: torch.Tensor,
    work1_water: torch.Tensor, # work1(:,:,1)
    work2: torch.Tensor,
    rslope_s: torch.Tensor,
    rslope2_s: torch.Tensor,
    rslopeb_s: torch.Tensor,
    rslopemu_s: torch.Tensor,
    *,
    params: SnowEvapParams,
    dtcld: float,
) -> torch.Tensor:
    """Fortran 2424-2429 — evaporation of melting snow.

    Outer gate: `supcol < 0` (warm) AND qs > 0 AND rh_w < 1 (sub-saturated water).
    psevp ≤ 0 (evap), capped by `-qs/dtcld`.

    Returns
    -------
    psevp : (B, K) tensor [kg/kg/s]. ≤ 0 (evap into vapor).
    """
    zero = torch.zeros_like(qs)
    active = (supcol < 0) & (qs > 0) & (rh_w < 1.0)

    work1_safe = torch.clamp(work1_water, min=params.qcrmin)
    coeres = rslope2_s * torch.sqrt(torch.clamp(rslope_s * rslopeb_s, min=params.qcrmin)) * rslopemu_s

    psevp_raw = (
        (rh_w - 1.0) * n0sfac
        * (params.precs1 * n0so * rslope2_s * rslopemu_s
           + params.precs2 * n0so * work2 * coeres)
        / work1_safe
    )
    # psevp = min(max(psevp, -qs/dt), 0)
    psevp_capped = torch.minimum(torch.maximum(psevp_raw, -qs / dtcld), zero)
    psevp = torch.where(active, psevp_capped, zero)
    return psevp


# ─── Step C6': Graupel evaporation (pgevp) ───────────────────────────────────
# Fortran 2435-2440 — `psevp`와 구조 동일, 단 (1) n0sfac factor 없음, (2) precg2는
# 시간 가변 텐서(ProgB output), (3) graupel rslope/n0go 사용. codex review #2 #4번
# 권고로 cold module에 누락되어 있던 process를 추가.


class GraupelEvapParams(NamedTuple):
    """pgevp 시간불변 스칼라. precg1은 dep_sub와 동일 (4·0.78·g2pmg)."""

    precg1: float
    qcrmin: float


def default_graupel_evap_params() -> GraupelEvapParams:
    g2pmg = _rgmma(2.0 + c.MUG)
    precg1 = 4.0 * 0.78 * g2pmg
    return GraupelEvapParams(precg1=precg1, qcrmin=c.QCRMIN)


def graupel_evap_torch(
    qg: torch.Tensor,
    rh_w: torch.Tensor,           # rh(:,:,1) — w.r.t. water
    supcol: torch.Tensor,
    n0go: torch.Tensor,
    work1_water: torch.Tensor,    # work1(:,:,1)
    work2: torch.Tensor,
    rslope_g: torch.Tensor,
    rslope2_g: torch.Tensor,
    rslopeb_g: torch.Tensor,
    rslopemu_g: torch.Tensor,
    precg2: torch.Tensor,         # ProgB runtime output (B, K)
    *,
    params: GraupelEvapParams,
    dtcld: float,
) -> torch.Tensor:
    """Fortran 2435-2440 — evaporation of melting graupel.

    Outer gate: `supcol < 0` (warm) AND qg > 0 AND rh_w < 1 (sub-saturated water).
    pgevp ≤ 0 (evap), capped by `-qg/dtcld`.

    Returns
    -------
    pgevp : (B, K) tensor [kg/kg/s]. ≤ 0 (evap into vapor).
    """
    zero = torch.zeros_like(qg)
    active = (supcol < 0) & (qg > 0) & (rh_w < 1.0)

    work1_safe = torch.clamp(work1_water, min=params.qcrmin)
    coeres = rslope2_g * torch.sqrt(torch.clamp(rslope_g * rslopeb_g, min=params.qcrmin)) * rslopemu_g

    pgevp_raw = (
        (rh_w - 1.0)
        * (params.precg1 * n0go * rslope2_g * rslopemu_g
           + precg2 * n0go * work2 * coeres)
        / work1_safe
    )
    pgevp_capped = torch.minimum(torch.maximum(pgevp_raw, -qg / dtcld), zero)
    pgevp = torch.where(active, pgevp_capped, zero)
    return pgevp


__all__ = [
    "IceAccretionParams",
    "IceToSnowGraupelParams",
    "NumberAccretionParams",
    "CloudWaterRimingParams",
    "CloudWaterRimingOutputs",
    "RainSnowGraupelCollectionParams",
    "RainSnowGraupelCollectionOutputs",
    "HallettMossopParams",
    "HallettMossopOutputs",
    "IceNucleationParams",
    "IceNucleationOutputs",
    "DepSubParams",
    "DepSubOutputs",
    "IceAggregationParams",
    "SnowEvapParams",
    "GraupelEvapParams",
    "default_ice_accretion_params",
    "default_ice_to_snow_graupel_params",
    "default_number_accretion_params",
    "default_cloud_water_riming_params",
    "default_rain_snow_graupel_collection_params",
    "default_hallett_mossop_params",
    "default_ice_nucleation_params",
    "default_dep_sub_params",
    "default_ice_aggregation_params",
    "default_snow_evap_params",
    "default_graupel_evap_params",
    "ice_accretion_torch",
    "ice_to_snow_graupel_torch",
    "number_accretion_torch",
    "cloud_water_riming_torch",
    "rain_snow_graupel_collection_torch",
    "hallett_mossop_torch",
    "ice_nucleation_torch",
    "dep_sub_torch",
    "ice_aggregation_torch",
    "snow_evap_torch",
    "graupel_evap_torch",
]
