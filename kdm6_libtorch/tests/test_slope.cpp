#include "kdm6/slope.h"

#include <torch/torch.h>

#include <cassert>
#include <cmath>
#include <iostream>
#include <utility>
#include <vector>

using namespace kdm6;
using namespace kdm6::slope;

#define TEST(name) std::cout << "  RUN  " << #name << "\n"; do
#define END_TEST() while(false); std::cout << "  PASS\n"

namespace {

SlopeKdm6Inputs base_inputs(bool requires_grad) {
    auto opts = torch::TensorOptions().dtype(torch::kFloat64).requires_grad(requires_grad);
    auto plain = torch::TensorOptions().dtype(torch::kFloat64);

    auto qr = torch::tensor({{2.0e-6, 3.5e-6}}, opts);
    auto qs = torch::tensor({{1.4e-6, 2.8e-6}}, opts);
    auto qg = torch::tensor({{1.8e-6, 2.2e-6}}, opts);
    auto qi = torch::tensor({{1.2e-7, 2.4e-7}}, opts);
    auto nr = torch::tensor({{1.2e6, 8.0e5}}, opts);
    auto ni = torch::tensor({{8.0e4, 1.1e5}}, opts);
    auto den = torch::tensor({{1.1, 0.95}}, plain);
    auto denfac = torch::tensor({{0.98, 1.04}}, plain);
    auto t = torch::tensor({{268.15, 258.15}}, plain);
    auto bvtg = torch::tensor({{0.5316, 0.5299}}, plain);
    auto pidn0g = torch::tensor({{2.5e5, 3.1e5}}, plain);
    auto pvtg = torch::tensor({{95.0, 110.0}}, plain);
    auto params = default_slope_params();
    auto rslopegbmax = torch::pow(torch::full_like(bvtg, params.rslopegmax), bvtg);

    return SlopeKdm6Inputs{
        qr, qs, qg, qi,
        nr, ni,
        den, denfac, t,
        pidn0g, pvtg, bvtg, rslopegbmax
    };
}

std::vector<std::pair<const char*, double>> param_fields(const SlopeParams& p) {
    return {
        {"pidnr", p.pidnr},
        {"pidn0s", p.pidn0s},
        {"pidni", p.pidni},
        {"pvtr", p.pvtr},
        {"pvtrn", p.pvtrn},
        {"pvti", p.pvti},
        {"pvtin", p.pvtin},
        {"pvts", p.pvts},
        {"rslopermax", p.rslopermax},
        {"rslopesmax", p.rslopesmax},
        {"rslopegmax", p.rslopegmax},
        {"rslopeimax", p.rslopeimax},
        {"rsloperbmax", p.rsloperbmax},
        {"rslopesbmax", p.rslopesbmax},
        {"rslopeibmax", p.rslopeibmax},
        {"rslopermmax", p.rslopermmax},
        {"rslopesmmax", p.rslopesmmax},
        {"rslopegmmax", p.rslopegmmax},
        {"rslopeimmax", p.rslopeimmax},
        {"rsloperdmax", p.rsloperdmax},
        {"rslopesdmax", p.rslopesdmax},
        {"rslopegdmax", p.rslopegdmax},
        {"rslopeidmax", p.rslopeidmax},
        {"rsloper2max", p.rsloper2max},
        {"rslopes2max", p.rslopes2max},
        {"rslopeg2max", p.rslopeg2max},
        {"rslopei2max", p.rslopei2max},
        {"rsloper3max", p.rsloper3max},
        {"rslopes3max", p.rslopes3max},
        {"rslopeg3max", p.rslopeg3max},
        {"rslopei3max", p.rslopei3max},
    };
}

std::vector<torch::Tensor> output_tensors(const SlopeOutputs& out) {
    return {
        out.rslope_r, out.rslope_s, out.rslope_g, out.rslope_i,
        out.rslopeb_r, out.rslopeb_s, out.rslopeb_g, out.rslopeb_i,
        out.rslopemu_r, out.rslopemu_s, out.rslopemu_g, out.rslopemu_i,
        out.rsloped_r, out.rsloped_s, out.rsloped_g, out.rsloped_i,
        out.rslope2_r, out.rslope2_s, out.rslope2_g, out.rslope2_i,
        out.rslope3_r, out.rslope3_s, out.rslope3_g, out.rslope3_i,
        out.vt_r, out.vt_s, out.vt_g, out.vt_i,
        out.vtn_r, out.vtn_i,
        out.n0sfac_field
    };
}

}  // namespace

void test_default_slope_params_finite() {
    TEST(test_default_slope_params_finite) {
        auto p = default_slope_params();
        for (const auto& field : param_fields(p)) {
            assert(std::isfinite(field.second));
            assert(field.second > 0.0);
        }
    } END_TEST();
}

void test_n0sfac_clamp() {
    TEST(test_n0sfac_clamp) {
        auto t = torch::tensor({{500.0, 273.15, 153.15, 100.0}}, torch::kFloat64);
        auto fac = n0sfac(compute_supcol(t));
        const double upper = constants::N0SMAX / constants::N0S;

        assert(torch::all(fac >= 1.0).item<bool>());
        assert(torch::all(fac <= upper).item<bool>());
        assert(fac[0][0].item<double>() == 1.0);
        assert(fac[0][1].item<double>() == 1.0);
        assert(fac[0][2].item<double>() == upper);
        assert(fac[0][3].item<double>() == upper);
    } END_TEST();
}

void test_slope_kdm6_branches_to_max() {
    TEST(test_slope_kdm6_branches_to_max) {
        auto p = default_slope_params();
        constexpr int B = 2;
        constexpr int K = 3;
        auto dtype = torch::TensorOptions().dtype(torch::kFloat64);

        auto zeros = torch::zeros({B, K}, dtype);
        auto ones = torch::ones({B, K}, dtype);
        auto t = torch::full({B, K}, 263.15, dtype);
        auto bvtg = torch::full({B, K}, 0.5316, dtype);
        auto rslopegbmax = torch::pow(torch::full({B, K}, p.rslopegmax, dtype), bvtg);
        auto pidn0g = torch::zeros({B, K}, dtype);
        auto pvtg = torch::full({B, K}, 100.0, dtype);

        SlopeKdm6Inputs in{
            zeros, zeros, zeros, zeros,
            zeros, zeros,
            ones, ones, t,
            pidn0g, pvtg, bvtg, rslopegbmax
        };

        auto out = slope_kdm6_torch(in, p);

        assert(torch::allclose(out.rslope_r, torch::full_like(zeros, p.rslopermax)));
        assert(torch::allclose(out.rslope_s, torch::full_like(zeros, p.rslopesmax)));
        assert(torch::allclose(out.rslope_g, torch::full_like(zeros, p.rslopegmax)));
        assert(torch::allclose(out.rslope_i, torch::full_like(zeros, p.rslopeimax)));
        assert(torch::allclose(out.rslopeb_r, torch::full_like(zeros, p.rsloperbmax)));
        assert(torch::allclose(out.rslopeb_s, torch::full_like(zeros, p.rslopesbmax)));
        assert(torch::allclose(out.rslopeb_g, rslopegbmax));
        assert(torch::allclose(out.rslopeb_i, torch::full_like(zeros, p.rslopeibmax)));
        assert(torch::allclose(out.rslopemu_r, torch::full_like(zeros, p.rslopermmax)));
        assert(torch::allclose(out.rslopemu_s, torch::full_like(zeros, p.rslopesmmax)));
        assert(torch::allclose(out.rslopemu_g, torch::full_like(zeros, p.rslopegmmax)));
        assert(torch::allclose(out.rslopemu_i, torch::full_like(zeros, p.rslopeimmax)));
        assert(torch::allclose(out.rsloped_r, torch::full_like(zeros, p.rsloperdmax)));
        assert(torch::allclose(out.rsloped_s, torch::full_like(zeros, p.rslopesdmax)));
        assert(torch::allclose(out.rsloped_g, torch::full_like(zeros, p.rslopegdmax)));
        assert(torch::allclose(out.rsloped_i, torch::full_like(zeros, p.rslopeidmax)));
        assert(torch::allclose(out.rslope2_r, torch::full_like(zeros, p.rsloper2max)));
        assert(torch::allclose(out.rslope2_s, torch::full_like(zeros, p.rslopes2max)));
        assert(torch::allclose(out.rslope2_g, torch::full_like(zeros, p.rslopeg2max)));
        assert(torch::allclose(out.rslope2_i, torch::full_like(zeros, p.rslopei2max)));
        assert(torch::allclose(out.rslope3_r, torch::full_like(zeros, p.rsloper3max)));
        assert(torch::allclose(out.rslope3_s, torch::full_like(zeros, p.rslopes3max)));
        assert(torch::allclose(out.rslope3_g, torch::full_like(zeros, p.rslopeg3max)));
        assert(torch::allclose(out.rslope3_i, torch::full_like(zeros, p.rslopei3max)));
        assert(torch::allclose(out.vt_r, zeros));
        assert(torch::allclose(out.vt_s, zeros));
        assert(torch::allclose(out.vt_g, zeros));
        assert(torch::allclose(out.vt_i, zeros));
        assert(torch::allclose(out.vtn_r, zeros));
        assert(torch::allclose(out.vtn_i, zeros));
    } END_TEST();
}

void test_slope_kdm6_above_threshold_grad() {
    TEST(test_slope_kdm6_above_threshold_grad) {
        auto p = default_slope_params();
        auto in = base_inputs(/*requires_grad=*/true);
        auto out = slope_kdm6_torch(in, p);

        for (const auto& tensor : output_tensors(out)) {
            assert(torch::isfinite(tensor).all().item<bool>());
        }

        auto loss = torch::zeros({}, torch::kFloat64);
        for (const auto& tensor : output_tensors(out)) {
            loss = loss + tensor.sum();
        }
        loss.backward();

        assert(in.qr.grad().defined());
        assert(in.qs.grad().defined());
        assert(in.qg.grad().defined());
        assert(in.qi.grad().defined());
        assert(in.nr.grad().defined());
        assert(in.ni.grad().defined());

        assert(torch::isfinite(in.qr.grad()).all().item<bool>());
        assert(torch::isfinite(in.qs.grad()).all().item<bool>());
        assert(torch::isfinite(in.qg.grad()).all().item<bool>());
        assert(torch::isfinite(in.qi.grad()).all().item<bool>());
        assert(torch::isfinite(in.nr.grad()).all().item<bool>());
        assert(torch::isfinite(in.ni.grad()).all().item<bool>());
    } END_TEST();
}

void test_slope_rain_consistency() {
    TEST(test_slope_rain_consistency) {
        auto p = default_slope_params();
        auto in = base_inputs(/*requires_grad=*/false);
        auto zeros = torch::zeros_like(in.qr);

        SlopeKdm6Inputs rain_only{
            in.qr, zeros, zeros, zeros,
            in.nr, zeros,
            in.den, in.denfac, in.t,
            zeros, torch::zeros_like(in.pvtg), in.bvtg, in.rslopegbmax
        };

        auto multi = slope_kdm6_torch(rain_only, p);
        auto rain = slope_rain_torch(in.qr, in.nr, in.den, in.denfac, in.t, p);

        assert(torch::allclose(rain.rslope, multi.rslope_r, 1e-12, 1e-15));
        assert(torch::allclose(rain.rslopeb, multi.rslopeb_r, 1e-12, 1e-15));
        assert(torch::allclose(rain.rslopemu, multi.rslopemu_r, 1e-12, 1e-15));
        assert(torch::allclose(rain.rsloped, multi.rsloped_r, 1e-12, 1e-15));
        assert(torch::allclose(rain.rslope2, multi.rslope2_r, 1e-12, 1e-15));
        assert(torch::allclose(rain.rslope3, multi.rslope3_r, 1e-12, 1e-15));
        assert(torch::allclose(rain.vt, multi.vt_r, 1e-12, 1e-15));
        assert(torch::allclose(rain.vtn, multi.vtn_r, 1e-12, 1e-15));
    } END_TEST();
}

int main() {
    std::cout << "kdm6_libtorch slope tests\n";
    test_default_slope_params_finite();
    test_n0sfac_clamp();
    test_slope_kdm6_branches_to_max();
    test_slope_kdm6_above_threshold_grad();
    test_slope_rain_consistency();
    std::cout << "All slope tests passed.\n";
    return 0;
}
