// Focused G3.3-M surface-causality driver.
//
// Runs the full sedimentation_chain on a deterministic top-first [B,K] fixture
// so the overlay emits the last main-substep fall accumulator and the actual
// L1_surface container.  The companion Python check proves:
//
//   final QR_FALLACC(k=K-1) -> surface.bottom_fall_qr
//   per-species bottom fallout -> left-associated total -> actual increments
//
// One algorithm per fresh process: argv[1] = legacy | conservative.
#include "kdm6/coordinator.h"
#include "kdm6/constants.h"
#include "g33_op_dump.h"

#include <torch/torch.h>

#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>

int main(int argc, char** argv) {
    if (argc != 2 || (std::strcmp(argv[1], "legacy") != 0 &&
                      std::strcmp(argv[1], "conservative") != 0)) {
        std::cerr << "usage: surface_selfcheck_driver legacy|conservative\n";
        return 2;
    }

    const bool conservative = std::strcmp(argv[1], "conservative") == 0;
    torch::NoGradGuard ng;
    const auto f32 = torch::TensorOptions().dtype(torch::kFloat32);
    const auto f64 = torch::TensorOptions().dtype(torch::kFloat64);
    const int64_t B = 3, K = 4;

    auto t32 = [&](std::vector<float> v) {
        return torch::tensor(v, f32).reshape({B, K});
    };
    auto t64 = [&](std::vector<double> v) {
        return torch::tensor(v, f64).reshape({B, K});
    };

    auto qr = t32({1.2e-4f, 3.4e-4f, 5.6e-4f, 7.8e-4f,
                   2.1e-4f, 4.3e-4f, 6.5e-4f, 8.7e-4f,
                   1.0e-6f, 2.0e-6f, 3.0e-6f, 4.0e-6f});
    auto nr = t32({1.1e3f, 2.2e3f, 3.3e3f, 4.4e3f,
                   1.5e3f, 2.5e3f, 3.5e3f, 4.5e3f,
                   2.0e1f, 3.0e1f, 4.0e1f, 5.0e1f});
    auto qs = t32({1.0e-5f, 2.0e-5f, 3.0e-5f, 4.0e-5f,
                   2.0e-5f, 3.0e-5f, 4.0e-5f, 5.0e-5f,
                   3.0e-5f, 4.0e-5f, 5.0e-5f, 6.0e-5f});
    auto qg = qs * 0.5f;
    auto brs = qs * 0.25f;
    auto qi = t32({0.8e-5f, 1.0e-5f, 1.2e-5f, 1.4e-5f,
                   1.0e-5f, 1.2e-5f, 1.4e-5f, 1.6e-5f,
                   1.2e-5f, 1.4e-5f, 1.6e-5f, 1.8e-5f});
    auto ni = t32({7.0e2f, 8.0e2f, 9.0e2f, 1.0e3f,
                   8.0e2f, 9.0e2f, 1.0e3f, 1.1e3f,
                   9.0e2f, 1.0e3f, 1.1e3f, 1.2e3f});

    auto delz = t32({310.f, 320.f, 330.f, 340.f,
                     410.f, 420.f, 430.f, 440.f,
                     510.f, 520.f, 530.f, 540.f});
    auto dend = t32({1.05f, 1.00f, 0.95f, 0.90f,
                     1.15f, 1.10f, 1.05f, 1.00f,
                     0.85f, 0.80f, 0.75f, 0.70f});

    auto w1_qr = t64({1.1e-2, 1.2e-2, 1.3e-2, 1.4e-2,
                      1.5e-2, 1.6e-2, 1.7e-2, 1.8e-2,
                      2.2e-1, 2.4e-1, 2.6e-1, 2.8e-1});
    auto wn_qr = t64({1.0e-2, 1.1e-2, 1.2e-2, 1.3e-2,
                      1.4e-2, 1.5e-2, 1.6e-2, 1.7e-2,
                      2.0e-1, 2.2e-1, 2.4e-1, 2.6e-1});
    auto w1_qs = w1_qr * 0.8;
    auto w1_qg = w1_qr * 0.9;
    auto w1_qi = t64({7.0e-3, 7.5e-3, 8.0e-3, 8.5e-3,
                      8.0e-3, 8.5e-3, 9.0e-3, 9.5e-3,
                      9.0e-3, 9.5e-3, 1.0e-2, 1.05e-2});
    auto wn_qi = w1_qi * 0.9;

    auto z = torch::zeros_like(qr);
    auto t = torch::full_like(qr, 260.0f);
    auto nccn = torch::full_like(qr, 1.0e8f);
    kdm6::CoordinatorState state{
        /*qv=*/z, /*qc=*/z, /*qr=*/qr, /*qs=*/qs, /*qg=*/qg, /*qi=*/qi,
        /*nc=*/z, /*nr=*/nr, /*ni=*/ni, /*nccn=*/nccn, /*brs=*/brs, /*t=*/t,
    };
    kdm6::CoordinatorForcing forcing{
        /*p=*/torch::full_like(qr, 80000.0f),
        /*den=*/dend, /*delz=*/delz, /*dend=*/dend,
    };

    auto mstep_main = torch::tensor(std::vector<double>{1.0, 2.0, 2.0}, f64);
    auto mstep_ice = torch::ones({B}, f64);
    const int mstepmax_main = 2;
    const int mstepmax_ice = 1;
    const double dtcld = 20.0;
    const kdm6::sed::SubstepAdvectionParams params{kdm6::constants::QCRMIN};

    auto env = [](const char* key) {
        const char* value = std::getenv(key);
        return value ? value : "";
    };
    kdm6::g33::ScopedDumpContext gctx(
        /*loop=*/1, env("KDM6_G33_CASE_ID"), env("KDM6_G33_PAIR_ID"), argv[1]);

    const auto variant = conservative
        ? kdm6::PhysicsVariant::ConservativeInterface
        : kdm6::PhysicsVariant::Legacy;
    auto out = kdm6::sedimentation_chain(
        state, forcing,
        w1_qr, wn_qr, w1_qs, w1_qg, w1_qi, wn_qi,
        mstep_main, mstepmax_main, mstep_ice, mstepmax_ice,
        dtcld, params,
        /*reslope_params=*/nullptr, /*progb_ret=*/nullptr, variant);

    std::cout << "SURFACE SELFCHECK DRIVER OK (" << argv[1] << ") rain_sum="
              << out.rain_increment.sum().item<float>() << "\n";
    return 0;
}
