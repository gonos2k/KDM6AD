// KDM6 coordinator post-update helpers (C++ libtorch port).
// Python kdm6_torch/kdm6/coordinator.py F1e post-update 함수 1:1 미러링.
//
// review #1~#10 권고 모두 반영. AD-friendly: in-place 없음, .item() 없음, mask는
// torch::where + multiplicative mask (subgradient at boundary 0).
//
#include "kdm6/coordinator.h"
#include "kdm6/constants.h"
#include "kdm6/ops.h"
#include "kdm6/fconst.h"

#include <cmath>

namespace kdm6 {

namespace {

constexpr double PI = 3.14159265358979323846;

// Fortran rgmma(x) = exp(GAMMLN(x)) = Γ(x). review6 audit fix (1/Γ 아님).
inline double rgmma_scalar(double x) {
    // Fortran rgmma(x)=EXP(GAMMLN(x)) in REAL(4): f32 expf of the f32-rounded
    // double Lanczos — differs from exp(lgamma(double)) for NON-INTEGER args
    // (e.g. Γ(4/3), Γ(7/3) in D2/D3 freezing — the step-67 qi/ni seed class).
    return static_cast<double>(fconst::rgmma_f(static_cast<float>(x)));
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
    const thermo::ThermoParams& /*thermo_params*/  // unused since the dead warm-satadj removal (0d931a3)
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

    // Note: CCN activation (pcact/ncact) and the warm-phase saturation adjustment are
    // intentionally NOT computed here. They are deferred to apply_satadj_step (Task #74),
    // the single LIVE activation+satadj site (see :1280 — it sequences pcact → satadj →
    // pcond/cloud_complete_evap exactly per module_mp_kdm6.F:2903-2943). A duplicate
    // warm-phase satadj used to live here, but its outputs (pcond/cloud_complete_evap/
    // ncact/pcact) were never consumed — the caller reads only the warm RATES returned
    // below — so it was dead compute (and a dead pow() that had to be NaN-guarded). It is
    // removed. The Python oracle's warm phase likewise emits only the rates, so dropping
    // these four fields also keeps the two trees structurally aligned.
    return WarmPhaseOutputs{
        /*praut=*/b1.praut,  /*nraut=*/b1.nraut,
        /*pracw=*/b2.pracw,  /*nracw=*/b2.nracw,
        /*nccol=*/b3.nccol,  /*nrcol=*/b3.nrcol,
        /*prevp=*/rain_evap.prevp,
        /*rain_complete_evap=*/rain_evap.rain_complete_evap,
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
    const CoordinatorParams& params,
    const c10::optional<torch::Tensor>& ncmin_for_slope
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
        state.qc, state.nc, forcing.den, params.cloud_dsd, ncmin_for_slope
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

// Forward decl — the lamda-snap number rewrite (defined below at the end-of-step
// DSD limiter). SEED#2 reuses it at the intra-substep re-slope (Fortran F:1453-1466
// & F:1638-1651) so the clamp-rewritten cloud number flows into D2-D4 / warm /
// activation / state_update, not only at end-of-step.
torch::Tensor limit_number_for_lamda(
    const torch::Tensor& q, const torch::Tensor& n, const torch::Tensor& den,
    double pidn, double dm, double lamda_min, double lamda_max,
    double q_thresh, double n_thresh);

// Pull thermo + cloud_dsd + rain-slope subset out of full PreambleOutputs for warm_phase.
PreambleWarm pre_warm_view(const PreambleOutputs& pre) {
    return PreambleWarm{
        /*cpm=*/pre.cpm, /*xl=*/pre.xl, /*qs1=*/pre.qs1, /*rh_w=*/pre.rh_w, /*supsat=*/pre.supsat, /*work2=*/pre.work2,
        /*rslopec=*/pre.rslopec, /*avedia_c=*/pre.avedia_c, /*avedia_r=*/pre.avedia_r, /*lenconcr=*/pre.lenconcr,
        /*rslope_r=*/pre.slope.rslope_r, /*rslopeb_r=*/pre.slope.rslopeb_r,
        /*rslope2_r=*/pre.slope.rslope2_r, /*rslope3_r=*/pre.slope.rslope3_r, /*rslopemu_r=*/pre.slope.rslopemu_r,
    };
}

PreambleCold pre_cold_view(const PreambleOutputs& pre) {
    // Codex stop-review fix: the cold rate loop's deposition/nucleation driver is
    // ICE supersaturation — Fortran module_mp_kdm6.F:1822 `supsat = max(q,qmin) - qs(i,k,2)`
    // (qs2 = ICE saturation), feeding satdt/supice/ifsat + the C3 gate (:2309) and
    // the pidep/psdep/pgdep caps (:2323-2390). The port's `pre.supsat` is WATER
    // (compute_supsat(qv, qs1)), correct for the WARM loop (:1695) but wrong for
    // cold. Reconstruct ice supsat from existing fields — EXACT since
    //   supsat + qs1 - qs2 = (max(q,qmin) - qs1) + qs1 - qs2 = max(q,qmin) - qs2.
    // cold_phase consumes PreambleCold.supsat ONLY in C3 (ice_nucleation) + C4
    // (dep_sub); snow/graupel evap use rh_w/rh_ice, so this field is ice-only.
    auto supsat_ice = pre.supsat + pre.qs1 - pre.qs2;
    return PreambleCold{
        /*supcol=*/pre.supcol, /*supsat=*/supsat_ice, /*rh_w=*/pre.rh_w, /*rh_ice=*/pre.rh_ice,
        /*denfac=*/pre.denfac, /*work2=*/pre.work2,
        /*rslopec=*/pre.rslopec,
        /*avtg=*/pre.progb.avtg, /*g3pbg=*/pre.progb.g3pbg, /*precg2=*/pre.progb.precg2,
        /*slope=*/pre.slope,
    };
}

PreambleMf pre_mf_view(const PreambleOutputs& pre) {
    return PreambleMf{
        /*supcol=*/pre.supcol, /*work2=*/pre.work2,
        /*rhox=*/pre.progb.rhox, /*precg2=*/pre.progb.precg2,
        /*slope=*/pre.slope,
    };
}

PreambleCore pre_core_view(const PreambleOutputs& pre) {
    return PreambleCore{
        /*cpm=*/pre.cpm, /*xl=*/pre.xl, /*supcol=*/pre.supcol, /*rhox=*/pre.progb.rhox,
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
    auto warm_mask = (pre.supcol < 0).to(dtype);  // Fortran F:1279 melt gate `t.gt.t0c` ⇔ supcol<0 (strict);
                                                   // matches state_update warm_mask; Codex round-3 Finding 1
                                                   // (must be <0 not <=0 to keep inline↔state_update identical at supcol==0).
    auto cpm_safe = torch::clamp(pre.cpm, /*min=*/constants::QCRMIN);
    // D1 MELT holds xlf = xlf0 (constant; Fortran F:1275, the whole melt block at T>T0c — for the
    // rate AND the t-update); D2-D4 FREEZE uses the variable xls-xl(T) (Fortran F:1404). Sharing one
    // xlf over-cools the melt heat-sink by +0.67%/K above freezing (audit round-6).
    auto xlf_freeze = xls - pre.xl;
    const double xlf_melt = melt::DEFAULT_XLF;
    const auto kF64 = torch::kFloat64;
    auto out = s;
    // STEP-67 SEED: pinuc/ninuc/pfrzdtc/nfrzdtc arrive as f64 tensors (Fortran
    // DOUBLE scalars, F:738/755-756) and Fortran applies D2 then D3 as TWO
    // SEQUENTIAL state stores, each rounding once to REAL(4):
    //   qc1 = f32(DBLE(qc) - pinuc)   (F:1536)   qc2 = f32(DBLE(qc1) - pfrzdtc) (F:1565)
    //   qi1 = f32(DBLE(qi) + pinuc)   (F:1537)   qi2 = f32(DBLE(qi1) + pfrzdtc) (F:1566)
    // (numbers analogous, F:1533-1534/1563-1564). pimlt (D1, REAL) rides at the
    // first store: in the d1 call the D2/D3 rates are zeros (and vice versa), so
    // each call degenerates to its own Fortran block. .to(dtype) is the f32 store
    // (no-op on the fp64 oracle path); autograd-safe (casts are differentiable).
    auto qc1 = (s.qc.to(kF64) - mf.pinuc.to(kF64) + mf.pimlt_qi.to(kF64)).to(dtype);
    out.qc  = (qc1.to(kF64) - mf.pfrzdtc.to(kF64)).to(dtype);                      // = dqc_amount (D2 then D3)
    out.qr  = s.qr + dtcld * (-(mf.psmlt + mf.pgmlt) * warm_mask) - mf.pfrzdtr;    // = dqr D1 + dqr_amount(D4)
    out.qs  = s.qs + dtcld * mf.psmlt;                                            // = dqs D1
    out.qg  = s.qg + dtcld * mf.pgmlt + mf.pfrzdtr;                               // = dqg D1 + dqg_amount(D4)
    auto qi1 = (s.qi.to(kF64) + mf.pinuc.to(kF64) - mf.pimlt_qi.to(kF64)).to(dtype);
    out.qi  = (qi1.to(kF64) + mf.pfrzdtc.to(kF64)).to(dtype);                      // = dqi_amount (D2 then D3)
    auto nc1 = (s.nc.to(kF64) - mf.ninuc.to(kF64) + mf.pimlt_ni.to(kF64)).to(dtype);
    out.nc  = (nc1.to(kF64) - mf.nfrzdtc.to(kF64)).to(dtype);                      // = dnc_amount (D2 then D3)
    out.nr  = s.nr + (-mf.nfrzdtr)                                                // = dnr_amount(D4)
            + dtcld * (-mf.sfac_melt * mf.psmlt - mf.gfac_melt * mf.pgmlt);        // D1 melt snow/graupel → rain number (Fortran 1299/1323)
    auto ni1 = (s.ni.to(kF64) + mf.ninuc.to(kF64) - mf.pimlt_ni.to(kF64)).to(dtype);
    out.ni  = (ni1.to(kF64) + mf.nfrzdtc.to(kF64)).to(dtype);                      // = dni_amount (D2 then D3)
    out.brs = s.brs + (dtcld * mf.delta_brs_melt + mf.delta_brs_freeze);          // = dbrs D1+D4 (clamp in state_update)
    // SEED#5 (Fortran module_mp_kdm6.F:1303 then :1327): Fortran applies psmlt and
    // pgmlt as TWO SEPARATE sequential t-adds (`t+=coef·psmlt; t+=coef·pgmlt`), each
    // float32-rounded. Summing (psmlt+pgmlt) BEFORE the coefficient (the prior form)
    // diverges by 1 ULP in cells where snow AND graupel melt together (verified 28%
    // of such cells). Split into two sequential adds; keep the dtcld·xlf0/cpm
    // coefficient (verified 0 ULP). Tensor-ops only ⇒ autograd-safe.
    auto coef_melt = dtcld * xlf_melt / cpm_safe;
    auto t_d1 = s.t
            + coef_melt * mf.psmlt                                                 // D1 melt psmlt → xlf0 (sequential, F:1303)
            + coef_melt * mf.pgmlt                                                 // D1 melt pgmlt → xlf0 (sequential, F:1327)
            - xlf_melt / cpm_safe * mf.pimlt_qi;                                   // D1 instant ice-melt → xlf0
    // D2-D4 freeze t-stores are SEQUENTIAL in Fortran (F:1539/F:1569/F:1591), each
    // `t += (xlf/cpm)*rate` rounding once to REAL(4); the f32 coefficient xlf/cpm
    // promotes against the DOUBLE D2/D3 rates exactly like gfortran.
    auto fr_coef = xlf_freeze / cpm_safe;
    auto t_d2 = (t_d1 + fr_coef * mf.pinuc).to(dtype);                             // D2 freeze heat (F:1539)
    auto t_d3 = (t_d2 + fr_coef * mf.pfrzdtc).to(dtype);                           // D3 freeze heat (F:1569)
    out.t   = (t_d3 + fr_coef * mf.pfrzdtr).to(dtype);                             // D4 freeze heat (F:1591, f32 rate)
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
    double dtcld,
    const c10::optional<torch::Tensor>& ncmin_for_slope
) {
    // F1pre: homogeneous cloud→ice freeze (supcol>40, Fortran module_mp_kdm6.F:1410-1420)
    // is now ENABLED (Stage H2), applied at step 1b below — BETWEEN D1 melt and the
    // post-melt rebuild_aux. It was previously disabled because, as a pre-cold
    // freezing step, the cold phase would have read STALE n0i on the post-freeze ice
    // (the 806× over-deposition class). The Stage-A re-architecture now ALWAYS
    // rebuild_aux's after the freeze (re-slope on the post-homog/post-freeze ice
    // before warm/cold), which removes the stale-aux hazard — validated on
    // em_squall2d_x (−80°C tops): QICE stays bounded (~1.8e-3, no 806× blowup).
    auto state_pre = state;

    // F1a: preamble (full diagnostics) on the ENTRY state.
    auto pre = preamble(state_pre, forcing, full_params, ncmin_for_slope);

    // ─── Stage-A STEP 2+3: SEQUENTIAL melt → re-slope → freeze → re-slope → warm/cold ──
    // Fortran module_mp_kdm6.F order: D1 melt (:1274-1345) → [homog freeze :1410-1420] →
    // re-slope (:1422-1480) → D2-D4 contact/Bigg freeze (:1485-1561) → re-slope
    // (:1596-1683) → warm/cold rate loop (:1818). We mirror it stage-by-stage:
    //   1. D1 melt from the ENTRY state (warm cells); apply inline → working1.
    //   2. rebuild_aux(working1) → pre1/aux1 (post-melt re-slope, :1422-1480).
    //   3. D2-D4 freeze from working1 + pre1/aux1 (cold cells); apply inline → working.
    //   4. rebuild_aux(working) → pre2/aux2 (post-freeze re-slope, :1596-1683).
    //   5. warm/cold/D5 read `working` + pre2/aux2.
    // STEP 3 (this split) is bit-identical to the prior STEP-2 single-apply modulo
    // float reassociation: melt (warm, supcol<0) and freeze (cold, supcol>0) are
    // mutually exclusive per cell, so D2-D4-on-post-melt ≡ D2-D4-on-entry. The split
    // exists to host the (still-disabled) homog freeze between melt and the freeze
    // re-slope (Fortran :1410-1420 — Stage H2).
    auto pre_core = pre_core_view(pre);   // ENTRY xl/cpm/supcol/rhox (Fortran-fixed)
    // SEED#2: cloud-number lamda-snap constant (Cohard-Pinty modified gamma), same
    // pidnc as the end-of-step DSD limiter (apply_dsd_number_limiters). Used to
    // back-mutate the prognostic cloud number at each intra-substep re-slope.
    // f32-stepwise pidnc (kdm6init F:3205): the double-precomputed value is 1 ULP
    // low (0x4402E652 vs gfortran 0x4402E653) — the step-45 DSD-snap seed. fconst.h.
    const double pidnc_snap = fconst::get().pidnc;
    // f32 reciprocal of DMC (Fortran `1./dmc` REAL(4)) — see cloud_dsd.cpp step-65 note.
    const double INV_DMC_F32 = static_cast<double>(1.0f / static_cast<float>(constants::DMC));
    // 1. D1 melt → working1.
    auto mf_d1 = melt_freeze_d1(
        state_pre, forcing, pre_mf_view(pre), aux.n0so, aux.n0go, mf_params, dtcld);
    auto working1 = apply_melt_freeze_inline(
        state_pre, mf_d1, pre_core, dtcld, full_params.thermo.xls);

    // 1b. Homogeneous freeze (Fortran :1410-1420): at supcol>40 (T<-40°C) freeze
    // ALL cloud water → ice (qi+=qc, ni+=nc, t+=xlf/cpm·qc, qc=nc=0). Runs BETWEEN
    // D1 melt and the post-melt re-slope, so the re-slope + D2-D4 see the post-homog
    // qc (=0 in homog cells). Previously disabled (it was the 806× stale-aux trigger);
    // now safe because the rebuild_aux below re-slopes n0i on the post-homog ice.
    auto working1b = apply_homogeneous_freeze_supercold(working1, full_params.thermo, /*supcol_threshold=*/40.0);

    // 2. rebuild on the post-melt+homog state (re-slope :1422-1480; entry thermo spliced).
    auto rebuilt1 = rebuild_aux(working1b, /*entry_pre=*/pre, forcing, full_params, aux.qcr, ncmin_for_slope);
    const auto& pre1 = rebuilt1.pre;
    auto aux1 = rebuilt1.aux;   // mutable: n0c recomputed from the snapped nc below
    // SEED#2 (post-melt re-slope, Fortran module_mp_kdm6.F:1453-1466): when the cloud
    // slope clamps (onset: tiny droplets ⇒ lamdc>lamdacmax), Fortran REWRITES the
    // prognostic nci(1)=den·qc·lamdc_clamped^dmc/pidnc before the D2-D4 freeze rates
    // read it (the ninuc/nfrzdtc number caps min() against this rewritten number,
    // F:1500-1501/1524-1531). The C++ previously kept the raw advected nc until the
    // end-of-step DSD snap. Apply it here so D2-D4 (and downstream) see the snapped
    // number. Inert in unclamped cells (snap == identity); gated qc≥qmin & nc≥ncmin
    // (F:1638). Tensor-ops only ⇒ autograd-safe.
    auto nc_orig1 = working1b.nc;
    auto nc_snap1 = limit_number_for_lamda(
        working1b.qc, nc_orig1, forcing.den,
        pidnc_snap, constants::DMC, constants::LAMDACMIN, constants::LAMDACMAX,
        constants::EPS, constants::NCMIN);
    // Fortran F:1638 gates this re-slope snap on the PER-CELL ncmin (ncmin_sea=10 /
    // ncmin_land=100, F:820/822), NOT the scalar DSD floor NCMIN=1e-2. limit_number_for_lamda
    // uses the scalar, so restore cells below the per-cell floor — a near-empty cell
    // (NCMIN ≤ nc < ncmin_cell) must NOT be snapped (Codex stop-review). Tests pass
    // ncmin_for_slope=nullopt ⇒ scalar gate (unchanged). autograd-safe where.
    working1b.nc = ncmin_for_slope.has_value()
        ? torch::where(nc_orig1 >= *ncmin_for_slope, nc_snap1, nc_orig1)
        : nc_snap1;
    // Rebuild n0c CONSISTENT with the snapped nc. Fortran F:1640-1649: for ACTIVE cloud
    // (qci≥qmin & nci≥ncmin) n0c comes from the snap's OWN lamda —
    //   lamdc = clamp((pidnc·nci_raw/(den·qci))^(1/dmc), lamdacmin, lamdacmax)   [F:1640/1643/1647]
    //   n0c   = (muc+1)·nci_final·lamdc^(muc+1)                                  [F:1641/1645/1649]
    // — NOT from the slope-gate rslopec. The C++ cloud-slope inactive gate is `nci≤ncmin`
    // while the snap gate is `nci≥ncmin`; they disagree at the nci==ncmin boundary (there
    // rslopec=rslopecmax, but Fortran uses lamdc), so an rslopec-based n0c mismatches
    // Fortran exactly at that boundary (Codex stop-review). nci_raw=nc_orig1 for lamdc;
    // nci_final=snapped working1b.nc for the multiply (= nci_rewritten for clamped cells,
    // = nci for unclamped). Inactive cells keep build_default_aux's default (F:1619).
    // libm pow (bit-matches gfortran) ⇒ autograd-safe; no .item().
    {
        auto active = (working1b.qc >= constants::EPS) &
            (ncmin_for_slope.has_value() ? (nc_orig1 >= *ncmin_for_slope)
                                         : (nc_orig1 >= constants::NCMIN));
        auto lamdc = torch::clamp(
            ops::libm_exp(ops::libm_log(torch::clamp(pidnc_snap * nc_orig1 /
                torch::clamp(working1b.qc * forcing.den, 1.0e-30), 1.0e-30)) * INV_DMC_F32),
            constants::LAMDACMIN, constants::LAMDACMAX);
        // STEP-67 SEED: Fortran n0c is DOUBLE (F:697) and F:1465 computes
        // (muc+1)*DBLE(nci)*lamdc**(muc+1) — i.e. 3.0d·DBLE(nc)·DBLE(powf(lamdc,3))
        // with the ONLY f32 rounding inside the REAL**REAL powf. Upcast nc so the
        // product runs f64 (no-op on the fp64 oracle path); D2/D3 consume this f64
        // intercept directly (their chains are f64 from the *n0c factor on).
        auto n0c_active = (constants::MUC + 1.0) * working1b.nc.to(torch::kFloat64) *
            ops::safe_pow(lamdc, constants::MUC + 1.0);
        aux1.n0c = torch::where(active, n0c_active, aux1.n0c);
    }

    // STEP-79 SEED (block-A ice P3, F:1499-1512): at qi>=1e-14 (qi-ONLY gate, no
    // n-threshold) the fresh f32 lamdi snapping to [lamdaimin,lamdaimax] REWRITES
    // the prognostic nci2 = (den*qi)*powf(bound,3)/pidni, and n0i = DBLE(nci2_new)
    // *bound (mui=0, g1pmi=1). Without it, lamdai<lamdaimin cells keep the raw ni,
    // the final re-slope clamps rslope_i at 1/lamdaimin, and Picons fires by
    // construction (avedia at the clamp bound >= 200um) -> catastrophic qi wipe.
    // Runs AFTER the aux1 rebuild (pre1 slope keeps the PRE-rewrite ni, Fortran
    // slope order) and BEFORE D2-D4 (F:1534/1564 add ninuc/nfrzdtc onto the
    // rewritten ni). Mirrors the SEED#2 cloud nc-snap idiom.
    {
        auto ni_orig1 = working1b.ni;
        working1b.ni = limit_number_for_lamda(
            working1b.qi, ni_orig1, forcing.den,
            fconst::get().pidni, constants::DMI,
            constants::LAMDAIMIN, constants::LAMDAIMAX,
            /*q_thresh=*/1.0e-14, /*n_thresh=*/0.0);
        const double INV_DMI_F32 = static_cast<double>(1.0f / static_cast<float>(constants::DMI));
        auto lamdi1 = torch::clamp(
            ops::libm_exp(ops::libm_log(torch::clamp(fconst::get().pidni * ni_orig1 /
                torch::clamp(working1b.qi * forcing.den, 1.0e-30), 1.0e-30)) * INV_DMI_F32),
            constants::LAMDAIMIN, constants::LAMDAIMAX);
        aux1.n0i = torch::where(working1b.qi >= 1.0e-14,
            working1b.ni.to(torch::kFloat64) * lamdi1.to(torch::kFloat64), aux1.n0i);
    }

    // 3. D2-D4 freeze on the post-melt+homog/re-sloped state → working. (homog has
    // zeroed qc in supcol>40 cells, so D2/D3 are inactive there — Fortran-exact.)
    auto mf_d234 = melt_freeze_d2_d4(
        working1b, forcing, pre_mf_view(pre1),
        aux1.n0c, aux1.n0r, pre1.rslopec, aux1.rslopecmu, aux1.rslopecd,
        mf_params, dtcld);
    auto working = apply_melt_freeze_inline(
        working1b, mf_d234, pre_core, dtcld, full_params.thermo.xls);

    // 4. rebuild on the post-freeze state (re-slope :1596-1683; the prior STEP-2
    // rebuild). qcr carried; entry `pre` supplies the substep-top thermo (qs/xl/rh/
    // supsat) Fortran does NOT recompute post-freeze (:835-836,:910-928).
    auto rebuilt = rebuild_aux(working, /*entry_pre=*/pre, forcing, full_params, aux.qcr, ncmin_for_slope);
    const auto& pre2 = rebuilt.pre;
    auto aux2 = rebuilt.aux;   // mutable: n0c recomputed from the snapped nc below
    // SEED#2 (post-freeze re-slope, Fortran module_mp_kdm6.F:1638-1651): same cloud
    // lamda-snap back-mutation, here BEFORE the warm rate loop. The rewritten
    // prognostic nci(1) is what warm praut/nraut (F:1706-1716) AND — decisively —
    // the CCN activation ncact (F:2905, reads nci1 twice) AND state_update consume.
    // This is the frame-3 QNCLOUD seed: at onset Fortran feeds activation the reduced
    // snapped nc; the C++ previously fed the raw larger nc. Gate qc≥qmin & nc≥ncmin
    // (F:1638, supcol-independent ⇒ fires for warm onset cells). autograd-safe.
    auto nc_orig2 = working.nc;
    auto nc_snap2 = limit_number_for_lamda(
        working.qc, nc_orig2, forcing.den,
        pidnc_snap, constants::DMC, constants::LAMDACMIN, constants::LAMDACMAX,
        constants::EPS, constants::NCMIN);
    // Per-cell ncmin gate (Fortran F:1638, ncmin_sea/land=10/100), not scalar NCMIN.
    working.nc = ncmin_for_slope.has_value()
        ? torch::where(nc_orig2 >= *ncmin_for_slope, nc_snap2, nc_orig2)
        : nc_snap2;
    // n0c CONSISTENT with the snapped nc (Fortran F:1640-1649) — cold_phase riming
    // (nsacw/ngacw/niacw) reads aux2.n0c. Rebuild from the snap's lamda (active cells),
    // NOT rslopec (boundary mismatch at nci==ncmin — Codex stop-review). See post-melt block.
    {
        auto active = (working.qc >= constants::EPS) &
            (ncmin_for_slope.has_value() ? (nc_orig2 >= *ncmin_for_slope)
                                         : (nc_orig2 >= constants::NCMIN));
        auto lamdc = torch::clamp(
            ops::libm_exp(ops::libm_log(torch::clamp(pidnc_snap * nc_orig2 /
                torch::clamp(working.qc * forcing.den, 1.0e-30), 1.0e-30)) * INV_DMC_F32),
            constants::LAMDACMIN, constants::LAMDACMAX);
        // f64 lamdc-form intercept — same as the post-melt block (Fortran F:1641/
        // 1645/1649, n0c DOUBLE F:697); cold riming (nsacw/ngacw/niacw) promotes
        // against it and rounds f32 at its rate stores.
        auto n0c_active = (constants::MUC + 1.0) * working.nc.to(torch::kFloat64) *
            ops::safe_pow(lamdc, constants::MUC + 1.0);
        aux2.n0c = torch::where(active, n0c_active, aux2.n0c);
    }

    // STEP-79 SEED (block-B ice P3, F:1684-1697) — same rewrite as the block-A
    // site above; see that comment. pre2/avedia_i keep the PRE-rewrite ni
    // (slope_kdm6 F:1624 precedes the F:1684 rewrite).
    {
        auto ni_orig2 = working.ni;
        working.ni = limit_number_for_lamda(
            working.qi, ni_orig2, forcing.den,
            fconst::get().pidni, constants::DMI,
            constants::LAMDAIMIN, constants::LAMDAIMAX,
            /*q_thresh=*/1.0e-14, /*n_thresh=*/0.0);
        const double INV_DMI_F32 = static_cast<double>(1.0f / static_cast<float>(constants::DMI));
        auto lamdi2 = torch::clamp(
            ops::libm_exp(ops::libm_log(torch::clamp(fconst::get().pidni * ni_orig2 /
                torch::clamp(working.qi * forcing.den, 1.0e-30), 1.0e-30)) * INV_DMI_F32),
            constants::LAMDAIMIN, constants::LAMDAIMAX);
        aux2.n0i = torch::where(working.qi >= 1.0e-14,
            working.ni.to(torch::kFloat64) * lamdi2.to(torch::kFloat64), aux2.n0i);
    }

    // F1b: warm phase (B1-B5) on the WORKING state + rebuilt pre2/aux2. thermo_params
    // lets the sequential pcact path recompute qs1 before satadj (module_mp_kdm6.F:2903-2943).
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
    // Fortran's combined budget+mass-balance loop (:2449-2756, gate `t.le.t0c`).
    // D1-D4 are already committed to `working`, and scale_rates only touches the
    // D5 fields (pseml/pgeml/nseml/ngeml), so passing mf5 is sufficient.
    auto scaled = scale_rates_for_conservation(
        working, pre2.supcol, warm_out, cold_out, mf5, dtcld,
        // per-cell ncmin floor for the cloud/ice NUMBER budgets (1:1 fix #18); same
        // xland-derived tensor runtime.cpp injects into the rate-gate params.
        cold_params.cloud_water_riming.ncmin_tensor
    );

    // F1e: state update on the WORKING base. HYBRID pre_core (Fortran-exact):
    //   xl/cpm  = ENTRY  (module_mp_kdm6.F:835-836 set once, reused through mass balance),
    //   supcol  = POST-FREEZE (mass-balance arm gates on t.le.t0c, :2456),
    //   rhox    = POST-FREEZE (re-sloped before the rate loop; brs terms :2643/2734).
    // delta_src = nullptr ⇒ delta2/delta3 track working qr/qs (Fortran :2452-2455
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
    // state. Mirrors Fortran module_mp_kdm6.F:2903-2943 sequence. The
    // earlier `state_update` deliberately omitted pcact/pcond/ncact_activation/
    // cloud_complete_evap from its budgets so this step can run on the proper
    // post-mass-balance + post-reclass state — fixing the frame-6+ cascade
    // (Codex stop-gate finding 8: satadj was applied to stale pre-mass-balance
    // state in C++, while Fortran runs it at line 2929 AFTER reclass at 2883).
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
    // Fortran: max(nint(delt/dtcldcr), 1).  For positive delt,
    // (int)(delt/dtcldcr + 0.5) == nint(delt/dtcldcr) (round-half-up).
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

    // Fortran module_mp_kdm6.F:801 entry-prologue clamp on nci(:,:,3).
    // Mirror it here so warm-phase ncact (coordinator.cpp:264-270) consumes the clamped
    // value, matching slot-37 behaviour. Post-rate clamp at line 791 is kept as the
    // surrogate for Fortran :2952 / :3006.
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

// Stage-A STEP 2/STEP 3 split. Fortran module_mp_kdm6.F runs, in order: D1 melt
// (:1274-1345) → [homog freeze :1410-1420] → re-slope (:1422-1480) → D2-D4 Bigg/
// contact freeze (:1485-1561) → re-slope → warm/cold rate loop. So the melt/freeze
// phase is split THREE ways: melt_freeze_d1 (D1 melt; warm cells), melt_freeze_d2_d4
// (D2 contact + D3 Bigg-cloud + D4 Bigg-rain; cold cells, computed on the POST-MELT/
// re-sloped state), and melt_freeze_d5 (enhanced melt; needs cold_out). This lets
// kdm62d_one_step apply D1 → rebuild_aux → D2-D4 → rebuild_aux → warm/cold, exactly
// mirroring Fortran's per-stage re-slope. melt_freeze_d1_d4 (combiner) + melt_freeze_phase
// recompose them so the legacy single-call signature (+ its tests) stay bit-identical.
MeltFreezePhaseOutputs melt_freeze_d1(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const PreambleMf& pre,
    const torch::Tensor& n0so,
    const torch::Tensor& n0go,
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
        pre.work2, pre.precg2,
        s.rslope_s, s.rslope2_s, s.rslopeb_s, s.rslopemu_s,
        s.rslope_g, s.rslope2_g, s.rslopeb_g, s.rslopemu_g,
    };
    auto d1 = melt::melting_torch(d1_in, params.melting, dtcld);
    return MeltFreezePhaseOutputs{
        /*psmlt=*/d1.psmlt, /*pgmlt=*/d1.pgmlt,
        /*pimlt_qi=*/d1.pimlt_qi, /*pimlt_ni=*/d1.pimlt_ni,
        /*sfac_melt=*/d1.sfac, /*gfac_melt=*/d1.gfac,
        /*delta_brs_melt=*/d1.delta_brs,
        /*pinuc=*/zero, /*ninuc=*/zero,                // D2 → melt_freeze_d2_d4
        /*pfrzdtc=*/zero, /*nfrzdtc=*/zero,            // D3
        /*pfrzdtr=*/zero, /*nfrzdtr=*/zero, /*delta_brs_freeze=*/zero,  // D4
        /*pseml=*/zero, /*nseml=*/zero, /*pgeml=*/zero, /*ngeml=*/zero, // D5
    };
}

MeltFreezePhaseOutputs melt_freeze_d2_d4(
    const CoordinatorState& state,
    const CoordinatorForcing& forcing,
    const PreambleMf& pre,
    const torch::Tensor& n0c,
    const torch::Tensor& n0r,
    const torch::Tensor& rslopec,
    const torch::Tensor& rslopecmu,
    const torch::Tensor& rslopecd,
    const MeltFreezePhaseParams& params,
    double dtcld
) {
    const auto& s = pre.slope;
    auto zero = torch::zeros_like(state.qc);
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

    // D3: Bigg cloud freezing (cold cells). STEP 4: caps against the POST-D2 cloud
    // reservoir — Fortran subtracts pinuc/ninuc (:1533/:1536) BEFORE :1545/:1557 cap
    // pfrzdtc/nfrzdtc. n0c is the SAME single re-sloped intercept across D2+D3.
    // pinuc/ninuc are f64 (Fortran DOUBLE, F:738); the Fortran qci/nci stores round
    // to REAL(4), so D3 must read the f32-stored value qc1 = f32(DBLE(qc) - pinuc)
    // (no-op .to on the fp64 oracle path).
    auto qc_post_d2 = (state.qc - d2.pinuc).to(state.qc.scalar_type());
    auto nc_post_d2 = (state.nc - d2.ninuc).to(state.nc.scalar_type());
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
        /*psmlt=*/zero, /*pgmlt=*/zero,                // D1 → melt_freeze_d1
        /*pimlt_qi=*/zero, /*pimlt_ni=*/zero,
        /*sfac_melt=*/zero, /*gfac_melt=*/zero, /*delta_brs_melt=*/zero,
        /*pinuc=*/d2.pinuc, /*ninuc=*/d2.ninuc,
        /*pfrzdtc=*/d3.pfrzdtc, /*nfrzdtc=*/d3.nfrzdtc,
        /*pfrzdtr=*/d4.pfrzdtr, /*nfrzdtr=*/d4.nfrzdtr,
        /*delta_brs_freeze=*/d4.delta_brs,
        /*pseml=*/zero, /*nseml=*/zero, /*pgeml=*/zero, /*ngeml=*/zero, // D5
    };
}

// Combiner — legacy D1-D4-from-one-state output (D5 zeroed). Bit-identical to the
// pre-split melt_freeze_d1_d4; used by melt_freeze_phase + the STEP-2 entry path.
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
    auto out  = melt_freeze_d1(state, forcing, pre, n0so, n0go, params, dtcld);
    auto d234 = melt_freeze_d2_d4(state, forcing, pre, n0c, n0r, rslopec, rslopecmu, rslopecd, params, dtcld);
    out.pinuc = d234.pinuc; out.ninuc = d234.ninuc;
    out.pfrzdtc = d234.pfrzdtc; out.nfrzdtc = d234.nfrzdtc;
    out.pfrzdtr = d234.pfrzdtr; out.nfrzdtr = d234.nfrzdtr;
    out.delta_brs_freeze = d234.delta_brs_freeze;
    return out;
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

// ─── F1d2: group conservation limiters (Fortran module_mp_kdm6.F) ─────────
//
// Ports the 14 Fortran group budgets: 8 cold-arm (t<=t0c, :2460-2597) + 6
// warm-arm (t>t0c, :2657-2728), the two branches of one per-cell conditional.
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
    double dtcld,
    const c10::optional<torch::Tensor>& ncmin_tensor
) {
    auto dtype = state.qc.dtype();
    auto cold_gate = (supcol >= 0);                 // Fortran F:2456 `t.le.t0c` ⇔ supcol>=0; == state_update cold_mask
    auto warm_gate = (supcol < 0);                  // complement (warm arm, Fortran t>t0c); supcol==0 is a no-op (cold rates strict-gated)

    // delta2/delta3 from PRE-update reservoirs (Fortran :2452-2455; identical to
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

    // Per-cell ncmin floor variant for the cloud/ice NUMBER budgets — Fortran
    // F:2554/2568/2706 max(ncmin,nci) with ncmin=10(sea)/100(land), NOT the
    // hardcoded 0.01. nullopt → scalar constants::NCMIN fallback. 1:1 fix #18.
    auto limit_ncmin = [&](const torch::Tensor& reservoir,
                           const torch::Tensor& source_sum, const torch::Tensor& gate,
                           std::initializer_list<torch::Tensor*> rates) {
        auto value = ncmin_tensor.has_value()
            ? torch::maximum(reservoir, ncmin_tensor.value())
            : torch::clamp(reservoir, constants::NCMIN);
        auto source = source_sum * dtcld;
        auto factor_raw = value / torch::maximum(source, value);
        auto factor = torch::where(gate, factor_raw, torch::ones_like(value));
        for (auto* r : rates) { *r = *r * factor; }
    };

    // ── PASS 1: cold arm (t<=t0c), gate=cold_gate ──────────────────────────
    // cloud mass (:2460): praut+pracw+2·paacw+piacw+pmulcs+pmulcg
    limit(state.qc, constants::EPS,
          warm.praut + warm.pracw + 2.0 * cold.paacw_adj + cold.piacw
              + cold.pmulcs + cold.pmulcg,
          cold_gate,
          {&warm.praut, &warm.pracw, &cold.paacw_adj, &cold.piacw,
           &cold.pmulcs, &cold.pmulcg});
    // ice mass (:2475): psaut-pinud-pidep+praci+psaci+pgaci-pmulcs-pmulrs-pmulcg-pmulrg-piacw
    limit(state.qi, constants::EPS,
          cold.psaut - cold.pinud - cold.pidep + cold.praci + cold.psaci
              + cold.pgaci - cold.pmulcs - cold.pmulrs - cold.pmulcg
              - cold.pmulrg - cold.piacw,
          cold_gate,
          {&cold.psaut, &cold.pinud, &cold.pidep, &cold.praci, &cold.psaci,
           &cold.pgaci, &cold.piacw, &cold.pmulcs, &cold.pmulrs, &cold.pmulcg,
           &cold.pmulrg});
    // rain mass (:2495): -praut-prevp-pracw+piacr+psacr+pgacr+pmulrs+pmulrg
    limit(state.qr, constants::EPS,
          -warm.praut - warm.prevp - warm.pracw + cold.piacr + cold.psacr_adj
              + cold.pgacr_adj + cold.pmulrs + cold.pmulrg,
          cold_gate,
          {&warm.praut, &warm.prevp, &warm.pracw, &cold.piacr, &cold.psacr_adj,
           &cold.pgacr_adj, &cold.pmulrs, &cold.pmulrg});
    // snow mass (:2512): -(psdep+psaut+paacw+piacr·d3+praci·d3-pracs·(1-d2)+psacr·d2+psaci)
    //   (pgaut, pgacs ≡ 0 dropped)
    limit(state.qs, constants::EPS,
          -(cold.psdep + cold.psaut + cold.paacw_adj
            + cold.piacr * delta3 + cold.praci * delta3
            - cold.pracs * one_m_d2 + cold.psacr_adj * delta2 + cold.psaci),
          cold_gate,
          {&cold.psdep, &cold.psaut, &cold.paacw_adj, &cold.piacr, &cold.praci,
           &cold.psaci, &cold.pracs, &cold.psacr_adj});
    // graupel mass (:2533): -(pgdep+piacr·(1-d3)+praci·(1-d3)+psacr·(1-d2)+pracs·(1-d2)+pgaci+paacw+pgacr)
    //   (pgaut, pgacs ≡ 0 dropped)
    limit(state.qg, constants::EPS,
          -(cold.pgdep + cold.piacr * one_m_d3 + cold.praci * one_m_d3
            + cold.psacr_adj * one_m_d2 + cold.pracs * one_m_d2 + cold.pgaci
            + cold.paacw_adj + cold.pgacr_adj),
          cold_gate,
          {&cold.pgdep, &cold.piacr, &cold.praci, &cold.psacr_adj, &cold.pracs,
           &cold.paacw_adj, &cold.pgaci, &cold.pgacr_adj});
    // cloud number (:2554): nraut+nccol+nracw+niacw+2·naacw
    limit_ncmin(state.nc,
          warm.nraut + warm.nccol + warm.nracw + cold.niacw + 2.0 * cold.naacw,
          cold_gate,
          {&warm.nraut, &warm.nccol, &warm.nracw, &cold.naacw, &cold.niacw});
    // ice number (:2568): nraci+nsaci+ngaci+niacr+nsaut-nmulcs-nmulcg-nmulrs-nmulrg-ninud
    limit_ncmin(state.ni,
          cold.nraci + cold.nsaci + cold.ngaci + cold.niacr + cold.nsaut
              - cold.nmulcs - cold.nmulcg - cold.nmulrs - cold.nmulrg
              - cold.ninud,
          cold_gate,
          {&cold.nraci, &cold.nsaci, &cold.ngaci, &cold.niacr, &cold.nsaut,
           &cold.ninud, &cold.nmulcs, &cold.nmulcg, &cold.nmulrs, &cold.nmulrg});
    // rain number (:2587): -nraut+nraci+nrcol+niacr+nsacr+ngacr
    limit(state.nr, constants::NRMIN,
          -warm.nraut + cold.nraci + warm.nrcol + cold.niacr + cold.nsacr
              + cold.ngacr,
          cold_gate,
          {&cold.nraci, &warm.nraut, &warm.nrcol, &cold.niacr, &cold.nsacr,
           &cold.ngacr});

    // ── PASS 2: warm arm (t>t0c), gate=warm_gate ───────────────────────────
    // cloud mass (:2657): praut+pracw+2·paacw
    limit(state.qc, constants::EPS,
          warm.praut + warm.pracw + 2.0 * cold.paacw_adj,
          warm_gate,
          {&warm.praut, &warm.pracw, &cold.paacw_adj});
    // rain mass (:2669): -2·paacw-praut+pseml+pgeml-pracw-prevp
    limit(state.qr, constants::EPS,
          -2.0 * cold.paacw_adj - warm.praut + mf.pseml + mf.pgeml
              - warm.pracw - warm.prevp,
          warm_gate,
          {&warm.praut, &warm.prevp, &warm.pracw, &cold.paacw_adj,
           &mf.pseml, &mf.pgeml});
    // snow mass (:2684, floor=qcrmin): -pseml-psevp   (pgacs ≡ 0 dropped)
    limit(state.qs, constants::QCRMIN,
          -mf.pseml - cold.psevp,
          warm_gate,
          {&cold.psevp, &mf.pseml});
    // graupel mass (:2695, floor=qcrmin): -(pgevp+pgeml)   (pgacs ≡ 0 dropped)
    limit(state.qg, constants::QCRMIN,
          -(cold.pgevp + mf.pgeml),
          warm_gate,
          {&cold.pgevp, &mf.pgeml});
    // cloud number (:2706): nraut+nccol+nracw+2·naacw
    limit_ncmin(state.nc,
          warm.nraut + warm.nccol + warm.nracw + 2.0 * cold.naacw,
          warm_gate,
          {&warm.nraut, &warm.nccol, &warm.nracw, &cold.naacw});
    // rain number (:2719): -nraut+nrcol-nseml-ngeml
    limit(state.nr, constants::NRMIN,
          -warm.nraut + warm.nrcol - mf.nseml - mf.ngeml,
          warm_gate,
          {&warm.nraut, &warm.nrcol, &mf.nseml, &mf.ngeml});

    return ConservedRates{/*warm=*/warm, /*cold=*/cold, /*mf=*/mf};
}

// ─── F1e: state mutation update (Fortran 2730-2873) ────────────────────────
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
    auto cold_mask = (pre.supcol >= 0).to(dtype);  // Fortran F:2456 `t.le.t0c` ⇔ supcol>=0
    auto warm_mask = 1.0 - cold_mask;              // = supcol<0 (Fortran t>t0c)
    // Stage-A STEP 1: delta2/delta3 are computed from the ENTRY state when the
    // base `state` is a post-melt/freeze working state (delta_src!=null). This
    // preserves the identity (melt/freeze must not flip the qr/qs<1e-4 routing
    // gates in the behaviour-preserving STEP 1). STEP 2 will pass null so delta
    // tracks the working state (Fortran computes it on the mutated state :2452-2455).
    const CoordinatorState& dstate = delta_src ? *delta_src : state;

    // dtcld as a tensor for addcmul (single-rounding FMA == gfortran's fused
    // `state + sum*dtcld` in `max(state+(...)*dtcld, 0.)`, F:2616-2755). The Fortran
    // budget statements compute the whole rate sum, multiply by dtcld, then add the
    // reservoir — gfortran -ffp-contract=fast fuses that LAST multiply with the add.
    auto dt_t = torch::full_like(state.qc, dtcld);

    // ── Mass balance ────────────────────────────────────────────────────────
    // qv — pcact/pcond DEFERRED to apply_satadj_step (called after state_update
    // + reclassifications in kdm62d_one_step), mirroring Fortran module_mp_kdm6.F:
    // mass balance at :2599-2755 runs FIRST, then reclass (Picons ice→snow
    // :2807-2813, rain→cloud :2883-2892), THEN pcact apply at :2903-2915, THEN
    // satadj/pcond at :2922-2943.
    // Per-cell warm/cold/mf rates are applied here; activation + condensation
    // run on the post-state-update + post-reclass state for proper Fortran
    // sequence parity (Codex stop-gate finding 8 - frame-6+ cascade origin).
    auto dqv_sum = (
        - warm.prevp
        - cold.pinud
        - cold.pidep - cold.psdep - cold.pgdep
        - cold.psevp
        - cold.pgevp
    );
    // Fortran F:2737 `q = q + work2*dtcld` (cold arm :2599 likewise) ⇒ fuse sum*dtcld+qv.
    auto qv_new = ops::fma_acc(state.qv, dqv_sum, dt_t);

    // qc — pcact/pcond also deferred (see dqv comment). Warm-phase qc sinks
    // (autoconv, accretion, etc.) and cold/mf amount-transfers stay here.
    auto dqc_rate_sum = (
        - warm.praut - warm.pracw
        - cold.piacw
        - 2.0 * cold.paacw_adj
        - cold.pmulcs - cold.pmulcg
    );
    // amount terms = inline D1-D4 transfers (Fortran applies them as separate adds
    // at :1504/1534 etc. — no dtcld, not fused). The rate sum*dtcld fuses with the
    // reservoir (F:2616/2738 `max(qci(1)+(...)*dtcld,0)`).
    // STEP-67 NOTE: this component path keeps the SUMMED amount form. At runtime it
    // is SHIELDED — kdm62d_one_step applies D1-D4 via apply_melt_freeze_inline
    // (which carries the Fortran f64-rate SEQUENTIAL store semantics for D2/D3)
    // and passes a D1-D4-zeroed mf here, so these amount terms are exact zeros.
    // The summed form stays only for the component/test path (exercised at f64,
    // where summed vs sequential is parity-invisible — see the Python identity guard).
    auto dqc_amount = -mf.pinuc - mf.pfrzdtc + mf.pimlt_qi;
    auto qc_new = ops::fma_acc(state.qc + dqc_amount, dqc_rate_sum, dt_t);

    // qr — cold 2621 / warm 2740 (rate) + inline D4 amount + D1/D5 melt
    auto dqr_rate_sum = (
        warm.praut + warm.pracw
        + warm.prevp
        - cold.piacr - cold.pgacr_adj - cold.psacr_adj
        - cold.pmulrs - cold.pmulrg
        - (mf.psmlt + mf.pgmlt) * warm_mask
        - mf.pseml - mf.pgeml
        // #1 (audit): WARM arm sheds rimed cloud to RAIN (Fortran :2740 qr+=2*paacw);
        // cold arm routes paacw to qs/qg instead (handled below, cold_mask). Was
        // missing in both ports — warm cells wrongly grew ice. (WRF-validated.)
        + 2.0 * cold.paacw_adj * warm_mask
    );
    // dqr_amount = inline D4 freeze (Fortran :1560 separate add). rate sum*dtcld fuses
    // with reservoir (F:2621/2740).
    auto dqr_amount = -mf.pfrzdtr;
    auto qr_new = ops::fma_acc(state.qr + dqr_amount, dqr_rate_sum, dt_t);

    // delta2/delta3 routing flags (Fortran 2452-2455) — from ENTRY state (dstate)
    auto delta2 = ((dstate.qr < 1.0e-4) & (dstate.qs < 1.0e-4)).to(dtype);
    auto delta3 = (dstate.qr < 1.0e-4).to(dtype);
    auto one_m_d2 = 1.0 - delta2;
    auto one_m_d3 = 1.0 - delta3;

    // qs — 2633 + warm-branch 2743. rate sum*dtcld fuses with reservoir.
    auto dqs_sum = (
        cold.psdep
        + cold.psaut
        + cold.paacw_adj * cold_mask          // #1: paacw→qs only in COLD arm (Fortran :2633); warm arm sheds to qr
        + cold.piacr * delta3
        + cold.praci * delta3
        + cold.psacr_adj * delta2
        + cold.psaci
        - cold.pracs * one_m_d2
        + cold.psevp
        + mf.psmlt
        + mf.pseml
    );
    auto qs_new = ops::fma_acc(state.qs, dqs_sum, dt_t);

    // qg — 2638 + warm-branch 2745. rate sum*dtcld fuses with reservoir.
    auto dqg_rate_sum = (
        cold.pgdep
        + cold.paacw_adj * cold_mask          // #1: paacw→qg only in COLD arm (Fortran :2641); warm arm sheds to qr
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
    // dqg_amount = inline D4 freeze (Fortran :1557 separate add).
    auto dqg_amount = mf.pfrzdtr;
    auto qg_new = ops::fma_acc(state.qg + dqg_amount, dqg_rate_sum, dt_t);

    // qi — 2626 + inline freeze amounts (D2-D4/homog). rate sum*dtcld fuses w/ reservoir.
    auto dqi_rate_sum = (
        cold.pinud + cold.pidep
        + cold.piacw
        - cold.praci - cold.psaci - cold.pgaci
        - cold.psaut
        + cold.pmulcs + cold.pmulrs
        + cold.pmulcg + cold.pmulrg
    );
    auto dqi_amount = mf.pinuc + mf.pfrzdtc - mf.pimlt_qi;
    auto qi_new = ops::fma_acc(state.qi + dqi_amount, dqi_rate_sum, dt_t);

    // ── Number balance ──────────────────────────────────────────────────────
    // nci(1) budget F:2619/2747 `max(nci(1)+(...)*dtcld,0)` ⇒ fuse rate sum*dtcld+reservoir.
    auto dnc_rate_sum = (
        - warm.nraut
        - warm.nccol
        - warm.nracw
        - cold.niacw
        - 2.0 * cold.naacw
    );
    auto dnc_amount = -mf.ninuc - mf.nfrzdtc + mf.pimlt_ni;
    // ncact (activation) and cloud_complete_evap deferred to apply_satadj_step
    // — they fire on the post-state-update + post-reclass state per Fortran
    // sequence (module_mp_kdm6.F:2937-2977). The mass balance here only
    // accounts for warm/cold/mf rates that Fortran applies BEFORE that block.
    auto nc_new = ops::fma_acc(state.nc + dnc_amount, dnc_rate_sum, dt_t);

    // nrs(1) budget F:2624/2749 `max(nrs(1)+(...)*dtcld,0)` ⇒ fuse rate sum*dtcld+reservoir.
    auto dnr_rate_sum = (
        warm.nraut
        - warm.nrcol
        - cold.niacr - cold.nraci
        - cold.nsacr - cold.ngacr
        // Fortran module_mp_kdm6.F:2749-2750 — enhanced-melt number sources to rain.
        // Previously omitted in C++; Codex review caught the gap.
        + mf.nseml + mf.ngeml
        // Fortran module_mp_kdm6.F:1299/1323 — D1 melt of snow/graupel → rain number.
        // (D1-zeroed in mf5 at runtime, preserves inline↔state_update identity; Codex review.)
        - mf.sfac_melt * mf.psmlt - mf.gfac_melt * mf.pgmlt
    );
    auto dnr_amount = -mf.nfrzdtr;
    // rce is a SEPARATE Fortran statement (F:1795 rain-number zeroing), not part of the
    // budget multiply — kept as its own subtract, not fused into the dtcld FMA.
    auto rain_complete_evap_amount = state.nr * warm.rain_complete_evap.to(dtype);
    auto nr_new = ops::fma_acc(
        state.nr + dnr_amount - rain_complete_evap_amount, dnr_rate_sum, dt_t);

    // nci(2) budget F:2630 `max(nci(2)+(...)*dtcld,0)` ⇒ fuse rate sum*dtcld+reservoir.
    auto dni_rate_sum = (
        cold.ninud
        - cold.nraci - cold.nsaci - cold.ngaci
        - cold.niacr
        + cold.nmulcs + cold.nmulcg
        + cold.nmulrs + cold.nmulrg
        - cold.nsaut
    );
    auto dni_amount = mf.ninuc + mf.nfrzdtc - mf.pimlt_ni;
    auto ni_new_pre = ops::fma_acc(state.ni + dni_amount, dni_rate_sum, dt_t);
    // complete sublimation mask → ni=0
    auto ni_zero_mask = cold.ice_complete_sublim.to(dtype);
    auto ni_new = ni_new_pre * (1.0 - ni_zero_mask);

    // ── brs (graupel volume) — Fortran 2643 + warm-branch 2751 ─────────
    // Each Fortran branch is `brs = max(brs + (Σb)*dtcld, 0)` — the (Σb)*dtcld multiply
    // fuses with the add. The port tensorizes the two branches with cold_mask/warm_mask
    // scales; fuse each `(mask·Σb)·dtcld` and the `delta_brs_melt·dtcld` into the running
    // sum via addcmul (one rounding per fused multiply). delta_brs_freeze is an inline
    // amount (separate add, no multiply).
    auto rhox_safe = torch::clamp(pre.rhox, /*min=*/constants::DENS);
    auto dbrs_cold_sum = cold_mask * (
        cold.pgdep / rhox_safe
        + cold.piacr / constants::DENR        // biacr
        + cold.praci / constants::DENI        // braci
        + cold.psacr_adj / constants::DENR    // bsacr
        + cold.pracs / constants::DENS        // bracs
        + cold.pgaci / constants::DENI        // bgaci
        + cold.paacw_adj / constants::DENR    // baacw
        + cold.pgacr_adj / constants::DENR    // bgacr
    );
    auto dbrs_warm_sum = warm_mask * (
        cold.pgevp / rhox_safe
        + mf.pgeml / rhox_safe
    );
    // brs + delta_brs_freeze + (delta_brs_melt + dbrs_cold_sum + dbrs_warm_sum)*dtcld,
    // accumulating each *dtcld as a fused addcmul.
    auto brs_acc = state.brs + mf.delta_brs_freeze;
    brs_acc = ops::fma_acc(brs_acc, mf.delta_brs_melt, dt_t);
    brs_acc = ops::fma_acc(brs_acc, dbrs_cold_sum, dt_t);
    brs_acc = ops::fma_acc(brs_acc, dbrs_warm_sum, dt_t);
    auto brs_new = torch::clamp(brs_acc, /*min=*/0.0);

    // ── Energy balance (T) — review3#4 / review4#4 / review5#1 ──────────────
    auto cpm_safe = torch::clamp(pre.cpm, /*min=*/constants::QCRMIN);
    // Fortran module_mp_kdm6.F:2646 — `xls` is the CONSTANT latent heat of
    // sublimation (XLS=2.85e6, passed in); the fusion latent heat is DERIVED and
    // TEMPERATURE-DEPENDENT: xlf(T) = xls - xl(T). The previous code INVERTED this
    // (constant xlf, derived xls), which over-heated freezing by up to ~56% at
    // cold (T≪0) updraft cores (where xl(T) grows, so the true xlf shrinks while
    // the constant did not) — the systematic ice-phase over-intensification that
    // made mp=137 produce ~90× more condensate than mp=37 in supercell ice
    // regions. Deposition correctly uses the constant `xls`; freezing uses xlf(T).
    auto xlf = xls - pre.xl;
    // D1 MELT (psmlt/pgmlt/pimlt_qi) uses the CONSTANT xlf0, NOT xls-xl(T): Fortran F:1275
    // `if(supcol<0) xlf=xlf0` applied at F:1303/1327/1339. Mirrors apply_melt_freeze_inline
    // (audit round-6); the single-xlf form over-cooled the D1-melt heat in the component
    // state_update path (Codex round-2). Runtime-shielded (mf5 zeroes D1) so parity-inert;
    // restores the inline<->state_update identity. D5 pseml/pgeml stay on xls-xl (F:2752);
    // cold riming on xls-xl (F:2645).
    const double xlf_melt = melt::DEFAULT_XLF;

    // pcact + pcond warming terms DEFERRED — apply_satadj_step adds them to
    // T after running on the post-state-update state (matches Fortran sequence
    // at module_mp_kdm6.F:2914 + :2943).
    auto dT_warm_phase = dtcld * pre.xl / cpm_safe * (
        warm.prevp + cold.psevp + cold.pgevp
    );
    auto dT_dep_phase = dtcld * xls / cpm_safe * (
        cold.pinud + cold.pidep + cold.psdep + cold.pgdep
    );
    // D1 melt (psmlt/pgmlt rate + pimlt_qi amount) → CONSTANT xlf0 (Fortran F:1303/1327/1339).
    // SEED#5: psmlt and pgmlt are two SEQUENTIAL summands (F:1303 then :1327), NOT
    // summed before the coefficient — split identically to apply_melt_freeze_inline
    // (the inline↔state_update identity guard requires the same grouping in both).
    auto coef_melt = dtcld * xlf_melt / cpm_safe;
    auto dT_melt_d1 = coef_melt * mf.psmlt + coef_melt * mf.pgmlt
                    - xlf_melt / cpm_safe * mf.pimlt_qi;
    auto dT_freeze_rate = dtcld * xlf / cpm_safe * (
        mf.pseml + mf.pgeml                       // D5 enhanced melt (xls-xl, F:2752)
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
    );
    auto t_new = state.t + dT_warm_phase + dT_dep_phase + dT_melt_d1 + dT_freeze_rate + dT_freeze_amount;
    // nccn: only rain_complete_evap adds back here (warm.rain_complete_evap is a
    // B4 output, applied with the warm rates). cloud_complete_evap and
    // nccn_activation are part of the deferred satadj step (see dqv comment),
    // so they are NOT applied at this point — apply_satadj_step handles them
    // after the reclassifications, matching Fortran module_mp_kdm6.F:2937-2977.
    // The rce addback is RAW (Fortran F:1795 `nci(:,:,3)+=nrs`, no clamp). The
    // [NCCN_MIN,NCCN_MAX] reservoir clamp is NOT applied here — it is deferred to
    // apply_satadj_step (Fortran F:3006), AFTER CCN activation reads nccn. Clamping
    // here would make activation read a MAX-clamped nccn, understating ncact by ~9%
    // when accumulated rce pins nccn near NCCN_MAX — a C++↔Fortran/Python divergence
    // the Python oracle does not have (it reads raw nccn in activation, coordinator.py:1701).
    auto nccn_new = state.nccn + rain_complete_evap_amount;

    // review5#2 (partial): nonneg clamp on the moisture/number fields. paired threshold
    // cleanup은 분리. nccn deliberately NOT clamped here (see above; entry clamp + add-only
    // rce keep it ≥ NCCN_MIN; the MAX clamp is applied post-activation in apply_satadj_step).
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
        /*nccn=*/nccn_new,
        brs_new,
        t_new,
    };
}

// ─── F1g+: pcact + satadj on post-state-update + post-reclass state ────────
//
// Mirrors Fortran module_mp_kdm6.F:2903-2943 (the `do i = its, ite` block
// after mass balance and reclassifications). The earlier `state_update` step
// intentionally OMITS pcact/pcond/cloud_complete_evap/ncact_activation from
// its budgets — they all happen here on the post-mass-balance state for
// Fortran-sequence parity (frame-6+ cascade root cause per Codex review).
//
// Sequence:
//   1. Recompute supsat from new_state (forcing.p, state.t, state.qv)
//   2. Compute pcact + ncact (module_mp_kdm6.F:2905-2909)
//   3. Apply pcact   →  q -=pcact·dt, qc +=pcact·dt, t +=pcact·xl/cpm·dt
//   4. Apply ncact   →  nc +=ncact·dt, nccn -=ncact·dt           (module_mp_kdm6.F:2912-2913)
//   5. Recompute qs1 from post-pcact t                            (module_mp_kdm6.F:2922-2926)
//   6. Run satadj → pcond, cloud_complete_evap                    (module_mp_kdm6.F:2927-2931)
//   7. Complete-evap NC→NCCN transfer                             (module_mp_kdm6.F:2936-2939)
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

    // Step 2: pcact + ncact (Fortran module_mp_kdm6.F:2905-2909).
    // Fortran `sw` is PERCENT supersaturation: sw = (rh - 1) * 100 (module_mp_kdm6.F:918, 2848).
    // The 0.48 threshold is in PERCENT (matches SATMAX=1.0048 → 0.48% activation cutoff).
    // We must compute sw in percent here, NOT use raw `supsat = qv - qs1` (kg/kg).
    auto qs1_safe = torch::clamp(qs1, /*min=*/constants::QCRMIN);
    auto sw_percent = (state.qv / qs1_safe - 1.0) * 100.0;
    auto sw_ratio = torch::clamp(sw_percent / 0.48, /*min=*/0.0);
    // pow(x, ACTK<1) grad = 0.6·x^-0.4 → inf at x=0 (rh_w=1) ⇒ NaN gradient; clamp the base
    // ≥ EPS for a finite one-sided subgradient (forward unchanged where sw_ratio≫EPS; ncact
    // gated to 0 at supsat≤0). Mirrors the Python apply_satadj_step_torch fix.
    auto activated_fraction = torch::minimum(
        torch::ones_like(sw_ratio),
        ops::safe_pow(sw_ratio, constants::ACTK)  // libm pow (bit-matches gfortran on float32)
    );
    // Fortran F:2935-2936 `((nci3+nci1)*frac - nci1)`: gfortran contracts the
    // multiply-subtract to ONE rounding (fmsub). The plain mul-then-sub differs by
    // 1 ULP exactly at large-activation cells (step-48 seed: X 4EAFE27A vs ...7B).
    auto ncact_raw = torch::clamp(
        ops::fma_acc(-state.nc, state.nccn + state.nc, activated_fraction), /*min=*/0.0
    ) / dtcld;
    auto ncact = torch::minimum(ncact_raw, torch::clamp(state.nccn, /*min=*/0.0) / dtcld);
    ncact = torch::where(supsat > 0.0, ncact, torch::zeros_like(ncact));
    // SEED#3 (Fortran module_mp_kdm6.F:2908): the pcact mass constant
    //   K = 4.*pi*denr*(actr*1.E-6)**3
    // is evaluated by gfortran in REAL(4), left-to-right, with the cube as x*x*x
    // (float32 rounding at EACH step). Computing it in double (4.0*PI*DENR*
    // std::pow(ACTR*1e-6,3.0)) then demoting to float32 at the `*ncact` op rounds
    // differently — 1 ULP in K → up to 2 ULP in pcact (25/30 onset cells). Build K
    // with float32 stepwise rounding, held in a double that exactly represents the
    // float32 value, so the single scalar→f32 demotion reproduces gfortran bit-for-
    // bit (verified K=0x293f0123, pcact=0x30cc86ad, 0/30 cells differ). float32(PI)
    // == float32(4*atan(1)) (verified), so static_cast<float>(PI) matches Fortran's
    // pi=4.*atan(1.). NOT FMA-reachable (constant precision) ⇒ the prior sweep missed
    // it. Pure scalar constant × tensor ⇒ autograd-safe (grad flows through ncact/den).
    static const double PCACT_MASS_CONST = []() {
        const float ax  = static_cast<float>(constants::ACTR) * 1.0e-6f;
        const float ax3 = (ax * ax) * ax;                                  // float32 x*x*x (Fortran **3)
        const float pi_f = static_cast<float>(PI);                          // == float32(4*atan(1))
        const float k_f = ((4.0f * pi_f) * static_cast<float>(constants::DENR)) * ax3;
        return static_cast<double>(k_f);
    }();
    // Fortran groups K*ncact/(3.*den): keep `3.0*den` separate (already float32, 0 ULP).
    auto pcact_raw = PCACT_MASS_CONST * ncact / (3.0 * forcing.den);
    auto pcact = torch::minimum(pcact_raw, torch::clamp(state.qv, /*min=*/0.0) / dtcld);

    // Step 3 + 4: apply pcact + ncact to (q, qc, t, nc, nccn). Use addcmul (single-rounding FMA,
    // bit-matches gfortran's fused `state + rate*dtcld`) instead of separate mul+add (two roundings).
    auto dt_t = torch::full_like(pcact, dtcld);
    auto qv_pp   = torch::clamp(ops::fma_acc(state.qv,   pcact, dt_t, -1.0), /*min=*/0.0);
    auto qc_pp   = torch::clamp(ops::fma_acc(state.qc,   pcact, dt_t,  1.0), /*min=*/0.0);
    auto t_pp    = ops::fma_acc(state.t, pcact * xl / cpm_safe, dt_t, 1.0);
    auto nc_pp   = torch::clamp(ops::fma_acc(state.nc,   ncact, dt_t,  1.0), /*min=*/0.0);
    auto nccn_pp = torch::clamp(ops::fma_acc(state.nccn, ncact, dt_t, -1.0), /*min=*/0.0);

    // Step 5: recompute qs1 from t_pp (Fortran module_mp_kdm6.F:2922-2926).
    auto qs1_pp = thermo::compute_qs_water(t_pp, forcing.p, thermo_params);

    // Step 6: satadj on the post-pcact snapshot (Fortran :2927-2931).
    auto sat = satadj::saturation_adjustment_torch(
        t_pp, qv_pp, qc_pp, qs1_pp, xl, cpm_safe, satadj_params, dtcld
    );

    // Step 7: complete-evap NC → NCCN (Fortran :2936-2939).
    auto complete_evap_mask = sat.cloud_complete_evap.to(dtype);
    auto nc_evap_amount   = nc_pp * complete_evap_mask;
    auto nc_final         = torch::clamp(nc_pp - nc_evap_amount, /*min=*/0.0);
    auto nccn_final_raw   = nccn_pp + nc_evap_amount;

    // Step 8: apply pcond to (q, qc, t) — addcmul single-rounding FMA (matches gfortran).
    auto qv_final = torch::clamp(ops::fma_acc(qv_pp, sat.pcond, dt_t, -1.0), /*min=*/0.0);
    auto qc_final = torch::clamp(ops::fma_acc(qc_pp, sat.pcond, dt_t,  1.0), /*min=*/0.0);
    auto t_final  = ops::fma_acc(t_pp, sat.pcond * xl / cpm_safe, dt_t, 1.0);

    // Step 9: reservoir clamps (preserve NCCN_MIN/MAX band).
    auto nccn_final = torch::clamp(nccn_final_raw, constants::NCCN_MIN, constants::NCCN_MAX);

    return CoordinatorState{
        /*qv=*/qv_final,
        /*qc=*/qc_final,
        /*qr=*/state.qr,
        /*qs=*/state.qs,
        /*qg=*/state.qg,
        /*qi=*/state.qi,
        /*nc=*/nc_final,
        /*nr=*/state.nr,
        /*ni=*/state.ni,
        /*nccn=*/nccn_final,
        /*brs=*/state.brs,
        /*t=*/t_final,
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
    const double pidni = fconst::get().pidni;   // f32-stepwise (kdm6init F:3263)
    // Fortran F:2802 evaluates (g4pmi/g1pmi)**(.3333333) all-REAL(4) -> powf
    // (step-91 latent class; sits on the Picons 200um comparator).
    const double avedia_factor = static_cast<double>(
        std::pow(static_cast<float>(g4pmi / g1pmi), 0.3333333f));
    const double rslopeimax = 1.0 / constants::LAMDAIMAX;
    const double rslopeimin = 1.0 / constants::LAMDAIMIN;

    constexpr double eps = 1.0e-30;
    auto dtype = state.qc.dtype();

    auto ice_active = (state.qi > qmin) & (state.ni > 0.0) & (den > 0.0);
    auto qi_safe = torch::clamp(state.qi * den, /*min=*/eps);
    auto ratio = pidni * torch::clamp(state.ni, /*min=*/0.0) / qi_safe;
    // libm pow (float32 bit-matches gfortran). Base already clamped min=eps(1e-30);
    // safe_pow's inner min=EPS(1e-15) only raises the floor in cells the ice_active
    // `where` below discards, so the value is unchanged where it is consumed.
    auto lamdai = ops::libm_exp(ops::libm_log(torch::clamp(ratio, /*min=*/eps))
                                * static_cast<double>(1.0f / static_cast<float>(constants::DMI)));
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
    const double pidnr = fconst::get().pidnr;   // f32-stepwise (kdm6init F:3235)
    // Fortran F:2878 rain avedia factor all-REAL(4) -> powf (step-91 latent class;
    // sits on the 82um reclass comparator).
    const double avedia_factor = static_cast<double>(
        std::pow(static_cast<float>(g4pmr / g1pmr), 0.3333333f));
    const double rslopermax = 1.0 / constants::LAMDARMAX;

    constexpr double eps = 1.0e-30;
    auto dtype = state.qc.dtype();

    auto rain_active = (state.qr > qcrmin) & (state.nr > 0.0) & (den > 0.0);
    auto qr_safe = torch::clamp(state.qr * den, /*min=*/eps);
    auto ratio = pidnr * torch::clamp(state.nr, /*min=*/0.0) / qr_safe;
    // libm pow (float32 bit-matches gfortran). Base already clamped min=eps(1e-30);
    // safe_pow's inner min=EPS(1e-15) only raises the floor in cells the rain_active
    // `where` below discards, so the value is unchanged where it is consumed.
    auto lamdar = ops::libm_exp(ops::libm_log(torch::clamp(ratio, /*min=*/eps))
                                * static_cast<double>(1.0f / static_cast<float>(constants::DMR)));
    // Fortran F:3490 active rain slope = min(1/lamdar, 1e-3): UPPER cap (1e-3 literal) ONLY, NO
    // lower floor. The earlier min=rslopermax pinned avedia_r ≥ ~82.4μm > di82=82μm so the small-drop
    // NR→NC / QR→QC reclass (F:2879-2892) could NEVER fire — dead code vs Fortran. Inactive branch
    // keeps rslopermax (F:3483), matching the authoritative slope module slope.cpp:44-46. audit r3.
    auto rslope_r_raw = torch::minimum(
        1.0 / torch::clamp(lamdar, /*min=*/eps),
        torch::full_like(lamdar, 1.0e-3)
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
// Fortran `module_mp_kdm6.F:1409-1419` — at supcol > 40 (T < t0c-40 ≈ 233K),
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
// NOTE: CALLED by kdm62d_one_step at the D1-melt→re-slope boundary (call site is
// BETWEEN melt_freeze_d1 and the post-melt rebuild_aux). It was briefly disabled
// (it was the 806× stale-n0i over-deposition trigger when run before any aux
// rebuild); it is now safe because the rebuild_aux immediately after it re-slopes
// n0i on the post-homog ice state. It MUST stay before that rebuild_aux so the
// re-slope + D2-D4 + cold phase all see the post-homog qc (=0 in homog-frozen cells).
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
    // libm pow (float32 bit-matches gfortran). `ratio` already clamped min=eps(1e-30);
    // safe_pow's inner min=EPS(1e-15) only raises the floor in cells the `active` gate
    // (too_small/too_large) discards, so the consumed value is unchanged.
    // Fortran lamda = exp(log(ratio)*(1./dm)) — exp-log with the f32 reciprocal,
    // NOT powf (step-65 evaluation-form class).
    auto lamda = ops::libm_exp(ops::libm_log(ratio) * static_cast<double>(1.0f / static_cast<float>(dm)));
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
    const double pidnr = fconst::get().pidnr;   // f32-stepwise (kdm6init F:3235)
    // Cohard-Pinty modified gamma for cloud
    const double pidnc = fconst::get().pidnc;   // f32-stepwise (kdm6init F:3205)
    const double pidni = fconst::get().pidni;   // f32-stepwise (kdm6init F:3263)

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
    // snap is Fortran module_mp_kdm6.F:2995 `qci(i,k,2).ge.qmin .and. nci(i,k,2).ge.ncmin`
    // — same qmin/ncmin pattern as the cloud snap (:2984) just above. The prior
    // 1e-14/0 gate mis-cited :1467 (the INLINE rate-phase snap, a different
    // occurrence with no n-gate); the final-block gate ANDs with ncmin.
    // (Adjudicated vs Fortran 2026-05-31; aggregate effect pending WRF per the
    // parity-audit memory — this is a confirmed Fortran-alignment correction.)
    auto ni_new = limit_number_for_lamda(
        state.qi, state.ni, den,
        pidni, constants::DMI,
        constants::LAMDAIMIN, constants::LAMDAIMAX,
        /*q_thresh=*/qmin, /*n_thresh=*/constants::NCMIN
    );

    // Absolute caps (Fortran 3007-3014)
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
    const torch::Tensor& mstep_col_main,
    int mstepmax_main,
    const torch::Tensor& mstep_col_ice,
    int mstepmax_ice,
    double dtcld,
    const sed::SubstepAdvectionParams& params,
    const CoordinatorParams* reslope_params
) {
    const int64_t K = state.qr.size(-1);
    // delz floor matches runtime.cpp:291 (the initial work1 normalization).
    auto delz_safe = torch::clamp(forcing.delz, /*min=*/1.0e-9);

    // ── Rain/snow/graupel/brs substepping ───────────────────────────────────
    sed::SubstepAdvectionState adv_state{state.qr, state.nr, state.qs, state.qg, state.brs};
    auto fall_qr = torch::zeros_like(state.qr);
    auto fall_nr = torch::zeros_like(state.qr);
    auto fall_qs = torch::zeros_like(state.qr);
    auto fall_qg = torch::zeros_like(state.qr);
    auto fall_brs = torch::zeros_like(state.qr);

    // Mutable per-substep work1 (1:1 fix #9). Initialized to the caller's E1-normalized
    // values for substep n=1; re-derived from the post-substep state when reslope_params is set
    // (Fortran F:1189-1205 ProgB+slope_kdm6 re-call after EVERY main substep). w1_qi/wn_qi are
    // ALSO updated by the main re-slope: Fortran's slope_kdm6 writes work1(4)/workn(2) [ice]
    // each main substep, and the ice loop below consumes the post-main-loop value — the
    // main→ice HANDOFF (F:1194 → F:1215). Fortran's main loop normalizes only work1(1,2,3)/
    // workn(1) (F:1198-1205) and leaves work1(4)/workn(2) RAW. The port runs the same flow but
    // NORMALIZES the ice handoff /delz: the RAW value over-sediments ice (vt_i·dt≫1 ⇒ qi→0) and
    // the depletion clamp zeroes ∂/∂qi, which breaks test_autograd_endtoend — the differentiable-
    // port core goal. Deliberate AD-required deviation (cf. #6 cloud-rslopec); inert where QICE≈0.
    auto w1_qr = work1_qr, wn_qr = workn_qr, w1_qs = work1_qs, w1_qg = work1_qg;
    auto w1_qi = work1_qi, wn_qi = workn_qi;

    for (int n = 1; n <= mstepmax_main; ++n) {
        sed::SubstepAdvectionInputs sin{
            adv_state,
            fall_qr, fall_nr, fall_qs, fall_qg, fall_brs,
            w1_qr, wn_qr, w1_qs, w1_qg,
            forcing.delz, forcing.dend,
        };
        auto out = sed::substep_advection_torch(sin, mstep_col_main, mstepmax_main, n, dtcld, params);
        adv_state = out.state;
        fall_qr = out.fall_qr;
        fall_nr = out.fall_nr;
        fall_qs = out.fall_qs;
        fall_qg = out.fall_qg;
        fall_brs = out.fall_brs;

        // Re-slope from the post-substep state after EVERY main substep (Fortran F:1189-1205
        // is unconditional within the n-loop, incl. the last): rebuild state (updated
        // qr/nr/qs/qg/brs; ORIGINAL qi/ni — ice substepped below), ProgB+slope_kdm6 via
        // preamble, re-normalize by delz. rain/snow/graupel work1 feeds the next main substep
        // (unused after the last); the ICE work1 (vt_i/vtn_i) is the HANDOFF the ice loop
        // consumes — Fortran's final main slope_kdm6 writes work1(4)/workn(2) for F:1215.
        if (reslope_params != nullptr) {
            CoordinatorState rs = state;
            rs.qr = adv_state.qr; rs.nr = adv_state.nr;
            rs.qs = adv_state.qs; rs.qg = adv_state.qg; rs.brs = adv_state.brs;
            auto pre = preamble(rs, forcing, *reslope_params);
            w1_qr = pre.slope.vt_r  / delz_safe;   // F:1198-1205 normalizes work1(1,2,3)/workn(1) /delz
            wn_qr = pre.slope.vtn_r / delz_safe;
            w1_qs = pre.slope.vt_s  / delz_safe;
            w1_qg = pre.slope.vt_g  / delz_safe;
            // main→ice handoff (F:1194 slope_kdm6 → work1(4) → F:1215). Fortran leaves work1(4)/
            // workn(2) RAW here (F:1198-1205 normalizes only 1,2,3/workn1), so the ICE substep n=1
            // consumes the UNDIVIDED vt (effective CFL = vt_i·dtcld, ~delz× stronger fall). This was
            // tracker #9's deliberate /delz normalization (AD: full-depletion cells get ∂/∂qi=0) —
            // measured as the step-68 qi/ni divergence seed once QICE>0 (mp37 loses 37%/step of qi
            // here vs 0.07% normalized; "C-chain + RAW handoff" lands on mp37 bit-exactly, 0 ULP).
            // Replicated per the Fortran-flow-fidelity directive; the depletion-clamp zero gradient
            // is the TRUE one-sided subgradient of this flow (kink class — fix test ICs, not the
            // forward). Substeps n>=2 use the re-divided values below (F:1296-1301), unchanged.
            w1_qi = pre.slope.vt_i;
            wn_qi = pre.slope.vtn_i;
        }
    }

    // ── Ice substepping ─────────────────────────────────────────────────────
    sed::IceSubstepState ice_state{state.qi, state.ni};
    auto fall_qi = torch::zeros_like(state.qr);
    auto fall_ni = torch::zeros_like(state.qr);
    // w1_qi/wn_qi carry the main-loop handoff (post-final-main re-slope) when reslope_params
    // is set, else the passed-in initial — Fortran's ice loop reads work1(4) left by the main.

    for (int n = 1; n <= mstepmax_ice; ++n) {
        sed::IceSubstepInputs iin{
            ice_state,
            fall_qi, fall_ni,
            w1_qi, wn_qi,
            forcing.delz, forcing.dend,
        };
        auto out_i = sed::ice_substep_advection_torch(iin, mstep_col_ice, mstepmax_ice, n, dtcld, params);
        ice_state = out_i.state;
        fall_qi = out_i.fall_qi;
        fall_ni = out_i.fall_ni;

        // Re-slope ice fall speeds from the post-substep ice state (F:1244-1269). Other
        // species are the final post-main values; vt_i/vtn_i depend only on qi/ni so that
        // is immaterial. Used for ice substep n+1.
        if (reslope_params != nullptr && n < mstepmax_ice) {
            CoordinatorState rs = state;
            rs.qr = adv_state.qr; rs.nr = adv_state.nr; rs.qs = adv_state.qs;
            rs.qg = adv_state.qg; rs.brs = adv_state.brs;
            rs.qi = ice_state.qi; rs.ni = ice_state.ni;
            auto pre = preamble(rs, forcing, *reslope_params);
            w1_qi = pre.slope.vt_i  / delz_safe;
            wn_qi = pre.slope.vtn_i / delz_safe;
        }
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
