#include "kdm6/cold.h"

#include <torch/torch.h>

#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>

using namespace kdm6;
using namespace kdm6::cold;

#define TEST(name) std::cout << "  RUN  " << #name << "\n"; do
#define END_TEST() while(false); std::cout << "  PASS\n"

namespace {

torch::TensorOptions f64() {
    return torch::TensorOptions().dtype(torch::kFloat64);
}

IceAccretionInputs make_inputs(double qi_value, double qr_value, bool grad = false) {
    auto opts = grad ? f64().requires_grad(true) : f64();
    auto plain = f64();
    auto qi = torch::full({1, 2}, qi_value, opts);
    auto qr = torch::full({1, 2}, qr_value, opts);
    auto den = torch::full({1, 2}, 1.1, plain);
    auto n0i = torch::full({1, 2}, 1.0e6, plain);
    auto n0r = torch::full({1, 2}, 8.0e6, plain);
    auto vt2r = torch::full({1, 2}, 5.0, plain);
    auto vt2i = torch::full({1, 2}, 0.5, plain);
    auto rslope_r = torch::full({1, 2}, 5.0e-4, plain);
    auto rslope2_r = rslope_r * rslope_r;
    auto rslope3_r = rslope2_r * rslope_r;
    auto rslopemu_r = torch::full({1, 2}, std::pow(5.0e-4, constants::MUR), plain);
    auto rsloped_r = torch::full({1, 2}, std::pow(5.0e-4, constants::DMR), plain);
    auto rslope_i = torch::full({1, 2}, 1.0e-4, plain);
    auto rslope2_i = rslope_i * rslope_i;
    auto rslope3_i = rslope2_i * rslope_i;
    auto rslopemu_i = torch::full({1, 2}, std::pow(1.0e-4, constants::MUI), plain);
    auto rsloped_i = torch::full({1, 2}, std::pow(1.0e-4, constants::DMI), plain);
    return IceAccretionInputs{
        qi, qr, den, n0i, n0r, vt2r, vt2i,
        rslope_r, rslope2_r, rslope3_r, rslopemu_r, rsloped_r,
        rslope_i, rslope2_i, rslope3_i, rslopemu_i, rsloped_i,
    };
}

}  // namespace

void test_ice_accretion_params_finite_and_positive() {
    TEST(test_ice_accretion_params_finite_and_positive) {
        auto p = default_ice_accretion_params();
        assert(std::isfinite(p.cmi) && p.cmi > 0);
        assert(std::isfinite(p.cmr) && p.cmr > 0);
        assert(std::isfinite(p.g1pmr) && p.g1pmr > 0);
        assert(std::isfinite(p.g3pmr) && p.g3pmr > 0);
        assert(std::isfinite(p.g3pdimi) && p.g3pdimi > 0);
        assert(p.eacri > 0 && p.eacir > 0);
        // mur=1 → g2pmr = rgmma(3) = Γ(3) = 2 (review6 audit fix).
        assert(std::abs(p.g2pmr - 2.0) < 1e-12);
    } END_TEST();
}

void test_ice_accretion_inactive_below_thresholds() {
    TEST(test_ice_accretion_inactive_below_thresholds) {
        auto p = default_ice_accretion_params();
        auto in = make_inputs(/*qi=*/1.0e-16, /*qr=*/1.0e-4);  // qi below the 1e-15 gate (#13) → exact 0
        auto out = ice_accretion_torch(in, p, 60.0);
        assert(torch::allclose(out.praci, torch::zeros_like(in.qi)));
        assert(torch::allclose(out.piacr, torch::zeros_like(in.qi)));

        // Gate-regression LOCK (#13): qi in (EPS=1e-15, old qcrmin=1e-9) → gate OPEN → praci>0
        // (capped at qi/dtcld). FAILS if the qmin gate regresses to 1e-9 (would re-block this qi).
        auto in_band = make_inputs(/*qi=*/1.0e-12, /*qr=*/1.0e-4);
        auto out_band = ice_accretion_torch(in_band, p, 60.0);
        assert(torch::all(out_band.praci > 0.0).item<bool>());

        auto in2 = make_inputs(/*qi=*/1.0e-5, /*qr=*/1.0e-12);  // qr too low
        auto out2 = ice_accretion_torch(in2, p, 60.0);
        assert(torch::allclose(out2.praci, torch::zeros_like(in2.qi)));
        assert(torch::allclose(out2.piacr, torch::zeros_like(in2.qi)));
    } END_TEST();
}

void test_ice_accretion_grad_finite() {
    TEST(test_ice_accretion_grad_finite) {
        auto p = default_ice_accretion_params();
        auto in = make_inputs(/*qi=*/1.0e-5, /*qr=*/1.0e-4, /*grad=*/true);
        auto out = ice_accretion_torch(in, p, 60.0);
        auto loss = out.praci.sum() + out.piacr.sum();
        loss.backward();
        assert(in.qi.grad().defined() && torch::isfinite(in.qi.grad()).all().item<bool>());
        assert(in.qr.grad().defined() && torch::isfinite(in.qr.grad()).all().item<bool>());
    } END_TEST();
}

// ═══════════════════════════════════════════════════════════════════════════
// C2 Ice → snow / graupel
// ═══════════════════════════════════════════════════════════════════════════

namespace {

IceToSnowGraupelInputs make_isg_inputs(double qi_value, double supcol_value, bool grad = false) {
    auto opts = grad ? f64().requires_grad(true) : f64();
    auto plain = f64();
    auto qi = torch::full({1, 2}, qi_value, opts);
    auto qs = torch::full({1, 2}, 1.0e-4, opts);
    auto qg = torch::full({1, 2}, 1.0e-4, opts);
    auto den = torch::full({1, 2}, 1.1, plain);
    auto n0i = torch::full({1, 2}, 1.0e6, plain);
    auto n0so = torch::full({1, 2}, 2.0e6, plain);
    auto n0go = torch::full({1, 2}, 4.0e6, plain);
    auto n0sfac = torch::full({1, 2}, 5.0, plain);
    auto supcol = torch::full({1, 2}, supcol_value, plain);
    auto vt2s = torch::full({1, 2}, 1.0, plain);
    auto vt2g = torch::full({1, 2}, 3.0, plain);
    auto vt2i = torch::full({1, 2}, 0.5, plain);
    auto rslope_s = torch::full({1, 2}, 5.0e-4, plain);
    auto rslope_g = torch::full({1, 2}, 1.0e-3, plain);
    auto rslope_i = torch::full({1, 2}, 1.0e-4, plain);
    return IceToSnowGraupelInputs{
        qi, qs, qg, den, n0i, n0so, n0go, n0sfac, supcol, vt2s, vt2g, vt2i,
        rslope_s, rslope_s * rslope_s, rslope_s * rslope_s * rslope_s,
        torch::full({1, 2}, std::pow(5.0e-4, constants::MUS), plain),
        rslope_g, rslope_g * rslope_g, rslope_g * rslope_g * rslope_g,
        torch::full({1, 2}, std::pow(1.0e-3, constants::MUG), plain),
        rslope_i, rslope_i * rslope_i, rslope_i * rslope_i * rslope_i,
        torch::full({1, 2}, std::pow(1.0e-4, constants::MUI), plain),
        torch::full({1, 2}, std::pow(1.0e-4, constants::DMI), plain),
    };
}

}  // namespace

void test_isg_params_finite() {
    TEST(test_isg_params_finite) {
        auto p = default_ice_to_snow_graupel_params();
        assert(std::isfinite(p.cmi) && p.cmi > 0);
        assert(p.g1pms == 1.0);  // mus=0 short-circuit
        assert(p.g1pmg == 1.0);
        // Γ(3) = 2 (review6 audit fix).
        assert(std::abs(p.g3pms - 2.0) < 1e-12);
        assert(std::abs(p.g3pmg - 2.0) < 1e-12);
    } END_TEST();
}

void test_isg_inactive_when_qi_low() {
    TEST(test_isg_inactive_when_qi_low) {
        auto p = default_ice_to_snow_graupel_params();
        auto in = make_isg_inputs(/*qi=*/1.0e-16, /*supcol=*/10.0);  // qi below the 1e-15 gate (#14) → exact 0
        auto out = ice_to_snow_graupel_torch(in, p, 60.0);
        assert(torch::allclose(out.psaci, torch::zeros_like(in.qi)));
        assert(torch::allclose(out.pgaci, torch::zeros_like(in.qi)));

        // Gate-regression LOCK (#14): qi in (EPS=1e-15, old 1e-9) → gate OPEN → psaci>0 (cap).
        // FAILS if the qmin gate regresses to 1e-9.
        auto in_band = make_isg_inputs(/*qi=*/1.0e-12, /*supcol=*/10.0);
        auto out_band = ice_to_snow_graupel_torch(in_band, p, 60.0);
        assert(torch::all(out_band.psaci > 0.0).item<bool>());
    } END_TEST();
}

void test_isg_eacgi_temperature_direction() {
    TEST(test_isg_eacgi_temperature_direction) {
        // Fortran 직역: cold(supcol↑) → eacgi 작음 → pgaci 작음 (직관 반대)
        auto p = default_ice_to_snow_graupel_params();
        auto in_warm = make_isg_inputs(/*qi=*/1.0e-5, /*supcol=*/2.0);
        auto in_cold = make_isg_inputs(/*qi=*/1.0e-5, /*supcol=*/50.0);
        auto out_warm = ice_to_snow_graupel_torch(in_warm, p, 60.0);
        auto out_cold = ice_to_snow_graupel_torch(in_cold, p, 60.0);
        assert(torch::all(out_cold.pgaci <= out_warm.pgaci + 1e-15).item<bool>());
    } END_TEST();
}

void test_isg_grad_finite() {
    TEST(test_isg_grad_finite) {
        auto p = default_ice_to_snow_graupel_params();
        auto in = make_isg_inputs(/*qi=*/1.0e-5, /*supcol=*/10.0, /*grad=*/true);
        auto out = ice_to_snow_graupel_torch(in, p, 60.0);
        auto loss = out.psaci.sum() + out.pgaci.sum();
        loss.backward();
        assert(in.qi.grad().defined() && torch::isfinite(in.qi.grad()).all().item<bool>());
        assert(in.qs.grad().defined() && torch::isfinite(in.qs.grad()).all().item<bool>());
        assert(in.qg.grad().defined() && torch::isfinite(in.qg.grad()).all().item<bool>());
    } END_TEST();
}

// ═══════════════════════════════════════════════════════════════════════════
// C2b Number accretion
// ═══════════════════════════════════════════════════════════════════════════

namespace {

NumberAccretionInputs make_na_inputs(double supcol_value, double ni_value, double nr_value, bool grad = false) {
    auto opts = grad ? f64().requires_grad(true) : f64();
    auto plain = f64();
    auto qi = torch::full({1, 2}, 1.0e-5, opts);
    auto qs = torch::full({1, 2}, 1.0e-4, plain);
    auto qg = torch::full({1, 2}, 1.0e-4, plain);
    auto qr = torch::full({1, 2}, 1.0e-4, plain);
    auto ni = torch::full({1, 2}, ni_value, opts);
    auto nr = torch::full({1, 2}, nr_value, opts);
    auto den = torch::full({1, 2}, 1.1, plain);
    auto n0i = torch::full({1, 2}, 1.0e6, plain);
    auto n0r = torch::full({1, 2}, 8.0e6, plain);
    auto n0sfac = torch::full({1, 2}, 5.0, plain);
    auto supcol = torch::full({1, 2}, supcol_value, plain);
    auto vt2r = torch::full({1, 2}, 5.0, plain);
    auto vt2s = torch::full({1, 2}, 1.0, plain);
    auto vt2g = torch::full({1, 2}, 3.0, plain);
    auto vt2i = torch::full({1, 2}, 0.5, plain);
    auto rsl_r = torch::full({1, 2}, 5.0e-4, plain);
    auto rsl_s = torch::full({1, 2}, 5.0e-4, plain);
    auto rsl_g = torch::full({1, 2}, 1.0e-3, plain);
    auto rsl_i = torch::full({1, 2}, 1.0e-4, plain);
    return NumberAccretionInputs{
        qi, qs, qg, qr, ni, nr, den, n0i, n0r, n0sfac, supcol,
        vt2r, vt2s, vt2g, vt2i,
        rsl_r, rsl_r * rsl_r, rsl_r * rsl_r * rsl_r,
        torch::full({1, 2}, std::pow(5.0e-4, constants::MUR), plain),
        rsl_s, rsl_s * rsl_s, rsl_s * rsl_s * rsl_s,
        torch::full({1, 2}, std::pow(5.0e-4, constants::MUS), plain),
        rsl_g, rsl_g * rsl_g, rsl_g * rsl_g * rsl_g,
        torch::full({1, 2}, std::pow(1.0e-3, constants::MUG), plain),
        rsl_i, rsl_i * rsl_i, rsl_i * rsl_i * rsl_i,
        torch::full({1, 2}, std::pow(1.0e-4, constants::MUI), plain),
    };
}

}  // namespace

void test_na_inactive_when_warm() {
    TEST(test_na_inactive_when_warm) {
        auto p = default_number_accretion_params();
        auto in = make_na_inputs(/*supcol=*/-5.0, /*ni=*/1.0e5, /*nr=*/1.0e4);
        auto out = number_accretion_torch(in, p, 60.0);
        auto z = torch::zeros_like(in.qi);
        assert(torch::allclose(out.nraci, z));
        assert(torch::allclose(out.niacr, z));
        assert(torch::allclose(out.nsaci, z));
        assert(torch::allclose(out.ngaci, z));
    } END_TEST();
}

void test_na_capped_by_ni_per_dt() {
    TEST(test_na_capped_by_ni_per_dt) {
        auto p = default_number_accretion_params();
        auto in = make_na_inputs(/*supcol=*/10.0, /*ni=*/1.0e5, /*nr=*/1.0e4);
        auto out = number_accretion_torch(in, p, 60.0);
        const double dtcld = 60.0;
        assert(torch::all(out.nraci <= in.ni / dtcld + 1e-15).item<bool>());
        assert(torch::all(out.nsaci <= in.ni / dtcld + 1e-15).item<bool>());
        assert(torch::all(out.ngaci <= in.ni / dtcld + 1e-15).item<bool>());
        assert(torch::all(out.niacr <= in.nr / dtcld + 1e-15).item<bool>());
    } END_TEST();
}

void test_na_grad_finite() {
    TEST(test_na_grad_finite) {
        auto p = default_number_accretion_params();
        auto in = make_na_inputs(/*supcol=*/10.0, /*ni=*/1.0e5, /*nr=*/1.0e4, /*grad=*/true);
        auto out = number_accretion_torch(in, p, 60.0);
        auto loss = out.nraci.sum() + out.niacr.sum() + out.nsaci.sum() + out.ngaci.sum();
        loss.backward();
        assert(in.qi.grad().defined() && torch::isfinite(in.qi.grad()).all().item<bool>());
        assert(in.ni.grad().defined() && torch::isfinite(in.ni.grad()).all().item<bool>());
        assert(in.nr.grad().defined() && torch::isfinite(in.nr.grad()).all().item<bool>());
    } END_TEST();
}

// ═══════════════════════════════════════════════════════════════════════════
// C2c Cloud water riming
// ═══════════════════════════════════════════════════════════════════════════

namespace {

CloudWaterRimingInputs make_cwr_inputs(double supcol_value, double avedia_i_value, bool grad = false, double qc_value = 1.0e-3) {
    auto opts = grad ? f64().requires_grad(true) : f64();
    auto plain = f64();
    auto qc = torch::full({1, 2}, qc_value, opts);
    auto nc = torch::full({1, 2}, 1.0e8, opts);
    auto qs = torch::full({1, 2}, 1.0e-4, plain);
    auto qg = torch::full({1, 2}, 1.0e-4, plain);
    auto qi = torch::full({1, 2}, 1.0e-5, plain);
    auto den = torch::full({1, 2}, 1.1, plain);
    auto denfac = torch::full({1, 2}, 1.0, plain);
    auto n0so = torch::full({1, 2}, 2.0e6, plain);
    auto n0go = torch::full({1, 2}, 4.0e6, plain);
    auto n0i = torch::full({1, 2}, 1.0e6, plain);
    auto n0c = torch::full({1, 2}, 1.0e8, plain);
    auto n0sfac = torch::full({1, 2}, 5.0, plain);
    auto avtg = torch::full({1, 2}, 100.0, plain);
    auto g3pbg = torch::full({1, 2}, 0.5, plain);
    auto avedia_i = torch::full({1, 2}, avedia_i_value, plain);
    auto supcol = torch::full({1, 2}, supcol_value, plain);
    auto rsl_s = torch::full({1, 2}, 5.0e-4, plain);
    auto rsl_g = torch::full({1, 2}, 1.0e-3, plain);
    auto rsl_i = torch::full({1, 2}, 1.0e-4, plain);
    auto rsl_c = torch::full({1, 2}, 5.0e-5, plain);
    return CloudWaterRimingInputs{
        qc, nc, qs, qg, qi, den, denfac, n0so, n0go, n0i, n0c, n0sfac,
        avtg, g3pbg, avedia_i, supcol,
        rsl_s * rsl_s * rsl_s, torch::full({1, 2}, std::pow(5.0e-4, constants::BVTS), plain),
        torch::full({1, 2}, std::pow(5.0e-4, constants::MUS), plain),
        rsl_g * rsl_g * rsl_g, torch::full({1, 2}, std::pow(1.0e-3, 0.5316), plain),
        torch::full({1, 2}, std::pow(1.0e-3, constants::MUG), plain),
        rsl_i * rsl_i * rsl_i, torch::full({1, 2}, std::pow(1.0e-4, constants::BVTI), plain),
        torch::full({1, 2}, std::pow(1.0e-4, constants::MUI), plain),
        rsl_c, torch::full({1, 2}, std::pow(5.0e-5, constants::MUC), plain),
    };
}

}  // namespace

void test_cwr_inactive_when_qc_low() {
    TEST(test_cwr_inactive_when_qc_low) {
        auto p = default_cloud_water_riming_params();
        // qc below the EPS=1e-15 gate (#16/#17) → psacw/pgacw/piacw = 0 (gate blocks; qs/qg>qcrmin).
        auto in_lo = make_cwr_inputs(/*supcol=*/10.0, /*avedia_i=*/1.0e-4, /*grad=*/false, /*qc=*/1.0e-16);
        auto out_lo = cloud_water_riming_torch(in_lo, p, 60.0);
        assert(torch::allclose(out_lo.psacw, torch::zeros_like(in_lo.qc)));
        assert(torch::allclose(out_lo.pgacw, torch::zeros_like(in_lo.qc)));
        assert(torch::allclose(out_lo.piacw, torch::zeros_like(in_lo.qc)));

        // Gate-regression LOCK (#16/#17): qc in (EPS=1e-15, old qcrmin=1e-9) → gate OPEN → ALL three
        // qc-gated rates (psacw/pgacw/piacw, sharing the qc>qmin gate) > 0 (capped at qc/dtcld).
        // FAILS if the qmin gate regresses to 1e-9 (would re-block this qc). inputs: qs/qg>qcrmin,
        // supcol>0, qi>qcrmin, avedia_i>=di50 so only the qc gate can zero them.
        auto in_band = make_cwr_inputs(/*supcol=*/10.0, /*avedia_i=*/1.0e-4, /*grad=*/false, /*qc=*/1.0e-12);
        auto out_band = cloud_water_riming_torch(in_band, p, 60.0);
        assert(torch::all(out_band.psacw > 0.0).item<bool>());
        assert(torch::all(out_band.pgacw > 0.0).item<bool>());
        assert(torch::all(out_band.piacw > 0.0).item<bool>());
    } END_TEST();
}

void test_cwr_piacw_pk97_di50_threshold() {
    TEST(test_cwr_piacw_pk97_di50_threshold) {
        auto p = default_cloud_water_riming_params();
        // avedia_i = 30 µm < di50 → piacw, niacw = 0
        auto in_small = make_cwr_inputs(/*supcol=*/10.0, /*avedia_i=*/3.0e-5);
        auto out_small = cloud_water_riming_torch(in_small, p, 60.0);
        assert(torch::allclose(out_small.piacw, torch::zeros_like(in_small.qc)));
        assert(torch::allclose(out_small.niacw, torch::zeros_like(in_small.qc)));

        // avedia_i = 100 µm >= di50 → active
        auto in_big = make_cwr_inputs(/*supcol=*/10.0, /*avedia_i=*/1.0e-4);
        auto out_big = cloud_water_riming_torch(in_big, p, 60.0);
        assert(torch::all(out_big.piacw > 0).item<bool>());
        assert(torch::all(out_big.niacw > 0).item<bool>());
    } END_TEST();
}

void test_cwr_paacw_weighted_average() {
    TEST(test_cwr_paacw_weighted_average) {
        auto p = default_cloud_water_riming_params();
        auto in = make_cwr_inputs(/*supcol=*/10.0, /*avedia_i=*/1.0e-4);
        auto out = cloud_water_riming_torch(in, p, 60.0);
        // qs == qg → paacw = 0.5*(psacw + pgacw)
        auto expected = 0.5 * (out.psacw + out.pgacw);
        assert(torch::allclose(out.paacw, expected, 1e-12, 1e-15));
    } END_TEST();
}

void test_cwr_grad_finite() {
    TEST(test_cwr_grad_finite) {
        auto p = default_cloud_water_riming_params();
        auto in = make_cwr_inputs(/*supcol=*/10.0, /*avedia_i=*/1.0e-4, /*grad=*/true);
        auto out = cloud_water_riming_torch(in, p, 60.0);
        auto loss = out.psacw.sum() + out.nsacw.sum() + out.pgacw.sum() + out.ngacw.sum()
                   + out.paacw.sum() + out.naacw.sum() + out.piacw.sum() + out.niacw.sum();
        loss.backward();
        assert(in.qc.grad().defined() && torch::isfinite(in.qc.grad()).all().item<bool>());
        assert(in.nc.grad().defined() && torch::isfinite(in.nc.grad()).all().item<bool>());
    } END_TEST();
}

// ═══════════════════════════════════════════════════════════════════════════
// C2d Rain-snow-graupel collection
// ═══════════════════════════════════════════════════════════════════════════

namespace {

RainSnowGraupelCollectionInputs make_rsgc_inputs(double supcol_value, bool grad = false) {
    auto opts = grad ? f64().requires_grad(true) : f64();
    auto plain = f64();
    auto qr = torch::full({1, 2}, 1.0e-4, opts);
    auto qs = torch::full({1, 2}, 1.0e-4, opts);
    auto qg = torch::full({1, 2}, 1.0e-4, opts);
    auto nr = torch::full({1, 2}, 1.0e5, opts);
    auto den = torch::full({1, 2}, 1.1, plain);
    auto n0r = torch::full({1, 2}, 8.0e6, plain);
    auto n0so = torch::full({1, 2}, 2.0e6, plain);
    auto n0go = torch::full({1, 2}, 4.0e6, plain);
    auto n0sfac = torch::full({1, 2}, 5.0, plain);
    auto supcol = torch::full({1, 2}, supcol_value, plain);
    auto vt2r = torch::full({1, 2}, 5.0, plain);
    auto vt2s = torch::full({1, 2}, 1.0, plain);
    auto vt2g = torch::full({1, 2}, 3.0, plain);
    auto rsl_r = torch::full({1, 2}, 5.0e-4, plain);
    auto rsl_s = torch::full({1, 2}, 5.0e-4, plain);
    auto rsl_g = torch::full({1, 2}, 1.0e-3, plain);
    return RainSnowGraupelCollectionInputs{
        qr, qs, qg, nr, den, n0r, n0so, n0go, n0sfac, supcol, vt2r, vt2s, vt2g,
        rsl_r, rsl_r * rsl_r, rsl_r * rsl_r * rsl_r,
        torch::full({1, 2}, std::pow(5.0e-4, constants::MUR), plain),
        torch::full({1, 2}, std::pow(5.0e-4, constants::DMR), plain),
        rsl_s, rsl_s * rsl_s, rsl_s * rsl_s * rsl_s,
        torch::full({1, 2}, std::pow(5.0e-4, constants::MUS), plain),
        torch::full({1, 2}, std::pow(5.0e-4, constants::DMS), plain),
        rsl_g, rsl_g * rsl_g, rsl_g * rsl_g * rsl_g,
        torch::full({1, 2}, std::pow(1.0e-3, constants::MUG), plain),
    };
}

}  // namespace

void test_rsgc_pracs_zero_when_warm() {
    TEST(test_rsgc_pracs_zero_when_warm) {
        auto p = default_rain_snow_graupel_collection_params();
        auto in = make_rsgc_inputs(/*supcol=*/-5.0);
        auto out = rain_snow_graupel_collection_torch(in, p, 60.0);
        assert(torch::allclose(out.pracs, torch::zeros_like(in.qr)));
        // Other processes should be active
        assert(torch::all(out.psacr > 0).item<bool>());
        assert(torch::all(out.pgacr > 0).item<bool>());
    } END_TEST();
}

void test_rsgc_nracs_always_zero() {
    TEST(test_rsgc_nracs_always_zero) {
        auto p = default_rain_snow_graupel_collection_params();
        auto in = make_rsgc_inputs(/*supcol=*/10.0);
        auto out = rain_snow_graupel_collection_torch(in, p, 60.0);
        assert(torch::allclose(out.nracs, torch::zeros_like(in.qr)));
    } END_TEST();
}

void test_rsgc_grad_finite() {
    TEST(test_rsgc_grad_finite) {
        auto p = default_rain_snow_graupel_collection_params();
        auto in = make_rsgc_inputs(/*supcol=*/10.0, /*grad=*/true);
        auto out = rain_snow_graupel_collection_torch(in, p, 60.0);
        auto loss = out.pracs.sum() + out.psacr.sum() + out.nsacr.sum()
                  + out.pgacr.sum() + out.ngacr.sum();
        loss.backward();
        assert(in.qr.grad().defined() && torch::isfinite(in.qr.grad()).all().item<bool>());
        assert(in.qs.grad().defined() && torch::isfinite(in.qs.grad()).all().item<bool>());
        assert(in.qg.grad().defined() && torch::isfinite(in.qg.grad()).all().item<bool>());
        assert(in.nr.grad().defined() && torch::isfinite(in.nr.grad()).all().item<bool>());
    } END_TEST();
}

// ═══════════════════════════════════════════════════════════════════════════
// C2e Hallett-Mossop multiplication
// ═══════════════════════════════════════════════════════════════════════════

namespace {

HallettMossopInputs make_hm_inputs(double t_value, bool grad = false) {
    auto opts = grad ? f64().requires_grad(true) : f64();
    auto plain = f64();
    auto paacw = torch::full({1, 2}, 1.0e-6, opts);
    auto psacr = torch::full({1, 2}, 1.0e-6, opts);
    auto pgacr = torch::full({1, 2}, 1.0e-6, opts);
    auto qc = torch::full({1, 2}, 1.0e-3, plain);
    auto qr = torch::full({1, 2}, 0.5e-3, plain);
    auto qs = torch::full({1, 2}, 0.5e-3, plain);
    auto qg = torch::full({1, 2}, 0.5e-3, plain);
    auto t = torch::full({1, 2}, t_value, plain);
    auto den = torch::full({1, 2}, 1.1, plain);
    return HallettMossopInputs{paacw, psacr, pgacr, qc, qr, qs, qg, t, den};
}

}  // namespace

void test_hm_inactive_outside_temperature_band() {
    TEST(test_hm_inactive_outside_temperature_band) {
        auto p = default_hallett_mossop_params();
        auto in = make_hm_inputs(/*t=*/260.0);
        auto out = hallett_mossop_torch(in, p);
        auto z = torch::zeros_like(in.paacw);
        assert(torch::allclose(out.pmulcs, z));
        assert(torch::allclose(out.pmulrs, z));
        assert(torch::allclose(out.pmulcg, z));
        assert(torch::allclose(out.pmulrg, z));
    } END_TEST();
}

void test_hm_active_at_peak() {
    TEST(test_hm_active_at_peak) {
        auto p = default_hallett_mossop_params();
        auto in = make_hm_inputs(/*t=*/268.16);
        auto out = hallett_mossop_torch(in, p);
        assert(torch::all(out.pmulcs > 0).item<bool>());
        assert(torch::all(out.pmulcg > 0).item<bool>());
    } END_TEST();
}

void test_hm_paacw_adj_consistency() {
    TEST(test_hm_paacw_adj_consistency) {
        auto p = default_hallett_mossop_params();
        auto in = make_hm_inputs(/*t=*/268.16);
        auto out = hallett_mossop_torch(in, p);
        auto expected = in.paacw - out.pmulcs - out.pmulcg;
        assert(torch::allclose(out.paacw_adj, expected, 1e-12, 1e-15));
    } END_TEST();
}

void test_hm_grad_finite() {
    TEST(test_hm_grad_finite) {
        auto p = default_hallett_mossop_params();
        auto in = make_hm_inputs(/*t=*/268.16, /*grad=*/true);
        auto out = hallett_mossop_torch(in, p);
        auto loss = out.pmulcs.sum() + out.pmulrs.sum() + out.pmulcg.sum() + out.pmulrg.sum();
        loss.backward();
        assert(in.paacw.grad().defined() && torch::isfinite(in.paacw.grad()).all().item<bool>());
        assert(in.psacr.grad().defined() && torch::isfinite(in.psacr.grad()).all().item<bool>());
        assert(in.pgacr.grad().defined() && torch::isfinite(in.pgacr.grad()).all().item<bool>());
    } END_TEST();
}

// ═══════════════════════════════════════════════════════════════════════════
// C3 Ice nucleation
// ═══════════════════════════════════════════════════════════════════════════

namespace {

IceNucleationInputs make_icenuc_inputs(double supcol_value, double rh_ice_value, double nci_value, bool grad = false) {
    auto opts = grad ? f64().requires_grad(true) : f64();
    auto plain = f64();
    auto supcol = torch::full({1, 2}, supcol_value, opts);
    auto supsat = torch::full({1, 2}, 1.0e-4, opts);
    auto rh_ice = torch::full({1, 2}, rh_ice_value, plain);
    auto prevp = torch::full({1, 2}, 0.0, opts);
    auto nci_ice = torch::full({1, 2}, nci_value, plain);
    auto den = torch::full({1, 2}, 1.1, plain);
    return IceNucleationInputs{supcol, supsat, rh_ice, prevp, nci_ice, den};
}

}  // namespace

void test_icenuc_inactive_when_warm() {
    TEST(test_icenuc_inactive_when_warm) {
        auto p = default_ice_nucleation_params();
        auto in = make_icenuc_inputs(/*supcol=*/2.0, /*rh_ice=*/1.0, /*nci=*/1.0e3);
        auto out = ice_nucleation_torch(in, p, 60.0);
        assert(torch::allclose(out.pinud, torch::zeros_like(in.supcol)));
    } END_TEST();
}

void test_icenuc_no_nucleation_when_nci_high() {
    TEST(test_icenuc_no_nucleation_when_nci_high) {
        auto p = default_ice_nucleation_params();
        auto in = make_icenuc_inputs(/*supcol=*/15.0, /*rh_ice=*/1.2, /*nci=*/1.0e6);
        auto out = ice_nucleation_torch(in, p, 60.0);
        assert(torch::allclose(out.pinud, torch::zeros_like(in.supcol)));
    } END_TEST();
}

void test_icenuc_grad_finite() {
    TEST(test_icenuc_grad_finite) {
        auto p = default_ice_nucleation_params();
        auto in = make_icenuc_inputs(/*supcol=*/15.0, /*rh_ice=*/1.2, /*nci=*/1.0e3, /*grad=*/true);
        auto out = ice_nucleation_torch(in, p, 60.0);
        auto loss = out.pinud.sum() + out.ninud.sum();
        loss.backward();
        assert(in.supcol.grad().defined() && torch::isfinite(in.supcol.grad()).all().item<bool>());
        assert(in.supsat.grad().defined() && torch::isfinite(in.supsat.grad()).all().item<bool>());
    } END_TEST();
}

// ═══════════════════════════════════════════════════════════════════════════
// C4 Dep / Sub
// ═══════════════════════════════════════════════════════════════════════════

namespace {

DepSubInputs make_depsub_inputs(double supcol_value, double rh_ice_value, bool grad = false) {
    auto opts = grad ? f64().requires_grad(true) : f64();
    auto plain = f64();
    auto qi = torch::full({1, 2}, 1.0e-5, opts);
    auto qs = torch::full({1, 2}, 1.0e-4, plain);
    auto qg = torch::full({1, 2}, 1.0e-4, plain);
    auto rh_ice = torch::full({1, 2}, rh_ice_value, plain);
    auto supcol = torch::full({1, 2}, supcol_value, plain);
    auto supsat = torch::full({1, 2}, 1.0e-4, plain);
    auto prevp = torch::full({1, 2}, 0.0, plain);
    auto pinud = torch::full({1, 2}, 0.0, plain);
    auto ifsat_in = torch::full({1, 2}, false, torch::TensorOptions().dtype(torch::kBool));
    auto n0i = torch::full({1, 2}, 1.0e6, plain);
    auto n0so = torch::full({1, 2}, 2.0e6, plain);
    auto n0go = torch::full({1, 2}, 4.0e6, plain);
    auto n0sfac = torch::full({1, 2}, 5.0, plain);
    auto work1_ice = torch::full({1, 2}, 1.0e-3, plain);
    auto work2 = torch::full({1, 2}, 1.5, plain);
    auto precg2 = torch::full({1, 2}, 0.5, plain);
    auto rsl_s = torch::full({1, 2}, 5.0e-4, plain);
    auto rsl_g = torch::full({1, 2}, 1.0e-3, plain);
    auto rsl_i = torch::full({1, 2}, 1.0e-4, plain);
    return DepSubInputs{
        qi, qs, qg, rh_ice, supcol, supsat, prevp, pinud, ifsat_in,
        n0i, n0so, n0go, n0sfac, work1_ice, work2, precg2,
        rsl_s, rsl_s * rsl_s, torch::full({1, 2}, std::pow(5.0e-4, constants::BVTS), plain),
        torch::full({1, 2}, std::pow(5.0e-4, constants::MUS), plain),
        rsl_g, rsl_g * rsl_g, torch::full({1, 2}, std::pow(1.0e-3, 0.5316), plain),
        torch::full({1, 2}, std::pow(1.0e-3, constants::MUG), plain),
        rsl_i * rsl_i, torch::full({1, 2}, std::pow(1.0e-4, constants::MUI), plain),
    };
}

}  // namespace

void test_depsub_inactive_when_warm() {
    TEST(test_depsub_inactive_when_warm) {
        auto p = default_dep_sub_params();
        auto in = make_depsub_inputs(/*supcol=*/-5.0, /*rh_ice=*/1.10);
        auto out = dep_sub_torch(in, p, 60.0);
        auto z = torch::zeros_like(in.qi);
        assert(torch::allclose(out.pidep, z));
        assert(torch::allclose(out.psdep, z));
        assert(torch::allclose(out.pgdep, z));
    } END_TEST();
}

void test_depsub_deposition_when_supersat() {
    TEST(test_depsub_deposition_when_supersat) {
        auto p = default_dep_sub_params();
        auto in = make_depsub_inputs(/*supcol=*/10.0, /*rh_ice=*/1.10);
        auto out = dep_sub_torch(in, p, 60.0);
        // pidep should be active and finite
        assert(torch::isfinite(out.pidep).all().item<bool>());
        assert(out.ifsat.dtype() == torch::kBool);
    } END_TEST();
}

void test_depsub_grad_finite() {
    TEST(test_depsub_grad_finite) {
        auto p = default_dep_sub_params();
        auto in = make_depsub_inputs(/*supcol=*/10.0, /*rh_ice=*/1.10, /*grad=*/true);
        auto out = dep_sub_torch(in, p, 60.0);
        auto loss = out.pidep.sum() + out.psdep.sum() + out.pgdep.sum();
        loss.backward();
        assert(in.qi.grad().defined() && torch::isfinite(in.qi.grad()).all().item<bool>());
    } END_TEST();
}

// ═══════════════════════════════════════════════════════════════════════════
// C5 / C6
// ═══════════════════════════════════════════════════════════════════════════

void test_agg_inactive_when_warm() {
    TEST(test_agg_inactive_when_warm) {
        auto p = default_ice_aggregation_params();
        auto qi = torch::full({1, 2}, 1.0e-4, f64());
        auto ni = torch::full({1, 2}, 1.0e5, f64());
        auto t = torch::full({1, 2}, 260.0, f64());
        auto den = torch::full({1, 2}, 1.1, f64());
        auto supcol = torch::full({1, 2}, -5.0, f64());
        auto out = ice_aggregation_torch(qi, ni, t, den, supcol, p, 60.0);
        assert(torch::allclose(out.psaut, torch::zeros_like(qi)));
        assert(torch::allclose(out.nsaut, torch::zeros_like(qi)));
    } END_TEST();
}

void test_agg_psaut_capped() {
    TEST(test_agg_psaut_capped) {
        auto p = default_ice_aggregation_params();
        auto qi = torch::full({1, 2}, 1.0e-2, f64());
        auto ni = torch::full({1, 2}, 1.0e5, f64());
        auto t = torch::full({1, 2}, 260.0, f64());
        auto den = torch::full({1, 2}, 1.1, f64());
        auto supcol = torch::full({1, 2}, 15.0, f64());
        auto out = ice_aggregation_torch(qi, ni, t, den, supcol, p, 60.0);
        assert(torch::all(out.psaut <= qi / 60.0 + 1e-15).item<bool>());
    } END_TEST();
}

void test_agg_grad_finite() {
    TEST(test_agg_grad_finite) {
        auto p = default_ice_aggregation_params();
        auto qi = torch::full({1, 2}, 1.0e-4, f64().requires_grad(true));
        auto ni = torch::full({1, 2}, 1.0e5, f64().requires_grad(true));
        auto t = torch::full({1, 2}, 260.0, f64());
        auto den = torch::full({1, 2}, 1.1, f64());
        auto supcol = torch::full({1, 2}, 15.0, f64());
        auto out = ice_aggregation_torch(qi, ni, t, den, supcol, p, 60.0);
        auto loss = out.psaut.sum() + out.nsaut.sum();
        loss.backward();
        assert(qi.grad().defined() && torch::isfinite(qi.grad()).all().item<bool>());
        assert(ni.grad().defined() && torch::isfinite(ni.grad()).all().item<bool>());
    } END_TEST();
}

namespace {

SnowEvapInputs make_evap_inputs(double supcol_value, double rh_value, bool grad = false) {
    auto opts = grad ? f64().requires_grad(true) : f64();
    auto plain = f64();
    auto qs = torch::full({1, 2}, 1.0e-4, opts);
    auto rh_w = torch::full({1, 2}, rh_value, plain);
    auto supcol = torch::full({1, 2}, supcol_value, plain);
    auto n0so = torch::full({1, 2}, 2.0e6, plain);
    auto n0sfac = torch::full({1, 2}, 1.0, plain);
    auto work1_water = torch::full({1, 2}, 1.0e-3, plain);
    auto work2 = torch::full({1, 2}, 1.5, plain);
    auto rsl_s = torch::full({1, 2}, 5.0e-4, plain);
    return SnowEvapInputs{
        qs, rh_w, supcol, n0so, n0sfac, work1_water, work2,
        rsl_s, rsl_s * rsl_s,
        torch::full({1, 2}, std::pow(5.0e-4, constants::BVTS), plain),
        torch::full({1, 2}, std::pow(5.0e-4, constants::MUS), plain),
    };
}

}  // namespace

void test_snow_evap_inactive_when_cold() {
    TEST(test_snow_evap_inactive_when_cold) {
        auto p = default_snow_evap_params();
        auto in = make_evap_inputs(/*supcol=*/5.0, /*rh=*/0.5);
        auto psevp = snow_evap_torch(in, p, 60.0);
        assert(torch::allclose(psevp, torch::zeros_like(in.qs)));
    } END_TEST();
}

void test_snow_evap_negative_and_capped() {
    TEST(test_snow_evap_negative_and_capped) {
        auto p = default_snow_evap_params();
        auto in = make_evap_inputs(/*supcol=*/-5.0, /*rh=*/0.5);
        auto psevp = snow_evap_torch(in, p, 60.0);
        assert(torch::all(psevp <= 1e-15).item<bool>());
        assert(torch::all(psevp >= -in.qs / 60.0 - 1e-15).item<bool>());
    } END_TEST();
}

void test_snow_evap_grad_finite() {
    TEST(test_snow_evap_grad_finite) {
        auto p = default_snow_evap_params();
        auto in = make_evap_inputs(/*supcol=*/-5.0, /*rh=*/0.5, /*grad=*/true);
        auto psevp = snow_evap_torch(in, p, 60.0);
        psevp.sum().backward();
        assert(in.qs.grad().defined() && torch::isfinite(in.qs.grad()).all().item<bool>());
    } END_TEST();
}

namespace {

GraupelEvapInputs make_graupel_evap_inputs(
    double supcol_value, double rh_value, bool grad = false
) {
    auto opts = grad ? f64().requires_grad(true) : f64();
    auto plain = f64();
    auto qg = torch::full({1, 2}, 1.0e-4, opts);
    auto rh_w = torch::full({1, 2}, rh_value, plain);
    auto supcol = torch::full({1, 2}, supcol_value, plain);
    auto n0go = torch::full({1, 2}, 4.0e6, plain);
    auto work1_water = torch::full({1, 2}, 1.0e-3, plain);
    auto work2 = torch::full({1, 2}, 1.5, plain);
    auto rsl_g = torch::full({1, 2}, 5.0e-4, plain);
    auto precg2 = torch::full({1, 2}, 0.5, plain);
    // bvtg는 graupel 밀도 의존 (ProgB runtime). 테스트에선 0.6 ≈ WDM6 기본값.
    auto rslopeb_g = torch::full({1, 2}, std::pow(5.0e-4, 0.6), plain);
    return GraupelEvapInputs{
        qg, rh_w, supcol, n0go, work1_water, work2,
        rsl_g, rsl_g * rsl_g, rslopeb_g,
        torch::full({1, 2}, std::pow(5.0e-4, constants::MUG), plain),
        precg2,
    };
}

}  // namespace

void test_graupel_evap_inactive_when_cold() {
    TEST(test_graupel_evap_inactive_when_cold) {
        // supcol > 0 (cold): graupel evap inactive (warm-only).
        auto p = default_graupel_evap_params();
        auto in = make_graupel_evap_inputs(/*supcol=*/5.0, /*rh=*/0.5);
        auto pgevp = graupel_evap_torch(in, p, 60.0);
        assert(torch::allclose(pgevp, torch::zeros_like(in.qg)));
    } END_TEST();
}

void test_graupel_evap_inactive_when_saturated() {
    TEST(test_graupel_evap_inactive_when_saturated) {
        // review13 gap fix: rh_w >= 1 (saturated/super-saturated) → pgevp = 0.
        // Outer gate가 `rh_w < 1`만 허용하므로 rh_w=1.05에선 evap 발생 안 해야 함.
        auto p = default_graupel_evap_params();
        auto in = make_graupel_evap_inputs(/*supcol=*/-5.0, /*rh=*/1.05);
        auto pgevp = graupel_evap_torch(in, p, 60.0);
        assert(torch::allclose(pgevp, torch::zeros_like(in.qg)));
    } END_TEST();
}

void test_graupel_evap_negative_and_capped() {
    TEST(test_graupel_evap_negative_and_capped) {
        auto p = default_graupel_evap_params();
        auto in = make_graupel_evap_inputs(/*supcol=*/-5.0, /*rh=*/0.5);
        auto pgevp = graupel_evap_torch(in, p, 60.0);
        // pgevp ≤ 0 (evap) AND pgevp ≥ -qg/dtcld (capped by available mass)
        assert(torch::all(pgevp <= 1e-15).item<bool>());
        assert(torch::all(pgevp >= -in.qg / 60.0 - 1e-15).item<bool>());
    } END_TEST();
}

void test_graupel_evap_grad_finite() {
    TEST(test_graupel_evap_grad_finite) {
        // qg leaf로 grad 흐르는지 + precg2 path도 함께 확인 (ProgB 결합 보호).
        auto p = default_graupel_evap_params();
        auto in = make_graupel_evap_inputs(/*supcol=*/-5.0, /*rh=*/0.5, /*grad=*/true);
        // precg2도 leaf로 만들어 ProgB → graupel_evap path 검증
        in.precg2 = in.precg2.detach().clone().requires_grad_(true);
        auto pgevp = graupel_evap_torch(in, p, 60.0);
        pgevp.sum().backward();
        assert(in.qg.grad().defined() && torch::isfinite(in.qg.grad()).all().item<bool>());
        assert(in.precg2.grad().defined() && torch::isfinite(in.precg2.grad()).all().item<bool>());
    } END_TEST();
}

// ═══════════════════════════════════════════════════════════════════════════
// C4-S1 shared parity exception (Case C, owner adjudication 2026-07-17):
// piacw must stage π path-conditionally (pi_t), like psacw/pgacw/paacw —
// operational f32 gets Fortran's REAL(4) π, the fp64 DA path keeps double π.
// ═══════════════════════════════════════════════════════════════════════════
namespace {

// same value as cold.cpp's TU-local PI
constexpr double kPI = 3.14159265358979323846;

// Witness inputs: a synthetic straddle cell where the f32-π and f64-π ladders
// round to DIFFERENT f32 bits (found by offline scan; cap non-binding).
// Mixed dtypes mirror the operational path: f32 states/slopes, f64
// rslopemu/n0*, so the chain promotes to f64 exactly as in production.
cold::CloudWaterRimingInputs make_piacw_pi_witness(torch::Dtype state_dt) {
    auto so = torch::TensorOptions().dtype(state_dt);
    auto o64 = torch::TensorOptions().dtype(torch::kFloat64);
    auto sv = [&](double v) { return torch::full({1, 1}, v, so); };
    auto dv = [&](double v) { return torch::full({1, 1}, v, o64); };
    return cold::CloudWaterRimingInputs{
        /*qc=*/sv(1.0e-5), /*nc=*/sv(0.0),
        /*qs=*/sv(0.0), /*qg=*/sv(0.0), /*qi=*/sv(2.0e-4),
        /*den=*/sv(1.0), /*denfac=*/sv(1.1),
        /*n0so=*/dv(1.0), /*n0go=*/dv(1.0), /*n0i=*/dv(1.0), /*n0c=*/dv(1.0),
        /*n0sfac=*/sv(1.0),
        /*avtg=*/sv(0.0), /*g3pbg=*/sv(1.0),
        /*avedia_i=*/sv(1.0e-4),          // >= DI50 = 0.5e-4 → gate open
        /*supcol=*/sv(5.0),
        /*rslope3_s=*/sv(0.0), /*rslopeb_s=*/sv(0.0), /*rslopemu_s=*/dv(1.0),
        /*rslope3_g=*/sv(0.0), /*rslopeb_g=*/sv(0.0), /*rslopemu_g=*/dv(1.0),
        /*rslope3_i=*/sv(2.0e-4), /*rslopeb_i=*/sv(1.8e-4), /*rslopemu_i=*/dv(1.0),
        /*rslopec=*/sv(1.0), /*rslopecmu=*/dv(1.0),
    };
}

// The piacw chain replicated left-to-right in double with a chosen π value
// (the production op order; wilt via f32 raw ratio, squared in f32).
double piacw_ref_chain(const cold::CloudWaterRimingParams& p, double pi_val) {
    const float r3 = 2.0e-4f, rb = 1.8e-4f, qc = 1.0e-5f, qi = 2.0e-4f,
                denfac = 1.1f;
    const double rmu = 1.0, n0i = 1.0;
    double ch = static_cast<double>(r3 * rb);           // f32 first multiply
    ch = ch * rmu;
    ch = ch * pi_val;                                   // ← the op under test
    ch = ch * n0i;
    ch = ch * static_cast<double>(p.avti);
    ch = ch * p.g3pbi;
    ch = ch * 0.25;
    ch = ch * p.eacic;
    float w = qi / qc;
    w = std::fmin(std::fmax(w, 0.0f), 1.0f);
    w = w * w;
    ch = ch * static_cast<double>(w);
    ch = ch * static_cast<double>(qc);
    ch = ch * static_cast<double>(denfac);
    return ch;
}

}  // namespace

void test_cwr_piacw_pi_staging_f32_witness() {
    TEST(test_cwr_piacw_pi_staging_f32_witness) {
        torch::NoGradGuard ng;
        auto p = cold::default_cloud_water_riming_params();
        auto in = make_piacw_pi_witness(torch::kFloat32);
        auto out = cold::cloud_water_riming_torch(in, p, /*dtcld=*/20.0);
        const float got = out.piacw.item<float>();

        const double pi32 = static_cast<double>(static_cast<float>(kPI));
        const float ref32 = static_cast<float>(piacw_ref_chain(p, pi32));
        const float ref64 = static_cast<float>(piacw_ref_chain(p, kPI));
        const float cap = 1.0e-5f / 20.0f;

        uint32_t bg, b32, b64;
        std::memcpy(&bg, &got, 4);
        std::memcpy(&b32, &ref32, 4);
        std::memcpy(&b64, &ref64, 4);
        std::cout << "    piacw got=" << got << " ref(f32-pi)=" << ref32
                  << " ref(f64-pi)=" << ref64 << "\n";
        // the witness genuinely discriminates the two ladders, off-cap:
        assert(b32 != b64);
        assert(ref32 < 0.9f * cap && ref64 < 0.9f * cap);
        // operational f32 must land on the Fortran REAL(4)-π ladder, raw-bit:
        assert(bg == b32);
    } END_TEST();
}

void test_cwr_piacw_pi_staging_fp64_invariance() {
    TEST(test_cwr_piacw_pi_staging_fp64_invariance) {
        auto p = cold::default_cloud_water_riming_params();
        // fp64 DA path: pi_t holds the SAME double π, so the function must be
        // value- and gradient-identical to the raw-scalar-π expression.
        auto in = make_piacw_pi_witness(torch::kFloat64);
        in.qc.requires_grad_(true);
        auto out = cold::cloud_water_riming_torch(in, p, /*dtcld=*/20.0);

        // scalar-π reference expression, same torch ops in f64:
        auto qc_safe = torch::clamp(in.qc, /*min=*/p.qcrmin);
        auto ratio = in.qi / qc_safe;   // fp64 path uses the SAFE ratio (§53n raw is f32-only)
        auto clamped = torch::fmin(torch::fmax(ratio, torch::zeros_like(ratio)),
                                   torch::ones_like(ratio));
        auto wilt = clamped * clamped;
        auto raw = in.rslope3_i * in.rslopeb_i * in.rslopemu_i
                   * kPI * in.n0i * p.avti * p.g3pbi * 0.25 * p.eacic
                   * wilt * in.qc * in.denfac;
        auto ref = torch::minimum(raw.to(in.qc.scalar_type()), in.qc / 20.0);

        assert(torch::equal(out.piacw, ref));
        auto g_fn = torch::autograd::grad({out.piacw.sum()}, {in.qc},
                                          /*grad_outputs=*/{}, /*retain_graph=*/true,
                                          /*create_graph=*/false, /*allow_unused=*/false)[0];
        auto g_ref = torch::autograd::grad({ref.sum()}, {in.qc})[0];
        assert(torch::all(torch::isfinite(g_fn)).item<bool>());
        assert(torch::equal(g_fn, g_ref));
    } END_TEST();
}

int main() {
    std::cout << "KDM6AD-k libtorch cold tests\n";
    test_ice_accretion_params_finite_and_positive();
    test_ice_accretion_inactive_below_thresholds();
    test_ice_accretion_grad_finite();
    test_isg_params_finite();
    test_isg_inactive_when_qi_low();
    test_isg_eacgi_temperature_direction();
    test_isg_grad_finite();
    test_na_inactive_when_warm();
    test_na_capped_by_ni_per_dt();
    test_na_grad_finite();
    test_cwr_inactive_when_qc_low();
    test_cwr_piacw_pk97_di50_threshold();
    test_cwr_paacw_weighted_average();
    test_cwr_grad_finite();
    test_cwr_piacw_pi_staging_f32_witness();
    test_cwr_piacw_pi_staging_fp64_invariance();
    test_rsgc_pracs_zero_when_warm();
    test_rsgc_nracs_always_zero();
    test_rsgc_grad_finite();
    test_hm_inactive_outside_temperature_band();
    test_hm_active_at_peak();
    test_hm_paacw_adj_consistency();
    test_hm_grad_finite();
    test_icenuc_inactive_when_warm();
    test_icenuc_no_nucleation_when_nci_high();
    test_icenuc_grad_finite();
    test_depsub_inactive_when_warm();
    test_depsub_deposition_when_supersat();
    test_depsub_grad_finite();
    test_agg_inactive_when_warm();
    test_agg_psaut_capped();
    test_agg_grad_finite();
    test_snow_evap_inactive_when_cold();
    test_snow_evap_negative_and_capped();
    test_snow_evap_grad_finite();
    test_graupel_evap_inactive_when_cold();
    test_graupel_evap_inactive_when_saturated();
    test_graupel_evap_negative_and_capped();
    test_graupel_evap_grad_finite();
    std::cout << "All cold tests passed.\n";
    return 0;
}
