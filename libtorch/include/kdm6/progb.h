#pragma once
//
// KDM6 ProgB_param — graupel volume + density-dependent DSD parameters.
//
// 원본:
//   - module_mp_kdm6.F: 3332-3425 (SUBROUTINE ProgB_param)
//   - module_mp_kdm6.F: 3090-3099 (kdm6init의 hail_opt-의존 graupel 상수)
//   - module_mp_kdm6.F: 3166-3262 (g1pmg/g1pdgmg gamma 파생)
//
// Python oracle: kdm6_torch/kdm6/progb.py — 본 파일과 1:1 정합.
//

#include "kdm6/constants.h"
#include <torch/torch.h>

namespace kdm6 {
namespace progb {

// ── ProgB_param 헤더 상수 ─────────────────────────────────────────────
inline constexpr double RHO_MIN = 100.0;   // kg m^-3
inline constexpr double RHO_MAX = 900.0;   // kg m^-3
inline constexpr double RHO_MID = 400.0;   // kg m^-3, default for inactive cells
inline constexpr double BRS_MIN = 1.0e-15; // m^3 kg^-1

struct ProgBParams {
    double qcrmin;
    double dmg;
    double mug;
    double n0g;
    double g1pdgmg;   // rgmma(1 + dmg + mug)
    double g1pmg;     // rgmma(1 + mug)   — mug==0이면 1.0
    double rslopegmax; // 1 / lamdagmax
};

struct ProgBOutputs {
    torch::Tensor rhox;       // graupel density [kg m^-3]
    torch::Tensor bg;         // updated volume mixing ratio (consistency)
    torch::Tensor cmg;        // pi * rhox / 6
    torch::Tensor pidn0g;
    torch::Tensor avtg;
    torch::Tensor bvtg;
    torch::Tensor bvtg1;      // 1 + bvtg
    torch::Tensor bvtg2;      // 2.5 + 0.5*bvtg + mug
    torch::Tensor bvtg3;      // 3 + bvtg + mug
    torch::Tensor bvtg4;      // 4 + bvtg
    torch::Tensor g1pbg;      // rgmma(bvtg1)
    torch::Tensor g3pbg;      // rgmma(bvtg3)
    torch::Tensor g4pbg;      // rgmma(bvtg4)
    torch::Tensor g5pbgo2;    // rgmma(bvtg2)
    torch::Tensor g1pdgbgmg;  // rgmma(dgbgmug1)
    torch::Tensor dgbgmug1;   // 1 + dmg + bvtg + mug
    torch::Tensor rslopegbmax;// rslopegmax ** bvtg
    torch::Tensor pvtg;
    torch::Tensor precg2;
};

// §53d: step-entry zero bundle for the PERSISTENT per-cell ProgB arrays. Fortran F:973-990
// zero-inits all these outputs each kdm62d sub-cycle; each ProgB call then writes ONLY
// active cells (F:3567), inactive cells RETAIN their last value. preamble() merges
// fresh-vs-retained through this bundle so slope/melt/cold consumers see the persistent
// arrays exactly as Fortran's slope_kdm6/rate loops do.
inline ProgBOutputs make_zero_progb_state(const torch::Tensor& ref) {
    auto z = torch::zeros_like(ref);
    return ProgBOutputs{z, z, z, z, z, z, z, z, z, z, z, z, z, z, z, z, z, z, z};
}

ProgBParams default_progb_params();

ProgBOutputs progb_param_torch(
    const torch::Tensor& qg,
    const torch::Tensor& bg,
    const ProgBParams& params,
    // rhox/bg computed in op_dtype: f32 op-path = Fortran REAL(4) (the [100,900] clamp tips
    // faithfully) / f64 DA-path = smooth (no staircase ⇒ VJP/FD/ABI-determinism intact).
    // nullopt → bg.scalar_type() (no cast; backward-compatible for direct test callers).
    c10::optional<c10::ScalarType> op_dtype = c10::nullopt
);

// Public access to the tensor rgmma helper.
// Fortran rgmma(x) = exp(GAMMLN(x)) = Γ(x). Used by progb_param_torch internally;
// exposed for regression testing and any caller that needs the tensor variant.
// Input is clamped to >= constants::EPS to keep lgamma defined for x→0.
torch::Tensor rgmma_tensor(const torch::Tensor& x);

}  // namespace progb
}  // namespace kdm6
