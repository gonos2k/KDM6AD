#include "kdm6/satadj.h"

#include <torch/torch.h>

#include <cassert>
#include <iostream>

using namespace kdm6;
using namespace kdm6::satadj;

#define TEST(name) std::cout << "  RUN  " << #name << "\n"; do
#define END_TEST() while(false); std::cout << "  PASS\n"

namespace {

torch::TensorOptions f64() {
    return torch::TensorOptions().dtype(torch::kFloat64);
}

struct Inputs {
    torch::Tensor t, q, qc, qs1, xl, cpm;
};

Inputs base_inputs(double rh_value, double qc_value, bool grad = false) {
    auto opts = grad ? f64().requires_grad(true) : f64();
    constexpr double qs1_val = 1.0e-2;
    return Inputs{
        torch::full({1, 2}, 290.0, f64()),
        torch::full({1, 2}, qs1_val * rh_value, opts),
        torch::full({1, 2}, qc_value, opts),
        torch::full({1, 2}, qs1_val, f64()),
        torch::full({1, 2}, 2.5e6, f64()),
        torch::full({1, 2}, 1004.0, f64()),
    };
}

}  // namespace

void test_satadj_zero_when_balanced_and_no_cloud() {
    TEST(test_satadj_zero_when_balanced_and_no_cloud) {
        auto p = default_satadj_params();
        auto in = base_inputs(/*rh=*/1.0, /*qc=*/0.0);
        auto pcond = saturation_adjustment_torch(in.t, in.q, in.qc, in.qs1, in.xl, in.cpm, p, 60.0).pcond;
        assert(torch::allclose(pcond, torch::zeros_like(pcond), 1e-12, 1e-15));
    } END_TEST();
}

void test_satadj_condensation_path() {
    TEST(test_satadj_condensation_path) {
        auto p = default_satadj_params();
        auto in = base_inputs(/*rh=*/1.05, /*qc=*/0.0);
        auto pcond = saturation_adjustment_torch(in.t, in.q, in.qc, in.qs1, in.xl, in.cpm, p, 60.0).pcond;
        assert(torch::all(pcond > 0).item<bool>());
        assert(torch::all(pcond <= in.q / 60.0 + 1e-15).item<bool>());
    } END_TEST();
}

void test_satadj_evaporation_path() {
    TEST(test_satadj_evaporation_path) {
        auto p = default_satadj_params();
        auto in = base_inputs(/*rh=*/0.95, /*qc=*/1.0e-4);
        auto pcond = saturation_adjustment_torch(in.t, in.q, in.qc, in.qs1, in.xl, in.cpm, p, 60.0).pcond;
        assert(torch::all(pcond < 0).item<bool>());
        assert(torch::all(pcond >= -in.qc / 60.0 - 1e-15).item<bool>());
    } END_TEST();
}

void test_satadj_no_evap_without_cloud() {
    TEST(test_satadj_no_evap_without_cloud) {
        auto p = default_satadj_params();
        auto in = base_inputs(/*rh=*/0.7, /*qc=*/0.0);
        auto pcond = saturation_adjustment_torch(in.t, in.q, in.qc, in.qs1, in.xl, in.cpm, p, 60.0).pcond;
        assert(torch::allclose(pcond, torch::zeros_like(pcond)));
    } END_TEST();
}

void test_satadj_grad_finite() {
    TEST(test_satadj_grad_finite) {
        auto p = default_satadj_params();
        auto in = base_inputs(/*rh=*/1.05, /*qc=*/1.0e-4, /*grad=*/true);
        auto pcond = saturation_adjustment_torch(in.t, in.q, in.qc, in.qs1, in.xl, in.cpm, p, 60.0).pcond;
        pcond.sum().backward();
        assert(in.q.grad().defined() && torch::isfinite(in.q.grad()).all().item<bool>());
        assert(in.qc.grad().defined() && torch::isfinite(in.qc.grad()).all().item<bool>());
    } END_TEST();
}

int main() {
    std::cout << "kdm6_libtorch satadj tests\n";
    test_satadj_zero_when_balanced_and_no_cloud();
    test_satadj_condensation_path();
    test_satadj_evaporation_path();
    test_satadj_no_evap_without_cloud();
    test_satadj_grad_finite();
    std::cout << "All satadj tests passed.\n";
    return 0;
}
