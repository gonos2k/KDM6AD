//
// C ABI bridge end-to-end smoke — KIM-meso wrapper가 호출할 경로 그대로 검증.
// kdm6/runtime.h를 *직접 인클루드하지 않고* kdm6_c_api.h만 사용해 ABI 격리 강제.
// Task #98 회귀: F4 wiring 활성 후 bridge layer가 NOT_IMPLEMENTED 던지지 않음을 보장.
//

#include "kdm6_c_api.h"

#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>
#include <vector>

#define TEST(name) std::cout << "  RUN  " << #name << "\n"; do
#define END_TEST() while(false); std::cout << "  PASS\n"

namespace {

// (im, kme, jme) Fortran column-major → flat double* (size im*kme*jme).
struct FortranBuf {
    int im, kme, jme;
    std::vector<double> data;

    FortranBuf(int im_, int kme_, int jme_, double fill = 0.0)
        : im(im_), kme(kme_), jme(jme_),
          data(static_cast<size_t>(im_) * kme_ * jme_, fill) {}

    double* ptr() { return data.data(); }
    const double* ptr() const { return data.data(); }
    size_t size() const { return data.size(); }
};

}  // anonymous namespace

void test_c_abi_step_runs_microphysics() {
    TEST(test_c_abi_step_runs_microphysics) {
        // (im=1, kme=1, jme=1) — single-cell warm-phase active 셀.
        const int im = 1, kme = 1, jme = 1;

        FortranBuf th(im, kme, jme,   285.0 / 1.1);
        FortranBuf qv(im, kme, jme,   6.5e-3);
        FortranBuf qc(im, kme, jme,   5.0e-4);
        FortranBuf qr(im, kme, jme,   1.0e-4);
        FortranBuf qi(im, kme, jme,   0.0);
        FortranBuf qs(im, kme, jme,   0.0);
        FortranBuf qg(im, kme, jme,   0.0);
        FortranBuf nccn(im, kme, jme, 12345.0);
        FortranBuf nc(im, kme, jme,   1.0e8);
        FortranBuf ni(im, kme, jme,   0.0);
        FortranBuf nr(im, kme, jme,   1.0e5);
        FortranBuf bg(im, kme, jme,   0.0);

        FortranBuf rho(im, kme, jme,  1.0);
        FortranBuf pii(im, kme, jme,  1.1);
        FortranBuf p(im, kme, jme,    8.0e4);
        FortranBuf delz(im, kme, jme, 550.0);

        FortranBuf th_o(im, kme, jme), qv_o(im, kme, jme), qc_o(im, kme, jme), qr_o(im, kme, jme);
        FortranBuf qi_o(im, kme, jme), qs_o(im, kme, jme), qg_o(im, kme, jme);
        FortranBuf nccn_o(im, kme, jme), nc_o(im, kme, jme), ni_o(im, kme, jme), nr_o(im, kme, jme);
        FortranBuf bg_o(im, kme, jme);

        kdm6_handle_t* handle = nullptr;
        const int rc = kdm6_step_c(
            th.ptr(), qv.ptr(), qc.ptr(), qr.ptr(), qi.ptr(), qs.ptr(), qg.ptr(),
            nccn.ptr(), nc.ptr(), ni.ptr(), nr.ptr(), bg.ptr(),
            rho.ptr(), pii.ptr(), p.ptr(), delz.ptr(),
            im, kme, jme, /*dt=*/60.0,
            /*param_grad_flags=*/0, /*value_only=*/1,
            th_o.ptr(), qv_o.ptr(), qc_o.ptr(), qr_o.ptr(),
            qi_o.ptr(), qs_o.ptr(), qg_o.ptr(),
            nccn_o.ptr(), nc_o.ptr(), ni_o.ptr(), nr_o.ptr(), bg_o.ptr(),
            &handle
        );
        // F4 wiring 검증: stub 시절엔 KDM6_ERR_NOT_IMPLEMENTED 반환했음.
        assert(rc == KDM6_OK);
        assert(handle == nullptr);

        // 모든 출력이 finite.
        for (auto* buf : {&th_o, &qv_o, &qc_o, &qr_o, &qi_o, &qs_o, &qg_o,
                          &nccn_o, &nc_o, &ni_o, &nr_o, &bg_o}) {
            for (size_t i = 0; i < buf->size(); ++i) {
                assert(std::isfinite(buf->data[i]));
            }
        }
        // water mixing ratios non-negative.
        for (auto* buf : {&qv_o, &qc_o, &qr_o, &qi_o, &qs_o, &qg_o}) {
            for (size_t i = 0; i < buf->size(); ++i) {
                assert(buf->data[i] >= 0.0);
            }
        }
        // microphysics 실제 실행: qc 또는 qr이 입력과 다름 (auto-conv/accretion/evap).
        bool qc_changed = std::fabs(qc_o.data[0] - qc.data[0]) > 1e-12;
        bool qr_changed = std::fabs(qr_o.data[0] - qr.data[0]) > 1e-12;
        assert(qc_changed || qr_changed);
        // Fortran module_mp_kdm6.F:747 prologue clamp [1e8, 2e10]; input 12345 → ≥1e8.
        std::fprintf(stderr, "nccn_o[0] = %.10e\n", nccn_o.data[0]);
        assert(nccn_o.data[0] >= 1.0e8 - 1e-3);
        assert(nccn_o.data[0] <= 2.0e10 + 1e-3);

        // NULL close is idempotent and KDM6_OK.
    } END_TEST();
}

void test_c_abi_invalid_dim() {
    TEST(test_c_abi_invalid_dim) {
        // im=0이면 KDM6_ERR_INVALID_DIM 즉시 반환 (미실행).
        FortranBuf one(1, 1, 1, 0.0);
        kdm6_handle_t* handle = nullptr;
        const int rc = kdm6_step_c(
            one.ptr(), one.ptr(), one.ptr(), one.ptr(), one.ptr(), one.ptr(), one.ptr(),
            one.ptr(), one.ptr(), one.ptr(), one.ptr(), one.ptr(),
            one.ptr(), one.ptr(), one.ptr(), one.ptr(),
            /*im=*/0, /*kme=*/1, /*jme=*/1, 60.0, 0, 1,
            one.ptr(), one.ptr(), one.ptr(), one.ptr(),
            one.ptr(), one.ptr(), one.ptr(),
            one.ptr(), one.ptr(), one.ptr(), one.ptr(), one.ptr(),
            &handle
        );
        assert(rc == KDM6_ERR_INVALID_DIM);
        assert(handle == nullptr);
    } END_TEST();
}

void test_c_abi_null_pointer() {
    TEST(test_c_abi_null_pointer) {
        // 입력 포인터 NULL → KDM6_ERR_NULL_POINTER (segfault 방지 검증).
        FortranBuf one(1, 1, 1, 0.0);
        kdm6_handle_t* handle = nullptr;
        const int rc = kdm6_step_c(
            /*th=*/nullptr, one.ptr(), one.ptr(), one.ptr(), one.ptr(), one.ptr(), one.ptr(),
            one.ptr(), one.ptr(), one.ptr(), one.ptr(), one.ptr(),
            one.ptr(), one.ptr(), one.ptr(), one.ptr(),
            1, 1, 1, 60.0, 0, 1,
            one.ptr(), one.ptr(), one.ptr(), one.ptr(),
            one.ptr(), one.ptr(), one.ptr(),
            one.ptr(), one.ptr(), one.ptr(), one.ptr(), one.ptr(),
            &handle
        );
        assert(rc == KDM6_ERR_NULL_POINTER);
    } END_TEST();
}

int main() {
    std::cout << "kdm6_libtorch C ABI bridge tests\n";
    test_c_abi_step_runs_microphysics();
    test_c_abi_invalid_dim();
    test_c_abi_null_pointer();
    std::cout << "All C ABI tests passed.\n";
    return 0;
}
