#include "kdm6_c_api.h"
#include "kdm6/runtime.h"
#include "kdm6/state.h"

#include <ATen/Parallel.h>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <dlfcn.h>
#include <exception>
#include <memory>
#include <mutex>
#include <fenv.h>

//
// C ABI ↔ C++ 어댑터.
// 모든 C++ 예외는 *catch all* → int 에러 코드로 변환. 절대 외부로 던지지 않음.
//

extern "C" struct kdm6_handle_t {
    std::unique_ptr<kdm6::Handle> impl;
    // [DA Phase 3] shape metadata for the packed VJP/JVP ABI:
    // packed layout = field-major sequence of FORTRAN (im,kme,jme) column-major
    // double blocks — same convention as the state arrays (field order =
    // State::fields(): th,qv,qc,qr,qi,qs,qg,nccn,nc,ni,nr,bg). See the
    // unpack/pack helpers below; supersedes the kdm6ad+da.md §6.4 (B,K)-C-order
    // sketch, which a Fortran caller could not fill without internal-layout
    // knowledge (Codex stop-review: wrong for nontrivial tiles).
    int im = 0;
    int kme = 0;
    int jme = 0;
    // dtype of the recorded graph (operational kdm6_step_c → Float32; a future
    // fp64 kdm6_step_ad_c → Float64). u/v are cast to this dtype; gradients
    // computed on an f32 graph carry f32 precision even in double buffers
    // (kdm6ad+da.md §0.1.A — the fp64 DA path is the design default).
    c10::ScalarType dtype = c10::ScalarType::Float;
};

namespace {

bool any_null(std::initializer_list<const void*> ptrs) {
    for (auto p : ptrs) {
        if (!p) return true;
    }
    return false;
}

// libtorch/OpenMP single-thread fence.
//
// libkdm6_c depends on libtorch_cpu, and libtorch_cpu depends on libomp, so a
// bridge constructor alone is not a reliable "before libomp" hook. Keep the
// environment defaults for lazy runtime reads, then also call the libomp API
// directly from the first kdm6_step_c entry before any tensor operation.

__attribute__((constructor))
static void kdm6_singlethread_env_fence() {
    // setenv with overwrite=0 respects external user override.
    setenv("OMP_NUM_THREADS", "1", 0);
    setenv("OMP_THREAD_LIMIT", "1", 0);
    setenv("MKL_NUM_THREADS", "1", 0);
    setenv("VECLIB_MAXIMUM_THREADS", "1", 0);
    setenv("KMP_BLOCKTIME", "0", 0);
    setenv("KMP_DUPLICATE_LIB_OK", "TRUE", 0);
}

void call_runtime_setter(const char* name, int value) {
    using setter_t = void (*)(int);
    if (auto* symbol = dlsym(RTLD_DEFAULT, name)) {
        reinterpret_cast<setter_t>(symbol)(value);
    }
}

void ensure_libtorch_singlethread() {
    static std::once_flag flag;
    std::call_once(flag, []() {
        call_runtime_setter("omp_set_dynamic", 0);
        call_runtime_setter("omp_set_num_threads", 1);
        call_runtime_setter("omp_set_max_active_levels", 1);
        call_runtime_setter("kmp_set_blocktime", 0);
        at::set_num_threads(1);
        at::set_num_interop_threads(1);
    });
}

// FP-environment fence (Codex deep-review lead, 2026-06-22): libtorch / its BLAS
// backend can set the denormals-flush (FTZ/FZ) and/or rounding bits in the host
// FP control register, and those LEAK back into the WRF Fortran dynamics that runs
// after this ABI call — diverging the multi-step trajectory even though the 12
// microphysics outputs are bitwise per step. Save the caller's FP env on entry and
// restore it on every return path (RAII) so the host dynamics keeps mp37's env.
// AD-safe: this is FP control only, touches no autograd tensor.
struct FpEnvGuard {
    fenv_t saved_;
    FpEnvGuard() { fegetenv(&saved_); }
    ~FpEnvGuard() { fesetenv(&saved_); }
};

}  // anonymous namespace

extern "C" int kdm6_step_c(
    const float* th, const float* qv, const float* qc, const float* qr,
    const float* qi, const float* qs, const float* qg,
    const float* nccn, const float* nc, const float* ni, const float* nr,
    const float* bg,
    const float* rho, const float* pii, const float* p, const float* delz,
    int im, int kme, int jme, double dt,
    int param_grad_flags, int value_only,
    float* th_out, float* qv_out, float* qc_out, float* qr_out,
    float* qi_out, float* qs_out, float* qg_out,
    float* nccn_out, float* nc_out, float* ni_out, float* nr_out,
    float* bg_out,
    kdm6_handle_t** handle,
    const float* xland,
    double ncmin_land,
    double ncmin_sea,
    float* rain_increment,
    float* snow_increment,
    float* graupel_increment,
    float* rhog_out
) {
    if (im <= 0 || kme <= 0 || jme <= 0) return KDM6_ERR_INVALID_DIM;
    // Note: `xland` deliberately excluded from null check — it's optional.
    if (any_null({th, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg,
                  rho, pii, p, delz,
                  th_out, qv_out, qc_out, qr_out, qi_out, qs_out, qg_out,
                  nccn_out, nc_out, ni_out, nr_out, bg_out, handle})) {
        return KDM6_ERR_NULL_POINTER;
    }

    // RAII: restore the caller's (Fortran host) FP env on every return path.
    // Defensive ABI hygiene — libtorch/its BLAS backend could set FTZ/DAZ/rounding;
    // verified a no-op on this build (ARM FPCR unchanged), kept to insulate the host dynamics.
    FpEnvGuard kdm6_fpenv_guard;

    ensure_libtorch_singlethread();

    try {
        kdm6::FortranArrayDescriptor desc{
            th, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg, im, kme, jme};
        // [C4] requires_grad는 value_only=0일 때만 켬
        bool requires_grad = (value_only == 0);
        auto state_in = kdm6::from_fortran_arrays(desc, requires_grad);

        auto forcing = kdm6::forcing_from_fortran_arrays(rho, pii, p, delz, im, kme, jme);

        auto params = kdm6::make_parameters(param_grad_flags);

        // Optional xland → Tensor conversion (state.cpp layout convention):
        // Fortran xland(im, jme) is column-major float*; C-order view is
        // (jme, im); permute({1, 0}) gives (im, jme); reshape to flat
        // (im*jme,) batch matches state batch index = i*jme + j.
        c10::optional<torch::Tensor> xland_t = c10::nullopt;
        if (xland != nullptr) {
            auto opts = torch::TensorOptions().dtype(torch::kFloat32);
            auto view2d = torch::from_blob(const_cast<float*>(xland),
                                           {jme, im}, opts)
                              .permute({1, 0})
                              .contiguous();
            xland_t = view2d.reshape({im * jme});
        }

        auto result = kdm6::kdm6_step(state_in, forcing, params, dt, value_only != 0,
                                      xland_t, ncmin_land, ncmin_sea);

        kdm6::to_fortran_arrays(result.state_out, im, jme,
                                th_out, qv_out, qc_out, qr_out, qi_out, qs_out, qg_out,
                                nccn_out, nc_out, ni_out, nr_out, bg_out);

        // diag_rhog/RHOPO3D — graupel density from the last ProgB (optional out;
        // NULL → discard). Same (im, kme, jme) column-major layout as bg_out.
        // intent(out) contract: when rhog_out is supplied it is ALWAYS written —
        // zeros if the result tensor is (defensively) undefined — so the Fortran
        // caller never copies uninitialized memory into diag_rhog.
        if (rhog_out != nullptr) {
            if (result.rhog.defined()) {
                kdm6::copy_back_to_fortran(result.rhog, im, jme, rhog_out);
            } else {
                const size_t n_rhog = static_cast<size_t>(im) * kme * jme;
                for (size_t idx = 0; idx < n_rhog; ++idx) rhog_out[idx] = 0.0f;
            }
        }

        // Copy-back sedimentation surface increments — (im*jme,) Tensor →
        // Fortran column-major float*(im, jme). Reuses the same (im, jme) ↔
        // batch-flat layout convention as xland staging (state.cpp:67-72):
        //   batch index B = i*jme + j; Fortran memory = (i, j) column-major.
        // So tensor[B] at index i*jme+j maps to fortran[i + im*j].
        auto copy_increment = [im, jme](const torch::Tensor& inc, float* dst) {
            if (dst == nullptr) return;
            auto inc_cpu = inc.contiguous().to(torch::kCPU, torch::kFloat32);
            auto inc_2d = inc_cpu.reshape({im, jme}); // (im, jme) C-order
            const float* src = inc_2d.data_ptr<float>();
            // Transpose to Fortran (im, jme) column-major: dst[i + im*j] = src[i*jme + j]
            for (int i = 0; i < im; ++i) {
                for (int j = 0; j < jme; ++j) {
                    dst[i + im * j] = src[i * jme + j];
                }
            }
        };
        copy_increment(result.rain_increment,    rain_increment);
        copy_increment(result.snow_increment,    snow_increment);
        copy_increment(result.graupel_increment, graupel_increment);

        if (value_only != 0) {
            *handle = nullptr;
        } else {
            auto* h = new kdm6_handle_t{};
            h->impl = std::move(result.handle);
            h->im = im; h->kme = kme; h->jme = jme;
            h->dtype = c10::ScalarType::Float;   // operational f32 graph
            *handle = h;
        }
        return KDM6_OK;
    } catch (const c10::NotImplementedError&) {
        return KDM6_ERR_NOT_IMPLEMENTED;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "kdm6_step_c: %s\n", e.what());
        return KDM6_ERR_INTERNAL;
    } catch (...) {
        std::fprintf(stderr, "kdm6_step_c: unknown non-std exception\n");
        return KDM6_ERR_INTERNAL;
    }
}

namespace {

// PACKED DERIVATIVE LAYOUT (Codex stop-review fix — "wrong for nontrivial tiles"):
// the packed u/v/grad/tangent buffers use the SAME convention as every other
// array in this ABI — a field-major sequence of FORTRAN (im, kme, jme)
// COLUMN-MAJOR double blocks (field order = State::fields(): th,qv,qc,qr,qi,
// qs,qg,nccn,nc,ni,nr,bg; per-field offset = field*im*kme*jme; within a field,
// element (i,k,j) sits at i + im*k + im*kme*j, exactly like the state arrays).
// The bridge performs the same (jme,kme,im)->(B=i*jme+j, K) staging as
// from_blob_3d (state.cpp) and its inverse on the way out — a Fortran caller
// fills these buffers exactly like its state arrays, no internal-layout
// knowledge required. (The previous draft consumed the internal (B,K) C-order
// directly, which only coincided with this for im=jme=1 tiles.)
kdm6::State unpack_packed_state(const double* packed, int im, int kme, int jme,
                                c10::ScalarType dtype) {
    const int64_t N = static_cast<int64_t>(im) * kme * jme;
    kdm6::State s;
    auto fp = s.fields();
    auto opts = torch::TensorOptions().dtype(torch::kFloat64);
    for (size_t f = 0; f < fp.size(); ++f) {
        // Fortran column-major (im,kme,jme) == C-order (jme,kme,im)
        auto view3d = torch::from_blob(
            const_cast<double*>(packed) + static_cast<int64_t>(f) * N,
            {jme, kme, im}, opts)
                          .permute({2, 1, 0});            // -> (im,kme,jme) logical
        auto flat = view3d.permute({0, 2, 1})              // -> (im,jme,kme)
                          .reshape({static_cast<int64_t>(im) * jme, kme});
        *fp[f] = flat.clone().to(dtype);                   // (B=i*jme+j, K)
    }
    return s;
}

// State (B,K) → packed Fortran column-major double blocks (always written fp64 —
// the DA-side containers; an f32-graph gradient keeps f32 PRECISION inside them).
// Mirrors copy_back_to_fortran (state.cpp) at double precision.
void pack_packed_state(const kdm6::State& s, double* packed,
                       int im, int kme, int jme) {
    const int64_t N = static_cast<int64_t>(im) * kme * jme;
    auto fp = const_cast<kdm6::State&>(s).fields();
    for (size_t f = 0; f < fp.size(); ++f) {
        auto t = fp[f]->detach().to(torch::kFloat64);
        TORCH_CHECK(t.numel() == N, "packed field ", f, " numel mismatch");
        auto fortran_order = t.reshape({im, jme, kme})     // (B,K)->(im,jme,K)
                                 .permute({0, 2, 1})       // -> (im,kme,jme) logical
                                 .permute({2, 1, 0})       // -> (jme,kme,im) C-order
                                 .contiguous();            //  == Fortran col-major bytes
        std::memcpy(packed + static_cast<int64_t>(f) * N,
                    fortran_order.data_ptr<double>(), sizeof(double) * N);
    }
}

}  // namespace

namespace {

// forcing_packed (4 Fortran col-major double blocks: rho,pii,p,delz) → Forcing
// tensors at the requested dtype, staged exactly like unpack_packed_state.
kdm6::Forcing unpack_packed_forcing(const double* packed, int im, int kme, int jme,
                                    c10::ScalarType dtype) {
    const int64_t N = static_cast<int64_t>(im) * kme * jme;
    auto opts = torch::TensorOptions().dtype(torch::kFloat64);
    auto one = [&](int f) {
        auto view3d = torch::from_blob(
            const_cast<double*>(packed) + static_cast<int64_t>(f) * N,
            {jme, kme, im}, opts)
                          .permute({2, 1, 0});
        return view3d.permute({0, 2, 1})
            .reshape({static_cast<int64_t>(im) * jme, kme})
            .clone().to(dtype);
    };
    kdm6::Forcing fc;
    fc.rho = one(0); fc.pii = one(1); fc.p = one(2); fc.delz = one(3);
    return fc;
}

}  // namespace

// NOTE: diag_rhog/RHOPO3D is deliberately NOT part of the adjoint packed ABI.
// rhog is a FORWARD-only diagnostic (graupel density for radar reflectivity), not
// a prognostic state variable and not an adjoint quantity — 4D-Var never needs its
// gradient. It is exposed solely on the forward operational path (kdm6_step_c's
// rhog_out). state_out_packed here carries only the prognostic state.
extern "C" int kdm6_step_ad_c(
    const double* state_in_packed,
    const double* forcing_packed,
    int im, int kme, int jme, double dt,
    int value_only,
    double* state_out_packed,
    kdm6_handle_t** handle,
    const float* xland,
    double ncmin_land,
    double ncmin_sea) {
    if (im <= 0 || kme <= 0 || jme <= 0) return KDM6_ERR_INVALID_DIM;
    if (any_null({state_in_packed, forcing_packed, state_out_packed,
                  static_cast<const void*>(handle)})) {
        return KDM6_ERR_NULL_POINTER;
    }
    ensure_libtorch_singlethread();
    try {
        // fp64 DA forward (design §0.1.A): same physics, float64 graph.
        auto state_in = unpack_packed_state(state_in_packed, im, kme, jme,
                                            c10::ScalarType::Double);
        if (value_only == 0) {
            auto sp = state_in.fields();
            for (auto* p : sp) p->requires_grad_(true);
        }
        auto forcing = unpack_packed_forcing(forcing_packed, im, kme, jme,
                                             c10::ScalarType::Double);
        auto params = kdm6::make_parameters(0);

        c10::optional<torch::Tensor> xland_t = c10::nullopt;
        if (xland != nullptr) {
            auto xopts = torch::TensorOptions().dtype(torch::kFloat32);
            auto view2d = torch::from_blob(const_cast<float*>(xland),
                                           {jme, im}, xopts)
                              .permute({1, 0})
                              .contiguous();
            xland_t = view2d.reshape({im * jme});
        }

        auto result = kdm6::kdm6_step(state_in, forcing, params, dt,
                                      value_only != 0, xland_t,
                                      ncmin_land, ncmin_sea);
        pack_packed_state(result.state_out, state_out_packed, im, kme, jme);

        if (value_only != 0) {
            *handle = nullptr;
        } else {
            auto* h = new kdm6_handle_t{};
            h->impl = std::move(result.handle);
            h->im = im; h->kme = kme; h->jme = jme;
            h->dtype = c10::ScalarType::Double;   // fp64 DA graph
            *handle = h;
        }
        return KDM6_OK;
    } catch (const c10::NotImplementedError&) {
        return KDM6_ERR_NOT_IMPLEMENTED;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "kdm6_step_ad_c: %s\n", e.what());
        return KDM6_ERR_INTERNAL;
    } catch (...) {
        return KDM6_ERR_INTERNAL;
    }
}

extern "C" int kdm6_handle_vjp_c(kdm6_handle_t* h,
                                  const double* u_packed,
                                  double* grad_out_packed) {
    if (!h || !h->impl) return KDM6_ERR_NULL_POINTER;
    if (!u_packed || !grad_out_packed) return KDM6_ERR_NULL_POINTER;
    if (h->impl->is_closed()) return KDM6_ERR_HANDLE_CLOSED;
    if (h->impl->is_value_only()) return KDM6_ERR_VALUE_ONLY;
    if (h->im <= 0 || h->kme <= 0 || h->jme <= 0) return KDM6_ERR_INVALID_DIM;

    try {
        auto u = unpack_packed_state(u_packed, h->im, h->kme, h->jme, h->dtype);
        // Repeat-callable by design at the ABI (a DA driver may apply several
        // observation adjoints to one step) — retain the forward graph.
        kdm6::GraphOptions opts;
        opts.retain_graph = true;
        auto grad = h->impl->vjp(u, opts);
        pack_packed_state(grad, grad_out_packed, h->im, h->kme, h->jme);
        return KDM6_OK;
    } catch (const c10::NotImplementedError&) {
        return KDM6_ERR_NOT_IMPLEMENTED;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "kdm6_handle_vjp_c: %s\n", e.what());
        return KDM6_ERR_INTERNAL;
    } catch (...) {
        return KDM6_ERR_INTERNAL;
    }
}

extern "C" int kdm6_handle_jvp_c(kdm6_handle_t* h,
                                  const double* v_packed,
                                  double* tangent_out_packed) {
    if (!h || !h->impl) return KDM6_ERR_NULL_POINTER;
    if (!v_packed || !tangent_out_packed) return KDM6_ERR_NULL_POINTER;
    if (h->impl->is_closed()) return KDM6_ERR_HANDLE_CLOSED;
    if (h->impl->is_value_only()) return KDM6_ERR_VALUE_ONLY;
    if (h->im <= 0 || h->kme <= 0 || h->jme <= 0) return KDM6_ERR_INVALID_DIM;

    try {
        auto v = unpack_packed_state(v_packed, h->im, h->kme, h->jme, h->dtype);
        // Pearlmutter double-VJP under the hood (Handle::jvp); the forward
        // graph is retained, so jvp/vjp may be interleaved on one handle.
        auto tangent = h->impl->jvp(v);
        pack_packed_state(tangent, tangent_out_packed, h->im, h->kme, h->jme);
        return KDM6_OK;
    } catch (const c10::NotImplementedError&) {
        return KDM6_ERR_NOT_IMPLEMENTED;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "kdm6_handle_jvp_c: %s\n", e.what());
        return KDM6_ERR_INTERNAL;
    } catch (...) {
        return KDM6_ERR_INTERNAL;
    }
}

extern "C" int kdm6_handle_close_c(kdm6_handle_t* h) {
    if (!h) return KDM6_OK;
    if (h->impl) h->impl->close();
    delete h;
    return KDM6_OK;
}
