"""
KDM6 thermodynamics 진단 모듈 — Step F0.

원본: module_mp_kdm6.F (코드 곳곳에 inline functions + 진단 코드):
  - cpm(q) = cpd·(1-max(q,qmin)) + max(q,qmin)·cpv             (Fortran 760)
  - xl(t)  = xlv0 - xlv1·(t-t0c)                                (Fortran 761)
  - supcol = T0c - clamp(t, 153.15, 393.15)                     (Fortran 1274)
  - qs(:,:,1) = psat·exp(log(tr)·xa)·exp(xb·(1-tr))             (Fortran 913)
                ep2·qs / (p - qs)
  - qs(:,:,2) = (T<t0c) psat·exp(log(tr)·xai)·exp(xbi·(1-tr))   (Fortran 921)
                else identical to qs(:,:,1)
  - rh(:,:,1) = max(q/qs1, qmin),  rh(:,:,2) = max(q/qs2, qmin)
  - supsat = max(q, qmin) - qs1
  - denfac = sqrt(den0/den)
  - work2 = venfac(p, t, den) (ventilation factor)

본 모듈은 *순수 thermodynamics* 진단만 담당. coordinator(F1)가 이 진단들을 사용해
Step A-E의 입력을 준비.
"""
from __future__ import annotations

from typing import NamedTuple

import torch

from . import constants as c


# ─── ThermoParams ─────────────────────────────────────────────────────────────


class ThermoParams(NamedTuple):
    """thermodynamic 진단의 시간/공간 불변 스칼라.

    Defaults: WRF 표준 대기 값. 운영 시 kdm6init이 외부 입력으로 받는 값들.
    """
    cpd: float          # specific heat dry air (J/kg/K) — 1004.5
    cpv: float          # specific heat water vapor — 1846
    cliq: float         # specific heat liquid water — 4190 (Fortran cliq)
    cice: float         # specific heat ice — 2106
    rv: float           # gas constant water vapor — 461.6 (Fortran r_v)
    rd: float           # gas constant dry air — 287.0 (Fortran r_d)
    t0c: float          # 273.15
    ttp: float          # triple-point T = t0c + 0.01 = 273.16
    xlv0: float         # latent heat vaporization at t0c — 2.5e6
    xls: float          # latent heat sublimation — 2.85e6 (Fortran XLS)
    xa: float           # Goff-Gratch exponent (water): -dldt/rv
    xb: float           # xa + hvap/(rv·ttp)
    xai: float          # ice version
    xbi: float          # ice version
    psat: float         # saturation vapor pressure at ttp (Pa) — 610.78
    ep2: float          # rd/rv ≈ 0.622
    den0: float         # reference density (1.28 kg/m³)
    qmin: float         # 1e-15


def default_thermo_params() -> ThermoParams:
    """WRF 표준 대기 default — Fortran share/module_model_constants.F 값 (significant-digit precision).
    r_d=287., r_v=461.6, cp=7*r_d/2=1004.5, cpv=4*r_v=1846.4, cliq=4190., XLS=2.85E6.
    """
    cpd = 1004.5
    cpv = 1846.4          # = 4*r_v (Fortran cpv = 4.*r_v)
    cliq = 4190.0         # Fortran cliq
    cice = 2106.0
    rv = 461.6            # Fortran r_v
    rd = 287.0            # Fortran r_d
    t0c = 273.15
    ttp = t0c + 0.01
    xlv0 = 2.5e6
    xls = 2.85e6          # Fortran XLS
    psat = 610.78
    ep2 = rd / rv

    # Goff-Gratch derivations — Fortran module_mp_kdm6.F:901-908. Note `cvap = cpv` so
    # dldt = cvap - cliq = cpv - cliq (NOT cliq-cpv). xa, xai are POSITIVE.
    dldt = cpv - cliq
    hvap = xlv0
    xa = -dldt / rv                # = (cliq - cpv) / rv > 0
    xb = xa + hvap / (rv * ttp)
    dldti = cpv - cice
    hsub = xls
    xai = -dldti / rv              # = (cice - cpv) / rv > 0
    xbi = xai + hsub / (rv * ttp)

    return ThermoParams(
        cpd=cpd, cpv=cpv, cliq=cliq, cice=cice,
        rv=rv, rd=rd, t0c=t0c, ttp=ttp,
        xlv0=xlv0, xls=xls,
        xa=xa, xb=xb, xai=xai, xbi=xbi,
        psat=psat, ep2=ep2, den0=c.DEN0,
        qmin=c.EPS,   # Fortran qmin = epsilon = 1e-15 (model_constants.F:10). 1:1 fix #1.
    )


# ─── 진단 함수 ─────────────────────────────────────────────────────────────


def compute_cpm(q: torch.Tensor, *, params: ThermoParams) -> torch.Tensor:
    """Fortran 760: cpm = cpd·(1-max(q,qmin)) + max(q,qmin)·cpv."""
    q_safe = torch.clamp(q, min=params.qmin)
    return params.cpd * (1.0 - q_safe) + q_safe * params.cpv


def compute_xl(t: torch.Tensor, *, params: ThermoParams) -> torch.Tensor:
    """Fortran module_mp_kdm6.F:761 xlcal(x) = xlv0 - xlv1*(x-t0c), where xlv1 = cl-cpv
    (kdm6init line ~3102). NOTE: this xlv1 is POSITIVE (cliq>cpv), distinct
    from the `dldt = cvap-cliq` (NEGATIVE) used for xa/xb in qs formula.
    See [[feedback-dldt-sign-convention]].
    """
    xlv1 = params.cliq - params.cpv  # Fortran: xlv1 = cl - cpv (module_mp_kdm6.F:3102)
    return params.xlv0 - xlv1 * (t - params.t0c)


def compute_supcol(t: torch.Tensor, *, params: ThermoParams) -> torch.Tensor:
    """Fortran F:1274/3477: supcol = t0c - t (raw, no clamp). 1:1 fix #2."""
    return params.t0c - t


def compute_qs_water(t: torch.Tensor, p: torch.Tensor, *, params: ThermoParams) -> torch.Tensor:
    """Fortran 913-916: saturation mixing ratio w.r.t. water (Goff-Gratch).

        es = psat · exp(log(ttp/t)·xa) · exp(xb·(1 - ttp/t))
        es = min(es, 0.99·p)
        qs = ep2·es / (p - es)
        qs = max(qs, qmin)
    """
    t_safe = torch.clamp(t, min=1.0)
    tr = params.ttp / t_safe
    es = params.psat * torch.exp(torch.log(tr) * params.xa) * torch.exp(params.xb * (1.0 - tr))
    es = torch.minimum(es, 0.99 * p)
    qs = params.ep2 * es / torch.clamp(p - es, min=params.qmin)
    return torch.clamp(qs, min=params.qmin)


def compute_qs_ice(t: torch.Tensor, p: torch.Tensor, *, params: ThermoParams) -> torch.Tensor:
    """Fortran 920-927: saturation w.r.t. ice (T<t0c) or water (T≥t0c).

    Note: 본 oracle은 *T<t0c일 때만 ice 식*, 그 외는 water 식과 동일. Fortran이
    `if (t < ttp) ice else water` 패턴을 사용.
    """
    t_safe = torch.clamp(t, min=1.0)
    tr = params.ttp / t_safe
    es_ice = params.psat * torch.exp(torch.log(tr) * params.xai) * torch.exp(params.xbi * (1.0 - tr))
    es_water = params.psat * torch.exp(torch.log(tr) * params.xa) * torch.exp(params.xb * (1.0 - tr))
    es_raw = torch.where(t < params.ttp, es_ice, es_water)
    es = torch.minimum(es_raw, 0.99 * p)
    qs = params.ep2 * es / torch.clamp(p - es, min=params.qmin)
    return torch.clamp(qs, min=params.qmin)


def compute_diffac(
    xl: torch.Tensor,
    pres: torch.Tensor,
    t: torch.Tensor,
    den: torch.Tensor,
    qs: torch.Tensor,
    *,
    params: ThermoParams,
) -> torch.Tensor:
    """work1 diffusion factor (Fortran module_mp_kdm6.F:775-778):
    diffac = den·xl²/(xka·rv·t²) + 1/(qs·diffus). 1:1 mirror of C++
    thermo::compute_diffac. xka = thermal conductivity, diffus = vapor
    diffusivity. AD-safe (clamp/sqrt/exp/log only, no .item()).
    """
    t_safe = torch.clamp(t, min=1.0)
    viscos = 1.496e-6 * (t_safe * torch.sqrt(t_safe)) / (t_safe + 120.0) \
        / torch.clamp(den, min=params.qmin)
    xka = 1.414e3 * viscos * den
    diffus = 8.794e-5 * torch.exp(torch.log(t_safe) * 1.81) \
        / torch.clamp(pres, min=params.qmin)
    qs_safe = torch.clamp(qs, min=params.qmin)
    term1 = den * xl * xl / (xka * params.rv * t_safe * t_safe)
    term2 = 1.0 / (qs_safe * diffus)
    return term1 + term2


def compute_rh(q: torch.Tensor, qs: torch.Tensor, *, params: ThermoParams) -> torch.Tensor:
    """rh = max(q/qs, qmin)."""
    qs_safe = torch.clamp(qs, min=params.qmin)
    return torch.clamp(q / qs_safe, min=params.qmin)


def compute_supsat(q: torch.Tensor, qs1: torch.Tensor, *, params: ThermoParams) -> torch.Tensor:
    """supsat = max(q, qmin) - qs1."""
    return torch.maximum(q, torch.tensor(params.qmin, dtype=q.dtype, device=q.device)) - qs1


def compute_denfac(den: torch.Tensor, *, params: ThermoParams) -> torch.Tensor:
    """denfac = sqrt(den0/den)."""
    den_safe = torch.clamp(den, min=params.qmin)
    return torch.sqrt(torch.tensor(params.den0, dtype=den.dtype, device=den.device) / den_safe)


def compute_work2_venfac(
    p: torch.Tensor, t: torch.Tensor, den: torch.Tensor,
    *, params: ThermoParams,
) -> torch.Tensor:
    """Fortran 779-780: venfac(p, t, den) = (viscos/diffus)^(1/3) / sqrt(viscos) · sqrt(sqrt(den0/den)).

    Used as `work2` in deposition/sublimation/melting산식.
    """
    # Clamp t≥1K (matching compute_qs_water/compute_diffac) so log(t)/sqrt(t) stay finite —
    # AD-hardening for the 4D-Var control th (t=th·pii could transiently go ≤0 → NaN grad).
    # Inert at all physical T (>1K); mirrored in C++ thermo.cpp venfac (§20).
    t_safe = torch.clamp(t, min=1.0)
    diffus = 8.794e-5 * torch.exp(torch.log(t_safe) * 1.81) / p
    viscos = 1.496e-6 * (t_safe * torch.sqrt(t_safe)) / (t_safe + 120.0) / den
    den0_t = torch.tensor(params.den0, dtype=t.dtype, device=t.device)
    return (
        # Fortran F:779 venfac uses the truncated literal .3333333 (NOT 1./3.); 1:1 fix (cf. avedia #4/#11).
        torch.exp(torch.log(viscos / diffus) * 0.3333333) / torch.sqrt(viscos)
        * torch.sqrt(torch.sqrt(den0_t / torch.clamp(den, min=params.qmin)))
    )


__all__ = [
    "ThermoParams",
    "default_thermo_params",
    "compute_cpm",
    "compute_xl",
    "compute_supcol",
    "compute_qs_water",
    "compute_qs_ice",
    "compute_rh",
    "compute_supsat",
    "compute_denfac",
    "compute_work2_venfac",
]
