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
    double dtcld,
    const thermo::ThermoParams& thermo_params
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

    // B-pre-5: pcact (CCN activation → cloud water). Computed BEFORE satadj so
    // that satadj sees the post-pcact (warmer, vapor-depleted) state — mirrors
    // Fortran module_mp_kdm6.f90:2890-2934 sequential ordering. The Python
    // oracle defers pcact entirely (kdm6_torch/kdm6/coordinator.py:733-740 +
    // constants.py:107-111 design intent: "wrapper 단계에서 처리할 simplified
    // default") which works for offline parity tests but causes 15× cloud-water
    // overshoot in supersaturation-active operational runs (em_squall2d_x).
    // This block implements Task #74 at the C++ layer; Python oracle parity is
    // preserved by keeping pcact OUT of the state_update budget when nullopt
    // (operational path always provides xland, so nccn-driven pcact fires).
    // Fortran `sw` is PERCENT supersaturation: sw = (rh - 1) * 100 (kdm6.f90:868, 2798).
    // 0.48 threshold is in PERCENT (matches SATMAX=1.0048 → 0.48% activation cutoff).
    auto sw_percent_wp = (pre.rh_w - 1.0) * 100.0;
    auto sw_ratio = torch::clamp(sw_percent_wp / 0.48, /*min=*/0.0);
    auto activated_fraction = torch::minimum(
        torch::ones_like(sw_ratio),
        torch::pow(sw_ratio, constants::ACTK)
    );
    auto ncact_raw = torch::clamp((state.nccn + state.nc) * activated_fraction - state.nc, /*min=*/0.0) / dtcld;
    auto ncact = torch::minimum(ncact_raw, torch::clamp(state.nccn, /*min=*/0.0) / dtcld);
    ncact = torch::where(pre.supsat > 0.0, ncact, torch::zeros_like(ncact));
    auto pcact_raw = 4.0 * PI * constants::DENR * std::pow(constants::ACTR * 1.0e-6, 3.0) * ncact / (3.0 * forcing.den);
    auto pcact = torch::minimum(pcact_raw, torch::clamp(state.qv, /*min=*/0.0) / dtcld);

    // Apply pcact to LOCAL copies of t/qv/qc before passing into satadj.
    // Functional construction only — autograd graph preserved (no in-place,
    // no .item()). Mirrors Fortran kdm6.f90:2894-2898 + saturation recompute
    // before conden at :2906-2914:
    //   q   := max(q   - pcact*dtcld, 0)         ← qv_post_pcact
    //   qci := max(qci + pcact*dtcld, 0)         ← qc_post_pcact
    //   t   := t       + pcact*xl/cpm*dtcld      ← t_post_pcact
    //   qs1 := compute_qs_water(t_post_pcact, p) ← qs1_post_pcact (Fortran
    //                                              reruns conden which
    //                                              recomputes saturation)
    auto t_post_pcact   = state.t  + pcact * pre.xl / pre.cpm * dtcld;
    auto qv_post_pcact  = torch::clamp(state.qv - pcact * dtcld, /*min=*/0.0);
    auto qc_post_pcact  = torch::clamp(state.qc + pcact * dtcld, /*min=*/0.0);
    auto qs1_post_pcact = thermo::compute_qs_water(t_post_pcact, forcing.p, thermo_params);

    // B5: Saturation adjustment (qv ↔ qc) — consumes the post-pcact snapshot.
    auto satadj = satadj::saturation_adjustment_torch(
        t_post_pcact, qv_post_pcact, qc_post_pcact, qs1_post_pcact, pre.xl, pre.cpm,
        params.satadj, dtcld
    );

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
    // Codex stop-review fix: the cold rate loop's deposition/nucleation driver is
    // ICE supersaturation — Fortran kdm6.f90:1772 `supsat = max(q,qmin) - qs(i,k,2)`
    // (qs2 = ICE saturation), feeding satdt/supice/ifsat + the C3 gate (:2259) and
    // the pidep/psdep/pgdep caps (:2273-2340). The port's `pre.supsat` is WATER
    // (compute_supsat(qv, qs1)), correct for the WARM loop (:1645) but wrong for
    // cold. Reconstruct ice supsat from existing fields — EXACT since
    //   supsat + qs1 - qs2 = (max(q,qmin) - qs1) + qs1 - qs2 = max(q,qmin) - qs2.
    // cold_phase consumes PreambleCold.supsat ONLY in C3 (ice_nucleation) + C4
    // (dep_sub); snow/graupel evap use rh_w/rh_ice, so this field is ice-only.
    auto supsat_ice = pre.supsat + pre.qs1 - pre.qs2;
    return PreambleCold{
        pre.supcol, supsat_ice, pre.rh_w, pre.rh_ice,
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

// Stage-A STEP 1: apply melt(D1) + freeze(D2-D4) as INLINE pre-state-update
// mutations of a working state, using EXACTLY the signed expressions state_update
// used for these terms — so "apply inline" + "zero the D1-D4 mf fields passed to
// state_update" is an algebraic identity (state_pre + D1-D4 + warm+cold+D5 = OLD).
// Functional (out = copy; reassign fields) ⇒ no in-place, autograd threads the
// deltas. xlf=xls-pre.xl. NO clamps here — final nonneg clamps stay in
// state_update on the full sum (so split clamp == single clamp). STEP 2 will move
// this BEFORE warm/cold + rebuild aux; STEP 1 keeps warm/cold reading entry.
CoordinatorState apply_melt_freeze_inline(
    const CoordinatorState& s, const MeltFreezePhaseOutputs& mf,
    const PreambleCore& pre, double dtcld, double xls
) {
    auto dtype = s.qc.dtype();
    auto warm_mask = (pre.supcol <= 0).to(dtype);
    auto cpm_safe = torch::clamp(pre.cpm, /*min=*/constants::QCRMIN);
    auto xlf = xls - pre.xl;
    auto out = s;
    out.qc  = s.qc + (-mf.pinuc - mf.pfrzdtc + mf.pimlt_qi);                       // = dqc_amount
    out.qr  = s.qr + dtcld * (-(mf.psmlt + mf.pgmlt) * warm_mask) - mf.pfrzdtr;    // = dqr D1 + dqr_amount(D4)
    out.qs  = s.qs + dtcld * mf.psmlt;                                            // = dqs D1
    out.qg  = s.qg + dtcld * mf.pgmlt + mf.pfrzdtr;                               // = dqg D1 + dqg_amount(D4)
    out.qi  = s.qi + (mf.pinuc + mf.pfrzdtc - mf.pimlt_qi);                        // = dqi_amount
    out.nc  = s.nc + (-mf.ninuc - mf.nfrzdtc + mf.pimlt_ni);                       // = dnc_amount
    out.nr  = s.nr + (-mf.nfrzdtr);                                               // = dnr_amount(D4)
    out.ni  = s.ni + (mf.ninuc + mf.nfrzdtc - mf.pimlt_ni);                        // = dni_amount
    out.brs = s.brs + (dtcld * mf.delta_brs_melt + mf.delta_brs_freeze);          // = dbrs D1+D4 (clamp in state_update)
    out.t   = s.t
            + dtcld * xlf / cpm_safe * (mf.psmlt + mf.pgmlt)                       // = dT_freeze_rate D1 part
            + xlf / cpm_safe * (mf.pinuc + mf.pfrzdtc + mf.pfrzdtr - mf.pimlt_qi); // = dT_freeze_amount
    return out;
}

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
    // F1pre: homogeneous cloud→ice freeze (supcol>40, Fortran kdm6.f90:1359-1369)
    // is DISABLED — kdm62d_one_step does NOT apply it. It is a pre-cold freezing
    // step, but `aux` (n0i/avedia_i) is built upstream in the runtime
    // (runtime.cpp build_default_aux, from the ORIGINAL state) and is NOT rebuilt
    // after this freeze — so the cold phase would see STALE n0i on the post-freeze
    // ice. That stale-aux pre-freeze staging is the same class that produced an
    // 806× ice over-deposition regression when tried for the contact/Bigg freezing
    // (joint Claude+Codex review, 2026-05-30). Re-enabling it requires the same
    // cross-layer refactor as the full staging fix (freeze → REBUILD aux → cold).
    // Until then we keep the step free of stale-aux pre-cold freezing. The
    // apply_homogeneous_freeze_supercold function is retained (unused) as the
    // reference implementation for proper re-introduction with the aux rebuild.
    auto state_pre = state;

    // F1a: preamble (full diagnostics) on the ENTRY state.
    auto pre = preamble(state_pre, forcing, full_params);

    // ─── Stage-A STEP 2: SEQUENTIAL melt/freeze → rebuild → warm/cold/D5 ──────
    // Fortran kdm6.f90 mutates the state with melt (D1, :1239-1295) + contact/Bigg
    // freeze (D2-D4, :1442-1511) BEFORE the warm/cold rate loop (:1768), then
    // RE-SLOPES (ProgB+slope, :1372-1430,:1546-1633) so the rate loop reads
    // post-freeze intercepts/slopes. We mirror that exactly:
    //   1. D1-D4 rates from the ENTRY state (entry aux + entry pre).
    //   2. apply them INLINE → `working` (entry pre_core: entry xl/cpm/supcol).
    //   3. rebuild_aux(working) → fresh pre2 + aux2 TOGETHER (stale-pre = 806×).
    //   4. warm/cold/D5 read `working` + pre2 + aux2 (post-freeze supcol/slopes/n0).
    // D2-D4 rates still come from the ENTRY state here (STEP 3 recomputes them on
    // the post-melt state; STEP 4 makes the D3 cap sequential vs post-D2 qc).
    auto pre_core = pre_core_view(pre);   // ENTRY xl/cpm/supcol/rhox
    auto mf14 = melt_freeze_d1_d4(
        state_pre, forcing, pre_mf_view(pre),
        aux.n0c, aux.n0r, aux.n0so, aux.n0go,
        pre.rslopec, aux.rslopecmu, aux.rslopecd,
        mf_params, dtcld
    );
    auto working = apply_melt_freeze_inline(
        state_pre, mf14, pre_core, dtcld, full_params.thermo.xls);

    // F1a': rebuild preamble + aux on the post-melt/freeze working state. qcr is
    // sea_mask-derived + state-independent ⇒ carried from the entry aux. The
    // entry `pre` supplies the substep-top thermo (qs/xl/rh/supsat) that Fortran
    // does NOT recompute post-freeze (kdm6.f90:785-786,:860-878) — spliced inside.
    auto rebuilt = rebuild_aux(working, /*entry_pre=*/pre, forcing, full_params, aux.qcr);
    const auto& pre2 = rebuilt.pre;
    const auto& aux2 = rebuilt.aux;

    // F1b: warm phase (B1-B5) on the WORKING state + rebuilt pre2/aux2. thermo_params
    // lets the sequential pcact path recompute qs1 before satadj (kdm6.f90:2890-2914).
    auto warm_out = warm_phase(
        working, forcing, pre_warm_view(pre2),
        aux2.n0r, aux2.work1_r, aux2.qcr,
        warm_params, dtcld, full_params.thermo
    );

    // F1c: cold phase (C1-C6') on the WORKING state + rebuilt pre2/aux2.
    auto cold_out = cold_phase(
        working, forcing, pre_cold_view(pre2),
        warm_out.prevp,
        aux2.n0i, aux2.n0r, aux2.n0so, aux2.n0go, aux2.n0c,
        aux2.rslopecmu, aux2.rslopecd,
        aux2.avedia_i, aux2.work1_ice, aux2.work1_water,
        cold_params, dtcld
    );

    // F1d: D5 enhanced melting — reads cold_out + the working state + rebuilt slopes.
    auto mf5 = melt_freeze_d5(
        working, forcing, pre_mf_view(pre2), cold_out,
        aux2.n0so, aux2.n0go, mf_params, dtcld
    );

    // F1d2: group conservation limiters bound warm/cold/D5 sinks against the
    // WORKING (post-melt/freeze) reservoirs, gated by post-freeze supcol — exactly
    // Fortran's combined budget+mass-balance loop (:2399-2706, gate `t.le.t0c`).
    // D1-D4 are already committed to `working`, and scale_rates only touches the
    // D5 fields (pseml/pgeml/nseml/ngeml), so passing mf5 is sufficient.
    auto scaled = scale_rates_for_conservation(
        working, pre2.supcol, warm_out, cold_out, mf5, dtcld
    );

    // F1e: state update on the WORKING base. HYBRID pre_core (Fortran-exact):
    //   xl/cpm  = ENTRY  (kdm6.f90:785-786 set once, reused through mass balance),
    //   supcol  = POST-FREEZE (mass-balance arm gates on t.le.t0c, :2406),
    //   rhox    = POST-FREEZE (re-sloped before the rate loop; brs terms :2593/2684).
    // delta_src = nullptr ⇒ delta2/delta3 track working qr/qs (Fortran :2402-2405
    // reads post-melt/freeze reservoirs). mf carries D5 only (D1-D4 in working).
    PreambleCore pre_core_su{pre.cpm, pre.xl, pre2.supcol, pre2.progb.rhox};
    auto new_state = state_update(
        working, pre_core_su, scaled.warm, scaled.cold, scaled.mf, dtcld,
        full_params.thermo.xls, /*delta_src=*/nullptr
    );

    // F1f: Picons (qi → qs at avedia_i ≥ 200μm).
    new_state = reclassify_large_ice_to_snow(new_state, forcing.den);

    // F1g: rain → cloud (avedia_r ≤ 82μm).
    new_state = reclassify_small_rain_to_cloud(new_state, forcing.den);

    // F1g+: pcact activation + satadj on post-state-update + post-reclass
    // state. Mirrors Fortran module_mp_kdm6.f90:2880-2929 sequence. The
    // earlier `state_update` deliberately omitted pcact/pcond/ncact_activation/
    // cloud_complete_evap from its budgets so this step can run on the proper
    // post-mass-balance + post-reclass state — fixing the frame-6+ cascade
    // (Codex stop-gate finding 8: satadj was applied to stale pre-mass-balance
    // state in C++, while Fortran runs it at line 2911 AFTER reclass at 2867).
    new_state = apply_satadj_step(
        new_state, forcing,
        pre.xl, pre.cpm,
        warm_params.satadj, full_params.thermo,
        dtcld
    );

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

    // Fortran module_mp_kdm6.F:747 entry-prologue clamp on nci(:,:,3).
    // Mirror it here so warm-phase ncact (coordinator.cpp:264-270) consumes the clamped
    // value, matching slot-37 behaviour. Post-rate clamp at line 791 is kept as the
    // surrogate for Fortran :2952 / :3076.
    CoordinatorState cur = state;
    cur.nccn = torch::clamp(cur.nccn, constants::NCCN_MIN, constants::NCCN_MAX);

    const int loops_max = compute_loops_max(delt, dtcldcr);
    const double dtcld = delt / static_cast<double>(loops_max);

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

// Stage-A STEP 2: the melt/freeze phase is SPLIT into the D1-D4 block (melt +
// ice-nucleation + Bigg freezing — depends ONLY on state+aux+slopes, NOT on
// cold_out) and the D5 block (enhanced melting — needs cold_out's accretion
// rates). This split lets kdm62d_one_step apply D1-D4 INLINE before warm/cold
// (Fortran kdm6.f90:1239-1511 mutate the state before the rate loop at :1768),
// then compute D5 AFTER cold_phase. melt_freeze_phase below recombines them so
// the legacy single-call signature (and its tests) stay bit-identical.
MeltFreezePhaseOutputs melt_freeze_d1_d4(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const PreambleMf& pre,
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
    auto zero = torch::zeros_like(state.qc);

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

    // D3: Bigg cloud freezing (cold cells). Stage-A STEP 4: caps against the
    // POST-D2 cloud reservoir — Fortran kdm6.f90 subtracts pinuc/ninuc from
    // qci(1)/nci(1) (:1451,:1454) BEFORE :1469/:1478 cap pfrzdtc/nfrzdtc against
    // them. SEQUENTIAL freeze draw (D2 then D3 on a running qc/nc), not two
    // parallel caps vs entry qc (which over-draws when pinuc+pfrzdtc>qc). n0c is
    // the SAME single re-sloped intercept Fortran shares across D2+D3 (NOT
    // recomputed after D2) — only the qc/nc cap+gate reservoir advances. AD-safe:
    // qc_post_d2 = qc - pinuc(qc) is differentiable, so the freeze-partition
    // sensitivity threads correctly.
    auto qc_post_d2 = state.qc - d2.pinuc;
    auto nc_post_d2 = state.nc - d2.ninuc;
    melt::BiggCloudInputs d3_in{
        qc_post_d2, nc_post_d2,
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

    return MeltFreezePhaseOutputs{
        /*psmlt=*/d1.psmlt, /*pgmlt=*/d1.pgmlt,
        /*pimlt_qi=*/d1.pimlt_qi, /*pimlt_ni=*/d1.pimlt_ni,
        /*sfac_melt=*/d1.sfac, /*gfac_melt=*/d1.gfac,
        /*delta_brs_melt=*/d1.delta_brs,
        /*pinuc=*/d2.pinuc, /*ninuc=*/d2.ninuc,
        /*pfrzdtc=*/d3.pfrzdtc, /*nfrzdtc=*/d3.nfrzdtc,
        /*pfrzdtr=*/d4.pfrzdtr, /*nfrzdtr=*/d4.nfrzdtr,
        /*delta_brs_freeze=*/d4.delta_brs,
        /*pseml=*/zero, /*nseml=*/zero,    // D5 deferred to melt_freeze_d5
        /*pgeml=*/zero, /*ngeml=*/zero,
    };
}

MeltFreezePhaseOutputs melt_freeze_d5(
    const CoordinatorState& state,
    const CoordinatorForcing& /*forcing*/,
    const PreambleMf& pre,
    const ColdPhaseOutputs& cold_out,
    const torch::Tensor& n0so,
    const torch::Tensor& n0go,
    const MeltFreezePhaseParams& params,
    double dtcld
) {
    const auto& s = pre.slope;
    auto zero = torch::zeros_like(state.qc);

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
        /*psmlt=*/zero, /*pgmlt=*/zero,    // D1-D4 belong to melt_freeze_d1_d4
        /*pimlt_qi=*/zero, /*pimlt_ni=*/zero,
        /*sfac_melt=*/zero, /*gfac_melt=*/zero,
        /*delta_brs_melt=*/zero,
        /*pinuc=*/zero, /*ninuc=*/zero,
        /*pfrzdtc=*/zero, /*nfrzdtc=*/zero,
        /*pfrzdtr=*/zero, /*nfrzdtr=*/zero,
        /*delta_brs_freeze=*/zero,
        /*pseml=*/d5.pseml, /*nseml=*/d5.nseml,
        /*pgeml=*/d5.pgeml, /*ngeml=*/d5.ngeml,
    };
}

// Legacy single-call orchestrator (D1-D5 from one state). Thin combiner over
// the split halves — used by tests + the STEP 1 (parallel-from-entry) path.
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
    auto out = melt_freeze_d1_d4(
        state, forcing, pre, n0c, n0r, n0so, n0go,
        rslopec, rslopecmu, rslopecd, params, dtcld);
    auto d5 = melt_freeze_d5(state, forcing, pre, cold_out, n0so, n0go, params, dtcld);
    out.pseml = d5.pseml; out.nseml = d5.nseml;
    out.pgeml = d5.pgeml; out.ngeml = d5.ngeml;
    return out;
}

// ─── F1d2: group conservation limiters (Fortran module_mp_kdm6.f90) ─────────
//
// Ports the 14 Fortran group budgets: 8 cold-arm (t<=t0c, :2410-2547) + 6
// warm-arm (t>t0c, :2607-2678), the two branches of one per-cell conditional.
// Each: value=max(floor,reservoir); source=Σ(signed sinks)·dtcld; if(source>
// value) scale every listed sink by factor=value/source. Tensorized over the
// full grid, gated by supcol so cold/warm budgets touch only their arm's cells.
//
// IMPLEMENTATION PRINCIPLE: each `source` is the LITERAL Fortran arithmetic on
// the corresponding C++ rate tensors (the port carries Fortran's sign
// convention, so identical arithmetic ⇒ identical source — no sign reasoning).
// Rates are scaled IN ORDER, in place: a rate re-read by a later budget (e.g.
// praut by cloud-mass then rain-mass) sees its already-scaled value, matching
// Fortran's sequential budgets. factor = value/max(source,value) is an EXACT
// no-op (=1.0) when source<=value (incl. net-source/wrong-arm cells), so the
// common case is bit-unchanged. pgaut/pgacs are identically 0 in this scheme
// (dropped, not invented). paacw/naacw appear ×2 in the source (state_update
// uses 2·*_adj) but are scaled ONCE. Autograd-safe: where+maximum, no .item().
ConservedRates scale_rates_for_conservation(
    const CoordinatorState& state,
    const torch::Tensor& supcol,
    WarmPhaseOutputs warm,
    ColdPhaseOutputs cold,
    MeltFreezePhaseOutputs mf,
    double dtcld
) {
    auto dtype = state.qc.dtype();
    auto cold_gate = (supcol > 0);                  // == state_update cold_mask
    auto warm_gate = (supcol <= 0);                 // complement (warm arm)

    // delta2/delta3 from PRE-update reservoirs (Fortran :2402-2405; identical to
    // state_update :711-712 — duplicated, pure function of pre-state).
    auto delta2 = ((state.qr < 1.0e-4) & (state.qs < 1.0e-4)).to(dtype);
    auto delta3 = (state.qr < 1.0e-4).to(dtype);
    auto one_m_d2 = 1.0 - delta2;
    auto one_m_d3 = 1.0 - delta3;

    // value=max(floor,reservoir); factor=value/max(source,value) gated to arm.
    auto limit = [&](const torch::Tensor& reservoir, double floor,
                     const torch::Tensor& source_sum, const torch::Tensor& gate,
                     std::initializer_list<torch::Tensor*> rates) {
        auto value = torch::clamp(reservoir, floor);
        auto source = source_sum * dtcld;
        auto factor_raw = value / torch::maximum(source, value);
        auto factor = torch::where(gate, factor_raw, torch::ones_like(value));
        for (auto* r : rates) { *r = *r * factor; }
    };

    // ── PASS 1: cold arm (t<=t0c), gate=cold_gate ──────────────────────────
    // cloud mass (:2410): praut+pracw+2·paacw+piacw+pmulcs+pmulcg
    limit(state.qc, constants::EPS,
          warm.praut + warm.pracw + 2.0 * cold.paacw_adj + cold.piacw
              + cold.pmulcs + cold.pmulcg,
          cold_gate,
          {&warm.praut, &warm.pracw, &cold.paacw_adj, &cold.piacw,
           &cold.pmulcs, &cold.pmulcg});
    // ice mass (:2425): psaut-pinud-pidep+praci+psaci+pgaci-pmulcs-pmulrs-pmulcg-pmulrg-piacw
    limit(state.qi, constants::EPS,
          cold.psaut - cold.pinud - cold.pidep + cold.praci + cold.psaci
              + cold.pgaci - cold.pmulcs - cold.pmulrs - cold.pmulcg
              - cold.pmulrg - cold.piacw,
          cold_gate,
          {&cold.psaut, &cold.pinud, &cold.pidep, &cold.praci, &cold.psaci,
           &cold.pgaci, &cold.piacw, &cold.pmulcs, &cold.pmulrs, &cold.pmulcg,
           &cold.pmulrg});
    // rain mass (:2445): -praut-prevp-pracw+piacr+psacr+pgacr+pmulrs+pmulrg
    limit(state.qr, constants::EPS,
          -warm.praut - warm.prevp - warm.pracw + cold.piacr + cold.psacr_adj
              + cold.pgacr_adj + cold.pmulrs + cold.pmulrg,
          cold_gate,
          {&warm.praut, &warm.prevp, &warm.pracw, &cold.piacr, &cold.psacr_adj,
           &cold.pgacr_adj, &cold.pmulrs, &cold.pmulrg});
    // snow mass (:2462): -(psdep+psaut+paacw+piacr·d3+praci·d3-pracs·(1-d2)+psacr·d2+psaci)
    //   (pgaut, pgacs ≡ 0 dropped)
    limit(state.qs, constants::EPS,
          -(cold.psdep + cold.psaut + cold.paacw_adj
            + cold.piacr * delta3 + cold.praci * delta3
            - cold.pracs * one_m_d2 + cold.psacr_adj * delta2 + cold.psaci),
          cold_gate,
          {&cold.psdep, &cold.psaut, &cold.paacw_adj, &cold.piacr, &cold.praci,
           &cold.psaci, &cold.pracs, &cold.psacr_adj});
    // graupel mass (:2483): -(pgdep+piacr·(1-d3)+praci·(1-d3)+psacr·(1-d2)+pracs·(1-d2)+pgaci+paacw+pgacr)
    //   (pgaut, pgacs ≡ 0 dropped)
    limit(state.qg, constants::EPS,
          -(cold.pgdep + cold.piacr * one_m_d3 + cold.praci * one_m_d3
            + cold.psacr_adj * one_m_d2 + cold.pracs * one_m_d2 + cold.pgaci
            + cold.paacw_adj + cold.pgacr_adj),
          cold_gate,
          {&cold.pgdep, &cold.piacr, &cold.praci, &cold.psacr_adj, &cold.pracs,
           &cold.paacw_adj, &cold.pgaci, &cold.pgacr_adj});
    // cloud number (:2504): nraut+nccol+nracw+niacw+2·naacw
    limit(state.nc, constants::NCMIN,
          warm.nraut + warm.nccol + warm.nracw + cold.niacw + 2.0 * cold.naacw,
          cold_gate,
          {&warm.nraut, &warm.nccol, &warm.nracw, &cold.naacw, &cold.niacw});
    // ice number (:2518): nraci+nsaci+ngaci+niacr+nsaut-nmulcs-nmulcg-nmulrs-nmulrg-ninud
    limit(state.ni, constants::NCMIN,
          cold.nraci + cold.nsaci + cold.ngaci + cold.niacr + cold.nsaut
              - cold.nmulcs - cold.nmulcg - cold.nmulrs - cold.nmulrg
              - cold.ninud,
          cold_gate,
          {&cold.nraci, &cold.nsaci, &cold.ngaci, &cold.niacr, &cold.nsaut,
           &cold.ninud, &cold.nmulcs, &cold.nmulcg, &cold.nmulrs, &cold.nmulrg});
    // rain number (:2537): -nraut+nraci+nrcol+niacr+nsacr+ngacr
    limit(state.nr, constants::NRMIN,
          -warm.nraut + cold.nraci + warm.nrcol + cold.niacr + cold.nsacr
              + cold.ngacr,
          cold_gate,
          {&cold.nraci, &warm.nraut, &warm.nrcol, &cold.niacr, &cold.nsacr,
           &cold.ngacr});

    // ── PASS 2: warm arm (t>t0c), gate=warm_gate ───────────────────────────
    // cloud mass (:2607): praut+pracw+2·paacw
    limit(state.qc, constants::EPS,
          warm.praut + warm.pracw + 2.0 * cold.paacw_adj,
          warm_gate,
          {&warm.praut, &warm.pracw, &cold.paacw_adj});
    // rain mass (:2619): -2·paacw-praut+pseml+pgeml-pracw-prevp
    limit(state.qr, constants::EPS,
          -2.0 * cold.paacw_adj - warm.praut + mf.pseml + mf.pgeml
              - warm.pracw - warm.prevp,
          warm_gate,
          {&warm.praut, &warm.prevp, &warm.pracw, &cold.paacw_adj,
           &mf.pseml, &mf.pgeml});
    // snow mass (:2634, floor=qcrmin): -pseml-psevp   (pgacs ≡ 0 dropped)
    limit(state.qs, constants::QCRMIN,
          -mf.pseml - cold.psevp,
          warm_gate,
          {&cold.psevp, &mf.pseml});
    // graupel mass (:2645, floor=qcrmin): -(pgevp+pgeml)   (pgacs ≡ 0 dropped)
    limit(state.qg, constants::QCRMIN,
          -(cold.pgevp + mf.pgeml),
          warm_gate,
          {&cold.pgevp, &mf.pgeml});
    // cloud number (:2656): nraut+nccol+nracw+2·naacw
    limit(state.nc, constants::NCMIN,
          warm.nraut + warm.nccol + warm.nracw + 2.0 * cold.naacw,
          warm_gate,
          {&warm.nraut, &warm.nccol, &warm.nracw, &cold.naacw});
    // rain number (:2669): -nraut+nrcol-nseml-ngeml
    limit(state.nr, constants::NRMIN,
          -warm.nraut + warm.nrcol - mf.nseml - mf.ngeml,
          warm_gate,
          {&warm.nraut, &warm.nrcol, &mf.nseml, &mf.ngeml});

    return ConservedRates{warm, cold, mf};
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
    double xls,
    const CoordinatorState* delta_src
) {
    auto dtype = state.qc.dtype();
    auto cold_mask = (pre.supcol > 0).to(dtype);
    auto warm_mask = 1.0 - cold_mask;
    // Stage-A STEP 1: delta2/delta3 are computed from the ENTRY state when the
    // base `state` is a post-melt/freeze working state (delta_src!=null). This
    // preserves the identity (melt/freeze must not flip the qr/qs<1e-4 routing
    // gates in the behaviour-preserving STEP 1). STEP 2 will pass null so delta
    // tracks the working state (Fortran computes it on the mutated state :2516).
    const CoordinatorState& dstate = delta_src ? *delta_src : state;

    // ── Mass balance ────────────────────────────────────────────────────────
    // qv — pcact/pcond DEFERRED to apply_satadj_step (called after state_update
    // + reclassifications in kdm62d_one_step), mirroring Fortran kdm6.f90:
    // mass balance at :2680-2823 runs FIRST, then reclass at :2862-2876, THEN
    // pcact apply at :2887-2898, THEN satadj/pcond at :2906-2927.
    // Per-cell warm/cold/mf rates are applied here; activation + condensation
    // run on the post-state-update + post-reclass state for proper Fortran
    // sequence parity (Codex stop-gate finding 8 - frame-6+ cascade origin).
    auto dqv = dtcld * (
        - warm.prevp
        - cold.pinud
        - cold.pidep - cold.psdep - cold.pgdep
        - cold.psevp
        - cold.pgevp
    );
    auto qv_new = state.qv + dqv;

    // qc — pcact/pcond also deferred (see dqv comment). Warm-phase qc sinks
    // (autoconv, accretion, etc.) and cold/mf amount-transfers stay here.
    auto dqc_rate = dtcld * (
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
        // #1 (audit): WARM arm sheds rimed cloud to RAIN (Fortran :2690 qr+=2*paacw);
        // cold arm routes paacw to qs/qg instead (handled below, cold_mask). Was
        // missing in both ports — warm cells wrongly grew ice. (WRF-validated.)
        + 2.0 * cold.paacw_adj * warm_mask
    );
    auto dqr_amount = -mf.pfrzdtr;
    auto qr_new = state.qr + dqr_rate + dqr_amount;

    // delta2/delta3 routing flags (Fortran 2516-2519) — from ENTRY state (dstate)
    auto delta2 = ((dstate.qr < 1.0e-4) & (dstate.qs < 1.0e-4)).to(dtype);
    auto delta3 = (dstate.qr < 1.0e-4).to(dtype);
    auto one_m_d2 = 1.0 - delta2;
    auto one_m_d3 = 1.0 - delta3;

    // qs — 2697-2701 + warm-branch 2811
    auto dqs = dtcld * (
        cold.psdep
        + cold.psaut
        + cold.paacw_adj * cold_mask          // #1: paacw→qs only in COLD arm (Fortran :2583); warm arm sheds to qr
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
        + cold.paacw_adj * cold_mask          // #1: paacw→qg only in COLD arm (Fortran :2591); warm arm sheds to qr
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
    // ncact (activation) and cloud_complete_evap deferred to apply_satadj_step
    // — they fire on the post-state-update + post-reclass state per Fortran
    // sequence (module_mp_kdm6.f90:2887-2927). The mass balance here only
    // accounts for warm/cold/mf rates that Fortran applies BEFORE that block.
    auto nc_new = state.nc + dnc_rate + dnc_amount;

    auto dnr_rate = dtcld * (
        warm.nraut
        - warm.nrcol
        - cold.niacr - cold.nraci
        - cold.nsacr - cold.ngacr
        // Fortran kdm6.f90:2733 — enhanced-melt number sources to rain.
        // Previously omitted in C++; Codex review caught the gap.
        + mf.nseml + mf.ngeml
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
    // Fortran module_mp_kdm6.f90:2596 — `xls` is the CONSTANT latent heat of
    // sublimation (XLS=2.85e6, passed in); the fusion latent heat is DERIVED and
    // TEMPERATURE-DEPENDENT: xlf(T) = xls - xl(T). The previous code INVERTED this
    // (constant xlf, derived xls), which over-heated freezing by up to ~56% at
    // cold (T≪0) updraft cores (where xl(T) grows, so the true xlf shrinks while
    // the constant did not) — the systematic ice-phase over-intensification that
    // made mp=137 produce ~90× more condensate than mp=37 in supercell ice
    // regions. Deposition correctly uses the constant `xls`; freezing uses xlf(T).
    auto xlf = xls - pre.xl;

    // pcact + pcond warming terms DEFERRED — apply_satadj_step adds them to
    // T after running on the post-state-update state (matches Fortran sequence
    // at module_mp_kdm6.f90:2898 + :2927).
    auto dT_warm_phase = dtcld * pre.xl / cpm_safe * (
        warm.prevp + cold.psevp + cold.pgevp
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
    // nccn: only rain_complete_evap adds back here (warm.rain_complete_evap is a
    // B4 output, applied with the warm rates). cloud_complete_evap and
    // nccn_activation are part of the deferred satadj step (see dqv comment),
    // so they are NOT applied at this point — apply_satadj_step handles them
    // after the reclassifications, matching Fortran module_mp_kdm6.f90:2887-2927.
    auto nccn_new = state.nccn + rain_complete_evap_amount;

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
        torch::clamp(nccn_new, constants::NCCN_MIN, constants::NCCN_MAX),
        brs_new,
        t_new,
    };
}

// ─── F1g+: pcact + satadj on post-state-update + post-reclass state ────────
//
// Mirrors Fortran module_mp_kdm6.f90:2880-2929 (the `do i = its, ite` block
// after mass balance and reclassifications). The earlier `state_update` step
// intentionally OMITS pcact/pcond/cloud_complete_evap/ncact_activation from
// its budgets — they all happen here on the post-mass-balance state for
// Fortran-sequence parity (frame-6+ cascade root cause per Codex review).
//
// Sequence:
//   1. Recompute supsat from new_state (forcing.p, state.t, state.qv)
//   2. Compute pcact + ncact (kdm6.f90:2889-2893)
//   3. Apply pcact   →  q -=pcact·dt, qc +=pcact·dt, t +=pcact·xl/cpm·dt
//   4. Apply ncact   →  nc +=ncact·dt, nccn -=ncact·dt           (kdm6.f90:2896-2897)
//   5. Recompute qs1 from post-pcact t                            (kdm6.f90:2906-2910)
//   6. Run satadj → pcond, cloud_complete_evap                    (kdm6.f90:2911-2915)
//   7. Complete-evap NC→NCCN transfer                             (kdm6.f90:2920-2923)
//   8. Apply pcond   →  q -=pcond·dt, qc +=pcond·dt, t +=pcond·xl/cpm·dt
//   9. Nonneg clamps + NCCN reservoir bounds
//
CoordinatorState apply_satadj_step(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const torch::Tensor& xl,
    const torch::Tensor& cpm,
    const satadj::SatAdjParams& satadj_params,
    const thermo::ThermoParams& thermo_params,
    double dtcld
) {
    auto dtype = state.qc.dtype();
    auto cpm_safe = torch::clamp(cpm, /*min=*/constants::QCRMIN);

    // Step 1: supsat from current state (post-state-update + reclass).
    auto qs1 = thermo::compute_qs_water(state.t, forcing.p, thermo_params);
    auto supsat = state.qv - qs1;

    // Step 2: pcact + ncact (Fortran kdm6.f90:2889-2893).
    // Fortran `sw` is PERCENT supersaturation: sw = (rh - 1) * 100 (kdm6.f90:868, 2798).
    // The 0.48 threshold is in PERCENT (matches SATMAX=1.0048 → 0.48% activation cutoff).
    // We must compute sw in percent here, NOT use raw `supsat = qv - qs1` (kg/kg).
    auto qs1_safe = torch::clamp(qs1, /*min=*/constants::QCRMIN);
    auto sw_percent = (state.qv / qs1_safe - 1.0) * 100.0;
    auto sw_ratio = torch::clamp(sw_percent / 0.48, /*min=*/0.0);
    auto activated_fraction = torch::minimum(
        torch::ones_like(sw_ratio),
        torch::pow(sw_ratio, constants::ACTK)
    );
    auto ncact_raw = torch::clamp(
        (state.nccn + state.nc) * activated_fraction - state.nc, /*min=*/0.0
    ) / dtcld;
    auto ncact = torch::minimum(ncact_raw, torch::clamp(state.nccn, /*min=*/0.0) / dtcld);
    ncact = torch::where(supsat > 0.0, ncact, torch::zeros_like(ncact));
    auto pcact_raw =
        4.0 * PI * constants::DENR * std::pow(constants::ACTR * 1.0e-6, 3.0)
        * ncact / (3.0 * forcing.den);
    auto pcact = torch::minimum(pcact_raw, torch::clamp(state.qv, /*min=*/0.0) / dtcld);

    // Step 3 + 4: apply pcact + ncact to (q, qc, t, nc, nccn).
    auto qv_pp   = torch::clamp(state.qv - pcact * dtcld, /*min=*/0.0);
    auto qc_pp   = torch::clamp(state.qc + pcact * dtcld, /*min=*/0.0);
    auto t_pp    = state.t + pcact * xl / cpm_safe * dtcld;
    auto nc_pp   = torch::clamp(state.nc + ncact * dtcld, /*min=*/0.0);
    auto nccn_pp = torch::clamp(state.nccn - ncact * dtcld, /*min=*/0.0);

    // Step 5: recompute qs1 from t_pp (Fortran kdm6.f90:2906-2910).
    auto qs1_pp = thermo::compute_qs_water(t_pp, forcing.p, thermo_params);

    // Step 6: satadj on the post-pcact snapshot (Fortran :2911-2915).
    auto sat = satadj::saturation_adjustment_torch(
        t_pp, qv_pp, qc_pp, qs1_pp, xl, cpm_safe, satadj_params, dtcld
    );

    // Step 7: complete-evap NC → NCCN (Fortran :2920-2923).
    auto complete_evap_mask = sat.cloud_complete_evap.to(dtype);
    auto nc_evap_amount   = nc_pp * complete_evap_mask;
    auto nc_final         = torch::clamp(nc_pp - nc_evap_amount, /*min=*/0.0);
    auto nccn_final_raw   = nccn_pp + nc_evap_amount;

    // Step 8: apply pcond to (q, qc, t).
    auto qv_final = torch::clamp(qv_pp - sat.pcond * dtcld, /*min=*/0.0);
    auto qc_final = torch::clamp(qc_pp + sat.pcond * dtcld, /*min=*/0.0);
    auto t_final  = t_pp + sat.pcond * xl / cpm_safe * dtcld;

    // Step 9: reservoir clamps (preserve NCCN_MIN/MAX band).
    auto nccn_final = torch::clamp(nccn_final_raw, constants::NCCN_MIN, constants::NCCN_MAX);

    return CoordinatorState{
        qv_final,
        qc_final,
        state.qr,
        state.qs,
        state.qg,
        state.qi,
        nc_final,
        state.nr,
        state.ni,
        nccn_final,
        state.brs,
        t_final,
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

// ─── F1g'': homogeneous cloud→ice freeze at supcol > 40 ────────────────────
//
// Fortran `module_mp_kdm6.f90:1359-1369` — at supcol > 40 (T < t0c-40 ≈ 233K),
// instantaneously convert ALL cloud water to ice and release fusion latent heat:
//   qci(2) += qci(1)         ! ice += cloud
//   nci(2) += nci(1)
//   t      += xlf/cpm * qci(1)
//   qci(1)  = 0
//   nci(1)  = 0
// where xlf = xls - xl(T) (sublimation - vaporization = fusion latent heat).
//
// Important for deep convective updraft tops (em_squall2d_x reaches T<-40°C).
// Without this, residual qc lingers above the supercooled limit, distorting
// downstream ice budget.
//
// NOTE: this function is CURRENTLY NOT CALLED by kdm62d_one_step (disabled
// 2026-05-30). As a pre-cold freezing step it needs aux (n0i) rebuilt from the
// post-freeze state (aux is built upstream in the runtime), and wiring it in
// without that rebuild left the cold phase on stale n0i (806× over-deposition
// regression). Retained for re-introduction with the aux-rebuild staging refactor.
CoordinatorState apply_homogeneous_freeze_supercold(
    const CoordinatorState& state,
    const thermo::ThermoParams& thermo_params,
    double supcol_threshold
) {
    auto dtype = state.qc.dtype();
    auto supcol = thermo_params.t0c - state.t;
    auto freeze_mask = (supcol > supcol_threshold) & (state.qc > 0.0);
    auto mask_f = freeze_mask.to(dtype);
    auto inv_mask_f = 1.0 - mask_f;

    // xlf = xls - xl(T). compute_xl gives xlv(T); subtract to get fusion.
    auto xl = thermo::compute_xl(state.t, thermo_params);
    auto cpm = thermo::compute_cpm(state.qv, thermo_params);
    auto xlf = thermo_params.xls - xl;
    auto cpm_safe = torch::clamp(cpm, /*min=*/constants::QCRMIN);
    auto dT = xlf / cpm_safe * state.qc;   // warming proportional to frozen mass

    return CoordinatorState{
        /*qv=*/state.qv,
        /*qc=*/state.qc * inv_mask_f,
        /*qr=*/state.qr,
        /*qs=*/state.qs,
        /*qg=*/state.qg,
        /*qi=*/state.qi + state.qc * mask_f,
        /*nc=*/state.nc * inv_mask_f,
        /*nr=*/state.nr,
        /*ni=*/state.ni + state.nc * mask_f,
        /*nccn=*/state.nccn,
        /*brs=*/state.brs,
        /*t=*/state.t + dT * mask_f,
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
    // apply_dsd_number_limiters implements the FINAL kdm62d block, whose ice
    // snap is Fortran kdm6.f90:2945 `qci(i,k,2).ge.qmin .and. nci(i,k,2).ge.ncmin`
    // — same qmin/ncmin pattern as the cloud snap (:2934) just above. The prior
    // 1e-14/0 gate mis-cited :1417 (the INLINE rate-phase snap, a different
    // occurrence with no n-gate); the final-block gate ANDs with ncmin.
    // (Adjudicated vs Fortran 2026-05-31; aggregate effect pending WRF per the
    // parity-audit memory — this is a confirmed Fortran-alignment correction.)
    auto ni_new = limit_number_for_lamda(
        state.qi, state.ni, den,
        pidni, constants::DMI,
        constants::LAMDAIMIN, constants::LAMDAIMAX,
        /*q_thresh=*/qmin, /*n_thresh=*/constants::NCMIN
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
