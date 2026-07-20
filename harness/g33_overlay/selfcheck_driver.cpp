// G3.3 self-check driver (§5a shadow-fidelity): run ONE instrumented substep
// chain on a DETERMINISTIC fixture under a sealed environment, producing real
// containers for the shadow == actual == offline comparison.
//
// Linked with the OVERLAY objects (their TUs replace the canonical archive
// members), so the dladdr binding resolves THIS executable — the artifact that
// actually contains the instrumented code. One algorithm per invocation, one
// process per run (the fresh-process rule): argv[1] = legacy | conservative.
//
// The fixture is literal, not random: every value chosen to exercise a branch —
// mstep {1,2,2} so n=2 gates column 0 off; work1/workn column 2 is 20x larger
// so the outflow cap BINDS there and stays open elsewhere; dend/delz sit far
// above qcrmin, so floors are inactive (the real-atmosphere policy — a floor
// firing here would be an input error, not physics).
#include "kdm6/sedimentation.h"
#include "kdm6/sedimentation_conservative.h"
#include "g33_op_dump.h"
#include <torch/torch.h>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>

int main(int argc, char** argv) {
    if (argc != 2 || (std::strcmp(argv[1], "legacy") != 0 &&
                      std::strcmp(argv[1], "conservative") != 0)) {
        std::cerr << "usage: selfcheck_driver legacy|conservative\n";
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

    // state (f32, canonical top-first [B,K]) — mixing ratios / number mixing ratio
    auto qr = t32({1.2e-4f, 3.4e-4f, 5.6e-4f, 7.8e-4f,
                   2.1e-4f, 4.3e-4f, 6.5e-4f, 8.7e-4f,
                   1.0e-6f, 2.0e-6f, 3.0e-6f, 4.0e-6f});   // col 2 tiny -> cap binds
    auto nr = t32({1.1e3f, 2.2e3f, 3.3e3f, 4.4e3f,
                   1.5e3f, 2.5e3f, 3.5e3f, 4.5e3f,
                   2.0e1f, 3.0e1f, 4.0e1f, 5.0e1f});
    auto qs = t32({1e-5f, 2e-5f, 3e-5f, 4e-5f,
                   2e-5f, 3e-5f, 4e-5f, 5e-5f,
                   3e-5f, 4e-5f, 5e-5f, 6e-5f});
    auto qg = qs * 0.5f;
    auto brs = qs * 0.25f;

    // E1-normalized fall speeds vt/delz (f64 — the f64-vt chain, §34);
    // column 2 is 20x so the entry cap binds there
    auto w1_qr = t64({1.1e-2, 1.2e-2, 1.3e-2, 1.4e-2,
                      1.5e-2, 1.6e-2, 1.7e-2, 1.8e-2,
                      2.2e-1, 2.4e-1, 2.6e-1, 2.8e-1});
    auto wn_qr = t64({1.0e-2, 1.1e-2, 1.2e-2, 1.3e-2,
                      1.4e-2, 1.5e-2, 1.6e-2, 1.7e-2,
                      2.0e-1, 2.2e-1, 2.4e-1, 2.6e-1});
    auto w1_qs = w1_qr * 0.8;
    auto w1_qg = w1_qr * 0.9;

    auto delz = t32({310.f, 320.f, 330.f, 340.f,
                     410.f, 420.f, 430.f, 440.f,
                     510.f, 520.f, 530.f, 540.f});
    auto dend = t32({1.05f, 1.00f, 0.95f, 0.90f,
                     1.15f, 1.10f, 1.05f, 1.00f,
                     0.85f, 0.80f, 0.75f, 0.70f});

    auto mstep_col = torch::tensor(std::vector<double>{1.0, 2.0, 2.0}, f64);
    const int mstepmax = 2;
    const double dtcld = 20.0;
    const kdm6::sed::SubstepAdvectionParams params{kdm6::constants::QCRMIN};

    auto env = [](const char* k) { const char* v = std::getenv(k); return v ? v : ""; };
    kdm6::g33::ScopedDumpContext gctx(
        /*loop=*/1, env("KDM6_G33_CASE_ID"), env("KDM6_G33_PAIR_ID"), argv[1]);

    kdm6::sed::SubstepAdvectionState state{qr, nr, qs, qg, brs};
    auto z = torch::zeros_like(qr);
    torch::Tensor fall_qr = z, fall_nr = z, fall_qs = z, fall_qg = z, fall_brs = z;

    for (int n = 1; n <= mstepmax; ++n) {
        kdm6::sed::SubstepAdvectionInputs in{
            state, fall_qr, fall_nr, fall_qs, fall_qg, fall_brs,
            w1_qr, wn_qr, w1_qs, w1_qg, delz, dend};
        auto out = conservative
            ? kdm6::sed::substep_advection_conservative(in, mstep_col, mstepmax, n, dtcld, params)
            : kdm6::sed::substep_advection_torch(in, mstep_col, mstepmax, n, dtcld, params);
        state = out.state;
        fall_qr = out.fall_qr; fall_nr = out.fall_nr;
        fall_qs = out.fall_qs; fall_qg = out.fall_qg; fall_brs = out.fall_brs;
    }
    std::cout << "SELFCHECK DRIVER OK (" << argv[1] << ", " << mstepmax
              << " substeps)\n";
    return 0;
}
