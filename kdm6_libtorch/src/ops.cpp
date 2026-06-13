#include "kdm6/fconst.h"
#include "kdm6/ops.h"

#include <c10/core/InferenceMode.h>
#include <cmath>

namespace kdm6 {
namespace ops {

namespace {

// Plain element-wise libm forwards (float32) / torch native (float64). The float32 forward
// bit-matches gfortran (Apple libSystem_m == libgfortran math); IEEE-754 does NOT require
// correctly-rounded exp/log/pow, which is why torch Sleef differs at the last bit.
inline torch::Tensor exp_fwd(const torch::Tensor& x) {
    if (x.scalar_type() == torch::kFloat32) {
        auto xc = x.contiguous(); auto out = torch::empty_like(xc);
        const float* xp = xc.data_ptr<float>(); float* op = out.data_ptr<float>();
        const int64_t n = xc.numel();
        for (int64_t i = 0; i < n; ++i) op[i] = std::exp(xp[i]);
        return out;
    }
    return x.exp();
}
inline torch::Tensor log_fwd(const torch::Tensor& x) {
    if (x.scalar_type() == torch::kFloat32) {
        auto xc = x.contiguous(); auto out = torch::empty_like(xc);
        const float* xp = xc.data_ptr<float>(); float* op = out.data_ptr<float>();
        const int64_t n = xc.numel();
        for (int64_t i = 0; i < n; ++i) op[i] = std::log(xp[i]);
        return out;
    }
    return x.log();
}
inline torch::Tensor pow_fwd(const torch::Tensor& x, double p) {
    if (x.scalar_type() == torch::kFloat32) {
        auto xc = x.contiguous(); auto out = torch::empty_like(xc);
        const float* xp = xc.data_ptr<float>(); float* op = out.data_ptr<float>();
        const float pf = static_cast<float>(p); const int64_t n = xc.numel();
        for (int64_t i = 0; i < n; ++i) op[i] = std::pow(xp[i], pf);
        return out;
    }
    return x.pow(p);
}
inline torch::Tensor pow_fwd(const torch::Tensor& x, const torch::Tensor& y) {
    if (x.scalar_type() == torch::kFloat32) {
        auto xc = x.contiguous(); auto yc = y.expand_as(x).contiguous();
        auto out = torch::empty_like(xc);
        const float* xp = xc.data_ptr<float>(); const float* yp = yc.data_ptr<float>();
        float* op = out.data_ptr<float>(); const int64_t n = xc.numel();
        for (int64_t i = 0; i < n; ++i) op[i] = std::pow(xp[i], yp[i]);
        return out;
    }
    return x.pow(y);
}

// Custom autograd Functions wrap the plain libm forwards with an analytic backward, so the
// differentiable graph is preserved. Used only when grad is on AND not inference (operational
// path runs under c10::InferenceMode where Function::apply on inference tensors SIGSEGVs).
struct LibmExp : public torch::autograd::Function<LibmExp> {
    static torch::Tensor forward(torch::autograd::AutogradContext* ctx, torch::Tensor x) {
        ctx->save_for_backward({x}); return exp_fwd(x);
    }
    static torch::autograd::tensor_list backward(torch::autograd::AutogradContext* ctx,
                                                 torch::autograd::tensor_list go) {
        return {go[0] * ctx->get_saved_variables()[0].exp()};
    }
};
inline torch::Tensor rgmma_fwd(const torch::Tensor& x) {
    // Fortran rgmma(x) = EXP(GAMMLN(x)) per CELL (ProgB per-cell gamma family):
    // GAMMLN is the f32-return double-Lanczos (fconst::gammln_f) and EXP is expf.
    // torch::lgamma f32 (Sleef lgammaf) differs from the Fortran GAMMLN mirror —
    // route the f32 path through fconst::rgmma_f elementwise. f64 (oracle) path
    // keeps exp(lgamma) — mirrors the Python oracle exactly.
    if (x.scalar_type() == torch::kFloat32) {
        auto xc = x.contiguous(); auto out = torch::empty_like(xc);
        const float* xp = xc.data_ptr<float>(); float* op = out.data_ptr<float>();
        const int64_t n = xc.numel();
        for (int64_t i = 0; i < n; ++i) op[i] = fconst::rgmma_f(xp[i]);
        return out;
    }
    return torch::exp(torch::lgamma(x));
}
struct LibmLog : public torch::autograd::Function<LibmLog> {
    static torch::Tensor forward(torch::autograd::AutogradContext* ctx, torch::Tensor x) {
        ctx->save_for_backward({x}); return log_fwd(x);
    }
    static torch::autograd::tensor_list backward(torch::autograd::AutogradContext* ctx,
                                                 torch::autograd::tensor_list go) {
        return {go[0] / ctx->get_saved_variables()[0]};
    }
};
struct LibmPowScalar : public torch::autograd::Function<LibmPowScalar> {
    static torch::Tensor forward(torch::autograd::AutogradContext* ctx, torch::Tensor x, double p) {
        ctx->saved_data["p"] = p; ctx->save_for_backward({x}); return pow_fwd(x, p);
    }
    static torch::autograd::tensor_list backward(torch::autograd::AutogradContext* ctx,
                                                 torch::autograd::tensor_list go) {
        auto x = ctx->get_saved_variables()[0]; const double p = ctx->saved_data["p"].toDouble();
        return {go[0] * p * x.pow(p - 1.0), torch::Tensor()};
    }
};

struct LibmPowTensor : public torch::autograd::Function<LibmPowTensor> {
    static torch::Tensor forward(torch::autograd::AutogradContext* ctx, torch::Tensor x, torch::Tensor y) {
        ctx->save_for_backward({x, y}); return pow_fwd(x, y);
    }
    static torch::autograd::tensor_list backward(torch::autograd::AutogradContext* ctx,
                                                 torch::autograd::tensor_list go) {
        auto s = ctx->get_saved_variables(); auto x = s[0], y = s[1];
        return {go[0] * y * x.pow(y - 1.0), go[0] * x.pow(y) * torch::log(x)};
    }
};

struct RgmmaT : public torch::autograd::Function<RgmmaT> {
    static torch::Tensor forward(torch::autograd::AutogradContext* ctx, torch::Tensor x) {
        auto out = rgmma_fwd(x);
        ctx->save_for_backward({x, out});
        return out;
    }
    static torch::autograd::tensor_list backward(torch::autograd::AutogradContext* ctx,
                                                 torch::autograd::tensor_list go) {
        auto saved = ctx->get_saved_variables();
        // d/dx Gamma(x) = Gamma(x) * digamma(x)
        return {go[0] * saved[1] * torch::digamma(saved[0])};
    }
};
inline bool use_custom_autograd(const torch::Tensor& x) {
    return at::GradMode::is_enabled() && !c10::InferenceMode::is_enabled() && x.requires_grad();
}
inline bool use_custom_autograd(const torch::Tensor& x, const torch::Tensor& y) {
    return at::GradMode::is_enabled() && !c10::InferenceMode::is_enabled()
           && (x.requires_grad() || y.requires_grad());
}

}  // namespace

// libm exp/log (float32 forward bit-matches gfortran; float64 -> torch native). Plain forward on
// the no-grad/inference operational path, autograd Function when differentiable (graph-preserving).
torch::Tensor libm_exp(const torch::Tensor& x) {
    return use_custom_autograd(x) ? LibmExp::apply(x) : exp_fwd(x);
}
// Strict-IEEE two-rounding accumulate: acc + value*t1*t2 with every op
// individually rounded, in gfortran -ffp-contract=off source order:
// (value*t1) rounds (exact for value=+-1), *t2 rounds, +acc rounds.
// HISTORY: this used to emit a guaranteed single-rounding std::fmaf per
// element (custom autograd Function) to mirror -ffp-contract=fast, after the
// step-44 seed showed torch::addcmul fuses shape-dependently (scalar tail
// fused, SIMD body not — 0x4EAD0F17 vs 0x4EAD0F18 on the same cell). The
// IEEE transition compiles both mp modules with -ffp-contract=off
// (configure.wrf per-file rules), so the strict two-rounding form below is
// now the bitwise-correct mirror — and being plain tensor ops it is
// autograd/InferenceMode-native (no custom Function needed).
torch::Tensor fma_acc(const torch::Tensor& acc, const torch::Tensor& t1,
                      const torch::Tensor& t2, double value) {
    if (value == 1.0)  return acc + t1 * t2;
    if (value == -1.0) return acc - t1 * t2;
    return acc + (t1 * value) * t2;
}

torch::Tensor libm_log(const torch::Tensor& x) {
    return use_custom_autograd(x) ? LibmLog::apply(x) : log_fwd(x);
}

torch::Tensor rgmma_t(const torch::Tensor& x) {
    return use_custom_autograd(x) ? RgmmaT::apply(x) : rgmma_fwd(x);
}

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

// [D3] scalar exponent — libm pow on the float32 operational path (bit-matches gfortran), torch
// native on float64 (oracle/parity unchanged). Clamp stays outside for correct clamp gradient.
torch::Tensor safe_pow(const torch::Tensor& x, double y) {
    auto xc = torch::clamp(x, /*min=*/constants::EPS);
    return use_custom_autograd(xc) ? LibmPowScalar::apply(xc, y) : pow_fwd(xc, y);
}

// [D3] tensor exponent — libm pow on float32 operational path (matches gfortran), torch native fp64.
torch::Tensor safe_pow(const torch::Tensor& x, const torch::Tensor& y) {
    auto xc = torch::clamp(x, /*min=*/constants::EPS);
    return use_custom_autograd(xc, y) ? LibmPowTensor::apply(xc, y) : pow_fwd(xc, y);
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
