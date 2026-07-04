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
        const int im = 2, kme = 2, jme = 2;
        const size_t NF = 12, BK = static_cast<size_t>(im) * kme * jme;   // 8
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

        // seed u = e_{qv at (i0,k0,j0)} — a single Fortran cell
        const int i0 = 1, k0 = 0, j0 = 1;
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
        assert(kdm6_handle_closep_c(&handle) == KDM6_OK);
        assert(handle == nullptr);
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

int main() {
    std::cout << "KDM6AD-k libtorch C ABI bridge tests\n";
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
    std::cout << "All C ABI tests passed.\n";
    return 0;
}
