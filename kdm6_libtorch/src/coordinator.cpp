// KDM6 coordinator post-update helpers (C++ libtorch port).
// Python kdm6_torch/kdm6/coordinator.py F1e post-update 함수 1:1 미러링.
//
// review #1~#10 권고 모두 반영. AD-friendly: in-place 없음, .item() 없음, mask는
// torch::where + multiplicative mask (subgradient at boundary 0).
//
#include "kdm6/coordinator.h"
#include "kdm6/constants.h"

#include <cmath>

namespace kdm6 {

namespace {

constexpr double PI = 3.14159265358979323846;

// Fortran rgmma(x) = exp(GAMMLN(x)) = Γ(x). review6 audit fix (1/Γ 아님).
inline double rgmma_scalar(double x) {
    return std::exp(std::lgamma(x));
}

}  // namespace

// ─── F1c: cold phase chain (C1-C6') ─────────────────────────────────────────

ColdPhaseParams default_cold_phase_params() {
    return ColdPhaseParams{
        cold::default_ice_accretion_params(),
        cold::default_ice_to_snow_graupel_params(),
        cold::default_number_accretion_params(),
        cold::default_cloud_water_riming_params(),
        cold::default_rain_snow_graupel_collection_params(),
        cold::default_hallett_mossop_params(),
        cold::default_ice_nucleation_params(),
        cold::default_dep_sub_params(),
        cold::default_ice_aggregation_params(),
        cold::default_snow_evap_params(),
        cold::default_graupel_evap_params(),
    };
}

ColdPhaseOutputs cold_phase(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const PreambleCold& pre,
    const torch::Tensor& prevp,
    const torch::Tensor& n0i,
    const torch::Tensor& n0r,
    const torch::Tensor& n0so,
    const torch::Tensor& n0go,
    const torch::Tensor& n0c,
    const torch::Tensor& rslopecmu,
    const torch::Tensor& rslopecd,
    const torch::Tensor& avedia_i,
    const torch::Tensor& work1_ice,
    const torch::Tensor& work1_water,
    const ColdPhaseParams& params,
    double dtcld
) {
    (void)rslopecd;  // reserved for D3 Bigg cloud (used in melt_freeze, not cold)

    auto rslopec3 = pre.rslopec * pre.rslopec * pre.rslopec;
    const auto& s = pre.slope;

    // C1: ice accretion
    cold::IceAccretionInputs c1_in{
        state.qi, state.qr,
        forcing.den, n0i, n0r,
        s.vt_r, s.vt_i,
        s.rslope_r, s.rslope2_r, s.rslope3_r, s.rslopemu_r, s.rsloped_r,
        s.rslope_i, s.rslope2_i, s.rslope3_i, s.rslopemu_i, s.rsloped_i,
    };
    auto c1 = cold::ice_accretion_torch(c1_in, params.ice_accretion, dtcld);

    // C2: ice → snow/graupel
    cold::IceToSnowGraupelInputs c2_in{
        state.qi, state.qs, state.qg,
        forcing.den,
        n0i, n0so, n0go, s.n0sfac_field,
        pre.supcol,
        s.vt_s, s.vt_g, s.vt_i,
        s.rslope_s, s.rslope2_s, s.rslope3_s, s.rslopemu_s,
        s.rslope_g, s.rslope2_g, s.rslope3_g, s.rslopemu_g,
        s.rslope_i, s.rslope2_i, s.rslope3_i, s.rslopemu_i, s.rsloped_i,
    };
    auto c2 = cold::ice_to_snow_graupel_torch(c2_in, params.ice_to_snow_graupel, dtcld);

    // C2b: number accretion
    cold::NumberAccretionInputs c2b_in{
        state.qi, state.qs, state.qg, state.qr,
        state.ni, state.nr,
        forcing.den,
        n0i, n0r, s.n0sfac_field,
        pre.supcol,
        s.vt_r, s.vt_s, s.vt_g, s.vt_i,
        s.rslope_r, s.rslope2_r, s.rslope3_r, s.rslopemu_r,
        s.rslope_s, s.rslope2_s, s.rslope3_s, s.rslopemu_s,
        s.rslope_g, s.rslope2_g, s.rslope3_g, s.rslopemu_g,
        s.rslope_i, s.rslope2_i, s.rslope3_i, s.rslopemu_i,
    };
    auto c2b = cold::number_accretion_torch(c2b_in, params.number_accretion, dtcld);

    // C2c: cloud water riming
    cold::CloudWaterRimingInputs c2c_in{
        state.qc, state.nc, state.qs, state.qg, state.qi,
        forcing.den, pre.denfac,
        n0so, n0go, n0i, n0c, s.n0sfac_field,
        pre.avtg, pre.g3pbg,
        avedia_i, pre.supcol,
        s.rslope3_s, s.rslopeb_s, s.rslopemu_s,
        s.rslope3_g, s.rslopeb_g, s.rslopemu_g,
        s.rslope3_i, s.rslopeb_i, s.rslopemu_i,
        pre.rslopec, rslopecmu,
    };
    auto cwr = cold::cloud_water_riming_torch(c2c_in, params.cloud_water_riming, dtcld);

    // C2d: rain-snow-graupel collection
    cold::RainSnowGraupelCollectionInputs c2d_in{
        state.qr, state.qs, state.qg, state.nr,
        forcing.den,
        n0r, n0so, n0go, s.n0sfac_field,
        pre.supcol,
        s.vt_r, s.vt_s, s.vt_g,
        s.rslope_r, s.rslope2_r, s.rslope3_r, s.rslopemu_r, s.rsloped_r,
        s.rslope_s, s.rslope2_s, s.rslope3_s, s.rslopemu_s, s.rsloped_s,
        s.rslope_g, s.rslope2_g, s.rslope3_g, s.rslopemu_g,
    };
    auto rsgc = cold::rain_snow_graupel_collection_torch(c2d_in, params.rsg_collection, dtcld);

    // C2e: Hallett-Mossop multiplication
    cold::HallettMossopInputs c2e_in{
        cwr.paacw, rsgc.psacr, rsgc.pgacr,
        state.qc, state.qr, state.qs, state.qg,
        state.t, forcing.den,
    };
    auto hm = cold::hallett_mossop_torch(c2e_in, params.hallett_mossop);

    // C3: ice nucleation
    cold::IceNucleationInputs c3_in{
        pre.supcol, pre.supsat, pre.rh_ice, prevp,
        state.ni, forcing.den,
    };
    auto icenuc = cold::ice_nucleation_torch(c3_in, params.ice_nucleation, dtcld);

    // C4: deposition/sublimation
    cold::DepSubInputs c4_in{
        state.qi, state.qs, state.qg,
        pre.rh_ice, pre.supcol, pre.supsat,
        prevp, icenuc.pinud, icenuc.ifsat,
        n0i, n0so, n0go, s.n0sfac_field,
        work1_ice, pre.work2,
        pre.precg2,
        s.rslope_s, s.rslope2_s, s.rslopeb_s, s.rslopemu_s,
        s.rslope_g, s.rslope2_g, s.rslopeb_g, s.rslopemu_g,
        s.rslope2_i, s.rslopemu_i,
    };
    auto depsub = cold::dep_sub_torch(c4_in, params.dep_sub, dtcld);

    // C5: ice aggregation (no Inputs struct — takes tensors directly)
    auto agg = cold::ice_aggregation_torch(
        state.qi, state.ni, state.t, forcing.den, pre.supcol,
        params.ice_aggregation, dtcld
    );

    // C6: snow evap (warm-only; review3#1 uses work1_water)
    cold::SnowEvapInputs c6_in{
        state.qs, pre.rh_w, pre.supcol,
        n0so, s.n0sfac_field, work1_water, pre.work2,
        s.rslope_s, s.rslope2_s, s.rslopeb_s, s.rslopemu_s,
    };
    auto psevp = cold::snow_evap_torch(c6_in, params.snow_evap, dtcld);

    // C6': graupel evap (warm-only; codex#4 + review3#1)
    cold::GraupelEvapInputs c6p_in{
        state.qg, pre.rh_w, pre.supcol,
        n0go, work1_water, pre.work2,
        s.rslope_g, s.rslope2_g, s.rslopeb_g, s.rslopemu_g,
        pre.precg2,
    };
    auto pgevp = cold::graupel_evap_torch(c6p_in, params.graupel_evap, dtcld);

    return ColdPhaseOutputs{
        /*praci=*/c1.praci, /*piacr=*/c1.piacr,
        /*psaci=*/c2.psaci, /*pgaci=*/c2.pgaci,
        /*nraci=*/c2b.nraci, /*niacr=*/c2b.niacr, /*nsaci=*/c2b.nsaci, /*ngaci=*/c2b.ngaci,
        /*psacw=*/cwr.psacw, /*nsacw=*/cwr.nsacw,
        /*pgacw=*/cwr.pgacw, /*ngacw=*/cwr.ngacw,
        /*paacw_adj=*/hm.paacw_adj, /*naacw=*/cwr.naacw,
        /*piacw=*/cwr.piacw, /*niacw=*/cwr.niacw,
        /*pracs=*/rsgc.pracs, /*psacr_adj=*/hm.psacr_adj, /*nsacr=*/rsgc.nsacr,
        /*pgacr_adj=*/hm.pgacr_adj, /*ngacr=*/rsgc.ngacr,
        /*pmulcs=*/hm.pmulcs, /*pmulrs=*/hm.pmulrs, /*pmulcg=*/hm.pmulcg, /*pmulrg=*/hm.pmulrg,
        /*nmulcs=*/hm.nmulcs, /*nmulrs=*/hm.nmulrs, /*nmulcg=*/hm.nmulcg, /*nmulrg=*/hm.nmulrg,
        /*pinud=*/icenuc.pinud, /*ninud=*/icenuc.ninud,
        /*pidep=*/depsub.pidep, /*psdep=*/depsub.psdep, /*pgdep=*/depsub.pgdep,
        /*ifsat=*/depsub.ifsat,
        /*ice_complete_sublim=*/depsub.ice_complete_sublim,
        /*psaut=*/agg.psaut, /*nsaut=*/agg.nsaut,
        /*psevp=*/psevp,
        /*pgevp=*/pgevp,
    };
}

// ─── F1b: warm phase chain (B1-B5) ──────────────────────────────────────────

WarmPhaseParams default_warm_phase_params() {
    return WarmPhaseParams{
        warm::default_warm_autoconv_params(),
        warm::default_warm_accretion_params(),
        warm::default_warm_self_collection_params(),
        warm::default_warm_rain_evap_params(),
        satadj::default_satadj_params(),
    };
}

WarmPhaseOutputs warm_phase(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const PreambleWarm& pre,
    const torch::Tensor& n0r,
    const torch::Tensor& work1_r,
    const torch::Tensor& qcr,
    const WarmPhaseParams& params,
    double dtcld
) {
    // rslopec3 = rslopec^3 (derived helper, matches Python pre.rslopec * pre.rslopec * pre.rslopec)
    auto rslopec3 = pre.rslopec * pre.rslopec * pre.rslopec;

    // B1: Autoconversion (qc → qr mass+number)
    auto b1 = warm::autoconv_torch(
        state.qc, state.nc, state.qr, state.nr, forcing.den,
        qcr, pre.lenconcr, params.autoconv, dtcld
    );

    // B2: Accretion (qc ← rain mass+number)
    auto b2 = warm::accretion_torch(
        state.qc, state.nc, state.qr, state.nr, forcing.den,
        pre.avedia_r, rslopec3, pre.rslope3_r, pre.lenconcr,
        params.accretion, dtcld
    );

    // B3: Self-collection (cloud + rain + breakup)
    auto b3 = warm::self_collection_torch(
        state.nc, state.nr, state.qr,
        pre.avedia_c, pre.avedia_r, rslopec3, pre.rslope3_r, pre.lenconcr,
        params.self_coll
    );

    // B4: Rain evaporation/condensation
    auto rain_evap = warm::rain_evap_torch(
        state.qr, pre.rh_w, pre.supsat,
        n0r, work1_r, pre.work2,
        pre.rslope_r, pre.rslopeb_r, pre.rslope2_r, pre.rslopemu_r,
        params.rain_evap, dtcld
    );

    // B5: Saturation adjustment (qv ↔ qc)
    auto satadj = satadj::saturation_adjustment_torch(
        state.t, state.qv, state.qc, pre.qs1, pre.xl, pre.cpm,
        params.satadj, dtcld
    );

    auto sw_ratio = torch::clamp(pre.supsat / 0.48, /*min=*/0.0);
    auto activated_fraction = torch::minimum(
        torch::ones_like(sw_ratio),
        torch::pow(sw_ratio, constants::ACTK)
    );
    auto ncact_raw = torch::clamp((state.nccn + state.nc) * activated_fraction - state.nc, /*min=*/0.0) / dtcld;
    auto ncact = torch::minimum(ncact_raw, torch::clamp(state.nccn, /*min=*/0.0) / dtcld);
    ncact = torch::where(pre.supsat > 0.0, ncact, torch::zeros_like(ncact));
    auto pcact_raw = 4.0 * PI * constants::DENR * std::pow(constants::ACTR * 1.0e-6, 3.0) * ncact / (3.0 * forcing.den);
    auto pcact = torch::minimum(pcact_raw, torch::clamp(state.qv, /*min=*/0.0) / dtcld);

    return WarmPhaseOutputs{
        /*praut=*/b1.praut,  /*nraut=*/b1.nraut,
        /*pracw=*/b2.pracw,  /*nracw=*/b2.nracw,
        /*nccol=*/b3.nccol,  /*nrcol=*/b3.nrcol,
        /*prevp=*/rain_evap.prevp,
        /*rain_complete_evap=*/rain_evap.rain_complete_evap,
        /*pcond=*/satadj.pcond,
        /*cloud_complete_evap=*/satadj.cloud_complete_evap,
        /*ncact=*/ncact,
        /*pcact=*/pcact,
    };
}

// ─── F1a: preamble (thermo + cloud_dsd + ProgB + slope_kdm6) ────────────────

CoordinatorParams default_coordinator_params(double den0) {
    return CoordinatorParams{
        thermo::default_thermo_params(),
        cloud_dsd::default_cloud_dsd_params(den0),
        progb::default_progb_params(),
        slope::default_slope_params(),
    };
}

PreambleOutputs preamble(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const CoordinatorParams& params
) {
    // ── Thermodynamics (10 helpers) ─────────────────────────────────────────
    auto cpm = thermo::compute_cpm(state.qv, params.thermo);
    auto xl = thermo::compute_xl(state.t, params.thermo);
    auto supcol = thermo::compute_supcol(state.t, params.thermo);
    auto qs1 = thermo::compute_qs_water(state.t, forcing.p, params.thermo);
    auto qs2 = thermo::compute_qs_ice(state.t, forcing.p, params.thermo);
    auto rh_w = thermo::compute_rh(state.qv, qs1, params.thermo);
    auto rh_ice = thermo::compute_rh(state.qv, qs2, params.thermo);
    auto supsat = thermo::compute_supsat(state.qv, qs1, params.thermo);
    auto denfac = thermo::compute_denfac(forcing.den, params.thermo);
    auto work2 = thermo::compute_work2_venfac(forcing.p, state.t, forcing.den, params.thermo);

    // ── Cloud DSD ───────────────────────────────────────────────────────────
    auto rslopec = cloud_dsd::diag_cloud_slope_torch(
        state.qc, state.nc, forcing.den, params.cloud_dsd
    );
    auto avedia_c = cloud_dsd::diag_avedia_cloud_torch(rslopec, params.cloud_dsd);
    auto sigma_c = cloud_dsd::diag_sigma_cloud_torch(rslopec, params.cloud_dsd);
    auto lencon_out = cloud_dsd::diag_lencon_torch(state.qc, forcing.den, avedia_c, sigma_c);

    // ── ProgB (graupel density 진단) ────────────────────────────────────────
    auto progb_out = progb::progb_param_torch(state.qg, state.brs, params.progb);

    // ── Slope (4-species) ───────────────────────────────────────────────────
    slope::SlopeKdm6Inputs slope_in{
        state.qr, state.qs, state.qg, state.qi,
        state.nr, state.ni,
        forcing.den, denfac, state.t,
        progb_out.pidn0g, progb_out.pvtg, progb_out.bvtg, progb_out.rslopegbmax,
    };
    auto slope_out = slope::slope_kdm6_torch(slope_in, params.slope);

    // avedia_r uses rslope_r from slope module
    auto avedia_r = cloud_dsd::diag_avedia_rain_torch(slope_out.rslope_r, params.cloud_dsd);

    return PreambleOutputs{
        /*cpm=*/cpm, /*xl=*/xl, /*supcol=*/supcol,
        /*qs1=*/qs1, /*qs2=*/qs2, /*rh_w=*/rh_w, /*rh_ice=*/rh_ice, /*supsat=*/supsat,
        /*denfac=*/denfac, /*work2=*/work2,
        /*rslopec=*/rslopec, /*avedia_c=*/avedia_c, /*avedia_r=*/avedia_r,
        /*sigma_c=*/sigma_c,
        /*lencon=*/lencon_out.lencon, /*lenconcr=*/lencon_out.lenconcr,
        /*progb=*/progb_out, /*slope=*/slope_out,
    };
}

// ─── F1 chain wrapper: single-timestep one-shot ─────────────────────────────

namespace {

// Pull thermo + cloud_dsd + rain-slope subset out of full PreambleOutputs for warm_phase.
PreambleWarm pre_warm_view(const PreambleOutputs& pre) {
    return PreambleWarm{
        pre.cpm, pre.xl, pre.qs1, pre.rh_w, pre.supsat, pre.work2,
        pre.rslopec, pre.avedia_c, pre.avedia_r, pre.lenconcr,
        pre.slope.rslope_r, pre.slope.rslopeb_r,
        pre.slope.rslope2_r, pre.slope.rslope3_r, pre.slope.rslopemu_r,
    };
}

PreambleCold pre_cold_view(const PreambleOutputs& pre) {
    return PreambleCold{
        pre.supcol, pre.supsat, pre.rh_w, pre.rh_ice,
        pre.denfac, pre.work2,
        pre.rslopec,
        pre.progb.avtg, pre.progb.g3pbg, pre.progb.precg2,
        pre.slope,
    };
}

PreambleMf pre_mf_view(const PreambleOutputs& pre) {
    return PreambleMf{
        pre.supcol, pre.work2,
        pre.progb.rhox, pre.progb.precg2,
        pre.slope,
    };
}

PreambleCore pre_core_view(const PreambleOutputs& pre) {
    return PreambleCore{
        pre.cpm, pre.xl, pre.supcol, pre.progb.rhox,
    };
}

}  // namespace

CoordinatorState kdm62d_one_step(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const CoordinatorAuxDiagnostics& aux,
    const torch::Tensor& /*sea_mask*/,    // qcr is supplied via aux; sea_mask kept for API mirror
    const CoordinatorParams& full_params,
    const WarmPhaseParams& warm_params,
    const ColdPhaseParams& cold_params,
    const MeltFreezePhaseParams& mf_params,
    double dtcld
) {
    // F1a: preamble (full diagnostics).
    auto pre = preamble(state, forcing, full_params);

    // F1b: warm phase (B1-B5).
    auto warm_out = warm_phase(
        state, forcing, pre_warm_view(pre),
        aux.n0r, aux.work1_r, aux.qcr,
        warm_params, dtcld
    );

    // F1c: cold phase (C1-C6'). Takes warm_out.prevp for C3/C4 ifsat budgeting.
    auto cold_out = cold_phase(
        state, forcing, pre_cold_view(pre),
        warm_out.prevp,
        aux.n0i, aux.n0r, aux.n0so, aux.n0go, aux.n0c,
        aux.rslopecmu, aux.rslopecd,
        aux.avedia_i, aux.work1_ice, aux.work1_water,
        cold_params, dtcld
    );

    // F1d: melt/freeze phase (D1-D5). D5 uses cold_out's post-HM-adjusted values.
    auto mf_out = melt_freeze_phase(
        state, forcing, pre_mf_view(pre), cold_out,
        aux.n0c, aux.n0r, aux.n0so, aux.n0go,
        pre.rslopec, aux.rslopecmu, aux.rslopecd,
        mf_params, dtcld
    );

    // F1e: state update (mass + number + energy + brs + nonneg clamp).
    auto new_state = state_update(
        state, pre_core_view(pre), warm_out, cold_out, mf_out, dtcld
    );

    // F1f: Picons (qi → qs at avedia_i ≥ 200μm).
    new_state = reclassify_large_ice_to_snow(new_state, forcing.den);

    // F1g: rain → cloud (avedia_r ≤ 82μm).
    new_state = reclassify_small_rain_to_cloud(new_state, forcing.den);

    // F1h: paired threshold cleanup (catches reclass-induced remainders).
    new_state = apply_threshold_cleanup(new_state);

    // F1i: DSD number limiters (lamda boundary snap + NRMAX/NCMAX caps).
    return apply_dsd_number_limiters(new_state, forcing.den);
}

// ─── F2: sub-cycling wrapper ────────────────────────────────────────────────

int compute_loops_max(double delt, double dtcldcr) {
    // Fortran: max(nint(delt/dtcldcr + 0.5), 1).
    int n = static_cast<int>(delt / dtcldcr + 0.5);
    return n > 1 ? n : 1;
}

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
    double dtcldcr
) {
    // codex stop-hook fix: delt<=0 → no-op. dtcld=0이면 kdm62d_one_step 내부의
    // mass/dtcld 분할 등이 NaN. 물리적으로도 zero elapsed time → state 불변이 옳음.
    if (delt <= 0.0) {
        return state;
    }

    const int loops_max = compute_loops_max(delt, dtcldcr);
    const double dtcld = delt / static_cast<double>(loops_max);

    CoordinatorState cur = state;
    for (int i = 0; i < loops_max; ++i) {
        cur = kdm62d_one_step(
            cur, forcing, aux, sea_mask,
            full_params, warm_params, cold_params, mf_params,
            dtcld
        );
    }
    return cur;
}

// ─── F1d: melt/freeze phase chain (D1-D5) ───────────────────────────────────

MeltFreezePhaseParams default_melt_freeze_phase_params() {
    return MeltFreezePhaseParams{
        melt::default_melting_params(),
        melt::default_contact_freezing_params(),
        melt::default_bigg_cloud_params(),
        melt::default_bigg_rain_params(),
        melt::default_enhanced_melting_params(),
    };
}

MeltFreezePhaseOutputs melt_freeze_phase(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const PreambleMf& pre,
    const ColdPhaseOutputs& cold_out,
    const torch::Tensor& n0c,
    const torch::Tensor& n0r,
    const torch::Tensor& n0so,
    const torch::Tensor& n0go,
    const torch::Tensor& rslopec,
    const torch::Tensor& rslopecmu,
    const torch::Tensor& rslopecd,
    const MeltFreezePhaseParams& params,
    double dtcld
) {
    const auto& s = pre.slope;

    // D1: melting (warm cells)
    melt::MeltingInputs d1_in{
        state.qs, state.qg, state.qi, state.ni,
        state.t, forcing.p, forcing.den, pre.rhox,
        n0so, n0go, s.n0sfac_field,
        pre.work2,
        pre.precg2,
        s.rslope_s, s.rslope2_s, s.rslopeb_s, s.rslopemu_s,
        s.rslope_g, s.rslope2_g, s.rslopeb_g, s.rslopemu_g,
    };
    auto d1 = melt::melting_torch(d1_in, params.melting, dtcld);

    // D2: contact freezing (Meyers, T < -2°C)
    auto rslopec2 = rslopec * rslopec;
    auto rslopec3 = rslopec2 * rslopec;
    melt::ContactFreezingInputs d2_in{
        state.qc, state.nc,
        state.t, forcing.p, forcing.den,
        n0c,
        rslopec, rslopec2, rslopec3, rslopecmu,
        pre.supcol,
    };
    auto d2 = melt::contact_freezing_torch(d2_in, params.contact, dtcld);

    // D3: Bigg cloud freezing (cold cells)
    melt::BiggCloudInputs d3_in{
        state.qc, state.nc,
        forcing.den,
        n0c,
        rslopec, rslopecd, rslopecmu,
        pre.supcol,
    };
    auto d3 = melt::bigg_cloud_freezing_torch(d3_in, params.bigg_cloud, dtcld);

    // D4: Bigg rain freezing (cold cells)
    melt::BiggRainInputs d4_in{
        state.qr, state.nr,
        forcing.den,
        n0r,
        s.rslope_r, s.rsloped_r, s.rslopemu_r,
        pre.supcol,
    };
    auto d4 = melt::bigg_rain_freezing_torch(d4_in, params.bigg_rain, dtcld);

    // D5: enhanced melting (uses cold_out's post-HM-adjusted values)
    melt::EnhancedMeltingInputs d5_in{
        state.qs, state.qg,
        cold_out.paacw_adj, cold_out.psacr_adj, cold_out.pgacr_adj,
        n0so, n0go, s.n0sfac_field,
        s.rslope_s, s.rslope_g,
        pre.supcol,
    };
    auto d5 = melt::enhanced_melting_torch(d5_in, params.enhanced_melt, dtcld);

    return MeltFreezePhaseOutputs{
        /*psmlt=*/d1.psmlt, /*pgmlt=*/d1.pgmlt,
        /*pimlt_qi=*/d1.pimlt_qi, /*pimlt_ni=*/d1.pimlt_ni,
        /*sfac_melt=*/d1.sfac, /*gfac_melt=*/d1.gfac,
        /*delta_brs_melt=*/d1.delta_brs,
        /*pinuc=*/d2.pinuc, /*ninuc=*/d2.ninuc,
        /*pfrzdtc=*/d3.pfrzdtc, /*nfrzdtc=*/d3.nfrzdtc,
        /*pfrzdtr=*/d4.pfrzdtr, /*nfrzdtr=*/d4.nfrzdtr,
        /*delta_brs_freeze=*/d4.delta_brs,
        /*pseml=*/d5.pseml, /*nseml=*/d5.nseml,
        /*pgeml=*/d5.pgeml, /*ngeml=*/d5.ngeml,
    };
}

// ─── F1e: state mutation update (Fortran 2680-2823) ────────────────────────
//
// Python state_update_torch와 1:1 정합. review3-10의 모든 수정 반영.
// AD-friendly: in-place 없음, .item() 없음, mask는 multiplicative.
//
CoordinatorState state_update(
    const CoordinatorState& state,
    const PreambleCore& pre,
    const WarmPhaseOutputs& warm,
    const ColdPhaseOutputs& cold,
    const MeltFreezePhaseOutputs& mf,
    double dtcld,
    double xlf
) {
    auto dtype = state.qc.dtype();
    auto cold_mask = (pre.supcol > 0).to(dtype);
    auto warm_mask = 1.0 - cold_mask;

    // ── Mass balance ────────────────────────────────────────────────────────
    // qv
    auto dqv = dtcld * (
        - warm.pcact
        - warm.pcond
        - warm.prevp
        - cold.pinud
        - cold.pidep - cold.psdep - cold.pgdep
        - cold.psevp
        - cold.pgevp
    );
    auto qv_new = state.qv + dqv;

    // qc — 2680-2682 (rate) + inline amounts (1556/1586/1391/3011)
    auto dqc_rate = dtcld * (
        warm.pcact
        + warm.pcond
        - warm.praut - warm.pracw
        - cold.piacw
        - 2.0 * cold.paacw_adj
        - cold.pmulcs - cold.pmulcg
    );
    auto dqc_amount = -mf.pinuc - mf.pfrzdtc + mf.pimlt_qi;
    auto qc_new = state.qc + dqc_rate + dqc_amount;

    // qr — 2685-2687 (rate) + inline 1612 amount + D1/D5 melt
    auto dqr_rate = dtcld * (
        warm.praut + warm.pracw
        + warm.prevp
        - cold.piacr - cold.pgacr_adj - cold.psacr_adj
        - cold.pmulrs - cold.pmulrg
        - (mf.psmlt + mf.pgmlt) * warm_mask
        - mf.pseml - mf.pgeml
    );
    auto dqr_amount = -mf.pfrzdtr;
    auto qr_new = state.qr + dqr_rate + dqr_amount;

    // delta2/delta3 routing flags (Fortran 2516-2519)
    auto delta2 = ((state.qr < 1.0e-4) & (state.qs < 1.0e-4)).to(dtype);
    auto delta3 = (state.qr < 1.0e-4).to(dtype);
    auto one_m_d2 = 1.0 - delta2;
    auto one_m_d3 = 1.0 - delta3;

    // qs — 2697-2701 + warm-branch 2811
    auto dqs = dtcld * (
        cold.psdep
        + cold.psaut
        + cold.paacw_adj
        + cold.piacr * delta3
        + cold.praci * delta3
        + cold.psacr_adj * delta2
        + cold.psaci
        - cold.pracs * one_m_d2
        + cold.psevp
        + mf.psmlt
        + mf.pseml
    );
    auto qs_new = state.qs + dqs;

    // qg — 2702-2706 + warm-branch 2814
    auto dqg_rate = dtcld * (
        cold.pgdep
        + cold.paacw_adj
        + cold.pgacr_adj
        + cold.pracs * one_m_d2
        + cold.piacr * one_m_d3
        + cold.praci * one_m_d3
        + cold.psacr_adj * one_m_d2
        + cold.pgaci
        + cold.pgevp
        + mf.pgmlt
        + mf.pgeml
    );
    auto dqg_amount = mf.pfrzdtr;
    auto qg_new = state.qg + dqg_rate + dqg_amount;

    // qi — 2690-2693 + inline 1556/1586/1391
    auto dqi_rate = dtcld * (
        cold.pinud + cold.pidep
        + cold.piacw
        - cold.praci - cold.psaci - cold.pgaci
        - cold.psaut
        + cold.pmulcs + cold.pmulrs
        + cold.pmulcg + cold.pmulrg
    );
    auto dqi_amount = mf.pinuc + mf.pfrzdtc - mf.pimlt_qi;
    auto qi_new = state.qi + dqi_rate + dqi_amount;

    // ── Number balance ──────────────────────────────────────────────────────
    auto dnc_rate = dtcld * (
        - warm.nraut
        - warm.nccol
        - warm.nracw
        - cold.niacw
        - 2.0 * cold.naacw
    );
    auto dnc_amount = -mf.ninuc - mf.nfrzdtc + mf.pimlt_ni;
    auto cloud_complete_evap_amount = state.nc * warm.cloud_complete_evap.to(dtype);
    auto nccn_activation_amount = warm.ncact * dtcld;
    auto nc_new = state.nc + dnc_rate + dnc_amount - cloud_complete_evap_amount + nccn_activation_amount;

    auto dnr_rate = dtcld * (
        warm.nraut
        - warm.nrcol
        - cold.niacr - cold.nraci
        - cold.nsacr - cold.ngacr
    );
    auto dnr_amount = -mf.nfrzdtr;
    auto rain_complete_evap_amount = state.nr * warm.rain_complete_evap.to(dtype);
    auto nr_new = state.nr + dnr_rate + dnr_amount - rain_complete_evap_amount;

    auto dni_rate = dtcld * (
        cold.ninud
        - cold.nraci - cold.nsaci - cold.ngaci
        - cold.niacr
        + cold.nmulcs + cold.nmulcg
        + cold.nmulrs + cold.nmulrg
        - cold.nsaut
    );
    auto dni_amount = mf.ninuc + mf.nfrzdtc - mf.pimlt_ni;
    auto ni_new_pre = state.ni + dni_rate + dni_amount;
    // complete sublimation mask → ni=0
    auto ni_zero_mask = cold.ice_complete_sublim.to(dtype);
    auto ni_new = ni_new_pre * (1.0 - ni_zero_mask);

    // ── brs (graupel volume) — Fortran 2709-2711 + warm-branch 2819 ─────────
    auto rhox_safe = torch::clamp(pre.rhox, /*min=*/constants::DENS);
    auto dbrs_cold_riming = cold_mask * dtcld * (
        cold.pgdep / rhox_safe
        + cold.piacr / constants::DENR        // biacr
        + cold.praci / constants::DENI        // braci
        + cold.psacr_adj / constants::DENR    // bsacr
        + cold.pracs / constants::DENS        // bracs
        + cold.pgaci / constants::DENI        // bgaci
        + cold.paacw_adj / constants::DENR    // baacw
        + cold.pgacr_adj / constants::DENR    // bgacr
    );
    auto dbrs_warm_evap = warm_mask * dtcld * (
        cold.pgevp / rhox_safe
        + mf.pgeml / rhox_safe
    );
    auto dbrs = (
        dtcld * mf.delta_brs_melt
        + mf.delta_brs_freeze
        + dbrs_cold_riming
        + dbrs_warm_evap
    );
    auto brs_new = torch::clamp(state.brs + dbrs, /*min=*/0.0);

    // ── Energy balance (T) — review3#4 / review4#4 / review5#1 ──────────────
    auto cpm_safe = torch::clamp(pre.cpm, /*min=*/constants::QCRMIN);
    auto xls = pre.xl + xlf;

    auto dT_warm_phase = dtcld * pre.xl / cpm_safe * (
        warm.pcact + warm.pcond + warm.prevp + cold.psevp + cold.pgevp
    );
    auto dT_dep_phase = dtcld * xls / cpm_safe * (
        cold.pinud + cold.pidep + cold.psdep + cold.pgdep
    );
    auto dT_freeze_rate = dtcld * xlf / cpm_safe * (
        mf.psmlt + mf.pgmlt
        + mf.pseml + mf.pgeml
        + cold_mask * (
            cold.piacr
            + 2.0 * cold.paacw_adj
            + cold.pmulcs + cold.pmulcg
            + cold.pmulrs + cold.pmulrg
            + cold.piacw
            + cold.pgacr_adj + cold.psacr_adj
        )
    );
    auto dT_freeze_amount = xlf / cpm_safe * (
        mf.pinuc + mf.pfrzdtc + mf.pfrzdtr
        - mf.pimlt_qi
    );
    auto t_new = state.t + dT_warm_phase + dT_dep_phase + dT_freeze_rate + dT_freeze_amount;
    auto nccn_new = state.nccn + rain_complete_evap_amount + cloud_complete_evap_amount - nccn_activation_amount;

    // review5#2 (partial): nonneg clamp. paired threshold cleanup은 분리.
    return CoordinatorState{
        torch::clamp(qv_new, /*min=*/0.0),
        torch::clamp(qc_new, /*min=*/0.0),
        torch::clamp(qr_new, /*min=*/0.0),
        torch::clamp(qs_new, /*min=*/0.0),
        torch::clamp(qg_new, /*min=*/0.0),
        torch::clamp(qi_new, /*min=*/0.0),
        torch::clamp(nc_new, /*min=*/0.0),
        torch::clamp(nr_new, /*min=*/0.0),
        torch::clamp(ni_new, /*min=*/0.0),
        torch::clamp(nccn_new, /*min=*/1.0e8, /*max=*/2.0e10),
        brs_new,
        t_new,
    };
}

// ─── F1h: paired threshold cleanup ──────────────────────────────────────────
CoordinatorState apply_threshold_cleanup(
    const CoordinatorState& state,
    double qmin,
    double qcrmin
) {
    auto dtype = state.qc.dtype();
    auto keep_qc = (state.qc > qmin).to(dtype);
    auto keep_qi = (state.qi > qmin).to(dtype);
    auto keep_qr = (state.qr > qcrmin).to(dtype);
    auto keep_qs = (state.qs > qcrmin).to(dtype);
    auto keep_qg = (state.qg > qcrmin).to(dtype);
    return CoordinatorState{
        /*qv=*/state.qv,
        /*qc=*/state.qc * keep_qc,
        /*qr=*/state.qr * keep_qr,
        /*qs=*/state.qs * keep_qs,
        /*qg=*/state.qg * keep_qg,
        /*qi=*/state.qi * keep_qi,
        /*nc=*/state.nc * keep_qc,
        /*nr=*/state.nr * keep_qr,
        /*ni=*/state.ni * keep_qi,
        /*nccn=*/state.nccn,
        /*brs=*/state.brs,
        /*t=*/state.t,
    };
}

// ─── F1f: Picons reclassification (qi → qs at avedia_i ≥ 200μm) ────────────
CoordinatorState reclassify_large_ice_to_snow(
    const CoordinatorState& state,
    const torch::Tensor& den,
    double qmin,
    double di_threshold,
    double t0c
) {
    // avedia_i = rslope_i · (Γ(4+MUI)/Γ(1+MUI))^(1/3)
    //   rslope_i = 1/lamdai, clamped to [1/LAMDAIMAX, 1/LAMDAIMIN]
    //   lamdai = (pidni · ni / (qi·den))^(1/DMI)
    //   pidni = cmi · Γ(1+DMI+MUI) / Γ(1+MUI),  cmi = π·DENI/6
    const double cmi = PI * constants::DENI / 6.0;
    const double g1pmi = rgmma_scalar(1.0 + constants::MUI);
    const double g1pdimi = rgmma_scalar(1.0 + constants::DMI + constants::MUI);
    const double g4pmi = rgmma_scalar(4.0 + constants::MUI);
    const double pidni = cmi * g1pdimi / g1pmi;
    const double avedia_factor = std::pow(g4pmi / g1pmi, 1.0 / 3.0);
    const double rslopeimax = 1.0 / constants::LAMDAIMAX;
    const double rslopeimin = 1.0 / constants::LAMDAIMIN;

    constexpr double eps = 1.0e-30;
    auto dtype = state.qc.dtype();

    auto ice_active = (state.qi > qmin) & (state.ni > 0.0) & (den > 0.0);
    auto qi_safe = torch::clamp(state.qi * den, /*min=*/eps);
    auto ratio = pidni * torch::clamp(state.ni, /*min=*/0.0) / qi_safe;
    auto lamdai = torch::pow(torch::clamp(ratio, /*min=*/eps), 1.0 / constants::DMI);
    auto rslope_i_raw = torch::clamp(
        1.0 / torch::clamp(lamdai, /*min=*/eps),
        /*min=*/rslopeimax, /*max=*/rslopeimin
    );
    auto rslopeimax_t = torch::full_like(rslope_i_raw, rslopeimax);
    auto rslope_i = torch::where(ice_active, rslope_i_raw, rslopeimax_t);
    auto avedia_i = rslope_i * avedia_factor;

    auto mask = ice_active & (state.t < t0c) & (avedia_i >= di_threshold);
    auto mask_f = mask.to(dtype);
    auto inv_mask_f = 1.0 - mask_f;

    return CoordinatorState{
        /*qv=*/state.qv,
        /*qc=*/state.qc,
        /*qr=*/state.qr,
        /*qs=*/state.qs + state.qi * mask_f,
        /*qg=*/state.qg,
        /*qi=*/state.qi * inv_mask_f,
        /*nc=*/state.nc,
        /*nr=*/state.nr,
        /*ni=*/state.ni * inv_mask_f,
        /*nccn=*/state.nccn,
        /*brs=*/state.brs,
        /*t=*/state.t,
    };
}

// ─── F1g: rain→cloud reclassification (qr → qc at avedia_r ≤ 82μm) ─────────
CoordinatorState reclassify_small_rain_to_cloud(
    const CoordinatorState& state,
    const torch::Tensor& den,
    double qcrmin,
    double di_threshold
) {
    const double cmr = PI * constants::DENR / 6.0;
    const double g1pmr = rgmma_scalar(1.0 + constants::MUR);
    const double g1pdrmr = rgmma_scalar(1.0 + constants::DMR + constants::MUR);
    const double g4pmr = rgmma_scalar(4.0 + constants::MUR);
    const double pidnr = cmr * g1pdrmr / g1pmr;
    const double avedia_factor = std::pow(g4pmr / g1pmr, 1.0 / 3.0);
    const double rslopermax = 1.0 / constants::LAMDARMAX;
    const double rslopermin = 1.0 / constants::LAMDARMIN;

    constexpr double eps = 1.0e-30;
    auto dtype = state.qc.dtype();

    auto rain_active = (state.qr > qcrmin) & (state.nr > 0.0) & (den > 0.0);
    auto qr_safe = torch::clamp(state.qr * den, /*min=*/eps);
    auto ratio = pidnr * torch::clamp(state.nr, /*min=*/0.0) / qr_safe;
    auto lamdar = torch::pow(torch::clamp(ratio, /*min=*/eps), 1.0 / constants::DMR);
    auto rslope_r_raw = torch::clamp(
        1.0 / torch::clamp(lamdar, /*min=*/eps),
        /*min=*/rslopermax, /*max=*/rslopermin
    );
    auto rslopermax_t = torch::full_like(rslope_r_raw, rslopermax);
    auto rslope_r = torch::where(rain_active, rslope_r_raw, rslopermax_t);
    auto avedia_r = rslope_r * avedia_factor;

    auto mask = rain_active & (avedia_r <= di_threshold);
    auto mask_f = mask.to(dtype);
    auto inv_mask_f = 1.0 - mask_f;

    return CoordinatorState{
        /*qv=*/state.qv,
        /*qc=*/state.qc + state.qr * mask_f,
        /*qr=*/state.qr * inv_mask_f,
        /*qs=*/state.qs,
        /*qg=*/state.qg,
        /*qi=*/state.qi,
        /*nc=*/state.nc + state.nr * mask_f,
        /*nr=*/state.nr * inv_mask_f,
        /*ni=*/state.ni,
        /*nccn=*/state.nccn,
        /*brs=*/state.brs,
        /*t=*/state.t,
    };
}

// ─── F1i: DSD number limiters ───────────────────────────────────────────────
namespace {

torch::Tensor limit_number_for_lamda(
    const torch::Tensor& q, const torch::Tensor& n, const torch::Tensor& den,
    double pidn, double dm,
    double lamda_min, double lamda_max,
    double q_thresh, double n_thresh
) {
    constexpr double eps = 1.0e-30;
    auto active = (q >= q_thresh) & (n >= n_thresh);
    auto qden = torch::clamp(q * den, /*min=*/eps);
    auto ratio = torch::clamp(pidn * n / qden, /*min=*/eps);
    auto lamda = torch::pow(ratio, 1.0 / dm);
    auto n_at_min = den * q * std::pow(lamda_min, dm) / pidn;
    auto n_at_max = den * q * std::pow(lamda_max, dm) / pidn;
    auto too_small = active & (lamda <= lamda_min);
    auto too_large = active & (lamda >= lamda_max);
    return torch::where(too_small, n_at_min,
                        torch::where(too_large, n_at_max, n));
}

}  // namespace

CoordinatorState apply_dsd_number_limiters(
    const CoordinatorState& state,
    const torch::Tensor& den,
    double qmin,
    double qcrmin
) {
    const double cmr = PI * constants::DENR / 6.0;
    const double cmc = PI * constants::DENR / 6.0;  // cloud uses water density
    const double cmi = PI * constants::DENI / 6.0;
    const double pidnr = cmr * rgmma_scalar(1.0 + constants::DMR + constants::MUR)
                              / rgmma_scalar(1.0 + constants::MUR);
    // Cohard-Pinty modified gamma for cloud
    const double pidnc = cmc * rgmma_scalar(1.0 + constants::DMC / (constants::MUC + 1.0));
    const double pidni = cmi * rgmma_scalar(1.0 + constants::DMI + constants::MUI)
                              / rgmma_scalar(1.0 + constants::MUI);

    auto nr_new = limit_number_for_lamda(
        state.qr, state.nr, den,
        pidnr, constants::DMR,
        constants::LAMDARMIN, constants::LAMDARMAX,
        qcrmin, constants::NRMIN
    );
    auto nc_new = limit_number_for_lamda(
        state.qc, state.nc, den,
        pidnc, constants::DMC,
        constants::LAMDACMIN, constants::LAMDACMAX,
        qmin, constants::NCMIN
    );
    auto ni_new = limit_number_for_lamda(
        state.qi, state.ni, den,
        pidni, constants::DMI,
        constants::LAMDAIMIN, constants::LAMDAIMAX,
        qmin, constants::NCMIN
    );

    // Absolute caps (Fortran 3079-3082)
    auto nr_at_max = den * state.qr * std::pow(constants::LAMDARMAX, constants::DMR) / pidnr;
    auto nc_at_max = den * state.qc * std::pow(constants::LAMDACMAX, constants::DMC) / pidnc;
    nr_new = torch::where(nr_new > constants::NRMAX, nr_at_max, nr_new);
    nc_new = torch::where(nc_new > constants::NCMAX, nc_at_max, nc_new);

    return CoordinatorState{
        /*qv=*/state.qv,
        /*qc=*/state.qc, /*qr=*/state.qr, /*qs=*/state.qs,
        /*qg=*/state.qg, /*qi=*/state.qi,
        /*nc=*/nc_new, /*nr=*/nr_new, /*ni=*/ni_new,
        /*nccn=*/state.nccn,
        /*brs=*/state.brs, /*t=*/state.t,
    };
}

// ─── F2b: sedimentation chain (NISLFV-PLM) ──────────────────────────────────

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
) {
    const int64_t K = state.qr.size(-1);

    // ── Rain/snow/graupel/brs substepping ───────────────────────────────────
    sed::SubstepAdvectionState adv_state{state.qr, state.nr, state.qs, state.qg, state.brs};
    auto fall_qr = torch::zeros_like(state.qr);
    auto fall_nr = torch::zeros_like(state.qr);
    auto fall_qs = torch::zeros_like(state.qr);
    auto fall_qg = torch::zeros_like(state.qr);
    auto fall_brs = torch::zeros_like(state.qr);

    for (int i = 0; i < mstep_main; ++i) {
        sed::SubstepAdvectionInputs sin{
            adv_state,
            fall_qr, fall_nr, fall_qs, fall_qg, fall_brs,
            work1_qr, workn_qr, work1_qs, work1_qg,
            forcing.delz, forcing.dend,
        };
        auto out = sed::substep_advection_torch(sin, mstep_main, dtcld, params);
        adv_state = out.state;
        fall_qr = out.fall_qr;
        fall_nr = out.fall_nr;
        fall_qs = out.fall_qs;
        fall_qg = out.fall_qg;
        fall_brs = out.fall_brs;
    }

    // ── Ice substepping ─────────────────────────────────────────────────────
    sed::IceSubstepState ice_state{state.qi, state.ni};
    auto fall_qi = torch::zeros_like(state.qr);
    auto fall_ni = torch::zeros_like(state.qr);

    for (int i = 0; i < mstep_ice; ++i) {
        sed::IceSubstepInputs iin{
            ice_state,
            fall_qi, fall_ni,
            work1_qi, workn_qi,
            forcing.delz, forcing.dend,
        };
        auto out_i = sed::ice_substep_advection_torch(iin, mstep_ice, dtcld, params);
        ice_state = out_i.state;
        fall_qi = out_i.fall_qi;
        fall_ni = out_i.fall_ni;
    }

    // ── Surface accumulation (bottom layer K-1) ─────────────────────────────
    using torch::indexing::Slice;
    using torch::indexing::None;
    auto bottom = K - 1;
    auto fall_qr_b = fall_qr.index({Slice(), bottom});
    auto fall_qs_b = fall_qs.index({Slice(), bottom});
    auto fall_qg_b = fall_qg.index({Slice(), bottom});
    auto fall_qi_b = fall_qi.index({Slice(), bottom});
    auto delz_b = forcing.delz.index({Slice(), bottom});
    auto surface = sed::surface_accumulation_torch(
        fall_qr_b, fall_qs_b, fall_qg_b, fall_qi_b, delz_b, dtcld
    );

    // ── Stitch updated state — qv/qc/nc/t/brs(graupel)는 sedimentation 비대상.
    //   본 함수는 qr/nr/qs/qg/brs/qi/ni만 갱신.
    //   주의: brs는 graupel volume이라 substep_advection의 출력 brs를 그대로 사용.
    CoordinatorState new_state{
        /*qv=*/state.qv,
        /*qc=*/state.qc,
        /*qr=*/adv_state.qr,
        /*qs=*/adv_state.qs,
        /*qg=*/adv_state.qg,
        /*qi=*/ice_state.qi,
        /*nc=*/state.nc,
        /*nr=*/adv_state.nr,
        /*ni=*/ice_state.ni,
        /*nccn=*/state.nccn,
        /*brs=*/adv_state.brs,
        /*t=*/state.t,
    };

    return SedimentationOutputs{
        /*state=*/new_state,
        /*rain_increment=*/surface.rain_increment,
        /*snow_increment=*/surface.snow_increment,
        /*graupel_increment=*/surface.graupel_increment,
    };
}

}  // namespace kdm6
