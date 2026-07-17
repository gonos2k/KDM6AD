#pragma once
//
// KDM6 PyTorch C++ runtime — Python kdm6_torch/kdm6/runtime.py의 C++ 등가물.
// G1-G7 결정 동일하게 적용.
//
#include "kdm6/constants.h"
#include "kdm6/coordinator.h"
#include "state.h"
#include <memory>

namespace kdm6 {

// Test-only helper — NOT part of the stable public API despite living in this
// installed header. Kept under `kdm6::testing` so external consumers cannot
// mistake it for a supported entry point (it is no longer found as
// `kdm6::build_default_aux_for_test`). Used by the aux-port regression test to
// verify the actual values the operational path installs (so the test breaks
// when build_default_aux is rewired to physics, instead of silently passing
// against hardcoded literals).
namespace testing {
CoordinatorAuxDiagnostics build_default_aux_for_test(
    const State& s, const Forcing& f);
}  // namespace testing

// ── [G4] Parameters — opt-in 미분가능 파라미터 ─────────────────────────────
//
// RESERVED / NOT WIRED. Physics-parameter sensitivity is not yet connected to the
// forward graph: kdm6_fn consumes baked-in constants and IGNORES `params` (see
// runtime.cpp). Building requires_grad parameter leaves via make_parameters(flags != 0)
// therefore has NO effect on any gradient — only STATE leaves are differentiable today.
// To avoid a silent "flag set, no effect" trap, kdm6_step() fast-fails (TORCH_CHECK) if
// any Parameters tensor requires grad, and the C ABI rejects param_grad_flags != 0
// (KDM6_ERR_NOT_IMPLEMENTED). These types are kept for a future param-grad ABI.
struct Parameters {
    torch::Tensor peaut;
    torch::Tensor ncrk1;
    torch::Tensor ncrk2;
    torch::Tensor eccbrk;
};

// 파라미터 grad 비트마스크 (ABI 호환) — RESERVED (see Parameters note above).
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
// Physics options (docs/FREEZE_LIFT_CONSERVATIVE_INTERFACE_V1.md).
// `variant` selects the sedimentation interface-transfer physics: Legacy
// (bitwise-identical to every pre-existing call path) or ConservativeInterface
// (the freeze-lifted conservative variant; oracle reference
// oracle/kdm6/sed_conservative.py). Selection is a separate kdm6_fn/kdm6_step
// OVERLOAD, not a defaulted trailing parameter: default arguments are
// caller-compile-time, so already-compiled C++ objects linking the installed
// kdm6 archive keep referencing the pre-variant mangled symbols. Those exact
// signatures are preserved below as thin overloads that forward here with
// PhysicsOptions{} (Legacy); the options overload has NO default argument and
// fail-louds (TORCH_CHECK) on any PhysicsVariant value it does not know.
struct PhysicsOptions {
    PhysicsVariant variant = PhysicsVariant::Legacy;
};

// Pure differentiable forward result — state + sedimentation increments.
// The increments are computed inside kdm6_fn via sedimentation_chain (after
// kdm62d_step) so they participate in the autograd graph alongside state.
struct FnResult {
    State state_out;
    torch::Tensor rain_increment;     // (im*jme,) [mm]
    torch::Tensor snow_increment;
    torch::Tensor graupel_increment;
    torch::Tensor rhog;               // (im*jme, kme) graupel density [kg m^-3] → WRF diag_rhog/RHOPO3D
};

// Legacy-signature overload — EXACT pre-variant signature (stable mangled
// symbol for already-compiled callers); forwards to the options overload with
// PhysicsOptions{} (Legacy).
FnResult kdm6_fn(const State& state,
                 const Forcing& forcing,
                 const Parameters& params,
                 double dt,
                 const c10::optional<torch::Tensor>& xland = c10::nullopt,
                 double ncmin_land = 0.0,
                 double ncmin_sea = 0.0);

// Options overload — explicit physics-variant selection. NO defaults: a
// defaulted trailing PhysicsOptions would silently re-route legacy call sites
// to a new mangled symbol on recompile.
FnResult kdm6_fn(const State& state,
                 const Forcing& forcing,
                 const Parameters& params,
                 double dt,
                 const c10::optional<torch::Tensor>& xland,
                 double ncmin_land,
                 double ncmin_sea,
                 const PhysicsOptions& physics);

// ── [G3] GraphOptions — DA derivative-call options (kdm6ad+da.md §8.1/§8.2) ──
//
// active_field_mask: bit i = State::fields()[i] (packed order th,qv,qc,qr,qi,
// qs,qg,nccn,nc,ni,nr,bg — kdm6ad+da.md §6.4). 0x0FFF = all 12 fields active.
// Semantics (adversarial review F1-MASK-ADJOINT-ASYM): vjp masks its OUTPUT
// grad (P∘J^T); jvp masks its INPUT direction (J∘P) — so the SAME mask on both
// sides forms an exactly-adjoint TL/AD pair: <J P v, u> = <v, P J^T u>.
// NOTE: only RecordGraph is implemented. The other modes are RESERVED design
// placeholders — Handle::vjp/jvp fast-fail (TORCH_CHECK) on any mode != RecordGraph
// rather than silently ignoring it. Graph recording vs value-only is selected by the
// `value_only` flag at kdm6_step time, not by this enum.
enum class GraphMode : int {
    ValueOnly = 0,
    RecordGraph = 1,
    LocalGraphForVjp = 2,        // reserved — not implemented
    CheckpointRecompute = 3,     // reserved — not implemented
    DiagnosticFullGraph = 4,     // reserved — not implemented
};

struct GraphOptions {
    GraphMode mode = GraphMode::RecordGraph;
    uint32_t active_field_mask = 0x0FFFu;   // all 12 State fields
    bool retain_graph = false;              // default one-shot vjp (DA policy §6.2)
    bool create_graph = false;              // true → grad-of-grad (double-VJP)
};

inline constexpr uint32_t kAllStateFields = 0x0FFFu;

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

    // [G3] Derivative API (kdm6ad+da.md §6.2/§7.2).
    // vjp: J^T u — scalar = state_dot(state_out, u); torch::autograd::grad to the
    //      state_in leaves. u field shapes must EQUAL state_out shapes (validated
    //      BEFORE autograd — broadcasting silently corrupts the adjoint).
    // jvp: J v via the double-VJP/Pearlmutter route (torch.func-style forward AD
    //      is NOT used — custom Functions lack forward-mode rules; §0.1.B).
    //      Repeat-callable (the forward graph is retained). v is INPUT-masked.
    State vjp(const State& u, const GraphOptions& opts = {}) const;
    State jvp(const State& v, const GraphOptions& opts = {}) const;
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
    // Sedimentation surface increments — populated by runtime kdm6_fn after
    // sedimentation_chain runs (see runtime.cpp). Shape (im*jme,) [mm] — one
    // value per column. Optional (zero tensors when sedimentation produced no
    // fallout) — caller can ignore if not consuming precip diagnostics.
    torch::Tensor rain_increment;
    torch::Tensor snow_increment;
    torch::Tensor graupel_increment;
    torch::Tensor rhog;               // (im*jme, kme) graupel density [kg m^-3] → WRF diag_rhog/RHOPO3D
};

// `xland`: optional Tensor with values 1 (land) or 2 (sea). Accepted shapes:
//   - (im, jme) 2-D — preferred for direct C++ callers
//   - (im*jme,) 1-D — what the C ABI flattens to before invoking runtime
// Runtime reshapes via `.view({-1})` so either layout works.
// Convention: xland >= 1.5 → sea, else land (WRF slmsk).
// When set, runtime derives sea_mask from xland (replacing the all-true
// fallback at runtime.cpp `kdm6_fn`) AND builds a per-cell ncmin tensor:
//   ncmin_eff(i,j) = (xland(i,j) >= 1.5) ? ncmin_sea : ncmin_land
// `sea_mask` is broadcast to (im*jme, kme) so cloud_dsd::diag_qcr_torch and
// other consumers see per-cell values. The per-cell `ncmin_tensor` is injected
// into the Phase Params' `ncmin_tensor` field (see warm.h, cold.h, melt_freeze.h).
// When `xland == nullopt`, the function preserves the pre-extension behavior
// (sea_mask all-true, scalar constants::NCMIN in every Params struct).
// Legacy-signature overload — EXACT pre-variant signature (stable mangled
// symbol for already-compiled callers); forwards to the options overload with
// PhysicsOptions{} (Legacy). The v1 C bridge and kdm6_step_ad_c bind here.
StepResult kdm6_step(const State& state,
                     const Forcing& forcing,
                     const Parameters& params,
                     double dt = 60.0,
                     bool value_only = false,
                     const c10::optional<torch::Tensor>& xland = c10::nullopt,
                     double ncmin_land = 0.0,
                     double ncmin_sea = 0.0);

// Options overload — explicit physics-variant selection (v2 C bridge binds
// here). NO defaults (see kdm6_fn note). Fail-louds (TORCH_CHECK) at entry on
// any PhysicsVariant value it does not know — an unknown selector must never
// silently run legacy.
StepResult kdm6_step(const State& state,
                     const Forcing& forcing,
                     const Parameters& params,
                     double dt,
                     bool value_only,
                     const c10::optional<torch::Tensor>& xland,
                     double ncmin_land,
                     double ncmin_sea,
                     const PhysicsOptions& physics);

}  // namespace kdm6
