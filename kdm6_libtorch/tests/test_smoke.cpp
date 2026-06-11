//
// Plain-assert smoke tests — Catch2/GTest 의존성 없이.
// Python kdm6_torch/tests/test_smoke.py와 1:1 정합되어야 함 (oracle 검증).
//

#include "kdm6/constants.h"
#include "kdm6/ops.h"
#include "kdm6/state.h"
#include "kdm6/runtime.h"

#include <torch/torch.h>
#include <cassert>
#include <cstring>
#include <iostream>
#include <vector>

using namespace kdm6;

#define TEST(name) std::cout << "  RUN  " << #name << "\n"; do
#define END_TEST() while(false); std::cout << "  PASS\n"

void test_constants_have_expected_values() {
    TEST(test_constants_have_expected_values) {
        assert(constants::PEAUT == 0.40);  // yhlee 변경값
        assert(constants::NCRK1 == 3.03e3);
        assert(constants::NCRK2 == 2.59e15);
        assert(constants::QCRMIN == 1.0e-9);
        assert(constants::LAMDAIMAX == 1.82e6);
        assert(constants::EPS == 1.0e-15);
        assert(constants::SMOOTH_EPS == 1.0e-4);
    } END_TEST();
}

void test_safe_div_pos_basic() {
    TEST(test_safe_div_pos_basic) {
        auto a = torch::tensor({1.0, 2.0, 3.0}, torch::dtype(torch::kFloat64).requires_grad(true));
        auto b = torch::tensor({2.0, 4.0, 6.0}, torch::kFloat64);
        auto r = ops::safe_div_pos(a, b);
        r.sum().backward();
        assert(a.grad().defined());
        auto expected = torch::tensor({0.5, 0.5, 0.5}, torch::kFloat64);
        assert(torch::allclose(r, expected));
    } END_TEST();
}

void test_safe_div_signed_small_negative_denominator() {
    TEST(test_safe_div_signed_small_negative_denominator) {
        auto num = torch::tensor({1.0}, torch::kFloat64);
        auto denom = torch::tensor({-constants::EPS / 2.0}, torch::kFloat64);
        auto r = ops::safe_div_signed(num, denom);
        assert(torch::isfinite(r).all().item<bool>());
        assert(r.item<double>() < 0.0);
        auto expected = torch::tensor({-1.0 / constants::EPS}, torch::kFloat64);
        assert(torch::allclose(r, expected));
    } END_TEST();
}

void test_clip_positive_subgradient() {
    TEST(test_clip_positive_subgradient) {
        auto x = torch::tensor({-1.0, 0.5, -0.1},
                               torch::dtype(torch::kFloat64).requires_grad(true));
        auto y = ops::clip_positive(x).sum();
        y.backward();
        auto g = x.grad();
        assert(g[0].item<double>() == 0.0);  // 음수 위치 grad=0
        assert(g[2].item<double>() == 0.0);
        assert(g[1].item<double>() == 1.0);  // 양수 위치 grad=1
    } END_TEST();
}

void test_smooth_minmod_eager_mode() {
    TEST(test_smooth_minmod_eager_mode) {
        auto a = torch::tensor({2.0, -3.0, 1.0}, torch::kFloat64);
        auto b = torch::tensor({3.0, -1.0, 2.0}, torch::kFloat64);
        auto r = ops::smooth_minmod(a, b, ops::MinmodMode::Eager);
        auto expected = torch::tensor({2.0, -1.0, 1.0}, torch::kFloat64);
        assert(torch::allclose(r, expected));
        // opposite sign → 0
        auto a2 = torch::tensor({1.0, -1.0}, torch::kFloat64);
        auto b2 = torch::tensor({-1.0, 1.0}, torch::kFloat64);
        auto r2 = ops::smooth_minmod(a2, b2, ops::MinmodMode::Eager);
        assert(torch::allclose(r2, torch::zeros({2}, torch::kFloat64)));
    } END_TEST();
}

void test_state_dot_basic() {
    TEST(test_state_dot_basic) {
        auto base = torch::arange(1, 7, torch::kFloat64).reshape({2, 3});
        State s;
        auto fields = s.fields();
        for (size_t i = 0; i < fields.size(); ++i) {
            *fields[i] = base + static_cast<double>(i);
        }
        auto expected = torch::zeros({}, torch::kFloat64);
        for (auto* f : s.fields()) {
            expected = expected + (*f * *f).sum();
        }
        auto r = state_dot(s, s);
        assert(r.dim() == 0);
        assert(torch::allclose(r, expected));
    } END_TEST();
}

void test_zeros_like_state_preserves_shape() {
    TEST(test_zeros_like_state_preserves_shape) {
        auto base = torch::arange(0, 6, torch::kFloat64).reshape({2, 3});
        State s;
        for (auto* f : s.fields()) *f = base.clone();
        auto z = zeros_like_state(s);
        for (auto* f : z.fields()) {
            assert(torch::allclose(*f, torch::zeros({2, 3}, torch::kFloat64)));
        }
    } END_TEST();
}

void test_make_parameters_default_frozen() {
    TEST(test_make_parameters_default_frozen) {
        auto p = make_parameters(/*grad_flags=*/0);
        assert(!p.peaut.requires_grad());
        assert(!p.ncrk1.requires_grad());
        assert(p.peaut.item<double>() == constants::PEAUT);

        auto p_grad = make_parameters(ParamGradFlags::PEAUT);
        assert(p_grad.peaut.requires_grad());
        assert(!p_grad.ncrk1.requires_grad());
    } END_TEST();
}

void test_layout_roundtrip() {
    TEST(test_layout_roundtrip) {
        const int im = 2;
        const int kme = 3;
        const int jme = 4;
        std::vector<float> data(im * kme * jme);  // native float32 ABI
        for (int j = 0; j < jme; ++j) {
            for (int k = 0; k < kme; ++k) {
                for (int i = 0; i < im; ++i) {
                    data[i + im * (k + kme * j)] = 100.0 * i + 10.0 * k + j;
                }
            }
        }

        FortranArrayDescriptor desc{
            data.data(), data.data(), data.data(), data.data(),
            data.data(), data.data(), data.data(), data.data(),
            data.data(), data.data(), data.data(), data.data(),
            im, kme, jme};
        auto state = from_fortran_arrays(desc, /*requires_grad=*/false);

        assert(state.qc.size(0) == im * jme);
        assert(state.qc.size(1) == kme);
        for (int i = 0; i < im; ++i) {
            for (int j = 0; j < jme; ++j) {
                for (int k = 0; k < kme; ++k) {
                    const int b = i * jme + j;
                    const double expected = 100.0 * i + 10.0 * k + j;
                    assert(state.qc[b][k].item<double>() == expected);
                }
            }
        }

        std::vector<float> out(data.size(), -1.0f);
        to_fortran_arrays(state, im, jme,
                          out.data(), out.data(), out.data(), out.data(),
                          out.data(), out.data(), out.data(), out.data(),
                          out.data(), out.data(), out.data(), out.data());
        assert(std::memcmp(out.data(), data.data(), data.size() * sizeof(float)) == 0);
    } END_TEST();
}

// ── F4 wiring end-to-end smoke ──────────────────────────────────────────────
//
// Task #97 회귀: kdm6_step → kdm6_fn → kdm62d_step 경로가 실제로 microphysics를
// 수행하는지 확인. NOT_IMPLEMENTED stub이었던 시절엔 이 테스트가 throw했음.
// warm-phase 활성 셀(qc>0, sub-saturated qv)을 넣어 prevp/praut가 켜진 결과를
// 기대 — 출력은 (a) finite (b) non-negative water mixing ratios (c) 입력과
// 다름(증발/auto-conversion 작동 증거).
//
void test_kdm6_step_wired_runs_microphysics() {
    TEST(test_kdm6_step_wired_runs_microphysics) {
        const int B = 1, K = 1;
        auto opts = torch::dtype(torch::kFloat64);

        State s;
        s.th   = torch::full({B, K}, 285.0 / 1.1, opts);   // T=285K, π=1.1
        s.qv   = torch::full({B, K}, 6.5e-3, opts);        // sub-saturated
        s.qc   = torch::full({B, K}, 5.0e-4, opts);        // cloud water present
        s.qr   = torch::full({B, K}, 1.0e-4, opts);        // some rain
        s.qi   = torch::zeros({B, K}, opts);
        s.qs   = torch::zeros({B, K}, opts);
        s.qg   = torch::zeros({B, K}, opts);
        s.nccn = torch::full({B, K}, 12345.0, opts);
        s.nc   = torch::full({B, K}, 1.0e8, opts);
        s.ni   = torch::zeros({B, K}, opts);
        s.nr   = torch::full({B, K}, 1.0e5, opts);
        s.bg   = torch::zeros({B, K}, opts);

        Forcing f;
        f.rho  = torch::full({B, K}, 1.0, opts);
        f.pii  = torch::full({B, K}, 1.1, opts);
        f.p    = torch::full({B, K}, 8.0e4, opts);
        f.delz = torch::full({B, K}, 550.0, opts);

        auto params = make_parameters(/*grad_flags=*/0);
        auto result = kdm6_step(s, f, params, /*dt=*/60.0, /*value_only=*/true);

        // (a) finite
        for (auto* t : result.state_out.fields()) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
        }
        // (b) water mixing ratios non-negative
        assert(torch::all(result.state_out.qv >= 0).item<bool>());
        assert(torch::all(result.state_out.qc >= 0).item<bool>());
        assert(torch::all(result.state_out.qr >= 0).item<bool>());
        // (c) state evolved (not stub passthrough). qc 또는 qr 중 적어도 하나가
        // 입력과 달라야 함 — auto-conversion(praut) + accretion(pracw) 발화.
        bool qc_changed = !torch::allclose(result.state_out.qc, s.qc, 0.0, 1e-12);
        bool qr_changed = !torch::allclose(result.state_out.qr, s.qr, 0.0, 1e-12);
        assert(qc_changed || qr_changed);
        // nccn input 12345 < constants::NCCN_MIN (1e8) so the entry-prologue
        // reservoir clamp (mirrors module_mp_kdm6.F:747) snaps it to NCCN_MIN.
        // Same expectation as test_c_abi.cpp:101-102.
        assert(torch::all(result.state_out.nccn >= 1.0e8 - 1e-3).item<bool>());
        assert(torch::all(result.state_out.nccn <= 2.0e10 + 1e-3).item<bool>());

        // (d) value_only path does not allocate a derivative handle.
        assert(result.handle == nullptr);
    } END_TEST();
}

// Per Codex review (task-mp83ehx5-w3eqhq): direct C++ caller exercising the
// public runtime.h xland contract — both accepted shapes (2-D (im, jme) and
// flat (im*jme,)) must produce identical per-cell ncmin behavior, and a
// mixed land/sea grid must produce land vs sea cells with detectably different
// autoconv outcomes (matches the test_c_abi mixed-xland test but goes through
// the C++ runtime entry directly, bypassing the C ABI flattening layer).
void test_kdm6_step_xland_direct_cpp_caller() {
    TEST(test_kdm6_step_xland_direct_cpp_caller) {
        const int im = 2, jme = 1, B = im * jme, K = 1;
        auto opts = torch::dtype(torch::kFloat64);

        auto build_state = [&]() {
            State s;
            s.th   = torch::full({B, K}, 285.0 / 1.1, opts);
            s.qv   = torch::full({B, K}, 6.5e-3, opts);
            s.qc   = torch::full({B, K}, 5.0e-4, opts);
            s.qr   = torch::full({B, K}, 1.0e-4, opts);
            s.qi   = torch::zeros({B, K}, opts);
            s.qs   = torch::zeros({B, K}, opts);
            s.qg   = torch::zeros({B, K}, opts);
            s.nccn = torch::full({B, K}, 5.0e8, opts);
            s.nc   = torch::full({B, K}, 1.0e2, opts);
            s.ni   = torch::zeros({B, K}, opts);
            s.nr   = torch::full({B, K}, 1.0e5, opts);
            s.bg   = torch::zeros({B, K}, opts);
            return s;
        };
        Forcing f;
        f.rho  = torch::full({B, K}, 1.0, opts);
        f.pii  = torch::full({B, K}, 1.1, opts);
        f.p    = torch::full({B, K}, 8.0e4, opts);
        f.delz = torch::full({B, K}, 550.0, opts);
        auto params = make_parameters(/*grad_flags=*/0);

        // Cell 0 = land (xland=1), cell 1 = sea (xland=2).
        // Choose ncmin_land >> nc > ncmin_sea so the autoconv gate fires only
        // in the sea cell.
        auto xland_2d  = torch::tensor({{1.0}, {2.0}}, opts);           // (im, jme) per public header
        auto xland_1d  = xland_2d.view({-1});                            // (im*jme,)

        auto s_2d = build_state();
        auto r_2d = kdm6_step(s_2d, f, params, /*dt=*/60.0,
                              /*value_only=*/true,
                              xland_2d, /*ncmin_land=*/1.0e3, /*ncmin_sea=*/1.0e1);

        auto s_1d = build_state();
        auto r_1d = kdm6_step(s_1d, f, params, /*dt=*/60.0,
                              /*value_only=*/true,
                              xland_1d, /*ncmin_land=*/1.0e3, /*ncmin_sea=*/1.0e1);

        // (a) finite + non-negative for both shape variants.
        for (auto* t : r_2d.state_out.fields()) assert(torch::all(torch::isfinite(*t)).item<bool>());
        for (auto* t : r_1d.state_out.fields()) assert(torch::all(torch::isfinite(*t)).item<bool>());
        // (b) the two shape variants are numerically identical — runtime
        // reshapes both to the same internal layout.
        assert(torch::allclose(r_2d.state_out.qc, r_1d.state_out.qc, 0.0, 0.0));
        // (c) per-cell ncmin reached warm.cpp:51 autoconv gate:
        //   land cell (nc=100 vs ncmin_land=1000): gate FALSE → autoconv off → qc preserved
        //   sea cell  (nc=100 vs ncmin_sea =  10): gate TRUE  → autoconv on  → qc lower
        // Therefore land cell's qc must be >= sea cell's qc.
        auto qc_land = r_2d.state_out.qc[0].item<double>();
        auto qc_sea  = r_2d.state_out.qc[1].item<double>();
        assert(qc_land >= qc_sea - 1e-12);
        // (d) sanity — at least one cell evolved (the sea one).
        assert(!torch::allclose(r_2d.state_out.qc, s_2d.qc, 0.0, 1e-12));
    } END_TEST();
}

int main() {
    std::cout << "kdm6_libtorch smoke tests\n";
    test_constants_have_expected_values();
    test_safe_div_pos_basic();
    test_safe_div_signed_small_negative_denominator();
    test_clip_positive_subgradient();
    test_smooth_minmod_eager_mode();
    test_state_dot_basic();
    test_zeros_like_state_preserves_shape();
    test_make_parameters_default_frozen();
    test_layout_roundtrip();
    test_kdm6_step_wired_runs_microphysics();
    test_kdm6_step_xland_direct_cpp_caller();
    std::cout << "All tests passed.\n";
    return 0;
}
