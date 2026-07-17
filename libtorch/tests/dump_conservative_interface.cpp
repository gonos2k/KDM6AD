//
// dump_conservative_interface — oracle cross-check dump tool (NOT a ctest
// test). Prints hexfloat dumps of the conservative-interface variant over a
// fixed fixture set; oracle/tests/test_cpp_conservative_interface_parity.py
// runs this binary as a subprocess, rebuilds the SAME fixtures in Python, and
// compares against oracle/kdm6/sed_conservative.py (the AUTHORITATIVE
// numerical reference — docs/FREEZE_LIFT_CONSERVATIVE_INTERFACE_V1.md).
//
// Output protocol (mirrors test_autograd_endtoend's CPPOUT dumps):
//   <TAG> <field> <hexfloat> <hexfloat> ...        one line per field
// hexfloat is the EXACT fp64 bit pattern (f32 values are printed through an
// exact float->double widening), parsed in Python with float.fromhex — zero
// text truncation. Values are the (B, K) tensor flattened row-major.
//
// Fixture groups (ICs are hardcoded HERE and mirrored in the Python test —
// if you change one side, change BOTH):
//   DS64_*  direct conservative substeps, fp64: uniform cap-inactive, uniform
//           cap-active, variable rho/delz, mixed per-column mstep, per-species
//           isolation (qr/qs/qg+brs/qi with their nr/ni bookkeeping)
//   DS32_*  controlled f32 direct substeps (variable-metric fixture)
//   FS64_*  full conservative kdm6_step (internal fp64, PhysicsOptions
//           ConservativeInterface): 12 state fields + rain/snow/graupel
//           increments; single-subcycle cap-active and dt=300 multi-subcycle
//
#include "kdm6/runtime.h"
#include "kdm6/sedimentation_conservative.h"
#include "kdm6/state.h"

#include <torch/torch.h>

#include <iostream>
#include <string>
#include <vector>

using namespace kdm6;
using namespace kdm6::sed;

namespace {

void dump(const std::string& tag, const char* field, const torch::Tensor& t) {
    torch::NoGradGuard ng;
    auto flat = t.detach().to(torch::kFloat64).reshape({-1}).contiguous();
    std::cout << tag << " " << field << std::hexfloat;
    for (int64_t i = 0; i < flat.numel(); ++i)
        std::cout << " " << flat[i].item<double>();
    std::cout << std::defaultfloat << "\n";
}

torch::Tensor mk(const std::vector<std::vector<double>>& rows, torch::Dtype dt) {
    const int64_t B = static_cast<int64_t>(rows.size());
    const int64_t K = static_cast<int64_t>(rows[0].size());
    auto t = torch::empty({B, K}, torch::TensorOptions().dtype(torch::kFloat64));
    for (int64_t b = 0; b < B; ++b)
        for (int64_t k = 0; k < K; ++k) t.index_put_({b, k}, rows[b][k]);
    return t.to(dt);
}

constexpr double kDtcld = 60.0;

// One direct main-chain fixture: n = 1..nmax substeps with carried state and
// fall accumulators, then dump the final state + fall arrays.
void run_main(const std::string& tag, torch::Dtype dt,
              const std::vector<std::vector<double>>& qr,
              const std::vector<std::vector<double>>& nr,
              const std::vector<std::vector<double>>& qs,
              const std::vector<std::vector<double>>& qg,
              const std::vector<std::vector<double>>& brs,
              double w1_qr, double wn_qr, double w1_qs, double w1_qg,
              const std::vector<std::vector<double>>& rho,
              const std::vector<std::vector<double>>& delz,
              const std::vector<double>& mstep_col, int nmax) {
    auto o = torch::TensorOptions().dtype(dt);
    SubstepAdvectionState st{mk(qr, dt), mk(nr, dt), mk(qs, dt),
                             mk(qg, dt), mk(brs, dt)};
    auto rho_t = mk(rho, dt);
    auto delz_t = mk(delz, dt);
    auto mcol = torch::tensor(mstep_col, torch::kFloat64).to(dt);
    auto z = torch::zeros_like(st.qr);
    torch::Tensor f_qr = z, f_nr = z, f_qs = z, f_qg = z, f_brs = z;
    auto p = default_substep_advection_params();
    for (int n = 1; n <= nmax; ++n) {
        SubstepAdvectionInputs in{
            st, f_qr, f_nr, f_qs, f_qg, f_brs,
            torch::full_like(st.qr, w1_qr), torch::full_like(st.qr, wn_qr),
            torch::full_like(st.qr, w1_qs), torch::full_like(st.qr, w1_qg),
            delz_t, rho_t,
        };
        auto out = substep_advection_conservative(in, mcol, nmax, n, kDtcld, p);
        st = out.state;
        f_qr = out.fall_qr; f_nr = out.fall_nr; f_qs = out.fall_qs;
        f_qg = out.fall_qg; f_brs = out.fall_brs;
    }
    dump(tag, "qr", st.qr);   dump(tag, "nr", st.nr);
    dump(tag, "qs", st.qs);   dump(tag, "qg", st.qg);
    dump(tag, "brs", st.brs);
    dump(tag, "fall_qr", f_qr);   dump(tag, "fall_nr", f_nr);
    dump(tag, "fall_qs", f_qs);   dump(tag, "fall_qg", f_qg);
    dump(tag, "fall_brs", f_brs);
    (void)o;
}

// One direct ice-chain fixture.
void run_ice(const std::string& tag, torch::Dtype dt,
             const std::vector<std::vector<double>>& qi,
             const std::vector<std::vector<double>>& ni,
             double w1_qi, double wn_qi,
             const std::vector<std::vector<double>>& rho,
             const std::vector<std::vector<double>>& delz,
             const std::vector<double>& mstep_col, int nmax) {
    IceSubstepState st{mk(qi, dt), mk(ni, dt)};
    auto rho_t = mk(rho, dt);
    auto delz_t = mk(delz, dt);
    auto mcol = torch::tensor(mstep_col, torch::kFloat64).to(dt);
    auto z = torch::zeros_like(st.qi);
    torch::Tensor f_qi = z, f_ni = z;
    auto p = default_substep_advection_params();
    for (int n = 1; n <= nmax; ++n) {
        IceSubstepInputs in{st, f_qi, f_ni,
                            torch::full_like(st.qi, w1_qi),
                            torch::full_like(st.qi, wn_qi), delz_t, rho_t};
        auto out = ice_substep_advection_conservative(in, mcol, nmax, n, kDtcld, p);
        st = out.state;
        f_qi = out.fall_qi; f_ni = out.fall_ni;
    }
    dump(tag, "qi", st.qi);   dump(tag, "ni", st.ni);
    dump(tag, "fall_qi", f_qi);   dump(tag, "fall_ni", f_ni);
}

// Full conservative step (internal fp64, variant=ConservativeInterface).
// Column values are (K,) with k=0 = SURFACE (WRF staging, as kdm6_step takes).
struct FsCol {
    double th, pii, p;
    std::vector<double> rho, delz;
    double qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg;
};

void run_full(const std::string& tag, const std::vector<FsCol>& cols, double dt) {
    const int64_t B = static_cast<int64_t>(cols.size());
    const int64_t K = static_cast<int64_t>(cols[0].rho.size());
    auto o = torch::TensorOptions().dtype(torch::kFloat64);
    auto fill = [&](double FsCol::* m) {
        auto t = torch::empty({B, K}, o);
        for (int64_t b = 0; b < B; ++b)
            for (int64_t k = 0; k < K; ++k) t.index_put_({b, k}, cols[b].*m);
        return t;
    };
    auto fill_v = [&](std::vector<double> FsCol::* m) {
        auto t = torch::empty({B, K}, o);
        for (int64_t b = 0; b < B; ++b)
            for (int64_t k = 0; k < K; ++k) t.index_put_({b, k}, (cols[b].*m)[k]);
        return t;
    };
    State s;
    s.th = fill(&FsCol::th);     s.qv = fill(&FsCol::qv);
    s.qc = fill(&FsCol::qc);     s.qr = fill(&FsCol::qr);
    s.qi = fill(&FsCol::qi);     s.qs = fill(&FsCol::qs);
    s.qg = fill(&FsCol::qg);     s.nccn = fill(&FsCol::nccn);
    s.nc = fill(&FsCol::nc);     s.ni = fill(&FsCol::ni);
    s.nr = fill(&FsCol::nr);     s.bg = fill(&FsCol::bg);
    Forcing f;
    f.rho = fill_v(&FsCol::rho); f.pii = fill(&FsCol::pii);
    f.p = fill(&FsCol::p);       f.delz = fill_v(&FsCol::delz);

    auto res = kdm6_step(s, f, make_parameters(0), dt, /*value_only=*/true,
                         c10::nullopt, 0.0, 0.0,
                         PhysicsOptions{PhysicsVariant::ConservativeInterface});
    const char* names[12] = {"th", "qv", "qc", "qr", "qi", "qs",
                             "qg", "nccn", "nc", "ni", "nr", "bg"};
    auto fp = res.state_out.fields();
    for (int i = 0; i < 12; ++i) dump(tag, names[i], *fp[i]);
    dump(tag, "rain_increment", res.rain_increment);
    dump(tag, "snow_increment", res.snow_increment);
    dump(tag, "graupel_increment", res.graupel_increment);
}

}  // namespace

int main() {
    at::set_num_threads(1);
    try { at::set_num_interop_threads(1); } catch (...) {}

    // ── shared fixture pieces (K index 0 = TOP for the direct substeps) ─────
    const std::vector<std::vector<double>> UNI_RHO{{1.0, 1.0, 1.0}};
    const std::vector<std::vector<double>> UNI_DZ{{500.0, 500.0, 500.0}};
    const std::vector<std::vector<double>> VAR_RHO{{0.6, 0.9, 1.2}};
    const std::vector<std::vector<double>> VAR_DZ{{300.0, 500.0, 700.0}};
    const std::vector<std::vector<double>> QR1{{3.0e-3, 2.0e-3, 1.0e-3}};
    const std::vector<std::vector<double>> NR1{{2.0e5, 1.5e5, 1.0e5}};
    const std::vector<std::vector<double>> QS1{{1.5e-3, 1.0e-3, 5.0e-4}};
    const std::vector<std::vector<double>> QG1{{1.0e-3, 7.0e-4, 3.0e-4}};
    const std::vector<std::vector<double>> BRS1{{4.0e-6, 3.0e-6, 1.0e-6}};
    const std::vector<std::vector<double>> QI1{{8.0e-4, 5.0e-4, 2.0e-4}};
    const std::vector<std::vector<double>> NI1{{5.0e5, 3.0e5, 1.0e5}};
    const std::vector<std::vector<double>> Z1{{0.0, 0.0, 0.0}};

    // uniform metric, cap-INACTIVE (w1*dtcld <= 0.24 everywhere)
    run_main("DS64_UNI_NOCAP", torch::kFloat64, QR1, NR1, QS1, QG1, BRS1,
             0.004, 0.003, 0.002, 0.003, UNI_RHO, UNI_DZ, {1.0}, 1);
    // uniform metric, cap-ACTIVE (w1*dtcld >= 1.2 -> entry cap binds)
    run_main("DS64_UNI_CAP", torch::kFloat64, QR1, NR1, QS1, QG1, BRS1,
             0.03, 0.02, 0.025, 0.028, UNI_RHO, UNI_DZ, {1.0}, 1);
    // variable rho/delz, mixed regimes
    run_main("DS64_VAR", torch::kFloat64, QR1, NR1, QS1, QG1, BRS1,
             0.02, 0.012, 0.006, 0.015, VAR_RHO, VAR_DZ, {1.0}, 1);
    run_ice("DS64_VAR_ICE", torch::kFloat64, QI1, NI1, 0.02, 0.008,
            VAR_RHO, VAR_DZ, {1.0}, 1);

    // mixed per-column mstep 1/2/3 (mstepmax=3), 3 columns, variable metric
    {
        auto scale3 = [](const std::vector<std::vector<double>>& r) {
            std::vector<std::vector<double>> out;
            for (int b = 0; b < 3; ++b) {
                std::vector<double> row;
                for (double v : r[0]) row.push_back(v * (1.0 + 0.5 * b));
                out.push_back(row);
            }
            return out;
        };
        auto rep3 = [](const std::vector<std::vector<double>>& r) {
            return std::vector<std::vector<double>>{r[0], r[0], r[0]};
        };
        run_main("DS64_MSTEP", torch::kFloat64, scale3(QR1), scale3(NR1),
                 scale3(QS1), scale3(QG1), scale3(BRS1),
                 0.02, 0.012, 0.006, 0.015, rep3(VAR_RHO), rep3(VAR_DZ),
                 {1.0, 2.0, 3.0}, 3);
        run_ice("DS64_MSTEP_ICE", torch::kFloat64, scale3(QI1), scale3(NI1),
                0.02, 0.008, rep3(VAR_RHO), rep3(VAR_DZ), {1.0, 2.0, 3.0}, 3);
    }

    // per-species isolation on the variable metric (other species EXACT zero)
    run_main("DS64_QR", torch::kFloat64, QR1, NR1, Z1, Z1, Z1,
             0.02, 0.012, 0.006, 0.015, VAR_RHO, VAR_DZ, {1.0}, 1);
    run_main("DS64_QS", torch::kFloat64, Z1, Z1, QS1, Z1, Z1,
             0.02, 0.012, 0.006, 0.015, VAR_RHO, VAR_DZ, {1.0}, 1);
    run_main("DS64_QG", torch::kFloat64, Z1, Z1, Z1, QG1, BRS1,
             0.02, 0.012, 0.006, 0.015, VAR_RHO, VAR_DZ, {1.0}, 1);
    run_ice("DS64_QI", torch::kFloat64, QI1, NI1, 0.02, 0.008,
            VAR_RHO, VAR_DZ, {1.0}, 1);

    // controlled f32 (same variable-metric fixture; values printed exactly)
    run_main("DS32_VAR", torch::kFloat32, QR1, NR1, QS1, QG1, BRS1,
             0.02, 0.012, 0.006, 0.015, VAR_RHO, VAR_DZ, {1.0}, 1);
    run_ice("DS32_VAR_ICE", torch::kFloat32, QI1, NI1, 0.02, 0.008,
            VAR_RHO, VAR_DZ, {1.0}, 1);

    // ── full conservative kdm6_step (internal fp64), k=0 = SURFACE ──────────
    // FS64_CAP: single warm rain-cap-active column, dt=60 (one sub-cycle).
    const FsCol rain_cap{290.0, 0.97, 9.0e4,
                         {1.0, 1.0, 1.0, 1.0}, {400.0, 400.0, 400.0, 400.0},
                         1.0e-3, 0.0, 5.0e-3, 0.0, 0.0, 0.0,
                         1.0e9, 1.0e8, 0.0, 1.0e4, 0.0};
    run_full("FS64_CAP", {rain_cap}, 60.0);
    // FS64_MULTI: cap-inactive / rain-cap / mixed-ice non-uniform-metric
    // columns, dt=300 (3 sub-cycles) — same columns as the C3.3 closure gates.
    const FsCol light_rain{290.0, 0.97, 9.0e4,
                           {1.0, 1.0, 1.0, 1.0}, {500.0, 500.0, 500.0, 500.0},
                           1.0e-3, 0.0, 1.0e-5, 0.0, 0.0, 0.0,
                           1.0e9, 1.0e8, 0.0, 1.0e5, 0.0};
    const FsCol mixed_ice{282.4, 0.9031, 7.0e4,
                          {1.2, 1.0, 0.8, 0.6}, {700.0, 600.0, 500.0, 300.0},
                          1.0e-3, 2.0e-4, 1.0e-3, 1.2e-3, 2.0e-3, 2.0e-3,
                          1.0e9, 1.0e8, 1.0e5, 1.0e4, 5.0e-6};
    run_full("FS64_MULTI", {light_rain, rain_cap, mixed_ice}, 300.0);

    return 0;
}
