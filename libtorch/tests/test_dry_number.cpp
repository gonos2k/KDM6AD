// Direct C++ S2 boundary check; the public C ABI remains on its old contract.
#include "kdm6/runtime.h"
#include "kdm6/state.h"

#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <iostream>

int main() {
    using namespace kdm6;
    auto mk = [](double value) {
        return torch::full({1, 3}, value, torch::kFloat64);
    };
    State state{
        mk(290.0), mk(0.014), mk(0.001), mk(0.0001), mk(0.0), mk(0.0),
        mk(0.0), mk(1e9), mk(1e8), mk(0.0), mk(1e4), mk(0.0),
    };
    Forcing forcing{mk(1.0), mk(0.97), mk(9e4), mk(500.0)};
    auto params = make_parameters(0);
    auto xland = torch::tensor({2.0}, torch::kFloat64);
    PhysicsOptions physics{};

    auto legacy = kdm6_fn(state, forcing, params, 20.0, xland, 100.0, 10.0, physics);
    auto explicit_legacy = kdm6_fn(state, forcing, params, 20.0, xland, 100.0,
                                   10.0, physics, /*dry_number=*/false);
    for (size_t field = 0; field < 12; ++field)
        assert(torch::equal(*legacy.state_out.fields()[field],
                            *explicit_legacy.state_out.fields()[field]));

    auto dry = kdm6_fn(state, forcing, params, 20.0, xland, 100.0, 10.0,
                       physics, /*dry_number=*/true);
    for (auto field : dry.state_out.fields()) assert(torch::isfinite(*field).all().item<bool>());
    PhysicsOptions conservative{PhysicsVariant::ConservativeInterface};
    auto dry_conservative = kdm6_fn(state, forcing, params, 20.0, xland, 100.0,
                                    10.0, conservative, /*dry_number=*/true);
    for (auto field : dry_conservative.state_out.fields())
        assert(torch::isfinite(*field).all().item<bool>());

    // Independent Python-oracle values for this same three-level dry-number input.
    const double expected_nr[3] = {11313.501157180002, 11313.501157180002,
                                   11013.914633307953};
    for (int k = 0; k < 3; ++k) {
        const double got = dry.state_out.nr[0][k].item<double>();
        assert(std::abs(got - expected_nr[k]) <= 1e-4 * expected_nr[k]);
    }

    State live = state;
    for (auto field : live.fields()) *field = field->clone().detach().requires_grad_(true);
    auto step = kdm6_step(live, forcing, params, 20.0, /*value_only=*/false,
                          xland, 100.0, 10.0, physics, /*dry_number=*/true);
    assert(step.handle);
    State direction = zeros_like_state(live);
    direction.qv = mk(1e-3);
    auto tangent = step.handle->jvp(direction);
    const double h = 1e-4;
    State plus = state, minus = state;
    plus.qv = state.qv + h * direction.qv;
    minus.qv = state.qv - h * direction.qv;
    auto out_plus = kdm6_fn(plus, forcing, params, 20.0, xland, 100.0, 10.0,
                            physics, /*dry_number=*/true);
    auto out_minus = kdm6_fn(minus, forcing, params, 20.0, xland, 100.0, 10.0,
                             physics, /*dry_number=*/true);
    const std::array<std::array<torch::Tensor, 3>, 4> numbers{{
        {tangent.nccn, out_plus.state_out.nccn, out_minus.state_out.nccn},
        {tangent.nc, out_plus.state_out.nc, out_minus.state_out.nc},
        {tangent.ni, out_plus.state_out.ni, out_minus.state_out.ni},
        {tangent.nr, out_plus.state_out.nr, out_minus.state_out.nr},
    }};
    for (const auto& row : numbers) {
        auto fd = (row[1] - row[2]) / (2 * h);
        assert(torch::isfinite(row[0]).all().item<bool>());
        auto error = (row[0] - fd).abs().max().item<double>();
        auto scale = std::max(1.0, row[0].abs().max().item<double>());
        assert(error <= 1e-5 * scale);
    }

    std::cout << "dry-number C++ forward and JVP: pass\n";
}
