#pragma once
//
// C3.6 old-signature caller fixture — see legacy_signature_caller.cpp.
// Wrappers around the EXACT pre-PR22 signatures (kdm6_step 8-param,
// kdm6_fn 7-param), defined in a separate translation unit so the test binary
// links the legacy mangled symbols the way a real pre-variant consumer would.
//
#include "kdm6/runtime.h"

namespace kdm6 {
namespace testing_legacy {

FnResult call_pre_pr22_kdm6_fn(const State& state, const Forcing& forcing,
                               const Parameters& params, double dt);

StepResult call_pre_pr22_kdm6_step(const State& state, const Forcing& forcing,
                                   const Parameters& params, double dt,
                                   bool value_only);

}  // namespace testing_legacy
}  // namespace kdm6
