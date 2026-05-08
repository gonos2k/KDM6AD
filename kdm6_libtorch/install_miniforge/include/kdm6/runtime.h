#pragma once
//
// KDM6 PyTorch C++ runtime — Python kdm6_torch/kdm6/runtime.py의 C++ 등가물.
// G1-G7 결정 동일하게 적용.
//
#include "kdm6/constants.h"
#include "state.h"
#include <memory>

namespace kdm6 {

// ── [G4] Parameters — opt-in 미분가능 파라미터 ─────────────────────────────
struct Parameters {
    torch::Tensor peaut;
    torch::Tensor ncrk1;
    torch::Tensor ncrk2;
    torch::Tensor eccbrk;
};

// 파라미터 grad 비트마스크 (ABI 호환)
namespace ParamGradFlags {
inline constexpr int PEAUT  = 1 << 0;
inline constexpr int NCRK1  = 1 << 1;
inline constexpr int NCRK2  = 1 << 2;
inline constexpr int ECCBRK = 1 << 3;
inline constexpr int ALL    = PEAUT | NCRK1 | NCRK2 | ECCBRK;
}  // namespace ParamGradFlags

Parameters make_parameters(int grad_flags = 0,
                           torch::Device device = torch::kCPU,
                           torch::Dtype dtype = torch::kFloat64);

// ── [G1] Pure function: dynamic graph 통과 ─────────────────────────────────
//
// 1차 prototype 단계에서는 NotImplementedError-equivalent (TORCH_CHECK fails).
// slope/core/sedimentation 모듈이 채워지면 본 함수가 그 합성.
//
State kdm6_fn(const State& state,
              const Forcing& forcing,
              const Parameters& params,
              double dt);

// ── [G3] Handle — vjp/jvp/jacobian 인터페이스 ──────────────────────────────
class Handle {
public:
    Handle(State state_in,
           State state_out,
           Forcing forcing,
           Parameters params,
           double dt,
           bool value_only);
    ~Handle();

    // 비복사 — Handle은 unique 소유 의도
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    Handle(Handle&&) noexcept;
    Handle& operator=(Handle&&) noexcept;

    // [G3] Derivative API
    State vjp(const State& u) const;
    State jvp(const State& v) const;
    // jacobian / param_grad — 후행 추가

    // [G6] RAII close — 명시적 해제
    void close();
    bool is_closed() const noexcept;
    bool is_value_only() const noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

// ── [G3] Public entry point ────────────────────────────────────────────────
//
// (state_out, handle) = kdm6_step(state, forcing, params, dt, value_only)
// Python prototype의 kdm6_step과 동일 의미.
//
struct StepResult {
    State state_out;
    std::unique_ptr<Handle> handle;
};

StepResult kdm6_step(const State& state,
                     const Forcing& forcing,
                     const Parameters& params,
                     double dt = 60.0,
                     bool value_only = false);

}  // namespace kdm6
