#include "kdm6/runtime.h"
#include "kdm6/coordinator.h"
#include "kdm6/ops.h"

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
    return CoordinatorForcing{
        /*p=*/f.p,
        /*den=*/f.rho,
        /*delz=*/f.delz,
        /*dend=*/f.rho * f.delz,
    };
}

CoordinatorAuxDiagnostics build_default_aux(const State& s, const torch::Tensor& rslopec) {
    // Parity/bootstrap defaults — matches `parity/run_parity.py:_build_aux`.
    // Operational KIM auxdiag arrays are not consumed here yet; drift can reflect
    // wrapper/diagnostic mismatch rather than libtorch microphysics drift.
    auto full_like = [&](double v) {
        return torch::full_like(s.qc, v);
    };
    return CoordinatorAuxDiagnostics{
        /*n0r=*/full_like(8.0e6),
        /*n0i=*/full_like(1.0e6),
        /*n0c=*/full_like(1.0e8),
        /*n0so=*/full_like(2.0e6),
        /*n0go=*/full_like(4.0e6),
        /*work1_r=*/full_like(1.0e-3),
        /*work1_ice=*/full_like(1.0e-3),
        /*work1_water=*/full_like(1.0e-3),
        /*qcr=*/full_like(8.0e-5),
        /*avedia_i=*/full_like(1.0e-4),
        /*rslopecmu=*/torch::pow(rslopec, constants::MUC),
        /*rslopecd=*/torch::pow(rslopec, constants::DMC),
    };
}

}  // namespace

State kdm6_fn(const State& state,
              const Forcing& forcing,
              const Parameters& /*params*/,
              double dt) {
    // F4 wiring: wrapper State → CoordinatorState → kdm62d_step → State.
    // params (PEAUT/NCRK1/NCRK2/ECCBRK)는 현재 default cold/warm/mf-phase params에서
    // baked-in 상수로 사용됨. AD-trainable parameters로 활용하려면 별도 plumbing 필요.
    auto cs = state_to_coord(state, forcing);
    auto cf = build_forcing(forcing);

    // Need rslopec to construct rslopecmu/rslopecd in aux. Compute via cloud_dsd.
    auto cloud_p = cloud_dsd::default_cloud_dsd_params();
    auto rslopec = cloud_dsd::diag_cloud_slope_torch(cs.qc, cs.nc, cf.den, cloud_p);
    auto aux = build_default_aux(state, rslopec);

    auto sea_mask = torch::ones_like(cs.qc, torch::dtype(torch::kBool));

    auto full_p = default_coordinator_params();
    auto warm_p = default_warm_phase_params();
    auto cold_p = default_cold_phase_params();
    auto mf_p   = default_melt_freeze_phase_params();

    auto cs_out = kdm62d_step(
        cs, cf, aux, sea_mask, full_p, warm_p, cold_p, mf_p,
        /*delt=*/dt
    );
    return coord_to_state(cs_out, state, forcing);
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
                     const Parameters& params, double dt, bool value_only) {
    if (value_only) {
        torch::NoGradGuard no_grad;
        auto state_out = kdm6_fn(state, forcing, params, dt);
        return StepResult{std::move(state_out), nullptr};
    }
    auto state_out = kdm6_fn(state, forcing, params, dt);
    auto handle = std::make_unique<Handle>(
        state, state_out, forcing, params, dt, /*value_only=*/false);
    return StepResult{std::move(state_out), std::move(handle)};
}

}  // namespace kdm6
