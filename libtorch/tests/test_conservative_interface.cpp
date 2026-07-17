//
// conservative-interface-v1 — C3 certification gates
// (docs/FREEZE_LIFT_CONSERVATIVE_INTERFACE_V1.md; oracle reference
// oracle/kdm6/sed_conservative.py; implementation
// src/sedimentation_conservative.cpp).
//
// Extends the C2 minimal gates (test_c_abi.cpp) with the owner's C3 list:
//   C3.1  non-uniform-metric interface identity on the DIRECT substeps
//         (rho*delz mass conversion for qr/qs/qg/brs/qi; delz-only for nr/ni;
//         the rho-only "wrong alternative" must demonstrably FAIL)
//   C3.2  per-column mstep gating/conservation/batch-independence on the
//         direct substeps (main + ice chains)
//   C3.3  dt=300 multi-subcycle per-column closure W_out - W_in + P = O(eps),
//         internal C++ fp64 AND public v2 f32 (kappa recorded + gated);
//         cap-inactive column legacy==conservative pinned BITWISE on both
//         paths (measured; see the gate comments)
//   C3.5  AD gates: fp64 adjoint identity / repeated JVP->JVP->VJP / 3-point
//         FD sweep on the internal options overload; public v2 f32 graph
//         mechanics; kdm6_step_ad_c pinned to Legacy physics
//   C3.6  legacy invariance via an OLD-SIGNATURE caller fixture in a separate
//         translation unit (legacy_signature_caller.cpp)
//
// Conventions:
//  - Direct substep tensors are (B, K) with K index 0 = TOP (chain order).
//  - Full-step State/ABI buffers are WRF-staged: k=0 = SURFACE (runtime flips).
//  - `dend` in this runtime is RHO ALONE (module_mp_kdm6.F:812 dend=den), NOT
//    rho*delz — the substeps multiply by delz explicitly for the interface
//    mass conversion.
//  - rain_increment is the TOTAL surface fallout [mm == kg m^-2]; snow/graupel
//    increments are SUBSETS of it (adding them to a closure double-counts).
//
#include "kdm6/runtime.h"
#include "kdm6/sedimentation_conservative.h"
#include "kdm6/state.h"
#include "kdm6_c_api.h"
#include "legacy_signature_caller.h"

#include <torch/torch.h>

#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <vector>

using namespace kdm6;
using namespace kdm6::sed;

#define TEST(name) std::cout << "  RUN  " << #name << "\n"; do
#define END_TEST() while(false); std::cout << "  PASS\n"

namespace {

torch::TensorOptions f64() { return torch::TensorOptions().dtype(torch::kFloat64); }

double eps_of(torch::Dtype dt) {
    return dt == torch::kFloat64
        ? std::numeric_limits<double>::epsilon()
        : static_cast<double>(std::numeric_limits<float>::epsilon());
}

double item(const torch::Tensor& t, int64_t b, int64_t k) {
    torch::NoGradGuard ng;
    return t.index({b, k}).item<double>();
}

// ── C3.3 / C3.5 fixed columns (k index 0 = SURFACE, WRF staging) ────────────
// col 0: cap-inactive light rain (per-substep fall ratio << 1/2 everywhere).
// col 1: rain-cap-active (heavy rain over thin layers; ratio > 1/2).
// col 2: ice/mixed cap-active with NON-UNIFORM rho/delz (cold, all species).
struct ColumnSpec {
    double th, pii, p;
    std::array<double, 4> rho, delz;
    double qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg;
};

const std::array<ColumnSpec, 3> kClosureCols = {{
    /*col0 cap-inactive*/
    {290.0, 0.97, 9.0e4, {1.0, 1.0, 1.0, 1.0}, {500.0, 500.0, 500.0, 500.0},
     1.0e-3, 0.0, 1.0e-5, 0.0, 0.0, 0.0, 1.0e9, 1.0e8, 0.0, 1.0e5, 0.0},
    /*col1 rain-cap-active*/
    {290.0, 0.97, 9.0e4, {1.0, 1.0, 1.0, 1.0}, {400.0, 400.0, 400.0, 400.0},
     1.0e-3, 0.0, 5.0e-3, 0.0, 0.0, 0.0, 1.0e9, 1.0e8, 0.0, 1.0e4, 0.0},
    /*col2 ice/mixed cap-active, non-uniform metric. Every field STRICTLY
      positive: this column doubles as the C3.5 AD base point, and a field
      sitting exactly ON a clamp boundary (e.g. qc = 0 at the entry
      clamp(qc,0)) is a kink where central FD averages the two one-sided
      slopes and can never match the one-sided AD subgradient.*/
    {282.4, 0.9031, 7.0e4, {1.2, 1.0, 0.8, 0.6}, {700.0, 600.0, 500.0, 300.0},
     1.0e-3, 2.0e-4, 1.0e-3, 1.2e-3, 2.0e-3, 2.0e-3, 1.0e9, 1.0e8, 1.0e5, 1.0e4,
     5.0e-6},
}};

// Build the (B=3, K=4) internal State/Forcing from kClosureCols (fp64).
void mk_closure_state(State& s, Forcing& f, bool requires_grad = false) {
    const int B = 3, K = 4;
    auto o = f64();
    auto fill = [&](double ColumnSpec::* m) {
        auto t = torch::empty({B, K}, o);
        for (int b = 0; b < B; ++b)
            for (int k = 0; k < K; ++k) t.index_put_({b, k}, kClosureCols[b].*m);
        return t;
    };
    auto fill_arr = [&](std::array<double, 4> ColumnSpec::* m) {
        auto t = torch::empty({B, K}, o);
        for (int b = 0; b < B; ++b)
            for (int k = 0; k < K; ++k)
                t.index_put_({b, k}, (kClosureCols[b].*m)[k]);
        return t;
    };
    s.th = fill(&ColumnSpec::th);   s.qv = fill(&ColumnSpec::qv);
    s.qc = fill(&ColumnSpec::qc);   s.qr = fill(&ColumnSpec::qr);
    s.qi = fill(&ColumnSpec::qi);   s.qs = fill(&ColumnSpec::qs);
    s.qg = fill(&ColumnSpec::qg);   s.nccn = fill(&ColumnSpec::nccn);
    s.nc = fill(&ColumnSpec::nc);   s.ni = fill(&ColumnSpec::ni);
    s.nr = fill(&ColumnSpec::nr);   s.bg = fill(&ColumnSpec::bg);
    if (requires_grad) for (auto* p : s.fields()) p->requires_grad_(true);
    f.rho = fill_arr(&ColumnSpec::rho);
    f.pii = fill(&ColumnSpec::pii);
    f.p = fill(&ColumnSpec::p);
    f.delz = fill_arr(&ColumnSpec::delz);
}

// Column water [kg m^-2]: sum_k rho*delz*(qv+qc+qr+qi+qs+qg).
double column_water(const State& s, const Forcing& f, int64_t b) {
    torch::NoGradGuard ng;
    auto w = (f.rho * f.delz *
              (s.qv + s.qc + s.qr + s.qi + s.qs + s.qg)).sum(-1);
    return w.index({b}).item<double>();
}

// Per-field scale-normalized difference: max|a-b| / (max|a| + max|b| + tiny).
double field_rel_diff(const torch::Tensor& a, const torch::Tensor& b, int64_t col) {
    torch::NoGradGuard ng;
    auto ac = a.index({col}).detach();
    auto bc = b.index({col}).detach();
    double num = (ac - bc).abs().max().item<double>();
    double den = ac.abs().max().item<double>() + bc.abs().max().item<double>() + 1e-300;
    return num / den;
}

double max_state_rel_diff(State& a, State& b, int64_t col) {
    auto ap = a.fields();
    auto bp = b.fields();
    double m = 0.0;
    for (size_t i = 0; i < ap.size(); ++i)
        m = std::max(m, field_rel_diff(*ap[i], *bp[i], col));
    return m;
}

// deterministic seeded state helpers (mirrors test_handle_vjp.cpp)
State unit_state(int64_t seed, int64_t B, int64_t K) {
    auto gen = at::detail::createCPUGenerator(seed);
    State s;
    for (auto* p : s.fields())
        *p = torch::randn({B, K}, gen, f64());
    return s;
}

// direction scaled per-field so x + eps*v stays physical
State scaled_direction(const State& ref, int64_t seed, double rel) {
    auto gen = at::detail::createCPUGenerator(seed);
    State s;
    auto sp = s.fields();
    auto rp = const_cast<State&>(ref).fields();
    for (size_t i = 0; i < sp.size(); ++i) {
        double scale = rp[i]->detach().abs().max().item<double>();
        if (scale == 0.0) scale = 1.0;
        *sp[i] = torch::randn(rp[i]->sizes(), gen,
                              rp[i]->options().requires_grad(false)) * rel * scale;
    }
    return s;
}

// ── C ABI helpers (local; the test links kdm6_c for the public-ABI gates) ──
struct FBuf {
    int im, kme, jme;
    std::vector<float> data;
    FBuf(int im_, int kme_, int jme_, float fill = 0.0f)
        : im(im_), kme(kme_), jme(jme_),
          data(static_cast<size_t>(im_) * kme_ * jme_, fill) {}
    float* ptr() { return data.data(); }
    // Fortran (im, kme, jme) column-major element.
    float& at(int i, int k, int j) {
        return data[static_cast<size_t>(i)
                    + static_cast<size_t>(im) * (k + static_cast<size_t>(kme) * j)];
    }
};

struct V2Tile {
    int im, kme, jme;
    // input order: th qv qc qr qi qs qg nccn nc ni nr bg rho pii p delz
    std::vector<FBuf> in;
    V2Tile(int im_, int kme_, int jme_) : im(im_), kme(kme_), jme(jme_) {
        for (int f = 0; f < 16; ++f) in.emplace_back(im_, kme_, jme_, 0.0f);
    }
    // Fill column j from a ColumnSpec (k=0 = surface, same as internal State).
    void fill_col(int j, const ColumnSpec& c) {
        const double* scal[16] = {&c.th, &c.qv, &c.qc, &c.qr, &c.qi, &c.qs,
                                  &c.qg, &c.nccn, &c.nc, &c.ni, &c.nr, &c.bg,
                                  nullptr, &c.pii, &c.p, nullptr};
        for (int k = 0; k < kme; ++k) {
            for (int f = 0; f < 16; ++f) {
                if (f == 12)      in[f].at(0, k, j) = static_cast<float>(c.rho[k]);
                else if (f == 15) in[f].at(0, k, j) = static_cast<float>(c.delz[k]);
                else              in[f].at(0, k, j) = static_cast<float>(*scal[f]);
            }
        }
    }
};

struct V2Run {
    std::vector<FBuf> o;                    // 12 state outputs
    std::vector<float> rain, snow, graup;   // (im*jme,)
    kdm6_handle_t* h = nullptr;
    int rc = -999;
};

V2Run run_v2(V2Tile& t, uint32_t variant, double dt, int value_only) {
    V2Run r;
    for (int f = 0; f < 12; ++f) r.o.emplace_back(t.im, t.kme, t.jme, -9.0f);
    const size_t ncol = static_cast<size_t>(t.im) * t.jme;
    r.rain.assign(ncol, -1.0f);
    r.snow.assign(ncol, -1.0f);
    r.graup.assign(ncol, -1.0f);
    kdm6_step_v2_args a;
    std::memset(&a, 0, sizeof(a));
    a.struct_size = kdm6_step_v2_args_size_c();
    a.abi_version = KDM6_ABI_VERSION;
    a.im = t.im; a.kme = t.kme; a.jme = t.jme; a.dt = dt;
    a.value_only = value_only; a.param_grad_flags = 0;
    const float* ip[16];
    for (int f = 0; f < 16; ++f) ip[f] = t.in[f].ptr();
    a.th = ip[0]; a.qv = ip[1]; a.qc = ip[2]; a.qr = ip[3]; a.qi = ip[4];
    a.qs = ip[5]; a.qg = ip[6]; a.nccn = ip[7]; a.nc = ip[8]; a.ni = ip[9];
    a.nr = ip[10]; a.bg = ip[11];
    a.rho = ip[12]; a.pii = ip[13]; a.p = ip[14]; a.delz = ip[15];
    a.th_out = r.o[0].ptr(); a.qv_out = r.o[1].ptr(); a.qc_out = r.o[2].ptr();
    a.qr_out = r.o[3].ptr(); a.qi_out = r.o[4].ptr(); a.qs_out = r.o[5].ptr();
    a.qg_out = r.o[6].ptr(); a.nccn_out = r.o[7].ptr(); a.nc_out = r.o[8].ptr();
    a.ni_out = r.o[9].ptr(); a.nr_out = r.o[10].ptr(); a.bg_out = r.o[11].ptr();
    a.handle = &r.h;
    a.rain_increment = r.rain.data();
    a.snow_increment = r.snow.data();
    a.graupel_increment = r.graup.data();
    a.physics_variant = variant;
    r.rc = kdm6_step_v2_c(&a);
    return r;
}

}  // namespace

// ═════════════════════════════════════════════════════════════════════════
// C3.1 — non-uniform-metric interface identity (DIRECT substeps)
// ═════════════════════════════════════════════════════════════════════════
//
// Two layers, top rho=0.6/delz=300, bottom rho=1.2/delz=700. The conserved
// transfer is per species (qr/qs/qg/brs and qi):
//     (rho*delz)_top * dq_out_top == (rho*delz)_bottom * dq_in_bottom
// and for numbers (nr/ni) the legacy delz-only measure (NO density factor):
//     delz_top * dN_out_top == delz_bottom * dN_in_bottom.
// The WRONG alternative — converting by rho alone, dq_in = dq_out*(rho_t/rho_b)
// — must FAIL by a factor of delz_t/delz_b (0.43x here), far outside roundoff.
//
// dq_out is reconstructed from the fall accumulator (fall = dq_out*rho/dtcld
// with fall_in = 0); dq_in from the state algebra q_out = q_in - dq_out + dq_in.
// Tolerance: |R| <= 64*eps*(|M_out| + |M_in| + 1) with eps of the dtype
// (fp64 direct + an f32-input case).
namespace {

void c31_case(torch::Dtype dt) {
    const double eps = eps_of(dt);
    auto o = torch::TensorOptions().dtype(dt);
    const double dtcld = 60.0;
    const double rho_t = 0.6, rho_b = 1.2, dz_t = 300.0, dz_b = 700.0;

    auto rho  = torch::tensor({{rho_t, rho_b}}, o);   // dend = rho ALONE
    auto delz = torch::tensor({{dz_t, dz_b}}, o);
    auto mcol = torch::ones({1}, o);
    auto p = default_substep_advection_params();
    auto zero = torch::zeros({1, 2}, o);
    auto cst = [&](double a, double b) { return torch::tensor({{a, b}}, o); };

    // mass conservation identity + wrong-alternative rejection, from the
    // (q_in, q_out, fall_out) triple of one species.
    auto check_mass = [&](const char* nm, const torch::Tensor& q_in,
                          const torch::Tensor& q_out, const torch::Tensor& fall) {
        const double dq_out_t = item(fall, 0, 0) * dtcld / rho_t;
        const double dq_out_b = item(fall, 0, 1) * dtcld / rho_b;
        const double dq_in_b =
            item(q_out, 0, 1) - item(q_in, 0, 1) + dq_out_b;
        assert(dq_out_t > 0.0);                       // flux actually fired
        const double M_out = rho_t * dz_t * dq_out_t;
        const double M_in  = rho_b * dz_b * dq_in_b;
        const double R = M_out - M_in;
        const double tol = 64.0 * eps * (std::fabs(M_out) + std::fabs(M_in) + 1.0);
        std::cout << "    [C3.1 " << nm << "] |R|=" << std::fabs(R)
                  << " tol=" << tol << "\n";
        assert(std::fabs(R) <= tol);
        // WRONG alternative: rho-only conversion misses the delz ratio.
        const double dq_in_wrong = dq_out_t * (rho_t / rho_b);
        assert(std::fabs(dq_in_b - dq_in_wrong) > 0.25 * std::fabs(dq_in_b));
    };
    // number identity: delz-only measure, and the rho*delz "mass" conversion
    // must FAIL on numbers (the density factor does NOT apply).
    auto check_number = [&](const char* nm, const torch::Tensor& n_in,
                            const torch::Tensor& n_out, const torch::Tensor& fall) {
        const double dn_out_t = item(fall, 0, 0) * dtcld;
        const double dn_out_b = item(fall, 0, 1) * dtcld;
        const double dn_in_b =
            item(n_out, 0, 1) - item(n_in, 0, 1) + dn_out_b;
        assert(dn_out_t > 0.0);
        const double N_out = dz_t * dn_out_t;
        const double N_in  = dz_b * dn_in_b;
        const double R = N_out - N_in;
        const double tol = 64.0 * eps * (std::fabs(N_out) + std::fabs(N_in) + 1.0);
        std::cout << "    [C3.1 " << nm << "] |R|=" << std::fabs(R)
                  << " tol=" << tol << "\n";
        assert(std::fabs(R) <= tol);
        const double dn_in_wrong = dn_out_t * (rho_t * dz_t) / (rho_b * dz_b);
        assert(std::fabs(dn_in_b - dn_in_wrong) > 0.25 * std::fabs(dn_in_b));
    };

    // ── main chain (qr/qs/qg/brs + nr) ──────────────────────────────────────
    SubstepAdvectionState st{cst(4.0e-3, 1.0e-3), cst(2.0e5, 5.0e4),
                             cst(2.0e-3, 5.0e-4), cst(1.5e-3, 3.0e-4),
                             cst(5.0e-6, 1.0e-6)};
    // work1 = vt/delz [1/s]: qr cap BINDS (w*dtcld = 1.8 > 1), qs cap-inactive
    // (0.24), qg in the legacy-defect band (0.72) — all three regimes covered.
    SubstepAdvectionInputs in{
        st, zero, zero, zero, zero, zero,
        /*work1_qr=*/torch::full({1, 2}, 0.03, o),
        /*workn_qr=*/torch::full({1, 2}, 0.008, o),
        /*work1_qs=*/torch::full({1, 2}, 0.004, o),
        /*work1_qg=*/torch::full({1, 2}, 0.012, o),
        delz, rho,
    };
    auto out = substep_advection_conservative(in, mcol, 1, 1, dtcld, p);
    // regime proof: the qr top-cell entry cap bound (dq_out == full q_top),
    // the qs one did not — the identity is exercised in BOTH regimes.
    {
        const double dq_out_qr_t = item(out.fall_qr, 0, 0) * dtcld / rho_t;
        const double dq_out_qs_t = item(out.fall_qs, 0, 0) * dtcld / rho_t;
        assert(std::fabs(dq_out_qr_t - 4.0e-3) <= 64.0 * eps * 4.0e-3);  // capped
        assert(dq_out_qs_t < 2.0e-3 * 0.5);                              // uncapped
    }
    check_mass("qr", st.qr, out.state.qr, out.fall_qr);
    check_mass("qs", st.qs, out.state.qs, out.fall_qs);
    check_mass("qg", st.qg, out.state.qg, out.fall_qg);
    check_mass("brs", st.brs, out.state.brs, out.fall_brs);
    check_number("nr", st.nr, out.state.nr, out.fall_nr);

    // ── ice chain (qi + ni) ─────────────────────────────────────────────────
    IceSubstepState ist{cst(8.0e-4, 2.0e-4), cst(5.0e5, 1.0e5)};
    IceSubstepInputs iin{
        ist, zero, zero,
        /*work1_qi=*/torch::full({1, 2}, 0.03, o),
        /*workn_qi=*/torch::full({1, 2}, 0.008, o),
        delz, rho,
    };
    auto iout = ice_substep_advection_conservative(iin, mcol, 1, 1, dtcld, p);
    check_mass("qi", ist.qi, iout.state.qi, iout.fall_qi);
    check_number("ni", ist.ni, iout.state.ni, iout.fall_ni);
}

}  // namespace

void test_c31_nonuniform_metric_interface_identity() {
    TEST(test_c31_nonuniform_metric_interface_identity) {
        c31_case(torch::kFloat64);   // eps64 direct
        c31_case(torch::kFloat32);   // f32-input case with eps32
    } END_TEST();
}

// ═════════════════════════════════════════════════════════════════════════
// C3.2 — per-column mstep: gating, closure, batch independence
// ═════════════════════════════════════════════════════════════════════════
//
// Batch of 3 columns with mstep 1/3/4 (mstepmax=4), non-uniform metric,
// looping n=1..4 on the direct substeps (state AND fall accumulators carried).
// After each n:
//   - columns with n > mstep(b) are EXACTLY unchanged (torch::equal), state
//     and fall accumulators alike;
// after the loop, per column and per species:
//   - interface conservation closes: sum_k rho_k*delz_k*(q_fin - q_init)
//     + fall_bottom*dtcld*delz_bottom == O(eps) (numbers: delz-only measure);
//   - the batch result equals each column run ALONE (bitwise), and permuting
//     the batch order leaves every per-column result bitwise identical.
// Both the main (qr/nr/qs/qg/brs) and ice (qi/ni) chains.
namespace {

struct MainChainResult {
    SubstepAdvectionState st;
    torch::Tensor fall_qr, fall_nr, fall_qs, fall_qg, fall_brs;
};

MainChainResult run_main_chain(const SubstepAdvectionState& st0,
                               const torch::Tensor& w1_qr, const torch::Tensor& wn_qr,
                               const torch::Tensor& w1_qs, const torch::Tensor& w1_qg,
                               const torch::Tensor& delz, const torch::Tensor& rho,
                               const torch::Tensor& mcol, int nmax, double dtcld,
                               const SubstepAdvectionParams& p,
                               bool assert_gating = false) {
    MainChainResult r{st0, torch::zeros_like(st0.qr), torch::zeros_like(st0.qr),
                      torch::zeros_like(st0.qr), torch::zeros_like(st0.qr),
                      torch::zeros_like(st0.qr)};
    for (int n = 1; n <= nmax; ++n) {
        MainChainResult prev = r;
        SubstepAdvectionInputs in{
            r.st, r.fall_qr, r.fall_nr, r.fall_qs, r.fall_qg, r.fall_brs,
            w1_qr, wn_qr, w1_qs, w1_qg, delz, rho,
        };
        auto out = substep_advection_conservative(in, mcol, nmax, n, dtcld, p);
        r = MainChainResult{out.state, out.fall_qr, out.fall_nr,
                            out.fall_qs, out.fall_qg, out.fall_brs};
        if (assert_gating) {
            torch::NoGradGuard ng;
            const int64_t B = st0.qr.size(0);
            for (int64_t b = 0; b < B; ++b) {
                if (mcol.index({b}).item<double>() >= static_cast<double>(n))
                    continue;   // active column — may change
                // gated column: state AND fall accumulators exactly unchanged
                const torch::Tensor cur_t[10] = {
                    r.st.qr, r.st.nr, r.st.qs, r.st.qg, r.st.brs,
                    r.fall_qr, r.fall_nr, r.fall_qs, r.fall_qg, r.fall_brs};
                const torch::Tensor prev_t[10] = {
                    prev.st.qr, prev.st.nr, prev.st.qs, prev.st.qg, prev.st.brs,
                    prev.fall_qr, prev.fall_nr, prev.fall_qs, prev.fall_qg,
                    prev.fall_brs};
                for (int f = 0; f < 10; ++f)
                    assert(torch::equal(cur_t[f].index({b}).detach(),
                                        prev_t[f].index({b}).detach()));
            }
        }
    }
    return r;
}

struct IceChainResult {
    IceSubstepState st;
    torch::Tensor fall_qi, fall_ni;
};

IceChainResult run_ice_chain(const IceSubstepState& st0,
                             const torch::Tensor& w1_qi, const torch::Tensor& wn_qi,
                             const torch::Tensor& delz, const torch::Tensor& rho,
                             const torch::Tensor& mcol, int nmax, double dtcld,
                             const SubstepAdvectionParams& p,
                             bool assert_gating = false) {
    IceChainResult r{st0, torch::zeros_like(st0.qi), torch::zeros_like(st0.qi)};
    for (int n = 1; n <= nmax; ++n) {
        IceChainResult prev = r;
        IceSubstepInputs in{r.st, r.fall_qi, r.fall_ni, w1_qi, wn_qi, delz, rho};
        auto out = ice_substep_advection_conservative(in, mcol, nmax, n, dtcld, p);
        r = IceChainResult{out.state, out.fall_qi, out.fall_ni};
        if (assert_gating) {
            torch::NoGradGuard ng;
            const int64_t B = st0.qi.size(0);
            for (int64_t b = 0; b < B; ++b) {
                if (mcol.index({b}).item<double>() >= static_cast<double>(n))
                    continue;
                const torch::Tensor cur_t[4] = {r.st.qi, r.st.ni, r.fall_qi, r.fall_ni};
                const torch::Tensor prev_t[4] = {prev.st.qi, prev.st.ni,
                                                 prev.fall_qi, prev.fall_ni};
                for (int f = 0; f < 4; ++f)
                    assert(torch::equal(cur_t[f].index({b}).detach(),
                                        prev_t[f].index({b}).detach()));
            }
        }
    }
    return r;
}

// per-column mass closure of a chained-substep species (K=0 top).
void assert_column_closure(const char* nm, const torch::Tensor& q0,
                           const torch::Tensor& qf, const torch::Tensor& fall,
                           const torch::Tensor& rho, const torch::Tensor& delz,
                           double dtcld, bool mass_measure) {
    torch::NoGradGuard ng;
    const int64_t B = q0.size(0), K = q0.size(1);
    for (int64_t b = 0; b < B; ++b) {
        double dW = 0.0, scale = 0.0;
        for (int64_t k = 0; k < K; ++k) {
            const double m = mass_measure ? item(rho, b, k) * item(delz, b, k)
                                          : item(delz, b, k);
            dW += m * (item(qf, b, k) - item(q0, b, k));
            scale += m * (std::fabs(item(qf, b, k)) + std::fabs(item(q0, b, k)));
        }
        // bottom fall accumulates dq_out*rho/dtcld (mass; rho already inside)
        // or dN/dtcld (number); x dtcld x delz_bottom = what left the column.
        const double P = item(fall, b, K - 1) * dtcld * item(delz, b, K - 1);
        const double R = dW + P;
        const double tol = 256.0 * eps_of(torch::kFloat64) * (scale + P + 1.0);
        if (!(std::fabs(R) <= tol))
            std::cout << "    [C3.2 " << nm << "] col " << b << " |R|="
                      << std::fabs(R) << " tol=" << tol << "\n";
        assert(std::fabs(R) <= tol);
    }
}

}  // namespace

void test_c32_per_column_mstep() {
    TEST(test_c32_per_column_mstep) {
        const int B = 3, K = 4, NMAX = 4;
        const double dtcld = 60.0;
        auto o = f64();
        auto p = default_substep_advection_params();

        // non-uniform metric (k=0 top): dend = rho alone.
        auto rho1  = torch::tensor({{0.6, 0.8, 1.0, 1.2}}, o);
        auto delz1 = torch::tensor({{300.0, 500.0, 600.0, 700.0}}, o);
        auto rho  = rho1.repeat({B, 1});
        auto delz = delz1.repeat({B, 1});
        auto mcol = torch::tensor({1.0, 3.0, 4.0}, o);   // mstepmax = 4

        // per-column, per-level species seeds (columns distinct so the
        // batch-vs-single and permutation gates are load-bearing).
        auto seed = [&](double base) {
            auto t = torch::empty({B, K}, o);
            for (int b = 0; b < B; ++b)
                for (int k = 0; k < K; ++k)
                    t.index_put_({b, k}, base * (1.0 + 0.5 * b) * (1.0 + 0.1 * k));
            return t;
        };
        SubstepAdvectionState st0{seed(3.0e-3), seed(2.0e5), seed(1.5e-3),
                                  seed(1.0e-3), seed(4.0e-6)};
        auto w1_qr = torch::full({B, K}, 0.02, o);
        auto wn_qr = torch::full({B, K}, 0.010, o);
        auto w1_qs = torch::full({B, K}, 0.008, o);
        auto w1_qg = torch::full({B, K}, 0.014, o);
        IceSubstepState ist0{seed(8.0e-4), seed(1.0e5)};
        auto w1_qi = torch::full({B, K}, 0.02, o);
        auto wn_qi = torch::full({B, K}, 0.006, o);

        // batch run with per-substep gating assertions
        auto rb = run_main_chain(st0, w1_qr, wn_qr, w1_qs, w1_qg, delz, rho,
                                 mcol, NMAX, dtcld, p, /*assert_gating=*/true);
        auto ib = run_ice_chain(ist0, w1_qi, wn_qi, delz, rho,
                                mcol, NMAX, dtcld, p, /*assert_gating=*/true);

        // per-column interface-conservation closure (mass and number measures)
        assert_column_closure("qr", st0.qr, rb.st.qr, rb.fall_qr, rho, delz, dtcld, true);
        assert_column_closure("qs", st0.qs, rb.st.qs, rb.fall_qs, rho, delz, dtcld, true);
        assert_column_closure("qg", st0.qg, rb.st.qg, rb.fall_qg, rho, delz, dtcld, true);
        assert_column_closure("brs", st0.brs, rb.st.brs, rb.fall_brs, rho, delz, dtcld, true);
        assert_column_closure("qi", ist0.qi, ib.st.qi, ib.fall_qi, rho, delz, dtcld, true);
        assert_column_closure("nr", st0.nr, rb.st.nr, rb.fall_nr, rho, delz, dtcld, false);
        assert_column_closure("ni", ist0.ni, ib.st.ni, ib.fall_ni, rho, delz, dtcld, false);

        // batch == each column run ALONE (bitwise)
        using torch::indexing::Slice;
        for (int64_t b = 0; b < B; ++b) {
            auto sl = [&](const torch::Tensor& t) {
                return t.index({Slice(b, b + 1)});
            };
            SubstepAdvectionState s1{sl(st0.qr), sl(st0.nr), sl(st0.qs),
                                     sl(st0.qg), sl(st0.brs)};
            auto r1 = run_main_chain(s1, sl(w1_qr), sl(wn_qr), sl(w1_qs),
                                     sl(w1_qg), sl(delz), sl(rho),
                                     mcol.index({Slice(b, b + 1)}), NMAX, dtcld, p);
            const torch::Tensor batch_t[10] = {
                rb.st.qr, rb.st.nr, rb.st.qs, rb.st.qg, rb.st.brs,
                rb.fall_qr, rb.fall_nr, rb.fall_qs, rb.fall_qg, rb.fall_brs};
            const torch::Tensor single_t[10] = {
                r1.st.qr, r1.st.nr, r1.st.qs, r1.st.qg, r1.st.brs,
                r1.fall_qr, r1.fall_nr, r1.fall_qs, r1.fall_qg, r1.fall_brs};
            for (int f = 0; f < 10; ++f)
                assert(torch::equal(batch_t[f].index({b}), single_t[f].index({0})));

            IceSubstepState i1{sl(ist0.qi), sl(ist0.ni)};
            auto ri1 = run_ice_chain(i1, sl(w1_qi), sl(wn_qi), sl(delz), sl(rho),
                                     mcol.index({Slice(b, b + 1)}), NMAX, dtcld, p);
            const torch::Tensor bi[4] = {ib.st.qi, ib.st.ni, ib.fall_qi, ib.fall_ni};
            const torch::Tensor si[4] = {ri1.st.qi, ri1.st.ni, ri1.fall_qi, ri1.fall_ni};
            for (int f = 0; f < 4; ++f)
                assert(torch::equal(bi[f].index({b}), si[f].index({0})));
        }

        // permuting the batch order leaves per-column results identical
        auto perm = torch::tensor({2, 0, 1}, torch::TensorOptions().dtype(torch::kLong));
        auto ps = [&](const torch::Tensor& t) { return t.index_select(0, perm); };
        SubstepAdvectionState stp{ps(st0.qr), ps(st0.nr), ps(st0.qs),
                                  ps(st0.qg), ps(st0.brs)};
        auto rp = run_main_chain(stp, ps(w1_qr), ps(wn_qr), ps(w1_qs), ps(w1_qg),
                                 ps(delz), ps(rho), ps(mcol), NMAX, dtcld, p);
        IceSubstepState istp{ps(ist0.qi), ps(ist0.ni)};
        auto rip = run_ice_chain(istp, ps(w1_qi), ps(wn_qi), ps(delz), ps(rho),
                                 ps(mcol), NMAX, dtcld, p);
        for (int64_t i = 0; i < B; ++i) {
            const int64_t b = perm[i].item<int64_t>();
            const torch::Tensor orig_t[10] = {
                rb.st.qr, rb.st.nr, rb.st.qs, rb.st.qg, rb.st.brs,
                rb.fall_qr, rb.fall_nr, rb.fall_qs, rb.fall_qg, rb.fall_brs};
            const torch::Tensor perm_t[10] = {
                rp.st.qr, rp.st.nr, rp.st.qs, rp.st.qg, rp.st.brs,
                rp.fall_qr, rp.fall_nr, rp.fall_qs, rp.fall_qg, rp.fall_brs};
            for (int f = 0; f < 10; ++f)
                assert(torch::equal(orig_t[f].index({b}), perm_t[f].index({i})));
            const torch::Tensor oi[4] = {ib.st.qi, ib.st.ni, ib.fall_qi, ib.fall_ni};
            const torch::Tensor pi[4] = {rip.st.qi, rip.st.ni, rip.fall_qi, rip.fall_ni};
            for (int f = 0; f < 4; ++f)
                assert(torch::equal(oi[f].index({b}), pi[f].index({i})));
        }
    } END_TEST();
}

// ═════════════════════════════════════════════════════════════════════════
// C3.3 — dt=300 multi-subcycle closure (3 sub-cycles, dtcld=100)
// ═════════════════════════════════════════════════════════════════════════
//
// Per column b:  R_b = W_out - W_in + P_actual,
//   W = sum_k rho*delz*(qv+qc+qr+qi+qs+qg),  P_actual = rain_increment ALONE
// (rain_increment is the WDM6 TOTAL surface fallout; the snow/graupel
// increments are SUBSETS of it — adding them would double-count).
// Gates: internal C++ fp64 tight closure; public v2 f32 kappa recorded and
// gated at measured-max with margin; finiteness/nonnegativity; cap-inactive
// column legacy==conservative BITWISE (measured on this toolchain, pinned
// exactly on both the internal fp64 and public v2 f32 paths); cap-active
// columns materially different.

void test_c33_multisubcycle_closure_internal_fp64() {
    TEST(test_c33_multisubcycle_closure_internal_fp64) {
        State s; Forcing f;
        mk_closure_state(s, f);
        auto params = make_parameters(0);
        const double dt = 300.0;   // loops = 3, dtcld = 100 (DTCLDCR = 120)

        auto res_c = kdm6_step(s, f, params, dt, /*value_only=*/true,
                               c10::nullopt, 0.0, 0.0,
                               PhysicsOptions{PhysicsVariant::ConservativeInterface});
        auto res_l = kdm6_step(s, f, params, dt, /*value_only=*/true,
                               c10::nullopt, 0.0, 0.0,
                               PhysicsOptions{PhysicsVariant::Legacy});

        // finite everywhere; hydrometeors + numbers + increments nonnegative.
        for (auto* t : res_c.state_out.fields())
            assert(torch::all(torch::isfinite(*t)).item<bool>());
        for (auto* t : {&res_c.state_out.qv, &res_c.state_out.qc,
                        &res_c.state_out.qr, &res_c.state_out.qi,
                        &res_c.state_out.qs, &res_c.state_out.qg,
                        &res_c.state_out.nc, &res_c.state_out.ni,
                        &res_c.state_out.nr, &res_c.state_out.bg})
            assert(torch::all(*t >= 0).item<bool>());
        for (auto* t : {&res_c.rain_increment, &res_c.snow_increment,
                        &res_c.graupel_increment}) {
            assert(torch::all(torch::isfinite(*t)).item<bool>());
            assert(torch::all(*t >= 0).item<bool>());
        }

        // per-column fp64 closure; kappa64 = |R| / (eps64*(W_in+W_out+P+1)).
        const double eps64 = eps_of(torch::kFloat64);
        for (int64_t b = 0; b < 3; ++b) {
            const double w_in  = column_water(s, f, b);
            const double w_out = column_water(res_c.state_out, f, b);
            const double P = res_c.rain_increment.index({b}).item<double>();
            const double R = w_out - w_in + P;
            const double kappa = std::fabs(R) / (eps64 * (w_in + w_out + P + 1.0));
            std::cout << "    [C3.3 fp64] col " << b << " R=" << R
                      << " kappa64=" << kappa << "\n";
            assert(P > 0.0);   // every column actually precipitated
            // Measured kappa64 max = 0.30 across the three columns; gate at
            // 8.0 (~26x margin for toolchain variance) — the legacy interface
            // deletion this variant removes lands ORDERS of magnitude above.
            assert(kappa <= 8.0);
        }

        // col 0 (cap-inactive): legacy vs conservative measured BITWISE on
        // this toolchain (rel = 0, |dP| = 0) — uncapped, the two interfaces
        // perform the SAME transfer and the fp64 rounding coincides here.
        // Pin it exactly (state AND all three precip increments): a future
        // nonzero difference on the cap-inactive column must be root-caused,
        // never absorbed into a tolerance.
        const double d0 = max_state_rel_diff(res_l.state_out, res_c.state_out, 0);
        const double p0 = std::fabs(res_l.rain_increment[0].item<double>()
                                    - res_c.rain_increment[0].item<double>());
        std::cout << "    [C3.3 fp64] col 0 legacy-vs-cons rel=" << d0
                  << " |dP|=" << p0 << "\n";
        {
            auto lp = res_l.state_out.fields();
            auto cp = res_c.state_out.fields();
            for (size_t i = 0; i < lp.size(); ++i)
                assert(torch::equal(lp[i]->index({0}), cp[i]->index({0})));
            assert(torch::equal(res_l.rain_increment.index({0}),
                                res_c.rain_increment.index({0})));
            assert(torch::equal(res_l.snow_increment.index({0}),
                                res_c.snow_increment.index({0})));
            assert(torch::equal(res_l.graupel_increment.index({0}),
                                res_c.graupel_increment.index({0})));
        }
        // cols 1/2 (cap-active): materially different physics.
        for (int64_t b : {1, 2}) {
            const double db = max_state_rel_diff(res_l.state_out, res_c.state_out, b);
            std::cout << "    [C3.3 fp64] col " << b
                      << " legacy-vs-cons rel=" << db << "\n";
            assert(db > 1.0e-6);
        }
    } END_TEST();
}

void test_c33_multisubcycle_closure_public_v2_f32() {
    TEST(test_c33_multisubcycle_closure_public_v2_f32) {
        const int IM = 1, KME = 4, JME = 3;
        V2Tile tile(IM, KME, JME);
        for (int j = 0; j < JME; ++j) tile.fill_col(j, kClosureCols[j]);

        auto rc_cons = run_v2(tile, KDM6_PHYSICS_CONSERVATIVE_INTERFACE, 300.0, 1);
        auto rc_leg  = run_v2(tile, KDM6_PHYSICS_LEGACY, 300.0, 1);
        assert(rc_cons.rc == KDM6_OK && rc_leg.rc == KDM6_OK);
        assert(rc_cons.h == nullptr);

        for (int fld = 0; fld < 12; ++fld)
            for (float x : rc_cons.o[fld].data) assert(std::isfinite(x));
        for (int fld : {1, 2, 3, 4, 5, 6, 8, 9, 10, 11})   // qv..qg, nc, ni, nr, bg
            for (float x : rc_cons.o[fld].data) assert(x >= 0.0f);
        for (const auto* v : {&rc_cons.rain, &rc_cons.snow, &rc_cons.graup})
            for (float x : *v) { assert(std::isfinite(x)); assert(x >= 0.0f); }

        // per-column f32 closure with kappa recording (task C3.3): W terms
        // accumulated in double from the f32 buffers.
        const double eps32 = eps_of(torch::kFloat32);
        double kappa_max = 0.0;
        for (int j = 0; j < JME; ++j) {
            double w_in = 0.0, w_out = 0.0;
            for (int k = 0; k < KME; ++k) {
                const double rdz = static_cast<double>(tile.in[12].at(0, k, j))
                                 * static_cast<double>(tile.in[15].at(0, k, j));
                double qi_sum = 0.0, qo_sum = 0.0;
                for (int fld : {1, 2, 3, 4, 5, 6}) {   // qv qc qr qi qs qg
                    qi_sum += static_cast<double>(tile.in[fld].at(0, k, j));
                    qo_sum += static_cast<double>(rc_cons.o[fld].at(0, k, j));
                }
                w_in += rdz * qi_sum;
                w_out += rdz * qo_sum;
            }
            const double P = static_cast<double>(rc_cons.rain[j]);
            const double R = w_out - w_in + P;
            const double kappa = std::fabs(R) / (eps32 * (w_in + w_out + P + 1.0));
            kappa_max = std::max(kappa_max, kappa);
            std::cout << "    [C3.3 f32] col " << j << " R=" << R
                      << " kappa32=" << kappa << "\n";
            assert(P > 0.0);
        }
        std::cout << "    [C3.3 f32] kappa32 max = " << kappa_max << "\n";
        // Measured kappa32 max = 0.26 across the three columns (f32 op-state,
        // 3 sub-cycles of micro+sed roundoff). Gate at 8.0 (~30x margin for
        // toolchain variance) — a REAL interface deletion (the legacy defect
        // this variant removes) lands 3+ orders of magnitude above this.
        // Do NOT widen this tolerance to make a regression pass.
        assert(kappa_max <= 8.0);

        // cap-active columns materially different from legacy through the ABI.
        for (int j : {1, 2}) {
            bool any_diff = false;
            for (int fld = 0; fld < 12 && !any_diff; ++fld)
                for (int k = 0; k < KME && !any_diff; ++k)
                    any_diff = rc_cons.o[fld].at(0, k, j) != rc_leg.o[fld].at(0, k, j);
            assert(any_diff);
        }

        // cap-inactive pin through the PUBLIC v2 f32 path: v2 runs whole
        // tiles, so build a SINGLE-COLUMN tile of the cap-inactive column
        // (in the 3-column tile above, the cap-ACTIVE columns 1/2
        // legitimately differ between variants). Legacy (variant 0) vs
        // conservative (variant 1) measured BITWISE on this toolchain —
        // memcmp-pin all 12 output buffers AND the three increments; a
        // future nonzero difference on the cap-inactive column must be
        // root-caused, never absorbed into a tolerance.
        {
            V2Tile t0(1, KME, 1);
            t0.fill_col(0, kClosureCols[0]);
            auto r_leg  = run_v2(t0, KDM6_PHYSICS_LEGACY, 300.0, 1);
            auto r_cons = run_v2(t0, KDM6_PHYSICS_CONSERVATIVE_INTERFACE, 300.0, 1);
            assert(r_leg.rc == KDM6_OK && r_cons.rc == KDM6_OK);
            float max_abs = 0.0f;
            for (int fld = 0; fld < 12; ++fld)
                for (int k = 0; k < KME; ++k)
                    max_abs = std::max(max_abs,
                                       std::fabs(r_leg.o[fld].at(0, k, 0)
                                                 - r_cons.o[fld].at(0, k, 0)));
            std::cout << "    [C3.3 f32] cap-inactive v2 legacy-vs-cons max|d state|="
                      << max_abs << " |dP|="
                      << std::fabs(r_leg.rain[0] - r_cons.rain[0]) << "\n";
            for (int fld = 0; fld < 12; ++fld)
                assert(std::memcmp(r_leg.o[fld].data.data(),
                                   r_cons.o[fld].data.data(),
                                   r_leg.o[fld].data.size() * sizeof(float)) == 0);
            assert(std::memcmp(r_leg.rain.data(), r_cons.rain.data(),
                               sizeof(float)) == 0);
            assert(std::memcmp(r_leg.snow.data(), r_cons.snow.data(),
                               sizeof(float)) == 0);
            assert(std::memcmp(r_leg.graup.data(), r_cons.graup.data(),
                               sizeof(float)) == 0);
        }
    } END_TEST();
}

// ═════════════════════════════════════════════════════════════════════════
// C3.5 — AD gates
// ═════════════════════════════════════════════════════════════════════════

namespace {

// cap-active branch-stable point for the derivative gates: the col2 mixed
// cold column alone (B=1), dt=60 (single sub-cycle — the multi-subcycle
// forward is stressed by C3.3).
void mk_ad_point(State& s, Forcing& f, bool requires_grad) {
    State s3; Forcing f3;
    mk_closure_state(s3, f3);
    using torch::indexing::Slice;
    auto sl = [&](const torch::Tensor& t) {
        return t.index({Slice(2, 3)}).detach().clone();
    };
    auto sp = s.fields();
    auto s3p = s3.fields();
    for (size_t i = 0; i < sp.size(); ++i) {
        *sp[i] = sl(*s3p[i]);
        if (requires_grad) sp[i]->requires_grad_(true);
    }
    f.rho = sl(f3.rho); f.pii = sl(f3.pii); f.p = sl(f3.p); f.delz = sl(f3.delz);
}

constexpr double kAdDt = 60.0;

double conservative_loss(const State& x, const Forcing& f, const Parameters& p,
                         const State& w) {
    torch::NoGradGuard ng;
    auto r = kdm6_step(x, f, p, kAdDt, /*value_only=*/true, c10::nullopt, 0.0, 0.0,
                       PhysicsOptions{PhysicsVariant::ConservativeInterface});
    return state_dot(r.state_out, w).item<double>();
}

State perturbed(const State& base, const State& v, double eps) {
    State x;
    auto xp = x.fields();
    auto bp = const_cast<State&>(base).fields();
    auto vp = const_cast<State&>(v).fields();
    for (size_t i = 0; i < xp.size(); ++i)
        *xp[i] = (bp[i]->detach() + eps * *vp[i]).clone();
    return x;
}

}  // namespace

void test_c35_ad_gates_internal_fp64() {
    TEST(test_c35_ad_gates_internal_fp64) {
        State s; Forcing f;
        mk_ad_point(s, f, /*requires_grad=*/true);
        auto params = make_parameters(0);

        // the point IS cap-active: forward legacy != conservative here.
        {
            State sv; Forcing fv;
            mk_ad_point(sv, fv, false);
            auto rl = kdm6_step(sv, fv, params, kAdDt, true, c10::nullopt, 0.0, 0.0,
                                PhysicsOptions{PhysicsVariant::Legacy});
            auto rc = kdm6_step(sv, fv, params, kAdDt, true, c10::nullopt, 0.0, 0.0,
                                PhysicsOptions{PhysicsVariant::ConservativeInterface});
            assert(max_state_rel_diff(rl.state_out, rc.state_out, 0) > 1.0e-6);
        }

        auto res = kdm6_step(s, f, params, kAdDt, /*value_only=*/false,
                             c10::nullopt, 0.0, 0.0,
                             PhysicsOptions{PhysicsVariant::ConservativeInterface});
        assert(res.handle != nullptr);

        // directions: u seeded covector; v scaled per-field (nonzero in ALL 12
        // fields — includes qr, qv, th, qi as required).
        auto u = unit_state(11, 1, 4);
        auto v = scaled_direction(s, 17, 1.0e-4);
        for (auto* t : {&v.qr, &v.qv, &v.th, &v.qi})
            assert((*t != 0).any().item<bool>());

        // ── adjoint identity <Jv,u> == <v,J^T u> at scale-aware fp64 tol ────
        auto jv = res.handle->jvp(v);
        GraphOptions ro; ro.retain_graph = true;
        auto jtu = res.handle->vjp(u, ro);
        {
            torch::NoGradGuard ng;
            const double lhs = state_dot(jv, u).item<double>();
            const double rhs = state_dot(v, jtu).item<double>();
            const double denom = std::max({std::fabs(lhs), std::fabs(rhs), 1e-30});
            const double rel = std::fabs(lhs - rhs) / denom;
            std::cout << "    [C3.5] adjoint identity: <Jv,u>=" << lhs
                      << " <v,J^Tu>=" << rhs << " rel=" << rel << "\n";
            assert(rel < 1.0e-12);
        }

        // ── JVP -> JVP -> VJP repeated on the SAME handle ────────────────────
        auto jv_a = res.handle->jvp(v);
        auto jv_b = res.handle->jvp(v);     // repeat: identical
        for (size_t i = 0; i < 12; ++i)
            assert(torch::equal(*jv_a.fields()[i], *jv_b.fields()[i]));
        auto v2 = scaled_direction(s, 23, 1.0e-4);
        auto jv_c = res.handle->jvp(v2);    // second direction still fine
        auto jtu2 = res.handle->vjp(unit_state(29, 1, 4), ro);
        for (auto& g : {jv_a, jv_b, jv_c, jtu2})
            for (auto* t : const_cast<State&>(g).fields())
                assert(torch::isfinite(*t).all().item<bool>());

        // ── 3-point central FD sweep vs AD directional derivative ───────────
        // g(x) = <F(x), w>;  AD: dg = <J^T w, v_dir> from the SAME handle.
        // w spans the MASS/ENERGY outputs only (th,qv,qc,qr,qi,qs,qg): the
        // number outputs (nccn/nc/ni/nr) pass through the DSD limiters, whose
        // lamda boundary snap is a genuine JUMP surface — a number-weighted
        // functional makes central FD invalid at ANY eps near such a surface
        // (repo kink policy: fix the test functional, not the forward). The
        // smooth-regime FD target is the mass/energy response.
        auto w = unit_state(31, 1, 4);
        {
            auto wp = w.fields();
            for (size_t i = 7; i < 12; ++i)   // nccn, nc, ni, nr, bg
                *wp[i] = torch::zeros_like(*wp[i]);
        }
        auto v_dir = scaled_direction(s, 37, 1.0);   // O(field-scale) direction
        auto jtw = res.handle->vjp(w, ro);
        double g_ad;
        {
            torch::NoGradGuard ng;
            g_ad = state_dot(jtw, v_dir).item<double>();
        }
        double rel_err[3];
        const double eps_sweep[3] = {1.0e-4, 1.0e-5, 1.0e-6};
        for (int i = 0; i < 3; ++i) {
            const double e = eps_sweep[i];
            const double gp = conservative_loss(perturbed(s, v_dir, +e), f, params, w);
            const double gm = conservative_loss(perturbed(s, v_dir, -e), f, params, w);
            const double fd = (gp - gm) / (2.0 * e);
            rel_err[i] = std::fabs(fd - g_ad) / std::max(std::fabs(g_ad), 1e-300);
            std::cout << "    [C3.5] FD eps=" << e << " fd=" << fd
                      << " ad=" << g_ad << " rel_err=" << rel_err[i] << "\n";
        }
        // truncation-dominated -> floor: the error DECREASES from the coarse
        // eps (measured 8.8e-4 -> 7.9e-6, the O(eps^2) central-FD rate), then
        // FLATTENS (7.5e-6 at eps=1e-6 — no blow-up past the coarse error),
        // and the min-error region agrees with AD. Gate at 1e-4 (~12x margin
        // over the measured 7.9e-6 floor).
        assert(rel_err[1] < rel_err[0]);
        assert(rel_err[2] < rel_err[0]);
        assert(std::min(rel_err[1], rel_err[2]) < 1.0e-4);

        res.handle->close();
    } END_TEST();
}

void test_c35_public_v2_f32_graph_gate() {
    TEST(test_c35_public_v2_f32_graph_gate) {
        // f32 GRAPH gate (NOT the public fp64 conservative DA, which does not
        // exist): variant=1 value_only=0 must return a live handle whose VJP
        // succeeds with finite gradients, and the pointer-nulling close must
        // work. Tile = the all-species-active col2 point: the f32 backward is
        // documented to NaN at INACTIVE-ice corners (qi=ni=0, as in col1), so
        // the finiteness gate runs where every species is strictly active.
        const int IM = 1, KME = 4, JME = 1;
        V2Tile tile(IM, KME, JME);
        tile.fill_col(0, kClosureCols[2]);   // mixed cap-active, all species > 0

        auto r = run_v2(tile, KDM6_PHYSICS_CONSERVATIVE_INTERFACE, 60.0, 0);
        assert(r.rc == KDM6_OK);
        assert(r.h != nullptr);

        const size_t N = static_cast<size_t>(IM) * KME * JME;
        std::vector<double> u(12 * N, 1.0), grad(12 * N, -777.0);
        assert(kdm6_handle_vjp_c(r.h, u.data(), grad.data()) == KDM6_OK);
        bool any_nonzero = false;
        for (double g : grad) {
            assert(std::isfinite(g));
            if (g != 0.0) any_nonzero = true;
        }
        assert(any_nonzero);
        assert(kdm6_handle_closep_c(&r.h) == KDM6_OK);
        assert(r.h == nullptr);
    } END_TEST();
}

void test_c35_pin_legacy_ad() {
    TEST(test_c35_pin_legacy_ad) {
        // kdm6_step_ad_c is PERMANENTLY Legacy: on an identical cap-active
        // input its fp64 output must equal the internal C++ Legacy fp64 output
        // EXACTLY, and differ from the internal Conservative fp64 output.
        const int IM = 1, KME = 4, JME = 1, N = IM * KME * JME;
        State s; Forcing f;
        mk_ad_point(s, f, /*requires_grad=*/false);   // col2 cap-active point

        // pack (field-major; within a block, Fortran (im,kme,jme) col-major —
        // for a 1x4x1 tile that is just the k index).
        std::vector<double> state_in(12 * N), forcing_in(4 * N),
            state_out(12 * N, -777.0);
        {
            torch::NoGradGuard ng;
            auto sp = s.fields();
            for (int fld = 0; fld < 12; ++fld)
                for (int k = 0; k < KME; ++k)
                    state_in[fld * N + k] = item(*sp[fld], 0, k);
            const torch::Tensor* fp[4] = {&f.rho, &f.pii, &f.p, &f.delz};
            for (int fld = 0; fld < 4; ++fld)
                for (int k = 0; k < KME; ++k)
                    forcing_in[fld * N + k] = item(*fp[fld], 0, k);
        }
        kdm6_handle_t* h = nullptr;
        assert(kdm6_step_ad_c(state_in.data(), forcing_in.data(), IM, KME, JME,
                              kAdDt, /*value_only=*/0, state_out.data(), &h,
                              nullptr, 0.0, 0.0) == KDM6_OK);
        assert(h != nullptr);
        assert(kdm6_handle_closep_c(&h) == KDM6_OK);

        // internal Legacy fp64, same graph mode as ad_c (value_only=0).
        State sg; Forcing fg;
        mk_ad_point(sg, fg, /*requires_grad=*/true);
        auto params = make_parameters(0);
        auto res_leg = kdm6_step(sg, fg, params, kAdDt, /*value_only=*/false,
                                 c10::nullopt, 0.0, 0.0,
                                 PhysicsOptions{PhysicsVariant::Legacy});
        res_leg.handle->close();
        auto res_cons = kdm6_step(s, f, params, kAdDt, /*value_only=*/true,
                                  c10::nullopt, 0.0, 0.0,
                                  PhysicsOptions{PhysicsVariant::ConservativeInterface});

        bool differs_from_cons = false;
        {
            torch::NoGradGuard ng;
            auto lp = res_leg.state_out.fields();
            auto cp = res_cons.state_out.fields();
            for (int fld = 0; fld < 12; ++fld) {
                for (int k = 0; k < KME; ++k) {
                    const double ad_v  = state_out[fld * N + k];
                    const double leg_v = item(*lp[fld], 0, k);
                    const double con_v = item(*cp[fld], 0, k);
                    assert(ad_v == leg_v);   // EXACT: ad_c IS the legacy physics
                    if (ad_v != con_v) differs_from_cons = true;
                }
            }
        }
        assert(differs_from_cons);   // and NOT the conservative physics
    } END_TEST();
}

// ═════════════════════════════════════════════════════════════════════════
// C3.6 — legacy invariance through the OLD-SIGNATURE caller fixture
// ═════════════════════════════════════════════════════════════════════════
//
// The fixture (legacy_signature_caller.cpp, a SEPARATE translation unit)
// resolves the pre-PR22 mangled symbols at link time — proving an
// already-compiled consumer keeps linking — and here their results are pinned
// bitwise to the options-overload Legacy path.
void test_c36_old_signature_fixture_bitwise_legacy() {
    TEST(test_c36_old_signature_fixture_bitwise_legacy) {
        State s; Forcing f;
        mk_ad_point(s, f, /*requires_grad=*/false);
        auto params = make_parameters(0);

        auto fn_old = testing_legacy::call_pre_pr22_kdm6_fn(s, f, params, kAdDt);
        auto fn_new = kdm6_fn(s, f, params, kAdDt, c10::nullopt, 0.0, 0.0,
                              PhysicsOptions{PhysicsVariant::Legacy});
        {
            auto a = fn_old.state_out.fields();
            auto b = fn_new.state_out.fields();
            for (size_t i = 0; i < a.size(); ++i) assert(torch::equal(*a[i], *b[i]));
            assert(torch::equal(fn_old.rain_increment, fn_new.rain_increment));
            assert(torch::equal(fn_old.snow_increment, fn_new.snow_increment));
            assert(torch::equal(fn_old.graupel_increment, fn_new.graupel_increment));
        }

        auto st_old = testing_legacy::call_pre_pr22_kdm6_step(s, f, params, kAdDt,
                                                              /*value_only=*/true);
        auto st_new = kdm6_step(s, f, params, kAdDt, /*value_only=*/true,
                                c10::nullopt, 0.0, 0.0,
                                PhysicsOptions{PhysicsVariant::Legacy});
        {
            auto a = st_old.state_out.fields();
            auto b = st_new.state_out.fields();
            for (size_t i = 0; i < a.size(); ++i) assert(torch::equal(*a[i], *b[i]));
            assert(torch::equal(st_old.rain_increment, st_new.rain_increment));
            assert(st_old.handle == nullptr && st_new.handle == nullptr);
        }
    } END_TEST();
}

int main() {
    // The public-ABI gates (kdm6_step_v2_c / kdm6_step_ad_c) enforce the
    // single-thread determinism fence; pin BEFORE any torch op so the direct
    // C++ calls in this binary run under the same threading.
    at::set_num_threads(1);
    try { at::set_num_interop_threads(1); } catch (...) {}
    torch::manual_seed(0);

    std::cout << "KDM6AD-k conservative-interface-v1 C3 certification gates\n";
    test_c31_nonuniform_metric_interface_identity();
    test_c32_per_column_mstep();
    test_c33_multisubcycle_closure_internal_fp64();
    test_c33_multisubcycle_closure_public_v2_f32();
    test_c35_ad_gates_internal_fp64();
    test_c35_public_v2_f32_graph_gate();
    test_c35_pin_legacy_ad();
    test_c36_old_signature_fixture_bitwise_legacy();
    std::cout << "All conservative-interface C3 gates passed.\n";
    return 0;
}
