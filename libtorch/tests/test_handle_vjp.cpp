// Phase 2 gates for the C++ DA Handle::vjp / Handle::jvp (kdm6ad+da.md §6.2,
// §7.2/§7.3, §8.2, §8.4, §10.2). Mirrors the Python Phase-1 gate set
// (kdm6_torch/tests/test_handle_vjp_jvp.py) plus the OPERATIONAL-f32
// forward-determinism gate (Phase 2.5) that Python cannot exercise.
//
// IC policy: the fixed well-conditioned mixed-phase 2-cell column (g_base
// family) — away from clamp knife-edges. Deterministic directions (fixed
// seeds); fp64 for derivative gates, f32 ONLY for the determinism gate.
#include <cassert>
#include <cmath>
#include <cstdio>
#include <stdexcept>
#include <string>

#include <torch/torch.h>

#include "kdm6/runtime.h"
#include "kdm6/state.h"

using namespace kdm6;

namespace {

int g_fail = 0;
void fail(const std::string& m) { std::fprintf(stderr, "  FAIL: %s\n", m.c_str()); ++g_fail; }

torch::Tensor t2(double a, double b, torch::Dtype dt, bool rg = false) {
    auto t = torch::tensor({{a, b}}, torch::TensorOptions().dtype(dt));
    if (rg) t.requires_grad_(true);
    return t;
}

State mk_state(torch::Dtype dt, bool rg) {
    State s;
    s.th   = t2(296.8, 282.4, dt, rg);
    s.qv   = t2(1.40e-2, 2.0e-3, dt, rg);
    s.qc   = t2(1.0e-3, 5.0e-4, dt, rg);
    s.qr   = t2(1.0e-4, 1.0e-5, dt, rg);
    s.qi   = t2(0.0, 1.0e-6, dt, rg);
    s.qs   = t2(0.0, 5.0e-5, dt, rg);
    s.qg   = t2(0.0, 1.0e-5, dt, rg);
    s.nccn = t2(1.0e9, 1.0e9, dt, rg);
    s.nc   = t2(1.0e8, 1.0e8, dt, rg);
    s.ni   = t2(0.0, 1.0e8, dt, rg);
    s.nr   = t2(1.0e4, 1.0e3, dt, rg);
    s.bg   = t2(0.0, 0.0, dt, rg);
    return s;
}

Forcing mk_forcing(torch::Dtype dt) {
    Forcing f;
    f.rho  = t2(1.089, 0.9567, dt);
    f.pii  = t2(0.9704, 0.9031, dt);
    f.p    = t2(9.0e4, 7.0e4, dt);
    f.delz = t2(500.0, 500.0, dt);
    return f;
}

State unit_state(int64_t seed, torch::Dtype dt) {
    auto gen = at::detail::createCPUGenerator(seed);
    State s;
    for (auto* p : s.fields())
        *p = torch::randn({1, 2}, gen, torch::TensorOptions().dtype(dt));
    return s;
}

// direction scaled per-field so x±v stays physical (mirrors Python helper)
State scaled_direction(const State& ref, int64_t seed, double rel = 1.0e-4) {
    auto gen = at::detail::createCPUGenerator(seed);
    State s;
    auto sp = s.fields();
    auto rp = const_cast<State&>(ref).fields();
    for (size_t i = 0; i < sp.size(); ++i) {
        double scale = rp[i]->detach().abs().max().item<double>();
        if (scale == 0.0) scale = 1.0;
        *sp[i] = torch::randn({1, 2}, gen, rp[i]->options().requires_grad(false)) * rel * scale;
    }
    return s;
}

constexpr double kDt = 20.0;  // single sub-cycle — smooth point (loops=1)

#define TEST(name) std::printf("[ %s ]\n", #name); try
#define END_TEST() catch (const std::exception& e) { fail(std::string("exception: ") + e.what()); }

}  // namespace

int main() {
    torch::manual_seed(0);

    // ── vjp == backward gradient (exact) ─────────────────────────────────────
    TEST(vjp_matches_backward) {
        auto st = mk_state(torch::kFloat64, /*rg=*/true);
        auto res = kdm6_step(st, mk_forcing(torch::kFloat64), make_parameters(0), kDt, false);
        auto u = unit_state(11, torch::kFloat64);

        GraphOptions opts; opts.retain_graph = true;
        auto g = res.handle->vjp(u, opts);

        auto scalar = state_dot(res.state_out, u);
        scalar.backward();
        auto gp = g.fields();
        auto sp = st.fields();
        for (size_t i = 0; i < gp.size(); ++i) {
            auto ref = sp[i]->grad().defined() ? sp[i]->grad()
                                               : torch::zeros_like(*sp[i]);
            if (!torch::equal(*gp[i], ref)) fail("vjp != backward at field " + std::to_string(i));
        }
        res.handle->close();
    } END_TEST();

    // ── Pearlmutter inner product: <Jv,u> == <v,J^T u> (exact, not FD) ───────
    TEST(jvp_vjp_inner_product_exact) {
        auto st = mk_state(torch::kFloat64, true);
        auto res = kdm6_step(st, mk_forcing(torch::kFloat64), make_parameters(0), kDt, false);
        auto u = unit_state(13, torch::kFloat64);
        auto v = scaled_direction(st, 17);

        auto jv = res.handle->jvp(v);
        GraphOptions opts; opts.retain_graph = true;
        auto jtu = res.handle->vjp(u, opts);
        res.handle->close();

        double lhs = state_dot(jv, u).item<double>();
        double rhs = state_dot(v, jtu).item<double>();
        double denom = std::max({std::fabs(lhs), std::fabs(rhs), 1e-30});
        if (std::fabs(lhs - rhs) / denom >= 1e-12)
            fail("inner product mismatch: " + std::to_string(lhs) + " vs " + std::to_string(rhs));
    } END_TEST();

    // ── masked adjoint identity: same mask both sides stays exactly adjoint ──
    TEST(masked_adjoint_identity) {
        auto st = mk_state(torch::kFloat64, true);
        auto res = kdm6_step(st, mk_forcing(torch::kFloat64), make_parameters(0), kDt, false);
        auto u = unit_state(19, torch::kFloat64);
        auto v = scaled_direction(st, 23);

        // hydrometeor mass+number bits: qc,qr,qi,qs,qg(2..6), nc,ni,nr(8..10)
        GraphOptions m;
        m.active_field_mask = (1u<<2)|(1u<<3)|(1u<<4)|(1u<<5)|(1u<<6)|(1u<<8)|(1u<<9)|(1u<<10);
        m.retain_graph = true;

        auto jv  = res.handle->jvp(v, m);    // J·Pv (input-masked)
        auto jtu = res.handle->vjp(u, m);    // P·J^T u (output-masked)
        res.handle->close();

        double lhs = state_dot(jv, u).item<double>();
        double rhs = state_dot(v, jtu).item<double>();
        double denom = std::max({std::fabs(lhs), std::fabs(rhs), 1e-30});
        if (std::fabs(lhs - rhs) / denom >= 1e-12)
            fail("masked adjoint identity broken (F1-MASK-ADJOINT-ASYM class)");
    } END_TEST();

    // ── double-backward readiness (custom Functions: FmaAcc/LibmLog/RgmmaT) ──
    TEST(double_backward_ready) {
        auto st = mk_state(torch::kFloat64, true);
        auto res = kdm6_step(st, mk_forcing(torch::kFloat64), make_parameters(0), kDt, false);
        auto u = unit_state(29, torch::kFloat64);

        GraphOptions opts; opts.create_graph = true;
        auto g1 = res.handle->vjp(u, opts);

        torch::Tensor probe = torch::zeros({}, torch::kFloat64);
        for (auto* p : g1.fields()) probe = probe + (*p * *p).sum();

        std::vector<torch::Tensor> leaves;
        for (auto* p : st.fields()) leaves.push_back(*p);
        auto g2 = torch::autograd::grad({probe}, leaves, {}, false, false, true);
        bool any_nonzero = false;
        for (size_t i = 0; i < g2.size(); ++i) {
            if (g2[i].defined()) {
                if (!torch::isfinite(g2[i]).all().item<bool>())
                    fail("double-backward non-finite at field " + std::to_string(i));
                if ((g2[i] != 0).any().item<bool>()) any_nonzero = true;
            }
        }
        if (!any_nonzero) fail("double-backward all-zero (graph severed?)");
        res.handle->close();
    } END_TEST();

    // ── OPERATIONAL f32 forward-determinism (Phase 2.5, kdm6ad+da.md §8.4):
    //    value_only(InferenceMode-class) vs graph forward must be BITWISE equal
    //    on float32 — the custom-op dispatch (GradMode/requires_grad) switches
    //    implementations but must not switch values. The 100-step bitwise
    //    campaign only ever exercised value_only=1; this is the grad-mode gate.
    TEST(f32_forward_determinism_value_vs_graph) {
        auto fz = mk_forcing(torch::kFloat32);
        auto r_val = kdm6_step(mk_state(torch::kFloat32, false), fz,
                               make_parameters(0), kDt, /*value_only=*/true);
        auto r_gph = kdm6_step(mk_state(torch::kFloat32, true), fz,
                               make_parameters(0), kDt, /*value_only=*/false);
        auto a = r_val.state_out.fields();
        auto b = r_gph.state_out.fields();
        for (size_t i = 0; i < a.size(); ++i) {
            if (!torch::equal(a[i]->detach(), b[i]->detach()))
                fail("f32 value-vs-graph forward mismatch at field " + std::to_string(i));
        }
        r_gph.handle->close();
    } END_TEST();

    // ── shape rejection BEFORE autograd (graph must survive) ────────────────
    TEST(shape_mismatch_rejected_graph_survives) {
        auto st = mk_state(torch::kFloat64, true);
        auto res = kdm6_step(st, mk_forcing(torch::kFloat64), make_parameters(0), kDt, false);

        State bad;  // (2,1) broadcastable-but-wrong vs (1,2)
        for (auto* p : bad.fields())
            *p = torch::ones({2, 1}, torch::TensorOptions().dtype(torch::kFloat64));
        bool threw = false;
        try { res.handle->vjp(bad); } catch (const std::exception&) { threw = true; }
        if (!threw) fail("broadcastable shape mismatch silently accepted (F1-SHAPE)");

        // the failed validation must not have consumed the one-shot graph
        auto g = res.handle->vjp(unit_state(31, torch::kFloat64));
        bool nz = false;
        for (auto* p : g.fields()) if ((*p != 0).any().item<bool>()) nz = true;
        if (!nz) fail("graph consumed by rejected call");
        res.handle->close();
    } END_TEST();

    // ── lifecycle: value_only returns NO handle; closed handles refuse calls ──
    TEST(lifecycle_guards) {
        // C++ contract (kdm6ad+da.md §1.2): value_only=true → handle == nullptr
        // (NOT a value-only Handle object — that is the Python-side shape).
        auto res_vo = kdm6_step(mk_state(torch::kFloat64, false), mk_forcing(torch::kFloat64),
                                make_parameters(0), kDt, /*value_only=*/true);
        if (res_vo.handle != nullptr) fail("value-only step must return null handle");

        auto res = kdm6_step(mk_state(torch::kFloat64, true), mk_forcing(torch::kFloat64),
                             make_parameters(0), kDt, false);
        res.handle->close();
        bool threw = false;
        try { res.handle->vjp(unit_state(41, torch::kFloat64)); }
        catch (const std::exception&) { threw = true; }
        if (!threw) fail("closed handle accepted vjp");
    } END_TEST();

    if (g_fail) { std::printf("%d check(s) failed\n", g_fail); return 1; }
    std::printf("  PASS  C++ Handle vjp/jvp gates (incl. f32 grad-mode determinism)\n");
    return 0;
}
