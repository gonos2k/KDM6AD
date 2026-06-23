#include "kdm6/melt_freeze.h"

#include <torch/torch.h>

#include <cassert>
#include <cmath>
#include <iostream>

using namespace kdm6;
using namespace kdm6::melt;

#define TEST(name) std::cout << "  RUN  " << #name << "\n"; do
#define END_TEST() while(false); std::cout << "  PASS\n"

namespace {

torch::TensorOptions f64() { return torch::TensorOptions().dtype(torch::kFloat64); }

MeltingInputs make_melt_inputs(double t_value, bool grad = false) {
    auto opts = grad ? f64().requires_grad(true) : f64();
    auto plain = f64();
    auto qs = torch::full({1, 2}, 1.0e-4, opts);
    auto qg = torch::full({1, 2}, 1.0e-4, opts);
    auto qi = torch::full({1, 2}, 1.0e-5, opts);
    auto ni = torch::full({1, 2}, 1.0e5, opts);
    auto t = torch::full({1, 2}, t_value, plain);
    auto p = torch::full({1, 2}, 8.0e4, plain);
    auto den = torch::full({1, 2}, 1.1, plain);
    auto rhox = torch::full({1, 2}, 400.0, plain);
    auto cpm = torch::full({1, 2}, 1005.0, plain);
    auto n0so = torch::full({1, 2}, 2.0e6, plain);
    auto n0go = torch::full({1, 2}, 4.0e6, plain);
    auto n0sfac = torch::full({1, 2}, 1.0, plain);
    auto work2 = torch::full({1, 2}, 1.5, plain);
    auto precg2 = torch::full({1, 2}, 0.5, plain);
    auto rsl_s = torch::full({1, 2}, 5.0e-4, plain);
    auto rsl_g = torch::full({1, 2}, 1.0e-3, plain);
    return MeltingInputs{
        qs, qg, qi, ni, t, p, den, rhox, cpm, n0so, n0go, n0sfac, work2, precg2,
        rsl_s, rsl_s * rsl_s,
        torch::full({1, 2}, std::pow(5.0e-4, constants::BVTS), plain),
        torch::full({1, 2}, std::pow(5.0e-4, constants::MUS), plain),
        rsl_g, rsl_g * rsl_g,
        torch::full({1, 2}, std::pow(1.0e-3, 0.5316), plain),
        torch::full({1, 2}, std::pow(1.0e-3, constants::MUG), plain),
    };
}

}  // namespace

void test_melt_inactive_when_cold() {
    TEST(test_melt_inactive_when_cold) {
        auto p = default_melting_params();
        auto in = make_melt_inputs(/*t=*/270.0);
        auto out = melting_torch(in, p, 60.0);
        auto z = torch::zeros_like(in.qs);
        assert(torch::allclose(out.psmlt, z));
        assert(torch::allclose(out.pgmlt, z));
        assert(torch::allclose(out.pimlt_qi, z));
    } END_TEST();
}

void test_melt_warm_psmlt_negative() {
    TEST(test_melt_warm_psmlt_negative) {
        auto p = default_melting_params();
        auto in = make_melt_inputs(/*t=*/280.0);
        auto out = melting_torch(in, p, 60.0);
        assert(torch::all(out.psmlt <= 1e-15).item<bool>());
        assert(torch::all(out.pgmlt <= 1e-15).item<bool>());
    } END_TEST();
}

void test_melt_pimlt_full_transfer() {
    TEST(test_melt_pimlt_full_transfer) {
        auto p = default_melting_params();
        auto in = make_melt_inputs(/*t=*/280.0);
        auto out = melting_torch(in, p, 60.0);
        assert(torch::allclose(out.pimlt_qi, in.qi));
        assert(torch::allclose(out.pimlt_ni, in.ni));
    } END_TEST();
}

void test_melt_grad_finite() {
    TEST(test_melt_grad_finite) {
        auto p = default_melting_params();
        auto in = make_melt_inputs(/*t=*/280.0, /*grad=*/true);
        auto out = melting_torch(in, p, 60.0);
        auto loss = out.psmlt.sum() + out.pgmlt.sum() + out.pimlt_qi.sum();
        loss.backward();
        assert(in.qs.grad().defined() && torch::isfinite(in.qs.grad()).all().item<bool>());
        assert(in.qg.grad().defined() && torch::isfinite(in.qg.grad()).all().item<bool>());
        assert(in.qi.grad().defined() && torch::isfinite(in.qi.grad()).all().item<bool>());
    } END_TEST();
}

// ═══════════════════════════════════════════════════════════════════════════
// D2 / D3 / D4 / D5
// ═══════════════════════════════════════════════════════════════════════════

namespace {

ContactFreezingInputs make_contact_inputs(double supcol_value, bool grad = false, double qc_value = 1.0e-3) {
    auto opts = grad ? f64().requires_grad(true) : f64();
    auto plain = f64();
    auto qc = torch::full({1, 2}, qc_value, opts);
    auto nc = torch::full({1, 2}, 1.0e8, opts);
    auto t = torch::full({1, 2}, 263.15, plain);
    auto p = torch::full({1, 2}, 8.0e4, plain);
    auto den = torch::full({1, 2}, 1.1, plain);
    auto n0c = torch::full({1, 2}, 1.0e8, plain);
    auto rsl_c = torch::full({1, 2}, 5.0e-5, plain);
    auto rsl_c2 = rsl_c * rsl_c;
    auto rsl_c3 = rsl_c2 * rsl_c;
    auto rsl_cmu = torch::full({1, 2}, std::pow(5.0e-5, constants::MUC), plain);
    auto supcol = torch::full({1, 2}, supcol_value, plain);
    return ContactFreezingInputs{qc, nc, t, p, den, n0c, rsl_c, rsl_c2, rsl_c3, rsl_cmu, supcol};
}

}  // namespace

void test_contact_inactive_when_supcol_low() {
    TEST(test_contact_inactive_when_supcol_low) {
        auto p = default_contact_freezing_params();
        auto in = make_contact_inputs(/*supcol=*/1.0);
        auto out = contact_freezing_torch(in, p, 60.0);
        assert(torch::allclose(out.pinuc, torch::zeros_like(in.qc)));
    } END_TEST();
}

void test_contact_qc_gate_regression() {
    TEST(test_contact_qc_gate_regression) {
        auto p = default_contact_freezing_params();
        // qc below the EPS=1e-15 gate (#1) → pinuc = 0 (gate blocks; supcol=10 > 2).
        auto in_lo = make_contact_inputs(/*supcol=*/10.0, /*grad=*/false, /*qc=*/1.0e-16);
        auto out_lo = contact_freezing_torch(in_lo, p, 60.0);
        assert(torch::allclose(out_lo.pinuc, torch::zeros_like(in_lo.qc)));
        // Gate-regression LOCK: qc in (EPS=1e-15, old qcrmin=1e-9) → gate OPEN → pinuc > 0
        // (capped at qc). FAILS if the qmin gate regresses to 1e-9.
        auto in_band = make_contact_inputs(/*supcol=*/10.0, /*grad=*/false, /*qc=*/1.0e-12);
        auto out_band = contact_freezing_torch(in_band, p, 60.0);
        assert(torch::all(out_band.pinuc > 0.0).item<bool>());
    } END_TEST();
}

void test_bigg_cloud_qc_gate_regression() {
    TEST(test_bigg_cloud_qc_gate_regression) {
        auto p = default_bigg_cloud_params();
        auto plain = f64();
        auto nc = torch::full({1, 2}, 1.0e8, plain);
        auto den = torch::full({1, 2}, 1.1, plain);
        auto n0c = torch::full({1, 2}, 1.0e8, plain);
        auto rsl_c = torch::full({1, 2}, 5.0e-5, plain);
        auto rsl_cd = torch::full({1, 2}, std::pow(5.0e-5, constants::DMC), plain);
        auto rsl_cmu = torch::full({1, 2}, std::pow(5.0e-5, constants::MUC), plain);
        auto supcol = torch::full({1, 2}, 10.0, plain);
        auto mk = [&](double qc_value) {
            auto qc = torch::full({1, 2}, qc_value, plain);
            return bigg_cloud_freezing_torch(BiggCloudInputs{qc, nc, den, n0c, rsl_c, rsl_cd, rsl_cmu, supcol}, p, 60.0);
        };
        // qc below EPS=1e-15 gate (#1) → pfrzdtc = 0; qc in (1e-15,1e-9) → pfrzdtc > 0 (gate-regression LOCK).
        assert(torch::allclose(mk(1.0e-16).pfrzdtc, torch::zeros({1, 2}, plain)));
        assert(torch::all(mk(1.0e-12).pfrzdtc > 0.0).item<bool>());
    } END_TEST();
}

void test_contact_grad_finite() {
    TEST(test_contact_grad_finite) {
        auto p = default_contact_freezing_params();
        auto in = make_contact_inputs(/*supcol=*/10.0, /*grad=*/true);
        auto out = contact_freezing_torch(in, p, 60.0);
        auto loss = out.pinuc.sum() + out.ninuc.sum();
        loss.backward();
        assert(in.qc.grad().defined() && torch::isfinite(in.qc.grad()).all().item<bool>());
    } END_TEST();
}

void test_bigg_cloud_grad_finite() {
    TEST(test_bigg_cloud_grad_finite) {
        auto p = default_bigg_cloud_params();
        auto opts = f64().requires_grad(true);
        auto plain = f64();
        auto qc = torch::full({1, 2}, 1.0e-3, opts);
        auto nc = torch::full({1, 2}, 1.0e8, opts);
        auto den = torch::full({1, 2}, 1.1, plain);
        auto n0c = torch::full({1, 2}, 1.0e8, plain);
        auto rsl_c = torch::full({1, 2}, 5.0e-5, plain);
        auto rsl_cd = torch::full({1, 2}, std::pow(5.0e-5, constants::DMC), plain);
        auto rsl_cmu = torch::full({1, 2}, std::pow(5.0e-5, constants::MUC), plain);
        auto supcol = torch::full({1, 2}, 10.0, plain);
        BiggCloudInputs in{qc, nc, den, n0c, rsl_c, rsl_cd, rsl_cmu, supcol};
        auto out = bigg_cloud_freezing_torch(in, p, 60.0);
        auto loss = out.pfrzdtc.sum() + out.nfrzdtc.sum();
        loss.backward();
        assert(qc.grad().defined() && torch::isfinite(qc.grad()).all().item<bool>());
    } END_TEST();
}

void test_bigg_rain_delta_brs() {
    TEST(test_bigg_rain_delta_brs) {
        auto p = default_bigg_rain_params();
        auto opts = f64();
        auto qr = torch::full({1, 2}, 1.0e-4, opts);
        auto nr = torch::full({1, 2}, 1.0e5, opts);
        auto den = torch::full({1, 2}, 1.1, opts);
        auto n0r = torch::full({1, 2}, 8.0e6, opts);
        auto rsl_r = torch::full({1, 2}, 5.0e-4, opts);
        auto rsl_rd = torch::full({1, 2}, std::pow(5.0e-4, constants::DMR), opts);
        auto rsl_rmu = torch::full({1, 2}, std::pow(5.0e-4, constants::MUR), opts);
        auto supcol = torch::full({1, 2}, 10.0, opts);
        BiggRainInputs in{qr, nr, den, n0r, rsl_r, rsl_rd, rsl_rmu, supcol};
        auto out = bigg_rain_freezing_torch(in, p, 60.0);
        auto expected = out.pfrzdtr / p.denr;
        assert(torch::allclose(out.delta_brs, expected, 1e-12, 1e-15));
    } END_TEST();
}

void test_enhanced_melting_negative_when_warm() {
    TEST(test_enhanced_melting_negative_when_warm) {
        auto p = default_enhanced_melting_params();
        auto opts = f64();
        auto qs = torch::full({1, 2}, 1.0e-4, opts);
        auto qg = torch::full({1, 2}, 1.0e-4, opts);
        auto paacw = torch::full({1, 2}, 1.0e-6, opts);
        auto psacr = torch::full({1, 2}, 1.0e-7, opts);
        auto pgacr = torch::full({1, 2}, 1.0e-7, opts);
        auto n0so = torch::full({1, 2}, 2.0e6, opts);
        auto n0go = torch::full({1, 2}, 4.0e6, opts);
        auto n0sfac = torch::full({1, 2}, 1.0, opts);
        auto rsl_s = torch::full({1, 2}, 5.0e-4, opts);
        auto rsl_g = torch::full({1, 2}, 1.0e-3, opts);
        auto supcol = torch::full({1, 2}, -5.0, opts);
        EnhancedMeltingInputs in{qs, qg, paacw, psacr, pgacr, n0so, n0go, n0sfac,
                                   rsl_s, rsl_g, supcol};
        auto out = enhanced_melting_torch(in, p, 60.0);
        assert(torch::all(out.pseml <= 1e-15).item<bool>());
        assert(torch::all(out.pgeml <= 1e-15).item<bool>());
    } END_TEST();
}

int main() {
    std::cout << "kdm6_libtorch melt_freeze tests\n";
    test_melt_inactive_when_cold();
    test_melt_warm_psmlt_negative();
    test_melt_pimlt_full_transfer();
    test_melt_grad_finite();
    test_contact_inactive_when_supcol_low();
    test_contact_qc_gate_regression();
    test_bigg_cloud_qc_gate_regression();
    test_contact_grad_finite();
    test_bigg_cloud_grad_finite();
    test_bigg_rain_delta_brs();
    test_enhanced_melting_negative_when_warm();
    std::cout << "All melt_freeze tests passed.\n";
    return 0;
}
