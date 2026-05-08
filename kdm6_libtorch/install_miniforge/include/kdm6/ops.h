#pragma once
//
// torch-safe operation idioms — Python kdm6_torch/kdm6/ops.py와 1:1 정합 필요.
// (Python oracle 검증 게이트가 같은 입력에 대해 같은 출력을 강제)
//
// 결정:
//   [D1]  safe_div_pos    = num / clamp(denom, min=EPS)
//   [D1b] safe_div_signed = sign-preserving |denom| floor
//   [D1c] safe_div        = safe_div_pos alias (호환)
//   [D2]  safe_sqrt       = sqrt(clamp(x, min=EPS))
//   [D3]  safe_pow        = clamp(x, min=EPS).pow(y)
//   [D4]  clip_positive   = clamp(x, min=0)
//   [D5]  smooth_minmod   = eager 또는 smoothed (별도 SMOOTH_EPS)
//   [D6]  EPS = constants::EPS = 1.0e-15
//   [D6b] SMOOTH_EPS = constants::SMOOTH_EPS = 1.0e-4
//
#include <torch/torch.h>
#include "constants.h"

namespace kdm6 {
namespace ops {

torch::Tensor safe_div_pos(const torch::Tensor& num, const torch::Tensor& denom);

torch::Tensor safe_div_signed(const torch::Tensor& num,
                              const torch::Tensor& denom,
                              double floor = constants::EPS);

inline torch::Tensor safe_div(const torch::Tensor& num, const torch::Tensor& denom) {
    return safe_div_pos(num, denom);  // [D1c] 호환 alias
}

torch::Tensor safe_sqrt(const torch::Tensor& x);

torch::Tensor safe_pow(const torch::Tensor& x, double y);
torch::Tensor safe_pow(const torch::Tensor& x, const torch::Tensor& y);

torch::Tensor clip_positive(const torch::Tensor& x);

enum class MinmodMode { Eager, Smoothed };

torch::Tensor smooth_minmod(const torch::Tensor& a,
                            const torch::Tensor& b,
                            MinmodMode mode = MinmodMode::Eager,
                            double smooth_eps = constants::SMOOTH_EPS);

torch::Tensor isfinite_else(const torch::Tensor& x, double fallback = 0.0);

}  // namespace ops
}  // namespace kdm6
