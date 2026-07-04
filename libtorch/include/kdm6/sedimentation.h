#pragma once
//
// KDM6 NISLFV-PLM sedimentation — Step E.
// Python oracle: kdm6_torch/kdm6/sedimentation.py
//
// E1 work normalization, E2 substep advection (qr/nr/qs/qg/brs),
// E4 ice substep (qi/ni), E5 surface accumulation.
//
// AD-friendly: list-of-columns chain (std::vector<Tensor>) → torch::stack.
//

#include "kdm6/constants.h"
#include <torch/torch.h>
#include <vector>

namespace kdm6 {
namespace sed {

// ─── E1: work normalization ─────────────────────────────────────────────────

torch::Tensor normalize_work_by_delz(const torch::Tensor& work, const torch::Tensor& delz);

// ─── E2: substep advection ──────────────────────────────────────────────────

struct SubstepAdvectionParams {
    double qcrmin;
};

SubstepAdvectionParams default_substep_advection_params();

struct SubstepAdvectionState {
    torch::Tensor qr, nr, qs, qg, brs;
};

struct SubstepAdvectionOutputs {
    SubstepAdvectionState state;
    torch::Tensor fall_qr, fall_nr;
    torch::Tensor fall_qs, fall_qg, fall_brs;
};

struct SubstepAdvectionInputs {
    SubstepAdvectionState state;
    torch::Tensor fall_qr_in, fall_nr_in;
    torch::Tensor fall_qs_in, fall_qg_in, fall_brs_in;
    torch::Tensor work1_qr, workn_qr;
    torch::Tensor work1_qs, work1_qg;
    torch::Tensor delz, dend;
};

SubstepAdvectionOutputs substep_advection_torch(
    const SubstepAdvectionInputs& inputs,
    const torch::Tensor& mstep_col,  // (B,) per-column integer-valued float divisor + gate
    int mstepmax,                     // loop bound (caller loops n=1..mstepmax)
    int n,                            // current substep number (1-indexed)
    double dtcld,
    const SubstepAdvectionParams& params
);

// ─── E4: Ice substep ────────────────────────────────────────────────────────

struct IceSubstepState {
    torch::Tensor qi, ni;
};

struct IceSubstepOutputs {
    IceSubstepState state;
    torch::Tensor fall_qi, fall_ni;
};

struct IceSubstepInputs {
    IceSubstepState state;
    torch::Tensor fall_qi_in, fall_ni_in;
    torch::Tensor work1_qi, workn_qi;
    torch::Tensor delz, dend;
};

IceSubstepOutputs ice_substep_advection_torch(
    const IceSubstepInputs& inputs,
    const torch::Tensor& mstep_col,  // (B,) per-column integer-valued float divisor + gate
    int mstepmax,                     // loop bound (caller loops n=1..mstepmax)
    int n,                            // current substep number (1-indexed)
    double dtcld,
    const SubstepAdvectionParams& params
);

// ─── E5: Surface accumulation ───────────────────────────────────────────────

struct SurfaceAccumOutputs {
    torch::Tensor rain_increment;
    torch::Tensor snow_increment;
    torch::Tensor graupel_increment;
};

SurfaceAccumOutputs surface_accumulation_torch(
    const torch::Tensor& fall_qr_bottom,
    const torch::Tensor& fall_qs_bottom,
    const torch::Tensor& fall_qg_bottom,
    const torch::Tensor& fall_qi_bottom,
    const torch::Tensor& delz_bottom,
    double dtcld
);

}  // namespace sed
}  // namespace kdm6
