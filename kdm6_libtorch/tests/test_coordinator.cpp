// Plain-assert tests for kdm6/coordinator post-update helpers.
// Python kdm6_torch/tests/test_coordinator.py와 1:1 정합되어야 함.
//
#include "kdm6/coordinator.h"
#include "kdm6/fconst.h"
#include "kdm6/constants.h"

#include <torch/torch.h>
#include <cassert>
#include <cmath>
#include <iostream>

using namespace kdm6;

#define TEST(name) std::cout << "  RUN  " << #name << "\n"; do
#define END_TEST() while(false); std::cout << "  PASS\n"

namespace {

torch::TensorOptions f64() {
    return torch::dtype(torch::kFloat64);
}

CoordinatorState make_zero_state(int B, int K) {
    auto opts = f64();
    return CoordinatorState{
        torch::zeros({B, K}, opts),  // qv
        torch::zeros({B, K}, opts),  // qc
        torch::zeros({B, K}, opts),  // qr
        torch::zeros({B, K}, opts),  // qs
        torch::zeros({B, K}, opts),  // qg
        torch::zeros({B, K}, opts),  // qi
        torch::zeros({B, K}, opts),  // nc
        torch::zeros({B, K}, opts),  // nr
        torch::zeros({B, K}, opts),  // ni
        torch::full({B, K}, 1.0e9, opts),  // nccn
        torch::zeros({B, K}, opts),  // brs
        torch::full({B, K}, 280.0, opts),  // t
    };
}

}  // namespace

// ─── apply_threshold_cleanup ────────────────────────────────────────────────

void test_threshold_cleanup_zeros_paired_number() {
    TEST(test_threshold_cleanup_zeros_paired_number) {
        auto opts = f64();
        CoordinatorState s = make_zero_state(1, 1);
        s.qc = torch::full({1, 1}, 1.0e-16, opts);     // < qmin (1e-15)
        s.qr = torch::full({1, 1}, 1.0e-10, opts);     // < QCRMIN (1e-9)
        s.qi = torch::full({1, 1}, 1.0e-16, opts);     // < qmin
        s.nc = torch::full({1, 1}, 1.0e8, opts);
        s.nr = torch::full({1, 1}, 1.0e6, opts);
        s.ni = torch::full({1, 1}, 1.0e6, opts);
        auto out = apply_threshold_cleanup(s);
        assert(out.qc.item<double>() == 0.0);
        assert(out.nc.item<double>() == 0.0);  // paired
        assert(out.qr.item<double>() == 0.0);
        assert(out.nr.item<double>() == 0.0);  // paired
        assert(out.qi.item<double>() == 0.0);
        assert(out.ni.item<double>() == 0.0);  // paired
    } END_TEST();
}

void test_threshold_cleanup_passes_through_above_threshold() {
    TEST(test_threshold_cleanup_passes_through_above_threshold) {
        auto opts = f64();
        CoordinatorState s = make_zero_state(1, 1);
        s.qc = torch::full({1, 1}, 1.0e-3, opts);
        s.nc = torch::full({1, 1}, 1.0e8, opts);
        auto out = apply_threshold_cleanup(s);
        assert(std::abs(out.qc.item<double>() - 1.0e-3) < 1e-15);
        assert(std::abs(out.nc.item<double>() - 1.0e8) < 1e-15);
    } END_TEST();
}

// ─── reclassify_large_ice_to_snow (Picons) ───────────────────────────────────

void test_picons_inactive_when_t_above_zero() {
    TEST(test_picons_inactive_when_t_above_zero) {
        auto opts = f64();
        CoordinatorState s = make_zero_state(1, 1);
        s.qi = torch::full({1, 1}, 1.0e-4, opts);  // significant ice
        s.ni = torch::full({1, 1}, 1.0e3, opts);   // very low → large diameter
        s.t  = torch::full({1, 1}, 280.0, opts);   // > t0c
        auto den = torch::full({1, 1}, 1.1, opts);
        auto out = reclassify_large_ice_to_snow(s, den);
        // T>0°C → mask false → no transfer
        assert(std::abs(out.qi.item<double>() - 1.0e-4) < 1e-15);
        assert(out.qs.item<double>() == 0.0);
    } END_TEST();
}

void test_picons_inactive_when_ni_zero() {
    TEST(test_picons_inactive_when_ni_zero) {
        auto opts = f64();
        CoordinatorState s = make_zero_state(1, 1);
        s.qi = torch::full({1, 1}, 1.0e-4, opts);
        s.ni = torch::full({1, 1}, 0.0, opts);     // ni=0 → ice_active=false
        s.t  = torch::full({1, 1}, 260.0, opts);
        auto den = torch::full({1, 1}, 1.1, opts);
        auto out = reclassify_large_ice_to_snow(s, den);
        // review8#1: ni<=0이면 false-positive Picons 안 걸려야 함
        assert(std::abs(out.qi.item<double>() - 1.0e-4) < 1e-15);
        assert(out.qs.item<double>() == 0.0);
    } END_TEST();
}

// ─── reclassify_small_rain_to_cloud ─────────────────────────────────────────

void test_rain_to_cloud_inactive_when_qr_zero() {
    TEST(test_rain_to_cloud_inactive_when_qr_zero) {
        auto opts = f64();
        CoordinatorState s = make_zero_state(1, 1);
        s.qr = torch::full({1, 1}, 0.0, opts);
        s.nr = torch::full({1, 1}, 1.0e3, opts);
        auto den = torch::full({1, 1}, 1.1, opts);
        auto out = reclassify_small_rain_to_cloud(s, den);
        assert(out.qc.item<double>() == 0.0);
        assert(out.nc.item<double>() == 0.0);
    } END_TEST();
}

void test_rain_to_cloud_fires_for_small_drops() {
    TEST(test_rain_to_cloud_fires_for_small_drops) {
        // audit round-3 regression: the small-drop rain→cloud reclass (Fortran F:2879-2892) MUST be
        // able to fire. The earlier port floored the reclass rain slope at rslopermax, pinning
        // avedia_r ≥ ~82.4μm > di82=82μm → it NEVER fired (dead code vs Fortran F:3490
        // min(1/lamdar,1e-3), no lower floor). Small drops (qr=1e-6, nr=6.36e5 → avedia≈14μm) must
        // move qr→qc + nr→nc; large drops (avedia≫82μm) must NOT.
        auto opts = f64();
        CoordinatorState s = make_zero_state(1, 1);
        s.qr = torch::full({1, 1}, 1.0e-6, opts);
        s.nr = torch::full({1, 1}, 6.36e5, opts);
        auto den = torch::full({1, 1}, 1.0, opts);
        auto out = reclassify_small_rain_to_cloud(s, den);
        assert(out.qr.item<double>() < 1.0e-6);   // qr drained
        assert(out.qc.item<double>() > 0.0);       // → cloud water
        assert(out.nc.item<double>() > 0.0);       // → cloud number
        CoordinatorState s2 = make_zero_state(1, 1);
        s2.qr = torch::full({1, 1}, 5.0e-3, opts);
        s2.nr = torch::full({1, 1}, 1.0e3, opts);
        auto out2 = reclassify_small_rain_to_cloud(s2, den);
        assert(std::abs(out2.qr.item<double>() - 5.0e-3) < 1e-15);  // large drops: NOT reclassified
    } END_TEST();
}

// ─── apply_dsd_number_limiters ──────────────────────────────────────────────

void test_dsd_limiter_clamps_oversized_ni_strong() {
    TEST(test_dsd_limiter_clamps_oversized_ni_strong) {
        // Strong-form regression for pidni = cmi · Γ(4)/Γ(1) = 1570.8.
        // With reciprocal-gamma bug pidni=43.6 → ni_at_max would be 36× off.
        auto opts = f64();
        CoordinatorState s = make_zero_state(1, 1);
        s.qi = torch::full({1, 1}, 1.0e-5, opts);
        s.ni = torch::full({1, 1}, 1.0e12, opts);  // → lamdai > LAMDAIMAX
        s.t  = torch::full({1, 1}, 260.0, opts);
        auto den = torch::full({1, 1}, 1.1, opts);
        auto out = apply_dsd_number_limiters(s, den);

        // Γ-truth: pidni = (π·DENI/6) · Γ(4)/Γ(1) = 261.8 · 6 = 1570.8 — now the
        // f32-stepwise Fortran value (fconst.h; differs ~1e-7 rel from the double
        // form, which this 1e-9 gate would false-fail). The 36×-reciprocal-bug
        // guard is preserved by the magnitude itself.
        const double pidni_expected = fconst::get().pidni;
        const double ni_at_max = 1.1 * 1.0e-5
            * std::pow(constants::LAMDAIMAX, constants::DMI) / pidni_expected;
        const double got = out.ni.item<double>();
        const double rel = std::abs(got - ni_at_max) / ni_at_max;
        assert(rel < 1e-9);
    } END_TEST();
}

void test_dsd_limiter_clamps_oversized_nc_structure() {
    TEST(test_dsd_limiter_clamps_oversized_nc_structure) {
        // pidnc = cmc · Γ(1+DMC/(MUC+1)) = 523.6 · Γ(2) = 523.6 · 1 (Cohard-Pinty).
        // MUC=2 lands on Γ(2)=1 self-reciprocal so 부호 단독은 anchor 못 하지만,
        // Cohard-Pinty *식 구조* 변경은 catch.
        auto opts = f64();
        CoordinatorState s = make_zero_state(1, 1);
        s.qc = torch::full({1, 1}, 1.0e-3, opts);
        s.nc = torch::full({1, 1}, 1.0e12, opts);
        auto den = torch::full({1, 1}, 1.1, opts);
        auto out = apply_dsd_number_limiters(s, den);

        const double pidnc_expected = fconst::get().pidnc;  // f32-stepwise (Γ(2)=1; structure guard preserved)
        const double nc_at_max = 1.1 * 1.0e-3
            * std::pow(constants::LAMDACMAX, constants::DMC) / pidnc_expected;
        const double got = out.nc.item<double>();
        const double rel = std::abs(got - nc_at_max) / nc_at_max;
        assert(rel < 1e-9);
    } END_TEST();
}

void test_dsd_limiter_passes_through_inactive() {
    TEST(test_dsd_limiter_passes_through_inactive) {
        auto opts = f64();
        CoordinatorState s = make_zero_state(1, 1);
        s.nr = torch::full({1, 1}, 1.0e3, opts);   // nr exists but qr=0
        auto den = torch::full({1, 1}, 1.1, opts);
        auto out = apply_dsd_number_limiters(s, den);
        assert(std::abs(out.nr.item<double>() - 1.0e3) < 1e-15);
    } END_TEST();
}

// ─── state_update: zero-rate identity test ─────────────────────────────────
//
// 모든 phase rate가 0이고 state가 모두 양수면 state_update는 nonneg clamp를
// 거쳐 입력 state를 그대로 반환해야 한다. 가장 강력한 baseline regression:
// 모든 부호와 routing이 정확히 dq=0을 만들지 않으면 fail.

namespace {

PreambleCore make_zero_pre(int B, int K) {
    auto opts = f64();
    return PreambleCore{
        torch::full({B, K}, 1004.5, opts),    // cpm (cpd, no qv weighting)
        torch::full({B, K}, 2.5e6, opts),     // xl (latent heat of vaporization)
        torch::full({B, K}, -10.0, opts),     // supcol < 0 → warm
        torch::full({B, K}, 500.0, opts),     // rhox
    };
}

WarmPhaseOutputs make_zero_warm(int B, int K) {
    auto z = torch::zeros({B, K}, f64());
    auto z_bool = torch::zeros({B, K}, torch::dtype(torch::kBool));
    return WarmPhaseOutputs{
        z, z, z, z, z, z,   // praut,nraut,pracw,nracw,nccol,nrcol
        z, z_bool,          // prevp, rain_complete_evap
    };
}

ColdPhaseOutputs make_zero_cold(int B, int K) {
    auto z = torch::zeros({B, K}, f64());
    auto z_bool = torch::zeros({B, K}, torch::dtype(torch::kBool));
    return ColdPhaseOutputs{
        z, z, z, z,                              // C1, C2
        z, z, z, z,                              // C2b
        z, z, z, z, z, z, z, z,                  // C2c
        z, z, z, z, z,                           // C2d
        z, z, z, z,                              // C2e mass
        z, z, z, z,                              // C2e number
        z, z,                                    // C3
        z, z, z, z_bool, z_bool,                 // C4 (ifsat, ice_complete_sublim는 bool)
        z, z,                                    // C5
        z, z,                                    // C6 / C6'
    };
}

MeltFreezePhaseOutputs make_zero_mf(int B, int K) {
    auto z = torch::zeros({B, K}, f64());
    return MeltFreezePhaseOutputs{
        z, z, z, z, z, z, z,     // D1 (psmlt, pgmlt, pimlt_qi, pimlt_ni, sfac_melt, gfac_melt, delta_brs_melt)
        z, z, z,                 // psmlt_capped, pgmlt_capped, delta_brs_capped (round-trip fix)
        z, z,                    // D2
        z, z,                    // D3
        z, z, z,                 // D4
        z, z, z, z,              // D5
    };
}

}  // namespace

void test_state_update_zero_rates_identity() {
    TEST(test_state_update_zero_rates_identity) {
        const int B = 1, K = 2;
        auto opts = f64();
        CoordinatorState s{
            torch::full({B, K}, 8.0e-3, opts),  // qv
            torch::full({B, K}, 5.0e-4, opts),  // qc
            torch::full({B, K}, 1.0e-4, opts),  // qr
            torch::full({B, K}, 5.0e-5, opts),  // qs
            torch::full({B, K}, 1.0e-5, opts),  // qg
            torch::full({B, K}, 1.0e-5, opts),  // qi
            torch::full({B, K}, 1.0e8, opts),   // nc
            torch::full({B, K}, 1.0e5, opts),   // nr
            torch::full({B, K}, 1.0e6, opts),   // ni
            torch::full({B, K}, 1.0e9, opts),   // nccn
            torch::zeros({B, K}, opts),         // brs
            torch::full({B, K}, 270.0, opts),   // t
        };
        auto pre = make_zero_pre(B, K);
        auto warm = make_zero_warm(B, K);
        auto cold = make_zero_cold(B, K);
        auto mf = make_zero_mf(B, K);

        auto out = state_update(s, pre, warm, cold, mf, /*dtcld=*/60.0);
        // 모든 rate=0 + 입력 state 양수 → output state == input state.
        assert(torch::allclose(out.qv, s.qv));
        assert(torch::allclose(out.qc, s.qc));
        assert(torch::allclose(out.qr, s.qr));
        assert(torch::allclose(out.qs, s.qs));
        assert(torch::allclose(out.qg, s.qg));
        assert(torch::allclose(out.qi, s.qi));
        assert(torch::allclose(out.nc, s.nc));
        assert(torch::allclose(out.nr, s.nr));
        assert(torch::allclose(out.ni, s.ni));
        assert(torch::allclose(out.brs, s.brs));
        assert(torch::allclose(out.t, s.t));
    } END_TEST();
}

void test_state_update_pcond_warms_and_moves_qv_to_qc() {
    TEST(test_state_update_pcond_warms_and_moves_qv_to_qc) {
        // Updated contract (Codex stop-gate finding 8, then dead-code removal):
        // the warm-phase pcond/pcact/cloud_complete_evap/ncact outputs were not just
        // deferred — they are now REMOVED from WarmPhaseOutputs entirely, because the
        // single live activation+satadj site is `apply_satadj_step` (it runs AFTER
        // state_update + reclassifications, mirroring module_mp_kdm6.f90:2880-2929).
        // So `state_update`, given only warm RATES (all zero here), structurally cannot
        // apply any warm-phase condensation and must LEAVE qv/qc/t unchanged (modulo
        // cold/mf identities). Condensation's effect is exercised by the separate
        // apply_satadj_step kernel test.
        const int B = 1, K = 1;
        auto opts = f64();
        CoordinatorState s{
            torch::full({B, K}, 8.0e-3, opts),  // qv
            torch::full({B, K}, 1.0e-4, opts),  // qc
            torch::zeros({B, K}, opts),         // qr
            torch::zeros({B, K}, opts),         // qs
            torch::zeros({B, K}, opts),         // qg
            torch::zeros({B, K}, opts),         // qi
            torch::full({B, K}, 1.0e8, opts),   // nc
            torch::zeros({B, K}, opts),         // nr
            torch::zeros({B, K}, opts),         // ni
            torch::full({B, K}, 1.0e9, opts),   // nccn
            torch::zeros({B, K}, opts),         // brs
            torch::full({B, K}, 280.0, opts),   // t (warm, supcol<0)
        };
        auto pre = make_zero_pre(B, K);
        auto warm = make_zero_warm(B, K);
        // (warm-phase pcond removed entirely — activation+satadj is now solely in
        // apply_satadj_step, so state_update can carry no warm-phase condensation term.)
        auto cold = make_zero_cold(B, K);
        auto mf = make_zero_mf(B, K);

        const double dtcld = 60.0;
        auto out = state_update(s, pre, warm, cold, mf, dtcld);
        // pcond no longer applied here → state is identity (modulo any rates).
        assert(std::abs(out.qv.item<double>() - 8.0e-3) < 1e-15);
        assert(std::abs(out.qc.item<double>() - 1.0e-4) < 1e-15);
        assert(std::abs(out.t.item<double>()  - 280.0)  < 1e-9);
    } END_TEST();
}

void test_state_update_does_not_clamp_nccn_to_max() {
    TEST(test_state_update_does_not_clamp_nccn_to_max) {
        // Regression for the nccn-clamp-ordering fix (adversarial-audit cross-tree #1, f5d6ce5):
        // state_update must NOT clamp nccn to NCCN_MAX. Fortran adds the rce addback RAW (F:1795);
        // the [NCCN_MIN,NCCN_MAX] reservoir clamp is deferred to apply_satadj_step, AFTER CCN
        // activation reads the raw nccn (F:2905/3006). Re-inserting a clamp at state_update's
        // return would make activation read a MAX-capped nccn (~9% ncact drift, the divergence
        // from the Python oracle). Feed nccn > NCCN_MAX with all rates zero; the returned nccn must
        // pass through UNCLAMPED (> NCCN_MAX). (Forward-inert end-to-end — rce⊥activation — so this
        // white-box check is the only guard for the clamp-order regression.)
        const int B = 1, K = 1;
        auto opts = f64();
        const double nccn_hi = constants::NCCN_MAX * 1.1;   // 2.2e10 > NCCN_MAX
        CoordinatorState s{
            torch::full({B, K}, 8.0e-3, opts),  torch::full({B, K}, 1.0e-4, opts),
            torch::zeros({B, K}, opts),         torch::zeros({B, K}, opts),
            torch::zeros({B, K}, opts),         torch::zeros({B, K}, opts),
            torch::full({B, K}, 1.0e8, opts),   torch::zeros({B, K}, opts),
            torch::zeros({B, K}, opts),         torch::full({B, K}, nccn_hi, opts),
            torch::zeros({B, K}, opts),         torch::full({B, K}, 280.0, opts),
        };
        auto out = state_update(s, make_zero_pre(B, K), make_zero_warm(B, K),
                                make_zero_cold(B, K), make_zero_mf(B, K), /*dtcld=*/60.0);
        assert(out.nccn.item<double>() > constants::NCCN_MAX);  // unclamped (raw passthrough)
    } END_TEST();
}

// review12#1: single-rate isolation tests. Zero-rate identity catches symmetric
// sign errors but not asymmetric routing — e.g., piacr·delta3 vs piacr·(1-delta3)
// would silently invert which species qr→{qs,qg} flows into.

namespace {

CoordinatorState make_test_state(int B, int K, double qr_v, double qs_v) {
    auto opts = f64();
    return CoordinatorState{
        torch::full({B, K}, 8.0e-3, opts),
        torch::full({B, K}, 1.0e-4, opts),
        torch::full({B, K}, qr_v, opts),
        torch::full({B, K}, qs_v, opts),
        torch::full({B, K}, 1.0e-5, opts),
        torch::full({B, K}, 1.0e-5, opts),
        torch::full({B, K}, 1.0e8, opts),
        torch::full({B, K}, 1.0e5, opts),
        torch::full({B, K}, 1.0e6, opts),
        torch::full({B, K}, 1.0e9, opts),
        torch::zeros({B, K}, opts),
        torch::full({B, K}, 270.0, opts),
    };
}

}  // namespace

void test_state_update_piacr_routes_to_qs_when_qr_small() {
    TEST(test_state_update_piacr_routes_to_qs_when_qr_small) {
        // delta3 = 1 (qr<1e-4) → piacr → qs. dqr -= piacr, dqs += piacr.
        const int B = 1, K = 1;
        auto opts = f64();
        // qr small (5e-5 < 1e-4)
        auto s = make_test_state(B, K, /*qr=*/5.0e-5, /*qs=*/1.0e-5);
        auto pre = make_zero_pre(B, K);
        pre.supcol = torch::full({B, K}, 5.0, opts);  // COLD cell: piacr is cold-only (F:2712/2724); routing is a cold-branch behavior
        auto warm = make_zero_warm(B, K);
        auto cold = make_zero_cold(B, K);
        cold.piacr = torch::full({B, K}, 1.0e-7, opts);
        auto mf = make_zero_mf(B, K);

        const double dtcld = 60.0;
        auto out = state_update(s, pre, warm, cold, mf, dtcld);
        const double dq = 1.0e-7 * dtcld;

        // qr loses piacr, qs gains piacr (delta3=1), qg unchanged.
        assert(std::abs(out.qr.item<double>() - (5.0e-5 - dq)) < 1e-15);
        assert(std::abs(out.qs.item<double>() - (1.0e-5 + dq)) < 1e-15);
        assert(std::abs(out.qg.item<double>() - 1.0e-5) < 1e-15);
    } END_TEST();
}

void test_state_update_piacr_routes_to_qg_when_qr_large() {
    TEST(test_state_update_piacr_routes_to_qg_when_qr_large) {
        // delta3 = 0 (qr ≥ 1e-4) → piacr → qg. Strong asymmetric-routing test.
        const int B = 1, K = 1;
        auto opts = f64();
        auto s = make_test_state(B, K, /*qr=*/5.0e-4, /*qs=*/1.0e-5);
        auto pre = make_zero_pre(B, K);
        pre.supcol = torch::full({B, K}, 5.0, opts);  // COLD cell: piacr is cold-only (F:2712/2729); routing is a cold-branch behavior
        auto warm = make_zero_warm(B, K);
        auto cold = make_zero_cold(B, K);
        cold.piacr = torch::full({B, K}, 1.0e-7, opts);
        auto mf = make_zero_mf(B, K);

        const double dtcld = 60.0;
        auto out = state_update(s, pre, warm, cold, mf, dtcld);
        const double dq = 1.0e-7 * dtcld;

        assert(std::abs(out.qr.item<double>() - (5.0e-4 - dq)) < 1e-15);
        assert(std::abs(out.qg.item<double>() - (1.0e-5 + dq)) < 1e-15);
        assert(std::abs(out.qs.item<double>() - 1.0e-5) < 1e-15);
    } END_TEST();
}

void test_state_update_psacr_adj_delta2_routing() {
    TEST(test_state_update_psacr_adj_delta2_routing) {
        // delta2 = 1 (qr<1e-4 AND qs<1e-4) → psacr → qs.
        const int B = 1, K = 1;
        auto opts = f64();
        auto s = make_test_state(B, K, /*qr=*/5.0e-5, /*qs=*/5.0e-5);
        auto pre = make_zero_pre(B, K);
        pre.supcol = torch::full({B, K}, 5.0, opts);  // COLD cell: psacr is cold-only (F:2724/2729); routing is a cold-branch behavior
        auto warm = make_zero_warm(B, K);
        auto cold = make_zero_cold(B, K);
        cold.psacr_adj = torch::full({B, K}, 1.0e-7, opts);
        auto mf = make_zero_mf(B, K);

        const double dtcld = 60.0;
        auto out = state_update(s, pre, warm, cold, mf, dtcld);
        const double dq = 1.0e-7 * dtcld;

        assert(std::abs(out.qr.item<double>() - (5.0e-5 - dq)) < 1e-15);
        assert(std::abs(out.qs.item<double>() - (5.0e-5 + dq)) < 1e-15);
        assert(std::abs(out.qg.item<double>() - 1.0e-5) < 1e-15);
    } END_TEST();
}

void test_state_update_psmlt_warm_routes_to_qr_only() {
    TEST(test_state_update_psmlt_warm_routes_to_qr_only) {
        // warm cell (supcol<0): psmlt (rate, signed: 음수 = melt) → qs += psmlt,
        // qr -= psmlt·warm_mask. qs/qr가 1:1 trade. cold cell이면 qr 변화 없음.
        const int B = 1, K = 1;
        auto opts = f64();
        auto s = make_test_state(B, K, /*qr=*/1.0e-4, /*qs=*/1.0e-4);
        auto pre = make_zero_pre(B, K);  // supcol = -10 (warm)
        auto warm = make_zero_warm(B, K);
        auto cold = make_zero_cold(B, K);
        auto mf = make_zero_mf(B, K);
        // psmlt < 0 (negative rate = melting). qs loses |psmlt|, qr gains |psmlt|.
        mf.psmlt = torch::full({B, K}, -1.0e-7, opts);

        const double dtcld = 60.0;
        auto out = state_update(s, pre, warm, cold, mf, dtcld);
        const double dq = 1.0e-7 * dtcld;  // |psmlt|·dt

        // qs += psmlt (negative rate → loses)
        assert(std::abs(out.qs.item<double>() - (1.0e-4 - dq)) < 1e-15);
        // qr -= psmlt·warm_mask = qr + |psmlt| (warm_mask=1)
        assert(std::abs(out.qr.item<double>() - (1.0e-4 + dq)) < 1e-15);
    } END_TEST();
}

void test_state_update_d1_melt_t_uses_xlf0() {
    TEST(test_state_update_d1_melt_t_uses_xlf0) {
        // Codex round-2: state_update's D1-melt t-update must use the CONSTANT xlf0
        // (Fortran F:1303/1327/1339), exactly like apply_melt_freeze_inline (round-6) — NOT
        // xls-xl(T). Runtime is shielded (mf5 zeroes D1) but this component path is reachable.
        // At xl=2.476e6, xls=2.85e6 → xls-xl=3.736e5 ≠ xlf0=3.5e5, so the choice is observable.
        const int B = 1, K = 1;
        auto opts = f64();
        const double cpm_v = 1005.0, xl_v = 2.476e6, xls = 2.85e6, psmlt_v = -1.0e-7, dtcld = 60.0, t0 = 283.0;
        CoordinatorState s{
            torch::full({B,K}, 8.0e-3, opts), torch::full({B,K}, 5.0e-4, opts),
            torch::full({B,K}, 1.0e-4, opts), torch::full({B,K}, 1.0e-4, opts),
            torch::full({B,K}, 1.0e-5, opts), torch::full({B,K}, 1.0e-5, opts),
            torch::full({B,K}, 1.0e8, opts),  torch::full({B,K}, 1.0e5, opts),
            torch::full({B,K}, 1.0e6, opts),  torch::full({B,K}, 1.0e9, opts),
            torch::zeros({B,K}, opts),        torch::full({B,K}, t0, opts),
        };
        PreambleCore pre{
            torch::full({B,K}, cpm_v, opts), torch::full({B,K}, xl_v, opts),
            torch::full({B,K}, -10.0, opts), torch::full({B,K}, 500.0, opts),  // supcol<0 → T>T0c (melt)
        };
        auto warm = make_zero_warm(B, K);
        auto cold = make_zero_cold(B, K);
        auto mf = make_zero_mf(B, K);
        mf.psmlt = torch::full({B,K}, psmlt_v, opts);  // melt-only

        auto out = state_update(s, pre, warm, cold, mf, dtcld, xls);
        const double dt_actual = out.t.item<double>() - t0;
        const double dt_xlf0  = dtcld * melt::DEFAULT_XLF / cpm_v * psmlt_v;       // correct (constant)
        const double dt_xlsxl = dtcld * (xls - xl_v)      / cpm_v * psmlt_v;       // buggy (xls-xl)
        // tol 1e-11: out.t-t0 cancels against t0≈283 (~6e-14 fp noise); the buggy xls-xl value
        // differs by ~1.4e-7, so 1e-11 cleanly separates correct (xlf0) from buggy.
        assert(std::abs(dt_actual - dt_xlf0) < 1e-11);          // D1 melt t uses xlf0
        assert(std::abs(dt_xlf0 - dt_xlsxl) > 1e-9);            // guard is meaningful (the two differ)
    } END_TEST();
}

void test_state_update_pinuc_is_amount_not_rate() {
    TEST(test_state_update_pinuc_is_amount_not_rate) {
        // review5#1 단위 정책: D2 pinuc는 amount (이미 dtcld 적용됨).
        // F1e가 dtcld 두 번 곱하면 dtcld² 적용 — 이걸 잡는 단위 회귀.
        const int B = 1, K = 1;
        auto opts = f64();
        auto s = make_test_state(B, K, /*qr=*/0.0, /*qs=*/0.0);
        auto pre = make_zero_pre(B, K);
        // T<0°C로 freezing이 활성. 단 supcol는 PreambleCore 사용; cold 진입 위해 변경.
        pre.supcol = torch::full({B, K}, 10.0, opts);
        auto warm = make_zero_warm(B, K);
        auto cold = make_zero_cold(B, K);
        auto mf = make_zero_mf(B, K);
        // pinuc = 1e-6 (amount, dtcld 이미 곱해진 값) → qc 1e-6 손실, qi 1e-6 증가
        mf.pinuc = torch::full({B, K}, 1.0e-6, opts);

        const double dtcld = 60.0;  // pinuc는 amount이므로 dtcld와 무관해야 함
        auto out = state_update(s, pre, warm, cold, mf, dtcld);
        const double dq = 1.0e-6;  // amount, NOT dtcld·rate

        assert(std::abs(out.qc.item<double>() - (1.0e-4 - dq)) < 1e-15);
        assert(std::abs(out.qi.item<double>() - (1.0e-5 + dq)) < 1e-15);
        // 만약 잘못해서 dtcld 곱하면: dq*dtcld = 6e-5 (qi가 7e-5 됨) — 이 어셔션 fail.
    } END_TEST();
}

// ─── cold_phase orchestration ───────────────────────────────────────────────

namespace {

PreambleCold make_test_pre_cold(int B, int K) {
    auto opts = f64();
    // Build SlopeOutputs with all-positive plausible values. Real path is via
    // slope_kdm6_torch; for orchestration smoke we just need shape-compatible.
    auto rsl = torch::full({B, K}, 5.0e-4, opts);
    auto rsl2 = rsl * rsl;
    auto rsl3 = rsl2 * rsl;
    auto rslmu = torch::full({B, K}, 5.0e-4, opts);  // mu=0/1 → rslope^mu ≈ rslope
    auto rslb = torch::full({B, K}, std::pow(5.0e-4, 0.6), opts);
    auto rsld = rsl3;
    auto vt = torch::full({B, K}, 1.0, opts);
    auto vtn = torch::full({B, K}, 1.5, opts);
    auto n0sfac = torch::full({B, K}, 1.0, opts);

    slope::SlopeOutputs slope_out{
        /*rslope_r=*/rsl, /*rslope_s=*/rsl, /*rslope_g=*/rsl, /*rslope_i=*/rsl,
        /*rslopeb_r=*/rslb, /*rslopeb_s=*/rslb, /*rslopeb_g=*/rslb, /*rslopeb_i=*/rslb,
        /*rslopemu_r=*/rslmu, /*rslopemu_s=*/rslmu, /*rslopemu_g=*/rslmu, /*rslopemu_i=*/rslmu,
        /*rsloped_r=*/rsld, /*rsloped_s=*/rsld, /*rsloped_g=*/rsld, /*rsloped_i=*/rsld,
        /*rslope2_r=*/rsl2, /*rslope2_s=*/rsl2, /*rslope2_g=*/rsl2, /*rslope2_i=*/rsl2,
        /*rslope3_r=*/rsl3, /*rslope3_s=*/rsl3, /*rslope3_g=*/rsl3, /*rslope3_i=*/rsl3,
        /*vt_r=*/vt, /*vt_s=*/vt, /*vt_g=*/vt, /*vt_i=*/vt, /*vt2g=*/vt,
        /*vtn_r=*/vtn, /*vtn_i=*/vtn,
        /*n0sfac_field=*/n0sfac,
    };

    return PreambleCold{
        /*supcol=*/torch::full({B, K}, 10.0, opts),    // T<T0c → cold
        /*supsat=*/torch::full({B, K}, 1.0e-4, opts),
        /*rh_w=*/torch::full({B, K}, 1.05, opts),       // super-saturated wrt water
        /*rh_ice=*/torch::full({B, K}, 1.10, opts),     // super-saturated wrt ice
        /*denfac=*/torch::full({B, K}, 1.0, opts),
        /*work2=*/torch::full({B, K}, 1.5, opts),
        /*rslopec=*/torch::full({B, K}, 1.0e-5, opts),
        /*avtg=*/torch::full({B, K}, 110.0, opts),
        /*g3pbg=*/torch::full({B, K}, 0.5, opts),
        /*precg2=*/torch::full({B, K}, 0.5, opts),
        /*slope=*/slope_out,
    };
}

}  // namespace

void test_cold_phase_runs_finite() {
    TEST(test_cold_phase_runs_finite) {
        // T<T0c (cold) cell: 모든 10 sub-step 활성화될 plausible 입력으로
        // run + finite 출력 sanity. 강한 Fortran-parity는 golden vector가 와야 검증.
        const int B = 1, K = 2;
        auto opts = f64();
        CoordinatorState s{
            torch::full({B, K}, 6.0e-3, opts),  // qv (sub-saturated wrt water in cold)
            torch::full({B, K}, 5.0e-4, opts),
            torch::full({B, K}, 1.0e-4, opts),
            torch::full({B, K}, 1.0e-5, opts),
            torch::full({B, K}, 1.0e-5, opts),
            torch::full({B, K}, 1.0e-5, opts),
            torch::full({B, K}, 1.0e8, opts),
            torch::full({B, K}, 1.0e5, opts),
            torch::full({B, K}, 1.0e6, opts),
            torch::full({B, K}, 1.0e9, opts),
            torch::full({B, K}, 1.0e-9, opts),
            torch::full({B, K}, 263.15, opts),  // -10°C (cold)
        };
        CoordinatorForcing f{
            torch::full({B, K}, 8.0e4, opts),
            torch::full({B, K}, 1.1, opts),
            torch::full({B, K}, 500.0, opts),
            torch::full({B, K}, 550.0, opts),
        };
        auto pre = make_test_pre_cold(B, K);
        auto prevp = torch::zeros({B, K}, opts);
        auto n0i = torch::full({B, K}, 1.0e6, opts);
        auto n0r = torch::full({B, K}, 8.0e6, opts);
        auto n0so = torch::full({B, K}, 2.0e6, opts);
        auto n0go = torch::full({B, K}, 4.0e6, opts);
        auto n0c = torch::full({B, K}, 1.0e8, opts);
        auto rslopecmu = torch::full({B, K}, 1.0e-5, opts);
        auto rslopecd = torch::full({B, K}, 1.0e-15, opts);
        auto avedia_i = torch::full({B, K}, 1.0e-4, opts);
        auto work1_ice = torch::full({B, K}, 1.0e-3, opts);
        auto work1_water = torch::full({B, K}, 1.0e-3, opts);

        auto params = default_cold_phase_params();
        auto out = cold_phase(
            s, f, pre, prevp,
            n0i, n0r, n0so, n0go, n0c,
            rslopecmu, rslopecd,
            avedia_i, work1_ice, work1_water,
            params, /*dtcld=*/60.0
        );

        // 모든 mass/number rate 출력이 finite.
        for (auto* t : {&out.praci, &out.piacr, &out.psaci, &out.pgaci,
                        &out.psacw, &out.pgacw, &out.paacw_adj,
                        &out.pracs, &out.psacr_adj, &out.pgacr_adj,
                        &out.pmulcs, &out.pmulrs, &out.pmulcg, &out.pmulrg,
                        &out.nmulcs, &out.nmulrs, &out.nmulcg, &out.nmulrg,
                        &out.pinud, &out.pidep, &out.psdep, &out.pgdep,
                        &out.psaut, &out.psevp, &out.pgevp}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
        }
        // C6/C6' (warm-only): cold cell이라 0이어야 함.
        assert(torch::allclose(out.psevp, torch::zeros_like(out.psevp)));
        assert(torch::allclose(out.pgevp, torch::zeros_like(out.pgevp)));
    } END_TEST();
}

// ─── kdm62d_one_step chain wrapper ──────────────────────────────────────────

namespace {

CoordinatorAuxDiagnostics make_test_aux(int B, int K) {
    auto opts = f64();
    return CoordinatorAuxDiagnostics{
        torch::full({B, K}, 8.0e6, opts),   // n0r
        torch::full({B, K}, 1.0e6, opts),   // n0i
        torch::full({B, K}, 1.0e8, opts),   // n0c
        torch::full({B, K}, 2.0e6, opts),   // n0so
        torch::full({B, K}, 4.0e6, opts),   // n0go
        torch::full({B, K}, 1.0e-3, opts),  // work1_r
        torch::full({B, K}, 1.0e-3, opts),  // work1_ice
        torch::full({B, K}, 1.0e-3, opts),  // work1_water
        torch::full({B, K}, 8.0e-5, opts),  // qcr
        torch::full({B, K}, 1.0e-4, opts),  // avedia_i
        torch::full({B, K}, 1.0e-5, opts),  // rslopecmu
        torch::full({B, K}, 1.0e-15, opts), // rslopecd
    };
}

}  // namespace

void test_kdm62d_one_step_runs_finite_warm() {
    TEST(test_kdm62d_one_step_runs_finite_warm) {
        // Warm cell: B1-B5 + D1 + D5 active; C-phase + D2/D3/D4 produce zeros.
        // Verifies the full F1 chain runs without numerical issue and the new state
        // remains physically plausible (nonneg + finite).
        const int B = 1, K = 2;
        auto opts = f64();
        CoordinatorState s{
            torch::full({B, K}, 8.0e-3, opts),
            torch::full({B, K}, 5.0e-4, opts),
            torch::full({B, K}, 1.0e-4, opts),
            torch::full({B, K}, 1.0e-5, opts),
            torch::full({B, K}, 1.0e-5, opts),
            torch::full({B, K}, 1.0e-5, opts),
            torch::full({B, K}, 1.0e8, opts),
            torch::full({B, K}, 1.0e5, opts),
            torch::full({B, K}, 1.0e6, opts),
            torch::full({B, K}, 1.0e9, opts),
            torch::full({B, K}, 1.0e-9, opts),
            torch::full({B, K}, 285.0, opts),  // warm
        };
        CoordinatorForcing f{
            torch::full({B, K}, 8.0e4, opts),
            torch::full({B, K}, 1.1, opts),
            torch::full({B, K}, 500.0, opts),
            torch::full({B, K}, 550.0, opts),
        };
        auto aux = make_test_aux(B, K);
        auto sea_mask = torch::ones({B, K}, torch::dtype(torch::kBool));
        auto full_p = default_coordinator_params();
        auto warm_p = default_warm_phase_params();
        auto cold_p = default_cold_phase_params();
        auto mf_p   = default_melt_freeze_phase_params();

        auto new_state = kdm62d_one_step(
            s, f, aux, sea_mask, full_p, warm_p, cold_p, mf_p, /*dtcld=*/60.0
        );

        // Mass species: nonneg + finite.
        for (auto* t : {&new_state.qv, &new_state.qc, &new_state.qr,
                        &new_state.qs, &new_state.qg, &new_state.qi}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
            assert(torch::all(*t >= 0).item<bool>());
        }
        // Number species: nonneg + finite.
        for (auto* t : {&new_state.nc, &new_state.nr, &new_state.ni}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
            assert(torch::all(*t >= 0).item<bool>());
        }
        // brs nonneg + finite.
        assert(torch::all(torch::isfinite(new_state.brs)).item<bool>());
        assert(torch::all(new_state.brs >= 0).item<bool>());
        // T finite (no clamp; physical plausibility checked elsewhere).
        assert(torch::all(torch::isfinite(new_state.t)).item<bool>());
    } END_TEST();
}

void test_kdm62d_one_step_grad_propagates() {
    TEST(test_kdm62d_one_step_grad_propagates) {
        // qv/qc/t leaf → new_state.qv backward → grad finite.
        // 가장 강력한 AD smoke test: 전체 chain (preamble + 3 phase + state_update + 4
        // post-update)을 통과하면서 in-place mutation 또는 .item()이 들어가면 fail.
        const int B = 1, K = 1;
        auto opts = f64().requires_grad(true);
        auto plain = f64();
        auto qv = torch::full({B, K}, 8.0e-3, opts);
        auto qc = torch::full({B, K}, 5.0e-4, opts);
        auto t  = torch::full({B, K}, 285.0, opts);
        CoordinatorState s{
            qv, qc,
            torch::full({B, K}, 1.0e-4, plain),
            torch::full({B, K}, 1.0e-5, plain),
            torch::full({B, K}, 1.0e-5, plain),
            torch::full({B, K}, 1.0e-5, plain),
            torch::full({B, K}, 1.0e8, plain),
            torch::full({B, K}, 1.0e5, plain),
            torch::full({B, K}, 1.0e6, plain),
            torch::full({B, K}, 1.0e9, plain),
            torch::full({B, K}, 1.0e-9, plain),
            t,
        };
        CoordinatorForcing f{
            torch::full({B, K}, 8.0e4, plain),
            torch::full({B, K}, 1.1, plain),
            torch::full({B, K}, 500.0, plain),
            torch::full({B, K}, 550.0, plain),
        };
        auto aux = make_test_aux(B, K);
        auto sea_mask = torch::ones({B, K}, torch::dtype(torch::kBool));
        auto full_p = default_coordinator_params();
        auto warm_p = default_warm_phase_params();
        auto cold_p = default_cold_phase_params();
        auto mf_p   = default_melt_freeze_phase_params();

        auto new_state = kdm62d_one_step(
            s, f, aux, sea_mask, full_p, warm_p, cold_p, mf_p, 60.0
        );
        // Multiple outputs to exercise different branches of the chain.
        auto loss = new_state.qv.sum() + new_state.qc.sum() + new_state.t.sum();
        loss.backward();
        for (auto* leaf : {&qv, &qc, &t}) {
            assert(leaf->grad().defined());
            assert(torch::all(torch::isfinite(leaf->grad())).item<bool>());
        }
    } END_TEST();
}

// ─── sedimentation_chain (NISLFV-PLM) ───────────────────────────────────────

void test_sedimentation_chain_runs_and_accumulates() {
    TEST(test_sedimentation_chain_runs_and_accumulates) {
        // Smoke test: rain at multiple levels, several substeps. Verifies that the chain
        // runs without numerical issue and that surface increments are nonneg + finite.
        const int B = 1, K = 4;
        auto opts = f64();
        CoordinatorState s{
            torch::full({B, K}, 8.0e-3, opts),
            torch::full({B, K}, 5.0e-4, opts),
            torch::full({B, K}, 1.0e-3, opts),  // qr substantial
            torch::full({B, K}, 5.0e-5, opts),  // qs
            torch::full({B, K}, 1.0e-5, opts),  // qg
            torch::full({B, K}, 1.0e-5, opts),  // qi
            torch::full({B, K}, 1.0e8, opts),
            torch::full({B, K}, 1.0e5, opts),
            torch::full({B, K}, 1.0e6, opts),
            torch::full({B, K}, 1.0e9, opts),
            torch::full({B, K}, 1.0e-9, opts),
            torch::full({B, K}, 280.0, opts),
        };
        CoordinatorForcing f{
            torch::full({B, K}, 8.0e4, opts),
            torch::full({B, K}, 1.1, opts),
            torch::full({B, K}, 500.0, opts),
            torch::full({B, K}, 550.0, opts),
        };
        auto work1 = torch::full({B, K}, 1.0e-3, opts);
        auto workn = torch::full({B, K}, 1.0e-3, opts);

        auto params = sed::default_substep_advection_params();
        auto out = sedimentation_chain(
            s, f, work1, workn, work1, work1, work1, workn,
            /*mstep_col_main=*/torch::full({B}, 2.0, opts), /*mstepmax_main=*/2,
            /*mstep_col_ice=*/torch::full({B}, 1.0, opts),  /*mstepmax_ice=*/1,
            /*dtcld=*/60.0, params
        );

        // Updated state finite + nonneg.
        for (auto* t : {&out.state.qr, &out.state.qs, &out.state.qg,
                        &out.state.qi, &out.state.nr, &out.state.ni,
                        &out.state.brs}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
            assert(torch::all(*t >= 0).item<bool>());
        }
        // Pass-through fields unchanged.
        assert(torch::allclose(out.state.qv, s.qv));
        assert(torch::allclose(out.state.qc, s.qc));
        assert(torch::allclose(out.state.t, s.t));
        // Surface increments finite + nonneg (rain expected positive given qr loading).
        for (auto* t : {&out.rain_increment, &out.snow_increment, &out.graupel_increment}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
            assert(torch::all(*t >= 0).item<bool>());
        }
    } END_TEST();
}

// ─── kdm62d_step sub-cycling ────────────────────────────────────────────────

void test_compute_loops_max_basic() {
    TEST(test_compute_loops_max_basic) {
        // delt=60s, dtcldcr=120 → loops_max = max(nint(60/120 + 0.5), 1) = 1.
        assert(compute_loops_max(60.0, 120.0) == 1);
        // delt=300s, dtcldcr=120 → nint(300/120 + 0.5) = nint(3.0) = 3.
        assert(compute_loops_max(300.0, 120.0) == 3);
        // delt=0 (degenerate) → max(0, 1) = 1.
        assert(compute_loops_max(0.0, 120.0) == 1);
    } END_TEST();
}

void test_kdm62d_step_matches_one_step_when_delt_le_dtcldcr() {
    TEST(test_kdm62d_step_matches_one_step_when_delt_le_dtcldcr) {
        // delt=60 <= dtcldcr=120 → loops_max=1 → kdm62d_step ≡ kdm62d_one_step(dtcld=60).
        const int B = 1, K = 1;
        auto opts = f64();
        CoordinatorState s{
            torch::full({B, K}, 8.0e-3, opts),
            torch::full({B, K}, 5.0e-4, opts),
            torch::full({B, K}, 1.0e-4, opts),
            torch::full({B, K}, 1.0e-5, opts),
            torch::full({B, K}, 1.0e-5, opts),
            torch::full({B, K}, 1.0e-5, opts),
            torch::full({B, K}, 1.0e8, opts),
            torch::full({B, K}, 1.0e5, opts),
            torch::full({B, K}, 1.0e6, opts),
            torch::full({B, K}, 1.0e9, opts),
            torch::full({B, K}, 1.0e-9, opts),
            torch::full({B, K}, 285.0, opts),
        };
        CoordinatorForcing f{
            torch::full({B, K}, 8.0e4, opts),
            torch::full({B, K}, 1.1, opts),
            torch::full({B, K}, 500.0, opts),
            torch::full({B, K}, 550.0, opts),
        };
        auto aux = make_test_aux(B, K);
        auto sea_mask = torch::ones({B, K}, torch::dtype(torch::kBool));
        auto full_p = default_coordinator_params();
        auto warm_p = default_warm_phase_params();
        auto cold_p = default_cold_phase_params();
        auto mf_p   = default_melt_freeze_phase_params();

        auto via_step = kdm62d_step(
            s, f, aux, sea_mask, full_p, warm_p, cold_p, mf_p,
            /*delt=*/60.0, /*dtcldcr=*/120.0
        );
        auto via_one = kdm62d_one_step(
            s, f, aux, sea_mask, full_p, warm_p, cold_p, mf_p, /*dtcld=*/60.0
        );
        // Single sub-cycle → identical (modulo float ordering, but deterministic same path).
        assert(torch::allclose(via_step.qv, via_one.qv));
        assert(torch::allclose(via_step.qc, via_one.qc));
        assert(torch::allclose(via_step.t, via_one.t));
    } END_TEST();
}

void test_kdm62d_step_delt_zero_is_noop_and_no_nan() {
    // codex stop-hook regression: delt <= 0 → state 불변, no NaN.
    // Without the early-return guard, dtcld=0 propagates into kdm62d_one_step's
    // `mass/dtcld` divisions and produces NaN.
    const int B = 1, K = 1;
    auto opts = f64();
    CoordinatorState s{
        torch::full({B, K}, 8.0e-3, opts),
        torch::full({B, K}, 5.0e-4, opts),
        torch::full({B, K}, 1.0e-4, opts),
        torch::full({B, K}, 1.0e-5, opts),
        torch::full({B, K}, 1.0e-5, opts),
        torch::full({B, K}, 1.0e-5, opts),
        torch::full({B, K}, 1.0e8, opts),
        torch::full({B, K}, 1.0e5, opts),
        torch::full({B, K}, 1.0e6, opts),
        torch::full({B, K}, 1.0e9, opts),
        torch::full({B, K}, 1.0e-9, opts),
        torch::full({B, K}, 285.0, opts),
    };
    CoordinatorForcing f{
        torch::full({B, K}, 8.0e4, opts),
        torch::full({B, K}, 1.1, opts),
        torch::full({B, K}, 500.0, opts),
        torch::full({B, K}, 550.0, opts),
    };
    auto aux = make_test_aux(B, K);
    auto sea_mask = torch::ones({B, K}, torch::dtype(torch::kBool));
    auto full_p = default_coordinator_params();
    auto warm_p = default_warm_phase_params();
    auto cold_p = default_cold_phase_params();
    auto mf_p   = default_melt_freeze_phase_params();

    TEST(test_kdm62d_step_delt_zero_is_noop_and_no_nan_zero) {
        auto out = kdm62d_step(
            s, f, aux, sea_mask, full_p, warm_p, cold_p, mf_p,
            /*delt=*/0.0, /*dtcldcr=*/120.0
        );
        // No NaN anywhere.
        for (auto* t : {&out.qv, &out.qc, &out.qr, &out.qs, &out.qg, &out.qi,
                        &out.nc, &out.nr, &out.ni, &out.brs, &out.t}) {
            assert(!torch::any(torch::isnan(*t)).item<bool>());
        }
        // State unchanged.
        assert(torch::allclose(out.qv, s.qv));
        assert(torch::allclose(out.qc, s.qc));
        assert(torch::allclose(out.t, s.t));
    } END_TEST();

    TEST(test_kdm62d_step_delt_zero_is_noop_and_no_nan_negative) {
        // Negative delt (degenerate) — also no-op.
        auto out = kdm62d_step(
            s, f, aux, sea_mask, full_p, warm_p, cold_p, mf_p,
            /*delt=*/-60.0, /*dtcldcr=*/120.0
        );
        assert(!torch::any(torch::isnan(out.qv)).item<bool>());
        assert(torch::allclose(out.qv, s.qv));
    } END_TEST();
}

void test_kdm62d_step_sub_cycling_runs() {
    TEST(test_kdm62d_step_sub_cycling_runs) {
        // delt=300 → loops_max=3. Just confirm finite + nonneg after 3 sub-cycles.
        const int B = 1, K = 1;
        auto opts = f64();
        CoordinatorState s{
            torch::full({B, K}, 8.0e-3, opts),
            torch::full({B, K}, 5.0e-4, opts),
            torch::full({B, K}, 1.0e-4, opts),
            torch::full({B, K}, 1.0e-5, opts),
            torch::full({B, K}, 1.0e-5, opts),
            torch::full({B, K}, 1.0e-5, opts),
            torch::full({B, K}, 1.0e8, opts),
            torch::full({B, K}, 1.0e5, opts),
            torch::full({B, K}, 1.0e6, opts),
            torch::full({B, K}, 1.0e9, opts),
            torch::full({B, K}, 1.0e-9, opts),
            torch::full({B, K}, 285.0, opts),
        };
        CoordinatorForcing f{
            torch::full({B, K}, 8.0e4, opts),
            torch::full({B, K}, 1.1, opts),
            torch::full({B, K}, 500.0, opts),
            torch::full({B, K}, 550.0, opts),
        };
        auto aux = make_test_aux(B, K);
        auto sea_mask = torch::ones({B, K}, torch::dtype(torch::kBool));
        auto full_p = default_coordinator_params();
        auto warm_p = default_warm_phase_params();
        auto cold_p = default_cold_phase_params();
        auto mf_p   = default_melt_freeze_phase_params();

        auto out = kdm62d_step(
            s, f, aux, sea_mask, full_p, warm_p, cold_p, mf_p,
            /*delt=*/300.0, /*dtcldcr=*/120.0
        );
        for (auto* t : {&out.qv, &out.qc, &out.qr, &out.qs, &out.qg, &out.qi,
                        &out.nc, &out.nr, &out.ni, &out.brs}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
            assert(torch::all(*t >= 0).item<bool>());
        }
        assert(torch::all(torch::isfinite(out.t)).item<bool>());
    } END_TEST();
}

// ─── preamble orchestration ─────────────────────────────────────────────────

void test_preamble_runs_finite() {
    TEST(test_preamble_runs_finite) {
        // 단일 호출로 thermo + cloud_dsd + ProgB + slope_kdm6 모든 진단 산출.
        // 결과 모든 필드 finite + plausible 범위 sanity.
        const int B = 1, K = 2;
        auto opts = f64();
        CoordinatorState s{
            torch::full({B, K}, 8.0e-3, opts),
            torch::full({B, K}, 5.0e-4, opts),
            torch::full({B, K}, 1.0e-4, opts),
            torch::full({B, K}, 5.0e-5, opts),
            torch::full({B, K}, 1.0e-5, opts),
            torch::full({B, K}, 1.0e-5, opts),
            torch::full({B, K}, 1.0e8, opts),
            torch::full({B, K}, 1.0e5, opts),
            torch::full({B, K}, 1.0e6, opts),
            torch::full({B, K}, 1.0e9, opts),
            torch::full({B, K}, 1.0e-9, opts),  // brs
            torch::full({B, K}, 270.0, opts),
        };
        CoordinatorForcing f{
            torch::full({B, K}, 8.0e4, opts),
            torch::full({B, K}, 1.1, opts),
            torch::full({B, K}, 500.0, opts),
            torch::full({B, K}, 550.0, opts),
        };
        auto params = default_coordinator_params();
        auto pre = preamble(s, f, params);

        // Thermo: 10 fields finite + plausible sign.
        for (auto* t : {&pre.cpm, &pre.xl, &pre.qs1, &pre.qs2, &pre.rh_w, &pre.rh_ice,
                        &pre.denfac, &pre.work2}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
            assert(torch::all(*t > 0).item<bool>());
        }
        // supcol = T0c - T = 273.15 - 270 = 3.15 (cold).
        assert(std::abs(pre.supcol[0][0].item<double>() - 3.15) < 1e-9);
        // supsat can be either sign; just finite.
        assert(torch::all(torch::isfinite(pre.supsat)).item<bool>());

        // Cloud DSD: rslopec/avedia_c/avedia_r/sigma_c/lencon{cr} finite + nonneg.
        for (auto* t : {&pre.rslopec, &pre.avedia_c, &pre.avedia_r, &pre.sigma_c, &pre.lenconcr}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
        }

        // ProgB output struct populated (rhox finite + > 0).
        assert(torch::all(torch::isfinite(pre.progb.rhox)).item<bool>());

        // Slope output struct populated (rslope_r etc.).
        assert(torch::all(torch::isfinite(pre.slope.rslope_r)).item<bool>());
        assert(torch::all(torch::isfinite(pre.slope.n0sfac_field)).item<bool>());
    } END_TEST();
}

void test_preamble_grad_propagates() {
    TEST(test_preamble_grad_propagates) {
        // qv/qc/t leaf → preamble outputs 합 backward → grad finite.
        const int B = 1, K = 1;
        auto opts = f64().requires_grad(true);
        auto plain = f64();
        auto qv = torch::full({B, K}, 8.0e-3, opts);
        auto qc = torch::full({B, K}, 5.0e-4, opts);
        auto t  = torch::full({B, K}, 270.0, opts);
        CoordinatorState s{
            qv, qc,
            torch::full({B, K}, 1.0e-4, plain),
            torch::full({B, K}, 5.0e-5, plain),
            torch::full({B, K}, 1.0e-5, plain),
            torch::full({B, K}, 1.0e-5, plain),
            torch::full({B, K}, 1.0e8, plain),
            torch::full({B, K}, 1.0e5, plain),
            torch::full({B, K}, 1.0e6, plain),
            torch::full({B, K}, 1.0e9, plain),
            torch::full({B, K}, 1.0e-9, plain),
            t,
        };
        CoordinatorForcing f{
            torch::full({B, K}, 8.0e4, plain),
            torch::full({B, K}, 1.1, plain),
            torch::full({B, K}, 500.0, plain),
            torch::full({B, K}, 550.0, plain),
        };
        auto params = default_coordinator_params();
        auto pre = preamble(s, f, params);
        // Mix several outputs so grad flows through different sub-modules.
        auto loss = pre.cpm.sum() + pre.qs1.sum() + pre.rslopec.sum() + pre.slope.rslope_r.sum();
        loss.backward();
        assert(qv.grad().defined() && torch::isfinite(qv.grad()).all().item<bool>());
        assert(qc.grad().defined() && torch::isfinite(qc.grad()).all().item<bool>());
        assert(t.grad().defined() && torch::isfinite(t.grad()).all().item<bool>());
    } END_TEST();
}

// ─── melt_freeze_phase orchestration ────────────────────────────────────────

namespace {

PreambleMf make_test_pre_mf(int B, int K) {
    auto opts = f64();
    auto rsl = torch::full({B, K}, 5.0e-4, opts);
    auto rsl2 = rsl * rsl;
    auto rsl3 = rsl2 * rsl;
    auto rslmu = torch::full({B, K}, 5.0e-4, opts);
    auto rslb = torch::full({B, K}, std::pow(5.0e-4, 0.6), opts);
    auto rsld = rsl3;
    auto vt = torch::full({B, K}, 1.0, opts);
    auto vtn = torch::full({B, K}, 1.5, opts);
    auto n0sfac = torch::full({B, K}, 1.0, opts);

    slope::SlopeOutputs slope_out{
        rsl, rsl, rsl, rsl,
        rslb, rslb, rslb, rslb,
        rslmu, rslmu, rslmu, rslmu,
        rsld, rsld, rsld, rsld,
        rsl2, rsl2, rsl2, rsl2,
        rsl3, rsl3, rsl3, rsl3,
        vt, vt, vt, vt, vt,
        vtn, vtn,
        n0sfac,
    };

    return PreambleMf{
        torch::full({B, K}, -10.0, opts),  // supcol < 0 → warm (D1 active)
        torch::full({B, K}, 1.5, opts),    // work2
        torch::full({B, K}, 1005.0, opts), // cpm (§35 pgmlt sequential-t)
        torch::full({B, K}, 500.0, opts),  // rhox
        torch::full({B, K}, 0.5, opts),    // precg2
        slope_out,
    };
}

ColdPhaseOutputs make_zero_cold_outputs(int B, int K) {
    auto z = torch::zeros({B, K}, f64());
    auto zb = torch::zeros({B, K}, torch::dtype(torch::kBool));
    return ColdPhaseOutputs{
        z, z, z, z,                              // C1, C2
        z, z, z, z,                              // C2b
        z, z, z, z, z, z, z, z,                  // C2c
        z, z, z, z, z,                           // C2d
        z, z, z, z,                              // C2e mass
        z, z, z, z,                              // C2e number
        z, z,                                    // C3
        z, z, z, zb, zb,                         // C4
        z, z,                                    // C5
        z, z,                                    // C6 / C6'
    };
}

}  // namespace

void test_melt_freeze_phase_runs_finite() {
    TEST(test_melt_freeze_phase_runs_finite) {
        // T>T0c warm cell — D1 melting + D5 enhanced melt 활성화. D2/D3/D4는 cold-only.
        const int B = 1, K = 1;
        auto opts = f64();
        CoordinatorState s{
            torch::full({B, K}, 8.0e-3, opts),
            torch::full({B, K}, 5.0e-4, opts),
            torch::full({B, K}, 1.0e-4, opts),
            torch::full({B, K}, 5.0e-5, opts),  // qs
            torch::full({B, K}, 1.0e-5, opts),  // qg
            torch::full({B, K}, 1.0e-5, opts),  // qi
            torch::full({B, K}, 1.0e8, opts),
            torch::full({B, K}, 1.0e5, opts),
            torch::full({B, K}, 1.0e6, opts),
            torch::full({B, K}, 1.0e9, opts),
            torch::zeros({B, K}, opts),
            torch::full({B, K}, 283.15, opts),  // 10°C (warm)
        };
        CoordinatorForcing f{
            torch::full({B, K}, 8.0e4, opts),
            torch::full({B, K}, 1.1, opts),
            torch::full({B, K}, 500.0, opts),
            torch::full({B, K}, 550.0, opts),
        };
        auto pre = make_test_pre_mf(B, K);
        auto cold_out = make_zero_cold_outputs(B, K);
        auto n0c = torch::full({B, K}, 1.0e8, opts);
        auto n0r = torch::full({B, K}, 8.0e6, opts);
        auto n0so = torch::full({B, K}, 2.0e6, opts);
        auto n0go = torch::full({B, K}, 4.0e6, opts);
        auto rslopec = torch::full({B, K}, 1.0e-5, opts);
        auto rslopecmu = torch::full({B, K}, 1.0e-5, opts);
        auto rslopecd = torch::full({B, K}, 1.0e-15, opts);

        auto params = default_melt_freeze_phase_params();
        auto out = melt_freeze_phase(
            s, f, pre, cold_out,
            n0c, n0r, n0so, n0go,
            rslopec, rslopecmu, rslopecd,
            params, /*dtcld=*/60.0
        );

        // 모든 출력 finite + sfac_melt/gfac_melt 새 필드 정의됨.
        for (auto* t : {&out.psmlt, &out.pgmlt, &out.pimlt_qi, &out.pimlt_ni,
                        &out.sfac_melt, &out.gfac_melt, &out.delta_brs_melt,
                        &out.pinuc, &out.ninuc, &out.pfrzdtc, &out.nfrzdtc,
                        &out.pfrzdtr, &out.nfrzdtr, &out.delta_brs_freeze,
                        &out.pseml, &out.nseml, &out.pgeml, &out.ngeml}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
        }
        // T>T0c (warm) → D2/D3/D4 freezing은 모두 0.
        assert(torch::allclose(out.pinuc, torch::zeros_like(out.pinuc)));
        assert(torch::allclose(out.pfrzdtc, torch::zeros_like(out.pfrzdtc)));
        assert(torch::allclose(out.pfrzdtr, torch::zeros_like(out.pfrzdtr)));
    } END_TEST();
}

// ─── warm_phase orchestration ───────────────────────────────────────────────

namespace {

PreambleWarm make_test_pre_warm(int B, int K) {
    auto opts = f64();
    return PreambleWarm{
        /*cpm=*/torch::full({B, K}, 1004.5, opts),
        /*xl=*/torch::full({B, K}, 2.5e6, opts),
        /*qs1=*/torch::full({B, K}, 7.0e-3, opts),
        /*rh_w=*/torch::full({B, K}, 0.95, opts),
        /*supsat=*/torch::full({B, K}, -3.5e-4, opts),  // qv - qs1 < 0 (sub-saturated)
        /*work2=*/torch::full({B, K}, 1.5, opts),
        /*rslopec=*/torch::full({B, K}, 1.0e-5, opts),
        /*avedia_c=*/torch::full({B, K}, 1.5e-5, opts),
        /*avedia_r=*/torch::full({B, K}, 5.0e-4, opts),
        /*lenconcr=*/torch::full({B, K}, 1.0e-3, opts),
        /*rslope_r=*/torch::full({B, K}, 1.0e-4, opts),
        /*rslopeb_r=*/torch::full({B, K}, std::pow(1.0e-4, 0.6), opts),
        /*rslope2_r=*/torch::full({B, K}, 1.0e-8, opts),
        /*rslope3_r=*/torch::full({B, K}, 1.0e-12, opts),
        /*rslopemu_r=*/torch::full({B, K}, 1.0e-4, opts),  // mur=1 → rslope^1 = rslope
    };
}

}  // namespace

void test_warm_phase_runs_finite() {
    TEST(test_warm_phase_runs_finite) {
        // 모든 sub-step이 실행되고 출력 8 필드가 finite한지 sanity check.
        const int B = 1, K = 2;
        auto opts = f64();
        CoordinatorState s{
            torch::full({B, K}, 6.5e-3, opts),  // qv (slightly sub-saturated)
            torch::full({B, K}, 5.0e-4, opts),  // qc
            torch::full({B, K}, 1.0e-4, opts),  // qr
            torch::zeros({B, K}, opts),         // qs
            torch::zeros({B, K}, opts),         // qg
            torch::zeros({B, K}, opts),         // qi
            torch::full({B, K}, 1.0e8, opts),
            torch::full({B, K}, 1.0e5, opts),
            torch::zeros({B, K}, opts),         // ni
            torch::full({B, K}, 1.0e9, opts),   // nccn
            torch::zeros({B, K}, opts),         // brs
            torch::full({B, K}, 285.0, opts),   // t (warm)
        };
        CoordinatorForcing f{
            torch::full({B, K}, 8.0e4, opts),
            torch::full({B, K}, 1.1, opts),
            torch::full({B, K}, 500.0, opts),
            torch::full({B, K}, 550.0, opts),
        };
        auto pre = make_test_pre_warm(B, K);
        auto n0r = torch::full({B, K}, 8.0e6, opts);
        auto work1_r = torch::full({B, K}, 1.0e-3, opts);
        auto qcr = torch::full({B, K}, 8.0e-5, opts);

        auto params = default_warm_phase_params();
        auto out = warm_phase(s, f, pre, n0r, work1_r, qcr, params, /*dtcld=*/60.0);

        // 모든 출력이 finite
        assert(torch::all(torch::isfinite(out.praut)).item<bool>());
        assert(torch::all(torch::isfinite(out.nraut)).item<bool>());
        assert(torch::all(torch::isfinite(out.pracw)).item<bool>());
        assert(torch::all(torch::isfinite(out.nracw)).item<bool>());
        assert(torch::all(torch::isfinite(out.nccol)).item<bool>());
        assert(torch::all(torch::isfinite(out.nrcol)).item<bool>());
        assert(torch::all(torch::isfinite(out.prevp)).item<bool>());
        assert(out.rain_complete_evap.defined());
        // (out.pcond removed — warm phase no longer runs a satadj; condensation finiteness
        // is covered by the apply_satadj_step kernel test.)

        // praut, pracw는 ≥ 0 (qc → qr은 양의 rate)
        assert(torch::all(out.praut >= 0).item<bool>());
        assert(torch::all(out.pracw >= 0).item<bool>());
        // 셀이 sub-saturated (rh<1)이라 prevp ≤ 0 (qr → qv 증발)
        assert(torch::all(out.prevp <= 1e-15).item<bool>());
    } END_TEST();
}

void test_warm_phase_grad_propagates() {
    TEST(test_warm_phase_grad_propagates) {
        // qc/qr에 grad → out.praut + out.pracw + out.prevp backward 흐름 finite
        // (qv는 warm_phase가 더 이상 읽지 않음 — satadj가 apply_satadj_step으로 이동).
        const int B = 1, K = 1;
        auto opts = torch::dtype(torch::kFloat64).requires_grad(true);
        auto qc = torch::full({B, K}, 5.0e-4, opts);
        auto qr = torch::full({B, K}, 1.0e-4, opts);
        auto qv = torch::full({B, K}, 6.5e-3, opts);
        auto t  = torch::full({B, K}, 285.0, opts);
        auto plain = f64();
        CoordinatorState s{
            qv, qc, qr,
            torch::zeros({B, K}, plain), torch::zeros({B, K}, plain), torch::zeros({B, K}, plain),
            torch::full({B, K}, 1.0e8, plain),
            torch::full({B, K}, 1.0e5, plain),
            torch::zeros({B, K}, plain),
            torch::full({B, K}, 1.0e9, plain),
            torch::zeros({B, K}, plain),
            t,
        };
        CoordinatorForcing f{
            torch::full({B, K}, 8.0e4, plain),
            torch::full({B, K}, 1.1, plain),
            torch::full({B, K}, 500.0, plain),
            torch::full({B, K}, 550.0, plain),
        };
        auto pre = make_test_pre_warm(B, K);
        auto n0r = torch::full({B, K}, 8.0e6, plain);
        auto work1_r = torch::full({B, K}, 1.0e-3, plain);
        auto qcr = torch::full({B, K}, 8.0e-5, plain);

        auto params = default_warm_phase_params();
        auto out = warm_phase(s, f, pre, n0r, work1_r, qcr, params, 60.0);
        // After the warm-phase satadj moved to apply_satadj_step, warm_phase reads qc (praut,
        // pracw) and qr (pracw, prevp) but NOT qv — the qv↔qc condensation is now solely in
        // apply_satadj_step. So the live grad paths are qc and qr (qv no longer flows through
        // warm_phase; asserting qv.grad here would be wrong post-removal).
        auto loss = out.praut.sum() + out.pracw.sum() + out.prevp.sum();
        loss.backward();
        assert(qc.grad().defined());
        assert(qr.grad().defined());
        assert(torch::all(torch::isfinite(qc.grad())).item<bool>());
        assert(torch::all(torch::isfinite(qr.grad())).item<bool>());
    } END_TEST();
}

void test_state_update_ice_complete_sublim_zeros_ni() {
    TEST(test_state_update_ice_complete_sublim_zeros_ni) {
        // review3#2: ice_complete_sublim mask가 true인 셀은 ni → 0 강제.
        // ninud, ninuc, nfrzdtc, nmul* 모두 0이라 baseline ni는 그대로지만
        // mask가 multiplicatively 0으로 만든다.
        const int B = 1, K = 1;
        auto opts = f64();
        auto s = make_test_state(B, K, /*qr=*/0.0, /*qs=*/0.0);
        auto pre = make_zero_pre(B, K);
        auto warm = make_zero_warm(B, K);
        auto cold = make_zero_cold(B, K);
        cold.ice_complete_sublim = torch::full({B, K}, true, torch::dtype(torch::kBool));
        auto mf = make_zero_mf(B, K);

        const double dtcld = 60.0;
        auto out = state_update(s, pre, warm, cold, mf, dtcld);
        // mask=true → ni_new = ni_pre * 0 = 0
        assert(out.ni.item<double>() == 0.0);
    } END_TEST();
}


// ─── grad propagation (AD-friendly) ─────────────────────────────────────────

void test_threshold_cleanup_grad_flows() {
    TEST(test_threshold_cleanup_grad_flows) {
        auto opts = torch::dtype(torch::kFloat64).requires_grad(true);
        CoordinatorState s = make_zero_state(1, 2);
        s.qc = torch::full({1, 2}, 1.0e-3, opts);
        s.nc = torch::full({1, 2}, 1.0e8, opts);
        auto out = apply_threshold_cleanup(s);
        out.qc.sum().backward();
        assert(s.qc.grad().defined());
        // 위로 전달되는 gradient 모두 finite.
        auto g = s.qc.grad();
        assert(torch::all(torch::isfinite(g)).item<bool>());
    } END_TEST();
}

// ── F1d2: group conservation limiter trip-correctness ───────────────────────
// Zero-filled phase structs (all fields = z; the compiler enforces the count).
WarmPhaseOutputs make_zero_warm(const torch::Tensor& z) {
    return WarmPhaseOutputs{ z, z, z, z, z, z, z, z };  // 8 (rates only; activation+satadj live in apply_satadj_step)
}
ColdPhaseOutputs make_zero_cold(const torch::Tensor& z) {
    return ColdPhaseOutputs{
        z, z, z, z,        z, z, z, z,        z, z, z, z, z, z, z, z,
        z, z, z, z, z,     z, z, z, z,        z, z, z, z,
        z, z,              z, z, z,           z, z,        z, z,        z, z,  // 40
    };
}
MeltFreezePhaseOutputs make_zero_mf(const torch::Tensor& z) {
    return MeltFreezePhaseOutputs{
        z, z, z, z, z, z, z,   z, z, z,   z, z,   z, z,   z, z, z,   z, z, z, z,          // 21 (+3 capped: psmlt/pgmlt/delta_brs)
    };
}

void test_group_limiter_caps_oversubscribed_ice_mass() {
    TEST(test_group_limiter_caps_oversubscribed_ice_mass) {
        // Trip-correctness: psaut+praci+psaci jointly demand ≫ qi; the ice-mass
        // budget must scale them so total consumption == qi exactly (806× fix).
        auto opts = f64();
        auto z = torch::zeros({1, 1}, opts);
        const double dtcld = 60.0, qi0 = 1.0e-6, big = 1.0e-4;
        auto state = make_zero_state(1, 1);
        state.qi = torch::full({1, 1}, qi0, opts);
        state.qr = torch::full({1, 1}, 1.0e-3, opts);          // delta2=delta3=0
        auto supcol = torch::full({1, 1}, 10.0, opts);         // cold arm (>0)
        auto warm = make_zero_warm(z);
        auto mf = make_zero_mf(z);
        auto cold = make_zero_cold(z);
        auto gopt = torch::dtype(torch::kFloat64).requires_grad(true);
        cold.psaut = torch::full({1, 1}, big, gopt);
        cold.praci = torch::full({1, 1}, big, gopt);
        cold.psaci = torch::full({1, 1}, big, gopt);

        auto scaled = scale_rates_for_conservation(state, supcol, warm, cold, mf, dtcld);
        auto consumed = (scaled.cold.psaut + scaled.cold.praci + scaled.cold.psaci) * dtcld;
        assert(torch::allclose(consumed, state.qi, /*rtol=*/1e-10));

        // factor = qi/source applied uniformly to each sink
        double expect = big * qi0 / (3.0 * big * dtcld);
        assert(torch::allclose(scaled.cold.psaut,
                               torch::full({1, 1}, expect, opts), /*rtol=*/1e-10));

        // autograd flows through the limiter (no graph break)
        scaled.cold.psaut.sum().backward();
        assert(cold.psaut.grad().defined()
               && torch::all(torch::isfinite(cold.psaut.grad())).item<bool>());
    } END_TEST();
}

void test_group_limiter_inactive_on_warm_cell() {
    TEST(test_group_limiter_inactive_on_warm_cell) {
        // A warm cell (supcol<=0) must be untouched by cold (pass-1) budgets.
        auto opts = f64();
        auto z = torch::zeros({1, 1}, opts);
        const double big = 1.0e-4;
        auto state = make_zero_state(1, 1);
        state.qi = torch::full({1, 1}, 1.0e-6, opts);
        state.qr = torch::full({1, 1}, 1.0e-3, opts);
        auto supcol = torch::full({1, 1}, -5.0, opts);         // WARM arm (<=0)
        auto warm = make_zero_warm(z);
        auto mf = make_zero_mf(z);
        auto cold = make_zero_cold(z);
        cold.psaut = torch::full({1, 1}, big, opts);
        cold.praci = torch::full({1, 1}, big, opts);

        auto scaled = scale_rates_for_conservation(state, supcol, warm, cold, mf, 60.0);
        assert(torch::equal(scaled.cold.psaut, cold.psaut));   // cold budget did NOT fire
        assert(torch::equal(scaled.cold.praci, cold.praci));
    } END_TEST();
}

int main() {
    std::cout << "kdm6_libtorch coordinator post-update tests\n";
    test_threshold_cleanup_zeros_paired_number();
    test_threshold_cleanup_passes_through_above_threshold();
    test_picons_inactive_when_t_above_zero();
    test_picons_inactive_when_ni_zero();
    test_rain_to_cloud_inactive_when_qr_zero();
    test_rain_to_cloud_fires_for_small_drops();
    test_dsd_limiter_clamps_oversized_ni_strong();
    test_dsd_limiter_clamps_oversized_nc_structure();
    test_dsd_limiter_passes_through_inactive();
    test_threshold_cleanup_grad_flows();
    test_state_update_zero_rates_identity();
    test_state_update_pcond_warms_and_moves_qv_to_qc();
    test_state_update_does_not_clamp_nccn_to_max();
    test_state_update_piacr_routes_to_qs_when_qr_small();
    test_state_update_piacr_routes_to_qg_when_qr_large();
    test_state_update_psacr_adj_delta2_routing();
    test_state_update_psmlt_warm_routes_to_qr_only();
    test_state_update_d1_melt_t_uses_xlf0();
    test_state_update_pinuc_is_amount_not_rate();
    test_state_update_ice_complete_sublim_zeros_ni();
    test_warm_phase_runs_finite();
    test_warm_phase_grad_propagates();
    test_cold_phase_runs_finite();
    test_melt_freeze_phase_runs_finite();
    test_preamble_runs_finite();
    test_preamble_grad_propagates();
    test_kdm62d_one_step_runs_finite_warm();
    test_kdm62d_one_step_grad_propagates();
    test_compute_loops_max_basic();
    test_kdm62d_step_matches_one_step_when_delt_le_dtcldcr();
    test_kdm62d_step_delt_zero_is_noop_and_no_nan();
    test_kdm62d_step_sub_cycling_runs();
    test_sedimentation_chain_runs_and_accumulates();
    test_group_limiter_caps_oversubscribed_ice_mass();
    test_group_limiter_inactive_on_warm_cell();
    std::cout << "All tests passed.\n";
    return 0;
}
