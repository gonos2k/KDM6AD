"""
KDM6 slope parameter oracle — `slope_kdm6` / `slope_rain` Fortran 직역.

원본:
  - module_mp_kdm6.F: 3427-3557 (`slope_kdm6`)
  - module_mp_kdm6.F: 3559-3608 (`slope_rain`)
  - module_mp_kdm6.F: 3125-3308 (`kdm6init` 파생 상수)
"""
from __future__ import annotations

from math import exp, lgamma, pi
from typing import NamedTuple

import torch

from . import constants as c
from .ops import EPS, isfinite_else, safe_pow

DOMAIN_FLOOR = 1.0e-30  # Fortran slope 루틴 전용 floor (`max(..., 1.e-30)`)
RAIN_RSLOPE_LIMIT = 1.0e-3


def _const(name: str, _legacy_fallback: float = 0.0) -> float:
    """`constants.py`에서 직접 lookup.

    (Legacy: 두 번째 인자는 archive 시점에 일부 상수가 빠져 있던 시기의
    fallback이었음. constants.py가 source-of-truth로 정리된 이후 무시됨.)
    """
    return float(getattr(c, name))


DENR = _const("DENR")
DMR = _const("DMR")
DMI = _const("DMI")
MUI = _const("MUI")
LAMDAGMAX = _const("LAMDAGMAX")


class SlopeParams(NamedTuple):
    pidnr: float
    pidn0s: float
    pidni: float
    pvtr: float
    pvtrn: float
    pvti: float
    pvtin: float
    pvts: float
    rslopermax: float
    rslopesmax: float
    rslopegmax: float
    rslopeimax: float
    rsloperbmax: float
    rslopesbmax: float
    rslopeibmax: float
    rslopermmax: float
    rslopesmmax: float
    rslopegmmax: float
    rslopeimmax: float
    rsloperdmax: float
    rslopesdmax: float
    rslopegdmax: float
    rslopeidmax: float
    rsloper2max: float
    rslopes2max: float
    rslopeg2max: float
    rslopei2max: float
    rsloper3max: float
    rslopes3max: float
    rslopeg3max: float
    rslopei3max: float


class SlopeOutputs(NamedTuple):
    rslope_r: torch.Tensor
    rslope_s: torch.Tensor
    rslope_g: torch.Tensor
    rslope_i: torch.Tensor
    rslopeb_r: torch.Tensor
    rslopeb_s: torch.Tensor
    rslopeb_g: torch.Tensor
    rslopeb_i: torch.Tensor
    rslopemu_r: torch.Tensor
    rslopemu_s: torch.Tensor
    rslopemu_g: torch.Tensor
    rslopemu_i: torch.Tensor
    rsloped_r: torch.Tensor
    rsloped_s: torch.Tensor
    rsloped_g: torch.Tensor
    rsloped_i: torch.Tensor
    rslope2_r: torch.Tensor
    rslope2_s: torch.Tensor
    rslope2_g: torch.Tensor
    rslope2_i: torch.Tensor
    rslope3_r: torch.Tensor
    rslope3_s: torch.Tensor
    rslope3_g: torch.Tensor
    rslope3_i: torch.Tensor
    vt_r: torch.Tensor
    vt_s: torch.Tensor
    vt_g: torch.Tensor
    vt_i: torch.Tensor
    vtn_r: torch.Tensor
    vtn_i: torch.Tensor
    n0sfac: torch.Tensor


class SlopeRainOutputs(NamedTuple):
    rslope_r: torch.Tensor
    rslopeb_r: torch.Tensor
    rslopemu_r: torch.Tensor
    rsloped_r: torch.Tensor
    rslope2_r: torch.Tensor
    rslope3_r: torch.Tensor
    vt_r: torch.Tensor
    vtn_r: torch.Tensor


def _rgamma(x: float) -> float:
    """Fortran `rgmma(x) = exp(GAMMLN(x)) = Γ(x)` 직역. GAMMLN은 ln(Γ).
    review6 audit에서 부호 수정 (이전 구현은 1/Γ였음). 함수명은 호환을 위해 유지."""
    return exp(lgamma(x))


def _pow_or_one(base: float, exponent: float) -> float:
    return 1.0 if exponent == 0.0 else base**exponent


def _scalar(value: float, ref: torch.Tensor) -> torch.Tensor:
    return torch.as_tensor(value, dtype=ref.dtype, device=ref.device)


def _domain_clamp(x: torch.Tensor) -> torch.Tensor:
    return torch.clamp(x, min=DOMAIN_FLOOR)


def _lamda_from_ratio(ratio: torch.Tensor, exponent: float) -> torch.Tensor:
    """Fortran의 `exp(log(max(...,1.e-30))*(1./exp))` 구조를 그대로 유지."""
    return torch.exp(torch.log(_domain_clamp(ratio)) / exponent)


def _rain_slope_components(
    qr: torch.Tensor,
    nr: torch.Tensor,
    den: torch.Tensor,
    denfac: torch.Tensor,
    *,
    params: SlopeParams,
    include_den_gate: bool,
) -> SlopeRainOutputs:
    qcrmin = _const("QCRMIN", c.QCRMIN)
    nrmin = _const("NRMIN", c.NRMIN)
    mur = _const("MUR", c.MUR)
    bvtr = _const("BVTR", c.BVTR)

    rain_mask = (qr <= qcrmin) | (nr <= nrmin)
    if include_den_gate:
        rain_mask = rain_mask | (den <= 0.0)

    pidnr = _scalar(params.pidnr, qr)
    lamdar = _lamda_from_ratio(pidnr * nr / _domain_clamp(qr * den), DMR)
    rslope_raw = torch.minimum(1.0 / lamdar, _scalar(RAIN_RSLOPE_LIMIT, qr))

    rslope = torch.where(rain_mask, _scalar(params.rslopermax, qr), rslope_raw)
    rslopeb = torch.where(
        rain_mask,
        _scalar(params.rsloperbmax, qr),
        safe_pow(rslope, bvtr),
    )
    rslopemu = torch.where(
        rain_mask,
        _scalar(params.rslopermmax, qr),
        safe_pow(rslope, mur),
    )
    rsloped = torch.where(
        rain_mask,
        _scalar(params.rsloperdmax, qr),
        safe_pow(rslope, DMR),
    )
    rslope2 = torch.where(rain_mask, _scalar(params.rsloper2max, qr), rslope * rslope)
    rslope3 = torch.where(rain_mask, _scalar(params.rsloper3max, qr), rslope2 * rslope)

    vt_r = _scalar(params.pvtr, qr) * rslopeb * denfac
    vtn_r = _scalar(params.pvtrn, qr) * rslopeb * denfac
    zeros = torch.zeros_like(qr)
    vt_r = torch.where(qr <= 0.0, zeros, vt_r)
    vtn_r = torch.where(nr <= 0.0, zeros, vtn_r)

    return SlopeRainOutputs(
        rslope_r=rslope,
        rslopeb_r=rslopeb,
        rslopemu_r=rslopemu,
        rsloped_r=rsloped,
        rslope2_r=rslope2,
        rslope3_r=rslope3,
        vt_r=vt_r,
        vtn_r=vtn_r,
    )


def default_slope_params() -> SlopeParams:
    """`kdm6init`의 slope 파생 상수들을 Python float으로 계산한다.

    Derivations
    -----------
    - `cmr = pi * denr / 6`, `cms = pi * dens / 6`, `cmi = pi * deni / 6`
    - `g1pmr = exp(lgamma(1 + mur)) = Γ(1+mur)`, 같은 패턴으로 snow/ice gamma family
      (review6 audit fix — 이전엔 부호 잘못 짜여 있었음)
    - `pidnr = cmr * g1pdrmr / g1pmr`
    - `pidn0s = cms * n0s * g1pdsms / g1pms`
    - `pidni = cmi * g1pdimi / g1pmi`
    - `pvtr = avtr * g1pdrbrmr / g1pdrmr`
    - `pvtrn = avtr * g1pbrmr / g1pmr`
    - `pvts = avts * g1pdsbsms / g1pdsms`
    - `pvti = avti * g1pdibimi / g1pdimi`
    - `pvtin = avti * g1pbimi / g1pmi`
    - `rslope*max = 1 / lamda*max`, 그리고 b/mu/d/2/3 family는 거듭제곱 전개
    """
    dens = _const("DENS", c.DENS)
    deni = _const("DENI", c.DENI)
    n0s = _const("N0S", c.N0S)
    mur = _const("MUR", c.MUR)
    mus = _const("MUS", c.MUS)
    mug = _const("MUG", c.MUG)
    dms = _const("DMS", c.DMS)
    dmg = _const("DMG", c.DMG)
    bvtr = _const("BVTR", c.BVTR)
    bvts = _const("BVTS", c.BVTS)
    bvti = _const("BVTI", c.BVTI)
    avtr = _const("AVTR", c.AVTR)
    avts = _const("AVTS", c.AVTS)
    avti = _const("AVTI", c.AVTI)
    lamdarmax = _const("LAMDARMAX", c.LAMDARMAX)
    lamdasmax = _const("LAMDASMAX", c.LAMDASMAX)
    lamdaimax = _const("LAMDAIMAX", c.LAMDAIMAX)

    cmr = pi * DENR / 6.0
    cms = pi * dens / 6.0
    cmi = pi * deni / 6.0

    g1pmr = _rgamma(1.0 + mur)
    g1pdrmr = _rgamma(1.0 + DMR + mur)
    g1pdrbrmr = _rgamma(1.0 + DMR + bvtr + mur)
    g1pbrmr = _rgamma(1.0 + bvtr + mur)

    g1pms = _rgamma(1.0 + mus)
    g1pdsms = _rgamma(1.0 + dms + mus)
    g1pdsbsms = _rgamma(1.0 + dms + bvts + mus)

    g1pmi = _rgamma(1.0 + MUI)
    g1pdimi = _rgamma(1.0 + DMI + MUI)
    g1pdibimi = _rgamma(1.0 + DMI + bvti + MUI)
    g1pbimi = _rgamma(1.0 + bvti + MUI)

    pidnr = cmr * g1pdrmr / g1pmr
    pidn0s = cms * n0s * g1pdsms / g1pms
    pidni = cmi * g1pdimi / g1pmi

    pvtr = avtr * g1pdrbrmr / g1pdrmr
    pvtrn = avtr * g1pbrmr / g1pmr
    pvts = avts * g1pdsbsms / g1pdsms
    pvti = avti * g1pdibimi / g1pdimi
    pvtin = avti * g1pbimi / g1pmi

    rslopermax = 1.0 / lamdarmax
    rslopesmax = 1.0 / lamdasmax
    rslopegmax = 1.0 / LAMDAGMAX
    rslopeimax = 1.0 / lamdaimax

    rsloperbmax = rslopermax**bvtr
    rslopesbmax = rslopesmax**bvts
    rslopeibmax = rslopeimax**bvti

    rslopermmax = _pow_or_one(rslopermax, mur)
    rslopesmmax = _pow_or_one(rslopesmax, mus)
    rslopegmmax = _pow_or_one(rslopegmax, mug)
    rslopeimmax = _pow_or_one(rslopeimax, MUI)

    rsloperdmax = rslopermax**DMR
    rslopesdmax = rslopesmax**dms
    rslopegdmax = rslopegmax**dmg
    rslopeidmax = rslopeimax**DMI

    rsloper2max = rslopermax * rslopermax
    rslopes2max = rslopesmax * rslopesmax
    rslopeg2max = rslopegmax * rslopegmax
    rslopei2max = rslopeimax * rslopeimax

    rsloper3max = rsloper2max * rslopermax
    rslopes3max = rslopes2max * rslopesmax
    rslopeg3max = rslopeg2max * rslopegmax
    rslopei3max = rslopei2max * rslopeimax

    return SlopeParams(
        pidnr=pidnr,
        pidn0s=pidn0s,
        pidni=pidni,
        pvtr=pvtr,
        pvtrn=pvtrn,
        pvti=pvti,
        pvtin=pvtin,
        pvts=pvts,
        rslopermax=rslopermax,
        rslopesmax=rslopesmax,
        rslopegmax=rslopegmax,
        rslopeimax=rslopeimax,
        rsloperbmax=rsloperbmax,
        rslopesbmax=rslopesbmax,
        rslopeibmax=rslopeibmax,
        rslopermmax=rslopermmax,
        rslopesmmax=rslopesmmax,
        rslopegmmax=rslopegmmax,
        rslopeimmax=rslopeimmax,
        rsloperdmax=rsloperdmax,
        rslopesdmax=rslopesdmax,
        rslopegdmax=rslopegdmax,
        rslopeidmax=rslopeidmax,
        rsloper2max=rsloper2max,
        rslopes2max=rslopes2max,
        rslopeg2max=rslopeg2max,
        rslopei2max=rslopei2max,
        rsloper3max=rsloper3max,
        rslopes3max=rslopes3max,
        rslopeg3max=rslopeg3max,
        rslopei3max=rslopei3max,
    )


def compute_supcol(t: torch.Tensor) -> torch.Tensor:
    """`273.15 - clamp(t, 153.15, 393.15)`."""
    return _scalar(273.15, t) - torch.clamp(t, min=153.15, max=393.15)


def n0sfac(supcol: torch.Tensor) -> torch.Tensor:
    """`max(min(exp(alpha*supcol), n0smax/n0s), 1.0)`."""
    alpha = _const("ALPHA", c.ALPHA)
    n0s = _const("N0S", c.N0S)
    n0smax = _const("N0SMAX", c.N0SMAX)
    capped = torch.clamp(torch.exp(alpha * supcol), min=1.0, max=n0smax / n0s)
    return isfinite_else(capped, fallback=1.0)


def slope_kdm6_torch(
    qr: torch.Tensor,
    qs: torch.Tensor,
    qg: torch.Tensor,
    qi: torch.Tensor,
    nr: torch.Tensor,
    ni: torch.Tensor,
    den: torch.Tensor,
    denfac: torch.Tensor,
    t: torch.Tensor,
    pidn0g: torch.Tensor,
    pvtg: torch.Tensor,
    bvtg: torch.Tensor,
    rslopegbmax: torch.Tensor,
    params: SlopeParams,
) -> SlopeOutputs:
    """Fortran `slope_kdm6`의 torch 포트."""
    qcrmin = _const("QCRMIN", c.QCRMIN)
    dms = _const("DMS", c.DMS)
    dmg = _const("DMG", c.DMG)
    mus = _const("MUS", c.MUS)
    mug = _const("MUG", c.MUG)
    bvts = _const("BVTS", c.BVTS)
    bvti = _const("BVTI", c.BVTI)
    lamdaimin = _const("LAMDAIMIN", c.LAMDAIMIN)
    lamdaimax = _const("LAMDAIMAX", c.LAMDAIMAX)
    qmin = EPS  # ops.EPS는 현재 Fortran qmin 정합값

    n0sfac_out = n0sfac(compute_supcol(t))

    rain = _rain_slope_components(
        qr,
        nr,
        den,
        denfac,
        params=params,
        include_den_gate=True,
    )

    snow_mask = (qs <= qcrmin) | (den <= 0.0)
    pidn0s = _scalar(params.pidn0s, qs)
    lamdas = _lamda_from_ratio(pidn0s * n0sfac_out / _domain_clamp(qs * den), dms + 1.0)
    rslope_s_raw = 1.0 / lamdas
    rslope_s = torch.where(snow_mask, _scalar(params.rslopesmax, qs), rslope_s_raw)
    rslopeb_s = torch.where(
        snow_mask,
        _scalar(params.rslopesbmax, qs),
        safe_pow(rslope_s, bvts),
    )
    rslopemu_s = torch.where(
        snow_mask,
        _scalar(params.rslopesmmax, qs),
        safe_pow(rslope_s, mus),
    )
    rsloped_s = torch.where(
        snow_mask,
        _scalar(params.rslopesdmax, qs),
        safe_pow(rslope_s, dms),
    )
    rslope2_s = torch.where(snow_mask, _scalar(params.rslopes2max, qs), rslope_s * rslope_s)
    rslope3_s = torch.where(snow_mask, _scalar(params.rslopes3max, qs), rslope2_s * rslope_s)

    graupel_mask = (qg <= qcrmin) | (den <= 0.0) | (pidn0g <= 0.0)
    lamdag = _lamda_from_ratio(pidn0g / _domain_clamp(qg * den), dmg + 1.0)
    rslope_g_raw = 1.0 / lamdag
    rslope_g = torch.where(graupel_mask, _scalar(params.rslopegmax, qg), rslope_g_raw)
    rslopeb_g = torch.where(graupel_mask, rslopegbmax, safe_pow(rslope_g, bvtg))
    rslopemu_g = torch.where(
        graupel_mask,
        _scalar(params.rslopegmmax, qg),
        safe_pow(rslope_g, mug),
    )
    rsloped_g = torch.where(
        graupel_mask,
        _scalar(params.rslopegdmax, qg),
        safe_pow(rslope_g, dmg),
    )
    rslope2_g = torch.where(graupel_mask, _scalar(params.rslopeg2max, qg), rslope_g * rslope_g)
    rslope3_g = torch.where(graupel_mask, _scalar(params.rslopeg3max, qg), rslope2_g * rslope_g)

    ice_mask = (qi <= qmin) | (den <= 0.0) | (ni <= 0.0)
    pidni = _scalar(params.pidni, qi)
    lamdai = _lamda_from_ratio(pidni * ni / _domain_clamp(qi * den), DMI)
    rslope_i_raw = torch.clamp(1.0 / lamdai, min=1.0 / lamdaimax, max=1.0 / lamdaimin)
    rslope_i = torch.where(ice_mask, _scalar(params.rslopeimax, qi), rslope_i_raw)
    rslopeb_i = torch.where(
        ice_mask,
        _scalar(params.rslopeibmax, qi),
        safe_pow(rslope_i, bvti),
    )
    rslopemu_i = torch.where(
        ice_mask,
        _scalar(params.rslopeimmax, qi),
        safe_pow(rslope_i, MUI),
    )
    rsloped_i = torch.where(
        ice_mask,
        _scalar(params.rslopeidmax, qi),
        safe_pow(rslope_i, DMI),
    )
    rslope2_i = torch.where(ice_mask, _scalar(params.rslopei2max, qi), rslope_i * rslope_i)
    rslope3_i = torch.where(ice_mask, _scalar(params.rslopei3max, qi), rslope2_i * rslope_i)

    vt_r = _scalar(params.pvtr, qr) * rain.rslopeb_r * denfac
    vt_s = _scalar(params.pvts, qs) * rslopeb_s * denfac
    vt_g = pvtg * rslopeb_g * denfac
    vt_i = _scalar(params.pvti, qi) * rslopeb_i * denfac

    vt_r = torch.where(qr <= 0.0, torch.zeros_like(qr), vt_r)
    vt_s = torch.where(qs <= 0.0, torch.zeros_like(qs), vt_s)
    vt_g = torch.where(qg <= 0.0, torch.zeros_like(qg), vt_g)
    vt_i = torch.where(qi <= 0.0, torch.zeros_like(qi), vt_i)

    vtn_r = _scalar(params.pvtrn, qr) * rain.rslopeb_r * denfac
    vtn_i = _scalar(params.pvtin, qi) * rslopeb_i * denfac
    vtn_r = torch.where(nr <= 0.0, torch.zeros_like(nr), vtn_r)
    vtn_i = torch.where(ni <= 0.0, torch.zeros_like(ni), vtn_i)

    return SlopeOutputs(
        rslope_r=rain.rslope_r,
        rslope_s=rslope_s,
        rslope_g=rslope_g,
        rslope_i=rslope_i,
        rslopeb_r=rain.rslopeb_r,
        rslopeb_s=rslopeb_s,
        rslopeb_g=rslopeb_g,
        rslopeb_i=rslopeb_i,
        rslopemu_r=rain.rslopemu_r,
        rslopemu_s=rslopemu_s,
        rslopemu_g=rslopemu_g,
        rslopemu_i=rslopemu_i,
        rsloped_r=rain.rsloped_r,
        rsloped_s=rsloped_s,
        rsloped_g=rsloped_g,
        rsloped_i=rsloped_i,
        rslope2_r=rain.rslope2_r,
        rslope2_s=rslope2_s,
        rslope2_g=rslope2_g,
        rslope2_i=rslope2_i,
        rslope3_r=rain.rslope3_r,
        rslope3_s=rslope3_s,
        rslope3_g=rslope3_g,
        rslope3_i=rslope3_i,
        vt_r=vt_r,
        vt_s=vt_s,
        vt_g=vt_g,
        vt_i=vt_i,
        vtn_r=vtn_r,
        vtn_i=vtn_i,
        n0sfac=n0sfac_out,
    )


def slope_rain_torch(
    qr: torch.Tensor,
    nr: torch.Tensor,
    den: torch.Tensor,
    denfac: torch.Tensor,
    t: torch.Tensor,
    params: SlopeParams,
) -> SlopeRainOutputs:
    """Fortran `slope_rain`의 torch 포트.

    주의: 원 Fortran은 default branch에서 `rsloped`를 대입하지 않는다. Python에서는
    미정 값을 둘 수 없으므로 `slope_kdm6`의 rain branch와 동일하게 `rsloperdmax`를
    채워 일관된 oracle 값으로 만든다.
    """
    del t  # Fortran 시그니처 유지용. slope_rain 내부 계산에는 사용되지 않음.
    return _rain_slope_components(
        qr,
        nr,
        den,
        denfac,
        params=params,
        include_den_gate=False,
    )


__all__ = [
    "SlopeParams",
    "SlopeOutputs",
    "SlopeRainOutputs",
    "default_slope_params",
    "compute_supcol",
    "n0sfac",
    "slope_kdm6_torch",
    "slope_rain_torch",
]
