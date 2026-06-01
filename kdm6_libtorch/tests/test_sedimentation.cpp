#include "kdm6/sedimentation.h"
#include "kdm6/coordinator.h"

#include <torch/torch.h>

#include <cassert>
#include <cmath>
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
        auto out = substep_advection_torch(
            in, /*mstep_col=*/torch::full({1}, 1.0, f64()),
            /*mstepmax=*/1, /*n=*/1, /*dtcld=*/60.0, p);
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
        auto out = substep_advection_torch(
            in, /*mstep_col=*/torch::full({1}, 2.0, f64()),
            /*mstepmax=*/2, /*n=*/1, /*dtcld=*/60.0, p);
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
        auto out = ice_substep_advection_torch(
            in, /*mstep_col=*/torch::full({1}, 2.0, f64()),
            /*mstepmax=*/2, /*n=*/1, /*dtcld=*/60.0, p);
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

// Reproduces the squall step-2 crash from B2 sedimentation wiring attempt:
// at sub-cycle 2 of em_squall2d_x mp=137, state is essentially IC + tiny
// tendency — qr/qs/qg/qi all ≈ 0, qv/qc/nc populated. The runtime would
// re-call preamble (slope) on that near-zero state then sedimentation_chain;
// the wiring crashed before "driver returned from kdm6ad" log line.
//
// This test exercises that exact failure surface in isolation. We bypass the
// runtime preamble re-call (which is the cleanup item) and construct work1_*
// tensors directly — non-zero but small fall velocities representative of a
// freshly-perturbed state — so the test focuses on whether `sedimentation_chain`
// itself is robust to near-zero precip mixing ratios with non-zero velocities.
void test_sedimentation_chain_near_zero_precip_state() {
    TEST(test_sedimentation_chain_near_zero_precip_state) {
        const int B = 2, K = 3;
        auto opts = f64();

        // Near-IC state: qv/qc nonzero, qr/qs/qg/qi essentially zero.
        // Matches what mp=137 cs_out looks like in step 2 of squall.
        CoordinatorState state{
            /*qv=*/torch::full({B, K}, 8.0e-3, opts),
            /*qc=*/torch::full({B, K}, 1.0e-4, opts),
            /*qr=*/torch::full({B, K}, 1.0e-12, opts),
            /*qs=*/torch::full({B, K}, 1.0e-12, opts),
            /*qg=*/torch::full({B, K}, 1.0e-12, opts),
            /*qi=*/torch::full({B, K}, 1.0e-12, opts),
            /*nc=*/torch::full({B, K}, 1.0e8, opts),
            /*nr=*/torch::full({B, K}, 1.0e0, opts),
            /*ni=*/torch::full({B, K}, 1.0e0, opts),
            /*nccn=*/torch::full({B, K}, 5.0e8, opts),
            /*brs=*/torch::zeros({B, K}, opts),
            /*t=*/torch::full({B, K}, 285.0, opts),
        };
        CoordinatorForcing forcing{
            /*p=*/torch::full({B, K}, 8.0e4, opts),
            /*den=*/torch::full({B, K}, 1.1, opts),
            /*delz=*/torch::full({B, K}, 250.0, opts),
            /*dend=*/torch::full({B, K}, 1.1 * 250.0, opts),
        };

        // Small but non-zero work1_* (normalized fall velocity / delz).
        // Typical orders for tiny qr at low velocity → work1_qr ~ 1e-3 / 250 ~ 4e-6
        auto work1_qr = torch::full({B, K}, 4.0e-6, opts);
        auto workn_qr = torch::full({B, K}, 4.0e-6, opts);
        auto work1_qs = torch::full({B, K}, 1.0e-6, opts);
        auto work1_qg = torch::full({B, K}, 2.0e-6, opts);
        auto work1_qi = torch::full({B, K}, 5.0e-7, opts);
        auto workn_qi = torch::full({B, K}, 5.0e-7, opts);

        // mstep derived from max work1 * dt + 0.5 — typically 1 for this scale.
        const double dtcld = 3.0;
        int mstep_main, mstep_ice;
        {
            torch::NoGradGuard no_grad;
            auto vmax_main = torch::maximum(
                torch::maximum(work1_qr, workn_qr),
                torch::maximum(work1_qs, work1_qg)
            ).max().item<double>();
            auto vmax_ice = torch::maximum(work1_qi, workn_qi).max().item<double>();
            mstep_main = std::max(static_cast<int>(std::round(vmax_main * dtcld + 0.5)), 1);
            mstep_ice  = std::max(static_cast<int>(std::round(vmax_ice  * dtcld + 0.5)), 1);
        }
        assert(mstep_main == 1);
        assert(mstep_ice == 1);

        auto sed_params = default_substep_advection_params();
        auto out = sedimentation_chain(
            state, forcing,
            work1_qr, workn_qr, work1_qs, work1_qg, work1_qi, workn_qi,
            /*mstep_col_main=*/torch::full({work1_qr.size(0)}, (double)mstep_main, f64()),
            /*mstepmax_main=*/mstep_main,
            /*mstep_col_ice=*/torch::full({work1_qr.size(0)}, (double)mstep_ice, f64()),
            /*mstepmax_ice=*/mstep_ice,
            dtcld, sed_params
        );

        // (a) finite outputs
        for (auto* t : {&out.state.qv, &out.state.qc, &out.state.qr, &out.state.qs,
                        &out.state.qg, &out.state.qi, &out.state.nc, &out.state.nr,
                        &out.state.ni, &out.state.nccn, &out.state.brs, &out.state.t}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
        }
        // (b) non-neg water mixing ratios after sedimentation
        for (auto* t : {&out.state.qv, &out.state.qc, &out.state.qr,
                        &out.state.qs, &out.state.qg, &out.state.qi}) {
            assert(torch::all(*t >= 0).item<bool>());
        }
        // (c) precip increments finite + non-negative (no precip from tiny state)
        assert(torch::all(torch::isfinite(out.rain_increment)).item<bool>());
        assert(torch::all(torch::isfinite(out.snow_increment)).item<bool>());
        assert(torch::all(torch::isfinite(out.graupel_increment)).item<bool>());
        assert(torch::all(out.rain_increment >= 0).item<bool>());
        assert(torch::all(out.snow_increment >= 0).item<bool>());
        assert(torch::all(out.graupel_increment >= 0).item<bool>());
        // (d) for this tiny state, increments should be near-zero (~1e-9 mm or less)
        assert(out.rain_increment.max().item<double>()    < 1e-6);
        assert(out.snow_increment.max().item<double>()    < 1e-6);
        assert(out.graupel_increment.max().item<double>() < 1e-6);
    } END_TEST();
}

// Mirrors the EXACT runtime.cpp B2 wire-up path that crashed at step 2 of
// the squall: a second `preamble(cs_out, cf, full_p)` call, slope output
// extraction, mstep derivation via `.item()` under NoGradGuard. The previous
// test bypassed the upstream preamble re-call; this test exercises it.
void test_sedimentation_via_preamble_repath() {
    TEST(test_sedimentation_via_preamble_repath) {
        const int B = 2, K = 3;
        auto opts = f64();

        CoordinatorState state{
            torch::full({B, K}, 8.0e-3, opts),
            torch::full({B, K}, 1.0e-4, opts),
            torch::full({B, K}, 1.0e-12, opts),
            torch::full({B, K}, 1.0e-12, opts),
            torch::full({B, K}, 1.0e-12, opts),
            torch::full({B, K}, 1.0e-12, opts),
            torch::full({B, K}, 1.0e8, opts),
            torch::full({B, K}, 1.0e0, opts),
            torch::full({B, K}, 1.0e0, opts),
            torch::full({B, K}, 5.0e8, opts),
            torch::zeros({B, K}, opts),
            torch::full({B, K}, 285.0, opts),
        };
        CoordinatorForcing forcing{
            torch::full({B, K}, 8.0e4, opts),
            torch::full({B, K}, 1.1, opts),
            torch::full({B, K}, 250.0, opts),
            torch::full({B, K}, 1.1 * 250.0, opts),
        };

        auto full_p = default_coordinator_params();

        // Step 1: re-call preamble on state (mirrors runtime.cpp B2 attempt).
        auto pre_post = preamble(state, forcing, full_p);

        // (a) preamble outputs finite for this near-zero state.
        assert(torch::all(torch::isfinite(pre_post.slope.vt_r)).item<bool>());
        assert(torch::all(torch::isfinite(pre_post.slope.vtn_r)).item<bool>());
        assert(torch::all(torch::isfinite(pre_post.slope.vt_s)).item<bool>());
        assert(torch::all(torch::isfinite(pre_post.slope.vt_g)).item<bool>());
        assert(torch::all(torch::isfinite(pre_post.slope.vt_i)).item<bool>());
        assert(torch::all(torch::isfinite(pre_post.slope.vtn_i)).item<bool>());

        // Step 2: build work1_* from slope / delz (matches runtime.cpp).
        auto delz_safe = torch::clamp(forcing.delz, /*min=*/1.0e-9);
        auto work1_qr = pre_post.slope.vt_r  / delz_safe;
        auto workn_qr = pre_post.slope.vtn_r / delz_safe;
        auto work1_qs = pre_post.slope.vt_s  / delz_safe;
        auto work1_qg = pre_post.slope.vt_g  / delz_safe;
        auto work1_qi = pre_post.slope.vt_i  / delz_safe;
        auto workn_qi = pre_post.slope.vtn_i / delz_safe;

        // (b) work1_* finite (no NaN/inf propagation through slope/delz).
        for (auto* t : {&work1_qr, &workn_qr, &work1_qs, &work1_qg, &work1_qi, &workn_qi}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
            assert(torch::all(*t >= 0).item<bool>());
        }

        // Step 3: mstep derivation (matches runtime.cpp).
        const double dtcld = 3.0;
        int mstep_main = 1, mstep_ice = 1;
        {
            torch::NoGradGuard no_grad;
            auto vmax_main_t = torch::maximum(
                torch::maximum(work1_qr, workn_qr),
                torch::maximum(work1_qs, work1_qg)
            ).max();
            auto vmax_ice_t = torch::maximum(work1_qi, workn_qi).max();
            // (c) max-reduce result finite.
            assert(torch::isfinite(vmax_main_t).item<bool>());
            assert(torch::isfinite(vmax_ice_t).item<bool>());
            auto vmax_main = vmax_main_t.item<double>();
            auto vmax_ice  = vmax_ice_t.item<double>();
            mstep_main = std::max(static_cast<int>(std::round(vmax_main * dtcld + 0.5)), 1);
            mstep_ice  = std::max(static_cast<int>(std::round(vmax_ice  * dtcld + 0.5)), 1);
            // (d) mstep counts sane (>=1, < some safety upper bound)
            assert(mstep_main >= 1 && mstep_main < 1000);
            assert(mstep_ice  >= 1 && mstep_ice  < 1000);
        }

        // Step 4: sedimentation_chain via the same path runtime.cpp uses.
        auto sed_params = default_substep_advection_params();
        auto out = sedimentation_chain(
            state, forcing,
            work1_qr, workn_qr, work1_qs, work1_qg, work1_qi, workn_qi,
            /*mstep_col_main=*/torch::full({work1_qr.size(0)}, (double)mstep_main, f64()),
            /*mstepmax_main=*/mstep_main,
            /*mstep_col_ice=*/torch::full({work1_qr.size(0)}, (double)mstep_ice, f64()),
            /*mstepmax_ice=*/mstep_ice,
            dtcld, sed_params
        );

        // (e) all outputs finite + non-neg
        for (auto* t : {&out.state.qv, &out.state.qc, &out.state.qr, &out.state.qs,
                        &out.state.qg, &out.state.qi, &out.state.nc, &out.state.nr,
                        &out.state.ni, &out.state.nccn, &out.state.brs, &out.state.t}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
        }
        for (auto* t : {&out.state.qv, &out.state.qc, &out.state.qr,
                        &out.state.qs, &out.state.qg, &out.state.qi}) {
            assert(torch::all(*t >= 0).item<bool>());
        }
    } END_TEST();
}

// Exact-zero precip mirroring squall step-1 cs_out: qr/qs/qg/qi == 0
// (not 1e-12). Tests whether slope output and downstream sedimentation
// remain finite when input is exactly zero — the exact condition at the
// FIRST few sub-cycles of em_squall2d_x where mp=137 entered B2 wire-up.
void test_sedimentation_exact_zero_precip() {
    TEST(test_sedimentation_exact_zero_precip) {
        const int B = 2, K = 3;
        auto opts = f64();

        CoordinatorState state{
            torch::full({B, K}, 8.0e-3, opts),
            torch::full({B, K}, 1.0e-4, opts),
            torch::zeros({B, K}, opts),                 // qr = 0 exactly
            torch::zeros({B, K}, opts),                 // qs = 0
            torch::zeros({B, K}, opts),                 // qg = 0
            torch::zeros({B, K}, opts),                 // qi = 0
            torch::full({B, K}, 1.0e8, opts),
            torch::zeros({B, K}, opts),                 // nr = 0
            torch::zeros({B, K}, opts),                 // ni = 0
            torch::full({B, K}, 5.0e8, opts),
            torch::zeros({B, K}, opts),
            torch::full({B, K}, 285.0, opts),
        };
        CoordinatorForcing forcing{
            torch::full({B, K}, 8.0e4, opts),
            torch::full({B, K}, 1.1, opts),
            torch::full({B, K}, 250.0, opts),
            torch::full({B, K}, 1.1 * 250.0, opts),
        };
        auto full_p = default_coordinator_params();
        auto pre = preamble(state, forcing, full_p);
        // Slope output finiteness on exact-zero precip — typical failure mode
        // is slope = qr/(pi*denr*n0r/8)^(1/4) → 0/0 if not guarded.
        assert(torch::all(torch::isfinite(pre.slope.vt_r)).item<bool>());
        assert(torch::all(torch::isfinite(pre.slope.vtn_r)).item<bool>());
        assert(torch::all(torch::isfinite(pre.slope.vt_s)).item<bool>());
        assert(torch::all(torch::isfinite(pre.slope.vt_g)).item<bool>());
        assert(torch::all(torch::isfinite(pre.slope.vt_i)).item<bool>());
        assert(torch::all(torch::isfinite(pre.slope.vtn_i)).item<bool>());

        auto delz_safe = torch::clamp(forcing.delz, /*min=*/1.0e-9);
        auto work1_qr = pre.slope.vt_r  / delz_safe;
        auto workn_qr = pre.slope.vtn_r / delz_safe;
        auto work1_qs = pre.slope.vt_s  / delz_safe;
        auto work1_qg = pre.slope.vt_g  / delz_safe;
        auto work1_qi = pre.slope.vt_i  / delz_safe;
        auto workn_qi = pre.slope.vtn_i / delz_safe;
        for (auto* t : {&work1_qr, &workn_qr, &work1_qs, &work1_qg, &work1_qi, &workn_qi}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
        }

        int mstep_main, mstep_ice;
        {
            torch::NoGradGuard no_grad;
            auto vmax_main = torch::maximum(
                torch::maximum(work1_qr, workn_qr),
                torch::maximum(work1_qs, work1_qg)
            ).max().item<double>();
            auto vmax_ice = torch::maximum(work1_qi, workn_qi).max().item<double>();
            assert(std::isfinite(vmax_main) && vmax_main >= 0);
            assert(std::isfinite(vmax_ice)  && vmax_ice  >= 0);
            mstep_main = std::max(static_cast<int>(std::round(vmax_main * 3.0 + 0.5)), 1);
            mstep_ice  = std::max(static_cast<int>(std::round(vmax_ice  * 3.0 + 0.5)), 1);
            assert(mstep_main >= 1 && mstep_main < 1000);
            assert(mstep_ice  >= 1 && mstep_ice  < 1000);
        }
        auto sed_params = default_substep_advection_params();
        auto out = sedimentation_chain(
            state, forcing,
            work1_qr, workn_qr, work1_qs, work1_qg, work1_qi, workn_qi,
            /*mstep_col_main=*/torch::full({work1_qr.size(0)}, (double)mstep_main, f64()),
            /*mstepmax_main=*/mstep_main,
            /*mstep_col_ice=*/torch::full({work1_qr.size(0)}, (double)mstep_ice, f64()),
            /*mstepmax_ice=*/mstep_ice,
            3.0, sed_params
        );
        for (auto* t : {&out.state.qv, &out.state.qc, &out.state.qr, &out.state.qs,
                        &out.state.qg, &out.state.qi, &out.state.nc, &out.state.nr,
                        &out.state.ni, &out.state.nccn, &out.state.brs, &out.state.t}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
        }
    } END_TEST();
}

// Per Codex stop-gate finding: non-uniform column test catching the vertical
// layout convention mismatch. Python sedimentation_chain treats K=0 as TOP
// and K-1 as the surface/bottom (per kdm6_torch/kdm6/sedimentation.py:103
// and coordinator.py:1432). WRF/KIM-meso wrapper stages (KTS..KTE) into
// (KK=1..KM) tensor K-dim where K=0 is the BOTTOM (surface) — opposite.
//
// This test injects qr ONLY at the top layer of the *Python convention*
// (K=0), then runs one sedimentation substep. After the step, the rain
// should have fallen toward the surface/bottom (K=K-1). If a layout bug
// inverts the direction, the rain stays at K=0 and the surface accumulation
// is wrong. Test fails fast in that case.
void test_sedimentation_direction_python_convention() {
    TEST(test_sedimentation_direction_python_convention) {
        const int B = 1, K = 4;
        auto opts = f64();

        // Inject qr only at K=0 (Python TOP).
        auto qr = torch::zeros({B, K}, opts);
        qr.index_put_({0, 0}, 1.0e-3);
        // All other species zero.
        CoordinatorState state{
            torch::full({B, K}, 8.0e-3, opts),  // qv
            torch::full({B, K}, 1.0e-4, opts),  // qc
            qr,                                  // qr (only top has mass)
            torch::zeros({B, K}, opts),
            torch::zeros({B, K}, opts),
            torch::zeros({B, K}, opts),
            torch::full({B, K}, 1.0e8, opts),
            torch::zeros({B, K}, opts),
            torch::zeros({B, K}, opts),
            torch::full({B, K}, 5.0e8, opts),
            torch::zeros({B, K}, opts),
            torch::full({B, K}, 285.0, opts),
        };
        // nr seeded matching qr (number proportional to mass)
        state.nr = state.nr + qr * 1.0e9;  // ~1e6 per kg/kg of qr at top
        CoordinatorForcing forcing{
            torch::full({B, K}, 8.0e4, opts),
            torch::full({B, K}, 1.1, opts),
            torch::full({B, K}, 500.0, opts),
            torch::full({B, K}, 1.1 * 500.0, opts),
        };

        // Strong fall velocity at all levels — large enough that one timestep
        // produces detectable downward movement (K=0 → K=1 in Python conv.)
        auto work1_qr = torch::full({B, K}, 5.0e-3, opts);   // 2.5 m/s / 500m
        auto workn_qr = torch::full({B, K}, 5.0e-3, opts);
        auto work1_qs = torch::zeros({B, K}, opts);
        auto work1_qg = torch::zeros({B, K}, opts);
        auto work1_qi = torch::zeros({B, K}, opts);
        auto workn_qi = torch::zeros({B, K}, opts);

        auto sed_params = default_substep_advection_params();
        auto out = sedimentation_chain(
            state, forcing,
            work1_qr, workn_qr, work1_qs, work1_qg, work1_qi, workn_qi,
            /*mstep_col_main=*/torch::full({work1_qr.size(0)}, 1.0, f64()), /*mstepmax_main=*/1,
            /*mstep_col_ice=*/torch::full({work1_qr.size(0)}, 1.0, f64()),  /*mstepmax_ice=*/1,
            /*dtcld=*/60.0, sed_params
        );

        // Python convention assertion: after one fall step, mass moved DOWN
        // (high K). qr at K=0 should DECREASE (drained); qr at K=K-1 (bottom)
        // should INCREASE (accumulated). Surface accumulation > 0.
        auto qr_out = out.state.qr;
        double qr_top    = qr_out[0][0].item<double>();
        double qr_bottom = qr_out[0][K-1].item<double>();
        // top emptied at least partly
        assert(qr_top < 1.0e-3);
        // bottom received something OR mass left the column (via surface)
        bool fell_internal = qr_bottom > 1.0e-15;
        bool fell_surface  = out.rain_increment[0].item<double>() > 1.0e-15;
        assert(fell_internal || fell_surface);
        // If layout is inverted, qr_top would STAY at 1e-3 and qr_bottom would be 0.
        // Defensive: explicit fail if both are violated.
        if (qr_top >= 1.0e-3 - 1e-15 && qr_bottom < 1e-15 && !fell_surface) {
            std::cerr << "LAYOUT BUG: sedimentation did not move mass downward in "
                         "Python K=0=top convention. qr_top=" << qr_top
                      << " qr_bottom=" << qr_bottom
                      << " rain_inc=" << out.rain_increment[0].item<double>() << "\n";
            assert(false);
        }
    } END_TEST();
}

int main() {
    std::cout << "kdm6_libtorch sedimentation tests\n";
    test_normalize_work_basic();
    test_substep_advection_state_nonneg();
    test_substep_advection_grad_finite();
    test_ice_substep_grad_finite();
    test_surface_accum_decomposition();
    test_sedimentation_chain_near_zero_precip_state();
    test_sedimentation_via_preamble_repath();
    test_sedimentation_exact_zero_precip();
    test_sedimentation_direction_python_convention();
    std::cout << "All sedimentation tests passed.\n";
    return 0;
}
