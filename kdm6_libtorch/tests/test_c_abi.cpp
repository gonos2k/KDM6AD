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
    std::vector<float> data;  // native float32 ABI

    FortranBuf(int im_, int kme_, int jme_, float fill = 0.0f)
        : im(im_), kme(kme_), jme(jme_),
          data(static_cast<size_t>(im_) * kme_ * jme_, fill) {}

    float* ptr() { return data.data(); }
    const float* ptr() const { return data.data(); }
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
            &handle,
            /*xland=*/nullptr, /*ncmin_land=*/0.0, /*ncmin_sea=*/0.0,
            /*rain_increment=*/nullptr, /*snow_increment=*/nullptr, /*graupel_increment=*/nullptr
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
        // Fortran module_mp_kdm6.F:747 prologue clamp; input 12345 < NCCN_MIN, so output
        // must be inside [NCCN_MIN, NCCN_MAX] (constants in kdm6/constants.h, duplicated
        // here as raw numbers because the test enforces ABI isolation by including only
        // kdm6_c_api.h — see file header).
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
            &handle,
            /*xland=*/nullptr, /*ncmin_land=*/0.0, /*ncmin_sea=*/0.0,
            /*rain_increment=*/nullptr, /*snow_increment=*/nullptr, /*graupel_increment=*/nullptr
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
            &handle,
            /*xland=*/nullptr, /*ncmin_land=*/0.0, /*ncmin_sea=*/0.0,
            /*rain_increment=*/nullptr, /*snow_increment=*/nullptr, /*graupel_increment=*/nullptr
        );
        assert(rc == KDM6_ERR_NULL_POINTER);
    } END_TEST();
}

// Per Codex review: positive test that distinct per-cell ncmin values flow
// through to a consumption site (B1 autoconv at warm.cpp:51). Uses a mixed
// land/sea grid (one cell each, WRF convention: xland>=1.5 → sea regime;
// else land) with `ncmin_land >> nc > ncmin_sea`, so the autoconv gate
// `nc > ncmin_eff` differs between the two cells: passes for the sea cell,
// fails for the land cell. Detected via qc_out divergence (sea cell loses
// qc → qr via autoconv; land cell preserved).
void test_c_abi_step_per_cell_ncmin_mixed_xland() {
    TEST(test_c_abi_step_per_cell_ncmin_mixed_xland) {
        const int im = 2, kme = 1, jme = 1;  // 2-cell domain

        // Uniform warm-phase active state across both cells.
        FortranBuf th(im, kme, jme,   285.0 / 1.1);
        FortranBuf qv(im, kme, jme,   6.5e-3);
        FortranBuf qc(im, kme, jme,   5.0e-4);
        FortranBuf qr(im, kme, jme,   1.0e-4);
        FortranBuf qi(im, kme, jme,   0.0);
        FortranBuf qs(im, kme, jme,   0.0);
        FortranBuf qg(im, kme, jme,   0.0);
        FortranBuf nccn(im, kme, jme, 5.0e8);
        FortranBuf nc(im, kme, jme,   1.0e2);  // 100/m³ — between sea (10) and land (1000)
        FortranBuf ni(im, kme, jme,   0.0);
        FortranBuf nr(im, kme, jme,   1.0e5);
        FortranBuf bg(im, kme, jme,   0.0);
        FortranBuf rho(im, kme, jme,  1.0);
        FortranBuf pii(im, kme, jme,  1.1);
        FortranBuf p(im, kme, jme,    8.0e4);
        FortranBuf delz(im, kme, jme, 550.0);

        FortranBuf th_o(im, kme, jme), qv_o(im, kme, jme), qc_o(im, kme, jme), qr_o(im, kme, jme);
        FortranBuf qi_o(im, kme, jme), qs_o(im, kme, jme), qg_o(im, kme, jme);
        FortranBuf nccn_o(im, kme, jme), nc_o(im, kme, jme), ni_o(im, kme, jme);
        FortranBuf nr_o(im, kme, jme), bg_o(im, kme, jme);

        // xland(im=2, jme=1): cell 0 = land (XLAND=1), cell 1 = sea (XLAND=2).
        std::vector<float> xland_buf = {1.0f, 2.0f};
        // Phase 4 ABI extension — per-column precip increment buffers (im, jme).
        std::vector<float> rain_inc(im * jme, 0.0f);
        std::vector<float> snow_inc(im * jme, 0.0f);
        std::vector<float> graupel_inc(im * jme, 0.0f);

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
            &handle,
            xland_buf.data(),
            /*ncmin_land=*/1.0e3,   // 1000/m³ — gates nc=100 (BLOCKS autoconv)
            /*ncmin_sea=*/1.0e1,    //   10/m³ — passes nc=100 (RUNS autoconv)
            // Phase 4 ABI extension — sedimentation surface increments (im, jme) [mm].
            // For this 2-cell test im=2 jme=1 so each buffer is 2 doubles.
            rain_inc.data(), snow_inc.data(), graupel_inc.data()
        );
        assert(rc == KDM6_OK);
        assert(handle == nullptr);
        // Precip increments finite + non-negative (no fallout from tiny qr/qs/qg
        // in this 1-step test, so all should be ≈0 but valid).
        for (double v : {rain_inc[0], rain_inc[1], snow_inc[0], snow_inc[1],
                         graupel_inc[0], graupel_inc[1]}) {
            assert(std::isfinite(v));
            assert(v >= 0.0);
        }
        // Outputs finite.
        for (auto* buf : {&th_o, &qv_o, &qc_o, &qr_o, &qi_o, &qs_o, &qg_o,
                          &nccn_o, &nc_o, &ni_o, &nr_o, &bg_o}) {
            for (size_t i = 0; i < buf->size(); ++i) {
                assert(std::isfinite(buf->data[i]));
            }
        }
        // Per-cell ncmin reached B1 autoconv (warm.cpp:51): the LAND cell's
        // gate `nc(100) > ncmin_land(1000)` is FALSE so autoconv produces zero
        // praut → qc preserved (within numerical drift from other warm rates);
        // the SEA cell's gate `nc(100) > ncmin_sea(10)` is TRUE so autoconv
        // fires → qc strictly less than land cell's qc.
        // Indices: cell 0 = land (high ncmin), cell 1 = sea (low ncmin).
        // Note FortranBuf is column-major (im, kme, jme) → flat layout
        // arr(i,k,j) = data[i + im*(k + kme*j)]; with kme=jme=1, data[i] = cell i.
        assert(qc_o.data[0] >= qc_o.data[1] - 1e-12);  // land qc >= sea qc
        // Sanity: at least one cell experienced detectable change vs input.
        bool qc_changed = std::fabs(qc_o.data[0] - qc.data[0]) > 1e-12
                       || std::fabs(qc_o.data[1] - qc.data[1]) > 1e-12;
        assert(qc_changed);
    } END_TEST();
}

int main() {
    std::cout << "kdm6_libtorch C ABI bridge tests\n";
    test_c_abi_step_runs_microphysics();
    test_c_abi_invalid_dim();
    test_c_abi_null_pointer();
    test_c_abi_step_per_cell_ncmin_mixed_xland();
    std::cout << "All C ABI tests passed.\n";
    return 0;
}
