// Phase 2 gates for the C++ DA Handle::vjp / Handle::jvp (kdm6ad+da.md §6.2,
// §7.2/§7.3, §8.2, §8.4, §10.2). Mirrors the Python Phase-1 gate set
// (kdm6_torch/tests/test_handle_vjp_jvp.py) plus the OPERATIONAL-f32
// forward-determinism gate (Phase 2.5) that Python cannot exercise.
//
// IC policy: the fixed well-conditioned mixed-phase 2-cell column (g_base
// family) — away from clamp knife-edges. Deterministic directions (fixed
// seeds); fp64 for derivative gates, f32 ONLY for the determinism gate.
#include <cassert>
#include <algorithm>
#include <array>
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

torch::Tensor leaf2(double a, double b, torch::Dtype dt = torch::kFloat64) {
    return torch::tensor({{a, b}}, torch::TensorOptions().dtype(dt)).requires_grad_(true);
}

State joint_leaf_state() {
    State s;
    auto fields = s.fields();
    for (size_t i = 0; i < fields.size(); ++i)
        *fields[i] = leaf2(0.2 + 0.07 * static_cast<double>(i),
                           -0.1 + 0.03 * static_cast<double>(i));
    return s;
}

Forcing joint_leaf_forcing() {
    Forcing f;
    auto fields = f.fields();
    for (size_t i = 0; i < fields.size(); ++i)
        *fields[i] = leaf2(0.4 + 0.11 * static_cast<double>(i),
                           -0.3 + 0.05 * static_cast<double>(i));
    return f;
}

struct LinearCoefficients {
    std::array<double, 12> state{};
    std::array<std::array<double, 4>, 12> forcing{};
};

LinearCoefficients linear_coefficients() {
    LinearCoefficients c;
    for (size_t i = 0; i < 12; ++i) {
        c.state[i] = 0.35 + 0.04 * static_cast<double>(i);
        for (size_t j = 0; j < 4; ++j)
            c.forcing[i][j] = (0.015 + 0.002 * static_cast<double>(i + 1)) *
                              (0.4 + 0.3 * static_cast<double>(j));
    }
    return c;
}

State linear_output(const State& state, const Forcing& forcing,
                    const LinearCoefficients& c) {
    State out;
    auto xs = state.fields();
    auto fs = forcing.fields();
    auto ys = out.fields();
    for (size_t i = 0; i < 12; ++i) {
        *ys[i] = c.state[i] * *xs[i];
        for (size_t j = 0; j < 4; ++j)
            *ys[i] = *ys[i] + c.forcing[i][j] * *fs[j];
    }
    return out;
}

Forcing zero_forcing_direction(const Forcing& ref) {
    Forcing f;
    auto r = ref.fields();
    auto o = f.fields();
    for (size_t i = 0; i < 4; ++i) *o[i] = torch::zeros_like(*r[i]);
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

    // Direct joint-Handle contract on an independently specified linear map.
    // This is a mechanics test, not a KDM6/physics result: output field i is
    // a_i*x_i + sum_j b_ij*forcing_j, so the exact 12+4 derivatives are known.
    TEST(joint_handle_linear_map_16_leaves_dot_and_mask) {
        auto st = joint_leaf_state();
        auto forcing = joint_leaf_forcing();
        const auto coeff = linear_coefficients();
        auto out = linear_output(st, forcing, coeff);
        Handle handle(st, out, forcing, make_parameters(0), 1.0, false);

        State u = unit_state(101, torch::kFloat64);
        State v = scaled_direction(st, 103, 2.0e-2);
        Forcing vf;
        GraphOptions keep_graph;
        keep_graph.retain_graph = true;
        auto vff = vf.fields();
        auto ref = forcing.fields();
        for (size_t j = 0; j < 4; ++j)
            *vff[j] = (0.03 * static_cast<double>(j + 1)) * torch::ones_like(*ref[j]);

        auto actual_jvp = handle.jvp_state_forcing(v, vf, keep_graph);
        State expected_jvp;
        auto ej = expected_jvp.fields();
        auto sf = v.fields();
        for (size_t i = 0; i < 12; ++i) {
            *ej[i] = coeff.state[i] * *sf[i];
            for (size_t j = 0; j < 4; ++j)
                *ej[i] = *ej[i] + coeff.forcing[i][j] * *vff[j];
        }
        auto actual_jvp_fields = actual_jvp.fields();
        auto expected_jvp_fields = expected_jvp.fields();
        for (size_t i = 0; i < 12; ++i) {
            if (!torch::allclose(*actual_jvp_fields[i], *expected_jvp_fields[i], 1e-13, 1e-13))
                fail("joint linear JVP differs from analytic 16-leaf map at state field " + std::to_string(i));
        }

        auto actual_vjp = handle.vjp_state_forcing(u, keep_graph);
        State expected_state;
        Forcing expected_forcing;
        auto expected_gs = expected_state.fields();
        auto expected_gf = expected_forcing.fields();
        auto uf = u.fields();
        for (size_t i = 0; i < 12; ++i)
            *expected_gs[i] = coeff.state[i] * *uf[i];
        for (size_t j = 0; j < 4; ++j) {
            *expected_gf[j] = torch::zeros_like(*ref[j]);
            for (size_t i = 0; i < 12; ++i)
                *expected_gf[j] = *expected_gf[j] + coeff.forcing[i][j] * *uf[i];
        }
        auto gs = actual_vjp.state.fields();
        auto gf = actual_vjp.forcing.fields();
        for (size_t i = 0; i < 12; ++i)
            if (!torch::allclose(*gs[i], *expected_gs[i], 1e-13, 1e-13))
                fail("joint linear VJP state block differs at field " + std::to_string(i));
        for (size_t j = 0; j < 4; ++j)
            if (!torch::allclose(*gf[j], *expected_gf[j], 1e-13, 1e-13))
                fail("joint linear VJP forcing block differs at field " + std::to_string(j));

        const double lhs = state_dot(actual_jvp, u).item<double>();
        double rhs = state_dot(v, actual_vjp.state).item<double>();
        auto vforcing = vf.fields();
        for (size_t j = 0; j < 4; ++j) rhs += (*vforcing[j] * *gf[j]).sum().item<double>();
        if (std::fabs(lhs-rhs) > 1e-12 * std::max({1.0, std::fabs(lhs), std::fabs(rhs)}))
            fail("joint linear map violates the 12+4 adjoint identity");

        GraphOptions masked;
        masked.active_field_mask = kAllStateFields & ~(1u << 2);
        masked.retain_graph = true;
        auto masked_jvp = handle.jvp_state_forcing(v, vf, masked);
        auto masked_vjp = handle.vjp_state_forcing(u, masked);
        if ((*masked_vjp.state.fields()[2] != 0).any().item<bool>())
            fail("joint VJP state mask did not zero the disabled state block");
        auto masked_vjp_forcing = masked_vjp.forcing.fields();
        for (size_t j = 0; j < 4; ++j)
            if (!torch::equal(*masked_vjp_forcing[j], *gf[j]))
                fail("state active mask incorrectly masked a forcing cotangent");
        const double masked_lhs = state_dot(masked_jvp, u).item<double>();
        double masked_rhs = state_dot(v, masked_vjp.state).item<double>();
        for (size_t j = 0; j < 4; ++j)
            masked_rhs += (*vforcing[j] * *masked_vjp_forcing[j]).sum().item<double>();
        if (std::fabs(masked_lhs-masked_rhs) >
            1e-12 * std::max({1.0, std::fabs(masked_lhs), std::fabs(masked_rhs)}))
            fail("masked joint 12+4 tangent/adjoint identity failed");
        handle.close();
    } END_TEST();

    TEST(joint_handle_rejects_frozen_nonleaf_aliased_and_bad_forcing_directions) {
        auto st = joint_leaf_state();
        auto forcing = joint_leaf_forcing();
        auto out = linear_output(st, forcing, linear_coefficients());
        Handle handle(st, out, forcing, make_parameters(0), 1.0, false);
        auto direction = scaled_direction(st, 107, 1.0e-2);
        auto forcing_direction = zero_forcing_direction(forcing);
        GraphOptions keep_graph;
        keep_graph.retain_graph = true;
        forcing_direction.pii = torch::ones({2, 1}, torch::kFloat64); // same numel, wrong shape
        bool threw = false;
        try { (void)handle.jvp_state_forcing(direction, forcing_direction); }
        catch (const std::exception&) { threw = true; }
        if (!threw) fail("joint JVP accepted broadcast-compatible forcing shape");

        forcing_direction = zero_forcing_direction(forcing);
        forcing_direction.rho = torch::ones({1, 2}, torch::kFloat32);
        threw = false;
        try { (void)handle.jvp_state_forcing(direction, forcing_direction); }
        catch (const std::exception&) { threw = true; }
        if (!threw) fail("joint JVP accepted forcing direction with wrong dtype");

        // Metadata rejection must happen before autograd and leave the live
        // joint graph usable for a later valid derivative call.
        forcing_direction = zero_forcing_direction(forcing);
        auto jv = handle.jvp_state_forcing(direction, forcing_direction, keep_graph);
        auto grad = handle.vjp_state_forcing(unit_state(109, torch::kFloat64), keep_graph);
        if (!torch::isfinite(state_dot(jv, jv)).item<bool>() ||
            !torch::isfinite(state_dot(grad.state, grad.state)).item<bool>())
            fail("joint graph unusable after rejected forcing directions");
        handle.close();

        auto reject_forcing = [&](Forcing bad, const char* message) {
            auto x = joint_leaf_state();
            auto y = linear_output(x, bad, linear_coefficients());
            Handle candidate(x, y, bad, make_parameters(0), 1.0, false);
            bool rejected = false;
            try { (void)candidate.vjp_state_forcing(unit_state(113, torch::kFloat64)); }
            catch (const std::exception&) { rejected = true; }
            if (!rejected) fail(message);
            candidate.close();
        };

        auto frozen = joint_leaf_forcing();
        for (auto* p : frozen.fields()) *p = p->detach().clone();
        reject_forcing(frozen, "joint VJP accepted frozen forcing leaves");

        auto nonleaf = joint_leaf_forcing();
        nonleaf.rho = nonleaf.rho * 2.0;
        reject_forcing(nonleaf, "joint VJP accepted non-leaf forcing");

        auto alias_state = joint_leaf_state();
        auto aliased = joint_leaf_forcing();
        aliased.rho = alias_state.th;
        auto alias_out = linear_output(alias_state, aliased, linear_coefficients());
        Handle alias_handle(alias_state, alias_out, aliased, make_parameters(0), 1.0, false);
        threw = false;
        try { (void)alias_handle.vjp_state_forcing(unit_state(127, torch::kFloat64)); }
        catch (const std::exception&) { threw = true; }
        if (!threw) fail("joint VJP accepted repeated state/forcing TensorImpl");
        alias_handle.close();
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

    // create_graph is a JVP contract, too: the tangent returned by the
    // double-VJP route must remain differentiable when requested.  This
    // catches a second autograd::grad call that silently hardcodes
    // create_graph=false while ordinary first-order JVP still passes.
    TEST(jvp_create_graph_ready) {
        auto st = mk_state(torch::kFloat64, true);
        auto res = kdm6_step(st, mk_forcing(torch::kFloat64), make_parameters(0), kDt, false);
        auto v = scaled_direction(st, 37);
        GraphOptions opts;
        opts.create_graph = true;
        auto jv = res.handle->jvp(v, opts);

        bool any_requires_grad = false;
        torch::Tensor probe = torch::zeros({}, torch::kFloat64);
        for (auto* p : jv.fields()) {
            any_requires_grad = any_requires_grad || p->requires_grad();
            probe = probe + (*p * *p).sum();
        }
        if (!any_requires_grad || !probe.requires_grad())
            fail("JVP create_graph=true returned a detached tangent");

        std::vector<torch::Tensor> leaves;
        for (auto* p : st.fields()) leaves.push_back(*p);
        auto second = torch::autograd::grad({probe}, leaves, {}, false, false, true);
        bool any_second = false;
        for (const auto& g : second) {
            if (g.defined()) {
                if (!torch::isfinite(g).all().item<bool>())
                    fail("JVP higher-order derivative is non-finite");
                any_second = any_second || (g != 0).any().item<bool>();
            }
        }
        if (!any_second) fail("JVP create_graph higher-order derivative is all-zero");
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

    // The direct runtime owns the same exact (B,K) State/Forcing contract as
    // Python.  Use fields not consumed by sedimentation so this test proves
    // the top-level guard rather than a downstream helper guard; dt=0 also
    // must reject malformed inputs before its identity return.
    TEST(runtime_shape_contract_rejects_broadcast) {
        auto st = mk_state(torch::kFloat64, false);
        auto f = mk_forcing(torch::kFloat64);

        auto bad_forcing = f;
        bad_forcing.pii = torch::ones({1, 1}, torch::kFloat64);
        bool threw = false;
        try {
            (void)kdm6_step(st, bad_forcing, make_parameters(0), kDt, true);
        } catch (const std::exception&) {
            threw = true;
        }
        if (!threw) fail("broadcast-compatible forcing.pii was accepted");

        auto bad_state = st;
        bad_state.qv = torch::ones({1, 1}, torch::kFloat64);
        threw = false;
        try {
            (void)kdm6_step(bad_state, f, make_parameters(0), /*dt=*/0.0, true);
        } catch (const std::exception&) {
            threw = true;
        }
        if (!threw) fail("malformed state.qv bypassed the dt<=0 shape guard");
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
