"""
KDM6 cloud DSD diagnostics — B1-B4의 placeholder 의존성 해소 모듈.

원본:
  - module_mp_kdm6.F: 1670-1673 (avedia_c, avedia_r, sigma_c)
  - module_mp_kdm6.F: 1703-1705 (lencon, lenconcr)
  - module_mp_kdm6.F: 842-847   (qcr - sea/land 분기)
  - module_mp_kdm6.F: 3104-3105 (qc0, qc1)
  - module_mp_kdm6.F: 3173      (pidnc = cmc * rgmma(1+dmc/(muc+1)))
  - module_mp_kdm6.F: 770       (lamdac = (pidnc·nc / (qc·den))^(1/dmc))

본 모듈이 산출하는 5개 양은 warm.py의 B1-B4 함수들이 입력으로 받는 placeholder.
Step B 검증 후 B1-B4를 *coordinator*에서 호출할 때 본 진단을 먼저 수행.
"""
from __future__ import annotations

from math import exp, lgamma, pi as _pi
from typing import NamedTuple

import torch

from . import constants as c
from . import fconst as _fc


def _rgmma(x: float) -> float:
    """Fortran `rgmma(x) = exp(GAMMLN(x)) = Γ(x)` 직역. GAMMLN은 ln(Γ)이므로
    rgmma는 *Γ(x)* (1/Γ 아님). 이전 구현은 `exp(-lgamma)` = 1/Γ로 잘못 짜여
    review6 audit에서 발견."""
    # Fortran rgmma = f32 expf(f32 gammln) — differs from exp(lgamma) at non-integer args (step-67 class)
    return _fc.rgmma_f(x)


# ─── Params ──────────────────────────────────────────────────────────────────


class CloudDsdParams(NamedTuple):
    pidnc: float       # cmc · rgmma(1 + dmc/(muc+1))
    dmc: float
    muc: float
    lamdacmax: float
    lamdacmin: float
    g3pmc: float       # rgmma(1 + 3/(muc+1))
    g6pmc: float       # rgmma(1 + 6/(muc+1))
    g4pmr_over_g1pmr: float  # rgmma(4+mur)/rgmma(1+mur)
    qc0: float         # continental critical: 4/3·π·denr·r0³·xncr0/den0
    qc1: float         # maritime    critical: 4/3·π·denr·r0³·xncr1/den0


def default_cloud_dsd_params(*, den0: float | None = None) -> CloudDsdParams:
    """Fortran kdm6init의 cloud-side 파생 상수.

    den0 default = c.DEN0 (1.28 kg/m³, 표준대기).
    """
    if den0 is None:
        den0 = c.DEN0
    cmc = _pi * c.DENR / 6.0
    pidnc = _fc.PIDNC   # f32-stepwise (kdm6init F:3205; see fconst.py)
    g3pmc = _rgmma(1.0 + 3.0 / (c.MUC + 1.0))
    g6pmc = _rgmma(1.0 + 6.0 / (c.MUC + 1.0))
    g1pmr = _rgmma(1.0 + c.MUR)
    g4pmr = _rgmma(4.0 + c.MUR)

    # STEP-91 latent class mirror: kdm6init F:3135-3136 REAL(4) l2r — *xncr BEFORE /den0.
    _qc_pre = _fc._f32(_fc._f32(_fc._f32(_fc._f32(4.0 / 3.0) * _fc.PI) * _fc._f32(c.DENR)) * _fc.powf(c.R0, 3.0))
    qc0 = _fc._f32(_fc._f32(_qc_pre * _fc._f32(c.XNCR0)) / _fc._f32(den0))
    qc1 = _fc._f32(_fc._f32(_qc_pre * _fc._f32(c.XNCR1)) / _fc._f32(den0))

    return CloudDsdParams(
        pidnc=pidnc,
        dmc=c.DMC,
        muc=c.MUC,
        lamdacmax=c.LAMDACMAX,
        lamdacmin=c.LAMDACMIN,
        g3pmc=g3pmc,
        g6pmc=g6pmc,
        g4pmr_over_g1pmr=g4pmr / g1pmr,
        qc0=qc0,
        qc1=qc1,
    )


# ─── Cloud slope (rslopec) ────────────────────────────────────────────────────


def diag_cloud_slope_torch(
    qc: torch.Tensor,
    nc: torch.Tensor,
    den: torch.Tensor,
    *,
    params: CloudDsdParams,
    ncmin_tensor: "torch.Tensor | None" = None,
) -> torch.Tensor:
    """rslopec = 1/lamdac, clamp to [1/lamdacmax, 1/lamdacmin], with the Fortran
    inactive-cloud gate (nc<=ncmin → rslopecmax = 1/lamdacmax).

    lamdac = (pidnc·nc / max(qc·den, 1e-30))^(1/dmc)
    """
    DOMAIN_FLOOR = 1.0e-30
    ratio = params.pidnc * nc / torch.clamp(qc * den, min=DOMAIN_FLOOR)
    lamdac = torch.exp(torch.log(torch.clamp(ratio, min=DOMAIN_FLOOR)) * _fc._f32(1.0 / _fc._f32(params.dmc)))  # Fortran *(1./dmc) — step-65 class
    # STEP-75 SEED (D-B) mirror: Fortran's ACTIVE rslopec is UNCLAMPED (stmt fn
    # lamdac F:802 has no bounds; the lamdacmax SNAP rewrites only nci/n0c). The
    # NaN guard is preserved structurally: the 1e-30 domain floors bound lamdac > 0
    # (no Inf), and the explosive qc/nc~0 cells are exactly the INACTIVE set
    # overwritten below with 1/lamdacmax (Fortran F:1454 same branch).
    rslopec_active = 1.0 / lamdac
    # Fortran F:1603-1608 inactive-cloud branch: (qc<=qmin .or. nc<=ncmin) →
    # rslopec = rslopecmax = 1/lamdacmax. Per-cell ncmin (xland) via ncmin_tensor.
    nc_floor = ncmin_tensor if ncmin_tensor is not None else c.NCMIN
    inactive = (qc <= c.EPS) | (nc <= nc_floor)
    rslopec = torch.where(inactive,
                          torch.full_like(rslopec_active, 1.0 / params.lamdacmax),
                          rslopec_active)
    return rslopec


def diag_species_slope_torch(
    q: torch.Tensor,
    n: torch.Tensor,
    den: torch.Tensor,
    pidn: float,
    dm: float,
    lamdamax: float,
    lamdamin: float,
) -> torch.Tensor:
    """rslope = 1/lamda clamped to [1/lamdamax, 1/lamdamin] (rain/ice species).

    lamda = (pidn·n / max(q·den, 1e-30))^(1/dm). 1:1 mirror of C++
    cloud_dsd::diag_species_slope_torch (the clamped DSD slope). Used by
    build_default_aux_torch for rslope_r/rslope_i. AD-safe (clamp/exp/log only).
    """
    DOMAIN_FLOOR = 1.0e-30
    ratio = pidn * n / torch.clamp(q * den, min=DOMAIN_FLOOR)
    # Fortran multiplies by the REAL(4) reciprocal `*(1./dmc)` — not /dm (step-65
    # lamda evaluation-form class; mirrors C++ cloud_dsd.cpp).
    inv_dm = _fc._f32(1.0 / _fc._f32(dm))
    lamda = torch.exp(torch.log(torch.clamp(ratio, min=DOMAIN_FLOOR)) * inv_dm)
    return torch.clamp(1.0 / lamda, min=1.0 / lamdamax, max=1.0 / lamdamin)


# ─── avedia (cloud, rain) ─────────────────────────────────────────────────────


def diag_avedia_cloud_torch(rslopec: torch.Tensor, *, params: CloudDsdParams) -> torch.Tensor:
    """Fortran 1670: avedia_c = rslopec * g3pmc^(1/3)."""
    return rslopec * (params.g3pmc ** (1.0 / 3.0))


def diag_avedia_rain_torch(rslope_r: torch.Tensor, *, params: CloudDsdParams) -> torch.Tensor:
    """Fortran 1671: avedia_r = rslope_r * (g4pmr/g1pmr)^.3333333 (truncated literal)."""
    return rslope_r * (params.g4pmr_over_g1pmr ** 0.3333333)  # 1:1 fix #4 (cloud avedia uses 1/3, see line 131)


# ─── sigma (cloud DSD width) ──────────────────────────────────────────────────


def diag_sigma_cloud_torch(
    rslopec: torch.Tensor,
    *,
    params: CloudDsdParams,
    strict_fortran: bool = False,
) -> torch.Tensor:
    """Fortran 1673: sigma_c = rslopec * (g6pmc - g3pmc²)^(1/6).

    review6 audit 후 `rgmma = Γ` 직역 적용 → muc=2에서:
        g3pmc = Γ(2) = 1.0, g6pmc = Γ(3) = 2.0, var_factor = 1.0 (positive).
    이전 코드의 `strict_fortran` mode와 EPS clamp는 잘못된 reciprocal-gamma 가정의
    잔재. 이제 Fortran 직역 자체가 안정. clamp는 numerical safety guard로만 유지.
    """
    raw = params.g6pmc - params.g3pmc * params.g3pmc
    if strict_fortran:
        var_factor = raw
    else:
        var_factor = max(raw, 1.0e-30)
    return rslopec * (var_factor ** (1.0 / 6.0))


# ─── lencon, lenconcr ─────────────────────────────────────────────────────────


def diag_lencon_torch(
    qc: torch.Tensor,
    den: torch.Tensor,
    avedia_c: torch.Tensor,
    sigma_c: torch.Tensor,
    *,
    qcrmin: float = c.QCRMIN,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Fortran 1703-1705:
        lencon = 2.7e-2 · den · qc · (1e20/16 · avedia_c · sigma_c³ - 0.4)
        lenconcr = max(1.2 · lencon, qcrmin)

    autoconv → accretion 전환의 임계 값. 음수가 될 수 있어서 후행 max로 가드.
    """
    factor = 1.0e20 / 16.0 * avedia_c * (sigma_c ** 3) - 0.4
    lencon = 2.7e-2 * den * qc * factor
    lenconcr = torch.clamp(1.2 * lencon, min=qcrmin)
    return lencon, lenconcr


# ─── qcr (sea/land 분기) ──────────────────────────────────────────────────────


def diag_qcr_torch(
    sea_mask: torch.Tensor,
    *,
    params: CloudDsdParams,
    ref: torch.Tensor | None = None,
) -> torch.Tensor:
    """Fortran module_mp_kdm6.F:842-847 — sea(slmsk==2) → qc0, land → qc1.

    Physical reasoning: qc0 = qc_base · XNCR0 (XNCR0=5e7, low CCN concentration)
    and qc1 = qc_base · XNCR1 (XNCR1=5e8, high CCN). Higher CCN → smaller
    cloud droplets → harder autoconversion → HIGHER qcr threshold. Ocean air
    is clean (LOW CCN) so it gets the LOWER threshold qc0; land air is dusty
    (HIGH CCN) so it gets the HIGHER threshold qc1. The Param-field names
    `qc0/continental`, `qc1/maritime` in CloudDsdParams are legacy labels
    pinned to the scalar values, not the regime mapping; the regime wiring
    is here and mirrors the operational Fortran assignment.

    Parameters
    ----------
    sea_mask : (B, K) boolean (True = sea)
    ref      : float tensor whose dtype/device the output should match.
               If None, defaults to float64/cpu (legacy behavior).

    Returns
    -------
    qcr : (B, K) tensor with qc0 (sea) or qc1 (land).
    """
    if ref is None:
        dtype = torch.float64
        device = sea_mask.device
    else:
        dtype = ref.dtype
        device = ref.device
    qc0_t = torch.tensor(params.qc0, dtype=dtype, device=device)
    qc1_t = torch.tensor(params.qc1, dtype=dtype, device=device)
    qcr = torch.where(sea_mask, qc0_t, qc1_t)
    return qcr


__all__ = [
    "CloudDsdParams",
    "default_cloud_dsd_params",
    "diag_cloud_slope_torch",
    "diag_avedia_cloud_torch",
    "diag_avedia_rain_torch",
    "diag_sigma_cloud_torch",
    "diag_lencon_torch",
    "diag_qcr_torch",
]
