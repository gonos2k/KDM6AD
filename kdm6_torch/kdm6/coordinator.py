"""
KDM6 kdm62D coordinator — Step F.

각 timestep의 microphysics chain을 *순수 함수* 형태로 묶는다. caller(F4 marshaling)는
Fortran-side state를 tensor로 변환 → coordinator 호출 → 결과 tensor를 Fortran state로
write-back.

본 파일은 sub-phase별 함수를 누적한다:
  F1a (현재): preamble — thermodynamics + cloud DSD + ProgB + slope diagnostics
  F1b: warm phase (B1-B5)
  F1c: cold phase (C1-C6)
  F1d: melt/freeze phase (D1-D5)
  F1e: state mutation update
  F2-F4: sub-cycling, marshaling

호출 순서:
    state, forcing → preamble (F1a) → warm (F1b) → cold (F1c) → melt (F1d)
                  → state update (F1e) → sedimentation (E with Step E module)
                  → surface accumulation
"""
from __future__ import annotations

import math
from typing import NamedTuple

import torch

from . import thermo as _thermo
from . import cloud_dsd as _dsd
from . import progb as _progb
from . import slope as _slope
from . import warm as _warm
from . import satadj as _satadj
from . import cold as _cold
from . import melt_freeze as _mf
from . import sedimentation as _sed
from . import constants as c


# ─── Step F1a: Preamble ──────────────────────────────────────────────────────


class CoordinatorState(NamedTuple):
    """Microphysics state — caller가 직접 mutation하지 않고 *new state*를 받는다."""
    qv: torch.Tensor   # water vapor
    qc: torch.Tensor   # cloud water
    qr: torch.Tensor   # rain
    qs: torch.Tensor   # snow
    qg: torch.Tensor   # graupel
    qi: torch.Tensor   # cloud ice
    nc: torch.Tensor   # cloud number
    nr: torch.Tensor   # rain number
    ni: torch.Tensor   # ice number
    brs: torch.Tensor  # graupel volume mixing ratio
    t: torch.Tensor    # temperature


class CoordinatorForcing(NamedTuple):
    """Microphysics forcing (외부 진단)."""
    p: torch.Tensor    # pressure [Pa]
    den: torch.Tensor  # air density
    delz: torch.Tensor # layer thickness
    dend: torch.Tensor # density × delz


class CoordinatorParams(NamedTuple):
    """모든 sub-module의 params를 하나로 묶음."""
    thermo: _thermo.ThermoParams
    cloud_dsd: _dsd.CloudDsdParams
    progb: _progb.ProgBParams
    slope: _slope.SlopeParams


def default_coordinator_params() -> CoordinatorParams:
    return CoordinatorParams(
        thermo=_thermo.default_thermo_params(),
        cloud_dsd=_dsd.default_cloud_dsd_params(),
        progb=_progb.default_progb_params(),
        slope=_slope.default_slope_params(),
    )


class PreambleOutputs(NamedTuple):
    """F1a 진단 결과 — 후속 phase의 입력으로 사용."""
    # Thermodynamics
    cpm: torch.Tensor
    xl: torch.Tensor
    supcol: torch.Tensor
    qs1: torch.Tensor          # saturation w.r.t. water
    qs2: torch.Tensor          # saturation w.r.t. ice
    rh_w: torch.Tensor         # rh w.r.t. water
    rh_ice: torch.Tensor       # rh w.r.t. ice
    supsat: torch.Tensor
    denfac: torch.Tensor
    work2: torch.Tensor        # venfac

    # Cloud DSD
    rslopec: torch.Tensor
    avedia_c: torch.Tensor
    avedia_r: torch.Tensor
    sigma_c: torch.Tensor
    lencon: torch.Tensor
    lenconcr: torch.Tensor

    # ProgB outputs
    progb: _progb.ProgBOutputs   # rhox, bg, cmg, pidn0g, avtg, bvtg, ..., precg2

    # Slope outputs
    slope: _slope.SlopeOutputs   # rslope_r/s/g/i, rslopeb_*, rslope2_*, rslope3_*, rslopemu_*, rsloped_*, vt_*, vtn_*, n0sfac


def preamble_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    sea_mask: torch.Tensor,           # (B, K) bool — for qcr (continental vs maritime)
    *,
    params: CoordinatorParams,
) -> PreambleOutputs:
    """F1a — thermodynamics + cloud DSD + ProgB + slope diagnostics 한 번에.

    *No state mutation*: state/forcing read-only. 모든 결과를 PreambleOutputs로 반환.
    """
    # ── Thermodynamics ──────────────────────────────────────────────────
    cpm = _thermo.compute_cpm(state.qv, params=params.thermo)
    xl = _thermo.compute_xl(state.t, params=params.thermo)
    supcol = _thermo.compute_supcol(state.t, params=params.thermo)
    qs1 = _thermo.compute_qs_water(state.t, forcing.p, params=params.thermo)
    qs2 = _thermo.compute_qs_ice(state.t, forcing.p, params=params.thermo)
    rh_w = _thermo.compute_rh(state.qv, qs1, params=params.thermo)
    rh_ice = _thermo.compute_rh(state.qv, qs2, params=params.thermo)
    supsat = _thermo.compute_supsat(state.qv, qs1, params=params.thermo)
    denfac = _thermo.compute_denfac(forcing.den, params=params.thermo)
    work2 = _thermo.compute_work2_venfac(forcing.p, state.t, forcing.den, params=params.thermo)

    # ── Cloud DSD ──────────────────────────────────────────────────────
    rslopec = _dsd.diag_cloud_slope_torch(state.qc, state.nc, forcing.den, params=params.cloud_dsd)
    avedia_c = _dsd.diag_avedia_cloud_torch(rslopec, params=params.cloud_dsd)
    sigma_c = _dsd.diag_sigma_cloud_torch(rslopec, params=params.cloud_dsd)
    lencon, lenconcr = _dsd.diag_lencon_torch(state.qc, forcing.den, avedia_c, sigma_c)
    # qcr is computed by caller via diag_qcr_torch(sea_mask).

    # ── ProgB (graupel density 진단) ────────────────────────────────────
    progb_out = _progb.progb_param_torch(state.qg, state.brs, params=params.progb)

    # ── Slope (4-species) ───────────────────────────────────────────────
    slope_out = _slope.slope_kdm6_torch(
        qr=state.qr, qs=state.qs, qg=state.qg, qi=state.qi,
        nr=state.nr, ni=state.ni,
        den=forcing.den, denfac=denfac, t=state.t,
        pidn0g=progb_out.pidn0g, pvtg=progb_out.pvtg, bvtg=progb_out.bvtg,
        rslopegbmax=progb_out.rslopegbmax,
        params=params.slope,
    )

    # avedia_r uses rslope_r from slope module
    avedia_r = _dsd.diag_avedia_rain_torch(slope_out.rslope_r, params=params.cloud_dsd)

    return PreambleOutputs(
        cpm=cpm, xl=xl, supcol=supcol,
        qs1=qs1, qs2=qs2, rh_w=rh_w, rh_ice=rh_ice, supsat=supsat,
        denfac=denfac, work2=work2,
        rslopec=rslopec, avedia_c=avedia_c, avedia_r=avedia_r,
        sigma_c=sigma_c, lencon=lencon, lenconcr=lenconcr,
        progb=progb_out, slope=slope_out,
    )


# ─── Step F1b: Warm phase chain (B1-B5) ──────────────────────────────────────


class WarmPhaseParams(NamedTuple):
    """B1-B5의 sub-module params 통합."""
    autoconv: _warm.WarmAutoconvParams
    accretion: _warm.WarmAccretionParams
    self_coll: _warm.WarmSelfCollectionParams
    rain_evap: _warm.WarmRainEvapParams
    satadj: _satadj.SatAdjParams


def default_warm_phase_params() -> WarmPhaseParams:
    return WarmPhaseParams(
        autoconv=_warm.default_warm_autoconv_params(),
        accretion=_warm.default_warm_accretion_params(),
        self_coll=_warm.default_warm_self_collection_params(),
        rain_evap=_warm.default_warm_rain_evap_params(),
        satadj=_satadj.default_satadj_params(),
    )


class WarmPhaseOutputs(NamedTuple):
    """B1-B5 모든 rate."""
    praut: torch.Tensor       # B1 mass autoconv (qc → qr)
    nraut: torch.Tensor       # B1 number
    pracw: torch.Tensor       # B2 mass accretion
    nracw: torch.Tensor
    nccol: torch.Tensor       # B3 cloud self-collection
    nrcol: torch.Tensor       # B3 rain self-collection + breakup
    prevp: torch.Tensor       # B4 rain evap
    pcond: torch.Tensor       # B5 saturation adjustment (qv ↔ qc)


def warm_phase_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    pre: PreambleOutputs,
    n0r: torch.Tensor,            # (B, K) — caller-supplied (slope from nr/(rslope·rslopemu·g1pmr))
    work1_r: torch.Tensor,         # (B, K) — caller-supplied rain capacitance
    qcr: torch.Tensor,             # (B, K) — caller-supplied (diag_qcr_torch with sea_mask)
    *,
    params: WarmPhaseParams,
    dtcld: float,
) -> WarmPhaseOutputs:
    """F1b — warm phase chain. 모든 phase rate를 묶어 반환.

    Process order (Fortran 1739-1855 + B5 saturation adjustment 2990-3011):
      B1 autoconv  (qc→qr mass+number)
      B2 accretion (qc←rain mass+number)
      B3 self-collection (cloud + rain + break-up)
      B4 rain evap/cond (qr↔qv)
      B5 saturation adjustment (qv↔qc)

    *No state mutation* — caller가 F1e에서 적용.
    """
    # rslopec3 = rslopec^3 (derived helper)
    rslopec3 = pre.rslopec * pre.rslopec * pre.rslopec

    # ── B1: Autoconversion ─────────────────────────────────────────────
    praut, nraut = _warm.autoconv_torch(
        state.qc, state.nc, state.qr, state.nr, forcing.den,
        qcr, pre.lenconcr,
        params=params.autoconv, dtcld=dtcld,
    )

    # ── B2: Accretion ──────────────────────────────────────────────────
    pracw, nracw = _warm.accretion_torch(
        state.qc, state.nc, state.qr, state.nr, forcing.den,
        pre.avedia_r, rslopec3, pre.slope.rslope3_r, pre.lenconcr,
        params=params.accretion, dtcld=dtcld,
    )

    # ── B3: Self-collection ────────────────────────────────────────────
    nccol, nrcol = _warm.self_collection_torch(
        state.nc, state.nr, state.qr,
        pre.avedia_c, pre.avedia_r, rslopec3, pre.slope.rslope3_r, pre.lenconcr,
        params=params.self_coll,
    )

    # ── B4: Rain evaporation/condensation ──────────────────────────────
    prevp = _warm.rain_evap_torch(
        state.qr, pre.rh_w, pre.supsat,
        n0r, work1_r, pre.work2,
        pre.slope.rslope_r, pre.slope.rslopeb_r,
        pre.slope.rslope2_r, pre.slope.rslopemu_r,
        params=params.rain_evap, dtcld=dtcld,
    )

    # ── B5: Saturation adjustment ──────────────────────────────────────
    pcond = _satadj.saturation_adjustment_torch(
        state.t, state.qv, state.qc, pre.qs1, pre.xl, pre.cpm,
        params=params.satadj, dtcld=dtcld,
    )

    return WarmPhaseOutputs(
        praut=praut, nraut=nraut,
        pracw=pracw, nracw=nracw,
        nccol=nccol, nrcol=nrcol,
        prevp=prevp,
        pcond=pcond,
    )


# ─── Step F1c: Cold phase chain (C1-C6) ──────────────────────────────────────


class ColdPhaseParams(NamedTuple):
    """C1-C6의 sub-module params 통합."""
    ice_accretion: _cold.IceAccretionParams
    ice_to_snow_graupel: _cold.IceToSnowGraupelParams
    number_accretion: _cold.NumberAccretionParams
    cloud_water_riming: _cold.CloudWaterRimingParams
    rsg_collection: _cold.RainSnowGraupelCollectionParams
    hallett_mossop: _cold.HallettMossopParams
    ice_nucleation: _cold.IceNucleationParams
    dep_sub: _cold.DepSubParams
    ice_aggregation: _cold.IceAggregationParams
    snow_evap: _cold.SnowEvapParams
    graupel_evap: _cold.GraupelEvapParams


def default_cold_phase_params() -> ColdPhaseParams:
    return ColdPhaseParams(
        ice_accretion=_cold.default_ice_accretion_params(),
        ice_to_snow_graupel=_cold.default_ice_to_snow_graupel_params(),
        number_accretion=_cold.default_number_accretion_params(),
        cloud_water_riming=_cold.default_cloud_water_riming_params(),
        rsg_collection=_cold.default_rain_snow_graupel_collection_params(),
        hallett_mossop=_cold.default_hallett_mossop_params(),
        ice_nucleation=_cold.default_ice_nucleation_params(),
        dep_sub=_cold.default_dep_sub_params(),
        ice_aggregation=_cold.default_ice_aggregation_params(),
        snow_evap=_cold.default_snow_evap_params(),
        graupel_evap=_cold.default_graupel_evap_params(),
    )


class ColdPhaseOutputs(NamedTuple):
    """C1-C6 모든 rate. HM의 *_adj는 caller가 후속 chain에 사용해야 함."""
    # C1
    praci: torch.Tensor
    piacr: torch.Tensor
    # C2
    psaci: torch.Tensor
    pgaci: torch.Tensor
    # C2b
    nraci: torch.Tensor
    niacr: torch.Tensor
    nsaci: torch.Tensor
    ngaci: torch.Tensor
    # C2c
    psacw: torch.Tensor
    nsacw: torch.Tensor
    pgacw: torch.Tensor
    ngacw: torch.Tensor
    paacw_adj: torch.Tensor   # post-HM
    naacw: torch.Tensor
    piacw: torch.Tensor
    niacw: torch.Tensor
    # C2d
    pracs: torch.Tensor
    psacr_adj: torch.Tensor   # post-HM
    nsacr: torch.Tensor
    pgacr_adj: torch.Tensor   # post-HM
    ngacr: torch.Tensor
    # C2e
    pmulcs: torch.Tensor
    pmulrs: torch.Tensor
    pmulcg: torch.Tensor
    pmulrg: torch.Tensor
    # C2e number outputs — review3#2: ni number balance에 필요
    nmulcs: torch.Tensor
    nmulrs: torch.Tensor
    nmulcg: torch.Tensor
    nmulrg: torch.Tensor
    # C3
    pinud: torch.Tensor
    ninud: torch.Tensor
    # C4
    pidep: torch.Tensor
    psdep: torch.Tensor
    pgdep: torch.Tensor
    ifsat: torch.Tensor
    ice_complete_sublim: torch.Tensor
    # C5
    psaut: torch.Tensor
    nsaut: torch.Tensor
    # C6
    psevp: torch.Tensor
    # C6' (codex#4): graupel evap (Fortran 2496-2505)
    pgevp: torch.Tensor


def cold_phase_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    pre: PreambleOutputs,
    prevp: torch.Tensor,           # B4 output (rain evap rate, used in C3/C4)
    n0i: torch.Tensor,             # caller-supplied
    n0r: torch.Tensor,             # rain intercept (caller-supplied)
    n0so: torch.Tensor,
    n0go: torch.Tensor,
    n0c: torch.Tensor,
    rslopecmu: torch.Tensor,
    rslopecd: torch.Tensor,        # for D3 Bigg cloud (not used here but reserve)
    avedia_i: torch.Tensor,
    work1_ice: torch.Tensor,       # work1(:,:,2) — ice deposition coefficient
    work1_water: torch.Tensor,     # work1(:,:,1) — water diffusivity (review3#1: psevp/pgevp용)
    *,
    params: ColdPhaseParams,
    dtcld: float,
) -> ColdPhaseOutputs:
    """F1c — cold phase chain. 10개 cold module 함수 sequential chain.

    Process order (Fortran 1858-2493):
      C1 ice accretion (praci, piacr)
      C2 ice→snow/graupel (psaci, pgaci)
      C2b number accretion (nraci, niacr, nsaci, ngaci)
      C2c cloud water riming (8 outputs incl. paacw)
      C2d rain-snow-graupel collection (pracs, psacr, nsacr, pgacr, ngacr; nracs=0)
      C2e Hallett-Mossop (pmul*, nmul*, paacw_adj, psacr_adj, pgacr_adj)
      C3 ice nucleation (pinud, ninud, ifsat)
      C4 deposition/sublimation (pidep, psdep, pgdep, ifsat_final, ice_complete_sublim)
      C5 ice aggregation (psaut, nsaut)
      C6 snow evap (psevp)

    HM (C2e)의 *_adj outputs를 caller chain에 사용.
    """
    rslopec3 = pre.rslopec * pre.rslopec * pre.rslopec
    s = pre.slope  # alias

    # ── C1: ice accretion ──────────────────────────────────────────────
    # Fix [codex#3]: aux.n0r 사용 (이전 zeros placeholder는 cold-rain coupling 무효화)
    praci, piacr = _cold.ice_accretion_torch(
        state.qi, state.qr, forcing.den, n0i,
        n0r=n0r,  # codex#3 fix
        vt2r=s.vt_r, vt2i=s.vt_i,
        rslope_r=s.rslope_r, rslope2_r=s.rslope2_r, rslope3_r=s.rslope3_r,
        rslopemu_r=s.rslopemu_r, rsloped_r=s.rsloped_r,
        rslope_i=s.rslope_i, rslope2_i=s.rslope2_i, rslope3_i=s.rslope3_i,
        rslopemu_i=s.rslopemu_i, rsloped_i=s.rsloped_i,
        params=params.ice_accretion, dtcld=dtcld,
    )

    # ── C2: ice → snow/graupel ────────────────────────────────────────
    psaci, pgaci = _cold.ice_to_snow_graupel_torch(
        state.qi, state.qs, state.qg, forcing.den,
        n0i, n0so, n0go, s.n0sfac,
        pre.supcol, s.vt_s, s.vt_g, s.vt_i,
        s.rslope_s, s.rslope2_s, s.rslope3_s, s.rslopemu_s,
        s.rslope_g, s.rslope2_g, s.rslope3_g, s.rslopemu_g,
        s.rslope_i, s.rslope2_i, s.rslope3_i, s.rslopemu_i, s.rsloped_i,
        params=params.ice_to_snow_graupel, dtcld=dtcld,
    )

    # ── C2b: number accretion ────────────────────────────────────────
    nraci, niacr, nsaci, ngaci = _cold.number_accretion_torch(
        state.qi, state.qs, state.qg, state.qr, state.ni, state.nr,
        forcing.den, n0i,
        n0r=n0r,  # codex#3 fix
        n0sfac=s.n0sfac, supcol=pre.supcol,
        vt2r=s.vt_r, vt2s=s.vt_s, vt2g=s.vt_g, vt2i=s.vt_i,
        rslope_r=s.rslope_r, rslope2_r=s.rslope2_r, rslope3_r=s.rslope3_r, rslopemu_r=s.rslopemu_r,
        rslope_s=s.rslope_s, rslope2_s=s.rslope2_s, rslope3_s=s.rslope3_s, rslopemu_s=s.rslopemu_s,
        rslope_g=s.rslope_g, rslope2_g=s.rslope2_g, rslope3_g=s.rslope3_g, rslopemu_g=s.rslopemu_g,
        rslope_i=s.rslope_i, rslope2_i=s.rslope2_i, rslope3_i=s.rslope3_i, rslopemu_i=s.rslopemu_i,
        params=params.number_accretion, dtcld=dtcld,
    )

    # ── C2c: cloud water riming ──────────────────────────────────────
    cwr = _cold.cloud_water_riming_torch(
        state.qc, state.nc, state.qs, state.qg, state.qi,
        forcing.den, pre.denfac,
        n0so, n0go, n0i, n0c, s.n0sfac,
        avtg=pre.progb.avtg, g3pbg=pre.progb.g3pbg,
        avedia_i=avedia_i, supcol=pre.supcol,
        rslope3_s=s.rslope3_s, rslopeb_s=s.rslopeb_s, rslopemu_s=s.rslopemu_s,
        rslope3_g=s.rslope3_g, rslopeb_g=s.rslopeb_g, rslopemu_g=s.rslopemu_g,
        rslope3_i=s.rslope3_i, rslopeb_i=s.rslopeb_i, rslopemu_i=s.rslopemu_i,
        rslopec=pre.rslopec, rslopecmu=rslopecmu,
        params=params.cloud_water_riming, dtcld=dtcld,
    )

    # ── C2d: rain-snow-graupel collection ────────────────────────────
    rsgc = _cold.rain_snow_graupel_collection_torch(
        state.qr, state.qs, state.qg, state.nr,
        forcing.den,
        n0r=n0r,  # codex#3 fix
        n0so=n0so, n0go=n0go, n0sfac=s.n0sfac,
        supcol=pre.supcol,
        vt2r=s.vt_r, vt2s=s.vt_s, vt2g=s.vt_g,
        rslope_r=s.rslope_r, rslope2_r=s.rslope2_r, rslope3_r=s.rslope3_r,
        rslopemu_r=s.rslopemu_r, rsloped_r=s.rsloped_r,
        rslope_s=s.rslope_s, rslope2_s=s.rslope2_s, rslope3_s=s.rslope3_s,
        rslopemu_s=s.rslopemu_s, rsloped_s=s.rsloped_s,
        rslope_g=s.rslope_g, rslope2_g=s.rslope2_g, rslope3_g=s.rslope3_g,
        rslopemu_g=s.rslopemu_g,
        params=params.rsg_collection, dtcld=dtcld,
    )

    # ── C2e: Hallett-Mossop multiplication ───────────────────────────
    hm = _cold.hallett_mossop_torch(
        cwr.paacw, rsgc.psacr, rsgc.pgacr,
        state.qc, state.qr, state.qs, state.qg,
        state.t, forcing.den,
        params=params.hallett_mossop,
    )

    # ── C3: ice nucleation ───────────────────────────────────────────
    icenuc = _cold.ice_nucleation_torch(
        pre.supcol, pre.supsat, pre.rh_ice, prevp,
        state.ni, forcing.den,
        params=params.ice_nucleation, dtcld=dtcld,
    )

    # ── C4: deposition/sublimation ───────────────────────────────────
    depsub = _cold.dep_sub_torch(
        state.qi, state.qs, state.qg,
        pre.rh_ice, pre.supcol, pre.supsat,
        prevp, icenuc.pinud, icenuc.ifsat,
        n0i, n0so, n0go, s.n0sfac,
        work1_ice, pre.work2,
        precg2=pre.progb.precg2,
        rslope_s=s.rslope_s, rslope2_s=s.rslope2_s, rslopeb_s=s.rslopeb_s, rslopemu_s=s.rslopemu_s,
        rslope_g=s.rslope_g, rslope2_g=s.rslope2_g, rslopeb_g=s.rslopeb_g, rslopemu_g=s.rslopemu_g,
        rslope2_i=s.rslope2_i, rslopemu_i=s.rslopemu_i,
        params=params.dep_sub, dtcld=dtcld,
    )

    # ── C5: ice aggregation ──────────────────────────────────────────
    psaut, nsaut = _cold.ice_aggregation_torch(
        state.qi, state.ni, state.t, forcing.den, pre.supcol,
        params=params.ice_aggregation, dtcld=dtcld,
    )

    # ── C6: snow evap (warm-only) ────────────────────────────────────
    # review3#1 fix: Fortran 2491 work1(i,k,1)=water diffusivity. ice 분기 아님.
    psevp = _cold.snow_evap_torch(
        state.qs, pre.rh_w, pre.supcol,
        n0so, s.n0sfac, work1_water, pre.work2,
        s.rslope_s, s.rslope2_s, s.rslopeb_s, s.rslopemu_s,
        params=params.snow_evap, dtcld=dtcld,
    )

    # ── C6': graupel evap (warm-only) — codex#4 fix + review3#1 ─────
    # Fortran 2496-2505: psevp와 동일 구조 (work1(:,:,1) water branch),
    # n0sfac 없음, precg2 (ProgB runtime).
    pgevp = _cold.graupel_evap_torch(
        state.qg, pre.rh_w, pre.supcol,
        n0go, work1_water, pre.work2,
        s.rslope_g, s.rslope2_g, s.rslopeb_g, s.rslopemu_g,
        pre.progb.precg2,
        params=params.graupel_evap, dtcld=dtcld,
    )

    return ColdPhaseOutputs(
        praci=praci, piacr=piacr,
        psaci=psaci, pgaci=pgaci,
        nraci=nraci, niacr=niacr, nsaci=nsaci, ngaci=ngaci,
        psacw=cwr.psacw, nsacw=cwr.nsacw,
        pgacw=cwr.pgacw, ngacw=cwr.ngacw,
        paacw_adj=hm.paacw_adj, naacw=cwr.naacw,
        piacw=cwr.piacw, niacw=cwr.niacw,
        pracs=rsgc.pracs, psacr_adj=hm.psacr_adj, nsacr=rsgc.nsacr,
        pgacr_adj=hm.pgacr_adj, ngacr=rsgc.ngacr,
        pmulcs=hm.pmulcs, pmulrs=hm.pmulrs,
        pmulcg=hm.pmulcg, pmulrg=hm.pmulrg,
        nmulcs=hm.nmulcs, nmulrs=hm.nmulrs,
        nmulcg=hm.nmulcg, nmulrg=hm.nmulrg,
        pinud=icenuc.pinud, ninud=icenuc.ninud,
        pidep=depsub.pidep, psdep=depsub.psdep, pgdep=depsub.pgdep,
        ifsat=depsub.ifsat, ice_complete_sublim=depsub.ice_complete_sublim,
        psaut=psaut, nsaut=nsaut,
        psevp=psevp,
        pgevp=pgevp,
    )


# ─── Step F1d: Melt/Freeze phase chain (D1-D5) ───────────────────────────────


class MeltFreezePhaseParams(NamedTuple):
    melting: _mf.MeltingParams
    contact: _mf.ContactFreezingParams
    bigg_cloud: _mf.BiggCloudParams
    bigg_rain: _mf.BiggRainParams
    enhanced_melt: _mf.EnhancedMeltingParams


def default_melt_freeze_phase_params() -> MeltFreezePhaseParams:
    return MeltFreezePhaseParams(
        melting=_mf.default_melting_params(),
        contact=_mf.default_contact_freezing_params(),
        bigg_cloud=_mf.default_bigg_cloud_params(),
        bigg_rain=_mf.default_bigg_rain_params(),
        enhanced_melt=_mf.default_enhanced_melting_params(),
    )


class MeltFreezePhaseOutputs(NamedTuple):
    """D1-D5 모든 rate."""
    # D1
    psmlt: torch.Tensor
    pgmlt: torch.Tensor
    pimlt_qi: torch.Tensor
    pimlt_ni: torch.Tensor
    sfac_melt: torch.Tensor
    gfac_melt: torch.Tensor
    delta_brs_melt: torch.Tensor
    # D2
    pinuc: torch.Tensor
    ninuc: torch.Tensor
    # D3
    pfrzdtc: torch.Tensor
    nfrzdtc: torch.Tensor
    # D4
    pfrzdtr: torch.Tensor
    nfrzdtr: torch.Tensor
    delta_brs_freeze: torch.Tensor
    # D5
    pseml: torch.Tensor
    nseml: torch.Tensor
    pgeml: torch.Tensor
    ngeml: torch.Tensor


def melt_freeze_phase_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    pre: PreambleOutputs,
    cold_out: ColdPhaseOutputs,    # paacw_adj, psacr_adj, pgacr_adj 사용
    n0c: torch.Tensor,
    n0r: torch.Tensor,
    n0so: torch.Tensor,
    n0go: torch.Tensor,
    rslopec: torch.Tensor,
    rslopecmu: torch.Tensor,
    rslopecd: torch.Tensor,
    *,
    params: MeltFreezePhaseParams,
    dtcld: float,
) -> MeltFreezePhaseOutputs:
    """F1d — melt/freeze phase chain.

    Process order:
      D1 melting (T > T0c)
      D2 contact freezing (Meyers, T < -2°C)
      D3 immersion freezing (Bigg cloud, T < T0c)
      D4 rain freezing (Bigg rain, T < T0c)
      D5 enhanced melting (T > T0c, uses cold's paacw_adj/psacr_adj/pgacr_adj)
    """
    s = pre.slope

    # ── D1: Melting (warm) ─────────────────────────────────────────────
    melt_in = _mf.MeltingOutputs._fields  # placeholder for documentation
    melt = _mf.melting_torch(
        state.qs, state.qg, state.qi, state.ni,
        state.t, forcing.p, forcing.den, pre.progb.rhox,
        n0so, n0go, s.n0sfac, pre.work2, pre.progb.precg2,
        s.rslope_s, s.rslope2_s, s.rslopeb_s, s.rslopemu_s,
        s.rslope_g, s.rslope2_g, s.rslopeb_g, s.rslopemu_g,
        params=params.melting, dtcld=dtcld,
    )

    # ── D2: Contact freezing ───────────────────────────────────────────
    rslopec2 = rslopec * rslopec
    rslopec3 = rslopec2 * rslopec
    contact = _mf.contact_freezing_torch(
        state.qc, state.nc, state.t, forcing.p, forcing.den,
        n0c, rslopec, rslopec2, rslopec3, rslopecmu,
        pre.supcol,
        params=params.contact, dtcld=dtcld,
    )

    # ── D3: Bigg cloud ─────────────────────────────────────────────────
    bigg_c = _mf.bigg_cloud_freezing_torch(
        state.qc, state.nc, forcing.den, n0c,
        rslopec, rslopecd, rslopecmu, pre.supcol,
        params=params.bigg_cloud, dtcld=dtcld,
    )

    # ── D4: Bigg rain ──────────────────────────────────────────────────
    bigg_r = _mf.bigg_rain_freezing_torch(
        state.qr, state.nr, forcing.den, n0r,
        s.rslope_r, s.rsloped_r, s.rslopemu_r, pre.supcol,
        params=params.bigg_rain, dtcld=dtcld,
    )

    # ── D5: Enhanced melting (uses cold's adjusted paacw/psacr/pgacr) ──
    enh = _mf.enhanced_melting_torch(
        state.qs, state.qg,
        cold_out.paacw_adj, cold_out.psacr_adj, cold_out.pgacr_adj,
        n0so, n0go, s.n0sfac,
        s.rslope_s, s.rslope_g, pre.supcol,
        params=params.enhanced_melt, dtcld=dtcld,
    )

    return MeltFreezePhaseOutputs(
        psmlt=melt.psmlt, pgmlt=melt.pgmlt,
        pimlt_qi=melt.pimlt_qi, pimlt_ni=melt.pimlt_ni,
        sfac_melt=melt.sfac, gfac_melt=melt.gfac,
        delta_brs_melt=melt.delta_brs,
        pinuc=contact.pinuc, ninuc=contact.ninuc,
        pfrzdtc=bigg_c.pfrzdtc, nfrzdtc=bigg_c.nfrzdtc,
        pfrzdtr=bigg_r.pfrzdtr, nfrzdtr=bigg_r.nfrzdtr,
        delta_brs_freeze=bigg_r.delta_brs,
        pseml=enh.pseml, nseml=enh.nseml,
        pgeml=enh.pgeml, ngeml=enh.ngeml,
    )


# ─── Step F1e: State mutation update ─────────────────────────────────────────


def scale_rates_for_conservation_torch(
    state: CoordinatorState,
    supcol: torch.Tensor,
    warm: WarmPhaseOutputs,
    cold: ColdPhaseOutputs,
    mf: MeltFreezePhaseOutputs,
    *,
    dtcld: float,
):
    """F1d2 — Fortran group conservation budgets (module_mp_kdm6.f90 :2410-2547
    cold-arm + :2607-2678 warm-arm). 14 budgets: value=max(floor,reservoir);
    source=Σ(signed sinks)·dtcld; if source>value scale every listed sink by
    factor=value/source. Bounds the SUM of competing sinks on one species — the
    tier the per-rate caps cannot provide (its absence caused the 806× staged-ice
    over-production). Runs AFTER melt_freeze (D5 read UNSCALED cold rates, as
    Fortran does) and BEFORE state_update; supcol gates cold(pass1)/warm(pass2)
    exactly as state_update's cold_mask=(supcol>0).

    Mirrors C++ scale_rates_for_conservation 1:1. Each `source` is the LITERAL
    Fortran arithmetic on the corresponding rate tensors (the port carries
    Fortran's signs ⇒ identical arithmetic). Rates are scaled IN ORDER,
    sequentially (a rate re-read by a later budget sees its already-scaled
    value). factor=value/max(source,value) is an exact no-op (=1) where
    source≤value (the common case ⇒ existing tests unchanged). pgaut/pgacs ≡ 0
    (dropped, not invented); paacw/naacw appear ×2 in source but scaled once.
    AD-safe: torch.where + maximum, no .item(). Returns scaled (warm, cold, mf).
    """
    dtype = state.qc.dtype
    cold_gate = supcol > 0          # == state_update cold_mask
    warm_gate = supcol <= 0         # complement (warm arm)
    delta2 = ((state.qr < 1.0e-4) & (state.qs < 1.0e-4)).to(dtype)
    delta3 = (state.qr < 1.0e-4).to(dtype)
    one_m_d2 = 1.0 - delta2
    one_m_d3 = 1.0 - delta3
    EPS = 1.0e-15                   # Fortran qmin (matches C++ constants::EPS)

    # Mutable working copies keyed by rate name (names are unique across the
    # three structs). Sequential mutation needs mutable state — NamedTuples are
    # immutable, so we mutate this dict and _replace at the end.
    W = ("praut", "pracw", "prevp", "nraut", "nccol", "nracw", "nrcol")
    C = ("paacw_adj", "piacw", "pmulcs", "pmulcg", "psaut", "pinud", "pidep",
         "praci", "psaci", "pgaci", "pmulrs", "pmulrg", "piacr", "psacr_adj",
         "pgacr_adj", "psdep", "pracs", "pgdep", "naacw", "niacw", "nraci",
         "nsaci", "ngaci", "niacr", "nsaut", "ninud", "nmulcs", "nmulcg",
         "nmulrs", "nmulrg", "nsacr", "ngacr", "psevp", "pgevp")
    M = ("pseml", "pgeml", "nseml", "ngeml")
    r = {nm: getattr(warm, nm) for nm in W}
    r.update({nm: getattr(cold, nm) for nm in C})
    r.update({nm: getattr(mf, nm) for nm in M})

    def limit(reservoir, floor, source_sum, gate, names):
        value = torch.clamp(reservoir, min=floor)
        source = source_sum * dtcld
        factor = torch.where(gate, value / torch.maximum(source, value),
                             torch.ones_like(value))
        for nm in names:
            r[nm] = r[nm] * factor

    # ── PASS 1: cold arm (t<=t0c), gate=cold_gate ──────────────────────────
    limit(state.qc, EPS,                                              # cloud mass :2410
          r["praut"] + r["pracw"] + 2.0 * r["paacw_adj"] + r["piacw"]
          + r["pmulcs"] + r["pmulcg"], cold_gate,
          ("praut", "pracw", "paacw_adj", "piacw", "pmulcs", "pmulcg"))
    limit(state.qi, EPS,                                              # ice mass :2425
          r["psaut"] - r["pinud"] - r["pidep"] + r["praci"] + r["psaci"]
          + r["pgaci"] - r["pmulcs"] - r["pmulrs"] - r["pmulcg"] - r["pmulrg"]
          - r["piacw"], cold_gate,
          ("psaut", "pinud", "pidep", "praci", "psaci", "pgaci", "piacw",
           "pmulcs", "pmulrs", "pmulcg", "pmulrg"))
    limit(state.qr, EPS,                                              # rain mass :2445
          -r["praut"] - r["prevp"] - r["pracw"] + r["piacr"] + r["psacr_adj"]
          + r["pgacr_adj"] + r["pmulrs"] + r["pmulrg"], cold_gate,
          ("praut", "prevp", "pracw", "piacr", "psacr_adj", "pgacr_adj",
           "pmulrs", "pmulrg"))
    limit(state.qs, EPS,                                              # snow mass :2462 (pgaut,pgacs≡0)
          -(r["psdep"] + r["psaut"] + r["paacw_adj"] + r["piacr"] * delta3
            + r["praci"] * delta3 - r["pracs"] * one_m_d2
            + r["psacr_adj"] * delta2 + r["psaci"]), cold_gate,
          ("psdep", "psaut", "paacw_adj", "piacr", "praci", "psaci", "pracs",
           "psacr_adj"))
    limit(state.qg, EPS,                                              # graupel mass :2483 (pgaut,pgacs≡0)
          -(r["pgdep"] + r["piacr"] * one_m_d3 + r["praci"] * one_m_d3
            + r["psacr_adj"] * one_m_d2 + r["pracs"] * one_m_d2 + r["pgaci"]
            + r["paacw_adj"] + r["pgacr_adj"]), cold_gate,
          ("pgdep", "piacr", "praci", "psacr_adj", "pracs", "paacw_adj",
           "pgaci", "pgacr_adj"))
    limit(state.nc, c.NCMIN,                                          # cloud number :2504
          r["nraut"] + r["nccol"] + r["nracw"] + r["niacw"] + 2.0 * r["naacw"],
          cold_gate, ("nraut", "nccol", "nracw", "naacw", "niacw"))
    limit(state.ni, c.NCMIN,                                          # ice number :2518
          r["nraci"] + r["nsaci"] + r["ngaci"] + r["niacr"] + r["nsaut"]
          - r["nmulcs"] - r["nmulcg"] - r["nmulrs"] - r["nmulrg"] - r["ninud"],
          cold_gate,
          ("nraci", "nsaci", "ngaci", "niacr", "nsaut", "ninud", "nmulcs",
           "nmulcg", "nmulrs", "nmulrg"))
    limit(state.nr, c.NRMIN,                                          # rain number :2537
          -r["nraut"] + r["nraci"] + r["nrcol"] + r["niacr"] + r["nsacr"]
          + r["ngacr"], cold_gate,
          ("nraci", "nraut", "nrcol", "niacr", "nsacr", "ngacr"))

    # ── PASS 2: warm arm (t>t0c), gate=warm_gate ───────────────────────────
    limit(state.qc, EPS,                                             # cloud mass :2607
          r["praut"] + r["pracw"] + 2.0 * r["paacw_adj"], warm_gate,
          ("praut", "pracw", "paacw_adj"))
    limit(state.qr, EPS,                                             # rain mass :2619
          -2.0 * r["paacw_adj"] - r["praut"] + r["pseml"] + r["pgeml"]
          - r["pracw"] - r["prevp"], warm_gate,
          ("praut", "prevp", "pracw", "paacw_adj", "pseml", "pgeml"))
    limit(state.qs, c.QCRMIN,                                        # snow mass :2634 (pgacs≡0)
          -r["pseml"] - r["psevp"], warm_gate, ("psevp", "pseml"))
    limit(state.qg, c.QCRMIN,                                        # graupel mass :2645 (pgacs≡0)
          -(r["pgevp"] + r["pgeml"]), warm_gate, ("pgevp", "pgeml"))
    limit(state.nc, c.NCMIN,                                         # cloud number :2656
          r["nraut"] + r["nccol"] + r["nracw"] + 2.0 * r["naacw"], warm_gate,
          ("nraut", "nccol", "nracw", "naacw"))
    limit(state.nr, c.NRMIN,                                         # rain number :2669
          -r["nraut"] + r["nrcol"] - r["nseml"] - r["ngeml"], warm_gate,
          ("nraut", "nrcol", "nseml", "ngeml"))

    warm2 = warm._replace(**{nm: r[nm] for nm in W})
    cold2 = cold._replace(**{nm: r[nm] for nm in C})
    mf2 = mf._replace(**{nm: r[nm] for nm in M})
    return warm2, cold2, mf2


def apply_melt_freeze_inline_torch(
    state: CoordinatorState,
    mf: MeltFreezePhaseOutputs,
    pre: PreambleOutputs,
    *,
    dtcld: float,
    xls: float,
) -> CoordinatorState:
    """Stage-A STEP 1: melt(D1)+freeze(D2-D4) as INLINE pre-state-update mutations
    of a working state, using EXACTLY the signed expressions state_update_torch
    used for these terms (so inline-apply ⟺ zeroing the D1-D4 mf fields is an
    algebraic identity). Functional (_replace), no clamps (final clamps stay in
    state_update_torch). xlf=xls-pre.xl. 1:1 mirror of C++ apply_melt_freeze_inline.
    """
    dtype = state.qc.dtype
    warm_mask = (pre.supcol <= 0).to(dtype)
    cpm_safe = torch.clamp(pre.cpm, min=c.QCRMIN)
    xlf = xls - pre.xl
    return state._replace(
        qc=state.qc + (-mf.pinuc - mf.pfrzdtc + mf.pimlt_qi),
        qr=state.qr + dtcld * (-(mf.psmlt + mf.pgmlt) * warm_mask) - mf.pfrzdtr,
        qs=state.qs + dtcld * mf.psmlt,
        qg=state.qg + dtcld * mf.pgmlt + mf.pfrzdtr,
        qi=state.qi + (mf.pinuc + mf.pfrzdtc - mf.pimlt_qi),
        nc=state.nc + (-mf.ninuc - mf.nfrzdtc + mf.pimlt_ni),
        nr=state.nr + (-mf.nfrzdtr),
        ni=state.ni + (mf.ninuc + mf.nfrzdtc - mf.pimlt_ni),
        brs=state.brs + (dtcld * mf.delta_brs_melt + mf.delta_brs_freeze),
        t=state.t
        + dtcld * xlf / cpm_safe * (mf.psmlt + mf.pgmlt)
        + xlf / cpm_safe * (mf.pinuc + mf.pfrzdtc + mf.pfrzdtr - mf.pimlt_qi),
    )


def state_update_torch(
    state: CoordinatorState,
    pre: PreambleOutputs,
    warm: WarmPhaseOutputs,
    cold: ColdPhaseOutputs,
    mf: MeltFreezePhaseOutputs,
    *,
    dtcld: float,
    xls: float = 2.85e6,   # CONSTANT sublimation latent heat (Fortran XLS); xlf(T)=xls-xl(T) derived
    delta_src: CoordinatorState = None,  # Stage-A STEP 1: state to compute delta2/delta3
                           # from (the ENTRY state) when `state` is a post-melt/freeze
                           # working base; None → use `state`. Mirrors C++ delta_src.
) -> CoordinatorState:
    """F1e — 모든 phase rate를 state에 적용해 새 state 산출.

    Mass balance (per dtcld):
        qv += dtcld·(prevp - pcond - pinud - pidep - psdep - pgdep
                     + psevp - pseml/xlf adjustments)
        qc += dtcld·(pcond - praut - pracw - piacw - psacw - pgacw
                     - paacw_adj - pinuc - pfrzdtc - pmulcs - pmulcg + pimlt_qi)
        qr += dtcld·(praut + pracw + paacw_adj - prevp + (psmlt + pgmlt) - pfrzdtr)
                # T<T0c routing: psacw/pgacw/paacw → qs/qg, psacr/pgacr remain in qr;
                # T>=T0c routing: snow→rain via psmlt/pgmlt; psacr/pgacr stay; pfrzdtr off (cold only)
        qs += dtcld·(psaut + psaci + paacw_adj_warm0 + psacr_adj·H[T<T0c] - psmlt - pseml
                     + pinud_psdep + pmulcs + pmulrs - pgaut + pfrzdtc·... )  # complex routing
        qg += dtcld·(pgaci + paacw_adj·warm0 + pgacr_adj + piacr - pgmlt - pgeml + pfrzdtr + pmulcg + pmulrg)
        qi += dtcld·(pinud + pinuc + pfrzdtc + pidep - praci - psaci - pgaci - pmulcs - pmulrs - pmulcg - pmulrg
                     + piacw - pimlt_qi - psaut)
        brs += delta_brs_melt + delta_brs_freeze  (graupel volume)

    Number balance: 비슷한 구조로 nc, nr, ni 갱신.

    Energy balance (T):
        T += dtcld·xl/cpm·(pcond - prevp - psevp)
           + dtcld·xlf/cpm·(pinud + pidep + psdep + pgdep + pinuc + pfrzdtc + pfrzdtr
                             - psmlt - pgmlt - pimlt_qi - pseml - pgeml)

    Note: Fortran의 모든 mutation을 정확히 직역. T-branch routing은 *cold*=`supcol > 0`,
    *warm*=`supcol < 0` mask로 처리.
    """
    cold_mask = (pre.supcol > 0).to(state.qc.dtype)
    warm_mask = 1.0 - cold_mask  # cold or warm

    # ── Unit policy (review5#1) ──────────────────────────────────────
    # warm/cold module 출력은 *rates* (per second) — F1e에서 dtcld 곱.
    # mf module 일부 출력은 *amounts* (이미 dtcld 적용됨) — 직접 적용:
    #   amount: pinuc/ninuc, pfrzdtc/nfrzdtc, pfrzdtr/nfrzdtr, pimlt_qi/pimlt_ni,
    #           delta_brs_freeze (= pfrzdtr/denr)
    #   rate:   psmlt/pgmlt, pseml/pgeml/nseml/ngeml, delta_brs_melt (= pgmlt/rhox)
    # F1e 안에서 두 group을 분리해 더한다.

    # ── Mass balance ───────────────────────────────────────────────────
    # qv (water vapor)
    dqv = dtcld * (
        # pcond DEFERRED to apply_satadj_step_torch (post-update + post-reclass,
        # Fortran :2906-2915; mirrors C++ apply_satadj_step). NOT applied here.
        - warm.prevp                            # B4 (rain↔vapor; prevp<0이면 qv 증가)
        - cold.pinud                            # C3 deposition nucleation (qv→qi)
        - cold.pidep - cold.psdep - cold.pgdep  # C4 dep/sub (vapor↔ice/snow/graupel)
        - cold.psevp                            # C6 snow evap (psevp<0 → vapor 증가)
        - cold.pgevp                            # C6' graupel evap (pgevp<0 → vapor 증가)
    )
    qv_new = state.qv + dqv

    # qc (cloud water)
    dqc_rate = dtcld * (
        # pcond DEFERRED to apply_satadj_step_torch (see qv). NOT applied here.
        - warm.praut - warm.pracw                                # B1/B2 (qc→qr)
        - cold.piacw                                             # 2680 piacw (qc→qi)
        - 2.0 * cold.paacw_adj                                   # 2681: paacw·2 (qc→qs+qg)
        - cold.pmulcs - cold.pmulcg                              # 2680 C2e HM
    )
    dqc_amount = -mf.pinuc - mf.pfrzdtc + mf.pimlt_qi            # 1556/1586/1391 (amounts)
    dqc = dqc_rate + dqc_amount
    qc_new = state.qc + dqc

    # qr (rain water)
    dqr_rate = dtcld * (
        warm.praut + warm.pracw                   # B1/B2 (qc→qr)
        + warm.prevp                              # 2685 prevp<0 → qr 감소
        - cold.piacr - cold.pgacr_adj - cold.psacr_adj  # 2685-2687 rain collected (sinks)
        - cold.pmulrs - cold.pmulrg               # 2685 HM rain→ice splinter sinks
        - (mf.psmlt + mf.pgmlt) * warm_mask       # D1 psmlt<0 → qr 증가 (qr -= psmlt)
        - mf.pseml - mf.pgeml                     # D5 enhanced melt (pseml<0 → qr 증가)
        + 2.0 * cold.paacw_adj * warm_mask        # #1: WARM arm sheds rimed cloud to RAIN (Fortran :2690 qr+=2*paacw);
                                                  # cold arm routes paacw to qs/qg (below, cold_mask). Mirrors C++.
    )
    dqr_amount = -mf.pfrzdtr                      # 1612 Bigg rain → qg (amount)
    dqr = dqr_rate + dqr_amount
    qr_new = state.qr + dqr

    # ── delta2/delta3 routing flags (Fortran 2516-2519) — review3#5
    #   delta2 = 1 if (qr<1e-4 AND qs<1e-4): psacr → qs, pracs stays in snow
    #   delta3 = 1 if (qr<1e-4):              piacr/praci → qs (else → qg)
    # Stage-A STEP 1: from ENTRY state (ds) when base is a working state.
    ds = delta_src if delta_src is not None else state
    delta2 = ((ds.qr < 1.0e-4) & (ds.qs < 1.0e-4)).to(state.qc.dtype)
    delta3 = (ds.qr < 1.0e-4).to(state.qc.dtype)
    one_m_d2 = 1.0 - delta2
    one_m_d3 = 1.0 - delta3

    # qs (snow) — Fortran 2697-2701 + warm-branch 2811 직역
    # review4#1: psacw 제거 (Fortran 2697은 paacw만 사용); cold_mask 제거 (paacw 무조건 적용);
    #   psevp 추가 (warm branch snow→vapor 직접 sink, Fortran 2811 일부).
    dqs = dtcld * (
        cold.psdep                                # C4 deposition
        + cold.psaut                              # C5 ice aggregation → snow
        + cold.paacw_adj * cold_mask              # #1: paacw→qs only in COLD arm (Fortran :2583); warm arm sheds to qr
        + cold.piacr * delta3                     # piacr → qs when qr small
        + cold.praci * delta3                     # praci → qs when qr small
        + cold.psacr_adj * delta2                 # psacr → qs when qr&qs small
        + cold.psaci                              # C2 ice → snow
        - cold.pracs * one_m_d2                   # snow→graupel when (1-delta2)
        + cold.psevp                              # 2811 warm: snow evap (psevp<0 → qs sink)
        + mf.psmlt                                # D1 melt (psmlt<0 → qs sink)
        + mf.pseml                                # D5 enhanced melt
        # review5 audit: pmulcs 제거 — Fortran 2697은 pmul* 없음. paacw_adj가 이미
        # HM 분기를 반영 (paacw_adj = paacw - pmulcs - pmulcg). pmul* 추가 시 double-count.
    )
    qs_new = state.qs + dqs

    # qg (graupel) — Fortran 2702-2706 + warm-branch 2814 직역
    # review4#1: pgacw 제거; cold_mask 제거. pgevp 유지 (codex#4).
    dqg_rate = dtcld * (
        cold.pgdep                                # C4 deposition
        + cold.paacw_adj * cold_mask              # #1: paacw→qg only in COLD arm (Fortran :2591); warm arm sheds to qr
        + cold.pgacr_adj                          # 2706 rain ←collected by graupel
        + cold.pracs * one_m_d2                   # snow → graupel when (1-delta2)
        + cold.piacr * one_m_d3                   # piacr → qg when qr ≥ 1e-4
        + cold.praci * one_m_d3                   # praci → qg when qr ≥ 1e-4
        + cold.psacr_adj * one_m_d2               # psacr → qg
        + cold.pgaci                              # C2 ice → graupel
        + cold.pgevp                              # C6' graupel evap (pgevp<0 → qg sink)
        + mf.pgmlt                                # D1 (pgmlt<0 → qg sink)
        + mf.pgeml                                # D5 enhanced melt
    )
    dqg_amount = mf.pfrzdtr                       # 1610 Bigg rain → qg (amount)
    dqg = dqg_rate + dqg_amount
    qg_new = state.qg + dqg

    # qi (cloud ice)
    # qi (cloud ice) — Fortran 2690-2693 + inline 1556/1586/1391
    dqi_rate = dtcld * (
        cold.pinud + cold.pidep                   # C3/C4 vapor → ice (+)
        + cold.piacw                              # 2691 piacw cloud → ice (+)
        - cold.praci - cold.psaci - cold.pgaci    # 2690 ice → rain/snow/graupel (sinks)
        - cold.psaut                              # 2690 ice → snow aggregation (sink)
        + cold.pmulcs + cold.pmulrs               # 2692 HM (+ to ice)
        + cold.pmulcg + cold.pmulrg               # 2693 HM (+ to ice)
    )
    dqi_amount = mf.pinuc + mf.pfrzdtc - mf.pimlt_qi   # 1556/1586/1391 (amounts)
    dqi = dqi_rate + dqi_amount
    qi_new = state.qi + dqi

    # ── Number balance ────────────────────────────────────────────────
    # nc (cloud number) — Fortran 2683 + inline 1553/1583
    # nc (cloud number) — Fortran 2683 + inline 1553/1583/1469
    dnc_rate = dtcld * (
        - warm.nraut                              # qc → qr autoconv
        - warm.nccol                              # cloud self-collection
        - warm.nracw                              # qc → qr accretion
        - cold.niacw                              # C2c ice riming on cloud
        - 2.0 * cold.naacw                        # naacw 2× (Fortran 2684)
    )
    dnc_amount = -mf.ninuc - mf.nfrzdtc + mf.pimlt_ni  # 1553/1583/1469 (amounts)
    dnc = dnc_rate + dnc_amount
    nc_new = state.nc + dnc

    # nr (rain number) — Fortran 2688 + inline 1607
    dnr_rate = dtcld * (
        warm.nraut                                # B1 autoconv → rain
        - warm.nrcol                              # rain self-collection
        - cold.niacr - cold.nraci                 # 2688 rain ←collected by ice
        - cold.nsacr - cold.ngacr                 # 2688 rain ←snow/graupel
        + mf.nseml + mf.ngeml                     # 2699-2700 warm enhanced-melt number → rain
                                                  # (warm-gated in melt_freeze ⇒ no-op when cold; mirrors C++)
    )
    dnr_amount = -mf.nfrzdtr                      # 1607 Bigg rain (amount)
    dnr = dnr_rate + dnr_amount
    # NOTE: complete-rain-evap nr-zeroing (Fortran :1744) is NOT applied here.
    # It must run BEFORE the conservation budget (so the rain-number budget reads
    # the zeroed nr) and before the cold-phase rates that read nr — i.e. right
    # after warm_phase, not in state_update. Both C++ and Python currently lack
    # that correct-timed zeroing; it is scoped to the WRF-validated pass with the
    # other shared Fortran gaps (see memory project_kdm6_parity_audit_findings).
    nr_new = state.nr + dnr

    # ni (ice number) — Fortran 2694-2696 + inline 1554/1584/1469
    dni_rate = dtcld * (
        cold.ninud                                # C3 nucleation (+)
        - cold.nraci - cold.nsaci - cold.ngaci    # 2694 ice → rain/snow/graupel (sinks)
        - cold.niacr                              # 2695 niacr (rain ←ice의 ice 소멸)
        + cold.nmulcs + cold.nmulcg               # 2695 HM cloud splinter (+)
        + cold.nmulrs + cold.nmulrg               # 2696 HM rain splinter (+)
        - cold.nsaut                              # 2696 ice → snow aggregation (-)
    )
    dni_amount = mf.ninuc + mf.nfrzdtc - mf.pimlt_ni  # 1554/1584/1469 (amounts)
    dni = dni_rate + dni_amount
    ni_new_pre = state.ni + dni
    # review3#2: complete sublimation (pidep == -qi/dtcld) 시 ni=0 강제 (Fortran 2407-2409
    # 영역의 nci=0 처리). 매끄러운 mask는 cold.ice_complete_sublim (bool).
    ni_zero_mask = cold.ice_complete_sublim.to(state.qc.dtype)
    ni_new = ni_new_pre * (1.0 - ni_zero_mask)

    # brs (graupel volume) — review4#3: Fortran 2709-2711 (cold) + 2819 (warm) 직역.
    #   기존 mf.delta_brs_melt (pgmlt/rhox), mf.delta_brs_freeze (pfrzdtr/denr) 외에
    #   cold-branch 8 항 + warm-branch pgevp 추가.
    rhox_safe = torch.clamp(pre.progb.rhox, min=c.DENS)  # Fortran 2707 max(rhox, dens)
    dbrs_cold_riming = cold_mask * dtcld * (
        cold.pgdep / rhox_safe                # 2709 graupel deposition
        + cold.piacr / c.DENR                  # biacr
        + cold.praci / c.DENI                  # braci
        + cold.psacr_adj / c.DENR              # bsacr (post-HM adj)
        + cold.pracs / c.DENS                  # bracs
        + cold.pgaci / c.DENI                  # bgaci
        + cold.paacw_adj / c.DENR              # baacw (post-HM adj)
        + cold.pgacr_adj / c.DENR              # bgacr (post-HM adj)
    )
    dbrs_warm_evap = warm_mask * dtcld * (
        cold.pgevp / rhox_safe                 # 2819 bgevp (pgevp<0 → brs 감소)
        + mf.pgeml / rhox_safe                 # 2819 bgeml (pgeml<0 → brs 감소)
    )
    # delta_brs_melt = pgmlt/rhox (rate, *dtcld 필요), delta_brs_freeze = pfrzdtr/denr (amount, 그대로)
    dbrs = (
        dtcld * mf.delta_brs_melt              # D1 pgmlt/rhox (rate)
        + mf.delta_brs_freeze                  # D4 pfrzdtr/denr (amount)
        + dbrs_cold_riming
        + dbrs_warm_evap
    )
    # review5#3: Fortran 2620/2728 `brs = max(brs+...,0.)` 직역. AD subgradient at 0
    # boundary는 well-defined (zero gradient on clamped cells).
    brs_new = torch.clamp(state.brs + dbrs, min=0.0)

    # ── Energy balance (T) — review3#4 fix: xls/xlf split ────────────
    # Fortran 2820-2825: xlwork2 = -xls·(psdep+pgdep+pidep+pinud) + xl·(prevp+psevp+pgevp)
    #                              + freeze/melt 항(xlf), t -= xlwork2/cpm·dtcld.
    #   Fortran 2596: xlf = xls - xl(T). xls is the CONSTANT sublimation latent
    #   heat (2.85e6); fusion xlf is DERIVED and TEMPERATURE-DEPENDENT. The prior
    #   code inverted this (constant xlf, derived xls), over-heating freezing at
    #   cold T. Mirrors the C++ coordinator.cpp fix (single bug across both ports).
    #   세 group으로 분리:
    #     (a) warm-phase vapor↔water (xl): pcond, prevp, psevp, pgevp
    #     (b) deposition/sublimation vapor↔ice (xls, CONSTANT): pinud, pidep, psdep, pgdep
    #     (c) freeze/melt liquid↔solid (xlf=xls-xl(T)): pinuc, pfrzdtc, pfrzdtr, psmlt, pgmlt, pimlt_qi, pseml, pgeml
    cpm_safe = torch.clamp(pre.cpm, min=c.QCRMIN)
    xlf = xls - pre.xl  # per-cell fusion latent heat (J/kg), temperature-dependent

    dT_warm_phase = dtcld * pre.xl / cpm_safe * (
        # pcond warming DEFERRED to apply_satadj_step_torch (post-reclass).
        warm.prevp                            # B4 rain evap (prevp<0 → cooling)
        + cold.psevp                          # C6 snow evap (psevp<0 → cooling)
        + cold.pgevp                          # C6' graupel evap (pgevp<0 → cooling)
    )
    dT_dep_phase = dtcld * xls / cpm_safe * (
        cold.pinud + cold.pidep + cold.psdep + cold.pgdep   # vapor→ice deposition (xls)
    )
    # xlf group — review4#4: Fortran 2713-2716 cold branch xlf list 추가.
    #   Fortran의 paacw/psacr/pgacr는 HM 후 *post-adjusted* value이므로, 우리 oracle의
    #   paacw_adj/psacr_adj/pgacr_adj와 동일. piacr·1 + paacw·2 + pmul*·1 + piacw·1
    #   + pgacr·1 + psacr·1 = 10 항.
    # xlf rate group (warm/cold rates) — review5#1: D2-D4와 pimlt는 amount group으로 분리.
    dT_freeze_rate = dtcld * xlf / cpm_safe * (
        mf.psmlt + mf.pgmlt                     # D1 melt (negative rate → cooling)
        + mf.pseml + mf.pgeml                   # D5 enhanced melt cooling
        # cold-branch riming/freezing: liquid → solid → fusion latent heat 방출 → warming
        + cold_mask * (
            cold.piacr                          # 2714 rain frozen on ice
            + 2.0 * cold.paacw_adj              # 2714 paacw·2 (cloud rimed on snow+graupel)
            + cold.pmulcs + cold.pmulcg         # 2714 HM cloud splinter
            + cold.pmulrs + cold.pmulrg         # 2715 HM rain splinter
            + cold.piacw                        # 2716 cloud frozen on ice
            + cold.pgacr_adj + cold.psacr_adj   # 2716 rain collected by graupel/snow
        )
    )
    # xlf amount group (D2-D4 freezes + D1 ice melt) — pimlt_qi는 instantaneous full-melt amount.
    dT_freeze_amount = xlf / cpm_safe * (
        mf.pinuc + mf.pfrzdtc + mf.pfrzdtr      # 1558/1588/1611 inline (amount, +)
        - mf.pimlt_qi                            # 1391 ice → cloud water (-, cooling)
    )
    dT_freeze_phase = dT_freeze_rate + dT_freeze_amount
    t_new = state.t + dT_warm_phase + dT_dep_phase + dT_freeze_phase

    # review5#2 (partial): Fortran 2680-2706 `max(... ,0.)` — nonnegative clamp만 적용.
    # review9#1 fix: paired threshold cleanup은 이 함수 *밖*에서 reclassification 뒤에
    # 적용 (Fortran 순서: state_update → Picons → rain-cloud → pcact → cleanup).
    return CoordinatorState(
        qv=torch.clamp(qv_new, min=0.0),
        qc=torch.clamp(qc_new, min=0.0),
        qr=torch.clamp(qr_new, min=0.0),
        qs=torch.clamp(qs_new, min=0.0),
        qg=torch.clamp(qg_new, min=0.0),
        qi=torch.clamp(qi_new, min=0.0),
        nc=torch.clamp(nc_new, min=0.0),
        nr=torch.clamp(nr_new, min=0.0),
        ni=torch.clamp(ni_new, min=0.0),
        brs=brs_new,                    # 위에서 이미 clamp(min=0) 적용
        t=t_new,                         # T는 clamp 없음 (음수 가능, 비물리적이지만 Fortran도 안 함)
    )


# ─── Step F1h: Post-reclassification paired threshold cleanup ────────────────


def apply_threshold_cleanup_torch(
    state: CoordinatorState,
    *,
    qmin: float = 1.0e-15,
    qcrmin: float = None,
) -> CoordinatorState:
    """Fortran 3017-3035 padding for small values (post-reclassification).

    review9#1 fix: 이전엔 `state_update_torch` 내부에 있어 Picons/rain-cloud 전에
    적용됐음. Fortran 순서는 reclassification *후* cleanup이라, Picons가 만들어낸 작은
    qs/qc 등을 추가로 zero할 기회가 있어야 함.

    Pattern: q*<=threshold → q=0; paired number도 zero (qc/qr/qi).
    """
    if qcrmin is None:
        qcrmin = c.QCRMIN
    keep_qc = (state.qc > qmin).to(state.qc.dtype)
    keep_qi = (state.qi > qmin).to(state.qi.dtype)
    keep_qr = (state.qr > qcrmin).to(state.qr.dtype)
    keep_qs = (state.qs > qcrmin).to(state.qs.dtype)
    keep_qg = (state.qg > qcrmin).to(state.qg.dtype)
    return CoordinatorState(
        qv=state.qv,
        qc=state.qc * keep_qc,
        nc=state.nc * keep_qc,
        qr=state.qr * keep_qr,
        nr=state.nr * keep_qr,
        qs=state.qs * keep_qs,
        qg=state.qg * keep_qg,
        qi=state.qi * keep_qi,
        ni=state.ni * keep_qi,
        brs=state.brs,
        t=state.t,
    )


# ─── Step F1f: Post-update Picons reclassification (Park-Lim 2023) ───────────


def reclassify_large_ice_to_snow_torch(
    state: CoordinatorState,
    den: torch.Tensor,
    *,
    qmin: float = 1.0e-15,
    di_threshold: float = 200.0e-6,
    t0c: float = 273.15,
) -> CoordinatorState:
    """Fortran 2876-2882 (Picons, Park-Lim 2023): 평균 직경이 임계값(200μm) 이상인
    cloud ice는 더 이상 ice이 아니라 snow로 재분류. T<0°C, qi>qmin 게이트.

    review6#1 / review7#1 fix: avedia_i를 *post-update* qi/ni/den으로 inline 재진단
    (Fortran 2870-2872 처럼 slope_kdm6 재호출 후 avedia 다시 계산하는 것을 흉내).
    review8#1 fix: ni<=0 / qi<=qmin 셀에서 rslope_i가 발산해 false-positive Picons가
    트리거되던 edge bug 수정. slope_kdm6 ice branch와 같은 mask + LAMDAIMAX/MIN clamp.

    Mass conservation: qs gains qi, qi → 0, ni → 0.
    AD-friendly multiplicative mask (subgradient at boundary OK).
    """
    # avedia_i = rslope_i · (Γ(4+MUI)/Γ(1+MUI))^(1/3)
    #   rslope_i = 1/lamdai, clamped to [1/LAMDAIMAX, 1/LAMDAIMIN]
    #   lamdai = (pidni · ni / (qi·den))^(1/DMI)
    #   pidni = cmi · Γ(1+DMI+MUI) / Γ(1+MUI),  cmi = π·DENI/6
    cmi = math.pi * c.DENI / 6.0
    g1pmi = math.exp(math.lgamma(1.0 + c.MUI))               # Γ(1+MUI)
    g1pdimi = math.exp(math.lgamma(1.0 + c.DMI + c.MUI))     # Γ(1+DMI+MUI)
    g4pmi = math.exp(math.lgamma(4.0 + c.MUI))               # Γ(4+MUI)
    pidni = cmi * g1pdimi / g1pmi
    avedia_factor = (g4pmi / g1pmi) ** (1.0 / 3.0)
    rslopeimax = 1.0 / c.LAMDAIMAX
    rslopeimin = 1.0 / c.LAMDAIMIN

    eps = 1.0e-30
    ice_active = (state.qi > qmin) & (state.ni > 0.0) & (den > 0.0)
    qi_safe = torch.clamp(state.qi * den, min=eps)
    ratio = pidni * torch.clamp(state.ni, min=0.0) / qi_safe
    lamdai = torch.clamp(ratio, min=eps) ** (1.0 / c.DMI)
    rslope_i_raw = torch.clamp(1.0 / torch.clamp(lamdai, min=eps),
                               min=rslopeimax, max=rslopeimin)
    # ice_active=False 시 rslope_i = rslopeimax (smallest avedia → Picons mask 거짓)
    rslope_i = torch.where(ice_active, rslope_i_raw,
                           torch.full_like(rslope_i_raw, rslopeimax))
    avedia_i = rslope_i * avedia_factor

    mask = ice_active & (state.t < t0c) & (avedia_i >= di_threshold)
    mask_f = mask.to(state.qc.dtype)
    return CoordinatorState(
        qv=state.qv, qc=state.qc, qr=state.qr,
        qs=state.qs + state.qi * mask_f,
        qg=state.qg,
        qi=state.qi * (1.0 - mask_f),
        nc=state.nc, nr=state.nr,
        ni=state.ni * (1.0 - mask_f),
        brs=state.brs,
        t=state.t,
    )


# ─── Step F1g: Post-update rain→cloud reclassification (small-drop cutoff) ───


def reclassify_small_rain_to_cloud_torch(
    state: CoordinatorState,
    den: torch.Tensor,
    *,
    qcrmin: float = None,
    di_threshold: float = 82.0e-6,
) -> CoordinatorState:
    """Fortran 2952-2964: post-update 평균 빗방울 직경(avedia_r) ≤ 82μm 시
    cloud water/number로 되돌림. Picons (qi→qs)와 짝을 이루는 산문(small-drop) 처리.

    review8#3 신규 추가. avedia_r은 post-update qr/nr/den으로 inline 재진단.

    Mass conservation: qc gains qr, qr → 0; nc gains nr, nr → 0.
    AD-friendly multiplicative mask.
    """
    if qcrmin is None:
        qcrmin = c.QCRMIN
    # avedia_r = rslope_r · (Γ(4+MUR)/Γ(1+MUR))^(1/3)
    cmr = math.pi * c.DENR / 6.0
    g1pmr = math.exp(math.lgamma(1.0 + c.MUR))               # Γ(1+MUR)
    g1pdrmr = math.exp(math.lgamma(1.0 + c.DMR + c.MUR))     # Γ(1+DMR+MUR)
    g4pmr = math.exp(math.lgamma(4.0 + c.MUR))               # Γ(4+MUR)
    pidnr = cmr * g1pdrmr / g1pmr
    avedia_factor = (g4pmr / g1pmr) ** (1.0 / 3.0)
    rslopermax = 1.0 / c.LAMDARMAX
    rslopermin = 1.0 / c.LAMDARMIN

    eps = 1.0e-30
    rain_active = (state.qr > qcrmin) & (state.nr > 0.0) & (den > 0.0)
    qr_safe = torch.clamp(state.qr * den, min=eps)
    ratio = pidnr * torch.clamp(state.nr, min=0.0) / qr_safe
    lamdar = torch.clamp(ratio, min=eps) ** (1.0 / c.DMR)
    rslope_r_raw = torch.clamp(1.0 / torch.clamp(lamdar, min=eps),
                               min=rslopermax, max=rslopermin)
    rslope_r = torch.where(rain_active, rslope_r_raw,
                           torch.full_like(rslope_r_raw, rslopermax))
    avedia_r = rslope_r * avedia_factor

    # 소형 drop이 cloud로 회귀: rain_active AND avedia_r ≤ 82μm
    mask = rain_active & (avedia_r <= di_threshold)
    mask_f = mask.to(state.qc.dtype)
    return CoordinatorState(
        qv=state.qv,
        qc=state.qc + state.qr * mask_f,
        qr=state.qr * (1.0 - mask_f),
        qs=state.qs, qg=state.qg, qi=state.qi,
        nc=state.nc + state.nr * mask_f,
        nr=state.nr * (1.0 - mask_f),
        ni=state.ni,
        brs=state.brs,
        t=state.t,
    )


# ─── Step F1i: DSD number limiters (Fortran 3039-3082) ──────────────────────


def _limit_number_for_lamda(
    q: torch.Tensor, n: torch.Tensor, den: torch.Tensor,
    *, pidn: float, dm: float, lamda_min: float, lamda_max: float,
    q_thresh: float, n_thresh: float,
) -> torch.Tensor:
    """Generic per-species DSD limiter:
        if q >= q_thresh AND n >= n_thresh:
            lamda = (pidn·n / (q·den))^(1/dm)
            if lamda <= lamda_min: n = den·q·lamda_min^dm/pidn
            elif lamda >= lamda_max: n = den·q·lamda_max^dm/pidn
    Inactive 셀은 n 그대로 반환. AD-friendly (subgradient at boundary OK).
    """
    eps = 1.0e-30
    active = (q >= q_thresh) & (n >= n_thresh)
    qden = torch.clamp(q * den, min=eps)
    ratio = torch.clamp(pidn * n / qden, min=eps)
    lamda = ratio ** (1.0 / dm)

    # Boundary back-derived numbers
    n_at_min = den * q * (lamda_min ** dm) / pidn
    n_at_max = den * q * (lamda_max ** dm) / pidn

    # 분기: lamda<=lamda_min 또는 lamda>=lamda_max에서만 n을 재계산.
    too_small = active & (lamda <= lamda_min)
    too_large = active & (lamda >= lamda_max)
    n_new = torch.where(too_small, n_at_min,
                       torch.where(too_large, n_at_max, n))
    return n_new


def apply_dsd_number_limiters_torch(
    state: CoordinatorState,
    den: torch.Tensor,
    *,
    qmin: float = 1.0e-15,
    qcrmin: float = None,
) -> CoordinatorState:
    """Fortran 3039-3082: post-cleanup DSD number limiter.

    Each (q, n) pair: lamda = (pidn·n / (q·den))^(1/dm). When lamda runs out of
    [lamda_min, lamda_max], snap and back-derive n. Plus rain/cloud absolute caps
    via NRMAX/NCMAX (Fortran 3079-3082).

    Note: nccn clamp `min(max(nccn, 1e8), 2e10)` (Fortran 3076)는 nccn이 본 oracle의
    CoordinatorState에 없어 미적용 (Task #74에서 KIM-meso 통합 단계에 처리).
    """
    if qcrmin is None:
        qcrmin = c.QCRMIN

    # gamma constants (rgmma = Γ; review6 audit fix 적용 후)
    rgmma = lambda x: math.exp(math.lgamma(x))
    cmr = math.pi * c.DENR / 6.0
    cmc = math.pi * c.DENR / 6.0    # cloud uses water density (cmc = π·DENR/6)
    cmi = math.pi * c.DENI / 6.0
    pidnr = cmr * rgmma(1.0 + c.DMR + c.MUR) / rgmma(1.0 + c.MUR)
    # cloud DMC=3, MUC=2 (Cohard-Pinty modified gamma)
    pidnc = cmc * rgmma(1.0 + c.DMC / (c.MUC + 1.0))
    pidni = cmi * rgmma(1.0 + c.DMI + c.MUI) / rgmma(1.0 + c.MUI)

    # Rain
    nr_new = _limit_number_for_lamda(
        state.qr, state.nr, den,
        pidn=pidnr, dm=c.DMR,
        lamda_min=c.LAMDARMIN, lamda_max=c.LAMDARMAX,
        q_thresh=qcrmin, n_thresh=c.NRMIN,
    )
    # Cloud
    nc_new = _limit_number_for_lamda(
        state.qc, state.nc, den,
        pidn=pidnc, dm=c.DMC,
        lamda_min=c.LAMDACMIN, lamda_max=c.LAMDACMAX,
        q_thresh=qmin, n_thresh=c.NCMIN,
    )
    # Ice — apply_dsd_number_limiters implements the FINAL kdm62d block, whose
    # ice snap is Fortran kdm6.f90:2945 `qci(i,k,2).ge.qmin .and. nci(i,k,2).ge.ncmin`
    # — same qmin/ncmin pattern as the cloud snap (:2934) above. The prior 1e-14/0
    # gate mis-cited :1417 (the INLINE rate-phase snap, a different occurrence
    # with no n-gate). Adjudicated vs Fortran 2026-05-31; mirrors the C++ fix.
    ni_new = _limit_number_for_lamda(
        state.qi, state.ni, den,
        pidn=pidni, dm=c.DMI,
        lamda_min=c.LAMDAIMIN, lamda_max=c.LAMDAIMAX,
        q_thresh=qmin, n_thresh=c.NCMIN,
    )

    # Absolute number caps (Fortran 3079-3082): nrs > NRMAX → snap to lamdarmax.
    eps = 1.0e-30
    qden_r = torch.clamp(state.qr * den, min=eps)
    nr_at_max = den * state.qr * (c.LAMDARMAX ** c.DMR) / pidnr
    nr_new = torch.where(nr_new > c.NRMAX, nr_at_max, nr_new)
    qden_c = torch.clamp(state.qc * den, min=eps)
    nc_at_max = den * state.qc * (c.LAMDACMAX ** c.DMC) / pidnc
    nc_new = torch.where(nc_new > c.NCMAX, nc_at_max, nc_new)

    return CoordinatorState(
        qv=state.qv,
        qc=state.qc, qr=state.qr, qs=state.qs, qg=state.qg, qi=state.qi,
        nc=nc_new, nr=nr_new, ni=ni_new,
        brs=state.brs,
        t=state.t,
    )


# ─── Step F2: Sub-cycling wrapper ────────────────────────────────────────────


class CoordinatorAuxDiagnostics(NamedTuple):
    """F1 chain이 사용하는 *외부 진단* 입력. 운영 시 caller가 산출.

    향후 Step F1f에서 자동 진단 모듈로 승격 가능 (n0r/n0i/n0c/n0so/n0go,
    work1_r/work1_ice, avedia_i, rslopecmu/rslopecd 등).
    """
    n0r: torch.Tensor
    n0i: torch.Tensor
    n0c: torch.Tensor
    n0so: torch.Tensor
    n0go: torch.Tensor
    work1_r: torch.Tensor
    work1_ice: torch.Tensor
    work1_water: torch.Tensor      # work1(:,:,1) — psevp/pgevp용 (review3#1)
    qcr: torch.Tensor
    avedia_i: torch.Tensor
    rslopecmu: torch.Tensor
    rslopecd: torch.Tensor


def build_default_aux_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    rslopec: torch.Tensor,
    *,
    thermo_params,
) -> CoordinatorAuxDiagnostics:
    """Physics-based DSD aux (n0r/n0i/n0c, work1_water/ice, avedia_i,
    rslopecmu/rslopecd) computed FROM the state. 1:1 mirror of C++
    build_default_aux (runtime.cpp:103). n0so/n0go are constants (mus=mug=0);
    qcr is a placeholder (8e-5) overridden by the caller via qcr_carry. Used by
    rebuild_aux_torch for the Stage-A sequential re-architecture. AD-safe.
    """
    rgmma = lambda x: math.exp(math.lgamma(x))
    g1pmr = rgmma(1.0 + c.MUR)
    g1pmi = rgmma(1.0 + c.MUI)
    g4pmi = rgmma(4.0 + c.MUI)
    pidnr = (math.pi * c.DENR / 6.0) * rgmma(1.0 + c.DMR + c.MUR) / g1pmr
    pidni = (math.pi * c.DENI / 6.0) * rgmma(1.0 + c.DMI + c.MUI) / g1pmi

    rslope_r = _dsd.diag_species_slope_torch(
        state.qr, state.nr, forcing.den, pidnr, c.DMR, c.LAMDARMAX, c.LAMDARMIN)
    rslope_i = _dsd.diag_species_slope_torch(
        state.qi, state.ni, forcing.den, pidni, c.DMI, c.LAMDAIMAX, c.LAMDAIMIN)
    rslopemu_r = rslope_r ** c.MUR
    rslopemu_i = torch.ones_like(rslope_i) if c.MUI == 0.0 else rslope_i ** c.MUI
    rslopecmu = rslopec ** c.MUC

    n0r = state.nr / (rslope_r * rslopemu_r * g1pmr)
    n0i = state.ni / (rslope_i * rslopemu_i * g1pmi)
    n0c = (c.MUC + 1.0) * state.nc / (rslopec * rslopecmu)

    xl = _thermo.compute_xl(state.t, params=thermo_params)
    xls_t = torch.full_like(state.t, thermo_params.xls)
    qs1 = _thermo.compute_qs_water(state.t, forcing.p, params=thermo_params)
    qs2 = _thermo.compute_qs_ice(state.t, forcing.p, params=thermo_params)
    work1_water = _thermo.compute_diffac(xl, forcing.p, state.t, forcing.den, qs1, params=thermo_params)
    work1_ice = _thermo.compute_diffac(xls_t, forcing.p, state.t, forcing.den, qs2, params=thermo_params)

    return CoordinatorAuxDiagnostics(
        n0r=n0r, n0i=n0i, n0c=n0c,
        n0so=torch.full_like(state.qs, c.N0S),
        n0go=torch.full_like(state.qg, c.N0G),
        work1_r=work1_water, work1_ice=work1_ice, work1_water=work1_water,
        qcr=torch.full_like(state.qc, 8.0e-5),
        avedia_i=rslope_i * (g4pmi / g1pmi) ** (1.0 / 3.0),
        rslopecmu=rslopecmu, rslopecd=rslopec ** c.DMC,
    )


def rebuild_aux_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    sea_mask: torch.Tensor,
    *,
    params: CoordinatorParams,
    qcr_carry: torch.Tensor,
):
    """Re-run preamble_torch + build_default_aux_torch on a working (post-melt/
    post-freeze) state. Returns (PreambleOutputs, CoordinatorAuxDiagnostics) —
    BOTH refreshed together (rebuilding aux but keeping a stale preamble is the
    806× over-deposition class). qcr is carried (sea_mask-derived). Mirrors C++
    rebuild_aux. STEP 0b: defined, NOT yet called (no flow change).
    """
    pre = preamble_torch(state, forcing, sea_mask, params=params)
    aux = build_default_aux_torch(state, forcing, pre.rslopec, thermo_params=params.thermo)
    aux = aux._replace(qcr=qcr_carry)
    return pre, aux


def apply_satadj_step_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    xl: torch.Tensor,
    cpm: torch.Tensor,
    satadj_params,
    thermo_params,
    *,
    dtcld: float,
) -> CoordinatorState:
    """F1g+ — saturation adjustment on the POST-state-update + POST-reclass state
    (Fortran module_mp_kdm6.f90:2906-2915). Mirrors C++ apply_satadj_step.

    pcond is DEFERRED out of state_update_torch so condensation fires on the
    proper post-mass-balance, post-reclassification state — matching Fortran's
    :2911 sequence (mass balance → Picons/rain-cloud reclass → satadj), NOT
    before it (which was the C++↔Python divergence Codex flagged).

    Scope vs C++: the C++ apply_satadj_step also runs pcact/ncact CCN activation
    and a complete-evap NC→NCCN transfer. This oracle's CoordinatorState has no
    `nccn` field, so those are deferred per Task #74 (same as warm_phase_torch,
    which carries no ncact/pcact). qs1 is recomputed from the post-update t
    (Fortran :2906) since t may have changed. AD-safe: clamp + arithmetic only.
    """
    cpm_safe = torch.clamp(cpm, min=c.QCRMIN)
    qs1 = _thermo.compute_qs_water(state.t, forcing.p, params=thermo_params)
    pcond = _satadj.saturation_adjustment_torch(
        state.t, state.qv, state.qc, qs1, xl, cpm_safe,
        params=satadj_params, dtcld=dtcld,
    )
    qv_final = torch.clamp(state.qv - pcond * dtcld, min=0.0)
    qc_final = torch.clamp(state.qc + pcond * dtcld, min=0.0)
    t_final = state.t + pcond * xl / cpm_safe * dtcld
    return state._replace(qv=qv_final, qc=qc_final, t=t_final)


def kdm62d_one_step_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    aux: CoordinatorAuxDiagnostics,
    sea_mask: torch.Tensor,
    *,
    full_params: CoordinatorParams,
    warm_params: WarmPhaseParams,
    cold_params: ColdPhaseParams,
    mf_params: MeltFreezePhaseParams,
    dtcld: float,
) -> CoordinatorState:
    """F1 chain을 *single timestep*에 대해 한 번 호출 → new state 반환.

    Order: preamble → warm → cold → melt/freeze → state_update.
    """
    pre = preamble_torch(state, forcing, sea_mask, params=full_params)

    warm_out = warm_phase_torch(
        state, forcing, pre,
        aux.n0r, aux.work1_r, aux.qcr,
        params=warm_params, dtcld=dtcld,
    )

    cold_out = cold_phase_torch(
        state, forcing, pre, warm_out.prevp,
        aux.n0i, aux.n0r, aux.n0so, aux.n0go, aux.n0c,
        aux.rslopecmu, aux.rslopecd,
        aux.avedia_i, aux.work1_ice, aux.work1_water,
        params=cold_params, dtcld=dtcld,
    )

    mf_out = melt_freeze_phase_torch(
        state, forcing, pre, cold_out,
        aux.n0c, aux.n0r, aux.n0so, aux.n0go,
        pre.rslopec, aux.rslopecmu, aux.rslopecd,
        params=mf_params, dtcld=dtcld,
    )

    # F1d2: group conservation limiters (Fortran group budgets :2410-2678).
    # AFTER melt_freeze (D5 read UNSCALED cold rates) + BEFORE state_update.
    # Bounds the SUM of competing sinks per species (the tier the per-rate caps
    # lack — the 806× staged-ice fix). Mirrors C++ scale_rates_for_conservation.
    warm_out, cold_out, mf_out = scale_rates_for_conservation_torch(
        state, pre.supcol, warm_out, cold_out, mf_out, dtcld=dtcld,
    )

    # Stage-A STEP 1 (mirror of C++): apply melt(D1)+freeze(D2-D4) INLINE to a
    # working state, and STRIP them from state_update by zeroing the 12 D1-D4 mf
    # fields (D5 pseml/pgeml/nseml/ngeml stay). Net identical to the old single
    # state_update. Behaviour-preserving: warm/cold/budgets read entry `state`,
    # delta2/delta3 forced from entry (delta_src=state). STEP 2 moves the
    # inline-apply BEFORE warm/cold + rebuilds aux. See STAGE_A_REARCH_BLUEPRINT.md.
    working = apply_melt_freeze_inline_torch(
        state, mf_out, pre, dtcld=dtcld, xls=full_params.thermo.xls)
    z = torch.zeros_like(state.qc)
    mf_d5 = mf_out._replace(                       # keep D5 (pseml/pgeml/nseml/ngeml)
        psmlt=z, pgmlt=z, pimlt_qi=z, pimlt_ni=z, delta_brs_melt=z,  # D1
        pinuc=z, ninuc=z,                          # D2
        pfrzdtc=z, nfrzdtc=z,                      # D3
        pfrzdtr=z, nfrzdtr=z, delta_brs_freeze=z,  # D4
    )

    # Pass the CONFIGURED sublimation latent heat (single source); fusion
    # xlf = xls - xl(T) is derived inside (Fortran convention). Mirrors C++.
    new_state = state_update_torch(
        working, pre, warm_out, cold_out, mf_d5,
        dtcld=dtcld, xls=full_params.thermo.xls, delta_src=state,
    )
    # review5#4 + review7#1: Picons (Fortran 2876-2882) qi→qs.
    new_state = reclassify_large_ice_to_snow_torch(new_state, forcing.den)
    # review8#3: rain→cloud reclassification (Fortran 2952-2964) when avedia_r ≤ 82μm.
    new_state = reclassify_small_rain_to_cloud_torch(new_state, forcing.den)
    # F1g+: satadj/pcond on the post-update + post-reclass state (Fortran
    # :2906-2915). Mirrors C++ apply_satadj_step; pcond was deferred OUT of
    # state_update_torch so condensation fires on the proper post-mass-balance,
    # post-reclass state (the C++↔Python parity fix Codex flagged).
    new_state = apply_satadj_step_torch(
        new_state, forcing, pre.xl, pre.cpm,
        warm_params.satadj, full_params.thermo, dtcld=dtcld,
    )
    # review9#1: paired threshold cleanup (Fortran 3017-3035) — *after* reclassifications
    # to catch tiny qs/qc remnants Picons/rain-cloud may have produced.
    new_state = apply_threshold_cleanup_torch(new_state)
    # review9#2: DSD number limiters (Fortran 3039-3082) — lamda 범위를 벗어나면 number
    # 재계산. nccn clamp는 deferred (Task #74).
    return apply_dsd_number_limiters_torch(new_state, forcing.den)


def compute_loops_max(delt: float, dtcldcr: float = c.DTCLDCR) -> int:
    """Fortran kdm62D 진입 시: loops_max = max(nint(delt/dtcldcr + 0.5), 1).

    정수 연산 — 미분 불가 영역 (caller가 결정).
    """
    return max(int(delt / dtcldcr + 0.5), 1)


def kdm62d_step_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    aux: CoordinatorAuxDiagnostics,
    sea_mask: torch.Tensor,
    *,
    full_params: CoordinatorParams,
    warm_params: WarmPhaseParams,
    cold_params: ColdPhaseParams,
    mf_params: MeltFreezePhaseParams,
    delt: float,
    dtcldcr: float = c.DTCLDCR,
) -> CoordinatorState:
    """F2 — sub-cycling wrapper.

    Outer timestep `delt`를 `dtcldcr` 단위로 분할 (loops_max sub-cycles), 매
    sub-cycle마다 F1 chain 호출. state는 sequential하게 갱신.

    Note: sedimentation은 본 함수 *밖*에서 호출 (sedimentation module 별도 사용).
    향후 F2b로 통합 가능.
    """
    # codex stop-hook fix: delt<=0 → no-op. delt=0이면 dtcld=0이 되고 kdm62d_one_step
    # 내부의 mass/dtcld 분할 등에서 NaN 발생. 물리적으로도 zero 시간 elapsed → state
    # 불변이 옳음. 이 가드는 wrapper 책임이고 caller validation은 권장이지만 강제 아님.
    if delt <= 0.0:
        return state

    loops_max = compute_loops_max(delt, dtcldcr)
    dtcld = delt / float(loops_max)

    cur_state = state
    for _ in range(loops_max):
        cur_state = kdm62d_one_step_torch(
            cur_state, forcing, aux, sea_mask,
            full_params=full_params,
            warm_params=warm_params,
            cold_params=cold_params,
            mf_params=mf_params,
            dtcld=dtcld,
        )
    return cur_state


# ─── Step F2b: Sedimentation chain integration ───────────────────────────────


class SedimentationOutputs(NamedTuple):
    """sedimentation 결과: 갱신된 state + 표면 누적."""
    state: CoordinatorState
    rain_increment: torch.Tensor       # (B,) [mm]
    snow_increment: torch.Tensor
    graupel_increment: torch.Tensor


def sedimentation_chain_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    work1_qr: torch.Tensor,    # already work1(:,:,1)/delz (E1 normalized)
    workn_qr: torch.Tensor,
    work1_qs: torch.Tensor,
    work1_qg: torch.Tensor,
    work1_qi: torch.Tensor,
    workn_qi: torch.Tensor,
    *,
    mstep_main: int,           # rain/snow/graupel/brs substeps
    mstep_ice: int,            # ice (qi/ni) substeps
    dtcld: float,
    params: _sed.SubstepAdvectionParams,
) -> SedimentationOutputs:
    """F2b — sedimentation 통합 chain.

    Order:
      1. rain/snow/graupel/brs substepping (mstep_main times)
      2. ice (qi/ni) substepping (mstep_ice times)
      3. surface accumulation (bottom layer)

    Note: ProgB+slope re-call (Fortran 1218-1234) — *각 substep 안에서* work1을
    재진단하는 정확한 Fortran 직역은 향후 보완. 본 oracle은 *시간 불변* work1을
    사용 (substep 내내 동일).
    """
    K = state.qr.shape[-1]
    fall_qr_init = torch.zeros_like(state.qr)
    fall_nr_init = torch.zeros_like(state.qr)
    fall_qs_init = torch.zeros_like(state.qr)
    fall_qg_init = torch.zeros_like(state.qr)
    fall_brs_init = torch.zeros_like(state.qr)

    # ── Rain/snow/graupel/brs substepping ─────────────────────────────
    adv_state = _sed.SubstepAdvectionState(
        qr=state.qr, nr=state.nr, qs=state.qs, qg=state.qg, brs=state.brs,
    )
    fall_qr = fall_qr_init
    fall_nr = fall_nr_init
    fall_qs = fall_qs_init
    fall_qg = fall_qg_init
    fall_brs = fall_brs_init
    for _ in range(mstep_main):
        out = _sed.substep_advection_torch(
            adv_state,
            fall_qr, fall_nr, fall_qs, fall_qg, fall_brs,
            work1_qr, workn_qr, work1_qs, work1_qg,
            forcing.delz, forcing.dend,
            mstep=mstep_main, dtcld=dtcld, params=params,
        )
        adv_state = out.state
        fall_qr = out.fall_qr
        fall_nr = out.fall_nr
        fall_qs = out.fall_qs
        fall_qg = out.fall_qg
        fall_brs = out.fall_brs

    # ── Ice substepping ──────────────────────────────────────────────
    ice_state = _sed.IceSubstepState(qi=state.qi, ni=state.ni)
    fall_qi = torch.zeros_like(state.qr)
    fall_ni = torch.zeros_like(state.qr)
    for _ in range(mstep_ice):
        out_i = _sed.ice_substep_advection_torch(
            ice_state, fall_qi, fall_ni,
            work1_qi, workn_qi, forcing.delz, forcing.dend,
            mstep=mstep_ice, dtcld=dtcld, params=params,
        )
        ice_state = out_i.state
        fall_qi = out_i.fall_qi
        fall_ni = out_i.fall_ni

    # ── Surface accumulation (bottom = K-1 in tensor) ─────────────────
    bottom = K - 1
    surface = _sed.surface_accumulation_torch(
        fall_qr[:, bottom], fall_qs[:, bottom],
        fall_qg[:, bottom], fall_qi[:, bottom],
        forcing.delz[:, bottom], dtcld=dtcld,
    )

    new_state = state._replace(
        qr=adv_state.qr, nr=adv_state.nr,
        qs=adv_state.qs, qg=adv_state.qg, brs=adv_state.brs,
        qi=ice_state.qi, ni=ice_state.ni,
    )
    return SedimentationOutputs(
        state=new_state,
        rain_increment=surface.rain_increment,
        snow_increment=surface.snow_increment,
        graupel_increment=surface.graupel_increment,
    )


__all__ = [
    "CoordinatorState",
    "CoordinatorForcing",
    "CoordinatorParams",
    "PreambleOutputs",
    "WarmPhaseParams",
    "WarmPhaseOutputs",
    "ColdPhaseParams",
    "ColdPhaseOutputs",
    "MeltFreezePhaseParams",
    "MeltFreezePhaseOutputs",
    "CoordinatorAuxDiagnostics",
    "SedimentationOutputs",
    "default_coordinator_params",
    "default_warm_phase_params",
    "default_cold_phase_params",
    "default_melt_freeze_phase_params",
    "preamble_torch",
    "warm_phase_torch",
    "cold_phase_torch",
    "melt_freeze_phase_torch",
    "state_update_torch",
    "kdm62d_one_step_torch",
    "reclassify_large_ice_to_snow_torch",
    "reclassify_small_rain_to_cloud_torch",
    "apply_threshold_cleanup_torch",
    "apply_dsd_number_limiters_torch",
    "kdm62d_step_torch",
    "compute_loops_max",
    "sedimentation_chain_torch",
]
