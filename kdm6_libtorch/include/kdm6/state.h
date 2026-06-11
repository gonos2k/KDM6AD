#pragma once
//
// KDM6 state vector — Python kdm6_torch/kdm6/state.py와 1:1 정합.
// (B, K) 텐서 layout, 12 prognostic + 4 forcing.
//
#include <torch/torch.h>
#include <functional>

namespace kdm6 {

// ── 12 prognostic 필드 (D8 NamedTuple ↔ C++ struct) ────────────────────────
struct State {
    torch::Tensor th;
    torch::Tensor qv;
    torch::Tensor qc;
    torch::Tensor qr;
    torch::Tensor qi;
    torch::Tensor qs;
    torch::Tensor qg;
    torch::Tensor nccn;
    torch::Tensor nc;
    torch::Tensor ni;
    torch::Tensor nr;
    torch::Tensor bg;

    // 텐서 12개를 순회 가능하게 ─ map_state, state_dot 구현용
    std::array<torch::Tensor*, 12> fields() {
        return {&th, &qv, &qc, &qr, &qi, &qs, &qg, &nccn, &nc, &ni, &nr, &bg};
    }
    std::array<const torch::Tensor*, 12> fields() const {
        return {&th, &qv, &qc, &qr, &qi, &qs, &qg, &nccn, &nc, &ni, &nr, &bg};
    }
};

// ── 4 forcing 필드 (보통 grad off) ─────────────────────────────────────────
struct Forcing {
    torch::Tensor rho;
    torch::Tensor pii;
    torch::Tensor p;
    torch::Tensor delz;
};

// ── state-algebra 헬퍼 ─────────────────────────────────────────────────────
State zeros_like_state(const State& s);
torch::Tensor state_dot(const State& a, const State& b);
State map_state(const State& s, const std::function<torch::Tensor(const torch::Tensor&)>& fn);

// ── Fortran-style array adapter ────────────────────────────────────────────
//
// [C4] Fortran의 (im, kme, jme) 배열을 zero-copy로 (B=im*jme, K=kme) 텐서로 변환.
// `requires_grad=true`이면 leaf clone 생성.
//
struct FortranArrayDescriptor {
    const float* th;
    const float* qv;
    const float* qc;
    const float* qr;
    const float* qi;
    const float* qs;
    const float* qg;
    const float* nccn;
    const float* nc;
    const float* ni;
    const float* nr;
    const float* bg;
    int im;
    int kme;
    int jme;
};

State from_fortran_arrays(const FortranArrayDescriptor& d,
                          bool requires_grad = true,
                          bool nan_gate = false,
                          bool clip_neg = false);

Forcing forcing_from_fortran_arrays(const float* rho,
                                    const float* pii,
                                    const float* p,
                                    const float* delz,
                                    int im,
                                    int kme,
                                    int jme);

void to_fortran_arrays(const State& state,
                       int im, int jme,
                       /* output buffers, caller-allocated */
                       float* th_out, float* qv_out, float* qc_out,
                       float* qr_out, float* qi_out, float* qs_out,
                       float* qg_out, float* nccn_out, float* nc_out,
                       float* ni_out, float* nr_out, float* bg_out);

}  // namespace kdm6
