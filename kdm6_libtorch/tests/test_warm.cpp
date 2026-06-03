#include "kdm6/warm.h"

#include <torch/torch.h>

#include <cassert>
#include <cmath>
#include <iostream>

using namespace kdm6;
using namespace kdm6::warm;

#define TEST(name) std::cout << "  RUN  " << #name << "\n"; do
#define END_TEST() while(false); std::cout << "  PASS\n"

namespace {

torch::TensorOptions f64() {
    return torch::TensorOptions().dtype(torch::kFloat64);
}

torch::TensorOptions f64_grad(bool grad) {
    return f64().requires_grad(grad);
}

}  // namespace

// ═══════════════════════════════════════════════════════════════════════════
// B1 Autoconv
// ═══════════════════════════════════════════════════════════════════════════

void test_autoconv_params_finite() {
    TEST(test_autoconv_params_finite) {
        auto p = default_warm_autoconv_params();
        assert(std::isfinite(p.qck1) && p.qck1 > 0);
        assert(std::isfinite(p.nraut_coeff) && p.nraut_coeff > 0);
        assert(std::isfinite(p.qcrmin) && p.qcrmin > 0);
        assert(std::isfinite(p.ncmin) && p.ncmin > 0);
    } END_TEST();
}

void test_autoconv_inactive_below_qcr() {
    TEST(test_autoconv_inactive_below_qcr) {
        auto p = default_warm_autoconv_params();
        auto qc = torch::full({1, 3}, 1.0e-7, f64());
        auto nc = torch::full({1, 3}, 1.0e8, f64());
        auto qr = torch::zeros({1, 3}, f64());
        auto nr = torch::zeros({1, 3}, f64());
        auto den = torch::full({1, 3}, 1.1, f64());
        auto qcr = torch::full({1, 3}, 1.0e-4, f64());  // larger threshold
        auto lenconcr = torch::full({1, 3}, 1.0e-9, f64());

        auto out = autoconv_torch(qc, nc, qr, nr, den, qcr, lenconcr, p, 60.0);
        assert(torch::allclose(out.praut, torch::zeros_like(qc)));
        assert(torch::allclose(out.nraut, torch::zeros_like(qc)));
    } END_TEST();
}

void test_autoconv_grad_finite() {
    TEST(test_autoconv_grad_finite) {
        auto p = default_warm_autoconv_params();
        auto qc = torch::tensor({{3.0e-4, 5.0e-4}}, f64_grad(true));
        auto nc = torch::tensor({{1.0e8, 2.0e8}}, f64_grad(true));
        auto qr = torch::tensor({{1.0e-5, 5.0e-5}}, f64_grad(true));
        auto nr = torch::tensor({{1.0e5, 5.0e5}}, f64_grad(true));
        auto den = torch::full({1, 2}, 1.1, f64());
        auto qcr = torch::full({1, 2}, 1.0e-7, f64());
        auto lenconcr = torch::full({1, 2}, 1.0e-6, f64());

        auto out = autoconv_torch(qc, nc, qr, nr, den, qcr, lenconcr, p, 60.0);
        auto loss = out.praut.sum() + out.nraut.sum();
        loss.backward();

        assert(qc.grad().defined() && torch::isfinite(qc.grad()).all().item<bool>());
        assert(nc.grad().defined() && torch::isfinite(nc.grad()).all().item<bool>());
        assert(nr.grad().defined() && torch::isfinite(nr.grad()).all().item<bool>());
    } END_TEST();
}

// ═══════════════════════════════════════════════════════════════════════════
// B2 Accretion
// ═══════════════════════════════════════════════════════════════════════════

void test_accretion_params_gamma() {
    TEST(test_accretion_params_gamma) {
        auto p = default_warm_accretion_params();
        // review6 audit fix: rgmma = Γ(x).
        // muc=2 ⇒ Γ(2)=1, Γ(3)=2, Γ(4)=6
        assert(std::abs(p.g3pmc - 1.0) < 1e-12);
        assert(std::abs(p.g6pmc - 2.0) < 1e-12);
        assert(std::abs(p.g9pmc - 6.0) < 1e-12);
        // mur=1 ⇒ Γ(2)=1, Γ(5)=24, Γ(8)=5040 (큰 값에서 lgamma+exp roundtrip 노이즈 허용).
        assert(std::abs(p.g1pmr - 1.0) < 1e-12);
        assert(std::abs(p.g4pmr - 24.0) < 1e-10);
        assert(std::abs(p.g7pmr - 5040.0) / 5040.0 < 1e-12);
    } END_TEST();
}

void test_accretion_inactive_below_lenconcr() {
    TEST(test_accretion_inactive_below_lenconcr) {
        auto p = default_warm_accretion_params();
        auto qc = torch::full({1, 2}, 1.0e-3, f64());
        auto nc = torch::full({1, 2}, 1.0e8, f64());
        auto qr = torch::full({1, 2}, 1.0e-9, f64());  // below lenconcr
        auto nr = torch::full({1, 2}, 1.0e5, f64());
        auto den = torch::full({1, 2}, 1.1, f64());
        auto avedia_r = torch::full({1, 2}, 2.0e-4, f64());
        auto rslopec3 = torch::full({1, 2}, std::pow(5.0e-5, 3), f64());
        auto rslope3_r = torch::full({1, 2}, std::pow(5.0e-4, 3), f64());
        auto lenconcr = torch::full({1, 2}, 1.0e-7, f64());

        auto out = accretion_torch(qc, nc, qr, nr, den, avedia_r, rslopec3, rslope3_r,
                                    lenconcr, p, 60.0);
        assert(torch::allclose(out.pracw, torch::zeros_like(qc)));
        assert(torch::allclose(out.nracw, torch::zeros_like(qc)));
    } END_TEST();
}

// ═══════════════════════════════════════════════════════════════════════════
// B3 Self-collection
// ═══════════════════════════════════════════════════════════════════════════

void test_self_collection_params_thresholds() {
    TEST(test_self_collection_params_thresholds) {
        auto p = default_warm_self_collection_params();
        assert(p.di100 < p.di600);
        assert(p.di600 < p.di2000);
    } END_TEST();
}

void test_self_collection_nrcol_zero_at_huge_drops() {
    TEST(test_self_collection_nrcol_zero_at_huge_drops) {
        auto p = default_warm_self_collection_params();
        auto nc = torch::full({1, 2}, 1.0e8, f64());
        auto nr = torch::full({1, 2}, 1.0e5, f64());
        auto qr = torch::full({1, 2}, 1.0e-4, f64());
        auto avedia_c = torch::full({1, 2}, 5.0e-5, f64());
        auto avedia_r = torch::full({1, 2}, p.di2000 + 1.0e-5, f64());  // > di2000
        auto rslopec3 = torch::full({1, 2}, std::pow(5.0e-5, 3), f64());
        auto rslope3_r = torch::full({1, 2}, std::pow(5.0e-4, 3), f64());
        auto lenconcr = torch::full({1, 2}, 1.0e-7, f64());

        auto out = self_collection_torch(nc, nr, qr, avedia_c, avedia_r,
                                          rslopec3, rslope3_r, lenconcr, p);
        assert(torch::allclose(out.nrcol, torch::zeros_like(nc)));
    } END_TEST();
}

// ═══════════════════════════════════════════════════════════════════════════
// B4 Rain evap
// ═══════════════════════════════════════════════════════════════════════════

void test_rain_evap_params_precr1() {
    TEST(test_rain_evap_params_precr1) {
        auto p = default_warm_rain_evap_params();
        // mur=1 ⇒ g2pmr = rgmma(3) = Γ(3) = 2 (review6 audit fix).
        const double expected = 2.0 * 3.14159265358979323846 * 0.78 * 2.0;
        assert(std::abs(p.precr1 - expected) < 1e-10);
    } END_TEST();
}

void test_rain_evap_inactive_when_qr_zero() {
    TEST(test_rain_evap_inactive_when_qr_zero) {
        auto p = default_warm_rain_evap_params();
        auto qr = torch::zeros({1, 2}, f64());
        auto rh_w = torch::full({1, 2}, 0.5, f64());
        auto supsat = torch::full({1, 2}, -1.0e-3, f64());
        auto n0r = torch::full({1, 2}, 8.0e6, f64());
        auto work1_r = torch::full({1, 2}, 1.0e-3, f64());
        auto work2 = torch::full({1, 2}, 1.5, f64());
        auto rslope_r = torch::full({1, 2}, 5.0e-4, f64());
        auto rslopeb_r = torch::full({1, 2}, std::pow(5.0e-4, constants::BVTR), f64());
        auto rslope2_r = rslope_r * rslope_r;
        auto rslopemu_r = torch::full({1, 2}, std::pow(5.0e-4, constants::MUR), f64());

        auto prevp = rain_evap_torch(qr, rh_w, supsat, n0r, work1_r, work2,
                                      rslope_r, rslopeb_r, rslope2_r, rslopemu_r, p, 60.0).prevp;
        assert(torch::allclose(prevp, torch::zeros_like(qr)));
    } END_TEST();
}

void test_rain_evap_evaporation_path() {
    TEST(test_rain_evap_evaporation_path) {
        auto p = default_warm_rain_evap_params();
        auto qr = torch::tensor({{1.0e-4, 5.0e-5}}, f64());
        auto rh_w = torch::full({1, 2}, 0.5, f64());
        auto supsat = torch::full({1, 2}, -2.5e-3, f64());
        auto n0r = torch::full({1, 2}, 8.0e6, f64());
        auto work1_r = torch::full({1, 2}, 1.0e-3, f64());
        auto work2 = torch::full({1, 2}, 1.5, f64());
        auto rslope_r = torch::full({1, 2}, 5.0e-4, f64());
        auto rslopeb_r = torch::full({1, 2}, std::pow(5.0e-4, constants::BVTR), f64());
        auto rslope2_r = rslope_r * rslope_r;
        auto rslopemu_r = torch::full({1, 2}, std::pow(5.0e-4, constants::MUR), f64());

        auto prevp = rain_evap_torch(qr, rh_w, supsat, n0r, work1_r, work2,
                                      rslope_r, rslopeb_r, rslope2_r, rslopemu_r, p, 60.0).prevp;
        // prevp <= 0 (evap)
        assert(torch::all(prevp <= 1e-15).item<bool>());
        // prevp >= -qr/dtcld (mass cap)
        assert(torch::all(prevp >= -qr / 60.0 - 1e-15).item<bool>());
    } END_TEST();
}

int main() {
    std::cout << "kdm6_libtorch warm tests\n";
    test_autoconv_params_finite();
    test_autoconv_inactive_below_qcr();
    test_autoconv_grad_finite();
    test_accretion_params_gamma();
    test_accretion_inactive_below_lenconcr();
    test_self_collection_params_thresholds();
    test_self_collection_nrcol_zero_at_huge_drops();
    test_rain_evap_params_precr1();
    test_rain_evap_inactive_when_qr_zero();
    test_rain_evap_evaporation_path();
    std::cout << "All warm tests passed.\n";
    return 0;
}
