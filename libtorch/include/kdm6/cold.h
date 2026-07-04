#pragma once
//
// KDM6 cold rain processes — ice phase microphysics.
// 원본: module_mp_kdm6.F: 1818-2444 (Step C 영역)
// Python oracle: kdm6_torch/kdm6/cold.py
//
// Sub-steps (procedures/kdm62d-port-decomposition.md):
//   C1 ice mass accretion         (1837-1863) — ice_accretion_torch
//   C2 ice→snow/graupel mass      (1868-1890) — ice_to_snow_graupel_torch  (TODO)
//   ... (C2b, C2c, C2d, C2e, C3-C6 누적 예정)
//

#include "kdm6/constants.h"
#include <torch/torch.h>

namespace kdm6 {
namespace cold {

// ─── Step C1: Ice mass accretion (praci + piacr) ─────────────────────────────

struct IceAccretionParams {
    double cmi;           // pi * deni / 6
    double cmr;           // pi * denr / 6
    double g1pmr, g2pmr, g3pmr;
    double g1pdimi, g2pdimi, g3pdimi;
    double g1pmi, g2pmi, g3pmi;
    double g1pdrmr, g2pdrmr, g3pdrmr;
    double eacri, eacir;
    double qmin, qcrmin;
};

IceAccretionParams default_ice_accretion_params();

struct IceAccretionOutputs {
    torch::Tensor praci;
    torch::Tensor piacr;
};

struct IceAccretionInputs {
    torch::Tensor qi, qr;
    torch::Tensor den;
    torch::Tensor n0i, n0r;
    torch::Tensor vt2r, vt2i;
    torch::Tensor rslope_r, rslope2_r, rslope3_r, rslopemu_r, rsloped_r;
    torch::Tensor rslope_i, rslope2_i, rslope3_i, rslopemu_i, rsloped_i;
};

IceAccretionOutputs ice_accretion_torch(
    const IceAccretionInputs& inputs,
    const IceAccretionParams& params,
    double dtcld
);

// ─── Step C2: Ice → snow / graupel mass accretion (psaci + pgaci) ────────────

struct IceToSnowGraupelParams {
    double cmi;
    double g1pms, g2pms, g3pms;
    double g1pmg, g2pmg, g3pmg;
    double g1pdimi, g2pdimi, g3pdimi;
    double qmin, qcrmin;
};

IceToSnowGraupelParams default_ice_to_snow_graupel_params();

struct IceToSnowGraupelOutputs {
    torch::Tensor psaci;
    torch::Tensor pgaci;
};

struct IceToSnowGraupelInputs {
    torch::Tensor qi, qs, qg;
    torch::Tensor den;
    torch::Tensor n0i, n0so, n0go, n0sfac;
    torch::Tensor supcol;
    torch::Tensor vt2s, vt2g, vt2i;
    torch::Tensor rslope_s, rslope2_s, rslope3_s, rslopemu_s;
    torch::Tensor rslope_g, rslope2_g, rslope3_g, rslopemu_g;
    torch::Tensor rslope_i, rslope2_i, rslope3_i, rslopemu_i, rsloped_i;
};

IceToSnowGraupelOutputs ice_to_snow_graupel_torch(
    const IceToSnowGraupelInputs& inputs,
    const IceToSnowGraupelParams& params,
    double dtcld
);

// ─── Step C2b: Number accretion (nraci + niacr + nsaci + ngaci) ──────────────

struct NumberAccretionParams {
    double g1pmr, g2pmr, g3pmr;
    double g1pmi, g2pmi, g3pmi;
    double g1pms, g2pms, g3pms;
    double g1pmg, g2pmg, g3pmg;
    double eacri, eacir;
    double n0s_const, n0g_const;
    double ncmin, nrmin, qcrmin;
    // Per-cell ncmin override (operational xland path; see runtime.cpp).
    c10::optional<torch::Tensor> ncmin_tensor;
};

NumberAccretionParams default_number_accretion_params();

struct NumberAccretionOutputs {
    torch::Tensor nraci;
    torch::Tensor niacr;
    torch::Tensor nsaci;
    torch::Tensor ngaci;
};

struct NumberAccretionInputs {
    torch::Tensor qi, qs, qg, qr;
    torch::Tensor ni, nr;
    torch::Tensor den;
    torch::Tensor n0i, n0r;
    torch::Tensor n0sfac;
    torch::Tensor supcol;
    torch::Tensor vt2r, vt2s, vt2g, vt2i;
    torch::Tensor rslope_r, rslope2_r, rslope3_r, rslopemu_r;
    torch::Tensor rslope_s, rslope2_s, rslope3_s, rslopemu_s;
    torch::Tensor rslope_g, rslope2_g, rslope3_g, rslopemu_g;
    torch::Tensor rslope_i, rslope2_i, rslope3_i, rslopemu_i;
};

NumberAccretionOutputs number_accretion_torch(
    const NumberAccretionInputs& inputs,
    const NumberAccretionParams& params,
    double dtcld
);

// ─── Step C2c: Cloud water riming (8 processes) ──────────────────────────────

struct CloudWaterRimingParams {
    double avts, avti;
    double g3pbs, g3pbi;
    double eacsc, eacgc, eacic;
    double muc;
    double di50;
    double qmin, qcrmin, ncmin;
    double qsum_floor;
    // Per-cell ncmin override (operational xland path; see runtime.cpp).
    c10::optional<torch::Tensor> ncmin_tensor;
};

CloudWaterRimingParams default_cloud_water_riming_params();

struct CloudWaterRimingOutputs {
    torch::Tensor psacw, nsacw;
    torch::Tensor pgacw, ngacw;
    torch::Tensor paacw, naacw;
    torch::Tensor piacw, niacw;
};

struct CloudWaterRimingInputs {
    torch::Tensor qc, nc;
    torch::Tensor qs, qg, qi;
    torch::Tensor den, denfac;
    torch::Tensor n0so, n0go, n0i, n0c;
    torch::Tensor n0sfac;
    torch::Tensor avtg, g3pbg;       // ProgB outputs (runtime tensors)
    torch::Tensor avedia_i;
    torch::Tensor supcol;
    torch::Tensor rslope3_s, rslopeb_s, rslopemu_s;
    torch::Tensor rslope3_g, rslopeb_g, rslopemu_g;
    torch::Tensor rslope3_i, rslopeb_i, rslopemu_i;
    torch::Tensor rslopec, rslopecmu;
};

CloudWaterRimingOutputs cloud_water_riming_torch(
    const CloudWaterRimingInputs& inputs,
    const CloudWaterRimingParams& params,
    double dtcld
);

// ─── Step C2d: Rain-snow-graupel collection (6 processes) ────────────────────

struct RainSnowGraupelCollectionParams {
    double cms, cmr;
    double g1pms, g2pms, g3pms;
    double g1pmr, g2pmr, g3pmr;
    double g1pmg, g2pmg, g3pmg;
    double g1pdsms, g2pdsms, g3pdsms;
    double g1pdrmr, g2pdrmr, g3pdrmr;
    double eacrs, eacsr, eacgr;
    double qcrmin, nrmin;
};

RainSnowGraupelCollectionParams default_rain_snow_graupel_collection_params();

struct RainSnowGraupelCollectionOutputs {
    torch::Tensor pracs, nracs;
    torch::Tensor psacr, nsacr;
    torch::Tensor pgacr, ngacr;
};

struct RainSnowGraupelCollectionInputs {
    torch::Tensor qr, qs, qg, nr;
    torch::Tensor den;
    torch::Tensor n0r, n0so, n0go, n0sfac;
    torch::Tensor supcol;
    torch::Tensor vt2r, vt2s, vt2g;
    torch::Tensor rslope_r, rslope2_r, rslope3_r, rslopemu_r, rsloped_r;
    torch::Tensor rslope_s, rslope2_s, rslope3_s, rslopemu_s, rsloped_s;
    torch::Tensor rslope_g, rslope2_g, rslope3_g, rslopemu_g;
};

RainSnowGraupelCollectionOutputs rain_snow_graupel_collection_torch(
    const RainSnowGraupelCollectionInputs& inputs,
    const RainSnowGraupelCollectionParams& params,
    double dtcld
);

// ─── Step C2e: Hallett-Mossop ice multiplication ─────────────────────────────

struct HallettMossopParams {
    double rispl;
    double deni;
    double qs_threshold, qg_threshold, qc_threshold, qr_threshold;
    double t_lo, t_hi, t_mid;
};

HallettMossopParams default_hallett_mossop_params();

struct HallettMossopOutputs {
    torch::Tensor pmulcs, pmulrs, pmulcg, pmulrg;
    torch::Tensor nmulcs, nmulrs, nmulcg, nmulrg;
    torch::Tensor paacw_adj, psacr_adj, pgacr_adj;
};

struct HallettMossopInputs {
    torch::Tensor paacw, psacr, pgacr;
    torch::Tensor qc, qr, qs, qg;
    torch::Tensor t;
    torch::Tensor den;
};

HallettMossopOutputs hallett_mossop_torch(
    const HallettMossopInputs& inputs,
    const HallettMossopParams& params
);

// ─── Step C3: Ice nucleation from vapor ──────────────────────────────────────

struct IceNucleationParams {
    double rinud;
    double deni;
    double cooper_a, cooper_b, cooper_unit;
    double nid_max;
    double supcol_threshold;
    double rh_ice_threshold;
};

IceNucleationParams default_ice_nucleation_params();

struct IceNucleationOutputs {
    torch::Tensor pinud;
    torch::Tensor ninud;
    torch::Tensor ifsat;  // bool tensor
};

struct IceNucleationInputs {
    torch::Tensor supcol;
    torch::Tensor supsat;
    torch::Tensor rh_ice;
    torch::Tensor prevp;
    torch::Tensor nci_ice;
    torch::Tensor den;
};

IceNucleationOutputs ice_nucleation_torch(
    const IceNucleationInputs& inputs,
    const IceNucleationParams& params,
    double dtcld
);

// ─── Step C4: Deposition / Sublimation ──────────────────────────────────────

struct DepSubParams {
    double g2pmi;
    double precs1, precs2;
    double precg1;
    double qcrmin;
};

DepSubParams default_dep_sub_params();

struct DepSubOutputs {
    torch::Tensor pidep;
    torch::Tensor psdep;
    torch::Tensor pgdep;
    torch::Tensor ifsat;
    torch::Tensor ice_complete_sublim;
};

struct DepSubInputs {
    torch::Tensor qi, qs, qg;
    torch::Tensor rh_ice;
    torch::Tensor supcol, supsat;
    torch::Tensor prevp, pinud;
    torch::Tensor ifsat_in;
    torch::Tensor n0i, n0so, n0go, n0sfac;
    torch::Tensor work1_ice, work2;
    torch::Tensor precg2;
    torch::Tensor rslope_s, rslope2_s, rslopeb_s, rslopemu_s;
    torch::Tensor rslope_g, rslope2_g, rslopeb_g, rslopemu_g;
    torch::Tensor rslope2_i, rslopemu_i;
};

DepSubOutputs dep_sub_torch(
    const DepSubInputs& inputs,
    const DepSubParams& params,
    double dtcld
);

// ─── Step C5: Aggregation (psaut + nsaut) ────────────────────────────────────

struct IceAggregationParams {
    double deni;
    double di125;
    double t_split;
    double qcrmin;
};

IceAggregationParams default_ice_aggregation_params();

struct IceAggregationOutputs {
    torch::Tensor psaut;
    torch::Tensor nsaut;
};

IceAggregationOutputs ice_aggregation_torch(
    const torch::Tensor& qi,
    const torch::Tensor& ni,
    const torch::Tensor& t,
    const torch::Tensor& den,
    const torch::Tensor& supcol,
    const IceAggregationParams& params,
    double dtcld
);

// ─── Step C6: Snow evaporation (psevp) ───────────────────────────────────────

struct SnowEvapParams {
    double precs1, precs2;
    double qcrmin;
};

SnowEvapParams default_snow_evap_params();

struct SnowEvapInputs {
    torch::Tensor qs, rh_w, supcol;
    torch::Tensor n0so, n0sfac;
    torch::Tensor work1_water, work2;
    torch::Tensor rslope_s, rslope2_s, rslopeb_s, rslopemu_s;
};

torch::Tensor snow_evap_torch(
    const SnowEvapInputs& inputs,
    const SnowEvapParams& params,
    double dtcld
);

// ─── Step C6': Graupel evaporation (pgevp) — Fortran 2435-2441 ──────────────
//
// Python 측은 codex#4 (Task #53)에서 추가됨. 구조는 snow_evap과 동일하되:
//   (1) n0sfac factor 없음 (graupel은 ice-fraction scaling 미적용)
//   (2) precg2는 ProgB runtime tensor (graupel 밀도 의존)
//   (3) graupel rslope/n0go 사용
// Outer gate: supcol < 0 (warm) AND qg > 0 AND rh_w < 1. pgevp ≤ 0 (evap), capped
// by `-qg/dtcld`.
//
struct GraupelEvapParams {
    double precg1;   // 4 * 0.78 * g2pmg
    double qcrmin;
};

GraupelEvapParams default_graupel_evap_params();

struct GraupelEvapInputs {
    torch::Tensor qg, rh_w, supcol;
    torch::Tensor n0go;
    torch::Tensor work1_water, work2;
    torch::Tensor rslope_g, rslope2_g, rslopeb_g, rslopemu_g;
    torch::Tensor precg2;     // (B, K) ProgB runtime output
};

torch::Tensor graupel_evap_torch(
    const GraupelEvapInputs& inputs,
    const GraupelEvapParams& params,
    double dtcld
);

}  // namespace cold
}  // namespace kdm6
