"""
KDM6 melting / freezing oracle — Step D.

원본: module_mp_kdm6.F (Step D는 여러 영역에 분산):
  D1 melting (1284-1342):
       psmlt + nsmlt + pgmlt + ngmlt + pimlt (instantaneous)
  D2 contact freezing — pinuc + ninuc (1485-1507)
  D3 immersion freezing (Bigg cloud) — pfrzdtc + nfrzdtc (1512-1537)
  D4 rain freezing (Bigg) — pfrzdtr + nfrzdtr (1542-1561)
  D5 enhanced melting — pseml/nseml/pgeml/ngeml (2276-2301)

본 모듈은 sub-step 단위 함수를 누적 추가한다. Step D가 Fortran의 *state mutation 집중*
영역이므로 oracle은 모든 rate를 산출하고 caller가 mutation을 적용한다.
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


# ─── Step D1: Melting (psmlt + pgmlt + pimlt + 그들의 number 효과) ────────────


class MeltingParams(NamedTuple):
    """psmlt/pgmlt/pimlt 시간불변 스칼라.

    precs1/precs2: snow deposition coefficient (Step C4와 동일 산식)
    precg1: graupel deposition coefficient (precg2는 ProgB runtime tensor)
    xlf : latent heat of fusion (Fortran XLF = 3.50e5 J/kg, module_model_constants.F:56)
    t0c : 273.15 K
    """

    precs1: float
    precs2: float
    precg1: float
    xlf: float
    t0c: float
    qcrmin: float


DEFAULT_XLF = 3.50e5  # J/kg, Fortran XLF (module_model_constants.F:56)
DEFAULT_T0C = 273.15


def default_melting_params(*, xlf: float = DEFAULT_XLF) -> MeltingParams:
    g2pms = _rgmma(2.0 + c.MUS)
    g2pmg = _rgmma(2.0 + c.MUG)
    bvts2 = 2.5 + 0.5 * c.BVTS + c.MUS
    g5pbso2 = _rgmma(bvts2)
    precs1 = 4.0 * 0.65 * g2pms
    precs2 = 4.0 * 0.44 * (c.AVTS ** 0.5) * g5pbso2
    precg1 = 4.0 * 0.78 * g2pmg
    return MeltingParams(
        precs1=precs1, precs2=precs2, precg1=precg1,
        xlf=xlf, t0c=DEFAULT_T0C, qcrmin=c.QCRMIN,
    )


class MeltingOutputs(NamedTuple):
    psmlt: torch.Tensor       # snow → rain mass [kg/kg/s]; ≤ 0
    pgmlt: torch.Tensor       # graupel → rain mass; ≤ 0
    pimlt_qi: torch.Tensor    # ice → cloud water (instantaneous, full transfer)
    pimlt_ni: torch.Tensor    # ice number → cloud water number
    sfac: torch.Tensor        # number-side factor for snow (caller applies to nrs)
    gfac: torch.Tensor        # number-side factor for graupel
    delta_brs: torch.Tensor   # brs increment from pgmlt (pgmlt/rhox)


def _venfac_proxy(p: torch.Tensor, t: torch.Tensor, den: torch.Tensor) -> torch.Tensor:
    """Fortran inline `venfac(p, t, den) = (viscos/diffus)^(1/3) / sqrt(viscos) · sqrt(sqrt(den0/den))`.

    *외부에서 사전 진단된 work2*를 사용하는 것이 정합. 본 함수는 fallback용.
    Caller가 work2를 명시 입력으로 넘기는 것이 권장.
    """
    # AD-harden: clamp t≥1K before sqrt/log. t=th·pii can transiently hit ≤0 (the 4D-Var control
    # is th), and torch's product-rule for t·sqrt(t) yields 0·Inf=NaN grad at t=0 (log(0)=-Inf too);
    # the where-gate downstream zeros the FORWARD but Inf×0=NaN still poisons backward. Inert at all
    # physical T (>1K). Mirrors thermo.py's t_safe (identical viscos form). (audit round-3)
    t_safe = torch.clamp(t, min=1.0)
    diffus = 8.794e-5 * torch.exp(torch.log(t_safe) * 1.81) / p
    viscos = 1.496e-6 * (t_safe * torch.sqrt(t_safe)) / (t_safe + 120.0) / den
    den0 = c.DEN0
    return (
        torch.exp(torch.log(viscos / diffus) / 3.0) / torch.sqrt(viscos)
        * torch.sqrt(torch.sqrt(torch.tensor(den0, dtype=t.dtype, device=t.device) / den))
    )


def _xka(t: torch.Tensor, den: torch.Tensor) -> torch.Tensor:
    """Fortran inline `xka(t, den) = 1.414e3 · viscos(t,den) · den`."""
    t_safe = torch.clamp(t, min=1.0)  # AD-harden (see _venfac_proxy): t·sqrt(t) grad = 0·Inf at t=0
    viscos = 1.496e-6 * (t_safe * torch.sqrt(t_safe)) / (t_safe + 120.0) / den
    return 1.414e3 * viscos * den


def melting_torch(
    qs: torch.Tensor,
    qg: torch.Tensor,
    qi: torch.Tensor,
    ni: torch.Tensor,
    t: torch.Tensor,
    p: torch.Tensor,
    den: torch.Tensor,
    rhox: torch.Tensor,            # graupel density (ProgB output)
    n0so: torch.Tensor,
    n0go: torch.Tensor,
    n0sfac: torch.Tensor,
    work2: torch.Tensor,           # venfac (외부 진단). None이면 fallback.
    precg2: torch.Tensor,          # ProgB output (graupel deposition coeff)
    rslope_s: torch.Tensor,
    rslope2_s: torch.Tensor,
    rslopeb_s: torch.Tensor,
    rslopemu_s: torch.Tensor,
    rslope_g: torch.Tensor,
    rslope2_g: torch.Tensor,
    rslopeb_g: torch.Tensor,
    rslopemu_g: torch.Tensor,
    *,
    params: MeltingParams,
    dtcld: float,
) -> MeltingOutputs:
    """Fortran 1284-1342 — psmlt + pgmlt + pimlt.

    Outer gate: T > T0c (warm). 모든 process inactive in cold.

    psmlt/pgmlt: snow/graupel → rain (negative rate, capped by -qs/dt or -qg/dt).
    pimlt: instantaneous ice → cloud water (full transfer of qi/ni).

    *State mutation*: Fortran은 qs/qg/qr/qi/ni/t/brs/nrs를 직접 수정. Oracle은 rate
    + factor만 산출하고 caller가 mutation 적용:
        qs_new = qs + psmlt
        qr_new = qr - psmlt - pgmlt
        qg_new = qg + pgmlt
        qi_new = qi - pimlt_qi  (즉 0)
        qc_new = qc + pimlt_qi
        nrs_new = nrs - sfac·psmlt - gfac·pgmlt
        brs_new = brs + delta_brs (pgmlt/rhox)
        t_new = t + xlf/cpm·(psmlt + pgmlt - pimlt_qi)
    """
    zero = torch.zeros_like(qs)
    warm = t > params.t0c
    den_safe = torch.clamp(den, min=params.qcrmin)

    # ── psmlt ──────────────────────────────────────────────────────────
    snow_active = warm & (qs > 0)
    coeres_s = rslope2_s * torch.sqrt(torch.clamp(rslope_s * rslopeb_s, min=params.qcrmin)) * rslopemu_s
    psmlt_raw = (
        _xka(t, den) / params.xlf * (params.t0c - t) * n0sfac
        * _pi / 2.0
        * (params.precs1 * n0so * rslope2_s * rslopemu_s
           + params.precs2 * n0so * work2 * coeres_s)
        / den_safe
    )
    psmlt_dt = psmlt_raw * dtcld
    psmlt_capped = torch.minimum(torch.maximum(psmlt_dt, -qs), zero)
    psmlt_dt_active = torch.where(snow_active, psmlt_capped, zero)
    # rate (per second)
    psmlt = psmlt_dt_active / dtcld

    # nsmlt sfac: rslope_s · n0so · n0sfac / max(qs, qcrmin)
    sfac_raw = rslope_s * n0so * n0sfac / torch.clamp(qs, min=params.qcrmin)
    sfac = torch.where(snow_active & (qs > params.qcrmin), sfac_raw, zero)

    # ── pgmlt ──────────────────────────────────────────────────────────
    graupel_active = warm & (qg > 0)
    coeres_g = rslope2_g * torch.sqrt(torch.clamp(rslope_g * rslopeb_g, min=params.qcrmin)) * rslopemu_g
    pgmlt_raw = (
        _xka(t, den) / params.xlf * (params.t0c - t)
        * _pi / 2.0
        * (params.precg1 * n0go * rslope2_g * rslopemu_g
           + precg2 * n0go * work2 * coeres_g)
        / den_safe
    )
    pgmlt_dt = pgmlt_raw * dtcld
    pgmlt_capped = torch.minimum(torch.maximum(pgmlt_dt, -qg), zero)
    pgmlt_dt_active = torch.where(graupel_active, pgmlt_capped, zero)
    pgmlt = pgmlt_dt_active / dtcld

    # ngmlt gfac: rslope_g · n0go / max(qg, qcrmin)
    gfac_raw = rslope_g * n0go / torch.clamp(qg, min=params.qcrmin)
    gfac = torch.where(graupel_active & (qg > params.qcrmin), gfac_raw, zero)

    # delta_brs = pgmlt / max(rhox, dens) (Fortran 1325-1328)
    rhox_safe = torch.clamp(rhox, min=c.DENS)
    delta_brs = torch.where(graupel_active, pgmlt / rhox_safe, zero)

    # ── pimlt: instantaneous melting (T > T0c AND qi > 0) ──────────────
    ice_active = warm & (qi > 0)
    pimlt_qi = torch.where(ice_active, qi, zero)         # full transfer
    pimlt_ni = torch.where(ice_active, ni, zero)

    return MeltingOutputs(
        psmlt=psmlt, pgmlt=pgmlt,
        pimlt_qi=pimlt_qi, pimlt_ni=pimlt_ni,
        sfac=sfac, gfac=gfac, delta_brs=delta_brs,
    )


# ─── Step D2: Contact freezing (pinuc + ninuc) ───────────────────────────────


class ContactFreezingParams(NamedTuple):
    """Meyers (1992) contact freezing parameters.

    Outer gate: supcol > 2 AND qc > qmin.
    Nic = exp(-2.80 + 0.262·supcolt) · 1000   (Meyers curve)
    """
    cmc: float
    muc: float
    g1pmc: float
    g4pmc: float
    rcn: float           # contact nuclei radius (1e-7 m)
    boltzmann: float     # k_B = 1.38e-23 J/K
    xlf: float
    qmin: float
    ncmin: float
    supcol_threshold: float  # 2.0
    # per-cell ncmin override (operational xland path; injected by _kdm6_pure, mirrors C++). None → scalar.
    ncmin_tensor: "torch.Tensor | None" = None


def default_contact_freezing_params(*, xlf: float = DEFAULT_XLF) -> ContactFreezingParams:
    # f32-stepwise kdm6init constants (fconst, step-67 seed class): cmc=(pi_f*1000)/6;
    # g4pmc carries the f32-stepwise argument 1.0f+4.0f/3.0f = 0x40155556 (the
    # double-then-demote arg is 1 ULP low). Mirrors C++ default_contact_freezing_params.
    cmc = _fc.CMC
    g1pmc = _fc.G1PMC
    g4pmc = _fc.G4PMC
    return ContactFreezingParams(
        cmc=cmc, muc=c.MUC, g1pmc=g1pmc, g4pmc=g4pmc,
        rcn=0.1e-6, boltzmann=1.38e-23,
        xlf=xlf, qmin=c.EPS, ncmin=c.NCMIN, supcol_threshold=2.0,  # qmin=epsilon=1e-15 (Fortran F:1485 qc>qmin gate). 1:1 fix #1
    )


class ContactFreezingOutputs(NamedTuple):
    pinuc: torch.Tensor   # qc → qi mass [kg/kg]
    ninuc: torch.Tensor   # nc → ni number [#/kg]


def contact_freezing_torch(
    qc: torch.Tensor,
    nc: torch.Tensor,
    t: torch.Tensor,
    p: torch.Tensor,
    den: torch.Tensor,
    n0c: torch.Tensor,
    rslopec: torch.Tensor,
    rslopec2: torch.Tensor,
    rslopec3: torch.Tensor,
    rslopecmu: torch.Tensor,
    supcol: torch.Tensor,
    *,
    params: ContactFreezingParams,
    dtcld: float,
) -> ContactFreezingOutputs:
    """Fortran 1485-1507 — Meyers contact freezing of cloud water → cloud ice.

    Returns rates over `dtcld` (Fortran 산식이 ·dtcld 후 cap).
    """
    zero = torch.zeros_like(qc)
    active = (supcol > params.supcol_threshold) & (qc > params.qmin)

    den_safe = torch.clamp(den, min=params.qmin)
    supcolt = torch.clamp(supcol, max=70.0)
    # Nic = exp(-2.80+0.262*supcolt)*1000 (F:1487): strict IEEE two-rounding in
    # plain source order — 0.262*supcolt rounds, then -2.80 + (.) rounds (was an
    # addcmul mirror of the -ffp-contract=fast fma — step-67 seed class — before
    # the IEEE transition).
    nic_arg = -2.80 + 0.262 * supcolt
    Nic = torch.exp(nic_arg) * 1000.0

    # Aerosol diffusivity. ele2 (F:1521) is REAL(4) stepwise in gfortran —
    # fconst.ELE2 holds the exact f32 value (C++ fconst::get().ele2 mirror).
    ele1 = 7.37 * t / (288.0 * 10.0 * p) / 100.0
    ele2 = _fc.ELE2
    t_safe = torch.clamp(t, min=1.0)  # AD-harden (see _venfac_proxy): t·sqrt(t) grad = 0·Inf at t=0
    viscos_t = 1.496e-6 * (t_safe * torch.sqrt(t_safe)) / (t_safe + 120.0) / den
    difa = ele2 * t * (1.0 + ele1 / params.rcn) / (viscos_t * den)

    pinuc_raw = (
        params.cmc * difa * 2.0 * _pi * Nic * n0c / den_safe / (params.muc + 1.0)
        * params.g4pmc * rslopecmu * rslopec3 * rslopec2 * dtcld
    )
    pinuc = torch.where(active, torch.minimum(pinuc_raw, qc), zero)

    nc_floor = params.ncmin_tensor if params.ncmin_tensor is not None else params.ncmin  # per-cell xland ncmin (C++ parity)
    nc_active = active & (nc > nc_floor)
    ninuc_raw = (
        difa * 2.0 * _pi * Nic * n0c / (params.muc + 1.0)
        * params.g1pmc * rslopecmu * rslopec2 * dtcld
    )
    ninuc = torch.where(nc_active, torch.minimum(ninuc_raw, nc), zero)
    return ContactFreezingOutputs(pinuc=pinuc, ninuc=ninuc)


# ─── Step D3: Bigg cloud freezing (pfrzdtc + nfrzdtc) ────────────────────────


class BiggCloudParams(NamedTuple):
    """Bigg (1953) cloud water freezing.

    Outer gate: supcol > 0 AND qc > qmin.
    pfrzdtc = cmc²·pfrz1·n0c/den/denr/(muc+1)·(exp(pfrz2·supcolt)-1)
             · g1p2dcomuc1·rslopecmu·rslopecd²·rslopec · dtcld
    """
    cmc: float
    denr: float
    muc: float
    pfrz1: float
    pfrz2: float
    g1p2dcomuc1: float
    g1pdcomuc1: float
    qmin: float
    ncmin: float
    # per-cell ncmin override (operational xland path; injected by _kdm6_pure, mirrors C++). None → scalar.
    ncmin_tensor: "torch.Tensor | None" = None


def default_bigg_cloud_params() -> BiggCloudParams:
    # fconst routing (C++ default_bigg_cloud_params mirror): cmc f32-stepwise;
    # g1p2dcomuc1=Γ_f(3), g1pdcomuc1=Γ_f(2) (integer args — same values as _rgmma).
    cmc = _fc.CMC
    g1p2dcomuc1 = _fc.G1P2DCOMUC1
    g1pdcomuc1 = _fc.G1PDCOMUC1
    return BiggCloudParams(
        cmc=cmc, denr=c.DENR, muc=c.MUC,
        pfrz1=c.PFRZ1, pfrz2=c.PFRZ2,
        g1p2dcomuc1=g1p2dcomuc1, g1pdcomuc1=g1pdcomuc1,
        qmin=c.EPS, ncmin=c.NCMIN,  # qmin=epsilon=1e-15 (Fortran F:1512 qc>qmin gate). 1:1 fix #1
    )


class BiggCloudOutputs(NamedTuple):
    pfrzdtc: torch.Tensor
    nfrzdtc: torch.Tensor


def bigg_cloud_freezing_torch(
    qc: torch.Tensor,
    nc: torch.Tensor,
    den: torch.Tensor,
    n0c: torch.Tensor,
    rslopec: torch.Tensor,
    rslopecd: torch.Tensor,
    rslopecmu: torch.Tensor,
    supcol: torch.Tensor,
    *,
    params: BiggCloudParams,
    dtcld: float,
) -> BiggCloudOutputs:
    """Fortran 1512-1537 — Bigg immersion freezing of cloud water → ice."""
    zero = torch.zeros_like(qc)
    active = (supcol > 0) & (qc > params.qmin)

    den_safe = torch.clamp(den, min=params.qmin)
    supcolt = torch.clamp(supcol, max=70.0)
    bigg_factor = torch.exp(params.pfrz2 * supcolt) - 1.0

    pfrzdtc_raw = (
        params.cmc * params.cmc * params.pfrz1 * n0c / den_safe / params.denr
        / (params.muc + 1.0) * bigg_factor * params.g1p2dcomuc1
        * rslopecmu * rslopecd * rslopecd * rslopec * dtcld
    )
    pfrzdtc = torch.where(active, torch.minimum(pfrzdtc_raw, qc), zero)

    nc_floor = params.ncmin_tensor if params.ncmin_tensor is not None else params.ncmin  # per-cell xland ncmin (C++ parity)
    nc_active = active & (nc > nc_floor)
    nfrzdtc_raw = (
        params.cmc * params.pfrz1 * n0c / params.denr / (params.muc + 1.0)
        * bigg_factor * params.g1pdcomuc1 * rslopecmu * rslopec * rslopecd * dtcld
    )
    nfrzdtc = torch.where(nc_active, torch.minimum(nfrzdtc_raw, nc), zero)
    return BiggCloudOutputs(pfrzdtc=pfrzdtc, nfrzdtc=nfrzdtc)


# ─── Step D4: Bigg rain freezing (pfrzdtr + nfrzdtr) ─────────────────────────


class BiggRainParams(NamedTuple):
    cmr: float
    denr: float
    pfrz1: float
    pfrz2: float
    g1pdrmr: float
    g1p2drmr: float
    qmin: float
    nrmin: float


def default_bigg_rain_params() -> BiggRainParams:
    cmr = _pi * c.DENR / 6.0
    g1pdrmr = _rgmma(1.0 + c.DMR + c.MUR)
    g1p2drmr = _rgmma(1.0 + 2.0 * c.DMR + c.MUR)
    return BiggRainParams(
        cmr=cmr, denr=c.DENR,
        pfrz1=c.PFRZ1, pfrz2=c.PFRZ2,
        g1pdrmr=g1pdrmr, g1p2drmr=g1p2drmr,
        qmin=c.EPS, nrmin=c.NRMIN,  # qmin only feeds clamp(den,qmin) (den~1, inert); gate is qr>0. EPS for consistency. 1:1 fix #1
    )


class BiggRainOutputs(NamedTuple):
    pfrzdtr: torch.Tensor       # qr → qg [kg/kg]
    nfrzdtr: torch.Tensor       # nr → 손실
    delta_brs: torch.Tensor     # brs += pfrzdtr/denr


def bigg_rain_freezing_torch(
    qr: torch.Tensor,
    nr: torch.Tensor,
    den: torch.Tensor,
    n0r: torch.Tensor,
    rslope_r: torch.Tensor,
    rsloped_r: torch.Tensor,
    rslopemu_r: torch.Tensor,
    supcol: torch.Tensor,
    *,
    params: BiggRainParams,
    dtcld: float,
) -> BiggRainOutputs:
    """Fortran 1542-1561 — Bigg freezing of rain → graupel.

    State mutation outputs:
        qg += pfrzdtr,   qr -= pfrzdtr,   brs += delta_brs (= pfrzdtr/denr),
        nr -= nfrzdtr,   t += xlf/cpm·pfrzdtr  (caller applies)
    """
    zero = torch.zeros_like(qr)
    active = (supcol > 0) & (qr > 0)

    den_safe = torch.clamp(den, min=params.qmin)
    supcolt = torch.clamp(supcol, max=70.0)
    bigg_factor = torch.exp(params.pfrz2 * supcolt) - 1.0

    pfrzdtr_raw = (
        params.cmr * params.cmr * params.pfrz1 * n0r / den_safe / params.denr
        * bigg_factor * rsloped_r * rsloped_r * rslopemu_r * rslope_r
        * params.g1p2drmr * dtcld
    )
    pfrzdtr = torch.where(active, torch.minimum(pfrzdtr_raw, qr), zero)

    nr_active = active & (nr > params.nrmin)
    nfrzdtr_raw = (
        params.cmr / params.denr * params.pfrz1 * n0r * bigg_factor
        * params.g1pdrmr * rslope_r * rsloped_r * rslopemu_r * dtcld
    )
    nfrzdtr = torch.where(nr_active, torch.minimum(nfrzdtr_raw, nr), zero)

    delta_brs = pfrzdtr / params.denr
    return BiggRainOutputs(pfrzdtr=pfrzdtr, nfrzdtr=nfrzdtr, delta_brs=delta_brs)


# ─── Step D5: Enhanced melting (pseml/nseml + pgeml/ngeml) ────────────────────


class EnhancedMeltingParams(NamedTuple):
    cliq: float          # specific heat of liquid water (kdm6init INPUT)
    xlf: float
    qcrmin: float


DEFAULT_CLIQ = 4190.0  # J/kg/K, Fortran cliq (module_model_constants.F:27)


def default_enhanced_melting_params(*, cliq: float = DEFAULT_CLIQ,
                                    xlf: float = DEFAULT_XLF) -> EnhancedMeltingParams:
    return EnhancedMeltingParams(cliq=cliq, xlf=xlf, qcrmin=c.QCRMIN)


class EnhancedMeltingOutputs(NamedTuple):
    pseml: torch.Tensor   # snow → rain enhanced (≤ 0)
    nseml: torch.Tensor   # snow number → rain
    pgeml: torch.Tensor   # graupel → rain
    ngeml: torch.Tensor


def enhanced_melting_torch(
    qs: torch.Tensor,
    qg: torch.Tensor,
    paacw: torch.Tensor,    # C2c output
    psacr: torch.Tensor,    # C2d output
    pgacr: torch.Tensor,    # C2d output
    n0so: torch.Tensor,
    n0go: torch.Tensor,
    n0sfac: torch.Tensor,
    rslope_s: torch.Tensor,
    rslope_g: torch.Tensor,
    supcol: torch.Tensor,
    *,
    params: EnhancedMeltingParams,
    dtcld: float,
) -> EnhancedMeltingOutputs:
    """Fortran 2276-2301 — enhanced melting by accreted water.

    pseml = min(max(cliq·supcol·(paacw+psacr)/xlf, -qs/dtcld), 0)
    pgeml = min(max(cliq·supcol·(paacw+pgacr)/xlf, -qg/dtcld), 0)
    nseml = -sfac·pseml,  ngeml = -gfac·pgeml
    Outer gate: supcol < 0 (warm).

    Note: supcol < 0 → cliq·supcol < 0 → pseml < 0 (sink for snow), 직관 일치.
    """
    zero = torch.zeros_like(qs)
    warm = supcol <= 0

    # ── pseml ──────────────────────────────────────────────────────────
    snow_active = warm & (qs > 0)
    pseml_raw = params.cliq * supcol * (paacw + psacr) / params.xlf
    pseml_capped = torch.minimum(torch.maximum(pseml_raw, -qs / dtcld), zero)
    pseml = torch.where(snow_active, pseml_capped, zero)

    # ── nseml ──────────────────────────────────────────────────────────
    snow_active_qcr = snow_active & (qs > params.qcrmin)
    sfac = rslope_s * n0so * n0sfac / torch.clamp(qs, min=params.qcrmin)
    nseml = torch.where(snow_active_qcr, -sfac * pseml, zero)

    # ── pgeml ──────────────────────────────────────────────────────────
    graupel_active = warm & (qg > 0)
    pgeml_raw = params.cliq * supcol * (paacw + pgacr) / params.xlf
    pgeml_capped = torch.minimum(torch.maximum(pgeml_raw, -qg / dtcld), zero)
    pgeml = torch.where(graupel_active, pgeml_capped, zero)

    graupel_active_qcr = graupel_active & (qg > params.qcrmin)
    gfac = rslope_g * n0go / torch.clamp(qg, min=params.qcrmin)
    ngeml = torch.where(graupel_active_qcr, -gfac * pgeml, zero)

    return EnhancedMeltingOutputs(pseml=pseml, nseml=nseml, pgeml=pgeml, ngeml=ngeml)


__all__ = [
    "MeltingParams",
    "MeltingOutputs",
    "ContactFreezingParams",
    "ContactFreezingOutputs",
    "BiggCloudParams",
    "BiggCloudOutputs",
    "BiggRainParams",
    "BiggRainOutputs",
    "EnhancedMeltingParams",
    "EnhancedMeltingOutputs",
    "default_melting_params",
    "default_contact_freezing_params",
    "default_bigg_cloud_params",
    "default_bigg_rain_params",
    "default_enhanced_melting_params",
    "melting_torch",
    "contact_freezing_torch",
    "bigg_cloud_freezing_torch",
    "bigg_rain_freezing_torch",
    "enhanced_melting_torch",
]
