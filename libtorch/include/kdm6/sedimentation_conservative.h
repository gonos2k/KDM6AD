#pragma once
//
// KDM6 NISLFV-PLM sedimentation — CONSERVATIVE-INTERFACE variant.
// Python oracle (AUTHORITATIVE semantics): oracle/kdm6/sed_conservative.py
// (conservative_substep_advection_torch / conservative_ice_substep_advection_torch).
// Freeze-lift contract: docs/FREEZE_LIFT_CONSERVATIVE_INTERFACE_V1.md.
//
// Differences from the legacy substep (sedimentation.h — which stays
// byte-identical and is NOT touched by this variant):
//   - each interior cell's inflow is the cell above's ACTUAL entry-capped
//     outflow mass, converted per species by (ρΔz)_above / (ρΔz)_here, instead
//     of the legacy stored-falk flux re-capped by the source's POST-update
//     reservoir (which deletes mass whenever the per-substep fall ratio > 1/2);
//   - the fall/precip accumulators carry the actual-outflow RATE
//     (dq_out·ρ_safe/dtcld), so the chain-end surface accumulation reports the
//     actual bottom outflow;
//   - number (nr/ni) bookkeeping keeps the legacy Δz-only measure with the
//     actual transferred amount (no ρΔz mass conversion on numbers).
// Uncapped, both interfaces agree to roundoff; capped, this one conserves:
//   mass out of cell k−1 = ρ_{k−1}Δz_{k−1}·dq_out_{k−1} = mass into cell k,
// so W_post − W_pre + P_actual = O(ε) per column, no positivity clamp needed
// (q − dq_out ≥ 0 by the entry cap; inflow is nonnegative).
//
// Reuses the legacy input/output/param structs; K index 0 = TOP (caller flips).
//

#include "kdm6/sedimentation.h"

namespace kdm6 {
namespace sed {

// Conservative counterpart of substep_advection_torch (same signature).
SubstepAdvectionOutputs substep_advection_conservative(
    const SubstepAdvectionInputs& inputs,
    const torch::Tensor& mstep_col,  // (B,) per-column integer-valued float divisor + gate
    int mstepmax,                     // loop bound (caller loops n=1..mstepmax)
    int n,                            // current substep number (1-indexed)
    double dtcld,
    const SubstepAdvectionParams& params
);

// Conservative counterpart of ice_substep_advection_torch (same signature).
IceSubstepOutputs ice_substep_advection_conservative(
    const IceSubstepInputs& inputs,
    const torch::Tensor& mstep_col,  // (B,) per-column integer-valued float divisor + gate
    int mstepmax,                     // loop bound (caller loops n=1..mstepmax)
    int n,                            // current substep number (1-indexed)
    double dtcld,
    const SubstepAdvectionParams& params
);

}  // namespace sed
}  // namespace kdm6
