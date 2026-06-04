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
    # NOTE: no pcond. The warm-phase B5 saturation adjustment is NOT emitted here — qv↔qc
    # condensation is done once, in apply_satadj_step_torch (after state_update +
    # reclassifications, Fortran F:2922-2943). Mirrors the C++ WarmPhaseOutputs (8 rates).
    rain_complete_evap: torch.Tensor = None  # B4 complete-evap mask → NR→NCCN (Task #74)


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

    Process order (Fortran 1693-1801 + B5 saturation adjustment 2922-2943):
      B1 autoconv  (qc→qr mass+number)
      B2 accretion (qc←rain mass+number)
      B3 self-collection (cloud + rain + break-up)
      B4 rain evap/cond (qr↔qv)
      (B5 saturation adjustment qv↔qc is DEFERRED to apply_satadj_step_torch, F:2922-2943)

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
    prevp, rain_complete_evap = _warm.rain_evap_torch(
        state.qr, pre.rh_w, pre.supsat,
        n0r, work1_r, pre.work2,
        pre.slope.rslope_r, pre.slope.rslopeb_r,
        pre.slope.rslope2_r, pre.slope.rslopemu_r,
        params=params.rain_evap, dtcld=dtcld,
        return_complete_evap=True,
    )

    # ── B5: Saturation adjustment — DEFERRED (not computed here). qv↔qc condensation is
    # done once in apply_satadj_step_torch, after state_update + reclassifications
    # (Fortran F:2922-2943). A duplicate warm-phase satadj used to live here, but its pcond
    # output was never consumed by the driver (apply_satadj_step recomputes it), so it was
    # removed to drop dead compute and stay structurally aligned with the C++ WarmPhaseOutputs
    # (8 rates). The qv-dependence of the warm phase therefore lives only in apply_satadj_step.

    return WarmPhaseOutputs(
        praut=praut, nraut=nraut,
        pracw=pracw, nracw=nracw,
        nccol=nccol, nrcol=nrcol,
        prevp=prevp,
        rain_complete_evap=rain_complete_evap,
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
    # C6' (codex#4): graupel evap (Fortran 2438-2440)
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

    Process order (Fortran 1818-2440):
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

    # Codex stop-review fix: the cold deposition/nucleation driver is ICE
    # supersaturation — Fortran module_mp_kdm6.F:1822 supsat=max(q,qmin)-qs(i,k,2) (qs2=ice
    # sat), feeding satdt/supice/ifsat + the C3 gate (:2309) and pidep/psdep/pgdep
    # caps (:2323-2390). pre.supsat is WATER (q-qs1, right for the WARM loop :1695,
    # wrong for cold). Reconstruct ice supsat from existing fields — EXACT since
    #   supsat + qs1 - qs2 = (max(q,qmin)-qs1) + qs1 - qs2 = max(q,qmin) - qs2.
    # Used ONLY by C3 (ice_nucleation) + C4 (dep_sub); snow/graupel evap use rh_*.
    supsat_ice = pre.supsat + pre.qs1 - pre.qs2

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
        pre.supcol, supsat_ice, pre.rh_ice, prevp,
        state.ni, forcing.den,
        params=params.ice_nucleation, dtcld=dtcld,
    )

    # ── C4: deposition/sublimation ───────────────────────────────────
    depsub = _cold.dep_sub_torch(
        state.qi, state.qs, state.qg,
        pre.rh_ice, pre.supcol, supsat_ice,
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
    # review3#1 fix: Fortran 1679 work1(i,k,1)=water diffusivity. ice 분기 아님.
    psevp = _cold.snow_evap_torch(
        state.qs, pre.rh_w, pre.supcol,
        n0so, s.n0sfac, work1_water, pre.work2,
        s.rslope_s, s.rslope2_s, s.rslopeb_s, s.rslopemu_s,
        params=params.snow_evap, dtcld=dtcld,
    )

    # ── C6': graupel evap (warm-only) — codex#4 fix + review3#1 ─────
    # Fortran 2438-2440: psevp와 동일 구조 (work1(:,:,1) water branch),
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


def melt_freeze_d1_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    pre: PreambleOutputs,
    n0so: torch.Tensor,
    n0go: torch.Tensor,
    *,
    params: MeltFreezePhaseParams,
    dtcld: float,
) -> MeltFreezePhaseOutputs:
    """Stage-A STEP 3 split: D1 melt only (warm cells). Applied inline first; a
    rebuild then re-slopes before D2-D4 (Fortran module_mp_kdm6.F melt :1274-1345 →
    re-slope :1422-1480 → freeze :1485-1561). Returns D2-D5 zeroed. 1:1 mirror of
    C++ melt_freeze_d1.
    """
    s = pre.slope
    z = torch.zeros_like(state.qc)
    melt = _mf.melting_torch(
        state.qs, state.qg, state.qi, state.ni,
        state.t, forcing.p, forcing.den, pre.progb.rhox,
        n0so, n0go, s.n0sfac, pre.work2, pre.progb.precg2,
        s.rslope_s, s.rslope2_s, s.rslopeb_s, s.rslopemu_s,
        s.rslope_g, s.rslope2_g, s.rslopeb_g, s.rslopemu_g,
        params=params.melting, dtcld=dtcld,
    )
    return MeltFreezePhaseOutputs(
        psmlt=melt.psmlt, pgmlt=melt.pgmlt,
        pimlt_qi=melt.pimlt_qi, pimlt_ni=melt.pimlt_ni,
        sfac_melt=melt.sfac, gfac_melt=melt.gfac,
        delta_brs_melt=melt.delta_brs,
        pinuc=z, ninuc=z, pfrzdtc=z, nfrzdtc=z,        # D2-D4 → melt_freeze_d2_d4_torch
        pfrzdtr=z, nfrzdtr=z, delta_brs_freeze=z,
        pseml=z, nseml=z, pgeml=z, ngeml=z,            # D5
    )


def melt_freeze_d2_d4_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    pre: PreambleOutputs,
    n0c: torch.Tensor,
    n0r: torch.Tensor,
    rslopec: torch.Tensor,
    rslopecmu: torch.Tensor,
    rslopecd: torch.Tensor,
    *,
    params: MeltFreezePhaseParams,
    dtcld: float,
) -> MeltFreezePhaseOutputs:
    """Stage-A STEP 3 split: D2 contact + D3 Bigg-cloud (post-D2 cap) + D4 Bigg-rain,
    computed on the POST-MELT/re-sloped state. Returns D1+D5 zeroed. 1:1 mirror of
    C++ melt_freeze_d2_d4.
    """
    s = pre.slope
    z = torch.zeros_like(state.qc)

    # ── D2: Contact freezing ───────────────────────────────────────────
    rslopec2 = rslopec * rslopec
    rslopec3 = rslopec2 * rslopec
    contact = _mf.contact_freezing_torch(
        state.qc, state.nc, state.t, forcing.p, forcing.den,
        n0c, rslopec, rslopec2, rslopec3, rslopecmu,
        pre.supcol,
        params=params.contact, dtcld=dtcld,
    )

    # ── D3: Bigg cloud (STEP 4: caps vs POST-D2 qc/nc; Fortran :1512-1537) ──
    qc_post_d2 = state.qc - contact.pinuc
    nc_post_d2 = state.nc - contact.ninuc
    bigg_c = _mf.bigg_cloud_freezing_torch(
        qc_post_d2, nc_post_d2, forcing.den, n0c,
        rslopec, rslopecd, rslopecmu, pre.supcol,
        params=params.bigg_cloud, dtcld=dtcld,
    )

    # ── D4: Bigg rain ──────────────────────────────────────────────────
    bigg_r = _mf.bigg_rain_freezing_torch(
        state.qr, state.nr, forcing.den, n0r,
        s.rslope_r, s.rsloped_r, s.rslopemu_r, pre.supcol,
        params=params.bigg_rain, dtcld=dtcld,
    )

    return MeltFreezePhaseOutputs(
        psmlt=z, pgmlt=z, pimlt_qi=z, pimlt_ni=z,      # D1 → melt_freeze_d1_torch
        sfac_melt=z, gfac_melt=z, delta_brs_melt=z,
        pinuc=contact.pinuc, ninuc=contact.ninuc,
        pfrzdtc=bigg_c.pfrzdtc, nfrzdtc=bigg_c.nfrzdtc,
        pfrzdtr=bigg_r.pfrzdtr, nfrzdtr=bigg_r.nfrzdtr,
        delta_brs_freeze=bigg_r.delta_brs,
        pseml=z, nseml=z, pgeml=z, ngeml=z,            # D5
    )


def melt_freeze_d1_d4_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    pre: PreambleOutputs,
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
    """Combiner — D1-D4 from one state (D5 zeroed). 1:1 mirror of C++
    melt_freeze_d1_d4. Used by melt_freeze_phase_torch + tests.
    """
    out = melt_freeze_d1_torch(state, forcing, pre, n0so, n0go, params=params, dtcld=dtcld)
    d234 = melt_freeze_d2_d4_torch(
        state, forcing, pre, n0c, n0r, rslopec, rslopecmu, rslopecd,
        params=params, dtcld=dtcld)
    return out._replace(
        pinuc=d234.pinuc, ninuc=d234.ninuc,
        pfrzdtc=d234.pfrzdtc, nfrzdtc=d234.nfrzdtc,
        pfrzdtr=d234.pfrzdtr, nfrzdtr=d234.nfrzdtr,
        delta_brs_freeze=d234.delta_brs_freeze,
    )


def melt_freeze_d5_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    pre: PreambleOutputs,
    cold_out: ColdPhaseOutputs,    # paacw_adj, psacr_adj, pgacr_adj 사용
    n0so: torch.Tensor,
    n0go: torch.Tensor,
    *,
    params: MeltFreezePhaseParams,
    dtcld: float,
) -> MeltFreezePhaseOutputs:
    """Stage-A STEP 2 split: D5 enhanced melting — needs cold_out's accretion
    rates, so computed AFTER cold_phase on the post-melt/freeze working state.
    Returns D1-D4 fields zeroed. 1:1 mirror of C++ melt_freeze_d5.
    """
    s = pre.slope
    z = torch.zeros_like(state.qc)

    # ── D5: Enhanced melting (uses cold's adjusted paacw/psacr/pgacr) ──
    enh = _mf.enhanced_melting_torch(
        state.qs, state.qg,
        cold_out.paacw_adj, cold_out.psacr_adj, cold_out.pgacr_adj,
        n0so, n0go, s.n0sfac,
        s.rslope_s, s.rslope_g, pre.supcol,
        params=params.enhanced_melt, dtcld=dtcld,
    )

    return MeltFreezePhaseOutputs(
        psmlt=z, pgmlt=z, pimlt_qi=z, pimlt_ni=z,
        sfac_melt=z, gfac_melt=z, delta_brs_melt=z,
        pinuc=z, ninuc=z, pfrzdtc=z, nfrzdtc=z,
        pfrzdtr=z, nfrzdtr=z, delta_brs_freeze=z,
        pseml=enh.pseml, nseml=enh.nseml,
        pgeml=enh.pgeml, ngeml=enh.ngeml,
    )


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
    """F1d — legacy single-call melt/freeze (D1-D5 from one state). Thin combiner
    over the split halves (melt_freeze_d1_d4_torch + melt_freeze_d5_torch); used by
    tests + the STEP 1 parallel-from-entry path. Process order:
      D1 melting → D2 contact freeze → D3 Bigg cloud → D4 Bigg rain → D5 enh-melt.
    """
    out = melt_freeze_d1_d4_torch(
        state, forcing, pre, n0c, n0r, n0so, n0go,
        rslopec, rslopecmu, rslopecd, params=params, dtcld=dtcld,
    )
    d5 = melt_freeze_d5_torch(
        state, forcing, pre, cold_out, n0so, n0go, params=params, dtcld=dtcld,
    )
    return out._replace(
        pseml=d5.pseml, nseml=d5.nseml, pgeml=d5.pgeml, ngeml=d5.ngeml,
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
    ncmin_tensor=None,   # per-cell ncmin floor for cloud/ice NUMBER budgets (1:1 fix #18)
):
    """F1d2 — Fortran group conservation budgets (module_mp_kdm6.F :2460-2597
    cold-arm + :2657-2728 warm-arm). 14 budgets: value=max(floor,reservoir);
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
    cold_gate = supcol >= 0         # Fortran F:2456 `t.le.t0c` ⇔ supcol>=0; == state_update cold_mask
    warm_gate = supcol < 0          # complement (warm arm, Fortran t>t0c). Boundary supcol==0 is a
                                    # no-op (all cold rates strict-gated supcol>0 ⇒ 0 there); literal-fidelity only
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

    def limit_ncmin(reservoir, source_sum, gate, names):
        # Per-cell ncmin floor (xland-derived) for cloud/ice NUMBER budgets — Fortran
        # F:2554/2568/2706 max(ncmin,nci), ncmin=10/100, NOT hardcoded 0.01. 1:1 fix #18.
        value = (torch.maximum(reservoir, ncmin_tensor) if ncmin_tensor is not None
                 else torch.clamp(reservoir, min=c.NCMIN))
        source = source_sum * dtcld
        factor = torch.where(gate, value / torch.maximum(source, value),
                             torch.ones_like(value))
        for nm in names:
            r[nm] = r[nm] * factor

    # ── PASS 1: cold arm (t<=t0c), gate=cold_gate ──────────────────────────
    limit(state.qc, EPS,                                              # cloud mass :2460
          r["praut"] + r["pracw"] + 2.0 * r["paacw_adj"] + r["piacw"]
          + r["pmulcs"] + r["pmulcg"], cold_gate,
          ("praut", "pracw", "paacw_adj", "piacw", "pmulcs", "pmulcg"))
    limit(state.qi, EPS,                                              # ice mass :2475
          r["psaut"] - r["pinud"] - r["pidep"] + r["praci"] + r["psaci"]
          + r["pgaci"] - r["pmulcs"] - r["pmulrs"] - r["pmulcg"] - r["pmulrg"]
          - r["piacw"], cold_gate,
          ("psaut", "pinud", "pidep", "praci", "psaci", "pgaci", "piacw",
           "pmulcs", "pmulrs", "pmulcg", "pmulrg"))
    limit(state.qr, EPS,                                              # rain mass :2495
          -r["praut"] - r["prevp"] - r["pracw"] + r["piacr"] + r["psacr_adj"]
          + r["pgacr_adj"] + r["pmulrs"] + r["pmulrg"], cold_gate,
          ("praut", "prevp", "pracw", "piacr", "psacr_adj", "pgacr_adj",
           "pmulrs", "pmulrg"))
    limit(state.qs, EPS,                                              # snow mass :2512 (pgaut,pgacs≡0)
          -(r["psdep"] + r["psaut"] + r["paacw_adj"] + r["piacr"] * delta3
            + r["praci"] * delta3 - r["pracs"] * one_m_d2
            + r["psacr_adj"] * delta2 + r["psaci"]), cold_gate,
          ("psdep", "psaut", "paacw_adj", "piacr", "praci", "psaci", "pracs",
           "psacr_adj"))
    limit(state.qg, EPS,                                              # graupel mass :2533 (pgaut,pgacs≡0)
          -(r["pgdep"] + r["piacr"] * one_m_d3 + r["praci"] * one_m_d3
            + r["psacr_adj"] * one_m_d2 + r["pracs"] * one_m_d2 + r["pgaci"]
            + r["paacw_adj"] + r["pgacr_adj"]), cold_gate,
          ("pgdep", "piacr", "praci", "psacr_adj", "pracs", "paacw_adj",
           "pgaci", "pgacr_adj"))
    limit_ncmin(state.nc,                                             # cloud number :2554
          r["nraut"] + r["nccol"] + r["nracw"] + r["niacw"] + 2.0 * r["naacw"],
          cold_gate, ("nraut", "nccol", "nracw", "naacw", "niacw"))
    limit_ncmin(state.ni,                                             # ice number :2568
          r["nraci"] + r["nsaci"] + r["ngaci"] + r["niacr"] + r["nsaut"]
          - r["nmulcs"] - r["nmulcg"] - r["nmulrs"] - r["nmulrg"] - r["ninud"],
          cold_gate,
          ("nraci", "nsaci", "ngaci", "niacr", "nsaut", "ninud", "nmulcs",
           "nmulcg", "nmulrs", "nmulrg"))
    limit(state.nr, c.NRMIN,                                          # rain number :2587
          -r["nraut"] + r["nraci"] + r["nrcol"] + r["niacr"] + r["nsacr"]
          + r["ngacr"], cold_gate,
          ("nraci", "nraut", "nrcol", "niacr", "nsacr", "ngacr"))

    # ── PASS 2: warm arm (t>t0c), gate=warm_gate ───────────────────────────
    limit(state.qc, EPS,                                             # cloud mass :2657
          r["praut"] + r["pracw"] + 2.0 * r["paacw_adj"], warm_gate,
          ("praut", "pracw", "paacw_adj"))
    limit(state.qr, EPS,                                             # rain mass :2669
          -2.0 * r["paacw_adj"] - r["praut"] + r["pseml"] + r["pgeml"]
          - r["pracw"] - r["prevp"], warm_gate,
          ("praut", "prevp", "pracw", "paacw_adj", "pseml", "pgeml"))
    limit(state.qs, c.QCRMIN,                                        # snow mass :2684 (pgacs≡0)
          -r["pseml"] - r["psevp"], warm_gate, ("psevp", "pseml"))
    limit(state.qg, c.QCRMIN,                                        # graupel mass :2695 (pgacs≡0)
          -(r["pgevp"] + r["pgeml"]), warm_gate, ("pgevp", "pgeml"))
    limit_ncmin(state.nc,                                            # cloud number :2706
          r["nraut"] + r["nccol"] + r["nracw"] + 2.0 * r["naacw"], warm_gate,
          ("nraut", "nccol", "nracw", "naacw"))
    limit(state.nr, c.NRMIN,                                         # rain number :2719
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
    state_update_torch). xlf: D1 melt → xlf0 (const), D2-D4 freeze → xls-pre.xl(T). 1:1 mirror of
    C++ apply_melt_freeze_inline.
    """
    dtype = state.qc.dtype
    warm_mask = (pre.supcol < 0).to(dtype)  # Fortran F:1279 melt gate `t.gt.t0c` ⇔ supcol<0 (strict);
                                             # matches state_update warm_mask (1-cold_mask, cold=supcol>=0).
                                             # Codex round-3 Finding 1: must be <0 (not <=0) to keep
                                             # inline↔state_update algebraically identical at supcol==0.
    cpm_safe = torch.clamp(pre.cpm, min=c.QCRMIN)
    # D1 MELT holds xlf = xlf0 (constant 3.5e5; Fortran F:1275 `if(supcol<0) xlf=xlf0`, and the
    # whole melt block runs at T>T0c so it always uses xlf0 — for BOTH the rate AND the t-update).
    # D2-D4 FREEZE uses the variable xls-xl(T) (Fortran F:1404). They must NOT share one xlf: using
    # xls-xl for the melt heat-sink over-cools by +0.67%/K above freezing (audit round-6).
    xlf_freeze = xls - pre.xl
    xlf_melt = _mf.DEFAULT_XLF
    return state._replace(
        qc=state.qc + (-mf.pinuc - mf.pfrzdtc + mf.pimlt_qi),
        qr=state.qr + dtcld * (-(mf.psmlt + mf.pgmlt) * warm_mask) - mf.pfrzdtr,
        qs=state.qs + dtcld * mf.psmlt,
        qg=state.qg + dtcld * mf.pgmlt + mf.pfrzdtr,
        qi=state.qi + (mf.pinuc + mf.pfrzdtc - mf.pimlt_qi),
        nc=state.nc + (-mf.ninuc - mf.nfrzdtc + mf.pimlt_ni),
        nr=state.nr + (-mf.nfrzdtr)
        + dtcld * (-mf.sfac_melt * mf.psmlt - mf.gfac_melt * mf.pgmlt),  # D1 melt snow/graupel → rain number (Fortran 1299/1323)
        ni=state.ni + (mf.ninuc + mf.nfrzdtc - mf.pimlt_ni),
        brs=state.brs + (dtcld * mf.delta_brs_melt + mf.delta_brs_freeze),
        t=state.t
        + dtcld * xlf_melt / cpm_safe * (mf.psmlt + mf.pgmlt)            # D1 melt rates → xlf0
        - xlf_melt / cpm_safe * mf.pimlt_qi                             # D1 instant ice-melt → xlf0
        + xlf_freeze / cpm_safe * (mf.pinuc + mf.pfrzdtc + mf.pfrzdtr),  # D2-D4 freeze → xls-xl(T)
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

    Note: Fortran의 모든 mutation을 정확히 직역. T-branch routing은 *cold*=`supcol >= 0`
    (Fortran F:2456 `t.le.t0c`), *warm*=`supcol < 0` mask로 처리. 경계 supcol==0은
    no-op (cold rate가 모두 strict-gate supcol>0 ⇒ 0) — 리터럴 충실도용.
    """
    cold_mask = (pre.supcol >= 0).to(state.qc.dtype)  # Fortran F:2456 `t.le.t0c` ⇔ supcol>=0
    warm_mask = 1.0 - cold_mask  # = supcol<0 (Fortran t>t0c)

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
        # Fortran :2922-2943; mirrors C++ apply_satadj_step). NOT applied here.
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
        - cold.piacw                                             # 2616 piacw (qc→qi)
        - 2.0 * cold.paacw_adj                                   # 2616: paacw·2 (qc→qs+qg)
        - cold.pmulcs - cold.pmulcg                              # 2616 C2e HM
    )
    dqc_amount = -mf.pinuc - mf.pfrzdtc + mf.pimlt_qi            # 1505/1533/1337 (amounts)
    dqc = dqc_rate + dqc_amount
    qc_new = state.qc + dqc

    # qr (rain water)
    dqr_rate = dtcld * (
        warm.praut + warm.pracw                   # B1/B2 (qc→qr)
        + warm.prevp                              # 2740 prevp<0 → qr 감소
        - cold.piacr - cold.pgacr_adj - cold.psacr_adj  # 2621-2623 rain collected (sinks)
        - cold.pmulrs - cold.pmulrg               # 2623 HM rain→ice splinter sinks
        - (mf.psmlt + mf.pgmlt) * warm_mask       # D1 psmlt<0 → qr 증가 (qr -= psmlt)
        - mf.pseml - mf.pgeml                     # D5 enhanced melt (pseml<0 → qr 증가)
        + 2.0 * cold.paacw_adj * warm_mask        # #1: WARM arm sheds rimed cloud to RAIN (Fortran :2740 qr+=2*paacw);
                                                  # cold arm routes paacw to qs/qg (below, cold_mask). Mirrors C++.
    )
    dqr_amount = -mf.pfrzdtr                      # 1560 Bigg rain → qg (amount)
    dqr = dqr_rate + dqr_amount
    qr_new = state.qr + dqr

    # ── delta2/delta3 routing flags (Fortran 2452-2455) — review3#5
    #   delta2 = 1 if (qr<1e-4 AND qs<1e-4): psacr → qs, pracs stays in snow
    #   delta3 = 1 if (qr<1e-4):              piacr/praci → qs (else → qg)
    # Stage-A STEP 1: from ENTRY state (ds) when base is a working state.
    ds = delta_src if delta_src is not None else state
    delta2 = ((ds.qr < 1.0e-4) & (ds.qs < 1.0e-4)).to(state.qc.dtype)
    delta3 = (ds.qr < 1.0e-4).to(state.qc.dtype)
    one_m_d2 = 1.0 - delta2
    one_m_d3 = 1.0 - delta3

    # qs (snow) — Fortran 2633-2637 + warm-branch 2743 직역
    # review4#1: psacw 제거 (Fortran 2633은 paacw만 사용); cold_mask 제거 (paacw 무조건 적용);
    #   psevp 추가 (warm branch snow→vapor 직접 sink, Fortran 2743 일부).
    dqs = dtcld * (
        cold.psdep                                # C4 deposition
        + cold.psaut                              # C5 ice aggregation → snow
        + cold.paacw_adj * cold_mask              # #1: paacw→qs only in COLD arm (Fortran :2633); warm arm sheds to qr
        + cold.piacr * delta3                     # piacr → qs when qr small
        + cold.praci * delta3                     # praci → qs when qr small
        + cold.psacr_adj * delta2                 # psacr → qs when qr&qs small
        + cold.psaci                              # C2 ice → snow
        - cold.pracs * one_m_d2                   # snow→graupel when (1-delta2)
        + cold.psevp                              # 2743 warm: snow evap (psevp<0 → qs sink)
        + mf.psmlt                                # D1 melt (psmlt<0 → qs sink)
        + mf.pseml                                # D5 enhanced melt
        # review5 audit: pmulcs 제거 — Fortran 2633은 pmul* 없음. paacw_adj가 이미
        # HM 분기를 반영 (paacw_adj = paacw - pmulcs - pmulcg). pmul* 추가 시 double-count.
    )
    qs_new = state.qs + dqs

    # qg (graupel) — Fortran 2638-2642 + warm-branch 2745 직역
    # review4#1: pgacw 제거; cold_mask 제거. pgevp 유지 (codex#4).
    dqg_rate = dtcld * (
        cold.pgdep                                # C4 deposition
        + cold.paacw_adj * cold_mask              # #1: paacw→qg only in COLD arm (Fortran :2641); warm arm sheds to qr
        + cold.pgacr_adj                          # 2641 rain ←collected by graupel
        + cold.pracs * one_m_d2                   # snow → graupel when (1-delta2)
        + cold.piacr * one_m_d3                   # piacr → qg when qr ≥ 1e-4
        + cold.praci * one_m_d3                   # praci → qg when qr ≥ 1e-4
        + cold.psacr_adj * one_m_d2               # psacr → qg
        + cold.pgaci                              # C2 ice → graupel
        + cold.pgevp                              # C6' graupel evap (pgevp<0 → qg sink)
        + mf.pgmlt                                # D1 (pgmlt<0 → qg sink)
        + mf.pgeml                                # D5 enhanced melt
    )
    dqg_amount = mf.pfrzdtr                       # 1558 Bigg rain → qg (amount)
    dqg = dqg_rate + dqg_amount
    qg_new = state.qg + dqg

    # qi (cloud ice)
    # qi (cloud ice) — Fortran 2626-2630 + inline 1505/1533/1337
    dqi_rate = dtcld * (
        cold.pinud + cold.pidep                   # C3/C4 vapor → ice (+)
        + cold.piacw                              # 2626 piacw cloud → ice (+)
        - cold.praci - cold.psaci - cold.pgaci    # 2626 ice → rain/snow/graupel (sinks)
        - cold.psaut                              # 2626 ice → snow aggregation (sink)
        + cold.pmulcs + cold.pmulrs               # 2628 HM (+ to ice)
        + cold.pmulcg + cold.pmulrg               # 2628 HM (+ to ice)
    )
    dqi_amount = mf.pinuc + mf.pfrzdtc - mf.pimlt_qi   # 1506/1534/1338 (amounts)
    dqi = dqi_rate + dqi_amount
    qi_new = state.qi + dqi

    # ── Number balance ────────────────────────────────────────────────
    # nc (cloud number) — Fortran 2733 + inline 1603/1633
    # nc (cloud number) — Fortran 2619 + inline 1500/1530/1338
    dnc_rate = dtcld * (
        - warm.nraut                              # qc → qr autoconv
        - warm.nccol                              # cloud self-collection
        - warm.nracw                              # qc → qr accretion
        - cold.niacw                              # C2c ice riming on cloud
        - 2.0 * cold.naacw                        # naacw 2× (Fortran 2620)
    )
    dnc_amount = -mf.ninuc - mf.nfrzdtc + mf.pimlt_ni  # 1500/1530/1338 (amounts)
    dnc = dnc_rate + dnc_amount
    nc_new = state.nc + dnc

    # nr (rain number) — Fortran 2624 + inline 1556
    dnr_rate = dtcld * (
        warm.nraut                                # B1 autoconv → rain
        - warm.nrcol                              # rain self-collection
        - cold.niacr - cold.nraci                 # 2624 rain ←collected by ice
        - cold.nsacr - cold.ngacr                 # 2625 rain ←snow/graupel
        + mf.nseml + mf.ngeml                     # 2749-2750 warm enhanced-melt number → rain
                                                  # (warm-gated in melt_freeze ⇒ no-op when cold; mirrors C++)
        - mf.sfac_melt * mf.psmlt - mf.gfac_melt * mf.pgmlt  # D1 melt snow/graupel → rain number (Fortran 1299/1323; D1-zeroed in mf5 at runtime, preserves inline↔state_update identity)
    )
    dnr_amount = -mf.nfrzdtr                      # 1556 Bigg rain (amount)
    dnr = dnr_rate + dnr_amount
    # NOTE: complete-rain-evap nr-zeroing (Fortran :1794) is NOT applied here.
    # It must run BEFORE the conservation budget (so the rain-number budget reads
    # the zeroed nr) and before the cold-phase rates that read nr — i.e. right
    # after warm_phase, not in state_update. Both C++ and Python currently lack
    # that correct-timed zeroing; it is scoped to the WRF-validated pass with the
    # other shared Fortran gaps (see memory project_kdm6_parity_audit_findings).
    nr_new = state.nr + dnr

    # ni (ice number) — Fortran 2630-2632 + inline 1501/1531/1338
    dni_rate = dtcld * (
        cold.ninud                                # C3 nucleation (+)
        - cold.nraci - cold.nsaci - cold.ngaci    # 2630 ice → rain/snow/graupel (sinks)
        - cold.niacr                              # 2631 niacr (rain ←ice의 ice 소멸)
        + cold.nmulcs + cold.nmulcg               # 2631 HM cloud splinter (+)
        + cold.nmulrs + cold.nmulrg               # 2632 HM rain splinter (+)
        - cold.nsaut                              # 2632 ice → snow aggregation (-)
    )
    dni_amount = mf.ninuc + mf.nfrzdtc - mf.pimlt_ni  # 1501/1531/1338 (amounts)
    dni = dni_rate + dni_amount
    ni_new_pre = state.ni + dni
    # review3#2: complete sublimation (pidep == -qi/dtcld) 시 ni=0 강제 (Fortran 2343-2344
    # 영역의 nci=0 처리). 매끄러운 mask는 cold.ice_complete_sublim (bool).
    ni_zero_mask = cold.ice_complete_sublim.to(state.qc.dtype)
    ni_new = ni_new_pre * (1.0 - ni_zero_mask)

    # brs (graupel volume) — review4#3: Fortran 2643-2645 (cold) + 2751 (warm) 직역.
    #   기존 mf.delta_brs_melt (pgmlt/rhox), mf.delta_brs_freeze (pfrzdtr/denr) 외에
    #   cold-branch 8 항 + warm-branch pgevp 추가.
    rhox_safe = torch.clamp(pre.progb.rhox, min=c.DENS)  # Fortran 2768 max(rhox, dens)
    dbrs_cold_riming = cold_mask * dtcld * (
        cold.pgdep / rhox_safe                # 2643 graupel deposition
        + cold.piacr / c.DENR                  # biacr
        + cold.praci / c.DENI                  # braci
        + cold.psacr_adj / c.DENR              # bsacr (post-HM adj)
        + cold.pracs / c.DENS                  # bracs
        + cold.pgaci / c.DENI                  # bgaci
        + cold.paacw_adj / c.DENR              # baacw (post-HM adj)
        + cold.pgacr_adj / c.DENR              # bgacr (post-HM adj)
    )
    dbrs_warm_evap = warm_mask * dtcld * (
        cold.pgevp / rhox_safe                 # 2734 bgevp (pgevp<0 → brs 감소)
        + mf.pgeml / rhox_safe                 # 2735 bgeml (pgeml<0 → brs 감소)
    )
    # delta_brs_melt = pgmlt/rhox (rate, *dtcld 필요), delta_brs_freeze = pfrzdtr/denr (amount, 그대로)
    dbrs = (
        dtcld * mf.delta_brs_melt              # D1 pgmlt/rhox (rate)
        + mf.delta_brs_freeze                  # D4 pfrzdtr/denr (amount)
        + dbrs_cold_riming
        + dbrs_warm_evap
    )
    # review5#3: Fortran 2643/2751 `brs = max(brs+...,0.)` 직역. AD subgradient at 0
    # boundary는 well-defined (zero gradient on clamped cells).
    brs_new = torch.clamp(state.brs + dbrs, min=0.0)

    # ── Energy balance (T) — review3#4 fix: xls/xlf split ────────────
    # Fortran 2647-2650: xlwork2 = -xls·(psdep+pgdep+pidep+pinud) + xl·(prevp+psevp+pgevp)
    #                              + freeze/melt 항(xlf), t -= xlwork2/cpm·dtcld.
    #   Fortran 2646: xlf = xls - xl(T). xls is the CONSTANT sublimation latent
    #   heat (2.85e6); fusion xlf is DERIVED and TEMPERATURE-DEPENDENT. The prior
    #   code inverted this (constant xlf, derived xls), over-heating freezing at
    #   cold T. Mirrors the C++ coordinator.cpp fix (single bug across both ports).
    #   세 group으로 분리:
    #     (a) warm-phase vapor↔water (xl): pcond, prevp, psevp, pgevp
    #     (b) deposition/sublimation vapor↔ice (xls, CONSTANT): pinud, pidep, psdep, pgdep
    #     (c) freeze/melt liquid↔solid (xlf=xls-xl(T)): pinuc, pfrzdtc, pfrzdtr, psmlt, pgmlt, pimlt_qi, pseml, pgeml
    cpm_safe = torch.clamp(pre.cpm, min=c.QCRMIN)
    xlf = xls - pre.xl  # freeze/D5/cold-riming fusion latent heat (J/kg), temperature-dependent
    # D1 MELT (psmlt/pgmlt/pimlt_qi) uses the CONSTANT xlf0, NOT xls-xl(T): Fortran F:1275
    # `if(supcol<0) xlf=xlf0` then the melt block applies it at F:1303/1327/1339. This mirrors
    # apply_melt_freeze_inline (audit round-6); the single-xlf form over-cooled the D1-melt heat
    # in the component/legacy state_update path by +0.67%/K above freezing (Codex round-2 catch).
    # Runtime is shielded (mf5 zeroes D1 before state_update) so this is parity-inert; the split
    # restores the inline↔state_update algebraic identity. D5 pseml/pgeml stay on xls-xl(T)
    # (Fortran warm-branch F:2752); cold riming on xls-xl(T) (F:2645).
    xlf_melt = _mf.DEFAULT_XLF

    dT_warm_phase = dtcld * pre.xl / cpm_safe * (
        # pcond warming DEFERRED to apply_satadj_step_torch (post-reclass).
        warm.prevp                            # B4 rain evap (prevp<0 → cooling)
        + cold.psevp                          # C6 snow evap (psevp<0 → cooling)
        + cold.pgevp                          # C6' graupel evap (pgevp<0 → cooling)
    )
    dT_dep_phase = dtcld * xls / cpm_safe * (
        cold.pinud + cold.pidep + cold.psdep + cold.pgdep   # vapor→ice deposition (xls)
    )
    # D1 melt (psmlt/pgmlt rate + pimlt_qi amount) → CONSTANT xlf0 (Fortran F:1303/1327/1339).
    dT_melt_d1 = (
        dtcld * xlf_melt / cpm_safe * (mf.psmlt + mf.pgmlt)   # D1 snow/graupel melt (rate, cooling)
        - xlf_melt / cpm_safe * mf.pimlt_qi                   # 1339 D1 instant ice-melt (amount, cooling)
    )
    # xlf group — review4#4: Fortran 2647-2650 cold branch xlf list 추가.
    #   Fortran의 paacw/psacr/pgacr는 HM 후 *post-adjusted* value이므로, 우리 oracle의
    #   paacw_adj/psacr_adj/pgacr_adj와 동일. piacr·1 + paacw·2 + pmul*·1 + piacw·1
    #   + pgacr·1 + psacr·1 = 10 항.
    # xlf rate group (D5 + cold riming) — D1 melt moved to dT_melt_d1 (xlf0, Codex round-2).
    dT_freeze_rate = dtcld * xlf / cpm_safe * (
        mf.pseml + mf.pgeml                     # D5 enhanced melt cooling (xls-xl, Fortran F:2752)
        # cold-branch riming/freezing: liquid → solid → fusion latent heat 방출 → warming
        + cold_mask * (
            cold.piacr                          # 2648 rain frozen on ice
            + 2.0 * cold.paacw_adj              # 2649 paacw·2 (cloud rimed on snow+graupel)
            + cold.pmulcs + cold.pmulcg         # 2649 HM cloud splinter
            + cold.pmulrs + cold.pmulrg         # 2649 HM rain splinter
            + cold.piacw                        # 2650 cloud frozen on ice
            + cold.pgacr_adj + cold.psacr_adj   # 2650 rain collected by graupel/snow
        )
    )
    # xlf amount group (D2-D4 freezes) — D1 ice-melt pimlt_qi moved to dT_melt_d1 (xlf0).
    dT_freeze_amount = xlf / cpm_safe * (
        mf.pinuc + mf.pfrzdtc + mf.pfrzdtr      # 1507/1536/1559 inline (amount, +)
    )
    dT_freeze_phase = dT_melt_d1 + dT_freeze_rate + dT_freeze_amount
    t_new = state.t + dT_warm_phase + dT_dep_phase + dT_freeze_phase

    # review5#2 (partial): Fortran 2615-2756 `max(... ,0.)` — nonnegative clamp만 적용.
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
    """Fortran 2951-2970 padding for small values (post-reclassification).

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
    """Fortran 2807-2813 (Picons, Park-Lim 2023): 평균 직경이 임계값(200μm) 이상인
    cloud ice는 더 이상 ice이 아니라 snow로 재분류. T<0°C, qi>qmin 게이트.

    review6#1 / review7#1 fix: avedia_i를 *post-update* qi/ni/den으로 inline 재진단
    (Fortran 2800-2802 처럼 slope_kdm6 재호출 후 avedia 다시 계산하는 것을 흉내).
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
    avedia_factor = (g4pmi / g1pmi) ** 0.3333333  # Fortran F:2802 ice avedia .3333333 literal. 1:1 fix #4/#11
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
    """Fortran 2883-2892: post-update 평균 빗방울 직경(avedia_r) ≤ 82μm 시
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
    avedia_factor = (g4pmr / g1pmr) ** 0.3333333  # Fortran F:2878 rain avedia .3333333 literal. 1:1 fix #4/#11
    rslopermax = 1.0 / c.LAMDARMAX

    eps = 1.0e-30
    rain_active = (state.qr > qcrmin) & (state.nr > 0.0) & (den > 0.0)
    qr_safe = torch.clamp(state.qr * den, min=eps)
    ratio = pidnr * torch.clamp(state.nr, min=0.0) / qr_safe
    lamdar = torch.clamp(ratio, min=eps) ** (1.0 / c.DMR)
    # Fortran F:3490 active rain slope = min(1/lamdar, 1e-3): UPPER cap (1e-3 literal) ONLY, NO
    # lower floor. The earlier `min=rslopermax` floor pinned avedia_r ≥ rslopermax·factor ≈ 82.4μm
    # > di82=82μm, so the small-drop NR→NC / QR→QC reclass (Fortran F:2879-2892, LH A14/A15) could
    # NEVER fire — dead code vs Fortran. The inactive branch keeps rslopermax (F:3483), matching the
    # authoritative slope module (slope.py:161-163 / slope.cpp:44-46). audit round-3.
    rslope_r_active = torch.minimum(1.0 / torch.clamp(lamdar, min=eps),
                                    torch.full_like(lamdar, 1.0e-3))
    rslope_r = torch.where(rain_active, rslope_r_active,
                           torch.full_like(rslope_r_active, rslopermax))
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


# ─── Step F1i: DSD number limiters (Fortran 2972-3013) ──────────────────────


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
    """Fortran 2972-3013: post-cleanup DSD number limiter.

    Each (q, n) pair: lamda = (pidn·n / (q·den))^(1/dm). When lamda runs out of
    [lamda_min, lamda_max], snap and back-derive n. Plus rain/cloud absolute caps
    via NRMAX/NCMAX (Fortran 3007-3013).

    Note: nccn clamp `min(max(nccn, 1e8), 2e10)` (Fortran 3006)는 nccn이 본 oracle의
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
    # ice snap is Fortran module_mp_kdm6.F:2995 `qci(i,k,2).ge.qmin .and. nci(i,k,2).ge.ncmin`
    # — same qmin/ncmin pattern as the cloud snap (:2984) above. The prior 1e-14/0
    # gate mis-cited :1467 (the INLINE rate-phase snap, a different occurrence
    # with no n-gate). Adjudicated vs Fortran 2026-05-31; mirrors the C++ fix.
    ni_new = _limit_number_for_lamda(
        state.qi, state.ni, den,
        pidn=pidni, dm=c.DMI,
        lamda_min=c.LAMDAIMIN, lamda_max=c.LAMDAIMAX,
        q_thresh=qmin, n_thresh=c.NCMIN,
    )

    # Absolute number caps (Fortran 3007-3013): nrs > NRMAX → snap to lamdarmax.
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
    # Fortran F:3482-3483 inactive-rain branch: (qr<=qcrmin .or. nr<=nrmin) → rslope=rslopermax
    # = 1/LAMDARMAX. The clamp inside diag_species_slope maps qr≈0 → 1/LAMDARMAX, but a nr<=nrmin
    # cell WITH qr>qcrmin would wrongly hit 1/LAMDARMIN; the nr<=nrmin gate forces 1/LAMDARMAX so
    # n0r (and prevp / rain collection) use the correct rain intercept (Codex round-4 F3). Rain ONLY
    # — ice has no n-threshold inactive branch (only the qi≈0 clamp; see feedback_if_threshold_audit).
    rain_inactive = (state.qr <= c.QCRMIN) | (state.nr <= c.NRMIN)
    rslope_r = torch.where(rain_inactive,
                           torch.full_like(rslope_r, 1.0 / c.LAMDARMAX), rslope_r)
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
        avedia_i=rslope_i * (g4pmi / g1pmi) ** 0.3333333,  # Fortran F:1672 ice avedia .3333333 literal. 1:1 fix #4/#11
        rslopecmu=rslopecmu, rslopecd=rslopec ** c.DMC,
    )


def rebuild_aux_torch(
    state: CoordinatorState,
    forcing: CoordinatorForcing,
    sea_mask: torch.Tensor,
    *,
    params: CoordinatorParams,
    qcr_carry: torch.Tensor,
    entry_pre: PreambleOutputs,
):
    """Re-run preamble_torch + build_default_aux_torch on a working (post-melt/
    post-freeze) state. Returns (PreambleOutputs, CoordinatorAuxDiagnostics) —
    BOTH refreshed together (rebuilding aux but keeping a stale preamble is the
    806× over-deposition class). qcr is carried (sea_mask-derived). Mirrors C++
    rebuild_aux.

    THERMO STAGING (Codex stop-review fix): Fortran's re-slope after melt/freeze
    recomputes GEOMETRY (rslope*/n0*/ProgB/work2/supcol) but NOT the saturation/
    latent-heat thermo — cpm(:835)/xl(:836)/qs1/qs2/rh/sw(:910-928) are computed
    once (entry/substep-top) and the rate loop reads those entry-staged values
    (supsat=q-qs at :1695/:1822 uses entry qs; q=qv is melt/freeze-invariant). So
    splice the entry thermo from `entry_pre`; recompute work1=diffac(xl,p,t,den,qs)
    with ENTRY xl/qs + the POST-FREEZE t (Fortran :1679-1680).
    """
    pre = preamble_torch(state, forcing, sea_mask, params=params)
    pre = pre._replace(
        cpm=entry_pre.cpm, xl=entry_pre.xl, qs1=entry_pre.qs1, qs2=entry_pre.qs2,
        rh_w=entry_pre.rh_w, rh_ice=entry_pre.rh_ice, supsat=entry_pre.supsat,
    )
    aux = build_default_aux_torch(state, forcing, pre.rslopec, thermo_params=params.thermo)
    xls_t = torch.full_like(state.t, params.thermo.xls)
    work1_water = _thermo.compute_diffac(
        entry_pre.xl, forcing.p, state.t, forcing.den, entry_pre.qs1, params=params.thermo)
    work1_ice = _thermo.compute_diffac(
        xls_t, forcing.p, state.t, forcing.den, entry_pre.qs2, params=params.thermo)
    aux = aux._replace(
        qcr=qcr_carry, work1_water=work1_water, work1_ice=work1_ice, work1_r=work1_water)
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
    nccn: "torch.Tensor | None" = None,
) -> "CoordinatorState | tuple[CoordinatorState, torch.Tensor]":
    """F1g+ — saturation adjustment on the POST-state-update + POST-reclass state
    (Fortran module_mp_kdm6.F:2922-2943). Mirrors C++ apply_satadj_step.

    pcond is DEFERRED out of state_update_torch so condensation fires on the
    proper post-mass-balance, post-reclassification state — matching Fortran's
    :2922-2943 sequence (mass balance → Picons/rain-cloud reclass → satadj), NOT
    before it (which was the C++↔Python divergence Codex flagged).

    Scope vs C++: the C++ apply_satadj_step also runs pcact/ncact CCN activation
    and a complete-evap NC→NCCN transfer. This oracle's CoordinatorState has no
    `nccn` field, so those are deferred per Task #74 (same as warm_phase_torch,
    which carries no ncact/pcact). qs1 is recomputed from the post-update t
    (Fortran :2922-2926) since t may have changed. AD-safe: clamp + arithmetic only.
    """
    cpm_safe = torch.clamp(cpm, min=c.QCRMIN)

    if nccn is None:
        # No CCN activation (nccn not threaded) — satadj only. Backward-compatible path used
        # by the component tests; returns a bare CoordinatorState as before.
        qs1 = _thermo.compute_qs_water(state.t, forcing.p, params=thermo_params)
        pcond = _satadj.saturation_adjustment_torch(
            state.t, state.qv, state.qc, qs1, xl, cpm_safe, params=satadj_params, dtcld=dtcld)
        return state._replace(
            qv=torch.clamp(state.qv - pcond * dtcld, min=0.0),
            qc=torch.clamp(state.qc + pcond * dtcld, min=0.0),
            t=state.t + pcond * xl / cpm_safe * dtcld,
        )

    # ── CCN activation + satadj + complete-evap NC→NCCN ──────────────────────────
    # 1:1 mirror of C++ apply_satadj_step (coordinator.cpp:1301-1361 / Fortran :2905-2939).
    # Returns (new_state, nccn_out) — the driver carries nccn across sub-cycles. AD-safe.
    qs1 = _thermo.compute_qs_water(state.t, forcing.p, params=thermo_params)
    supsat = state.qv - qs1
    qs1_safe = torch.clamp(qs1, min=c.QCRMIN)
    sw_percent = (state.qv / qs1_safe - 1.0) * 100.0          # Fortran sw in PERCENT (:918/2848)
    sw_ratio = torch.clamp(sw_percent / 0.48, min=0.0)        # 0.48% activation cutoff (SATMAX)
    # pow(x, ACTK<1) has grad 0.6·x^-0.4 → ∞ at x=0; at exactly rh_w=1 (sw_ratio=0) that NaNs
    # the autograd. Clamp the base ≥ EPS for a finite one-sided subgradient (forward unchanged
    # where sw_ratio≫EPS, and ncact is gated to 0 at supsat≤0 so the value is unaffected).
    activated_fraction = torch.minimum(
        torch.ones_like(sw_ratio), torch.pow(torch.clamp(sw_ratio, min=c.EPS), c.ACTK))
    ncact_raw = torch.clamp((nccn + state.nc) * activated_fraction - state.nc, min=0.0) / dtcld
    ncact = torch.minimum(ncact_raw, torch.clamp(nccn, min=0.0) / dtcld)
    ncact = torch.where(supsat > 0.0, ncact, torch.zeros_like(ncact))
    pcact_raw = (4.0 * math.pi * c.DENR * (c.ACTR * 1.0e-6) ** 3) * ncact / (3.0 * forcing.den)
    pcact = torch.minimum(pcact_raw, torch.clamp(state.qv, min=0.0) / dtcld)

    # apply pcact + ncact (pre-satadj snapshot)
    qv_pp = torch.clamp(state.qv - pcact * dtcld, min=0.0)
    qc_pp = torch.clamp(state.qc + pcact * dtcld, min=0.0)
    t_pp = state.t + pcact * xl / cpm_safe * dtcld
    nc_pp = torch.clamp(state.nc + ncact * dtcld, min=0.0)
    nccn_pp = torch.clamp(nccn - ncact * dtcld, min=0.0)

    # satadj on the post-pcact snapshot (qs1 recomputed from t_pp)
    qs1_pp = _thermo.compute_qs_water(t_pp, forcing.p, params=thermo_params)
    pcond = _satadj.saturation_adjustment_torch(
        t_pp, qv_pp, qc_pp, qs1_pp, xl, cpm_safe, params=satadj_params, dtcld=dtcld)
    # complete-evap NC → NCCN (Fortran :2936-2939). C++ satadj's cloud_complete_evap mask =
    # is_sub_with_cloud & (pcond == -qc/dtcld); recomputed here (Python satadj returns pcond only).
    cloud_complete_evap = (qc_pp > 0.0) & (pcond == (-qc_pp / dtcld))
    nc_evap = nc_pp * cloud_complete_evap.to(state.qc.dtype)
    nc_final = torch.clamp(nc_pp - nc_evap, min=0.0)
    nccn_final = torch.clamp(nccn_pp + nc_evap, min=c.NCCN_MIN, max=c.NCCN_MAX)

    # apply pcond
    qv_final = torch.clamp(qv_pp - pcond * dtcld, min=0.0)
    qc_final = torch.clamp(qc_pp + pcond * dtcld, min=0.0)
    t_final = t_pp + pcond * xl / cpm_safe * dtcld

    return state._replace(qv=qv_final, qc=qc_final, t=t_final, nc=nc_final), nccn_final


def apply_homogeneous_freeze_supercold_torch(
    state: CoordinatorState,
    thermo_params,
    *,
    supcol_threshold: float = 40.0,
) -> CoordinatorState:
    """Fortran module_mp_kdm6.F:1409-1419 — at supcol > 40 (T < t0c-40 ≈ 233K) with qc>0,
    instantaneously freeze ALL cloud water to ice + release fusion latent heat:
      qi += qc; ni += nc; t += xlf/cpm·qc; qc = 0; nc = 0   (xlf = xls - xl(T)).
    Runs between D1 melt and the post-melt re-slope (Fortran order), so D2-D4 see
    the post-homog qc (=0 in homog cells). 1:1 mirror of C++
    apply_homogeneous_freeze_supercold. AD-safe (multiplicative mask). cpm uses qv
    (melt/freeze-invariant) and xl uses t — both == entry values in homog cells
    (D1 melt is warm-gated ⇒ inactive where supcol>40), matching Fortran's entry-
    fixed cpm/xl (:835-836).
    """
    dtype = state.qc.dtype
    supcol = thermo_params.t0c - state.t
    mask = ((supcol > supcol_threshold) & (state.qc > 0.0)).to(dtype)
    inv = 1.0 - mask
    xl = _thermo.compute_xl(state.t, params=thermo_params)
    cpm = _thermo.compute_cpm(state.qv, params=thermo_params)
    xlf = thermo_params.xls - xl
    cpm_safe = torch.clamp(cpm, min=c.QCRMIN)
    dT = xlf / cpm_safe * state.qc
    return state._replace(
        qc=state.qc * inv,
        qi=state.qi + state.qc * mask,
        nc=state.nc * inv,
        ni=state.ni + state.nc * mask,
        t=state.t + dT * mask,
    )


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
    ncmin_tensor=None,   # per-cell ncmin floor for the conservation NUMBER budgets (#18);
                         # None → scalar c.NCMIN fallback. Built from xland by the driver.
    nccn=None,           # CCN reservoir for activation in apply_satadj_step (Task #74);
                         # None → no activation (returns bare state). Threaded by the driver.
) -> "CoordinatorState | tuple[CoordinatorState, torch.Tensor]":
    """F1 chain을 *single timestep*에 대해 한 번 호출 → new state 반환.

    Order: preamble → warm → cold → melt/freeze → state_update.
    When ``nccn`` is given, apply_satadj_step runs CCN activation and this returns
    ``(new_state, nccn_out)``; otherwise it returns a bare ``CoordinatorState``.
    """
    pre = preamble_torch(state, forcing, sea_mask, params=full_params)

    # ─── Stage-A STEP 2+3: SEQUENTIAL melt → re-slope → freeze → re-slope → warm/cold ──
    # Mirror of C++ kdm62d_one_step. Fortran module_mp_kdm6.F order: D1 melt (:1274-1345) →
    # [homog freeze :1410-1420] → re-slope (:1422-1480) → D2-D4 freeze (:1485-1561) →
    # re-slope (:1596-1683) → warm/cold rate loop (:1818). We mirror it stage-by-stage:
    #   1. D1 melt from the ENTRY state (warm cells); apply inline → working1.
    #   2. rebuild_aux_torch(working1) → pre1/aux1 (post-melt re-slope).
    #   3. D2-D4 freeze from working1 + pre1/aux1 (cold cells); apply inline → working.
    #   4. rebuild_aux_torch(working) → pre2/aux2 (post-freeze re-slope).
    #   5. warm/cold/D5 read `working` + pre2/aux2.
    # STEP 3 (this split) is bit-identical to the prior STEP-2 single-apply modulo
    # float reassociation (melt warm / freeze cold are per-cell mutually exclusive,
    # so D2-D4-on-post-melt ≡ D2-D4-on-entry). Hosts the (disabled) homog freeze
    # between melt and the freeze re-slope (Stage H2).
    # 1. D1 melt → working1.
    mf_d1 = melt_freeze_d1_torch(
        state, forcing, pre, aux.n0so, aux.n0go, params=mf_params, dtcld=dtcld)
    working1 = apply_melt_freeze_inline_torch(
        state, mf_d1, pre, dtcld=dtcld, xls=full_params.thermo.xls)

    # 1b. Homogeneous freeze (Fortran :1410-1420): supcol>40 ⇒ all qc→qi, between
    # D1 melt and the post-melt re-slope (so the re-slope + D2-D4 see post-homog qc).
    # Now safe (rebuild below re-slopes n0i on the post-homog ice). Mirror of C++.
    working1b = apply_homogeneous_freeze_supercold_torch(working1, full_params.thermo)

    # 2. rebuild on the post-melt+homog state (re-slope; entry thermo spliced).
    pre1, aux1 = rebuild_aux_torch(
        working1b, forcing, sea_mask, params=full_params, qcr_carry=aux.qcr, entry_pre=pre)

    # 3. D2-D4 freeze on the post-melt+homog/re-sloped state → working. (homog zeroed
    # qc in supcol>40 cells, so D2/D3 inactive there — Fortran-exact.)
    mf_d234 = melt_freeze_d2_d4_torch(
        working1b, forcing, pre1,
        aux1.n0c, aux1.n0r, pre1.rslopec, aux1.rslopecmu, aux1.rslopecd,
        params=mf_params, dtcld=dtcld)
    working = apply_melt_freeze_inline_torch(
        working1b, mf_d234, pre, dtcld=dtcld, xls=full_params.thermo.xls)

    # 4. rebuild on the post-freeze state (re-slope; the prior STEP-2 rebuild).
    pre2, aux2 = rebuild_aux_torch(
        working, forcing, sea_mask, params=full_params, qcr_carry=aux.qcr, entry_pre=pre)

    warm_out = warm_phase_torch(
        working, forcing, pre2,
        aux2.n0r, aux2.work1_r, aux2.qcr,
        params=warm_params, dtcld=dtcld,
    )

    cold_out = cold_phase_torch(
        working, forcing, pre2, warm_out.prevp,
        aux2.n0i, aux2.n0r, aux2.n0so, aux2.n0go, aux2.n0c,
        aux2.rslopecmu, aux2.rslopecd,
        aux2.avedia_i, aux2.work1_ice, aux2.work1_water,
        params=cold_params, dtcld=dtcld,
    )

    mf5 = melt_freeze_d5_torch(
        working, forcing, pre2, cold_out,
        aux2.n0so, aux2.n0go, params=mf_params, dtcld=dtcld,
    )

    # F1d2: group conservation limiters bound warm/cold/D5 sinks against the
    # WORKING (post-melt/freeze) reservoirs, gated by post-freeze supcol — exactly
    # Fortran's combined budget+mass-balance loop (:2449-2756, gate `t.le.t0c`).
    # D1-D4 already committed to `working`; scale_rates only touches the D5 fields
    # (pseml/pgeml/nseml/ngeml). Mirrors C++ scale_rates_for_conservation.
    warm_out, cold_out, mf5 = scale_rates_for_conservation_torch(
        working, pre2.supcol, warm_out, cold_out, mf5, dtcld=dtcld,
        # 1:1 fix #18: per-cell ncmin floor for cloud/ice NUMBER budgets. The driver
        # (runtime._kdm6_pure) now builds this from xland + ncmin_land/ncmin_sea (mirroring
        # the C++ WRF path) and threads it here; None → scalar c.NCMIN fallback (no xland).
        # Only the conservation floor takes the per-cell tensor — the warm/cold rate-gate
        # ncmin stays scalar (#10, Python phase params are scalar-typed).
        ncmin_tensor=ncmin_tensor,
    )

    # F1e: state update on the WORKING base. HYBRID pre (Fortran-exact):
    #   xl/cpm = ENTRY (module_mp_kdm6.F:835-836 set once, reused through mass balance),
    #   supcol/rhox = POST-FREEZE (mass-balance arm gates on t.le.t0c :2456; brs
    #   rhox is post re-slope, :2643/2734). delta_src=None ⇒ delta2/delta3 track
    #   working qr/qs (Fortran :2452-2455). mf5 carries D5 only (D1-D4 in working).
    pre_su = pre._replace(
        supcol=pre2.supcol, progb=pre.progb._replace(rhox=pre2.progb.rhox))
    new_state = state_update_torch(
        working, pre_su, warm_out, cold_out, mf5,
        dtcld=dtcld, xls=full_params.thermo.xls, delta_src=None,
    )
    # complete-rain-evap NR → NCCN (Fortran :2937; C++ state_update coordinator.cpp:1170/1254).
    # state_update_torch gives new_state.nr = working.nr + dnr (no rce term — C++ subtracts rce
    # separately); mirror C++ here: nr -= rce, nccn += rce. Gated on nccn so the component-test
    # path (nccn=None) is byte-unchanged; placed before the reclass/satadj, matching C++.
    if nccn is not None:
        rce_amount = working.nr * warm_out.rain_complete_evap.to(working.nr.dtype)
        nccn = nccn + rce_amount
        new_state = new_state._replace(nr=torch.clamp(new_state.nr - rce_amount, min=0.0))
    # review5#4 + review7#1: Picons (Fortran 2807-2813) qi→qs.
    new_state = reclassify_large_ice_to_snow_torch(new_state, forcing.den)
    # review8#3: rain→cloud reclassification (Fortran 2883-2892) when avedia_r ≤ 82μm.
    new_state = reclassify_small_rain_to_cloud_torch(new_state, forcing.den)
    # F1g+: satadj/pcond on the post-update + post-reclass state (Fortran
    # :2922-2943). Mirrors C++ apply_satadj_step; pcond was deferred OUT of
    # state_update_torch so condensation fires on the proper post-mass-balance,
    # post-reclass state (the C++↔Python parity fix Codex flagged).
    _activate = nccn is not None
    sat_result = apply_satadj_step_torch(
        new_state, forcing, pre.xl, pre.cpm,
        warm_params.satadj, full_params.thermo, dtcld=dtcld, nccn=nccn,
    )
    if _activate:
        new_state, nccn = sat_result   # nccn updated by CCN activation — carried out
    else:
        new_state = sat_result
    # review9#1: paired threshold cleanup (Fortran 2951-2970) — *after* reclassifications
    # to catch tiny qs/qc remnants Picons/rain-cloud may have produced.
    new_state = apply_threshold_cleanup_torch(new_state)
    # review9#2: DSD number limiters (Fortran 2972-3013) — lamda 범위를 벗어나면 number 재계산.
    new_state = apply_dsd_number_limiters_torch(new_state, forcing.den)
    return (new_state, nccn) if _activate else new_state


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
    mstep_main: int,           # rain/snow/graupel/brs loop bound (= mstepmax over columns)
    mstep_ice: int,            # ice (qi/ni) loop bound (= mstepmax over columns)
    dtcld: float,
    params: _sed.SubstepAdvectionParams,
    reslope_params: "CoordinatorParams | None" = None,  # 1:1 fix #9: per-substep re-slope
    sea_mask: "torch.Tensor | None" = None,             # (B,K) bool for preamble_torch (qcr only; not vt)
    mstep_col_main: "torch.Tensor | None" = None,       # (B,) per-column mstep (1:1 fix #10);
    mstep_col_ice: "torch.Tensor | None" = None,        # None → scalar mstep_main/mstep_ice (legacy)
) -> SedimentationOutputs:
    """F2b — sedimentation 통합 chain.

    Order:
      1. rain/snow/graupel/brs substepping (mstep_main times)
      2. ice (qi/ni) substepping (mstep_ice times)
      3. surface accumulation (bottom layer)

    1:1 fix #9: when `reslope_params` is given, fall speeds are re-derived from the
    post-substep state INSIDE the loop (Fortran F:1189-1205/1244-1269 ProgB+slope_kdm6
    re-call) and used for the next substep; otherwise the passed-in work1 is reused for
    every substep (identical when mstep==1). sea_mask only feeds preamble's qcr (which
    sedimentation does not use), so any mask gives the same vt.
    """
    K = state.qr.shape[-1]
    dz = torch.clamp(forcing.delz, min=1.0e-9)
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
    # Mutable per-substep work1 (#9): re-derived from the post-substep state when
    # reslope_params is set (Fortran F:1189-1205 after EVERY main substep). w1_qi/wn_qi are
    # ALSO updated by the main re-slope — Fortran's slope_kdm6 writes work1(4)/workn(2) [ice]
    # each main substep and the ice loop below consumes the post-main value (main→ice handoff,
    # F:1194→F:1215). Fortran leaves work1(4)/workn(2) RAW (F:1198-1205 normalizes only
    # 1,2,3/workn1); the port NORMALIZES the ice handoff /delz because the RAW value
    # over-sediments ice and the depletion clamp zeroes ∂/∂qi, breaking the differentiable-port
    # core goal (test_autograd_endtoend). Deliberate AD-required deviation (cf. #6); inert where QICE≈0.
    w1_qr, wn_qr, w1_qs, w1_qg = work1_qr, workn_qr, work1_qs, work1_qg
    w1_qi, wn_qi = work1_qi, workn_qi
    _sm = sea_mask if sea_mask is not None else torch.zeros_like(state.qr, dtype=torch.bool)
    for n in range(1, mstep_main + 1):
        out = _sed.substep_advection_torch(
            adv_state,
            fall_qr, fall_nr, fall_qs, fall_qg, fall_brs,
            w1_qr, wn_qr, w1_qs, w1_qg,
            forcing.delz, forcing.dend,
            mstep=mstep_main, mstep_col=mstep_col_main, n_current=n, dtcld=dtcld, params=params,
        )
        adv_state = out.state
        fall_qr = out.fall_qr
        fall_nr = out.fall_nr
        fall_qs = out.fall_qs
        fall_qg = out.fall_qg
        fall_brs = out.fall_brs
        # Re-slope after EVERY main substep (F:1189-1205, unconditional incl. the last);
        # ORIGINAL qi/ni kept (ice substepped below). rain/snow/graupel work1 feeds the next
        # main substep; the ICE work1 (vt_i/vtn_i) is the handoff the ice loop consumes.
        if reslope_params is not None:
            rs = state._replace(qr=adv_state.qr, nr=adv_state.nr, qs=adv_state.qs,
                                qg=adv_state.qg, brs=adv_state.brs)
            pre = preamble_torch(rs, forcing, _sm, params=reslope_params)
            w1_qr = pre.slope.vt_r / dz   # F:1198-1205 normalizes work1(1,2,3)/workn(1) /delz
            wn_qr = pre.slope.vtn_r / dz
            w1_qs = pre.slope.vt_s / dz
            w1_qg = pre.slope.vt_g / dz
            # main→ice handoff (F:1194 → F:1215). Fortran leaves work1(4)/workn(2) RAW here
            # (F:1198-1205 normalizes only 1,2,3/workn1). The port normalizes /delz: the RAW value
            # over-sediments ice (vt_i·dt≫1 ⇒ qi→0) and the depletion clamp zeroes ∂/∂qi, breaking
            # the differentiable-port core goal (test_autograd_endtoend). DELIBERATE AD-required
            # deviation (cf. #6); inert where QICE≈0. See tracker #9.
            w1_qi = pre.slope.vt_i / dz
            wn_qi = pre.slope.vtn_i / dz

    # ── Ice substepping ──────────────────────────────────────────────
    ice_state = _sed.IceSubstepState(qi=state.qi, ni=state.ni)
    fall_qi = torch.zeros_like(state.qr)
    fall_ni = torch.zeros_like(state.qr)
    # w1_qi/wn_qi carry the main-loop handoff (or the passed-in initial if reslope is off).
    for n in range(1, mstep_ice + 1):
        out_i = _sed.ice_substep_advection_torch(
            ice_state, fall_qi, fall_ni,
            w1_qi, wn_qi, forcing.delz, forcing.dend,
            mstep=mstep_ice, mstep_col=mstep_col_ice, n_current=n, dtcld=dtcld, params=params,
        )
        ice_state = out_i.state
        fall_qi = out_i.fall_qi
        fall_ni = out_i.fall_ni
        # Re-slope ice from the post-substep ice state (F:1244-1269).
        if reslope_params is not None and n < mstep_ice:
            rs = state._replace(qr=adv_state.qr, nr=adv_state.nr, qs=adv_state.qs,
                                qg=adv_state.qg, brs=adv_state.brs,
                                qi=ice_state.qi, ni=ice_state.ni)
            pre = preamble_torch(rs, forcing, _sm, params=reslope_params)
            w1_qi = pre.slope.vt_i / dz
            wn_qi = pre.slope.vtn_i / dz

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
