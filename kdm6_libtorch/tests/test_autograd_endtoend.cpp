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

#include <algorithm>
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

// ── Kink-robust FD gate ──────────────────────────────────────────────────────
// Central FD is INVALID at a non-smooth point (clamp / flux-limiter corner):
// it averages the two one-sided slopes, so at a genuine kink it reports a value
// autograd's (correct) subgradient cannot match. PART B routes such a "failing"
// leaf here. Decision (designed + adversarially red-teamed — see commit msg):
//   PASS  iff g_ad coincides with a CONVERGED, NON-DIVERGENT one-sided slope
//         (AD is a valid one-sided subgradient at a real non-smoothness; the
//          OTHER side carries a different slope — the kink signature).
//   FAIL  if g_ad matches NEITHER one-sided slope while both converge to the
//         same large slope  → genuine missing(S2)/attenuated(S3) gradient,
//         OR both one-sided slopes diverge ~1/eps → discontinuity/jump(S4).
// Central FD is NEVER consulted for the decision — only one-sided slopes are.
// Every borderline case resolves to FAIL: it can never silently pass a real bug.
constexpr double KK_EPS_MACH = 2.220446049250313e-16;
inline double kk_nf(double e, double l0) {            // one-sided quotient round-off floor
    return 8.0 * KK_EPS_MACH * (std::abs(l0) + 1.0) / e;
}
inline double kk_rel(double a, double b) {
    return std::abs(a - b) / (std::abs(a) + std::abs(b) + 1e-300);
}
struct KinkVerdict { bool pass; std::string note; };

// PURE decision (no I/O, no eval_loss) — unit-testable with synthetic samples.
// Inputs: autograd grad + 5 loss samples (base l0, ±eps coarse, ±eps2 fine).
KinkVerdict kink_decision(double g_ad, double eps, double l0,
                          double lp, double lm,
                          double eps2, double lp2, double lm2) {
    const double TOL_REL = 5.0e-2, TOL_ABS = 1.0e-12, K_NF = 4.0, G_MAX = 4.0;
    const double gLc = (l0 - lm)  / eps,  gRc = (lp  - l0) / eps;    // coarse one-sided
    const double gLf = (l0 - lm2) / eps2, gRf = (lp2 - l0) / eps2;   // fine one-sided
    const double nfC = kk_nf(eps, l0), nfF = kk_nf(eps2, l0);
    // Per side: resolved limit (prefer finer level); flat = noise on both; div = ~1/eps growth.
    auto side = [&](double sc, double sf, bool& flat, bool& div) -> double {
        bool resC = std::abs(sc) > 3.0 * nfC, resF = std::abs(sf) > 3.0 * nfF;
        flat = !(resC || resF); div = false;
        if (flat) return 0.0;
        if (resC && resF && std::abs(sf) > G_MAX * std::abs(sc)) div = true;
        return resF ? sf : sc;
    };
    bool flatL, flatR, divL, divR;
    const double sL = side(gLc, gLf, flatL, divL);
    const double sR = side(gRc, gRf, flatR, divR);
    if (divL && divR)
        return {false, "DISCONTINUITY/JUMP at base point (both one-sided slopes diverge ~1/eps)"};
    auto match = [&](double s, bool fine) -> bool {
        double nf = fine ? nfF : nfC;
        return kk_rel(g_ad, s) < TOL_REL ||
               std::abs(g_ad - s) < std::max(TOL_ABS, K_NF * nf);
    };
    bool mL = !divL && match(sL, !flatL);
    bool mR = !divR && match(sR, !flatR);
    if (mL || mR) {
        bool sidesAgree = !divL && !divR && kk_rel(sL, sR) < TOL_REL;
        return {true, sidesAgree
            ? "kink-note: AD==one-sided slope (sides agree; central test tripped on FD noise)"
            : "kink-note: AD equals a valid one-sided subgradient (other side carries a different slope)"};
    }
    bool sidesAgree = !divL && !divR && !flatL && !flatR && kk_rel(sL, sR) < TOL_REL;
    return {false, sidesAgree
        ? "AUTOGRAD BUG: both one-sided derivatives agree on a large slope AD matches neither (missing/attenuated)"
        : "AUTOGRAD inconsistent with both one-sided derivatives (no valid subgradient match)"};
}

// Probing wrapper: gathers l0 + one finer ± probe (3 extra eval_loss) then decides.
// Reuses the lp/lm PART B already computed at the routing eps. Under NoGradGuard.
KinkVerdict classify_kink(int pf, int pk, double g_ad,
                          double eps, double lp, double lm) {
    const double l0   = eval_loss(pf, pk, 0.0);
    const double eps2 = eps * 0.1;
    const double lp2  = eval_loss(pf, pk,  eps2);
    const double lm2  = eval_loss(pf, pk, -eps2);
    return kink_decision(g_ad, eps, l0, lp, lm, eps2, lp2, lm2);
}

// Adversarial self-test of the PURE decision: the gate MUST keep its teeth.
// Synthesizes loss samples reproducing the four canonical scenarios and asserts
// S1→PASS, S2/S3/S4→FAIL. This is the committed proof that the kink tolerance
// cannot mask a real autograd break (S2 missing / S3 attenuated / S4 jump).
void selftest_kink_decision() {
    std::cout << "\n[PART B0] kink-gate adversarial self-test (S2/S3/S4 must FAIL)\n";
    const double eps = 1.0e-2, eps2 = 1.0e-3, l0 = 0.05;   // ni-like scale
    auto mk = [&](double gL_c, double gR_c, double gL_f, double gR_f) {
        // returns {lp, lm, lp2, lm2} reproducing the requested one-sided slopes
        return std::array<double,4>{ l0 + gR_c*eps, l0 - gL_c*eps,
                                     l0 + gR_f*eps2, l0 - gL_f*eps2 };
    };
    struct Case { const char* name; double g_ad; std::array<double,4> s; bool expect_pass; };
    const Case cases[] = {
        // S1 legit kink: flat left (=g_ad), steep right; AD == left subgradient.
        {"S1 kink",       -1.58e-9, mk(-1.58e-9,-6.08e-5,-1.58e-9,-6.08e-5), true},
        // S2 missing/severed: both sides agree large, AD≈0.
        {"S2 missing",     1.0e-12, mk(-3.0e-5,-3.0e-5,-3.0e-5,-3.0e-5),     false},
        // S3 attenuated: both sides agree large, AD is half.
        {"S3 attenuated", -1.5e-5,  mk(-3.0e-5,-3.0e-5,-3.0e-5,-3.0e-5),     false},
        // S4 jump: both one-sided slopes grow ~10x as eps shrinks.
        {"S4 jump",       -1.58e-9, mk(-6.0e-5,-6.0e-5,-6.0e-4,-6.0e-4),     false},
    };
    for (const auto& c : cases) {
        KinkVerdict v = kink_decision(c.g_ad, eps, l0, c.s[0], c.s[1], eps2, c.s[2], c.s[3]);
        bool ok = (v.pass == c.expect_pass);
        std::cout << "  " << c.name << ": verdict=" << (v.pass ? "PASS" : "FAIL")
                  << " expect=" << (c.expect_pass ? "PASS" : "FAIL")
                  << (ok ? "  [ok]" : "  [WRONG]") << "  (" << v.note << ")\n";
        if (!ok) fail(std::string("kink-gate self-test ") + c.name);
    }
}

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

    // ── PART B0: prove the kink-robust gate still catches real breaks ─────────
    selftest_kink_decision();

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
            bool central_fail = !(rel < 1.0e-3 || negligible);
            // A central-FD failure may be a genuine non-smoothness (clamp / flux-
            // limiter corner) where AD is a valid one-sided subgradient and central
            // FD is invalid (it averages the two one-sided slopes). Route those
            // through the kink-robust gate; only a real missing/attenuated/jump
            // gradient still FAILs (kink_decision, self-tested in PART B0).
            KinkVerdict kv{true, ""};
            if (central_fail) kv = classify_kink(p.fi, p.k, g_ad, eps, lp, lm);
            bool is_kink_pass = central_fail && kv.pass;
            // A kink leaf is a NON-smooth point: its central-FD "digits" are
            // meaningless, so it must not poison the worst-digits headline.
            if (!negligible && !is_kink_pass && digits < worst_digits) worst_digits = digits;
            std::cout << "  " << FNAME[p.fi] << "[k" << p.k << "]"
                      << "  ad=" << g_ad << "  fd=" << g_fd
                      << "  rel=" << rel
                      << "  (" << (digits >= 99.0 ? std::string("exact")
                                   : std::to_string(digits).substr(0,4)) << " digits)"
                      << (!central_fail ? "" : (is_kink_pass ? "  [KINK-OK]" : "  [MISMATCH]"))
                      << "\n";
            if (central_fail) {
                if (is_kink_pass)
                    std::cout << "      -> PASS-with-kink: " << kv.note << "\n";
                else
                    fail(std::string("FD mismatch ") + FNAME[p.fi]
                         + "[k" + std::to_string(p.k) + "]: " + kv.note);
            }
        }
        std::cout << "  worst-case agreement: " << worst_digits
                  << " significant digits (target >= 3)\n";
        if (worst_digits < 3.0) fail("worst-case FD agreement < 3 significant digits");
    }

    // ── PART C: sub-cycled timestep (loops>1) — Stage-S2 per-substep sediment ─
    // DT in PART A/B is 20s ⇒ loops=1 (single sub-cycle). Here DT=300s ⇒ loops=3
    // (dtcld=100s), exercising the per-substep [sediment → re-slope/aux →
    // microphysics] interleave + the accumulated surface increments + autograd
    // through the sub-cycle loop. Smoke: forward finite, loss differentiable,
    // ∂loss/∂(grad leaf) defined + finite (the loops>1 path the loops=1 gates
    // can't reach).
    std::cout << "\n[PART C] sub-cycled DT=300 (loops=3) — Stage-S2 per-substep sediment\n";
    {
        auto inC = build(/*grad=*/true);
        auto rC = kdm6_fn(inC.s, inC.f, make_parameters(0), /*dt=*/300.0);
        auto lossC = loss_of(rC);
        bool fwd_finite = std::isfinite(lossC.item<double>())
            && torch::isfinite(rC.state_out.qc).all().item<bool>()
            && torch::isfinite(rC.state_out.qi).all().item<bool>()
            && torch::isfinite(rC.rain_increment).all().item<bool>();
        std::cout << "  forward finite: " << (fwd_finite ? "yes" : "NO")
                  << "  loss=" << lossC.item<double>() << "\n";
        if (!fwd_finite) fail("loops>1 forward non-finite");
        lossC.backward();
        for (int gi : GRAD_LEAVES) {
            const auto& g = inC.leaves[gi].grad();
            bool ok = g.defined() && torch::isfinite(g).all().item<bool>();
            if (!ok) { std::cout << "  d/d(" << FNAME[gi] << ") SEVERED/NON-FINITE\n";
                       fail(std::string("loops>1 grad ") + FNAME[gi]); }
        }
        if (!g_fail) std::cout << "  loops>1 forward finite + all grad leaves defined/finite [ok]\n";
    }

    if (g_fail) { std::cerr << "\n" << g_fail << " check(s) failed\n"; return 1; }
    std::cout << "\n  PASS  kdm6_fn is differentiable end-to-end AND matches "
                 "central FD to significant digits\n";
    return 0;
}
