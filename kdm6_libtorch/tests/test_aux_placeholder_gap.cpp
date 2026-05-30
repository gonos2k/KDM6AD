// Operational-aux port verification (formerly the placeholder-gap regression).
//
// build_default_aux now computes n0r/n0i/n0c and work1_water/ice/r from the
// post-staging state (Fortran module_mp_kdm6.f90:1385-1430 + 1629-1630) instead
// of installing static placeholders. This test validates two contracts:
//
//   PART A — VALUE: production aux matches an independent Fortran-style
//   computation at a known cell. work1 uses the exact diffac formula; n0 uses
//   the clamped DSD slope. (Cross-checks the wiring against Fortran ground truth.)
//
//   PART B — AUTOGRAD: the new aux path keeps the differentiable graph intact.
//   This is the project's core requirement (autodiff-capable KDM6 for 4D-Var).
//   The previous placeholders were CONSTANTS — they contributed ZERO gradient,
//   so ∂(rate)/∂(state) was missing the ∂(rate)/∂(aux)·∂(aux)/∂(state) terms.
//   Now aux is a function of state, so those pathways must exist and be nonzero.
//
// Fortran ground truth: module_mp_kdm6.f90:1385-1387 (n0), :1629-1630 (work1=diffac).

#include "kdm6/runtime.h"
#include "kdm6/state.h"
#include "kdm6/thermo.h"

#include <cmath>
#include <iostream>

using namespace kdm6;

namespace {

// Single-cell column matching the verified em_squall2d_x frame-28 peak-QC point
// (T~273K, p~60kPa, qc~9e-3, nc~3.2e9). build_default_aux is elementwise, so one
// cell suffices. `grad` toggles requires_grad on the differentiable leaves.
struct Cell { State s; Forcing f; };

const double P_FULL = 6.047e4;
const double T_CELL = 273.05;

Cell make_test_cell(bool grad) {
    auto opts = torch::TensorOptions().dtype(torch::kFloat64).requires_grad(grad);
    auto plain = torch::TensorOptions().dtype(torch::kFloat64);
    auto leaf  = [&](double v) { return torch::full({1, 1}, v, opts); };
    auto fixed = [&](double v) { return torch::full({1, 1}, v, plain); };

    const double pii = std::pow(P_FULL / 1.0e5, 287.0 / 1004.5);
    const double th  = T_CELL / pii;

    // State field order: th, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg.
    State s{
        /*th=*/leaf(th), /*qv=*/leaf(1.0e-3), /*qc=*/leaf(9.0e-3), /*qr=*/leaf(1.85e-4),
        /*qi=*/leaf(1.0e-6), /*qs=*/leaf(2.7e-5), /*qg=*/leaf(4.1e-4),
        /*nccn=*/fixed(1.0e8), /*nc=*/leaf(3.2e9), /*ni=*/leaf(1.0e3),
        /*nr=*/leaf(5.6e2), /*bg=*/fixed(0.0),
    };
    // Forcing field order: rho, pii, p, delz  (NOT pii,p,rho,delz — struct-order trap).
    Forcing f{
        /*rho=*/fixed(0.7716), /*pii=*/fixed(pii), /*p=*/fixed(P_FULL), /*delz=*/fixed(250.0),
    };
    return {std::move(s), std::move(f)};
}

int g_failures = 0;
void check(bool cond, const std::string& msg) {
    if (!cond) { std::cerr << "  FAIL: " << msg << "\n"; ++g_failures; }
}

}  // namespace

int main() {
    std::cout << "RUN test_operational_aux_port\n";
    auto params = thermo::default_thermo_params();

    // ── PART A: value parity vs independent Fortran-style computation ──────────
    {
        auto cell = make_test_cell(/*grad=*/false);
        auto aux = build_default_aux_for_test(cell.s, cell.f);

        double n0r_p  = aux.n0r.item<double>();
        double n0i_p  = aux.n0i.item<double>();
        double n0c_p  = aux.n0c.item<double>();
        double w1w_p  = aux.work1_water.item<double>();
        double w1i_p  = aux.work1_ice.item<double>();
        double w1r_p  = aux.work1_r.item<double>();
        double n0so_p = aux.n0so.item<double>();
        double n0go_p = aux.n0go.item<double>();

        // Independent Fortran-style work1 = diffac(xl/xls, p, t, den, qs1/qs2).
        auto t_t   = torch::full({1, 1}, T_CELL, torch::kFloat64);
        auto p_t   = torch::full({1, 1}, P_FULL, torch::kFloat64);
        auto den_t = torch::full({1, 1}, 0.7716, torch::kFloat64);
        auto xl    = thermo::compute_xl(t_t, params);
        auto xls_t = torch::full_like(t_t, params.xls);
        auto qs1   = thermo::compute_qs_water(t_t, p_t, params);
        auto qs2   = thermo::compute_qs_ice(t_t, p_t, params);
        double w1w_f = thermo::compute_diffac(xl,    p_t, t_t, den_t, qs1, params).item<double>();
        double w1i_f = thermo::compute_diffac(xls_t, p_t, t_t, den_t, qs2, params).item<double>();

        std::cout << "  work1_water: prod=" << w1w_p << " fortran=" << w1w_f
                  << " (ratio " << w1w_f / w1w_p << ")\n";
        std::cout << "  work1_ice:   prod=" << w1i_p << " fortran=" << w1i_f
                  << " (ratio " << w1i_f / w1i_p << ")\n";
        std::cout << "  n0r=" << n0r_p << "  n0i=" << n0i_p << "  n0c=" << n0c_p
                  << "  n0so=" << n0so_p << "  n0go=" << n0go_p << "\n";

        // work1 must match the diffac formula to floating tolerance (same inputs).
        auto rel = [](double a, double b) { return std::abs(a - b) / std::max(std::abs(b), 1e-300); };
        check(rel(w1w_p, w1w_f) < 1e-6, "work1_water does not match diffac(xl,p,t,den,qs1)");
        check(rel(w1i_p, w1i_f) < 1e-6, "work1_ice does not match diffac(xls,p,t,den,qs2)");
        check(rel(w1r_p, w1w_f) < 1e-6, "work1_r must equal work1_water (Fortran work1(:,:,1))");

        // n0so/n0go collapse to the constants n0s/n0g when mus=mug=0.
        check(rel(n0so_p, 2.0e6) < 1e-9, "n0so should equal n0s=2e6 (mus=0)");
        check(rel(n0go_p, 4.0e6) < 1e-9, "n0go should equal n0g=4e6 (mug=0)");

        // n0 intercepts: physical magnitude (no longer placeholders 8e6/1e6/1e8).
        // Sanity band only — exact value depends on the clamped slope; the squall
        // run is the real parity gate against mp=37.
        check(n0r_p > 1.0e9 && n0r_p < 1.0e11, "n0r out of expected physical band (~1e9-1e10)");
        check(n0i_p > 0.0,                      "n0i should be positive (cell has ice)");
        check(n0c_p > 1.0e20,                   "n0c should be the gamma-normalized scale (>>1e8)");
        check(w1w_p > 1.0e5,                    "work1_water should be physical (~1e6-1e7), not placeholder 1e-3");
    }

    // ── PART B: gradient anchor — the autodiff graph must survive build_default_aux ──
    {
        auto cell = make_test_cell(/*grad=*/true);
        auto aux = build_default_aux_for_test(cell.s, cell.f);

        // Scalarize every aux field that depends on state so a single backward()
        // exercises all new pathways.
        auto loss = aux.n0r.sum() + aux.n0i.sum() + aux.n0c.sum()
                  + aux.work1_water.sum() + aux.work1_ice.sum()
                  + aux.avedia_i.sum() + aux.rslopecmu.sum();
        loss.backward();

        struct Leaf { const char* name; const torch::Tensor& t; };
        // Leaves that MUST receive gradient through the aux computation:
        //   nr → n0r ; ni → n0i, avedia_i ; nc → n0c, rslopecmu ;
        //   qr → n0r(slope) ; qi → n0i(slope) ; qc → rslopec ;
        //   th → t → work1 (diffac depends on T).
        Leaf leaves[] = {
            {"th", cell.s.th}, {"qc", cell.s.qc}, {"qr", cell.s.qr},
            {"qi", cell.s.qi}, {"nc", cell.s.nc}, {"nr", cell.s.nr},
            {"ni", cell.s.ni},
        };
        for (auto& lf : leaves) {
            bool ok = lf.t.grad().defined()
                   && torch::isfinite(lf.t.grad()).all().item<bool>()
                   && lf.t.grad().abs().max().item<double>() > 0.0;
            std::cout << "  grad d(aux)/d(" << lf.name << ") = "
                      << (lf.t.grad().defined() ? lf.t.grad().abs().max().item<double>() : -1.0)
                      << (ok ? "  [ok]" : "  [SEVERED]") << "\n";
            check(ok, std::string("gradient severed or non-finite for leaf ") + lf.name);
        }
    }

    if (g_failures > 0) { std::cerr << g_failures << " check(s) failed\n"; return 1; }
    std::cout << "  PASS  operational aux matches Fortran-style AND preserves autograd graph\n";
    return 0;
}
