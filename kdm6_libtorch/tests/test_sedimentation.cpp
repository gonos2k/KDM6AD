#include "kdm6/sedimentation.h"

#include <torch/torch.h>

#include <cassert>
#include <iostream>

using namespace kdm6;
using namespace kdm6::sed;

#define TEST(name) std::cout << "  RUN  " << #name << "\n"; do
#define END_TEST() while(false); std::cout << "  PASS\n"

namespace {

torch::TensorOptions f64() { return torch::TensorOptions().dtype(torch::kFloat64); }

SubstepAdvectionInputs make_adv_inputs(int K, bool grad = false) {
    auto opts = grad ? f64().requires_grad(true) : f64();
    auto plain = f64();
    SubstepAdvectionState state{
        torch::full({1, K}, 1.0e-3, opts),
        torch::full({1, K}, 1.0e6, opts),
        torch::full({1, K}, 5.0e-4, opts),
        torch::full({1, K}, 5.0e-4, opts),
        torch::full({1, K}, 1.0e-6, opts),
    };
    auto fall_zero = torch::zeros({1, K}, plain);
    return SubstepAdvectionInputs{
        state, fall_zero, fall_zero, fall_zero, fall_zero, fall_zero,
        torch::full({1, K}, 1.0e-3, plain),
        torch::full({1, K}, 1.0e-3, plain),
        torch::full({1, K}, 5.0e-4, plain),
        torch::full({1, K}, 8.0e-4, plain),
        torch::full({1, K}, 500.0, plain),
        torch::full({1, K}, 1.1 * 500.0, plain),
    };
}

}  // namespace

void test_normalize_work_basic() {
    TEST(test_normalize_work_basic) {
        auto work = torch::tensor({{2.0, 4.0}}, f64());
        auto delz = torch::tensor({{100.0, 200.0}}, f64());
        auto out = normalize_work_by_delz(work, delz);
        auto expected = torch::tensor({{0.02, 0.02}}, f64());
        assert(torch::allclose(out, expected));
    } END_TEST();
}

void test_substep_advection_state_nonneg() {
    TEST(test_substep_advection_state_nonneg) {
        auto p = default_substep_advection_params();
        auto in = make_adv_inputs(4);
        auto out = substep_advection_torch(in, /*mstep=*/1, /*dtcld=*/60.0, p);
        assert(torch::all(out.state.qr >= 0).item<bool>());
        assert(torch::all(out.state.qs >= 0).item<bool>());
        assert(torch::all(out.state.qg >= 0).item<bool>());
        assert(torch::all(out.state.brs >= 0).item<bool>());
    } END_TEST();
}

void test_substep_advection_grad_finite() {
    TEST(test_substep_advection_grad_finite) {
        auto p = default_substep_advection_params();
        auto in = make_adv_inputs(4, /*grad=*/true);
        auto out = substep_advection_torch(in, /*mstep=*/2, /*dtcld=*/60.0, p);
        auto loss = out.state.qr.sum() + out.state.qs.sum() + out.fall_qr.sum();
        loss.backward();
        assert(in.state.qr.grad().defined()
               && torch::isfinite(in.state.qr.grad()).all().item<bool>());
        assert(in.state.qs.grad().defined()
               && torch::isfinite(in.state.qs.grad()).all().item<bool>());
    } END_TEST();
}

void test_ice_substep_grad_finite() {
    TEST(test_ice_substep_grad_finite) {
        auto p = default_substep_advection_params();
        auto opts = f64().requires_grad(true);
        auto plain = f64();
        IceSubstepState state{
            torch::full({1, 4}, 1.0e-5, opts),
            torch::full({1, 4}, 1.0e5, opts),
        };
        auto fall_zero = torch::zeros({1, 4}, plain);
        IceSubstepInputs in{
            state, fall_zero, fall_zero,
            torch::full({1, 4}, 5.0e-4, plain),
            torch::full({1, 4}, 5.0e-4, plain),
            torch::full({1, 4}, 500.0, plain),
            torch::full({1, 4}, 1.1 * 500.0, plain),
        };
        auto out = ice_substep_advection_torch(in, /*mstep=*/2, /*dtcld=*/60.0, p);
        auto loss = out.state.qi.sum() + out.state.ni.sum()
                  + out.fall_qi.sum() + out.fall_ni.sum();
        loss.backward();
        assert(in.state.qi.grad().defined()
               && torch::isfinite(in.state.qi.grad()).all().item<bool>());
        assert(in.state.ni.grad().defined()
               && torch::isfinite(in.state.ni.grad()).all().item<bool>());
    } END_TEST();
}

void test_surface_accum_decomposition() {
    TEST(test_surface_accum_decomposition) {
        auto fall_qr = torch::tensor({1.0e-3}, f64());
        auto fall_qs = torch::tensor({2.0e-4}, f64());
        auto fall_qg = torch::tensor({5.0e-4}, f64());
        auto fall_qi = torch::tensor({1.0e-4}, f64());
        auto delz = torch::tensor({500.0}, f64());
        auto out = surface_accumulation_torch(fall_qr, fall_qs, fall_qg, fall_qi, delz, 60.0);
        const double factor = 500.0 / constants::DENR * 60.0 * 1000.0;
        auto expected_rain = (fall_qr + fall_qs + fall_qg + fall_qi) * factor;
        assert(torch::allclose(out.rain_increment, expected_rain, 1e-12, 1e-15));
        auto expected_snow = (fall_qs + fall_qi) * factor;
        assert(torch::allclose(out.snow_increment, expected_snow, 1e-12, 1e-15));
        auto expected_graupel = fall_qg * factor;
        assert(torch::allclose(out.graupel_increment, expected_graupel, 1e-12, 1e-15));
    } END_TEST();
}

int main() {
    std::cout << "kdm6_libtorch sedimentation tests\n";
    test_normalize_work_basic();
    test_substep_advection_state_nonneg();
    test_substep_advection_grad_finite();
    test_ice_substep_grad_finite();
    test_surface_accum_decomposition();
    std::cout << "All sedimentation tests passed.\n";
    return 0;
}
