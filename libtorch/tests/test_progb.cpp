#include "kdm6/progb.h"

#include <torch/torch.h>

#include <array>
#include <cassert>
#include <cmath>
#include <iostream>
#include <utility>
#include <vector>

using namespace kdm6;
using namespace kdm6::progb;

#define TEST(name) std::cout << "  RUN  " << #name << "\n"; do
#define END_TEST() while(false); std::cout << "  PASS\n"

namespace {

// AVTG/BVTG node values mirrored from progb.cpp (검증 reference)
constexpr std::array<double, 9> DENSITY_NODES = {
    100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0
};
constexpr std::array<double, 9> AVTG_NODES = {
    54.9153, 74.2262, 88.8313, 101.0411, 111.7359, 121.3625, 130.1841, 138.3714, 146.0422
};
constexpr std::array<double, 9> BVTG_NODES = {
    0.5446, 0.5375, 0.5339, 0.5316, 0.5299, 0.5286, 0.5275, 0.5266, 0.5258
};

std::pair<torch::Tensor, torch::Tensor> active_inputs(bool requires_grad) {
    auto opts = torch::TensorOptions().dtype(torch::kFloat64).requires_grad(requires_grad);
    auto qg = torch::tensor({{3.0e-4, 5.0e-4}}, opts);
    auto bg = torch::tensor({{1.0e-6, 1.0e-6}}, opts);
    return {qg, bg};
}

std::vector<std::pair<const char*, double>> param_fields(const ProgBParams& p) {
    return {
        {"qcrmin",     p.qcrmin},
        {"dmg",        p.dmg},
        {"mug",        p.mug},
        {"n0g",        p.n0g},
        {"g1pdgmg",    p.g1pdgmg},
        {"g1pmg",      p.g1pmg},
        {"rslopegmax", p.rslopegmax},
    };
}

std::vector<torch::Tensor> output_tensors(const ProgBOutputs& out) {
    return {
        out.rhox, out.bg, out.cmg, out.pidn0g,
        out.avtg, out.bvtg,
        out.bvtg1, out.bvtg2, out.bvtg3, out.bvtg4,
        out.g1pbg, out.g3pbg, out.g4pbg, out.g5pbgo2, out.g1pdgbgmg,
        out.dgbgmug1, out.rslopegbmax, out.pvtg, out.precg2,
    };
}

}  // namespace

void test_default_progb_params_finite_and_nonnegative() {
    TEST(test_default_progb_params_finite_and_nonnegative) {
        auto p = default_progb_params();
        for (const auto& f : param_fields(p)) {
            assert(std::isfinite(f.second));
            assert(f.second >= 0.0);
        }
        // 엄격한 양수 (mug는 0 허용)
        assert(p.qcrmin > 0.0);
        assert(p.dmg > 0.0);
        assert(p.n0g > 0.0);
        assert(p.g1pdgmg > 0.0);
        assert(p.g1pmg > 0.0);
        assert(p.rslopegmax > 0.0);
    } END_TEST();
}

void test_default_progb_params_g1pmg_mug_zero() {
    TEST(test_default_progb_params_g1pmg_mug_zero) {
        auto p = default_progb_params();
        if (p.mug == 0.0) {
            assert(p.g1pmg == 1.0);
        }
    } END_TEST();
}

void test_progb_inactive_branches_to_zero() {
    TEST(test_progb_inactive_branches_to_zero) {
        auto p = default_progb_params();
        auto opts = torch::TensorOptions().dtype(torch::kFloat64);
        auto qg = torch::zeros({1, 4}, opts);
        auto bg = torch::zeros({1, 4}, opts);
        auto out = progb_param_torch(qg, bg, p);
        auto zero = torch::zeros({1, 4}, opts);

        assert(torch::allclose(out.cmg, zero));
        assert(torch::allclose(out.pidn0g, zero));
        assert(torch::allclose(out.avtg, zero));
        assert(torch::allclose(out.bvtg, zero));
        assert(torch::allclose(out.pvtg, zero));
        assert(torch::allclose(out.precg2, zero));
        assert(torch::allclose(out.rslopegbmax, zero));
        assert(torch::allclose(out.g1pbg, zero));

        // rhox는 RHO_MID, bg는 입력 보존
        assert(torch::allclose(out.rhox, torch::full_like(qg, RHO_MID)));
        assert(torch::allclose(out.bg, bg));
    } END_TEST();
}

void test_progb_density_clamp_low() {
    TEST(test_progb_density_clamp_low) {
        auto p = default_progb_params();
        auto opts = torch::TensorOptions().dtype(torch::kFloat64);
        // rhox_raw = 5e-4 / 1e-5 = 50 (< RHO_MIN). clamp 결과 100.
        auto qg = torch::tensor({{5.0e-4}}, opts);
        auto bg = torch::tensor({{1.0e-5}}, opts);
        auto out = progb_param_torch(qg, bg, p);
        assert(torch::allclose(out.rhox, torch::full_like(qg, RHO_MIN)));
    } END_TEST();
}

void test_progb_density_clamp_high() {
    TEST(test_progb_density_clamp_high) {
        auto p = default_progb_params();
        auto opts = torch::TensorOptions().dtype(torch::kFloat64);
        // rhox_raw = 1e-3 / 1e-6 = 1000 (> RHO_MAX). clamp 결과 900.
        auto qg = torch::tensor({{1.0e-3}}, opts);
        auto bg = torch::tensor({{1.0e-6}}, opts);
        auto out = progb_param_torch(qg, bg, p);
        assert(torch::allclose(out.rhox, torch::full_like(qg, RHO_MAX)));
        // rhox==RHO_MAX일 때 table interp endpoint
        assert(torch::allclose(out.avtg, torch::full_like(qg, AVTG_NODES[8])));
        assert(torch::allclose(out.bvtg, torch::full_like(qg, BVTG_NODES[8])));
    } END_TEST();
}

void test_progb_table_interp_at_node_points() {
    TEST(test_progb_table_interp_at_node_points) {
        auto p = default_progb_params();
        auto opts = torch::TensorOptions().dtype(torch::kFloat64);
        for (int i = 0; i < 9; ++i) {
            const double rho_node = DENSITY_NODES[i];
            auto qg = torch::tensor({{rho_node * 1.0e-6}}, opts);
            auto bg = torch::tensor({{1.0e-6}}, opts);
            auto out = progb_param_torch(qg, bg, p);
            assert(torch::allclose(out.rhox, torch::full_like(qg, rho_node)));
            assert(torch::allclose(out.avtg, torch::full_like(qg, AVTG_NODES[i])));
            assert(torch::allclose(out.bvtg, torch::full_like(qg, BVTG_NODES[i])));
        }
    } END_TEST();
}

void test_progb_table_interp_midpoint() {
    TEST(test_progb_table_interp_midpoint) {
        auto p = default_progb_params();
        auto opts = torch::TensorOptions().dtype(torch::kFloat64);
        // rhox=250 — Tbl[1]=200과 Tbl[2]=300의 중점
        auto qg = torch::tensor({{2.5e-4}}, opts);
        auto bg = torch::tensor({{1.0e-6}}, opts);
        auto out = progb_param_torch(qg, bg, p);

        const double expected_a = 0.5 * (AVTG_NODES[1] + AVTG_NODES[2]);
        const double expected_b = 0.5 * (BVTG_NODES[1] + BVTG_NODES[2]);
        assert(torch::allclose(out.rhox, torch::full_like(qg, 250.0)));
        assert(torch::allclose(out.avtg, torch::full_like(qg, expected_a)));
        assert(torch::allclose(out.bvtg, torch::full_like(qg, expected_b)));
    } END_TEST();
}

void test_progb_grad_finite_active_cells() {
    TEST(test_progb_grad_finite_active_cells) {
        auto p = default_progb_params();
        auto [qg, bg] = active_inputs(/*requires_grad=*/true);

        auto out = progb_param_torch(qg, bg, p);
        for (const auto& t : output_tensors(out)) {
            assert(torch::isfinite(t).all().item<bool>());
        }

        auto loss = torch::zeros({}, torch::kFloat64);
        for (const auto& t : output_tensors(out)) {
            loss = loss + t.sum();
        }
        loss.backward();

        assert(qg.grad().defined());
        assert(bg.grad().defined());
        assert(torch::isfinite(qg.grad()).all().item<bool>());
        assert(torch::isfinite(bg.grad()).all().item<bool>());
    } END_TEST();
}

void test_progb_grad_finite_inactive_cells() {
    TEST(test_progb_grad_finite_inactive_cells) {
        auto p = default_progb_params();
        auto opts = torch::TensorOptions().dtype(torch::kFloat64).requires_grad(true);
        auto qg = torch::zeros({1, 3}, opts);
        auto bg = torch::zeros({1, 3}, opts);

        auto out = progb_param_torch(qg, bg, p);
        auto loss = torch::zeros({}, torch::kFloat64);
        for (const auto& t : output_tensors(out)) {
            loss = loss + t.sum();
        }
        loss.backward();

        assert(qg.grad().defined() && torch::isfinite(qg.grad()).all().item<bool>());
        assert(bg.grad().defined() && torch::isfinite(bg.grad()).all().item<bool>());
    } END_TEST();
}

void test_progb_bg_consistency_after_update() {
    TEST(test_progb_bg_consistency_after_update) {
        auto p = default_progb_params();
        auto [qg, bg] = active_inputs(/*requires_grad=*/false);
        auto out = progb_param_torch(qg, bg, p);
        auto expected_bg = qg / out.rhox;
        assert(torch::allclose(out.bg, expected_bg, 1e-12, 1e-15));
    } END_TEST();
}

// review7#5 parallel regression: anchor the tensor rgmma against Γ-truth.
// Mirrors Python `test_progb_rgmma_tensor_returns_gamma`. If the C++ rgmma sign
// ever drifts back to 1/Γ, this test fails immediately.
void test_progb_rgmma_tensor_returns_gamma() {
    TEST(test_progb_rgmma_tensor_returns_gamma) {
        auto x = torch::tensor({1.0, 2.0, 3.0, 4.0, 5.0}, torch::dtype(torch::kFloat64));
        auto out = rgmma_tensor(x);
        // Γ(1)=1, Γ(2)=1, Γ(3)=2, Γ(4)=6, Γ(5)=24
        auto expected = torch::tensor({1.0, 1.0, 2.0, 6.0, 24.0}, torch::dtype(torch::kFloat64));
        // lgamma+exp roundtrip noise 허용 (rel_tol ~ 1e-12).
        assert(torch::allclose(out, expected, /*rtol=*/1e-12, /*atol=*/0.0));
    } END_TEST();
}

int main() {
    std::cout << "KDM6AD-k libtorch progb tests\n";
    test_default_progb_params_finite_and_nonnegative();
    test_default_progb_params_g1pmg_mug_zero();
    test_progb_inactive_branches_to_zero();
    test_progb_density_clamp_low();
    test_progb_density_clamp_high();
    test_progb_table_interp_at_node_points();
    test_progb_table_interp_midpoint();
    test_progb_grad_finite_active_cells();
    test_progb_grad_finite_inactive_cells();
    test_progb_bg_consistency_after_update();
    test_progb_rgmma_tensor_returns_gamma();
    std::cout << "All progb tests passed.\n";
    return 0;
}
