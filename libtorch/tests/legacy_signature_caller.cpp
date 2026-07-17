//
// C3.6 — old-signature caller fixture (conservative-interface-v1 C3 gates).
//
// This is a SEPARATE translation unit on purpose: it stands in for an
// already-compiled pre-PR22 consumer. Calling the pre-variant signatures from
// the same TU as the new tests would still exercise overload RESOLUTION, but a
// real legacy consumer's object file carries an undefined reference to the
// pre-PR22 MANGLED SYMBOLS — linking this TU into a test binary proves those
// exact symbols still exist in the kdm6 archive (the freeze-lift's
// "already-compiled callers keep linking" clause).
//
// The prototypes below re-declare the EXACT pre-PR22 signatures (kdm6_step
// 8-parameter, kdm6_fn 7-parameter) WITHOUT default arguments, so every call
// site here emits the legacy mangled symbol — never the options/variant
// overloads added by PR #22.
//
#include "legacy_signature_caller.h"

namespace kdm6 {

// Pre-PR22 prototypes (no defaults; identical types/order to the legacy
// overloads in runtime.h). A mismatch would fail to link, which is the gate.
FnResult kdm6_fn(const State& state,
                 const Forcing& forcing,
                 const Parameters& params,
                 double dt,
                 const c10::optional<torch::Tensor>& xland,
                 double ncmin_land,
                 double ncmin_sea);

StepResult kdm6_step(const State& state,
                     const Forcing& forcing,
                     const Parameters& params,
                     double dt,
                     bool value_only,
                     const c10::optional<torch::Tensor>& xland,
                     double ncmin_land,
                     double ncmin_sea);

namespace testing_legacy {

FnResult call_pre_pr22_kdm6_fn(const State& state, const Forcing& forcing,
                               const Parameters& params, double dt) {
    // 7-parameter legacy kdm6_fn — the pre-variant mangled symbol.
    return kdm6_fn(state, forcing, params, dt, c10::nullopt, 0.0, 0.0);
}

StepResult call_pre_pr22_kdm6_step(const State& state, const Forcing& forcing,
                                   const Parameters& params, double dt,
                                   bool value_only) {
    // 8-parameter legacy kdm6_step — the pre-variant mangled symbol.
    return kdm6_step(state, forcing, params, dt, value_only,
                     c10::nullopt, 0.0, 0.0);
}

}  // namespace testing_legacy
}  // namespace kdm6
