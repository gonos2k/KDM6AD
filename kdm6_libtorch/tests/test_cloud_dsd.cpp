// Plain-assert tests for kdm6/cloud_dsd.
// Mirror Python kdm6_torch/tests/test_cloud_dsd.py — anchors Γ-truth on params.
//
#include "kdm6/cloud_dsd.h"
#include "kdm6/constants.h"

#include <torch/torch.h>
#include <cassert>
#include <cmath>
#include <iostream>

using namespace kdm6;
using namespace kdm6::cloud_dsd;

#define TEST(name) std::cout << "  RUN  " << #name << "\n"; do
#define END_TEST() while(false); std::cout << "  PASS\n"

namespace {
torch::TensorOptions f64() { return torch::dtype(torch::kFloat64); }
}

void test_default_params_finite_and_positive() {
    TEST(test_default_params_finite_and_positive) {
        auto p = default_cloud_dsd_params();
        assert(std::isfinite(p.pidnc) && p.pidnc > 0);
        assert(std::isfinite(p.g3pmc) && p.g3pmc > 0);
        assert(std::isfinite(p.g6pmc) && p.g6pmc > 0);
        assert(std::isfinite(p.g4pmr_over_g1pmr) && p.g4pmr_over_g1pmr > 0);
        assert(std::isfinite(p.qc0) && p.qc0 > 0);
        assert(std::isfinite(p.qc1) && p.qc1 > p.qc0);
    } END_TEST();
}

void test_g3pmc_g6pmc_gamma_truth() {
    // MUC=2 → g3pmc = Γ(2) = 1, g6pmc = Γ(3) = 2 (review6 audit fix anchor).
    // Mirrors Python `test_g3pmc_g6pmc_hardcoded`.
    TEST(test_g3pmc_g6pmc_gamma_truth) {
        auto p = default_cloud_dsd_params();
        assert(constants::MUC == 2.0);
        assert(std::abs(p.g3pmc - 1.0) < 1e-12);
        assert(std::abs(p.g6pmc - 2.0) < 1e-12);
        // var_factor positive (precludes reciprocal-gamma bug).
        assert(p.g6pmc - p.g3pmc * p.g3pmc > 0);
    } END_TEST();
}

void test_g4pmr_over_g1pmr_is_24() {
    // MUR=1 → Γ(5)/Γ(2) = 24/1 = 24.
    TEST(test_g4pmr_over_g1pmr_is_24) {
        auto p = default_cloud_dsd_params();
        assert(constants::MUR == 1.0);
        assert(std::abs(p.g4pmr_over_g1pmr - 24.0) < 1e-12);
    } END_TEST();
}

void test_avedia_rain_hardcoded() {
    // avedia_r = rslope_r · (g4pmr/g1pmr)^0.3333333 — Fortran F:1671 truncated literal. 1:1 fix #4.
    TEST(test_avedia_rain_hardcoded) {
        auto p = default_cloud_dsd_params();
        auto rslope_r = torch::tensor({{1.0e-4, 5.0e-4}}, f64());
        auto out = diag_avedia_rain_torch(rslope_r, p);
        auto expected = rslope_r * std::pow(p.g4pmr_over_g1pmr, 0.3333333);
        assert(torch::allclose(out, expected, /*rtol=*/1e-12, /*atol=*/0.0));
    } END_TEST();
}

void test_diag_qcr_sea_land_branch() {
    TEST(test_diag_qcr_sea_land_branch) {
        auto p = default_cloud_dsd_params();
        auto sea_mask = torch::tensor({{true, false, true}});
        auto ref = torch::full({1, 3}, 1.0, f64());
        auto qcr = diag_qcr_torch(sea_mask, p, ref);
        // Mirrors Fortran module_mp_kdm6.F:826-830: sea(slmsk==2) → qc0
        // (low-CCN/low-threshold), land → qc1 (high-CCN/high-threshold).
        // qc0/qc1 field names are scalar labels, not regime labels; the
        // regime wiring is in src/cloud_dsd.cpp diag_qcr_torch.
        assert(std::abs(qcr[0][0].item<double>() - p.qc0) < 1e-12);
        assert(std::abs(qcr[0][1].item<double>() - p.qc1) < 1e-12);
        assert(std::abs(qcr[0][2].item<double>() - p.qc0) < 1e-12);
    } END_TEST();
}

void test_diag_cloud_slope_clamp() {
    TEST(test_diag_cloud_slope_clamp) {
        auto p = default_cloud_dsd_params();
        // STEP-75 D-B semantics: the ACTIVE slope is UNCLAMPED (Fortran stmt fn
        // lamdac F:802 has no bounds) — tiny qc with qc>qmin gives rslopec BELOW
        // 1/lamdacmax; only the INACTIVE gate (qc<=qmin | nc<=ncmin) forces
        // rslopec = 1/lamdacmax.
        auto qc = torch::full({1, 1}, 1.0e-12, f64());
        auto nc = torch::full({1, 1}, 1.0e8, f64());
        auto den = torch::full({1, 1}, 1.1, f64());
        auto rslope = diag_cloud_slope_torch(qc, nc, den, p);
        assert(rslope.item<double>() > 0.0);
        assert(rslope.item<double>() < 1.0 / p.lamdacmax);  // active, unclamped (below the old floor)
        // inactive gates -> 1/lamdacmax exactly
        auto qc0 = torch::full({1, 1}, 0.0, f64());
        auto r_inact = diag_cloud_slope_torch(qc0, nc, den, p);
        assert(std::abs(r_inact.item<double>() - 1.0 / p.lamdacmax) < 1e-18);
        auto nc0 = torch::full({1, 1}, 0.0, f64());
        auto r_inact2 = diag_cloud_slope_torch(qc, nc0, den, p);
        assert(std::abs(r_inact2.item<double>() - 1.0 / p.lamdacmax) < 1e-18);
    } END_TEST();
}

void test_diag_lencon_floors_at_qcrmin() {
    TEST(test_diag_lencon_floors_at_qcrmin) {
        auto qc = torch::full({1, 2}, 1.0e-9, f64());  // very low qc → lencon ≈ 0
        auto den = torch::full({1, 2}, 1.1, f64());
        auto avedia_c = torch::full({1, 2}, 5.0e-5, f64());
        auto sigma_c = torch::full({1, 2}, 2.0e-5, f64());
        auto out = diag_lencon_torch(qc, den, avedia_c, sigma_c);
        assert(torch::all(out.lenconcr >= constants::QCRMIN - 1e-30).item<bool>());
    } END_TEST();
}

void test_diag_avedia_grad_propagates() {
    TEST(test_diag_avedia_grad_propagates) {
        auto p = default_cloud_dsd_params();
        auto opts = f64().requires_grad(true);
        auto rslope = torch::full({1, 1}, 5.0e-4, opts);
        auto avedia = diag_avedia_rain_torch(rslope, p);
        avedia.sum().backward();
        assert(rslope.grad().defined() && torch::isfinite(rslope.grad()).all().item<bool>());
    } END_TEST();
}

int main() {
    std::cout << "kdm6_libtorch cloud_dsd tests\n";
    test_default_params_finite_and_positive();
    test_g3pmc_g6pmc_gamma_truth();
    test_g4pmr_over_g1pmr_is_24();
    test_avedia_rain_hardcoded();
    test_diag_qcr_sea_land_branch();
    test_diag_cloud_slope_clamp();
    test_diag_lencon_floors_at_qcrmin();
    test_diag_avedia_grad_propagates();
    std::cout << "All cloud_dsd tests passed.\n";
    return 0;
}
