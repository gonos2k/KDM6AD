#pragma once
//
// KDM6 coordinator types + post-update helpers (C++ libtorch).
// Python kdm6_torch/kdm6/coordinator.py와 1:1 정합. F1e의 post-update 4함수를
// 우선 미러링; preamble/warm/cold/mf chain orchestration은 별도 follow-up.
//
// 본 CoordinatorState는 microphysics-level state (qv, qc, qr, qs, qg, qi, nc,
// nr, ni, brs, t)이다. wrapper-level의 `kdm6::State`(th, nccn 등 포함)와는
// 별개로 두어 Python 측 oracle과의 parity를 직접 맞춘다.
//
#include "kdm6/cloud_dsd.h"
#include "kdm6/cold.h"
#include "kdm6/melt_freeze.h"
#include "kdm6/progb.h"
#include "kdm6/satadj.h"
#include "kdm6/sedimentation.h"
#include "kdm6/slope.h"
#include "kdm6/thermo.h"
#include "kdm6/warm.h"

#include <torch/torch.h>

namespace kdm6 {

struct CoordinatorState {
    torch::Tensor qv;
    torch::Tensor qc;
    torch::Tensor qr;
    torch::Tensor qs;
    torch::Tensor qg;
    torch::Tensor qi;
    torch::Tensor nc;
    torch::Tensor nr;
    torch::Tensor ni;
    torch::Tensor nccn;
    torch::Tensor brs;   // graupel volume mixing ratio
    torch::Tensor t;     // absolute temperature [K]
};

struct CoordinatorForcing {
    torch::Tensor p;     // pressure [Pa]
    torch::Tensor den;   // air density
    torch::Tensor delz;  // layer thickness
    torch::Tensor dend;  // density × delz
};

// Subset of PreambleOutputs that state_update actually consumes. Full preamble
// has many more fields used by warm/cold/mf phases — those are declared
// separately when phase orchestration is ported.
struct PreambleCore {
    torch::Tensor cpm;       // moist heat capacity
    torch::Tensor xl;        // latent heat of vaporization (per cell)
    torch::Tensor supcol;    // T0c - T (positive when cold)
    torch::Tensor rhox;      // graupel density (from ProgB)
};

// Subset of PreambleOutputs that warm_phase consumes. (Picked from Python
// PreambleOutputs: thermo + cloud_dsd + rain-slope subset of slope outputs.)
// Cold/mf phases will need additional struct extensions with their own subsets.
struct PreambleWarm {
    // thermo
    torch::Tensor cpm;
    torch::Tensor xl;
    torch::Tensor qs1;       // saturation w.r.t. water
    torch::Tensor rh_w;
    torch::Tensor supsat;    // (q - qs1)
    torch::Tensor work2;     // venfac
    // cloud DSD
    torch::Tensor rslopec;
    torch::Tensor avedia_c;
    torch::Tensor avedia_r;
    torch::Tensor lenconcr;
    // rain-slope subset (slope_rain outputs)
    torch::Tensor rslope_r;
    torch::Tensor rslopeb_r;
    torch::Tensor rslope2_r;
    torch::Tensor rslope3_r;
    torch::Tensor rslopemu_r;
};

// B1-B5 warm-phase rates.
struct WarmPhaseOutputs {
    torch::Tensor praut;
    torch::Tensor nraut;
    torch::Tensor pracw;
    torch::Tensor nracw;
    torch::Tensor nccol;
    torch::Tensor nrcol;
    torch::Tensor prevp;
    torch::Tensor rain_complete_evap;
    torch::Tensor pcond;
    torch::Tensor cloud_complete_evap;
    torch::Tensor ncact;
    torch::Tensor pcact;
};

// C1-C6' cold-phase rates (post-HM 조정 포함).
struct ColdPhaseOutputs {
    // C1
    torch::Tensor praci;
    torch::Tensor piacr;
    // C2
    torch::Tensor psaci;
    torch::Tensor pgaci;
    // C2b
    torch::Tensor nraci;
    torch::Tensor niacr;
    torch::Tensor nsaci;
    torch::Tensor ngaci;
    // C2c
    torch::Tensor psacw;
    torch::Tensor nsacw;
    torch::Tensor pgacw;
    torch::Tensor ngacw;
    torch::Tensor paacw_adj;   // post-HM
    torch::Tensor naacw;
    torch::Tensor piacw;
    torch::Tensor niacw;
    // C2d
    torch::Tensor pracs;
    torch::Tensor psacr_adj;   // post-HM
    torch::Tensor nsacr;
    torch::Tensor pgacr_adj;   // post-HM
    torch::Tensor ngacr;
    // C2e (mass)
    torch::Tensor pmulcs;
    torch::Tensor pmulrs;
    torch::Tensor pmulcg;
    torch::Tensor pmulrg;
    // C2e (number)
    torch::Tensor nmulcs;
    torch::Tensor nmulrs;
    torch::Tensor nmulcg;
    torch::Tensor nmulrg;
    // C3
    torch::Tensor pinud;
    torch::Tensor ninud;
    // C4
    torch::Tensor pidep;
    torch::Tensor psdep;
    torch::Tensor pgdep;
    torch::Tensor ifsat;
    torch::Tensor ice_complete_sublim;
    // C5
    torch::Tensor psaut;
    torch::Tensor nsaut;
    // C6 / C6'
    torch::Tensor psevp;
    torch::Tensor pgevp;
};

// D1-D5 melt/freeze rates (D2-D4는 amount, D1·D5는 rate; review5#1 단위 정책).
struct MeltFreezePhaseOutputs {
    // D1 (rate)
    torch::Tensor psmlt;
    torch::Tensor pgmlt;
    torch::Tensor pimlt_qi;       // amount (full ice melt)
    torch::Tensor pimlt_ni;       // amount
    torch::Tensor sfac_melt;      // D1 sfac (snow factor; review12#3 added)
    torch::Tensor gfac_melt;      // D1 gfac (graupel factor)
    torch::Tensor delta_brs_melt; // rate (pgmlt/rhox)
    // D2 (amount)
    torch::Tensor pinuc;
    torch::Tensor ninuc;
    // D3 (amount)
    torch::Tensor pfrzdtc;
    torch::Tensor nfrzdtc;
    // D4 (amount)
    torch::Tensor pfrzdtr;
    torch::Tensor nfrzdtr;
    torch::Tensor delta_brs_freeze;  // amount (pfrzdtr/denr)
    // D5 (rate)
    torch::Tensor pseml;
    torch::Tensor nseml;
    torch::Tensor pgeml;
    torch::Tensor ngeml;
};

// Subset of PreambleOutputs that cold_phase consumes. SlopeOutputs (full) is
// embedded as a member to avoid declaring 20+ rslope* tensors individually.
// Per codex review #13 #3: when all phase orchestrations are ported, fold
// PreambleCore/PreambleWarm/PreambleCold into a single PreambleOutputs.
struct PreambleCold {
    // thermo
    torch::Tensor supcol;
    torch::Tensor supsat;
    torch::Tensor rh_w;
    torch::Tensor rh_ice;
    torch::Tensor denfac;
    torch::Tensor work2;
    // cloud DSD
    torch::Tensor rslopec;
    // ProgB subset (cold uses avtg, g3pbg, precg2)
    torch::Tensor avtg;
    torch::Tensor g3pbg;
    torch::Tensor precg2;
    // slope outputs (rslope_r/s/g/i + variants; vt_r/s/g/i; n0sfac)
    slope::SlopeOutputs slope;
};

// ─── Step F1c: cold phase chain (C1-C6') ────────────────────────────────────
//
// Aggregates 10 cold sub-step params into one struct. Caller builds via
// default_cold_phase_params().
//
struct ColdPhaseParams {
    cold::IceAccretionParams ice_accretion;
    cold::IceToSnowGraupelParams ice_to_snow_graupel;
    cold::NumberAccretionParams number_accretion;
    cold::CloudWaterRimingParams cloud_water_riming;
    cold::RainSnowGraupelCollectionParams rsg_collection;
    cold::HallettMossopParams hallett_mossop;
    cold::IceNucleationParams ice_nucleation;
    cold::DepSubParams dep_sub;
    cold::IceAggregationParams ice_aggregation;
    cold::SnowEvapParams snow_evap;
    cold::GraupelEvapParams graupel_evap;
};

ColdPhaseParams default_cold_phase_params();

// Run C1-C6' sequentially, returning the ColdPhaseOutputs aggregate.
// HM (C2e)의 *_adj outputs는 이미 paacw/psacr/pgacr를 post-HM-adjusted 값으로 산출.
ColdPhaseOutputs cold_phase(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const PreambleCold& pre,
    const torch::Tensor& prevp,        // B4 output (passed from warm_phase)
    const torch::Tensor& n0i,
    const torch::Tensor& n0r,
    const torch::Tensor& n0so,
    const torch::Tensor& n0go,
    const torch::Tensor& n0c,
    const torch::Tensor& rslopecmu,
    const torch::Tensor& rslopecd,
    const torch::Tensor& avedia_i,
    const torch::Tensor& work1_ice,    // work1(:,:,2) — ice deposition
    const torch::Tensor& work1_water,  // work1(:,:,1) — water diffusivity (review3#1)
    const ColdPhaseParams& params,
    double dtcld
);

// ─── Step F1b: warm phase chain (B1-B5) ─────────────────────────────────────
//
// Aggregate of B1-B5 sub-params. Caller can build via default_warm_phase_params()
// and override individual fields as needed.
//
struct WarmPhaseParams {
    warm::WarmAutoconvParams autoconv;
    warm::WarmAccretionParams accretion;
    warm::WarmSelfCollectionParams self_coll;
    warm::WarmRainEvapParams rain_evap;
    satadj::SatAdjParams satadj;
};

WarmPhaseParams default_warm_phase_params();

// Run B1-B5 sequentially and return the 8-rate WarmPhaseOutputs.
// No state mutation — caller applies via state_update.
WarmPhaseOutputs warm_phase(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const PreambleWarm& pre,
    const torch::Tensor& n0r,         // (B, K) — caller-supplied
    const torch::Tensor& work1_r,     // (B, K) — caller-supplied (rain capacitance)
    const torch::Tensor& qcr,         // (B, K) — caller-supplied (sea/land DSD threshold)
    const WarmPhaseParams& params,
    double dtcld
);

// Subset of PreambleOutputs that melt_freeze_phase consumes.
struct PreambleMf {
    // thermo
    torch::Tensor supcol;
    torch::Tensor work2;
    // ProgB subset (D1 melting uses rhox, precg2)
    torch::Tensor rhox;
    torch::Tensor precg2;
    // slope outputs (rain/snow/graupel — D1/D4/D5 use these)
    slope::SlopeOutputs slope;
};

// ─── Step F1d: melt/freeze phase chain (D1-D5) ──────────────────────────────
//
// Aggregates 5 mf sub-step params. Caller builds via default_melt_freeze_phase_params().
//
struct MeltFreezePhaseParams {
    melt::MeltingParams melting;
    melt::ContactFreezingParams contact;
    melt::BiggCloudParams bigg_cloud;
    melt::BiggRainParams bigg_rain;
    melt::EnhancedMeltingParams enhanced_melt;
};

MeltFreezePhaseParams default_melt_freeze_phase_params();

// Run D1-D5 sequentially. D5 uses cold_out's post-HM-adjusted paacw/psacr/pgacr.
MeltFreezePhaseOutputs melt_freeze_phase(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const PreambleMf& pre,
    const ColdPhaseOutputs& cold_out,    // paacw_adj, psacr_adj, pgacr_adj
    const torch::Tensor& n0c,
    const torch::Tensor& n0r,
    const torch::Tensor& n0so,
    const torch::Tensor& n0go,
    const torch::Tensor& rslopec,
    const torch::Tensor& rslopecmu,
    const torch::Tensor& rslopecd,
    const MeltFreezePhaseParams& params,
    double dtcld
);

// ─── Step F1a: preamble (thermo + cloud_dsd + ProgB + slope_kdm6) ───────────
//
// Aggregates all sub-module params into one struct. Mirrors Python
// `CoordinatorParams` NamedTuple.
//
struct CoordinatorParams {
    thermo::ThermoParams thermo;
    cloud_dsd::CloudDsdParams cloud_dsd;
    progb::ProgBParams progb;
    slope::SlopeParams slope;
};

CoordinatorParams default_coordinator_params(double den0 = constants::DEN0);

// Full preamble outputs — every diagnostic that downstream phases (warm/cold/mf)
// or state_update may need. Per codex review #13 #3: this is the unified struct
// that PreambleCore/PreambleWarm/PreambleCold/PreambleMf will eventually fold into.
struct PreambleOutputs {
    // Thermodynamics
    torch::Tensor cpm, xl, supcol;
    torch::Tensor qs1, qs2, rh_w, rh_ice, supsat;
    torch::Tensor denfac, work2;
    // Cloud DSD
    torch::Tensor rslopec, avedia_c, avedia_r;
    torch::Tensor sigma_c, lencon, lenconcr;
    // ProgB outputs (full)
    progb::ProgBOutputs progb;
    // Slope outputs (full)
    slope::SlopeOutputs slope;
};

// Run thermo + cloud_dsd + ProgB + slope_kdm6 sequentially.
// `qcr` is computed by caller via `cloud_dsd::diag_qcr_torch(sea_mask, ...)` — preamble
// itself doesn't take sea_mask, matching Python.
PreambleOutputs preamble(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const CoordinatorParams& params
);

// External diagnostics that the F1 chain consumes. In production these are
// supplied by the host (KIM-meso) wrapper; harness/tests build defaults.
// Mirrors Python `CoordinatorAuxDiagnostics`.
struct CoordinatorAuxDiagnostics {
    torch::Tensor n0r;
    torch::Tensor n0i;
    torch::Tensor n0c;
    torch::Tensor n0so;
    torch::Tensor n0go;
    torch::Tensor work1_r;
    torch::Tensor work1_ice;
    torch::Tensor work1_water;     // work1(:,:,1) — psevp/pgevp용 (review3#1)
    torch::Tensor qcr;
    torch::Tensor avedia_i;
    torch::Tensor rslopecmu;
    torch::Tensor rslopecd;
};

// ─── F1 chain wrapper: single-timestep one-shot ──────────────────────────────
//
// Python kdm62d_one_step_torch와 1:1 정합. Order:
//   preamble → warm_phase → cold_phase → melt_freeze_phase → state_update
//     → reclassify_large_ice_to_snow → reclassify_small_rain_to_cloud
//     → apply_threshold_cleanup → apply_dsd_number_limiters
//
CoordinatorState kdm62d_one_step(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const CoordinatorAuxDiagnostics& aux,
    const torch::Tensor& sea_mask,        // unused inside (qcr is in aux); kept for API mirror
    const CoordinatorParams& full_params,
    const WarmPhaseParams& warm_params,
    const ColdPhaseParams& cold_params,
    const MeltFreezePhaseParams& mf_params,
    double dtcld
);

// Fortran kdm62D entry: loops_max = max(nint(delt/dtcldcr + 0.5), 1).
// Integer arithmetic — non-differentiable (caller decides delt).
int compute_loops_max(double delt, double dtcldcr = constants::DTCLDCR);

// ─── F2 sub-cycling wrapper ─────────────────────────────────────────────────
//
// Outer timestep `delt`를 `dtcldcr` 단위로 분할해 loops_max 회 sequential하게
// kdm62d_one_step 호출. state는 매 sub-cycle마다 갱신.
// Note: sedimentation은 본 함수 *밖*. (Python과 동일.)
//
CoordinatorState kdm62d_step(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const CoordinatorAuxDiagnostics& aux,
    const torch::Tensor& sea_mask,
    const CoordinatorParams& full_params,
    const WarmPhaseParams& warm_params,
    const ColdPhaseParams& cold_params,
    const MeltFreezePhaseParams& mf_params,
    double delt,
    double dtcldcr = constants::DTCLDCR
);

// ─── Step F1e: state mutation update (Fortran 2680-2823 직역) ────────────────
//
// Python state_update_torch와 1:1 정합. Mass + number + energy + brs 통합 갱신
// + nonneg clamp. Threshold cleanup은 *별도* (apply_threshold_cleanup 사용).
// review3-10의 모든 수정 반영:
//   - delta2/delta3 routing (qr<1e-4 / qr&qs<1e-4 분기)
//   - paacw_adj (post-HM) 사용; psacw/pgacw 개별 sink 제거
//   - dT 3-group split: warm (xl), deposition (xls), freeze/melt (xlf)
//   - dbrs: cold-branch riming 8개 + warm-branch pgevp/pgeml
//   - amount/rate 단위 분리 (D2-D4 + pimlt_qi + delta_brs_freeze는 amount,
//     dtcld 곱하지 않음)
//
CoordinatorState state_update(
    const CoordinatorState& state,
    const PreambleCore& pre,
    const WarmPhaseOutputs& warm,
    const ColdPhaseOutputs& cold,
    const MeltFreezePhaseOutputs& mf,
    double dtcld,
    double xlf = 3.336e5    // latent heat of fusion (J/kg) — Fortran kdm6init INPUT
);

// ─── Step F1h: paired threshold cleanup (Fortran 3017-3035) ─────────────────
//
// q*<=qmin (qc/qi) 또는 q*<=qcrmin (qr/qs/qg) 셀에서:
//   q* = 0; paired number도 0 (qc/qr/qi pair만)
// AD-friendly multiplicative mask (subgradient at boundary 0).
//
CoordinatorState apply_threshold_cleanup(
    const CoordinatorState& state,
    double qmin = 1.0e-15,
    double qcrmin = 1.0e-9
);

// ─── Step F1f: Picons reclassification (Fortran 2876-2882, Park-Lim 2023) ───
//
// 평균 ice 직경 ≥ 200μm → qi → qs로 재분류 (T<0°C, qi>qmin).
// avedia_i를 post-update qi/ni/den으로 inline 재진단 (review6#1/review7#1).
// ice_active mask + LAMDAIMAX/MIN clamp (review8#1).
//
CoordinatorState reclassify_large_ice_to_snow(
    const CoordinatorState& state,
    const torch::Tensor& den,
    double qmin = 1.0e-15,
    double di_threshold = 200.0e-6,
    double t0c = 273.15
);

// ─── Step F1g: rain→cloud reclassification (Fortran 2952-2964) ──────────────
//
// 평균 빗방울 직경 ≤ 82μm → qr → qc 회수 (drizzle-sized).
// avedia_r post-update qr/nr/den + LAMDARMAX/MIN clamp.
//
CoordinatorState reclassify_small_rain_to_cloud(
    const CoordinatorState& state,
    const torch::Tensor& den,
    double qcrmin = 1.0e-9,
    double di_threshold = 82.0e-6
);

// ─── Step F1i: DSD number limiters (Fortran 3039-3082) ──────────────────────
//
// (q, n) 쌍에 대해 lamda = (pidn·n / (q·den))^(1/dm). lamda가 [lamda_min,
// lamda_max] 밖이면 boundary로 snap, n = den·q·lamda^dm/pidn 재계산.
// rain (LAMDAR), cloud (LAMDAC, Cohard-Pinty pidnc), ice (LAMDAI). Plus
// absolute caps NRMAX/NCMAX (Fortran 3079-3082).
// nccn clamp는 nccn 부재로 미적용.
//
CoordinatorState apply_dsd_number_limiters(
    const CoordinatorState& state,
    const torch::Tensor& den,
    double qmin = 1.0e-15,
    double qcrmin = 1.0e-9
);

// ─── F2b: sedimentation chain (NISLFV-PLM) ──────────────────────────────────
//
// Mirrors Python `sedimentation_chain_torch`:
//   1. rain/snow/graupel/brs substepping (mstep_main times)
//   2. ice (qi, ni) substepping (mstep_ice times)
//   3. surface accumulation (bottom layer)
//
// Note: `work1_qr/qs/qg/qi`는 caller 측에서 이미 `work / delz` (E1 normalize) 적용된
// 텐서. ProgB/slope re-call (Fortran 1218-1234)은 *substep 내부에서* work1을 재진단
// 하지만, 본 oracle/wrapper는 시간 불변 work1 가정 (Python과 동일).
//
struct SedimentationOutputs {
    CoordinatorState state;
    torch::Tensor rain_increment;     // (B,) [mm]
    torch::Tensor snow_increment;
    torch::Tensor graupel_increment;
};

SedimentationOutputs sedimentation_chain(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const torch::Tensor& work1_qr,
    const torch::Tensor& workn_qr,
    const torch::Tensor& work1_qs,
    const torch::Tensor& work1_qg,
    const torch::Tensor& work1_qi,
    const torch::Tensor& workn_qi,
    int mstep_main,
    int mstep_ice,
    double dtcld,
    const sed::SubstepAdvectionParams& params
);

}  // namespace kdm6
