#include "kdm6/ops.h"

namespace kdm6 {
namespace ops {

// [D1] 양수 분모 전용
torch::Tensor safe_div_pos(const torch::Tensor& num, const torch::Tensor& denom) {
    return num / torch::clamp(denom, /*min=*/constants::EPS);
}

// [D1b] 부호 보존 floor
torch::Tensor safe_div_signed(const torch::Tensor& num,
                              const torch::Tensor& denom,
                              double floor) {
    if (floor <= 0.0) {
        TORCH_CHECK(false, "floor must be > 0, got ", floor);
    }
    auto floor_t = torch::full_like(denom, floor);
    auto sign    = torch::where(denom != 0, torch::sign(denom), torch::ones_like(denom));
    auto safe    = torch::where(denom.abs() < floor_t, sign * floor_t, denom);
    return num / safe;
}

// [D2]
torch::Tensor safe_sqrt(const torch::Tensor& x) {
    return torch::sqrt(torch::clamp(x, /*min=*/constants::EPS));
}

// [D3] scalar exponent
torch::Tensor safe_pow(const torch::Tensor& x, double y) {
    return torch::clamp(x, /*min=*/constants::EPS).pow(y);
}

// [D3] tensor exponent
torch::Tensor safe_pow(const torch::Tensor& x, const torch::Tensor& y) {
    return torch::clamp(x, /*min=*/constants::EPS).pow(y);
}

// [D4]
torch::Tensor clip_positive(const torch::Tensor& x) {
    return torch::clamp(x, /*min=*/0.0);
}

// [D5]
torch::Tensor smooth_minmod(const torch::Tensor& a,
                            const torch::Tensor& b,
                            MinmodMode mode,
                            double smooth_eps) {
    if (mode == MinmodMode::Eager) {
        auto same_sign = (a * b > 0).to(a.dtype());
        return same_sign * torch::sign(a) * torch::minimum(a.abs(), b.abs());
    }
    // Smoothed
    if (smooth_eps <= 0.0) {
        TORCH_CHECK(false, "smooth_eps must be > 0, got ", smooth_eps);
    }
    auto sgn_weight = 0.5 * (torch::tanh((a * b) / smooth_eps) + 1.0);
    return sgn_weight * torch::sign(a) * torch::minimum(a.abs(), b.abs());
}

// ieee NaN gate
torch::Tensor isfinite_else(const torch::Tensor& x, double fallback) {
    return torch::where(torch::isfinite(x), x, torch::full_like(x, fallback));
}

}  // namespace ops
}  // namespace kdm6
