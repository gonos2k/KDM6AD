#include "kdm6/runtime.h"
#include "kdm6/coordinator.h"
#include "kdm6/ops.h"
#include "kdm6/sedimentation.h"

#include <cmath>

namespace kdm6 {

// ── Parameters ──────────────────────────────────────────────────────────────
static torch::Tensor mkparam(double value, bool grad,
                             torch::Device device, torch::Dtype dtype) {
    auto opts = torch::TensorOptions().dtype(dtype).device(device);
    auto t = torch::tensor(value, opts);
    if (grad) {
        t = t.detach().clone().requires_grad_(true);
    }
    return t;
}

Parameters make_parameters(int grad_flags, torch::Device device, torch::Dtype dtype) {
    Parameters p;
    p.peaut  = mkparam(constants::PEAUT,  grad_flags & ParamGradFlags::PEAUT,  device, dtype);
    p.ncrk1  = mkparam(constants::NCRK1,  grad_flags & ParamGradFlags::NCRK1,  device, dtype);
    p.ncrk2  = mkparam(constants::NCRK2,  grad_flags & ParamGradFlags::NCRK2,  device, dtype);
    p.eccbrk = mkparam(constants::ECCBRK, grad_flags & ParamGradFlags::ECCBRK, device, dtype);
    return p;
}

// ── Wrapper State ↔ microphysics CoordinatorState 변환 ────────────────────
//
// Wrapper-level `kdm6::State`는 KIM-meso 측 layout (th, qv, qc, qr, qi, qs, qg,
// nccn, nc, ni, nr, bg)를 따름. microphysics-level `kdm6::CoordinatorState`는
// (qv, qc, qr, qs, qg, qi, nc, nr, ni, nccn, brs, t)이라 다음 매핑 필요:
//   t = th · pii   (Exner inverse: T = θ · π)
//   brs = bg       (graupel volume mixing ratio)
//
namespace {

CoordinatorState state_to_coord(const State& s, const Forcing& f) {
    return CoordinatorState{
        /*qv=*/s.qv, /*qc=*/s.qc, /*qr=*/s.qr,
        /*qs=*/s.qs, /*qg=*/s.qg, /*qi=*/s.qi,
        /*nc=*/s.nc, /*nr=*/s.nr, /*ni=*/s.ni,
        /*nccn=*/s.nccn,
        /*brs=*/s.bg,
        /*t=*/s.th * f.pii,
    };
}

State coord_to_state(const CoordinatorState& c, const State& orig, const Forcing& f) {
    State out = orig;
    out.qv = c.qv; out.qc = c.qc; out.qr = c.qr;
    out.qs = c.qs; out.qg = c.qg; out.qi = c.qi;
    out.nc = c.nc; out.nr = c.nr; out.ni = c.ni;
    out.nccn = c.nccn;
    out.bg = c.brs;
    out.th = c.t / f.pii;
    return out;
}

CoordinatorForcing build_forcing(const Forcing& f) {
    // dend = air density (NOT density × delz).
    // Fortran reference `module_mp_kdm6.F:812` sets `dend(i,k) = den(i,k)`.
    // Python oracle's `CoordinatorForcing.dend` is mis-documented as
    // `density × delz` at `coordinator.py:63` — that label is wrong vs
    // operational Fortran. Codex stop-gate review caught this when the
    // squall RAINNC came out at 10,455 mm / 30 min (~250× physical) because
    // the extra delz factor cascaded through `falk = dend·q·work1/mstep`
    // (where work1 = vt/delz, so delz cancels OUT of falk only if dend=ρ),
    // and the bottom-layer fall ended up over-scaled by delz when
    // `surface_accumulation_torch` multiplies by delz again.
    return CoordinatorForcing{
        /*p=*/f.p,
        /*den=*/f.rho,
        /*delz=*/f.delz,
        /*dend=*/f.rho,
    };
}

}  // namespace

// Operational auxiliary diagnostics — physics-based, mirroring Fortran
// module_mp_kdm6.F:1435-1480 (n0 intercepts) and :1679-1680 (work1 = diffac).
// Stage-A STEP 0: PROMOTED out of the anonymous namespace (declared in
// coordinator.h) so rebuild_aux + the symbol-parity contract see it; matches the
// Python build_default_aux_torch. Uses only cloud_dsd::/thermo:: + constants.
//
// Design (validated against the cross-file contract map):
//   - n0r/n0i/n0c derive from the clamped DSD slope (diag_species_slope_torch),
//     using the Fortran "default formula" n0 = n/(rslope·rslope^mu·g1pm) which is
//     identical to the gated lamda-recompute except for the rare clamp-fired
//     number back-mutation (a second-order effect on a fringe of cells; the
//     downstream rate gates zero inactive cells regardless).
//   - n0so/n0go: Fortran n0so = n0s/g1pms/rslopemu_s with mus=0 ⇒ g1pms=1,
//     rslopemu_s=rslope^0=1, so n0so collapses to the constant n0s=2e6 (likewise
//     n0go=n0g=4e6). The historical placeholders were therefore already EXACT;
//     kept as constants to avoid the progb→slope_kdm6_torch graupel dependency.
//   - work1_water = diffac(xl,  p, t, den, qs_water)  (Fortran work1(:,:,1))
//     work1_ice   = diffac(xls, p, t, den, qs_ice)    (Fortran work1(:,:,2))
//     work1_r     = work1_water (rain evap uses water diffusivity, review3#1).
//   - avedia_i = rslope_i·(g4pmi/g1pmi)^(1/3)  (Fortran 1672).
//
// COUPLING NOTE: n0 (rate numerators) and work1 (evap/dep denominators) MUST be
// installed together. A prior work1-only attempt collapsed QC because it changed
// the denominator without the matching numerator. See
// project_kdm6_operational_aux_port_required.md.
CoordinatorAuxDiagnostics build_default_aux(
    const CoordinatorState& cs,
    const CoordinatorForcing& cf,
    const torch::Tensor& rslopec,
    const thermo::ThermoParams& tp) {
    constexpr double PI = 3.14159265358979323846;

    // Gamma normalization constants (rgmma = Γ = exp(lgamma)).
    const double g1pmr = std::exp(std::lgamma(1.0 + constants::MUR));            // Γ(2)=1
    const double g1pmi = std::exp(std::lgamma(1.0 + constants::MUI));            // Γ(1)=1
    const double g4pmi = std::exp(std::lgamma(4.0 + constants::MUI));            // Γ(4)=6
    const double pidnr = (PI * constants::DENR / 6.0)
                       * std::exp(std::lgamma(1.0 + constants::DMR + constants::MUR)) / g1pmr;
    const double pidni = (PI * constants::DENI / 6.0)
                       * std::exp(std::lgamma(1.0 + constants::DMI + constants::MUI)) / g1pmi;

    // Rain / ice clamped DSD slopes (Fortran rslope(:,1) / rslope(:,4)).
    auto rslope_r = cloud_dsd::diag_species_slope_torch(
        cs.qr, cs.nr, cf.den, pidnr, constants::DMR,
        constants::LAMDARMAX, constants::LAMDARMIN);
    auto rslope_i = cloud_dsd::diag_species_slope_torch(
        cs.qi, cs.ni, cf.den, pidni, constants::DMI,
        constants::LAMDAIMAX, constants::LAMDAIMIN);

    auto rslopemu_r = torch::pow(rslope_r, constants::MUR);                      // ^1
    auto rslopemu_i = (constants::MUI == 0.0)
                    ? torch::ones_like(rslope_i)
                    : torch::pow(rslope_i, constants::MUI);
    auto rslopecmu = torch::pow(rslopec, constants::MUC);

    // n0 intercepts (Fortran 1435-1437 default formula; clamped rslope already
    // reflects the lamda bounds).
    auto n0r = cs.nr / (rslope_r * rslopemu_r * g1pmr);
    auto n0i = cs.ni / (rslope_i * rslopemu_i * g1pmi);
    auto n0c = (constants::MUC + 1.0) * cs.nc / (rslopec * rslopecmu);

    // work1 diffusion factors (Fortran 1679-1680).
    auto xl    = thermo::compute_xl(cs.t, tp);
    auto xls_t = torch::full_like(cs.t, tp.xls);
    auto qs1   = thermo::compute_qs_water(cs.t, cf.p, tp);
    auto qs2   = thermo::compute_qs_ice(cs.t, cf.p, tp);
    auto work1_water = thermo::compute_diffac(xl,    cf.p, cs.t, cf.den, qs1, tp);
    auto work1_ice   = thermo::compute_diffac(xls_t, cf.p, cs.t, cf.den, qs2, tp);

    auto full_like = [&](double v) { return torch::full_like(cs.qc, v); };

    return CoordinatorAuxDiagnostics{
        /*n0r=*/n0r,
        /*n0i=*/n0i,
        /*n0c=*/n0c,
        /*n0so=*/full_like(constants::N0S),     // = n0s (mus=0 ⇒ formula collapses)
        /*n0go=*/full_like(constants::N0G),     // = n0g (mug=0 ⇒ formula collapses)
        /*work1_r=*/work1_water,                // Fortran work1(:,:,1)
        /*work1_ice=*/work1_ice,                // Fortran work1(:,:,2)
        /*work1_water=*/work1_water,            // Fortran work1(:,:,1)
        /*qcr=*/full_like(8.0e-5),              // overridden by diag_qcr_torch when xland present
        /*avedia_i=*/rslope_i * std::pow(g4pmi / g1pmi, 0.3333333),  // Fortran F:1672 ice avedia uses .3333333 literal. 1:1 fix #4/#11.
        /*rslopecmu=*/rslopecmu,
        /*rslopecd=*/torch::pow(rslopec, constants::DMC),
    };
}

// Test-facing wrapper around the now-exported build_default_aux. Mirrors
// the production path so tests assert what the operational path actually installs.
CoordinatorAuxDiagnostics build_default_aux_for_test(
    const State& s, const Forcing& f) {
    auto cs = state_to_coord(s, f);
    auto cf = build_forcing(f);
    auto cloud_p = cloud_dsd::default_cloud_dsd_params();
    auto rslopec = cloud_dsd::diag_cloud_slope_torch(cs.qc, cs.nc, cf.den, cloud_p);
    auto full_p = default_coordinator_params();
    return build_default_aux(cs, cf, rslopec, full_p.thermo);
}

// Stage-A re-architecture support (STEP 0). Defined here because the
// anonymous-namespace build_default_aux is reachable from this TU; declared in
// coordinator.h for kdm62d_one_step to call once the sequential chain lands.
// Rebuilds BOTH preamble (slopes/work2/ProgB) AND aux (n0*/work1*/rslopec*) on
// the working state — never one without the other (stale-pre = 806× class).
//
// THERMO STAGING (Codex stop-review fix): Fortran's re-slope after melt/freeze
// (kdm6.F:1422-1480,:1596-1683,:1677-1683) recomputes the GEOMETRY (rslope*/
// n0*/ProgB/work2/n0sfac) and supcol on the post-freeze state, but does NOT
// recompute the saturation/latent-heat thermo: cpm(:835), xl(:836), qs1/qs2/
// rh/sw(:910-928) are computed ONCE (entry/substep-top) and the rate loop reads
// those entry-staged values (supsat=q-qs at :1695/:1822 uses entry qs; q=qv is
// melt/freeze-invariant). So we SPLICE the entry-staged thermo back into the
// rebuilt preamble — otherwise warm/cold would see post-freeze qs (exponential
// in t ⇒ materially wrong supersaturation) and post-freeze xl. work1=diffac(xl,
// p,t,den,qs) is re-slope-recomputed with POST-FREEZE t but ENTRY xl/qs
// (:1679-1680), so we rebuild it with the entry thermo + the working t.
RebuiltDiagnostics rebuild_aux(
    const CoordinatorState& state,         // working (post-melt/freeze)
    const PreambleOutputs& entry_pre,      // entry/substep-top preamble (thermo source)
    const CoordinatorForcing& forcing,
    const CoordinatorParams& params,
    const torch::Tensor& qcr_carry) {
    auto pre = preamble(state, forcing, params);                       // re-slope + work2 + ProgB + (discarded) thermo
    // Splice entry-staged thermo; keep post-freeze supcol/work2/denfac + geometry.
    pre.cpm = entry_pre.cpm;  pre.xl = entry_pre.xl;
    pre.qs1 = entry_pre.qs1;  pre.qs2 = entry_pre.qs2;
    pre.rh_w = entry_pre.rh_w;  pre.rh_ice = entry_pre.rh_ice;
    pre.supsat = entry_pre.supsat;
    auto aux = build_default_aux(state, forcing, pre.rslopec, params.thermo);
    // work1 = diffac(ENTRY xl/qs, POST-FREEZE t) — Fortran kdm6.F:1679-1680.
    auto xls_t = torch::full_like(state.t, params.thermo.xls);
    aux.work1_water = thermo::compute_diffac(entry_pre.xl, forcing.p, state.t, forcing.den, entry_pre.qs1, params.thermo);
    aux.work1_ice   = thermo::compute_diffac(xls_t,        forcing.p, state.t, forcing.den, entry_pre.qs2, params.thermo);
    aux.work1_r     = aux.work1_water;   // Fortran work1(:,:,1) for rain capacitance
    aux.qcr = qcr_carry;   // sea_mask-derived, state-independent — carry, don't recompute
    return RebuiltDiagnostics{pre, aux};
}

FnResult kdm6_fn(const State& state,
                 const Forcing& forcing,
                 const Parameters& /*params*/,
                 double dt,
                 const c10::optional<torch::Tensor>& xland,
                 double ncmin_land,
                 double ncmin_sea) {
    // F4 wiring: wrapper State → CoordinatorState → kdm62d_step → State.
    // params (PEAUT/NCRK1/NCRK2/ECCBRK)는 현재 default cold/warm/mf-phase params에서
    // baked-in 상수로 사용됨. AD-trainable parameters로 활용하려면 별도 plumbing 필요.
    auto cs = state_to_coord(state, forcing);
    auto cf = build_forcing(forcing);

    // Coordinator params first — build_default_aux needs thermo params for the
    // diffac (work1) computation.
    auto full_p = default_coordinator_params();

    // delt<=0 → no-op (dtcld=0 would NaN the per-rate mass/dtcld divisions).
    if (dt <= 0.0) {
        auto z = torch::zeros({cs.qc.size(0)}, cs.qc.options());
        return FnResult{coord_to_state(cs, state, forcing), z, z, z};
    }

    auto warm_p   = default_warm_phase_params();
    auto cold_p   = default_cold_phase_params();
    auto mf_p     = default_melt_freeze_phase_params();
    auto cloud_p  = cloud_dsd::default_cloud_dsd_params();
    auto sed_params = sed::default_substep_advection_params();

    // [xland plumbing] sea_mask + per-cell ncmin are state-independent ⇒ derived
    // ONCE. xland may be (im, jme) 2-D or flat (im*jme,); WRF slmsk: xland>=1.5 →
    // sea. The qcr override (sea→qc0=8.4e-5, land→qc1=8.4e-4; Fortran :840-846) is
    // re-applied per sub-cycle since aux is rebuilt each substep.
    torch::Tensor sea_mask;
    const bool use_xland_qcr = xland.has_value();
    if (use_xland_qcr) {
        auto xl = xland.value().to(cs.qc.options());
        auto xl_flat = xl.contiguous().view({-1});
        auto sea_mask_flat = xl_flat >= 1.5;
        sea_mask = sea_mask_flat.unsqueeze(1).expand_as(cs.qc).contiguous();
        auto ncmin_flat = torch::where(
            sea_mask_flat,
            torch::full_like(xl_flat, ncmin_sea),
            torch::full_like(xl_flat, ncmin_land));
        auto ncmin_tensor = ncmin_flat.unsqueeze(1).expand_as(cs.qc).contiguous();
        warm_p.autoconv.ncmin_tensor              = ncmin_tensor;
        cold_p.number_accretion.ncmin_tensor      = ncmin_tensor;
        cold_p.cloud_water_riming.ncmin_tensor    = ncmin_tensor;
        mf_p.contact.ncmin_tensor                 = ncmin_tensor;
        mf_p.bigg_cloud.ncmin_tensor              = ncmin_tensor;
    } else {
        sea_mask = torch::ones_like(cs.qc, torch::dtype(torch::kBool));
    }

    // ─── Stage-A sediment-order fix (Stage S2): per-substep [sediment → microphysics] ──
    // Fortran's dtcld sub-cycle (kdm6.F:876) does, EACH substep: sediment at the
    // TOP (:1119) → re-slope/ProgB/n0 (:1422-1480) → melt/freeze/rate block (:1274+)
    // → state_update. The port previously did all microphysics then sedimented ONCE,
    // inverting the order. We now split the timestep into `loops` sub-cycles and, per
    // substep: fall(dtcld) on the current state → rebuild aux on the post-fall state →
    // run ONE microphysics pass (kdm62d_one_step) over dtcld. The Fortran entry-prologue
    // nccn clamp (:801) is applied ONCE here (kdm62d_one_step does NOT re-clamp), matching
    // Fortran (clamp before the sub-cycle loop, not per substep). For loops=1 (dt<=dtcldcr;
    // every validation/typical case) this == Stage S1's single sub-cycle. K-flip: WRF
    // stages K=0 at surface, sedimentation_chain wants K=0 at TOP; cf is constant so its
    // flip + delz are hoisted out of the loop.
    auto flip_k = [](const torch::Tensor& t) { return torch::flip(t, {1}); };
    CoordinatorForcing cf_pyc{
        flip_k(cf.p), flip_k(cf.den), flip_k(cf.delz), flip_k(cf.dend),
    };
    auto delz_safe = torch::clamp(cf_pyc.delz, /*min=*/1.0e-9);

    const int loops = compute_loops_max(dt, constants::DTCLDCR);
    const double dtcld = dt / static_cast<double>(loops);

    auto cur = cs;                                          // WRF K-order, evolves across sub-cycles
    cur.nccn = torch::clamp(cur.nccn, constants::NCCN_MIN, constants::NCCN_MAX);  // Fortran :801, ONCE
    torch::Tensor rain_inc, snow_inc, graup_inc;

    for (int i = 0; i < loops; ++i) {
        // 1. SEDIMENT(dtcld) at the TOP of the sub-cycle (Fortran :1119), per-substep mstep.
        CoordinatorState cur_pyc{
            flip_k(cur.qv), flip_k(cur.qc), flip_k(cur.qr),
            flip_k(cur.qs), flip_k(cur.qg), flip_k(cur.qi),
            flip_k(cur.nc), flip_k(cur.nr), flip_k(cur.ni),
            flip_k(cur.nccn), flip_k(cur.brs), flip_k(cur.t),
        };
        auto pre_sed = preamble(cur_pyc, cf_pyc, full_p);
        auto w1_qr = pre_sed.slope.vt_r  / delz_safe;
        auto wn_qr = pre_sed.slope.vtn_r / delz_safe;
        auto w1_qs = pre_sed.slope.vt_s  / delz_safe;
        auto w1_qg = pre_sed.slope.vt_g  / delz_safe;
        auto w1_qi = pre_sed.slope.vt_i  / delz_safe;
        auto wn_qi = pre_sed.slope.vtn_i / delz_safe;
        // Per-column mstep (Fortran :1107-1117): mstep(i)=max(nint(vmax(i)*dtcld+.5),1),
        // capped at 100; mstepmax = max over columns (loop bound). All integer work in
        // NoGradGuard. mstep_col_* kept as float (B,) tensors for use as divisor / gate.
        torch::Tensor mstep_col_main, mstep_col_ice;
        int mstepmax_main = 1, mstepmax_ice = 1;
        {
            torch::NoGradGuard no_grad;
            // Per-column max fall speed over K (Fortran nested k-loop takes the column max).
            auto vmax_main_col = torch::maximum(torch::maximum(w1_qr, wn_qr),
                                                torch::maximum(w1_qs, w1_qg)).amax(/*dim=*/-1);
            mstep_col_main = torch::clamp(
                torch::round(vmax_main_col * dtcld + 0.5).to(torch::kLong),
                /*min=*/1, /*max=*/100).to(w1_qr.dtype());
            mstepmax_main = static_cast<int>(mstep_col_main.max().item<double>());

            auto vmax_ice_col = torch::maximum(w1_qi, wn_qi).amax(/*dim=*/-1);
            mstep_col_ice = torch::clamp(
                torch::round(vmax_ice_col * dtcld + 0.5).to(torch::kLong),
                /*min=*/1, /*max=*/100).to(w1_qi.dtype());
            mstepmax_ice = static_cast<int>(mstep_col_ice.max().item<double>());
        }
        auto sed = sedimentation_chain(
            cur_pyc, cf_pyc, w1_qr, wn_qr, w1_qs, w1_qg, w1_qi, wn_qi,
            mstep_col_main, mstepmax_main, mstep_col_ice, mstepmax_ice, dtcld, sed_params,
            /*reslope_params=*/&full_p);  // 1:1 fix #9: per-substep fall-speed re-slope (F:1189-1205)
        cur = CoordinatorState{
            flip_k(sed.state.qv), flip_k(sed.state.qc), flip_k(sed.state.qr),
            flip_k(sed.state.qs), flip_k(sed.state.qg), flip_k(sed.state.qi),
            flip_k(sed.state.nc), flip_k(sed.state.nr), flip_k(sed.state.ni),
            flip_k(sed.state.nccn), flip_k(sed.state.brs), flip_k(sed.state.t),
        };
        rain_inc  = (i == 0) ? sed.rain_increment    : rain_inc  + sed.rain_increment;
        snow_inc  = (i == 0) ? sed.snow_increment    : snow_inc  + sed.snow_increment;
        graup_inc = (i == 0) ? sed.graupel_increment : graup_inc + sed.graupel_increment;

        // 2. Re-slope + aux on the POST-FALL state (Fortran :1422-1480 / :1679-1680).
        auto rslopec = cloud_dsd::diag_cloud_slope_torch(cur.qc, cur.nc, cf.den, cloud_p);
        auto aux = build_default_aux(cur, cf, rslopec, full_p.thermo);
        if (use_xland_qcr) aux.qcr = cloud_dsd::diag_qcr_torch(sea_mask, cloud_p, cur.qc);

        // 3. ONE microphysics pass over dtcld (melt → … → state_update), Fortran :1274+.
        cur = kdm62d_one_step(cur, cf, aux, sea_mask, full_p, warm_p, cold_p, mf_p, dtcld);
    }

    // Surface increments accumulated across the sub-cycles (1-D per column [mm]) ⇒
    // FnResult ⇒ kdm6_step_c ⇒ WRF RAINNCV/SNOWNCV/GRAUPELNCV.
    return FnResult{
        coord_to_state(cur, state, forcing),
        rain_inc, snow_inc, graup_inc,
    };
}

// ── Handle::Impl ────────────────────────────────────────────────────────────
struct Handle::Impl {
    State state_in;
    State state_out;
    Forcing forcing;
    Parameters params;
    double dt;
    bool value_only;
    bool closed = false;
};

Handle::Handle(State state_in, State state_out, Forcing forcing,
               Parameters params, double dt, bool value_only)
    : impl_(std::make_unique<Impl>(Impl{
          std::move(state_in), std::move(state_out), std::move(forcing),
          std::move(params), dt, value_only, false})) {}

Handle::~Handle() = default;
Handle::Handle(Handle&&) noexcept = default;
Handle& Handle::operator=(Handle&&) noexcept = default;

void Handle::close() {
    if (impl_) {
        impl_->closed = true;
        impl_->state_in = State{};
        impl_->state_out = State{};
        impl_->forcing = Forcing{};
        impl_->params = Parameters{};
    }
}

bool Handle::is_closed() const noexcept {
    return !impl_ || impl_->closed;
}

bool Handle::is_value_only() const noexcept {
    return impl_ && impl_->value_only;
}

State Handle::vjp(const State& /*u*/) const {
    TORCH_CHECK(impl_, "Handle is moved-from");
    TORCH_CHECK(!impl_->closed, "Handle is closed");
    TORCH_CHECK(!impl_->value_only, "Handle is value-only");
    TORCH_CHECK_NOT_IMPLEMENTED(false, "[G3] vjp — implement after kdm6_fn body works");
}

State Handle::jvp(const State& /*v*/) const {
    TORCH_CHECK(impl_, "Handle is moved-from");
    TORCH_CHECK(!impl_->closed, "Handle is closed");
    TORCH_CHECK(!impl_->value_only, "Handle is value-only");
    TORCH_CHECK_NOT_IMPLEMENTED(false, "[G3] jvp — implement after kdm6_fn body works");
}

// ── kdm6_step ───────────────────────────────────────────────────────────────
StepResult kdm6_step(const State& state, const Forcing& forcing,
                     const Parameters& params, double dt, bool value_only,
                     const c10::optional<torch::Tensor>& xland,
                     double ncmin_land, double ncmin_sea) {
    if (value_only) {
        torch::NoGradGuard no_grad;
        auto fn_out = kdm6_fn(state, forcing, params, dt, xland, ncmin_land, ncmin_sea);
        return StepResult{
            std::move(fn_out.state_out), nullptr,
            std::move(fn_out.rain_increment),
            std::move(fn_out.snow_increment),
            std::move(fn_out.graupel_increment),
        };
    }
    auto fn_out = kdm6_fn(state, forcing, params, dt, xland, ncmin_land, ncmin_sea);
    auto handle = std::make_unique<Handle>(
        state, fn_out.state_out, forcing, params, dt, /*value_only=*/false);
    return StepResult{
        std::move(fn_out.state_out), std::move(handle),
        std::move(fn_out.rain_increment),
        std::move(fn_out.snow_increment),
        std::move(fn_out.graupel_increment),
    };
}

}  // namespace kdm6
