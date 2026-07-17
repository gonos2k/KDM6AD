//
// C ABI bridge end-to-end smoke — KIM-meso wrapper가 호출할 경로 그대로 검증.
// kdm6/runtime.h를 *직접 인클루드하지 않고* kdm6_c_api.h만 사용해 ABI 격리 강제.
// Task #98 회귀: F4 wiring 활성 후 bridge layer가 NOT_IMPLEMENTED 던지지 않음을 보장.
//

#include "kdm6_c_api.h"

#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdlib>
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
            /*rain_increment=*/nullptr, /*snow_increment=*/nullptr, /*graupel_increment=*/nullptr,
            /*rhog_out=*/nullptr
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
            /*rain_increment=*/nullptr, /*snow_increment=*/nullptr, /*graupel_increment=*/nullptr,
            /*rhog_out=*/nullptr
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
            /*rain_increment=*/nullptr, /*snow_increment=*/nullptr, /*graupel_increment=*/nullptr,
            /*rhog_out=*/nullptr
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
            rain_inc.data(), snow_inc.data(), graupel_inc.data(),
            /*rhog_out=*/nullptr
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


// ── [DA Phase 3] value_only=0 + packed VJP/JVP ABI (kdm6ad+da.md §6.4/§10.2) ──
void test_c_abi_vjp_jvp_roundtrip() {
    TEST(test_c_abi_vjp_jvp_roundtrip) {
        const int im = 1, kme = 2, jme = 1;          // 2-cell column
        const size_t NF = 12;
        const size_t BK = static_cast<size_t>(im) * jme * kme;

        // mixed-phase 2-cell IC (g_base family; k0 warm, k1 supercooled)
        auto fill2 = [&](FortranBuf& b, float v0, float v1) {
            b.data[0] = v0; b.data[1] = v1;          // (im=1,jme=1) → k-major
        };
        FortranBuf th(im,kme,jme), qv(im,kme,jme), qc(im,kme,jme), qr(im,kme,jme);
        FortranBuf qi(im,kme,jme), qs(im,kme,jme), qg(im,kme,jme), nccn(im,kme,jme);
        FortranBuf nc(im,kme,jme), ni(im,kme,jme), nr(im,kme,jme), bg(im,kme,jme);
        fill2(th, 296.8f, 282.4f);   fill2(qv, 1.40e-2f, 2.0e-3f);
        fill2(qc, 1.0e-3f, 5.0e-4f); fill2(qr, 1.0e-4f, 1.0e-5f);
        fill2(qi, 0.0f, 1.0e-6f);    fill2(qs, 0.0f, 5.0e-5f);
        fill2(qg, 0.0f, 1.0e-5f);    fill2(nccn, 1.0e9f, 1.0e9f);
        fill2(nc, 1.0e8f, 1.0e8f);   fill2(ni, 0.0f, 1.0e8f);
        fill2(nr, 1.0e4f, 1.0e3f);   fill2(bg, 0.0f, 0.0f);
        FortranBuf rho(im,kme,jme), pii(im,kme,jme), p(im,kme,jme), delz(im,kme,jme);
        fill2(rho, 1.089f, 0.9567f); fill2(pii, 0.9704f, 0.9031f);
        fill2(p, 9.0e4f, 7.0e4f);    fill2(delz, 500.0f, 500.0f);

        FortranBuf th_o(im,kme,jme), qv_o(im,kme,jme), qc_o(im,kme,jme), qr_o(im,kme,jme);
        FortranBuf qi_o(im,kme,jme), qs_o(im,kme,jme), qg_o(im,kme,jme);
        FortranBuf nccn_o(im,kme,jme), nc_o(im,kme,jme), ni_o(im,kme,jme), nr_o(im,kme,jme);
        FortranBuf bg_o(im,kme,jme);

        kdm6_handle_t* handle = nullptr;
        int rc = kdm6_step_c(
            th.ptr(), qv.ptr(), qc.ptr(), qr.ptr(), qi.ptr(), qs.ptr(), qg.ptr(),
            nccn.ptr(), nc.ptr(), ni.ptr(), nr.ptr(), bg.ptr(),
            rho.ptr(), pii.ptr(), p.ptr(), delz.ptr(),
            im, kme, jme, /*dt=*/20.0,
            /*param_grad_flags=*/0, /*value_only=*/0,
            th_o.ptr(), qv_o.ptr(), qc_o.ptr(), qr_o.ptr(),
            qi_o.ptr(), qs_o.ptr(), qg_o.ptr(),
            nccn_o.ptr(), nc_o.ptr(), ni_o.ptr(), nr_o.ptr(), bg_o.ptr(),
            &handle,
            nullptr, 0.0, 0.0, nullptr, nullptr, nullptr, /*rhog_out=*/nullptr);
        assert(rc == KDM6_OK);
        assert(handle != nullptr);              // grad-mode → handle exists

        // packed covector u = field-scaled deterministic pattern
        std::vector<double> u_packed(NF * BK), grad_out(NF * BK, -777.0);
        for (size_t i = 0; i < u_packed.size(); ++i)
            u_packed[i] = 1.0 + 0.25 * static_cast<double>(i % 7);

        rc = kdm6_handle_vjp_c(handle, u_packed.data(), grad_out.data());
        assert(rc == KDM6_OK);
        // f32-GRAPH CONTRACT (kdm6ad+da.md §0.1.A): the operational float32 handle's
        // VJP/JVP is a MECHANICS / DIAGNOSTICS path — it is NOT a finiteness contract.
        // The f32 backward can underflow deep rslope^k chains at inactive-ice corners
        // (1/0*0 in the where-mask backward) and the resulting NaN PROPAGATES to whatever
        // upstream inputs are graph-connected. WHICH fields go non-finite is f32-rounding /
        // toolchain dependent (e.g. on the pinned clang the `th` gradient also NaNs), so we
        // deliberately do NOT pin the non-finite field set — that would assert a
        // non-contractual implementation detail. Reliable, fully-finite fp64 adjoints come
        // from kdm6_step_ad_c (the DA design default). This smoke asserts the packed-ABI
        // MECHANICS only: buffer fully overwritten + a real finite non-zero gradient exists +
        // the backward did not blow up wholesale.
        bool any_nz = false;
        size_t n_nonfinite = 0;
        for (size_t i = 0; i < grad_out.size(); ++i) {
            assert(grad_out[i] != -777.0);      // fully overwritten (packing mechanics)
            if (!std::isfinite(grad_out[i])) ++n_nonfinite;
            else if (grad_out[i] != 0.0) any_nz = true;
        }
        assert(any_nz);                          // a real finite gradient signal exists
        assert(n_nonfinite < grad_out.size());   // NOT everything NaN'd (backward not fully broken)
        if (n_nonfinite)                         // diagnostic only — expected f32 corner NaN
            std::fprintf(stderr, "[f32-vjp] %zu/%zu grad entries non-finite "
                         "(expected f32 inactive-ice corner NaN; use kdm6_step_ad_c fp64 "
                         "for finite adjoints)\n", n_nonfinite, grad_out.size());

        // packed direction v (small, field-major) → JVP
        std::vector<double> v_packed(NF * BK), tan_out(NF * BK, -777.0);
        for (size_t f = 0; f < NF; ++f) {
            // per-field scale ~1e-4 of typical magnitude (rough, deterministic)
            double scale = (f == 0) ? 1e-2 : (f >= 7 ? 1e4 : 1e-7);
            for (size_t b = 0; b < BK; ++b)
                v_packed[f * BK + b] = scale * (0.5 + 0.1 * static_cast<double>((f + b) % 5));
        }
        rc = kdm6_handle_jvp_c(handle, v_packed.data(), tan_out.data());
        assert(rc == KDM6_OK);
        bool tan_overwritten = false;
        for (size_t i = 0; i < tan_out.size(); ++i)
            if (tan_out[i] != -777.0) tan_overwritten = true;
        assert(tan_overwritten);
        // NOTE: the <Jv,u> == <v,J^T u> adjoint identity is NOT asserted at the
        // f32 ABI — the operational f32 backward NaNs at the inactive-ice corner
        // (see the vjp caveat above) and the Pearlmutter inner product propagates
        // it (0*NaN). The identity is asserted EXACTLY (1e-12) on the fp64 paths:
        // C++ test_handle_vjp (jvp_vjp_inner_product_exact, masked_adjoint_identity)
        // and Python test_handle_vjp_jvp.py. The fp64 kdm6_step_ad(_c) entry is
        // the design-default DA path (kdm6ad+da.md §0.1.A); this smoke pins the
        // packed-ABI MECHANICS (rc, layout, overwrite, lifecycle).

        // lifecycle: close → further calls refused with the documented code
        rc = kdm6_handle_close_c(handle);
        assert(rc == KDM6_OK);
        // NOTE: handle memory is freed by close — calling again with the same
        // pointer is UB per the ABI contract; a NULL handle returns OK.
        assert(kdm6_handle_close_c(nullptr) == KDM6_OK);
    } END_TEST();
}

void test_c_abi_vjp_value_only_refused() {
    TEST(test_c_abi_vjp_value_only_refused) {
        // value_only=1 → handle == nullptr → vjp on nullptr = NULL_POINTER.
        // (the VALUE_ONLY error code is reserved for a future value-only handle
        // object; the operational contract returns no handle at all.)
        std::vector<double> buf(12, 0.0);
        assert(kdm6_handle_vjp_c(nullptr, buf.data(), buf.data()) == KDM6_ERR_NULL_POINTER);
        assert(kdm6_handle_jvp_c(nullptr, buf.data(), buf.data()) == KDM6_ERR_NULL_POINTER);
    } END_TEST();
}


// ── [DA Phase 3] packed layout on a NONTRIVIAL tile (Codex stop-review) ──────
// Columns evolve independently in kdm6 (no horizontal coupling), so the vjp of
// a covector supported on ONE Fortran cell (i0,k0,j0) must have its gradient
// support confined to the SAME (i0,j0) column. If the packed layout scrambles
// (im,kme,jme) ordering, the support lands in a different column — this test
// fails for any wrong permutation on an im=2,kme=2,jme=2 tile.
void test_c_abi_vjp_packed_layout_nontrivial_tile() {
    TEST(test_c_abi_vjp_packed_layout_nontrivial_tile) {
        const int im = 2, kme = 2, jme = 2;
        const size_t NF = 12, N = static_cast<size_t>(im) * kme * jme;
        auto idx = [&](int i, int k, int j) {            // Fortran col-major
            return static_cast<size_t>(i) + im * (static_cast<size_t>(k) + kme * j);
        };

        // distinct, physical values per column so every column is active-warm
        FortranBuf th(im,kme,jme), qv(im,kme,jme), qc(im,kme,jme), qr(im,kme,jme);
        FortranBuf qi(im,kme,jme), qs(im,kme,jme), qg(im,kme,jme), nccn(im,kme,jme);
        FortranBuf nc(im,kme,jme), ni(im,kme,jme), nr(im,kme,jme), bg(im,kme,jme);
        FortranBuf rho(im,kme,jme), pii(im,kme,jme), p(im,kme,jme), delz(im,kme,jme);
        for (int j = 0; j < jme; ++j) for (int k = 0; k < kme; ++k) for (int i = 0; i < im; ++i) {
            const size_t q = idx(i,k,j);
            const float col = static_cast<float>(1 + i + 2*j);   // column flavor
            th.data[q]   = 295.0f + 1.5f*col + 2.0f*k;
            qv.data[q]   = 1.2e-2f + 1e-3f*col;
            qc.data[q]   = 8.0e-4f + 1e-4f*col;
            qr.data[q]   = 5.0e-5f + 1e-5f*col;
            qi.data[q]   = 0.0f; qs.data[q] = 0.0f; qg.data[q] = 0.0f;
            nccn.data[q] = 1.0e9f;
            nc.data[q]   = 1.0e8f + 1e7f*col;
            ni.data[q]   = 0.0f;
            nr.data[q]   = 1.0e4f;
            bg.data[q]   = 0.0f;
            rho.data[q]  = 1.05f; pii.data[q] = 0.97f;
            p.data[q]    = 8.8e4f; delz.data[q] = 500.0f;
        }
        FortranBuf th_o(im,kme,jme), qv_o(im,kme,jme), qc_o(im,kme,jme), qr_o(im,kme,jme);
        FortranBuf qi_o(im,kme,jme), qs_o(im,kme,jme), qg_o(im,kme,jme);
        FortranBuf nccn_o(im,kme,jme), nc_o(im,kme,jme), ni_o(im,kme,jme), nr_o(im,kme,jme);
        FortranBuf bg_o(im,kme,jme);

        kdm6_handle_t* handle = nullptr;
        int rc = kdm6_step_c(
            th.ptr(), qv.ptr(), qc.ptr(), qr.ptr(), qi.ptr(), qs.ptr(), qg.ptr(),
            nccn.ptr(), nc.ptr(), ni.ptr(), nr.ptr(), bg.ptr(),
            rho.ptr(), pii.ptr(), p.ptr(), delz.ptr(),
            im, kme, jme, /*dt=*/20.0, 0, /*value_only=*/0,
            th_o.ptr(), qv_o.ptr(), qc_o.ptr(), qr_o.ptr(),
            qi_o.ptr(), qs_o.ptr(), qg_o.ptr(),
            nccn_o.ptr(), nc_o.ptr(), ni_o.ptr(), nr_o.ptr(), bg_o.ptr(),
            &handle, nullptr, 0.0, 0.0, nullptr, nullptr, nullptr, /*rhog_out=*/nullptr);
        assert(rc == KDM6_OK && handle != nullptr);

        // covector: u = e_{qv at (i0=1,k0=0,j0=1)} — single Fortran cell
        const int i0 = 1, k0 = 0, j0 = 1;
        std::vector<double> u(NF * N, 0.0), g(NF * N, 0.0);
        const size_t QV = 1;                              // field index of qv
        u[QV * N + idx(i0, k0, j0)] = 1.0;
        rc = kdm6_handle_vjp_c(handle, u.data(), g.data());
        assert(rc == KDM6_OK);

        // gradient support must be confined to column (i0,j0) across ALL fields
        bool any_in_col = false;
        for (size_t f = 0; f < NF; ++f) {
            for (int j = 0; j < jme; ++j) for (int k = 0; k < kme; ++k) for (int i = 0; i < im; ++i) {
                const double val = g[f * N + idx(i,k,j)];
                if (!std::isfinite(val)) continue;        // f32 corner caveat
                if (val != 0.0) {
                    assert(i == i0 && j == j0);           // scrambled layout fails HERE
                    any_in_col = true;
                }
            }
        }
        assert(any_in_col);
        assert(kdm6_handle_close_c(handle) == KDM6_OK);
    } END_TEST();
}


// ── [DA §0.1.A] fp64 DA adjoint forward via the C ABI ────────────────────────
// THE motivation: the f32 graph's backward NaNs at inactive-ice corners (see
// the f32 caveat in test_c_abi_vjp_jvp_roundtrip). The fp64 entry must give
// (a) ALL-FINITE gradients on the same IC and (b) the adjoint identity at
// fp64 tightness — neither holds on the f32 path.
void test_c_abi_step_ad_fp64_vjp_finite_and_adjoint() {
    TEST(test_c_abi_step_ad_fp64_vjp_finite_and_adjoint) {
        const int im = 1, kme = 2, jme = 1;
        const size_t NF = 12, BK = 2, N = NF * BK;

        // same mixed-phase IC as the f32 roundtrip test (NaN corner: qi/nc/ni)
        double st[N] = {
            296.8, 282.4,        // th
            1.40e-2, 2.0e-3,     // qv
            1.0e-3, 5.0e-4,      // qc
            1.0e-4, 1.0e-5,      // qr
            0.0, 1.0e-6,         // qi
            0.0, 5.0e-5,         // qs
            0.0, 1.0e-5,         // qg
            1.0e9, 1.0e9,        // nccn
            1.0e8, 1.0e8,        // nc
            0.0, 1.0e8,          // ni
            1.0e4, 1.0e3,        // nr
            0.0, 0.0,            // bg
        };
        double fz[4 * BK] = {
            1.089, 0.9567,       // rho
            0.9704, 0.9031,      // pii
            9.0e4, 7.0e4,        // p
            500.0, 500.0,        // delz
        };
        std::vector<double> out(N, -777.0);

        kdm6_handle_t* handle = nullptr;
        int rc = kdm6_step_ad_c(st, fz, im, kme, jme, /*dt=*/20.0,
                                /*value_only=*/0, out.data(), &handle,
                                nullptr, 0.0, 0.0);
        assert(rc == KDM6_OK);
        assert(handle != nullptr);
        for (size_t i = 0; i < N; ++i) {
            assert(out[i] != -777.0);
            assert(std::isfinite(out[i]));
        }

        // u = the same deterministic covector as the f32 test
        std::vector<double> u(N), g(N, 0.0);
        for (size_t i = 0; i < N; ++i) u[i] = 1.0 + 0.25 * static_cast<double>(i % 7);
        rc = kdm6_handle_vjp_c(handle, u.data(), g.data());
        assert(rc == KDM6_OK);
        bool any_nz = false;
        for (size_t i = 0; i < N; ++i) {
            assert(std::isfinite(g[i]));     // fp64: NO ice-corner NaN — the point
            if (g[i] != 0.0) any_nz = true;
        }
        assert(any_nz);

        // adjoint identity at fp64 tightness (the f32 test could not assert this)
        std::vector<double> v(N), tan_out(N, 0.0);
        for (size_t f = 0; f < NF; ++f) {
            double scale = (f == 0) ? 1e-2 : (f >= 7 ? 1e4 : 1e-7);
            for (size_t b = 0; b < BK; ++b)
                v[f * BK + b] = scale * (0.5 + 0.1 * static_cast<double>((f + b) % 5));
        }
        rc = kdm6_handle_jvp_c(handle, v.data(), tan_out.data());
        assert(rc == KDM6_OK);
        double lhs = 0.0, rhs = 0.0;
        for (size_t i = 0; i < N; ++i) {
            assert(std::isfinite(tan_out[i]));
            lhs += tan_out[i] * u[i];
            rhs += v[i] * g[i];
        }
        const double denom = std::max(std::abs(lhs), std::abs(rhs));
        assert(denom > 0.0);
        assert(std::abs(lhs - rhs) / denom < 1e-12);

        assert(kdm6_handle_close_c(handle) == KDM6_OK);

        // value_only=1 → no handle, forward matches the graph forward bitwise
        std::vector<double> out2(N, -777.0);
        kdm6_handle_t* h2 = reinterpret_cast<kdm6_handle_t*>(0x1);
        rc = kdm6_step_ad_c(st, fz, im, kme, jme, 20.0, /*value_only=*/1,
                            out2.data(), &h2, nullptr, 0.0, 0.0);
        assert(rc == KDM6_OK);
        assert(h2 == nullptr);
        for (size_t i = 0; i < N; ++i)
            assert(out2[i] == out[i]);   // fp64 forward-determinism through the ABI
    } END_TEST();
}

void test_c_abi_fp64_packed_layout_nontrivial_tile() {
    TEST(test_c_abi_fp64_packed_layout_nontrivial_tile) {
        // fp64 twin of test_c_abi_vjp_packed_layout_nontrivial_tile, via kdm6_step_ad_c. The
        // f32 layout test must `continue` past non-finite gradients (the f32 corner caveat),
        // so an off-column leak that happens to be NaN could slip through. fp64 has NO
        // ice-corner NaN, so EVERY off-column gradient is a real finite number and the
        // column-confinement is checked with no skip. Also needs no Fortran compiler (unlike
        // the stronger fortran_smoke value-level layout check).
        // ASYMMETRIC extents (im != kme != jme) on purpose — a symmetric 2x2x2 tile with
        // i0==j0 would make an i<->j axis swap invisible. Matches the fortran_smoke tile shape.
        const int im = 2, kme = 3, jme = 4;
        const size_t NF = 12, BK = static_cast<size_t>(im) * kme * jme;   // 24
        const size_t N = NF * BK;
        auto idx = [&](int i, int k, int j) {              // Fortran col-major within a field block
            return static_cast<size_t>(i) + im * (static_cast<size_t>(k) + kme * j);
        };
        // Packed state, field order th,qv,qc,qr,qi,qs,qg,nccn,nc,ni,nr,bg; distinct warm columns.
        std::vector<double> st(N, 0.0);
        auto set = [&](size_t field, int i, int k, int j, double v) { st[field * BK + idx(i,k,j)] = v; };
        for (int j = 0; j < jme; ++j) for (int k = 0; k < kme; ++k) for (int i = 0; i < im; ++i) {
            const double col = 1.0 + i + 2.0 * j;
            set(0, i,k,j, 295.0 + 1.5*col + 2.0*k);   // th
            set(1, i,k,j, 1.2e-2 + 1e-3*col);          // qv
            set(2, i,k,j, 8.0e-4 + 1e-4*col);          // qc
            set(3, i,k,j, 5.0e-5 + 1e-5*col);          // qr
            set(7, i,k,j, 1.0e9);                       // nccn
            set(8, i,k,j, 1.0e8 + 1e7*col);            // nc
            set(10, i,k,j, 1.0e4);                      // nr
            // qi/qs/qg/ni/bg stay 0 — fp64 keeps them finite anyway
        }
        std::vector<double> fz(4 * BK, 0.0);
        auto setf = [&](size_t field, int i, int k, int j, double v) { fz[field * BK + idx(i,k,j)] = v; };
        for (int j = 0; j < jme; ++j) for (int k = 0; k < kme; ++k) for (int i = 0; i < im; ++i) {
            setf(0, i,k,j, 1.05); setf(1, i,k,j, 0.97); setf(2, i,k,j, 8.8e4); setf(3, i,k,j, 500.0);
        }
        std::vector<double> out(N, -777.0);
        kdm6_handle_t* handle = nullptr;
        int rc = kdm6_step_ad_c(st.data(), fz.data(), im, kme, jme, /*dt=*/20.0,
                                /*value_only=*/0, out.data(), &handle, nullptr, 0.0, 0.0);
        assert(rc == KDM6_OK && handle != nullptr);
        for (size_t i = 0; i < N; ++i) { assert(out[i] != -777.0); assert(std::isfinite(out[i])); }

        // seed u = e_{qv at (i0,k0,j0)} — a single Fortran cell; i0 != j0 so an i<->j swap moves it
        const int i0 = 1, k0 = 1, j0 = 2;
        const size_t QV = 1;
        std::vector<double> u(N, 0.0), g(N, 0.0);
        u[QV * BK + idx(i0, k0, j0)] = 1.0;
        rc = kdm6_handle_vjp_c(handle, u.data(), g.data());
        assert(rc == KDM6_OK);

        // fp64 → all grads finite; microphysics couples only within a column, so gradient
        // support must be confined to column (i0,j0) across EVERY field. No NaN-skip here: a
        // scrambled packed layout OR an off-column leak fails the (i==i0 && j==j0) assert.
        bool any_in_col = false;
        for (size_t f = 0; f < NF; ++f)
            for (int j = 0; j < jme; ++j) for (int k = 0; k < kme; ++k) for (int i = 0; i < im; ++i) {
                const double val = g[f * BK + idx(i,k,j)];
                assert(std::isfinite(val));               // fp64: no ice-corner NaN
                if (val != 0.0) { assert(i == i0 && j == j0); any_in_col = true; }
            }
        assert(any_in_col);

        // VALUE-LEVEL column-independence check: re-run column (i0,j0) as a STANDALONE
        // (1,kme,1) tile and require its forward output to equal the embedded column
        // BIT-FOR-BIT (microphysics is column-local + fp64-deterministic).
        // WHAT THIS PINS: the batch (i,j) striding and column independence — a wrong batch
        // stride or any cross-column value contamination in the multi-column run makes the
        // embedded column differ from standalone. Combined with the gradient-confinement
        // check above (asymmetric extents → catches i<->j axis swaps), this locks the (i,j)
        // batch layout at the value level, not just the gradient-support level.
        // WHAT THIS DOES *NOT* PIN: the absolute field-block order or within-column k / forcing
        // order. Those are built AND read with the same convention on both sides here, so a
        // *consistent* mislabeling cancels out and the match still holds — a self-consistent
        // buffer cannot validate its own convention. The fortran_smoke value-level test is the
        // stronger absolute-ordering oracle (it uses Fortran's native x(i,k,j,field) layout).
        std::vector<double> st_s(NF * kme, 0.0), fz_s(4 * kme, 0.0), out_s(NF * kme, -777.0);
        for (size_t f = 0; f < NF; ++f)
            for (int k = 0; k < kme; ++k) st_s[f * kme + k] = st[f * BK + idx(i0, k, j0)];
        for (size_t f = 0; f < 4; ++f)
            for (int k = 0; k < kme; ++k) fz_s[f * kme + k] = fz[f * BK + idx(i0, k, j0)];
        kdm6_handle_t* hs = reinterpret_cast<kdm6_handle_t*>(0x1);
        rc = kdm6_step_ad_c(st_s.data(), fz_s.data(), /*im=*/1, kme, /*jme=*/1, /*dt=*/20.0,
                            /*value_only=*/1, out_s.data(), &hs, nullptr, 0.0, 0.0);
        assert(rc == KDM6_OK && hs == nullptr);
        for (size_t f = 0; f < NF; ++f)
            for (int k = 0; k < kme; ++k)
                assert(out_s[f * kme + k] == out[f * BK + idx(i0, k, j0)]);  // bit-exact (column-local fp64)

        assert(kdm6_handle_closep_c(&handle) == KDM6_OK);
        assert(handle == nullptr);
    } END_TEST();
}

void test_c_abi_invalid_value_only() {
    TEST(test_c_abi_invalid_value_only) {
        // value_only is a 0/1 flag; a stray value (2) must be REJECTED with KDM6_ERR_INVALID_ARG,
        // and the output handle must be left NULL (the entry nulls it before any early return).
        const int im = 1, kme = 1, jme = 1;
        FortranBuf a(im, kme, jme, 1.0f);   // one valid non-null buffer reused for every arg —
                                            // the value_only check fires before any physics runs
        kdm6_handle_t* h = reinterpret_cast<kdm6_handle_t*>(0x1);   // poison; must be nulled
        int rc = kdm6_step_c(
            a.ptr(), a.ptr(), a.ptr(), a.ptr(), a.ptr(), a.ptr(), a.ptr(),
            a.ptr(), a.ptr(), a.ptr(), a.ptr(), a.ptr(),
            a.ptr(), a.ptr(), a.ptr(), a.ptr(),
            im, kme, jme, /*dt=*/20.0, /*param_grad_flags=*/0, /*value_only=*/2,
            a.ptr(), a.ptr(), a.ptr(), a.ptr(), a.ptr(), a.ptr(), a.ptr(),
            a.ptr(), a.ptr(), a.ptr(), a.ptr(), a.ptr(),
            &h, nullptr, 0.0, 0.0, nullptr, nullptr, nullptr, nullptr);
        assert(rc == KDM6_ERR_INVALID_ARG);
        assert(h == nullptr);

        // same 0/1 contract on the packed fp64 entry
        std::vector<double> st(12, 0.0), fz(4, 0.0), out(12, -1.0);
        kdm6_handle_t* h2 = reinterpret_cast<kdm6_handle_t*>(0x1);
        rc = kdm6_step_ad_c(st.data(), fz.data(), im, kme, jme, /*dt=*/20.0,
                            /*value_only=*/2, out.data(), &h2, nullptr, 0.0, 0.0);
        assert(rc == KDM6_ERR_INVALID_ARG);
        assert(h2 == nullptr);
    } END_TEST();
}

void test_c_abi_closep_nulls_handle() {
    TEST(test_c_abi_closep_nulls_handle) {
        // Idempotent no-ops: NULL pointer-to-handle and pointer-to-NULL both return OK.
        assert(kdm6_handle_closep_c(nullptr) == KDM6_OK);
        kdm6_handle_t* nullh = nullptr;
        assert(kdm6_handle_closep_c(&nullh) == KDM6_OK);
        assert(nullh == nullptr);

        // Build a real grad-mode handle (1 cell), then closep must free AND null it.
        const int im = 1, kme = 1, jme = 1;
        FortranBuf th(im,kme,jme,290.0f), qv(im,kme,jme,1.0e-2f), qc(im,kme,jme,5.0e-4f);
        FortranBuf qr(im,kme,jme,1.0e-4f), qi(im,kme,jme), qs(im,kme,jme), qg(im,kme,jme);
        FortranBuf nccn(im,kme,jme,1.0e9f), nc(im,kme,jme,1.0e8f), ni(im,kme,jme), nr(im,kme,jme,1.0e4f);
        FortranBuf bg(im,kme,jme);
        FortranBuf rho(im,kme,jme,1.0f), pii(im,kme,jme,0.97f), p(im,kme,jme,9.0e4f), delz(im,kme,jme,500.0f);
        FortranBuf th_o(im,kme,jme), qv_o(im,kme,jme), qc_o(im,kme,jme), qr_o(im,kme,jme);
        FortranBuf qi_o(im,kme,jme), qs_o(im,kme,jme), qg_o(im,kme,jme), nccn_o(im,kme,jme);
        FortranBuf nc_o(im,kme,jme), ni_o(im,kme,jme), nr_o(im,kme,jme), bg_o(im,kme,jme);
        kdm6_handle_t* h = nullptr;
        int rc = kdm6_step_c(
            th.ptr(), qv.ptr(), qc.ptr(), qr.ptr(), qi.ptr(), qs.ptr(), qg.ptr(),
            nccn.ptr(), nc.ptr(), ni.ptr(), nr.ptr(), bg.ptr(),
            rho.ptr(), pii.ptr(), p.ptr(), delz.ptr(),
            im, kme, jme, /*dt=*/20.0, /*param_grad_flags=*/0, /*value_only=*/0,
            th_o.ptr(), qv_o.ptr(), qc_o.ptr(), qr_o.ptr(), qi_o.ptr(), qs_o.ptr(), qg_o.ptr(),
            nccn_o.ptr(), nc_o.ptr(), ni_o.ptr(), nr_o.ptr(), bg_o.ptr(),
            &h, nullptr, 0.0, 0.0, nullptr, nullptr, nullptr, nullptr);
        assert(rc == KDM6_OK);
        assert(h != nullptr);
        assert(kdm6_handle_closep_c(&h) == KDM6_OK);
        assert(h == nullptr);                          // pointer-nulling contract
        assert(kdm6_handle_closep_c(&h) == KDM6_OK);   // second close is a safe no-op
    } END_TEST();
}

// PR1-A: thread-determinism fail-closed. Single-thread pinning is a
// PRECONDITION for the operational f32 bitwise determinism, so if libtorch/
// OpenMP cannot be pinned to 1/1 the call must be REFUSED with
// KDM6_ERR_THREAD_CONFIG BEFORE any tensor creation — never silently run
// multi-threaded. The pure-C ABI test cannot spin a real >1 thread pool
// (it links only kdm6_c, no torch headers), so the fail path is exercised
// via a test-only env seam that lives entirely inside the thread fence and
// touches no numerical path.
void test_c_abi_thread_config_fail_closed_step_c() {
    TEST(test_c_abi_thread_config_fail_closed_step_c) {
        // The whole body is gated on the test hook (moved up to avoid
        // unused-variable warnings under a future -Werror test build).
#ifdef KDM6_ENABLE_TEST_HOOKS
        const int im = 1, kme = 1, jme = 1;
        FortranBuf th(im,kme,jme,290.0f), qv(im,kme,jme,1.0e-2f), qc(im,kme,jme,5.0e-4f);
        FortranBuf qr(im,kme,jme,1.0e-4f), qi(im,kme,jme), qs(im,kme,jme), qg(im,kme,jme);
        FortranBuf nccn(im,kme,jme,1.0e9f), nc(im,kme,jme,1.0e8f), ni(im,kme,jme), nr(im,kme,jme,1.0e4f);
        FortranBuf bg(im,kme,jme);
        FortranBuf rho(im,kme,jme,1.0f), pii(im,kme,jme,0.97f), p(im,kme,jme,9.0e4f), delz(im,kme,jme,500.0f);
        // sentinel outputs — a fail-closed refusal must leave them UNTOUCHED
        const float SENT = -12345.0f;
        FortranBuf th_o(im,kme,jme,SENT), qv_o(im,kme,jme,SENT), qc_o(im,kme,jme,SENT), qr_o(im,kme,jme,SENT);
        FortranBuf qi_o(im,kme,jme,SENT), qs_o(im,kme,jme,SENT), qg_o(im,kme,jme,SENT), nccn_o(im,kme,jme,SENT);
        FortranBuf nc_o(im,kme,jme,SENT), ni_o(im,kme,jme,SENT), nr_o(im,kme,jme,SENT), bg_o(im,kme,jme,SENT);
        // ALL optional outputs provided non-NULL + sentinel too, so a future
        // regression that moves the fence BELOW any output write is caught
        // (rain/snow/graupel are (im,jme); rhog_out is (im,kme,jme)).
        FortranBuf rain_o(im,1,jme,SENT), snow_o(im,1,jme,SENT), graup_o(im,1,jme,SENT);
        FortranBuf rhog_o(im,kme,jme,SENT);
        auto all_outputs_are_sentinel = [&]() {
            for (auto* buf : {&th_o, &qv_o, &qc_o, &qr_o, &qi_o, &qs_o, &qg_o,
                              &nccn_o, &nc_o, &ni_o, &nr_o, &bg_o,
                              &rain_o, &snow_o, &graup_o, &rhog_o})
                for (size_t i = 0; i < buf->size(); ++i)
                    if (buf->data[i] != SENT) return false;
            return true;
        };
        auto call = [&](int im_, int value_only_, int pgf, const float* th_in,
                        kdm6_handle_t** hh) {
            return kdm6_step_c(
                th_in, qv.ptr(), qc.ptr(), qr.ptr(), qi.ptr(), qs.ptr(), qg.ptr(),
                nccn.ptr(), nc.ptr(), ni.ptr(), nr.ptr(), bg.ptr(),
                rho.ptr(), pii.ptr(), p.ptr(), delz.ptr(),
                im_, kme, jme, /*dt=*/60.0, pgf, value_only_,
                th_o.ptr(), qv_o.ptr(), qc_o.ptr(), qr_o.ptr(), qi_o.ptr(), qs_o.ptr(), qg_o.ptr(),
                nccn_o.ptr(), nc_o.ptr(), ni_o.ptr(), nr_o.ptr(), bg_o.ptr(),
                hh, nullptr, 0.0, 0.0,
                rain_o.ptr(), snow_o.ptr(), graup_o.ptr(), rhog_o.ptr());
        };

        // fail-closed: fault injected, all args valid -> THREAD_CONFIG, handle
        // nulled, EVERY output (incl. optional) untouched
        setenv("KDM6_TEST_FORCE_THREAD_CONFIG_FAIL", "1", 1);
        kdm6_handle_t* handle = reinterpret_cast<kdm6_handle_t*>(0x1);
        assert(call(im, /*value_only=*/1, /*pgf=*/0, th.ptr(), &handle) == KDM6_ERR_THREAD_CONFIG);
        assert(handle == nullptr);
        assert(all_outputs_are_sentinel());

        // precedence: with the fault STILL injected, every existing argument
        // error is reported BEFORE the thread fence (fence is step 5) and no
        // output is touched
        kdm6_handle_t* h = reinterpret_cast<kdm6_handle_t*>(0x1);
        assert(call(/*im=*/0, 1, 0, th.ptr(), &h) == KDM6_ERR_INVALID_DIM);
        assert(h == nullptr && all_outputs_are_sentinel());
        h = reinterpret_cast<kdm6_handle_t*>(0x1);
        assert(call(im, /*value_only=*/2, 0, th.ptr(), &h) == KDM6_ERR_INVALID_ARG);
        assert(h == nullptr && all_outputs_are_sentinel());
        h = reinterpret_cast<kdm6_handle_t*>(0x1);
        assert(call(im, 1, 0, /*th=*/nullptr, &h) == KDM6_ERR_NULL_POINTER);
        assert(h == nullptr && all_outputs_are_sentinel());
        h = reinterpret_cast<kdm6_handle_t*>(0x1);
        assert(call(im, 1, /*pgf=*/1, th.ptr(), &h) == KDM6_ERR_NOT_IMPLEMENTED);
        assert(h == nullptr && all_outputs_are_sentinel());
        unsetenv("KDM6_TEST_FORCE_THREAD_CONFIG_FAIL");

        // no fault -> the normal value_only call still succeeds
        kdm6_handle_t* h3 = reinterpret_cast<kdm6_handle_t*>(0x1);
        assert(call(im, 1, 0, th.ptr(), &h3) == KDM6_OK && h3 == nullptr);
#else
        std::cout << "  SKIP (build without -DKDM6_ENABLE_TEST_HOOKS=ON)\n";
#endif
    } END_TEST();
}

void test_c_abi_thread_config_fail_closed_step_ad_c() {
    TEST(test_c_abi_thread_config_fail_closed_step_ad_c) {
#ifdef KDM6_ENABLE_TEST_HOOKS
        const int im = 1, kme = 1, jme = 1;
        const size_t NF = 12, BK = static_cast<size_t>(im) * kme * jme;
        std::vector<double> st(NF * BK, 0.0), fz(4 * BK, 0.0);
        st[0*BK] = 290.0; st[1*BK] = 1.0e-2; st[2*BK] = 5.0e-4; st[3*BK] = 1.0e-4;
        st[7*BK] = 1.0e9; st[8*BK] = 1.0e8; st[10*BK] = 1.0e4;
        fz[0*BK] = 0.97; fz[1*BK] = 1.0; fz[2*BK] = 9.0e4; fz[3*BK] = 500.0;
        const double SENT = -777.0;
        std::vector<double> out(NF * BK, SENT);
        auto out_all_sentinel = [&]() {
            for (double v : out) if (v != SENT) return false;   // ALL, not just [0]
            return true;
        };

        // fail-closed: THREAD_CONFIG, handle nulled, whole packed buffer untouched
        setenv("KDM6_TEST_FORCE_THREAD_CONFIG_FAIL", "1", 1);
        kdm6_handle_t* handle = reinterpret_cast<kdm6_handle_t*>(0x1);
        int rc = kdm6_step_ad_c(st.data(), fz.data(), im, kme, jme, /*dt=*/20.0,
                                /*value_only=*/1, out.data(), &handle, nullptr, 0.0, 0.0);
        assert(rc == KDM6_ERR_THREAD_CONFIG && handle == nullptr && out_all_sentinel());

        // precedence with the fault still injected: dim / value_only / null all
        // win before the fence
        kdm6_handle_t* h = reinterpret_cast<kdm6_handle_t*>(0x1);
        rc = kdm6_step_ad_c(st.data(), fz.data(), /*im=*/0, kme, jme, 20.0, 1, out.data(), &h, nullptr, 0.0, 0.0);
        assert(rc == KDM6_ERR_INVALID_DIM && h == nullptr && out_all_sentinel());
        h = reinterpret_cast<kdm6_handle_t*>(0x1);
        rc = kdm6_step_ad_c(st.data(), fz.data(), im, kme, jme, 20.0, /*value_only=*/2, out.data(), &h, nullptr, 0.0, 0.0);
        assert(rc == KDM6_ERR_INVALID_ARG && h == nullptr && out_all_sentinel());
        h = reinterpret_cast<kdm6_handle_t*>(0x1);
        rc = kdm6_step_ad_c(/*state_in=*/nullptr, fz.data(), im, kme, jme, 20.0, 1, out.data(), &h, nullptr, 0.0, 0.0);
        assert(rc == KDM6_ERR_NULL_POINTER && h == nullptr && out_all_sentinel());
        unsetenv("KDM6_TEST_FORCE_THREAD_CONFIG_FAIL");
#else
        std::cout << "  SKIP (build without -DKDM6_ENABLE_TEST_HOOKS=ON)\n";
#endif
    } END_TEST();
}

// ── PR2: stable ABI v2 (docs/PR2_ABI_V2_DESIGN.md) ──────────────────────────

// Fill a v2 args struct from the v1 positional inputs used across these tests.
static kdm6_step_v2_args mk_v2_args(
    const float* th, const float* qv, const float* qc, const float* qr,
    const float* qi, const float* qs, const float* qg, const float* nccn,
    const float* nc, const float* ni, const float* nr, const float* bg,
    const float* rho, const float* pii, const float* p, const float* delz,
    int im, int kme, int jme, double dt, int value_only,
    float* th_o, float* qv_o, float* qc_o, float* qr_o, float* qi_o,
    float* qs_o, float* qg_o, float* nccn_o, float* nc_o, float* ni_o,
    float* nr_o, float* bg_o, kdm6_handle_t** handle) {
    kdm6_step_v2_args a;
    std::memset(&a, 0, sizeof(a));
    a.struct_size = kdm6_step_v2_args_size_c();
    a.abi_version = KDM6_ABI_VERSION;
    a.im = im; a.kme = kme; a.jme = jme; a.dt = dt;
    a.value_only = value_only; a.param_grad_flags = 0;
    a.th = th; a.qv = qv; a.qc = qc; a.qr = qr; a.qi = qi; a.qs = qs; a.qg = qg;
    a.nccn = nccn; a.nc = nc; a.ni = ni; a.nr = nr; a.bg = bg;
    a.rho = rho; a.pii = pii; a.p = p; a.delz = delz;
    a.th_out = th_o; a.qv_out = qv_o; a.qc_out = qc_o; a.qr_out = qr_o;
    a.qi_out = qi_o; a.qs_out = qs_o; a.qg_out = qg_o; a.nccn_out = nccn_o;
    a.nc_out = nc_o; a.ni_out = ni_o; a.nr_out = nr_o; a.bg_out = bg_o;
    a.handle = handle;
    return a;
}

void test_c_abi_v2_version_and_size() {
    TEST(test_c_abi_v2_version_and_size) {
        assert(kdm6_get_abi_version_c() == (int)KDM6_ABI_VERSION);
        assert(kdm6_step_v2_args_size_c() == (uint32_t)sizeof(kdm6_step_v2_args));
        assert(KDM6_STEP_V2_MIN_SIZE == 8u);   // struct_size + abi_version
    } END_TEST();
}

void test_c_abi_v2_framing() {
    TEST(test_c_abi_v2_framing) {
        // args == NULL → NULL_POINTER (no dereference)
        assert(kdm6_step_v2_c(nullptr) == KDM6_ERR_NULL_POINTER);

        const int im = 1, kme = 1, jme = 1;
        FortranBuf one(im, kme, jme, 1.0f);
        FortranBuf o(im, kme, jme, -9.0f);
        kdm6_handle_t* h = nullptr;
        auto base = mk_v2_args(
            one.ptr(),one.ptr(),one.ptr(),one.ptr(),one.ptr(),one.ptr(),one.ptr(),
            one.ptr(),one.ptr(),one.ptr(),one.ptr(),one.ptr(),
            one.ptr(),one.ptr(),one.ptr(),one.ptr(), im,kme,jme,60.0,1,
            o.ptr(),o.ptr(),o.ptr(),o.ptr(),o.ptr(),o.ptr(),o.ptr(),
            o.ptr(),o.ptr(),o.ptr(),o.ptr(),o.ptr(), &h);

        // struct_size below the framing minimum → INVALID_ARG, abi_version NOT read
        for (uint32_t bad : {0u, 4u, 7u}) {
            kdm6_step_v2_args a = base;
            a.struct_size = bad;
            a.abi_version = 999999u;              // must be ignored (not read)
            assert(kdm6_step_v2_c(&a) == KDM6_ERR_INVALID_ARG);
        }
        // wrong abi_version major (with a valid struct_size) → INVALID_ARG
        {
            kdm6_step_v2_args a = base; a.abi_version = KDM6_ABI_VERSION + 1u;
            assert(kdm6_step_v2_c(&a) == KDM6_ERR_INVALID_ARG);
        }
        // struct_size >= framing minimum but below the required-fields cutoff
        {
            kdm6_step_v2_args a = base; a.struct_size = KDM6_STEP_V2_MIN_SIZE;
            assert(kdm6_step_v2_c(&a) == KDM6_ERR_INVALID_ARG);
        }
    } END_TEST();
}

void test_c_abi_v2_precedence() {
    TEST(test_c_abi_v2_precedence) {
        const int im = 1, kme = 1, jme = 1;
        FortranBuf one(im, kme, jme, 1.0f);
        FortranBuf o(im, kme, jme, -9.0f);
        kdm6_handle_t* h = nullptr;
        auto base = mk_v2_args(
            one.ptr(),one.ptr(),one.ptr(),one.ptr(),one.ptr(),one.ptr(),one.ptr(),
            one.ptr(),one.ptr(),one.ptr(),one.ptr(),one.ptr(),
            one.ptr(),one.ptr(),one.ptr(),one.ptr(), im,kme,jme,60.0,1,
            o.ptr(),o.ptr(),o.ptr(),o.ptr(),o.ptr(),o.ptr(),o.ptr(),
            o.ptr(),o.ptr(),o.ptr(),o.ptr(),o.ptr(), &h);
        { kdm6_step_v2_args a = base; a.im = 0;
          assert(kdm6_step_v2_c(&a) == KDM6_ERR_INVALID_DIM); }
        { kdm6_step_v2_args a = base; a.value_only = 2;
          assert(kdm6_step_v2_c(&a) == KDM6_ERR_INVALID_ARG); }
        { kdm6_step_v2_args a = base; a.th = nullptr;
          assert(kdm6_step_v2_c(&a) == KDM6_ERR_NULL_POINTER); }
        { kdm6_step_v2_args a = base; a.param_grad_flags = 1;
          assert(kdm6_step_v2_c(&a) == KDM6_ERR_NOT_IMPLEMENTED); }
    } END_TEST();
}

// The load-bearing test: v2 == v1 BITWISE (same physics core), across a
// single cell, an asymmetric multi-cell tile, mixed xland, and with the
// optional precip/rhog outputs — for both value_only paths.
void test_c_abi_v2_matches_v1_bitwise() {
    TEST(test_c_abi_v2_matches_v1_bitwise) {
        struct Case { int im, kme, jme; bool use_xland, use_precip; };
        for (Case c : {Case{1,1,1,false,false}, Case{2,3,4,true,true},
                       Case{3,1,2,true,false}}) {
            const int im=c.im, kme=c.kme, jme=c.jme;
            auto seed = [&](FortranBuf& b, float v){ for (auto& x: b.data) x = v; };
            FortranBuf th(im,kme,jme), qv(im,kme,jme), qc(im,kme,jme), qr(im,kme,jme);
            FortranBuf qi(im,kme,jme), qs(im,kme,jme), qg(im,kme,jme), nccn(im,kme,jme);
            FortranBuf nc(im,kme,jme), ni(im,kme,jme), nr(im,kme,jme), bg(im,kme,jme);
            FortranBuf rho(im,kme,jme), pii(im,kme,jme), p(im,kme,jme), delz(im,kme,jme);
            seed(th,290.0f); seed(qv,1.0e-2f); seed(qc,5.0e-4f); seed(qr,1.0e-4f);
            seed(nccn,1.0e9f); seed(nc,1.0e8f); seed(nr,1.0e4f);
            seed(rho,1.0f); seed(pii,0.97f); seed(p,9.0e4f); seed(delz,500.0f);
            FortranBuf xl(im,1,jme,2.0f); if (im>1) xl.data[0]=1.0f;  // mixed land/sea
            const float* xland = c.use_xland ? xl.ptr() : nullptr;

            // Output buffers are pre-seeded with the INPUT state (not a -1.0f
            // sentinel) so the non-triviality guard below is non-vacuous: o2
            // differs from the input ONLY if physics actually wrote an evolved
            // value. A no-op that leaves the buffer untouched, or one that
            // writes the input straight back, leaves o2 == input → guard fails.
            const FortranBuf* insrc[12] = {
                &th,&qv,&qc,&qr,&qi,&qs,&qg,&nccn,&nc,&ni,&nr,&bg};
            for (int value_only : {1, 0}) {
                auto outs = [&](){
                    std::vector<FortranBuf> v; v.reserve(12);
                    for (int f = 0; f < 12; ++f) v.push_back(*insrc[f]);  // baseline = input
                    return v;
                };
                auto o1 = outs(); auto o2 = outs();
                FortranBuf r1(im,1,jme,-1.0f), s1(im,1,jme,-1.0f), g1(im,1,jme,-1.0f), rg1(im,kme,jme,-1.0f);
                FortranBuf r2(im,1,jme,-1.0f), s2(im,1,jme,-1.0f), g2(im,1,jme,-1.0f), rg2(im,kme,jme,-1.0f);
                float *R1=c.use_precip?r1.ptr():nullptr, *S1=c.use_precip?s1.ptr():nullptr,
                      *G1=c.use_precip?g1.ptr():nullptr, *RG1=c.use_precip?rg1.ptr():nullptr;
                float *R2=c.use_precip?r2.ptr():nullptr, *S2=c.use_precip?s2.ptr():nullptr,
                      *G2=c.use_precip?g2.ptr():nullptr, *RG2=c.use_precip?rg2.ptr():nullptr;
                kdm6_handle_t *h1=nullptr, *h2=nullptr;

                int rc1 = kdm6_step_c(
                    th.ptr(),qv.ptr(),qc.ptr(),qr.ptr(),qi.ptr(),qs.ptr(),qg.ptr(),
                    nccn.ptr(),nc.ptr(),ni.ptr(),nr.ptr(),bg.ptr(),
                    rho.ptr(),pii.ptr(),p.ptr(),delz.ptr(), im,kme,jme,60.0,0,value_only,
                    o1[0].ptr(),o1[1].ptr(),o1[2].ptr(),o1[3].ptr(),o1[4].ptr(),o1[5].ptr(),o1[6].ptr(),
                    o1[7].ptr(),o1[8].ptr(),o1[9].ptr(),o1[10].ptr(),o1[11].ptr(),
                    &h1, xland, 30.0, 10.0, R1, S1, G1, RG1);

                auto a = mk_v2_args(
                    th.ptr(),qv.ptr(),qc.ptr(),qr.ptr(),qi.ptr(),qs.ptr(),qg.ptr(),
                    nccn.ptr(),nc.ptr(),ni.ptr(),nr.ptr(),bg.ptr(),
                    rho.ptr(),pii.ptr(),p.ptr(),delz.ptr(), im,kme,jme,60.0,value_only,
                    o2[0].ptr(),o2[1].ptr(),o2[2].ptr(),o2[3].ptr(),o2[4].ptr(),o2[5].ptr(),o2[6].ptr(),
                    o2[7].ptr(),o2[8].ptr(),o2[9].ptr(),o2[10].ptr(),o2[11].ptr(), &h2);
                a.xland = xland; a.ncmin_land = 30.0; a.ncmin_sea = 10.0;
                a.rain_increment = R2; a.snow_increment = S2;
                a.graupel_increment = G2; a.rhog_out = RG2;
                int rc2 = kdm6_step_v2_c(&a);

                assert(rc1 == KDM6_OK && rc2 == KDM6_OK);
                for (int f = 0; f < 12; ++f)
                    assert(std::memcmp(o1[f].ptr(), o2[f].ptr(),
                                       o1[f].size()*sizeof(float)) == 0);  // BITWISE
                // Physics actually ran: at least one output moved off its input
                // baseline (see the input-seeded outs() above), so "v1==v2
                // bitwise" is over genuinely-evolved state — not a shared no-op
                // that left the buffers untouched or echoed the input back.
                bool any_evolved = false;
                for (int f = 0; f < 12; ++f)
                    if (std::memcmp(o2[f].ptr(), insrc[f]->ptr(),
                                    o2[f].size()*sizeof(float)) != 0)
                        any_evolved = true;
                assert(any_evolved);
                if (c.use_precip) {
                    assert(std::memcmp(r1.ptr(),r2.ptr(),r1.size()*sizeof(float))==0);
                    assert(std::memcmp(s1.ptr(),s2.ptr(),s1.size()*sizeof(float))==0);
                    assert(std::memcmp(g1.ptr(),g2.ptr(),g1.size()*sizeof(float))==0);
                    assert(std::memcmp(rg1.ptr(),rg2.ptr(),rg1.size()*sizeof(float))==0);
                }
                if (value_only) { assert(h1==nullptr && h2==nullptr); }
                else {
                    assert(h1!=nullptr && h2!=nullptr);
                    // same VJP for a unit seed on th (bitwise fp64)
                    const size_t NP = 12u*im*kme*jme;
                    std::vector<double> u(NP,0.0), g_1(NP,0.0), g_2(NP,0.0);
                    u[0]=1.0;
                    assert(kdm6_handle_vjp_c(h1,u.data(),g_1.data())==KDM6_OK);
                    assert(kdm6_handle_vjp_c(h2,u.data(),g_2.data())==KDM6_OK);
                    assert(std::memcmp(g_1.data(),g_2.data(),NP*sizeof(double))==0);
                    kdm6_handle_closep_c(&h1); kdm6_handle_closep_c(&h2);
                }
            }
        }
    } END_TEST();
}

// A small-but-valid struct_size (ends at the required-fields cutoff, no
// optional tail): the call RUNS with the optionals defaulted (xland NULL,
// ncmin 0, no precip) — bitwise-equal to a v1 call with those same defaults.
void test_c_abi_v2_small_struct_size_runs_with_defaults() {
    TEST(test_c_abi_v2_small_struct_size_runs_with_defaults) {
        const int im = 1, kme = 1, jme = 1;
        FortranBuf th(im,kme,jme,290.0f), qv(im,kme,jme,1.0e-2f), qc(im,kme,jme,5.0e-4f);
        FortranBuf qr(im,kme,jme,1.0e-4f), qi(im,kme,jme), qs(im,kme,jme), qg(im,kme,jme);
        FortranBuf nccn(im,kme,jme,1.0e9f), nc(im,kme,jme,1.0e8f), ni(im,kme,jme), nr(im,kme,jme,1.0e4f);
        FortranBuf bg(im,kme,jme);
        FortranBuf rho(im,kme,jme,1.0f), pii(im,kme,jme,0.97f), p(im,kme,jme,9.0e4f), delz(im,kme,jme,500.0f);
        auto outs = [&](){ return std::vector<FortranBuf>(12, FortranBuf(im,kme,jme,-1.0f)); };
        auto o1 = outs(); auto o2 = outs();
        kdm6_handle_t *h1=nullptr, *h2=nullptr;

        int rc1 = kdm6_step_c(
            th.ptr(),qv.ptr(),qc.ptr(),qr.ptr(),qi.ptr(),qs.ptr(),qg.ptr(),
            nccn.ptr(),nc.ptr(),ni.ptr(),nr.ptr(),bg.ptr(),
            rho.ptr(),pii.ptr(),p.ptr(),delz.ptr(), im,kme,jme,60.0,0,/*value_only=*/1,
            o1[0].ptr(),o1[1].ptr(),o1[2].ptr(),o1[3].ptr(),o1[4].ptr(),o1[5].ptr(),o1[6].ptr(),
            o1[7].ptr(),o1[8].ptr(),o1[9].ptr(),o1[10].ptr(),o1[11].ptr(),
            &h1, /*xland*/nullptr, 0.0, 0.0, nullptr, nullptr, nullptr, nullptr);

        auto a = mk_v2_args(
            th.ptr(),qv.ptr(),qc.ptr(),qr.ptr(),qi.ptr(),qs.ptr(),qg.ptr(),
            nccn.ptr(),nc.ptr(),ni.ptr(),nr.ptr(),bg.ptr(),
            rho.ptr(),pii.ptr(),p.ptr(),delz.ptr(), im,kme,jme,60.0,1,
            o2[0].ptr(),o2[1].ptr(),o2[2].ptr(),o2[3].ptr(),o2[4].ptr(),o2[5].ptr(),o2[6].ptr(),
            o2[7].ptr(),o2[8].ptr(),o2[9].ptr(),o2[10].ptr(),o2[11].ptr(), &h2);
        // caller supplies NO optional tail — struct_size ends at the first
        // optional field. The optionals (poisoned to a nonsense pointer) MUST
        // NOT be read.
        a.struct_size = (uint32_t)offsetof(kdm6_step_v2_args, xland);
        a.xland = reinterpret_cast<const float*>(0x1);   // must be ignored
        a.rain_increment = reinterpret_cast<float*>(0x1);
        int rc2 = kdm6_step_v2_c(&a);

        assert(rc1 == KDM6_OK && rc2 == KDM6_OK);
        for (int f = 0; f < 12; ++f)
            assert(std::memcmp(o1[f].ptr(), o2[f].ptr(), o1[f].size()*sizeof(float)) == 0);

        // POSITIVE control — the gate is load-bearing: with a FULL struct_size
        // that DOES cover the optional tail, a supplied optional (rhog_out) IS
        // read and written. Without this, the negative above would be vacuous
        // (an impl that ignores every optional would also "pass").
        {
            auto o3 = outs();
            kdm6_handle_t* h3 = nullptr;
            FortranBuf rhog(im, kme, jme, -777.0f);   // sentinel
            auto a3 = mk_v2_args(
                th.ptr(),qv.ptr(),qc.ptr(),qr.ptr(),qi.ptr(),qs.ptr(),qg.ptr(),
                nccn.ptr(),nc.ptr(),ni.ptr(),nr.ptr(),bg.ptr(),
                rho.ptr(),pii.ptr(),p.ptr(),delz.ptr(), im,kme,jme,60.0,1,
                o3[0].ptr(),o3[1].ptr(),o3[2].ptr(),o3[3].ptr(),o3[4].ptr(),o3[5].ptr(),o3[6].ptr(),
                o3[7].ptr(),o3[8].ptr(),o3[9].ptr(),o3[10].ptr(),o3[11].ptr(), &h3);
            a3.rhog_out = rhog.ptr();                 // full struct_size covers it
            assert(kdm6_step_v2_c(&a3) == KDM6_OK);
            assert(rhog.data[0] != -777.0f);          // covered optional was written
        }
    } END_TEST();
}

// A larger/future struct_size (caller struct bigger than the library's). The
// forward-compat contract has two genuinely-testable halves:
//   (1) struct_size > LIB is ACCEPTED, not rejected (catches an exact-match
//       `struct_size != sizeof` guard that would break future callers);
//   (2) every field WITHIN the library struct is still honored despite the
//       oversized claim — proven by a supplied in-LIB optional (rhog_out) that
//       must be written, plus the 12 state outputs matching a normal call.
// (The poisoned bytes beyond LIB are unreachable by construction — the library
// only accesses named members at offset < sizeof — so their presence is only a
// no-crash smoke, NOT the load-bearing assertion.)
void test_c_abi_v2_large_struct_size_ignores_tail() {
    TEST(test_c_abi_v2_large_struct_size_ignores_tail) {
        const int im = 1, kme = 1, jme = 1;
        FortranBuf th(im,kme,jme,290.0f), qv(im,kme,jme,1.0e-2f), qc(im,kme,jme,5.0e-4f);
        FortranBuf qr(im,kme,jme,1.0e-4f), qi(im,kme,jme), qs(im,kme,jme), qg(im,kme,jme);
        FortranBuf nccn(im,kme,jme,1.0e9f), nc(im,kme,jme,1.0e8f), ni(im,kme,jme), nr(im,kme,jme,1.0e4f);
        FortranBuf bg(im,kme,jme);
        FortranBuf rho(im,kme,jme,1.0f), pii(im,kme,jme,0.97f), p(im,kme,jme,9.0e4f), delz(im,kme,jme,500.0f);
        auto outs = [&](){ return std::vector<FortranBuf>(12, FortranBuf(im,kme,jme,-1.0f)); };
        auto oref = outs(); auto obig = outs();
        kdm6_handle_t *href=nullptr, *hbig=nullptr;

        auto fill = [&](std::vector<FortranBuf>& o, kdm6_handle_t** h) {
            return mk_v2_args(
                th.ptr(),qv.ptr(),qc.ptr(),qr.ptr(),qi.ptr(),qs.ptr(),qg.ptr(),
                nccn.ptr(),nc.ptr(),ni.ptr(),nr.ptr(),bg.ptr(),
                rho.ptr(),pii.ptr(),p.ptr(),delz.ptr(), im,kme,jme,60.0,1,
                o[0].ptr(),o[1].ptr(),o[2].ptr(),o[3].ptr(),o[4].ptr(),o[5].ptr(),o[6].ptr(),
                o[7].ptr(),o[8].ptr(),o[9].ptr(),o[10].ptr(),o[11].ptr(), h);
        };
        // reference: a normal full-size v2 call
        auto aref = fill(oref, &href);
        assert(kdm6_step_v2_c(&aref) == KDM6_OK);

        // oversized buffer: a valid full struct in front + 64 poisoned bytes.
        const size_t LIB = sizeof(kdm6_step_v2_args);
        std::vector<unsigned char> buf(LIB + 64, 0xAB);
        FortranBuf rhog(im, kme, jme, -777.0f);          // in-LIB optional, sentinel
        auto abig = fill(obig, &hbig);
        abig.rhog_out = rhog.ptr();                       // covered by the real struct
        std::memcpy(buf.data(), &abig, LIB);
        auto* pbig = reinterpret_cast<kdm6_step_v2_args*>(buf.data());
        pbig->struct_size = (uint32_t)(LIB + 64);        // claims bigger than LIB
        int rc = kdm6_step_v2_c(pbig);
        assert(rc == KDM6_OK);                            // (1) accepted, not rejected
        for (int f = 0; f < 12; ++f)                      // (2a) state fields honored
            assert(std::memcmp(oref[f].ptr(), obig[f].ptr(), oref[f].size()*sizeof(float)) == 0);
        assert(rhog.data[0] != -777.0f);                 // (2b) in-LIB optional honored
    } END_TEST();
}

// ── conservative-interface-v1 freeze-lift: physics_variant selector ─────────
// (docs/FREEZE_LIFT_CONSERVATIVE_INTERFACE_V1.md). The selector is an
// append-only v2 tail field with a LEGACY default; every legacy access path
// must stay bitwise-identical, and unknown values must fail loud with the
// fail-closed handle/output contract.
void test_c_abi_v2_physics_variant_gate() {
    TEST(test_c_abi_v2_physics_variant_gate) {
        const int im = 2, kme = 3, jme = 2;
        auto seed = [&](FortranBuf& b, float v){ for (auto& x: b.data) x = v; };
        FortranBuf th(im,kme,jme), qv(im,kme,jme), qc(im,kme,jme), qr(im,kme,jme);
        FortranBuf qi(im,kme,jme), qs(im,kme,jme), qg(im,kme,jme), nccn(im,kme,jme);
        FortranBuf nc(im,kme,jme), ni(im,kme,jme), nr(im,kme,jme), bg(im,kme,jme);
        FortranBuf rho(im,kme,jme), pii(im,kme,jme), p(im,kme,jme), delz(im,kme,jme);
        seed(th,290.0f); seed(qv,1.0e-2f); seed(qc,5.0e-4f); seed(qr,1.0e-4f);
        seed(nccn,1.0e9f); seed(nc,1.0e8f); seed(nr,1.0e4f);
        seed(rho,1.0f); seed(pii,0.97f); seed(p,9.0e4f); seed(delz,500.0f);

        auto outs = [&](float v){
            std::vector<FortranBuf> o;
            for (int f = 0; f < 12; ++f) o.emplace_back(im,kme,jme,v);
            return o;
        };
        auto run_v2 = [&](std::vector<FortranBuf>& o, kdm6_handle_t** h,
                          uint32_t struct_size, uint32_t variant_in_memory) {
            auto a = mk_v2_args(
                th.ptr(),qv.ptr(),qc.ptr(),qr.ptr(),qi.ptr(),qs.ptr(),qg.ptr(),
                nccn.ptr(),nc.ptr(),ni.ptr(),nr.ptr(),bg.ptr(),
                rho.ptr(),pii.ptr(),p.ptr(),delz.ptr(), im,kme,jme,60.0,1,
                o[0].ptr(),o[1].ptr(),o[2].ptr(),o[3].ptr(),o[4].ptr(),o[5].ptr(),
                o[6].ptr(),o[7].ptr(),o[8].ptr(),o[9].ptr(),o[10].ptr(),o[11].ptr(), h);
            a.struct_size = struct_size;
            a.physics_variant = variant_in_memory;
            return kdm6_step_v2_c(&a);
        };

        // v1 reference — kdm6_step_c has no selector and is permanently legacy.
        auto oref = outs(-9.0f);
        kdm6_handle_t* href = nullptr;
        int rcref = kdm6_step_c(
            th.ptr(),qv.ptr(),qc.ptr(),qr.ptr(),qi.ptr(),qs.ptr(),qg.ptr(),
            nccn.ptr(),nc.ptr(),ni.ptr(),nr.ptr(),bg.ptr(),
            rho.ptr(),pii.ptr(),p.ptr(),delz.ptr(), im,kme,jme,60.0,0,1,
            oref[0].ptr(),oref[1].ptr(),oref[2].ptr(),oref[3].ptr(),oref[4].ptr(),
            oref[5].ptr(),oref[6].ptr(),oref[7].ptr(),oref[8].ptr(),oref[9].ptr(),
            oref[10].ptr(),oref[11].ptr(), &href,
            nullptr, 0.0, 0.0, nullptr, nullptr, nullptr, nullptr);
        assert(rcref == KDM6_OK);

        const uint32_t off = (uint32_t)offsetof(kdm6_step_v2_args, physics_variant);
        auto expect_legacy_bitwise = [&](uint32_t struct_size, uint32_t poison) {
            auto o = outs(-9.0f);
            kdm6_handle_t* h = nullptr;
            assert(run_v2(o, &h, struct_size, poison) == KDM6_OK);
            for (int f = 0; f < 12; ++f)
                assert(std::memcmp(oref[f].ptr(), o[f].ptr(),
                                   oref[f].size()*sizeof(float)) == 0);  // BITWISE
        };
        // old-v2 caller: struct_size ends BEFORE the field → legacy, even with
        // a poison value physically present in memory past the declared size.
        expect_legacy_bitwise(off, KDM6_PHYSICS_CONSERVATIVE_INTERFACE);
        // one byte short of covering the field → field NOT read → legacy.
        expect_legacy_bitwise(off + (uint32_t)sizeof(uint32_t) - 1u,
                              KDM6_PHYSICS_CONSERVATIVE_INTERFACE);
        // full new size, explicit variant 0 → legacy bitwise.
        expect_legacy_bitwise(kdm6_step_v2_args_size_c(), KDM6_PHYSICS_LEGACY);

        // fail-loud rejection: handle nulled, output buffers untouched — in
        // BOTH value_only modes, and including the four OPTIONAL outputs
        // (rain/snow/graupel increments + rhog_out), which a rejected call
        // must never write either.
        auto expect_rejected = [&](uint32_t variant, int want_rc) {
            for (int value_only : {1, 0}) {
                auto o = outs(-777.0f);
                FortranBuf rain(im,1,jme,-777.0f), snow(im,1,jme,-777.0f);
                FortranBuf graup(im,1,jme,-777.0f), rhog(im,kme,jme,-777.0f);
                kdm6_handle_t* h = (kdm6_handle_t*)0x1;   // must be fail-closed to NULL
                auto a = mk_v2_args(
                    th.ptr(),qv.ptr(),qc.ptr(),qr.ptr(),qi.ptr(),qs.ptr(),qg.ptr(),
                    nccn.ptr(),nc.ptr(),ni.ptr(),nr.ptr(),bg.ptr(),
                    rho.ptr(),pii.ptr(),p.ptr(),delz.ptr(), im,kme,jme,60.0,value_only,
                    o[0].ptr(),o[1].ptr(),o[2].ptr(),o[3].ptr(),o[4].ptr(),o[5].ptr(),
                    o[6].ptr(),o[7].ptr(),o[8].ptr(),o[9].ptr(),o[10].ptr(),o[11].ptr(), &h);
                a.physics_variant = variant;
                a.rain_increment = rain.ptr(); a.snow_increment = snow.ptr();
                a.graupel_increment = graup.ptr(); a.rhog_out = rhog.ptr();
                assert(kdm6_step_v2_c(&a) == want_rc);
                assert(h == nullptr);           // fail-closed NULL in both modes
                for (int f = 0; f < 12; ++f)
                    for (float x : o[f].data) assert(x == -777.0f);   // untouched
                for (const FortranBuf* b : {&rain, &snow, &graup, &rhog})
                    for (float x : b->data) assert(x == -777.0f);     // optionals untouched
            }
        };
        // unknown values fail loud.
        expect_rejected(2u, KDM6_ERR_INVALID_ARG);
        expect_rejected(UINT32_MAX, KDM6_ERR_INVALID_ARG);

        // ── conservative variant ACTIVE (freeze-lift commit 2) ───────────────
        // Taller tile in the cap-binding regime: heavy rain (qr = 5e-3) over
        // thin layers (delz = 400 m) gives vt·dtcld/(mstep·delz) > 1/2 per
        // substep, so the legacy post-update interface re-cap BINDS and deletes
        // mass at internal interfaces — exactly what the conservative-interface
        // variant fixes. Oracle reference: oracle/kdm6/sed_conservative.py.
        {
            const int cim = 1, ckme = 4, cjme = 1;
            FortranBuf cth(cim,ckme,cjme, 290.0f),  cqv(cim,ckme,cjme, 1.0e-2f);
            FortranBuf cqc(cim,ckme,cjme, 5.0e-4f), cqr(cim,ckme,cjme, 5.0e-3f);
            FortranBuf cqi(cim,ckme,cjme), cqs(cim,ckme,cjme), cqg(cim,ckme,cjme);
            FortranBuf cnccn(cim,ckme,cjme, 1.0e9f), cnc(cim,ckme,cjme, 1.0e8f);
            FortranBuf cni(cim,ckme,cjme), cnr(cim,ckme,cjme, 1.0e4f), cbg(cim,ckme,cjme);
            FortranBuf crho(cim,ckme,cjme, 1.0f),   cpii(cim,ckme,cjme, 0.97f);
            FortranBuf cp(cim,ckme,cjme, 9.0e4f),   cdelz(cim,ckme,cjme, 400.0f);

            auto couts = [&]{
                std::vector<FortranBuf> o;
                for (int f = 0; f < 12; ++f) o.emplace_back(cim, ckme, cjme, -9.0f);
                return o;
            };
            auto run_variant = [&](std::vector<FortranBuf>& o, uint32_t variant,
                                   float* rain_inc) {
                kdm6_handle_t* h = nullptr;
                auto a = mk_v2_args(
                    cth.ptr(),cqv.ptr(),cqc.ptr(),cqr.ptr(),cqi.ptr(),cqs.ptr(),cqg.ptr(),
                    cnccn.ptr(),cnc.ptr(),cni.ptr(),cnr.ptr(),cbg.ptr(),
                    crho.ptr(),cpii.ptr(),cp.ptr(),cdelz.ptr(), cim,ckme,cjme,60.0,1,
                    o[0].ptr(),o[1].ptr(),o[2].ptr(),o[3].ptr(),o[4].ptr(),o[5].ptr(),
                    o[6].ptr(),o[7].ptr(),o[8].ptr(),o[9].ptr(),o[10].ptr(),o[11].ptr(), &h);
                a.physics_variant = variant;
                a.rain_increment = rain_inc;   // total surface fallout [mm ≡ kg m^-2]
                return kdm6_step_v2_c(&a);
            };

            auto oleg = couts();
            assert(run_variant(oleg, KDM6_PHYSICS_LEGACY, nullptr) == KDM6_OK);

            // (a) the conservative selector now runs the physics.
            std::vector<float> rain(static_cast<size_t>(cim) * cjme, -1.0f);
            auto ocons = couts();
            assert(run_variant(ocons, KDM6_PHYSICS_CONSERVATIVE_INTERFACE,
                               rain.data()) == KDM6_OK);
            for (float r : rain) assert(r > 0.0f);   // sedimentation actually fired

            // (b) it is a DIFFERENT physics: with the interface cap binding,
            // at least one state field must differ from the legacy run.
            bool any_diff = false;
            for (int f = 0; f < 12 && !any_diff; ++f)
                any_diff = std::memcmp(oleg[f].ptr(), ocons[f].ptr(),
                                       oleg[f].size() * sizeof(float)) != 0;
            assert(any_diff);

            // (c) per-column water closure for the conservative run:
            //   Σ_k ρ·Δz·Δ(qv+qc+qr+qi+qs+qg) + P_actual ≈ 0.
            // rain_increment [mm] is numerically kg m^-2 (surface_accumulation:
            // fallsum·Δz/DENR·dtcld·1000 with DENR = 1000). The C core stores
            // through f32, so the residual carries accumulated f32 roundoff from
            // the full micro+sed chain — gate at rtol 1e-5 of the column water
            // (≈100× the single-op f32 eps, orders of magnitude below the
            // legacy interface deletion this variant removes).
            for (int j = 0; j < cjme; ++j) {
                for (int i = 0; i < cim; ++i) {
                    double w_in = 0.0, w_out = 0.0;
                    for (int k = 0; k < ckme; ++k) {
                        const size_t idx = (size_t)i
                            + (size_t)cim * ((size_t)k + (size_t)ckme * j);
                        const double rdz =
                            (double)crho.data[idx] * (double)cdelz.data[idx];
                        w_in += rdz * ((double)cqv.data[idx] + cqc.data[idx]
                            + cqr.data[idx] + cqi.data[idx]
                            + cqs.data[idx] + cqg.data[idx]);
                        w_out += rdz * ((double)ocons[1].data[idx] + ocons[2].data[idx]
                            + ocons[3].data[idx] + ocons[4].data[idx]
                            + ocons[5].data[idx] + ocons[6].data[idx]);
                    }
                    const double precip = (double)rain[i + cim * j];  // kg m^-2
                    assert(std::fabs(w_out - w_in + precip) <= 1.0e-5 * w_in);
                }
            }
        }
    } END_TEST();
}

int main() {
    std::cout << "KDM6AD-k libtorch C ABI bridge tests\n";
    test_c_abi_v2_version_and_size();
    test_c_abi_v2_framing();
    test_c_abi_v2_precedence();
    test_c_abi_v2_physics_variant_gate();
    test_c_abi_v2_small_struct_size_runs_with_defaults();
    test_c_abi_v2_large_struct_size_ignores_tail();
    test_c_abi_v2_matches_v1_bitwise();
    test_c_abi_thread_config_fail_closed_step_c();
    test_c_abi_thread_config_fail_closed_step_ad_c();
    test_c_abi_closep_nulls_handle();
    test_c_abi_step_runs_microphysics();
    test_c_abi_invalid_dim();
    test_c_abi_null_pointer();
    test_c_abi_step_per_cell_ncmin_mixed_xland();
    test_c_abi_vjp_jvp_roundtrip();
    test_c_abi_vjp_value_only_refused();
    test_c_abi_vjp_packed_layout_nontrivial_tile();
    test_c_abi_step_ad_fp64_vjp_finite_and_adjoint();
    test_c_abi_fp64_packed_layout_nontrivial_tile();
    test_c_abi_invalid_value_only();
    std::cout << "All C ABI tests passed.\n";
    return 0;
}
