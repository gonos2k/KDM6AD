#include "kdm6/thermo.h"

#include <torch/torch.h>

#include <cassert>
#include <cmath>
#include <iostream>

using namespace kdm6::thermo;

#define TEST(name) std::cout << "  RUN  " << #name << "\n"; do
#define END_TEST() while(false); std::cout << "  PASS\n"

namespace {
torch::TensorOptions f64() { return torch::TensorOptions().dtype(torch::kFloat64); }
}

void test_thermo_params_finite() {
    TEST(test_thermo_params_finite) {
        auto p = default_thermo_params();
        assert(std::isfinite(p.xa) && std::isfinite(p.xb));
        assert(std::isfinite(p.xai) && std::isfinite(p.xbi));
    } END_TEST();
}

void test_xl_at_freezing() {
    TEST(test_xl_at_freezing) {
        auto p = default_thermo_params();
        auto t = torch::full({1}, p.t0c, f64());
        auto xl = compute_xl(t, p);
        assert(torch::isclose(xl, torch::tensor(p.xlv0, f64()))
                .item<bool>());
    } END_TEST();
}

void test_qs_water_at_ttp() {
    TEST(test_qs_water_at_ttp) {
        auto p = default_thermo_params();
        auto t = torch::full({1}, p.ttp, f64());
        auto pres = torch::full({1}, 1.0e5, f64());
        auto qs = compute_qs_water(t, pres, p);
        const double expected = p.ep2 * p.psat / (1.0e5 - p.psat);
        assert(std::abs(qs.item<double>() - expected) < 1e-10);
    } END_TEST();
}

void test_denfac_at_reference() {
    TEST(test_denfac_at_reference) {
        auto p = default_thermo_params();
        auto den = torch::full({1}, p.den0, f64());
        auto df = compute_denfac(den, p);
        assert(std::abs(df.item<double>() - 1.0) < 1e-12);
    } END_TEST();
}

void test_thermo_grad_finite() {
    TEST(test_thermo_grad_finite) {
        auto p = default_thermo_params();
        auto opts = f64().requires_grad(true);
        auto t = torch::full({1}, 280.0, opts);
        auto q = torch::full({1}, 5.0e-3, opts);
        auto pres = torch::full({1}, 1.0e5, opts);
        auto den = torch::full({1}, 1.1, opts);

        auto qs1 = compute_qs_water(t, pres, p);
        auto rh = compute_rh(q, qs1, p);
        auto cpm = compute_cpm(q, p);
        auto xl = compute_xl(t, p);
        auto df = compute_denfac(den, p);
        auto w2 = compute_work2_venfac(pres, t, den, p);

        auto loss = qs1.sum() + rh.sum() + cpm.sum() + xl.sum() + df.sum() + w2.sum();
        loss.backward();
        assert(t.grad().defined() && torch::isfinite(t.grad()).all().item<bool>());
        assert(q.grad().defined() && torch::isfinite(q.grad()).all().item<bool>());
        assert(pres.grad().defined() && torch::isfinite(pres.grad()).all().item<bool>());
        assert(den.grad().defined() && torch::isfinite(den.grad()).all().item<bool>());
    } END_TEST();
}

int main() {
    std::cout << "KDM6AD-k libtorch thermo tests\n";
    test_thermo_params_finite();
    test_xl_at_freezing();
    test_qs_water_at_ttp();
    test_denfac_at_reference();
    test_thermo_grad_finite();
    std::cout << "All thermo tests passed.\n";
    return 0;
}
