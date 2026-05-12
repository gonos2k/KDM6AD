#include "kdm6_c_api.h"
#include "kdm6/runtime.h"
#include "kdm6/state.h"

#include <ATen/Parallel.h>
#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>
#include <exception>
#include <memory>
#include <mutex>

//
// C ABI ↔ C++ 어댑터.
// 모든 C++ 예외는 *catch all* → int 에러 코드로 변환. 절대 외부로 던지지 않음.
//

extern "C" struct kdm6_handle_t {
    std::unique_ptr<kdm6::Handle> impl;
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

}  // anonymous namespace

extern "C" int kdm6_step_c(
    const double* th, const double* qv, const double* qc, const double* qr,
    const double* qi, const double* qs, const double* qg,
    const double* nccn, const double* nc, const double* ni, const double* nr,
    const double* bg,
    const double* rho, const double* pii, const double* p, const double* delz,
    int im, int kme, int jme, double dt,
    int param_grad_flags, int value_only,
    double* th_out, double* qv_out, double* qc_out, double* qr_out,
    double* qi_out, double* qs_out, double* qg_out,
    double* nccn_out, double* nc_out, double* ni_out, double* nr_out,
    double* bg_out,
    kdm6_handle_t** handle
) {
    if (im <= 0 || kme <= 0 || jme <= 0) return KDM6_ERR_INVALID_DIM;
    if (any_null({th, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg,
                  rho, pii, p, delz,
                  th_out, qv_out, qc_out, qr_out, qi_out, qs_out, qg_out,
                  nccn_out, nc_out, ni_out, nr_out, bg_out, handle})) {
        return KDM6_ERR_NULL_POINTER;
    }

    ensure_libtorch_singlethread();

    try {
        kdm6::FortranArrayDescriptor desc{
            th, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg, im, kme, jme};
        // [C4] requires_grad는 value_only=0일 때만 켬
        bool requires_grad = (value_only == 0);
        auto state_in = kdm6::from_fortran_arrays(desc, requires_grad);

        auto forcing = kdm6::forcing_from_fortran_arrays(rho, pii, p, delz, im, kme, jme);

        auto params = kdm6::make_parameters(param_grad_flags);

        auto result = kdm6::kdm6_step(state_in, forcing, params, dt, value_only != 0);

        kdm6::to_fortran_arrays(result.state_out, im, jme,
                                th_out, qv_out, qc_out, qr_out, qi_out, qs_out, qg_out,
                                nccn_out, nc_out, ni_out, nr_out, bg_out);

        if (value_only != 0) {
            *handle = nullptr;
        } else {
            auto* h = new kdm6_handle_t{std::move(result.handle)};
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

extern "C" int kdm6_handle_vjp_c(kdm6_handle_t* h,
                                  const double* /*u_packed*/,
                                  double* /*grad_out_packed*/) {
    if (!h || !h->impl) return KDM6_ERR_NULL_POINTER;
    if (h->impl->is_closed()) return KDM6_ERR_HANDLE_CLOSED;
    if (h->impl->is_value_only()) return KDM6_ERR_VALUE_ONLY;
    // [TODO] u_packed → State, vjp 호출, grad_out_packed에 복사
    return KDM6_ERR_NOT_IMPLEMENTED;
}

extern "C" int kdm6_handle_jvp_c(kdm6_handle_t* h,
                                  const double* /*v_packed*/,
                                  double* /*tangent_out_packed*/) {
    if (!h || !h->impl) return KDM6_ERR_NULL_POINTER;
    if (h->impl->is_closed()) return KDM6_ERR_HANDLE_CLOSED;
    if (h->impl->is_value_only()) return KDM6_ERR_VALUE_ONLY;
    return KDM6_ERR_NOT_IMPLEMENTED;
}

extern "C" int kdm6_handle_close_c(kdm6_handle_t* h) {
    if (!h) return KDM6_OK;
    if (h->impl) h->impl->close();
    delete h;
    return KDM6_OK;
}
