// End-to-end autograd validation for KDM6AD — the project's CORE goal
// (자동미분 가능한 KDM6 / 4D-Var). Validates the FULL differentiable forward
// `kdm6_fn`:  state_to_coord (t = θ·π)  →  build_default_aux (n0/work1)  →
// kdm62d_step (preamble→warm→cold→melt/freeze→state_update→reclass→satadj→
// DSD limiters)  →  sedimentation_chain.  This is the exact function the
// Handle/vjp/jvp adjoint interface differentiates, so it is the right target.
//
//   PART A — GRAPH INTEGRITY (the must-have): ∂loss/∂(state leaf) is defined,
//     finite, and nonzero for every leaf that physically influences the loss.
//     A stray `.item()`/detach outside NoGradGuard ANYWHERE in the chain would
//     sever the graph and surface here as an undefined or zero gradient.
//
//   PART B — NUMERICAL CORRECTNESS ("fp 형태, 유효숫자까지 정합성"): central
//     finite differences  (L(x+ε) − L(x−ε)) / (2ε)  in float64 vs the autograd
//     gradient must agree to several significant digits at a smooth operating
//     point. This is the standard torch.autograd.gradcheck contract, hand-rolled
//     in C++ so it runs against the production libtorch path WRF actually calls.
//
// Operating point: a single column (B=1, K=2) — k0 warm/supersaturated/raining
// (exercises θ,qv,qc,qr,nc,nr via pcact/pcond/praut/pracw/prevp), k1 cold/
// mixed-phase (exercises qi,ni and the cold/melt-freeze rates). Hydrometeors
// and delz are chosen so every internal step count (loops_max, sedimentation
// mstep) is a robust 1 ⇒ no integer-control-flow kink under the ε perturbation.

#include "kdm6/runtime.h"
#include "kdm6/state.h"

#include <array>
#include <cmath>
#include <iostream>
#include <string>

using namespace kdm6;

namespace {

constexpr double DT = 20.0;   // short ⇒ loops_max = mstep = 1 (smooth, no kink)

// State::fields() order — keep in lockstep.
const char* FNAME[12] =
    {"th","qv","qc","qr","qi","qs","qg","nccn","nc","ni","nr","bg"};

// base[field][k]: k=0 warm-lower, k=1 cold-upper.
double g_base[12][2] = {
    /* th  */ {296.8,   282.4 },   // θ ⇒ T≈288K (k0), ≈255K (k1)
    /* qv  */ {1.40e-2, 2.0e-3},   // k0 supersat wrt water; k1 supersat wrt ice
    /* qc  */ {1.0e-3,  5.0e-4},   // k1 supercooled cloud
    /* qr  */ {1.0e-4,  1.0e-5},
    /* qi  */ {0.0,     1.0e-4},
    /* qs  */ {0.0,     5.0e-5},
    /* qg  */ {0.0,     1.0e-5},
    /* nccn*/ {1.0e9,   1.0e9 },
    /* nc  */ {1.0e8,   1.0e8 },
    /* ni  */ {0.0,     1.0e4 },
    /* nr  */ {1.0e4,   1.0e3 },
    /* bg  */ {0.0,     0.0   },
};
// forcing[field][k]: rho, pii, p, delz.
double g_force[4][2] = {
    /* rho */ {1.089,   0.9567},
    /* pii */ {0.9704,  0.9031},
    /* p   */ {9.0e4,   7.0e4 },
    /* delz*/ {500.0,   500.0 },
};

// Differentiable leaves (the 8 the user named): θ,qv,qc,qr,qi,nc,ni,nr.
const std::array<int,8> GRAD_LEAVES = {0,1,2,3,4,8,9,10};
bool is_grad_leaf(int fi) {
    for (int g : GRAD_LEAVES) if (g == fi) return true;
    return false;
}

torch::Tensor mk(double v0, double v1, bool grad) {
    auto t = torch::tensor({v0, v1}, torch::kFloat64).reshape({1, 2});
    if (grad) t.requires_grad_(true);
    return t;
}

// Build (State, Forcing). If pf>=0, perturb base[pf][pk] by `delta` (FD probe);
// such probe builds are always grad=false (used under NoGradGuard).
struct Inputs { State s; Forcing f; std::array<torch::Tensor,12> leaves; };
Inputs build(bool grad, int pf = -1, int pk = -1, double delta = 0.0) {
    auto val = [&](int fi, int k) {
        double v = g_base[fi][k];
        if (fi == pf && k == pk) v += delta;
        return v;
    };
    std::array<torch::Tensor,12> L;
    for (int fi = 0; fi < 12; ++fi)
        L[fi] = mk(val(fi,0), val(fi,1), grad && is_grad_leaf(fi));
    State s{L[0],L[1],L[2],L[3],L[4],L[5],L[6],L[7],L[8],L[9],L[10],L[11]};
    Forcing f{
        mk(g_force[0][0], g_force[0][1], false),
        mk(g_force[1][0], g_force[1][1], false),
        mk(g_force[2][0], g_force[2][1], false),
        mk(g_force[3][0], g_force[3][1], false),
    };
    return {std::move(s), std::move(f), std::move(L)};
}

// Scalar loss over the forward result. Includes rain_increment so the
// sedimentation branch (NoGradGuard mstep + flip) is exercised end-to-end.
// Number species weighted by 1e-9 so mass/number contributions are commensurate
// (irrelevant to FD↔AD agreement, which compares the SAME loss both ways).
torch::Tensor loss_of(const FnResult& r) {
    const auto& o = r.state_out;
    auto mass = o.qv.sum() + o.qc.sum() + o.qr.sum()
              + o.qi.sum() + o.qs.sum() + o.qg.sum();
    auto numb = o.nc.sum() + o.nr.sum() + o.ni.sum();
    return mass + 1.0e-9 * numb + r.rain_increment.sum();
}

double eval_loss(int pf, int pk, double delta) {
    torch::NoGradGuard ng;
    auto in = build(/*grad=*/false, pf, pk, delta);
    auto r  = kdm6_fn(in.s, in.f, make_parameters(0), DT);
    return loss_of(r).item<double>();
}

int g_fail = 0;
void fail(const std::string& m) { std::cerr << "  FAIL: " << m << "\n"; ++g_fail; }

}  // namespace

int main() {
    std::cout << "RUN test_autograd_endtoend\n";

    // ── Forward + backward once on the grad-enabled leaves ────────────────────
    auto in = build(/*grad=*/true);
    auto res = kdm6_fn(in.s, in.f, make_parameters(0), DT);
    auto loss = loss_of(res);
    loss.backward();

    // (leaf, k) probes — each of the 8 leaves at the cell where it is active.
    struct Probe { int fi; int k; bool expect_active; };
    const Probe probes[] = {
        {0,0,true}, {0,1,true},     // th  (latent heating both cells)
        {1,0,true}, {1,1,true},     // qv  (condensation/deposition source)
        {2,0,true}, {2,1,true},     // qc  (autoconv/accretion/freezing)
        {3,0,true},                 // qr  (warm rain, k0)
        {4,1,true},                 // qi  (cold ice, k1)
        {8,0,true}, {8,1,true},     // nc
        {9,1,true},                 // ni  (cold, k1)
        {10,0,true},                // nr  (warm, k0)
    };

    // ── PART A: graph integrity ───────────────────────────────────────────────
    std::cout << "\n[PART A] autograd graph integrity (defined / finite / nonzero)\n";
    {
        torch::NoGradGuard ng;  // reading .grad()/.item() — no graph needed
        for (const auto& p : probes) {
            const auto& g = in.leaves[p.fi].grad();
            bool defined = g.defined();
            double gv = 0.0; bool finite = false;
            if (defined) {
                gv = g.index({0, p.k}).item<double>();
                finite = std::isfinite(gv);
            }
            bool nonzero = std::abs(gv) > 0.0;
            bool ok = defined && finite && (!p.expect_active || nonzero);
            std::cout << "  d(loss)/d(" << FNAME[p.fi] << "[k" << p.k << "]) = "
                      << gv << (ok ? "  [ok]"
                                   : (!defined ? "  [SEVERED: undefined]"
                                      : !finite ? "  [NON-FINITE]"
                                                : "  [ZERO where active]")) << "\n";
            if (!ok) fail(std::string("graph integrity ") + FNAME[p.fi]
                          + "[k" + std::to_string(p.k) + "]");
        }
    }

    // ── PART B: central finite-difference vs autograd (fp64, sig-digit) ───────
    std::cout << "\n[PART B] central FD vs autograd  (rel = |ad-fd|/(|ad|+|fd|))\n";
    {
        torch::NoGradGuard ng;
        double worst_digits = 99.0;
        for (const auto& p : probes) {
            double x = g_base[p.fi][p.k];
            // relative step, floored so zero-valued leaves still probe (qi[k0]=0
            // is not in the probe list, but qr/qg small values are handled).
            double eps = std::max(1.0e-6 * std::abs(x), 1.0e-11);
            double lp = eval_loss(p.fi, p.k,  eps);
            double lm = eval_loss(p.fi, p.k, -eps);
            double g_fd = (lp - lm) / (2.0 * eps);
            double g_ad = in.leaves[p.fi].grad().defined()
                        ? in.leaves[p.fi].grad().index({0, p.k}).item<double>()
                        : 0.0;
            double denom = std::abs(g_ad) + std::abs(g_fd);
            double rel = denom > 1.0e-300 ? std::abs(g_ad - g_fd) / denom : 0.0;
            double digits = rel > 0.0 ? -std::log10(rel) : 99.0;
            // Negligible-gradient leaves (both ~0) trivially agree — don't let
            // their noise dominate the "worst digits" headline.
            bool negligible = denom < 1.0e-12 * std::abs(g_ad + g_fd + 1.0);
            if (!negligible && digits < worst_digits) worst_digits = digits;
            std::cout << "  " << FNAME[p.fi] << "[k" << p.k << "]"
                      << "  ad=" << g_ad << "  fd=" << g_fd
                      << "  rel=" << rel
                      << "  (" << (digits >= 99.0 ? std::string("exact")
                                   : std::to_string(digits).substr(0,4)) << " digits)"
                      << (rel < 1.0e-3 || negligible ? "" : "  [MISMATCH]") << "\n";
            if (!(rel < 1.0e-3 || negligible))
                fail(std::string("FD mismatch ") + FNAME[p.fi]
                     + "[k" + std::to_string(p.k) + "]");
        }
        std::cout << "  worst-case agreement: " << worst_digits
                  << " significant digits (target >= 3)\n";
        if (worst_digits < 3.0) fail("worst-case FD agreement < 3 significant digits");
    }

    if (g_fail) { std::cerr << "\n" << g_fail << " check(s) failed\n"; return 1; }
    std::cout << "\n  PASS  kdm6_fn is differentiable end-to-end AND matches "
                 "central FD to significant digits\n";
    return 0;
}
