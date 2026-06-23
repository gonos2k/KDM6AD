#include "kdm6/state.h"

#include <cstring>

namespace kdm6 {

// ── state-algebra ───────────────────────────────────────────────────────────
State zeros_like_state(const State& s) {
    State z;
    auto src = s.fields();
    auto dst = z.fields();
    for (size_t i = 0; i < src.size(); ++i) {
        *dst[i] = torch::zeros_like(*src[i]);
    }
    return z;
}

torch::Tensor state_dot(const State& a, const State& b) {
    auto af = a.fields();
    auto bf = b.fields();
    auto total = torch::zeros({}, af[0]->options());
    for (size_t i = 0; i < af.size(); ++i) {
        total = total + (*af[i] * *bf[i]).sum();
    }
    return total;
}

State map_state(const State& s, const std::function<torch::Tensor(const torch::Tensor&)>& fn) {
    State r;
    auto src = s.fields();
    auto dst = r.fields();
    for (size_t i = 0; i < src.size(); ++i) {
        *dst[i] = fn(*src[i]);
    }
    return r;
}

// ── Fortran adapter ─────────────────────────────────────────────────────────
//
// Fortran의 arr(im, kme, jme)는 column-major로 저장된다.
// offset(arr(i, k, j)) = i + im * (k + kme * j)  [0-based]
// 따라서 raw double*를 C-order로 읽으면 logical shape은 (jme, kme, im)이다.
// 이를 torch::from_blob({jme, kme, im}).permute({2, 1, 0})로 복구하면
// Python oracle이 기대하는 (im, kme, jme) tensor가 된다.
//
// 예: arr(2, 3, 2), value(i, k, j) = 100*i + 10*k + j
// Fortran offsets:
//   0: arr(0,0,0)=0    1: arr(1,0,0)=100
//   2: arr(0,1,0)=10   3: arr(1,1,0)=110
//   4: arr(0,2,0)=20   5: arr(1,2,0)=120
//   6: arr(0,0,1)=1    7: arr(1,0,1)=101
//   8: arr(0,1,1)=11   9: arr(1,1,1)=111
//  10: arr(0,2,1)=21  11: arr(1,2,1)=121
// Python/C++ flat(B, K) with B = i*jme + j must therefore be:
//   B=0 (i=0,j=0): [0, 10, 20]
//   B=1 (i=0,j=1): [1, 11, 21]
//   B=2 (i=1,j=0): [100, 110, 120]
//   B=3 (i=1,j=1): [101, 111, 121]
static torch::Tensor from_blob_3d(const float* ptr, int im, int kme, int jme,
                                  bool requires_grad,
                                  bool nan_gate,
                                  bool clip_neg,
                                  bool is_th /*th는 clip_neg 면제*/) {
    // [C4] non-owning view — NATIVE float32 operational ABI (matches Fortran RWORDSIZE=4);
    // dtype propagates so the whole kdm6_fn forward runs single, like Fortran mp37.
    auto opts = torch::TensorOptions().dtype(torch::kFloat32);
    auto view3d = torch::from_blob(const_cast<float*>(ptr),
                                   {jme, kme, im},
                                   opts)
                      .permute({2, 1, 0})
                      .contiguous();
    // (im, kme, jme) → (im, jme, kme) → (B=im*jme, kme)
    auto flat = view3d.permute({0, 2, 1}).reshape({im * jme, kme});

    // [D10] NaN gate (optional)
    if (nan_gate) {
        flat = torch::where(torch::isfinite(flat), flat, torch::zeros_like(flat));
    }
    // [D11] clip_neg (optional, th 제외)
    if (clip_neg && !is_th) {
        flat = torch::clamp(flat, /*min=*/0.0);
    }
    // [D9] requires_grad — leaf clone
    if (requires_grad) {
        flat = flat.detach().clone().requires_grad_(true);
    } else {
        // owning copy (graph 외부에서 안전)
        flat = flat.clone();
    }
    return flat;
}

State from_fortran_arrays(const FortranArrayDescriptor& d,
                          bool requires_grad,
                          bool nan_gate,
                          bool clip_neg) {
    State s;
    s.th   = from_blob_3d(d.th,   d.im, d.kme, d.jme, requires_grad, nan_gate, clip_neg, /*is_th=*/true);
    s.qv   = from_blob_3d(d.qv,   d.im, d.kme, d.jme, requires_grad, nan_gate, clip_neg, false);
    s.qc   = from_blob_3d(d.qc,   d.im, d.kme, d.jme, requires_grad, nan_gate, clip_neg, false);
    s.qr   = from_blob_3d(d.qr,   d.im, d.kme, d.jme, requires_grad, nan_gate, clip_neg, false);
    s.qi   = from_blob_3d(d.qi,   d.im, d.kme, d.jme, requires_grad, nan_gate, clip_neg, false);
    s.qs   = from_blob_3d(d.qs,   d.im, d.kme, d.jme, requires_grad, nan_gate, clip_neg, false);
    s.qg   = from_blob_3d(d.qg,   d.im, d.kme, d.jme, requires_grad, nan_gate, clip_neg, false);
    s.nccn = from_blob_3d(d.nccn, d.im, d.kme, d.jme, requires_grad, nan_gate, clip_neg, false);
    s.nc   = from_blob_3d(d.nc,   d.im, d.kme, d.jme, requires_grad, nan_gate, clip_neg, false);
    s.ni   = from_blob_3d(d.ni,   d.im, d.kme, d.jme, requires_grad, nan_gate, clip_neg, false);
    s.nr   = from_blob_3d(d.nr,   d.im, d.kme, d.jme, requires_grad, nan_gate, clip_neg, false);
    s.bg   = from_blob_3d(d.bg,   d.im, d.kme, d.jme, requires_grad, nan_gate, clip_neg, false);
    return s;
}

Forcing forcing_from_fortran_arrays(const float* rho,
                                    const float* pii,
                                    const float* p,
                                    const float* delz,
                                    int im,
                                    int kme,
                                    int jme) {
    Forcing forcing;
    forcing.rho = from_blob_3d(rho, im, kme, jme, /*requires_grad=*/false,
                               /*nan_gate=*/false, /*clip_neg=*/false, /*is_th=*/false);
    forcing.pii = from_blob_3d(pii, im, kme, jme, /*requires_grad=*/false,
                               /*nan_gate=*/false, /*clip_neg=*/false, /*is_th=*/false);
    forcing.p = from_blob_3d(p, im, kme, jme, /*requires_grad=*/false,
                             /*nan_gate=*/false, /*clip_neg=*/false, /*is_th=*/false);
    forcing.delz = from_blob_3d(delz, im, kme, jme, /*requires_grad=*/false,
                                /*nan_gate=*/false, /*clip_neg=*/false, /*is_th=*/false);
    return forcing;
}

void copy_back_to_fortran(const torch::Tensor& flat /*(B, K)*/,
                          int im, int jme,
                          float* out /*(im, kme, jme)*/) {
    auto K = flat.size(1);
    // Recover logical (im, kme, jme), then emit row-major (jme, kme, im)
    // so memcpy lands in the same byte order that Fortran uses for
    // arr(im, kme, jme) column-major storage. NATIVE float32 (cast in case the
    // tensor is fp64 from a differentiable path; operational path is already float32).
    auto view3d = flat.detach().to(torch::kFloat32)
                      .reshape({im, jme, K})
                      .permute({0, 2, 1})
                      .permute({2, 1, 0})
                      .contiguous();
    auto* src = view3d.data_ptr<float>();
    std::memcpy(out, src, sizeof(float) * im * K * jme);
}

void to_fortran_arrays(const State& s, int im, int jme,
                       float* th_out, float* qv_out, float* qc_out,
                       float* qr_out, float* qi_out, float* qs_out,
                       float* qg_out, float* nccn_out, float* nc_out,
                       float* ni_out, float* nr_out, float* bg_out) {
    copy_back_to_fortran(s.th,   im, jme, th_out);
    copy_back_to_fortran(s.qv,   im, jme, qv_out);
    copy_back_to_fortran(s.qc,   im, jme, qc_out);
    copy_back_to_fortran(s.qr,   im, jme, qr_out);
    copy_back_to_fortran(s.qi,   im, jme, qi_out);
    copy_back_to_fortran(s.qs,   im, jme, qs_out);
    copy_back_to_fortran(s.qg,   im, jme, qg_out);
    copy_back_to_fortran(s.nccn, im, jme, nccn_out);
    copy_back_to_fortran(s.nc,   im, jme, nc_out);
    copy_back_to_fortran(s.ni,   im, jme, ni_out);
    copy_back_to_fortran(s.nr,   im, jme, nr_out);
    copy_back_to_fortran(s.bg,   im, jme, bg_out);
}

}  // namespace kdm6
