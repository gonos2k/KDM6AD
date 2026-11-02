#include "kdm6/sedimentation_conservative.h"
#include "kdm6/coordinator.h"
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <locale>
#include <string>

#include <initializer_list>

//
// Conservative-interface sedimentation substeps — 1:1 port of
// oracle/kdm6/sed_conservative.py (the AUTHORITATIVE numerical semantics).
// Dtype discipline follows the LEGACY C++ substep (sedimentation.cpp): falk is
// stored through ONE f32 rounding of the (possibly f64-vt) chain via
// .to(state dtype); everything downstream stays in the state dtype, exactly as
// the legacy file's corresponding operations. The ledger/_SubstepCapture hooks
// of the oracle are analysis-only instrumentation and are not ported.
//

namespace kdm6 {
namespace sed {

namespace {

// The conservative counterfactual has the same direct (B,K)/(B,) input
// contract as the legacy substeps.  Keep this guard metadata-only and before
// K extraction, splitting, or denominator clamps so broadcast-compatible
// malformed grids fail deterministically without changing valid arithmetic.
void require_conservative_column_shapes(
    const torch::Tensor& reference,
    std::initializer_list<torch::Tensor> tensors,
    const torch::Tensor& mstep_col) {
    TORCH_CHECK(reference.defined() && reference.dim() == 2 &&
                    reference.size(0) > 0 && reference.size(1) > 0,
                "conservative sedimentation state must have positive (B, K) shape");
    for (const auto& tensor : tensors) {
        TORCH_CHECK(tensor.defined() && tensor.sizes() == reference.sizes(),
                    "all conservative sedimentation state/work/fall/forcing shapes "
                    "must match (B, K)");
    }
    TORCH_CHECK(mstep_col.defined() && mstep_col.dim() == 1 &&
                    mstep_col.size(0) == reference.size(0),
                "conservative mstep_col must have shape (B,)");
}

std::vector<torch::Tensor> split_columns(const torch::Tensor& x, int64_t K) {
    std::vector<torch::Tensor> cols;
    cols.reserve(K);
    for (int64_t k = 0; k < K; ++k) {
        cols.push_back(x.select(/*dim=*/-1, k));
    }
    return cols;
}

// BEGIN generated KDM6 factorial conservative ice trace
void trace_factorial_ice_layer(
    int n, int64_t k, double dtcld,
    const torch::Tensor& mstep, const torch::Tensor& gate,
    const torch::Tensor& dend, const torch::Tensor& dend_safe,
    const torch::Tensor& delz, const torch::Tensor& delz_safe,
    const torch::Tensor& work1_qi, const torch::Tensor& workn_qi,
    const torch::Tensor& qi_before, const torch::Tensor& ni_before,
    const torch::Tensor& falk_qi, const torch::Tensor& falk_ni,
    const torch::Tensor& out_attempt_qi, const torch::Tensor& out_attempt_ni,
    const torch::Tensor& out_applied_qi, const torch::Tensor& out_applied_ni,
    const torch::Tensor& arrival_applied_qi, const torch::Tensor& arrival_applied_ni,
    const torch::Tensor& qi_after, const torch::Tensor& ni_after) {
    const char* path = std::getenv("KDM6_ICE_BOUNDARY_TRACE");
    if (path == nullptr || *path == '\0') return;
    const torch::Tensor* tensors[] = {
        &mstep, &gate, &dend, &dend_safe, &delz, &delz_safe, &work1_qi, &workn_qi,
        &qi_before, &ni_before, &falk_qi, &falk_ni, &out_attempt_qi, &out_attempt_ni,
        &out_applied_qi, &out_applied_ni, &arrival_applied_qi, &arrival_applied_ni,
        &qi_after, &ni_after};
    for (const auto* t : tensors) {
        TORCH_CHECK(t->scalar_type() == torch::kFloat64,
                    "factorial conservative ice trace requires binary64 tensors");
    }
    torch::NoGradGuard no_grad;
    const char* mode_env = std::getenv("KDM6_ICE_FACTORIAL_MODE");
    const char* mode = (mode_env == nullptr || *mode_env == '\0') ? "legacy" : mode_env;
    const std::string out_path = std::string(path) + ".layers.tsv";
    std::ofstream out(out_path, std::ios::out | std::ios::app);
    TORCH_CHECK(out.good(), "cannot append factorial ice layer trace: ", out_path);
    out.imbue(std::locale::classic());
    out << std::setprecision(17);
    for (int64_t b = 0; b < qi_before.size(0); ++b) {
        auto value = [b](const torch::Tensor& t) { return t.select(0, b).item<double>(); };
        out << "schema=kdm6.ice_factorial_layer.v1 record=ice_factor_layer order=top_first"
            << " factor_mode=" << mode << " recurrence=actual_departure substep=" << n
            << " dtcld_s=" << dtcld << " column=" << b << " level_top0=" << k
            << " mstep=" << value(mstep) << " gate=" << value(gate)
            << " DEND_kg_m3=" << value(dend) << " DEND_safe_kg_m3=" << value(dend_safe)
            << " DELZ_m=" << value(delz) << " DELZ_safe_m=" << value(delz_safe)
            << " work1_qi=" << value(work1_qi) << " workn_qi=" << value(workn_qi)
            << " QI_before_kg_kg=" << value(qi_before)
            << " NI_before_number_m3=" << value(ni_before)
            << " falk_qi_code_value=" << value(falk_qi)
            << " falk_ni_code_value=" << value(falk_ni)
            << " out_attempt_qi=" << value(out_attempt_qi)
            << " out_attempt_ni=" << value(out_attempt_ni)
            << " out_applied_qi=" << value(out_applied_qi)
            << " out_applied_ni=" << value(out_applied_ni)
            << " arrival_applied_qi=" << value(arrival_applied_qi)
            << " arrival_applied_ni=" << value(arrival_applied_ni)
            << " QI_after_kg_kg=" << value(qi_after)
            << " NI_after_number_m3=" << value(ni_after) << '\n';
    }
    TORCH_CHECK(out.good(), "failed writing factorial conservative ice trace");
}
// END generated KDM6 factorial conservative ice trace

}  // namespace

SubstepAdvectionOutputs substep_advection_conservative(
    const SubstepAdvectionInputs& in,
    const torch::Tensor& mstep_col,
    int /*mstepmax*/,
    int n,
    double dtcld,
    const SubstepAdvectionParams& p
) {
    require_conservative_column_shapes(in.state.qr, {
        in.state.nr, in.state.qs, in.state.qg, in.state.brs,
        in.fall_qr_in, in.fall_nr_in, in.fall_qs_in, in.fall_qg_in, in.fall_brs_in,
        in.work1_qr, in.workn_qr, in.work1_qs, in.work1_qg, in.delz, in.dend}, mstep_col);
    const int64_t K = in.state.qr.size(-1);
    // dend_safe/delz_safe are NUMERICAL denominator guards only (ρ and Δz appear
    // in divisors below), NOT a physical threshold — and the three quantities
    // carry different units. Valid meteorological inputs must not activate either
    // floor; the host/replay gates require zero activations.
    auto dend_safe = torch::clamp(in.dend, /*min=*/p.qcrmin);
    auto delz_safe = torch::clamp(in.delz, /*min=*/p.qcrmin);
    // Per-column divisor + gate — identical to the legacy substep (Fortran
    // .../mstep(i) and if(n.le.mstep(i))): divide the numerator by
    // mstep_col_safe (single rounding), gate is exact 0/1.
    auto mstep_col_safe = torch::clamp(mstep_col, /*min=*/1.0);
    auto gate_col = (mstep_col_safe >= static_cast<double>(n)).to(in.state.qr.dtype()); // (B,)

    auto dend_col      = [&](int64_t k) { return in.dend.select(-1, k); };
    auto dend_safe_col = [&](int64_t k) { return dend_safe.select(-1, k); };
    auto delz_col      = [&](int64_t k) { return in.delz.select(-1, k); };
    auto delz_safe_col = [&](int64_t k) { return delz_safe.select(-1, k); };

    // Per-species chain state: q columns, fall columns, and the cell-above's
    // ACTUAL capped outflow (mixing ratio) — the conserved transfer.
    struct SpeciesChain {
        std::vector<torch::Tensor> cols;
        std::vector<torch::Tensor> fall;
        const torch::Tensor* work1;   // E1-normalized fall speed (vt/delz)
        torch::Tensor prev_out;       // dq_out of cell k-1
    };
    SpeciesChain qr{split_columns(in.state.qr, K),  split_columns(in.fall_qr_in, K),  &in.work1_qr, {}};
    SpeciesChain qs{split_columns(in.state.qs, K),  split_columns(in.fall_qs_in, K),  &in.work1_qs, {}};
    SpeciesChain qg{split_columns(in.state.qg, K),  split_columns(in.fall_qg_in, K),  &in.work1_qg, {}};
    SpeciesChain brs{split_columns(in.state.brs, K), split_columns(in.fall_brs_in, K), &in.work1_qg, {}};  // brs rides the graupel fall speed (as legacy)

    auto nr_cols = split_columns(in.state.nr, K);
    auto fall_nr_cols = split_columns(in.fall_nr_in, K);
    torch::Tensor prev_out_nr;

    for (int64_t k = 0; k < K; ++k) {
        // ── extensive mass/volume moments (qr/qs/qg/brs) sharing the ρΔz layer
        // metric: ρΔz-conserving interface transfer. brs is a graupel VOLUME
        // moment, not water mass; it rides the same metric, not the same units. ─
        for (SpeciesChain* s : {&qr, &qs, &qg, &brs}) {
            // falk as in legacy: ONE f32 rounding of the (f64-vt) chain (§34).
            auto falk = (dend_col(k) * s->cols[k] * s->work1->select(-1, k)
                         / mstep_col_safe * gate_col).to(in.state.qr.scalar_type());
            // ACTUAL outflow: raw flux entry-capped by this cell's reservoir.
            auto dq_out = torch::minimum(falk * dtcld / dend_safe_col(k), s->cols[k]);
            // actual-outflow RATE into the fall accumulator, so the chain-end
            // surface accumulation reports the actual bottom outflow.
            s->fall[k] = s->fall[k] + dq_out * dend_safe_col(k) / dtcld;
            if (k == 0) {
                s->cols[k] = s->cols[k] - dq_out;
            } else {
                // mass-conserving transfer of the source cell's actual outflow:
                // ρΔz-converted: algebraically conservative under valid metrics,
                // closing to within a measured f32 roundoff envelope (NOT bit-exact).
                auto dq_in = s->prev_out * (dend_safe_col(k - 1) * delz_col(k - 1))
                             / (dend_safe_col(k) * delz_safe_col(k));
                s->cols[k] = s->cols[k] - dq_out + dq_in;
            }
            s->prev_out = dq_out;
        }

        // ── numbers (nr): legacy's implied Δz-only measure, actual transfer ──
        // (no ρΔz mass conversion on numbers — oracle keeps the legacy form).
        // Reference-faithful ONLY: for a number mixing ratio [#/kg] this does NOT
        // conserve the physical ρΔz·n column-number moment (release science gate).
        auto falk_nr = (nr_cols[k] * in.workn_qr.select(-1, k)
                        / mstep_col_safe * gate_col).to(in.state.qr.scalar_type());
        auto dn_out = torch::minimum(falk_nr * dtcld, nr_cols[k]);
        fall_nr_cols[k] = fall_nr_cols[k] + dn_out / dtcld;
        if (k == 0) {
            nr_cols[k] = nr_cols[k] - dn_out;
        } else {
            auto dn_in = prev_out_nr * delz_col(k - 1) / delz_safe_col(k);
            nr_cols[k] = nr_cols[k] - dn_out + dn_in;
        }
        prev_out_nr = dn_out;
    }

    return SubstepAdvectionOutputs{
        SubstepAdvectionState{
            torch::stack(qr.cols, /*dim=*/-1),
            torch::stack(nr_cols, /*dim=*/-1),
            torch::stack(qs.cols, /*dim=*/-1),
            torch::stack(qg.cols, /*dim=*/-1),
            torch::stack(brs.cols, /*dim=*/-1),
        },
        torch::stack(qr.fall, /*dim=*/-1),
        torch::stack(fall_nr_cols, /*dim=*/-1),
        torch::stack(qs.fall, /*dim=*/-1),
        torch::stack(qg.fall, /*dim=*/-1),
        torch::stack(brs.fall, /*dim=*/-1),
    };
}

IceSubstepOutputs ice_substep_advection_conservative(
    const IceSubstepInputs& in,
    const torch::Tensor& mstep_col,
    int /*mstepmax*/,
    int n,
    double dtcld,
    const SubstepAdvectionParams& p
) {
    require_conservative_column_shapes(in.state.qi, {
        in.state.ni, in.fall_qi_in, in.fall_ni_in,
        in.work1_qi, in.workn_qi, in.delz, in.dend}, mstep_col);
    const int64_t K = in.state.qi.size(-1);
    const bool native_capture = native_capture_active();
    std::string native_ice_stage;
    if (native_capture) {
        native_ice_stage = "ice_sedimentation_conservative_n" + std::to_string(n);
        const char* factor_mode_env = std::getenv("KDM6_ICE_FACTORIAL_MODE");
        const std::string factor_mode = factor_mode_env == nullptr ? "legacy" : factor_mode_env;
        const bool workn_vt_over_delz = factor_mode == "norm_actual" || factor_mode == "norm_cap";
        capture_native_ice_constant(native_ice_stage.c_str(), "dtcld", dtcld, K, static_cast<unsigned long>(n));
        capture_native_ice_constant(native_ice_stage.c_str(), "workn_vt_over_delz", workn_vt_over_delz ? 1.0 : 0.0, K, static_cast<unsigned long>(n));
    }
    auto dend_safe = torch::clamp(in.dend, /*min=*/p.qcrmin);
    auto delz_safe = torch::clamp(in.delz, /*min=*/p.qcrmin);
    auto mstep_col_safe = torch::clamp(mstep_col, /*min=*/1.0);
    auto gate_col = (mstep_col_safe >= static_cast<double>(n)).to(in.state.qi.dtype()); // (B,)

    auto dend_col      = [&](int64_t k) { return in.dend.select(-1, k); };
    auto dend_safe_col = [&](int64_t k) { return dend_safe.select(-1, k); };
    auto delz_col      = [&](int64_t k) { return in.delz.select(-1, k); };
    auto delz_safe_col = [&](int64_t k) { return delz_safe.select(-1, k); };

    auto qi_cols = split_columns(in.state.qi, K);
    auto ni_cols = split_columns(in.state.ni, K);
    auto fall_qi_cols = split_columns(in.fall_qi_in, K);
    auto fall_ni_cols = split_columns(in.fall_ni_in, K);
    torch::Tensor prev_out_qi, prev_out_ni;

    for (int64_t k = 0; k < K; ++k) {
        // falk/falkn: ONE f32 rounding of the f64-vt chain — as legacy ice.
        auto qi_before_k = qi_cols[k];
        auto ni_before_k = ni_cols[k];
        auto fall_qi_before_k = fall_qi_cols[k];
        auto fall_ni_before_k = fall_ni_cols[k];
        auto falk_qi = (dend_col(k) * qi_cols[k] * in.work1_qi.select(-1, k)
                        / mstep_col_safe * gate_col).to(in.state.qi.scalar_type());
        auto falk_ni = (ni_cols[k] * in.workn_qi.select(-1, k)
                        / mstep_col_safe * gate_col).to(in.state.qi.scalar_type());
        // Name the exact source-order operands to the independent departure caps.
        // This preserves the same tensor operations while making attempted and applied
        // amounts separately capturable.
        auto dqi_out_attempt = falk_qi * dtcld / dend_safe_col(k);
        auto dni_out_attempt = falk_ni * dtcld;
        auto dqi_out = torch::minimum(dqi_out_attempt, qi_cols[k]);
        auto dni_out = torch::minimum(dni_out_attempt, ni_cols[k]);
        // Actual-outflow rates, not candidate falk, enter the cumulative accumulators.
        fall_qi_cols[k] = fall_qi_cols[k] + dqi_out * dend_safe_col(k) / dtcld;
        fall_ni_cols[k] = fall_ni_cols[k] + dni_out / dtcld;
        torch::Tensor dqi_in = torch::zeros_like(dqi_out);
        torch::Tensor dni_in = torch::zeros_like(dni_out);
        if (k == 0) {
            qi_cols[k] = qi_cols[k] - dqi_out;
            ni_cols[k] = ni_cols[k] - dni_out;
        } else {
            // mass: ρΔz-conserving transfer; number: legacy Δz-only measure.
            dqi_in = prev_out_qi * (dend_safe_col(k - 1) * delz_col(k - 1))
                     / (dend_safe_col(k) * delz_safe_col(k));
            // Conservative NI has no arrival reservoir cap: the preceding cell's
            // already-capped actual outflow is transferred using raw dz_above/safe dz_here.
            dni_in = prev_out_ni * delz_col(k - 1) / delz_safe_col(k);
            qi_cols[k] = qi_cols[k] - dqi_out + dqi_in;
            ni_cols[k] = ni_cols[k] - dni_out + dni_in;
        }
        if (native_capture) capture_native_ice_scalar(native_ice_stage.c_str(), "ni_before", ni_before_k, k, static_cast<unsigned long>(n));
        if (native_capture) {
            capture_native_ice_scalar(native_ice_stage.c_str(), "work1_qi", in.work1_qi.select(-1, k), k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "workn_qi", in.workn_qi.select(-1, k), k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "dend", dend_col(k), k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "dend_safe", dend_safe_col(k), k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "delz", delz_col(k), k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "delz_safe", delz_safe_col(k), k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "mstep", mstep_col_safe, k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "gate", gate_col, k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "falk_stored_ni", falk_ni, k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "out_attempt_ni", dni_out_attempt, k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "applied_out_ni", dni_out, k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "in_attempt_ni", dni_in, k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "applied_in_ni", dni_in, k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "fall_ni_before", fall_ni_before_k, k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "ni_after", ni_cols[k], k, static_cast<unsigned long>(n));
            capture_native_ice_scalar(native_ice_stage.c_str(), "fall_ni_after", fall_ni_cols[k], k, static_cast<unsigned long>(n));
        }
        if (native_capture) {
            const auto b = native_capture_column();
            const auto ni_before_b = ni_before_k.select(0, b);
            const auto workn_b = in.workn_qi.select(-1, k).select(0, b);
            const auto mstep_b = mstep_col_safe.select(0, b);
            const auto gate_b = gate_col.select(0, b);
            const auto candidate_pre_store = ni_before_b * workn_b / mstep_b * gate_b;
            capture_native_ice_selected_scalar(native_ice_stage.c_str(), "falk_candidate_pre_store_ni", candidate_pre_store, k, static_cast<unsigned long>(n));
            auto out_capped = (dni_out_attempt.select(0, b) > ni_before_b).to(torch::kFloat64);
            auto out_tie = (dni_out_attempt.select(0, b) == ni_before_b).to(torch::kFloat64);
            capture_native_ice_selected_scalar(native_ice_stage.c_str(), "departure_cap_active", out_capped, k, static_cast<unsigned long>(n));
            capture_native_ice_selected_scalar(native_ice_stage.c_str(), "departure_tie_active", out_tie, k, static_cast<unsigned long>(n));
            const auto expected_after = k == 0
                ? ni_before_b - dni_out.select(0, b)
                : ni_before_b - dni_out.select(0, b) + dni_in.select(0, b);
            const auto projection = ni_cols[k].select(0, b) - expected_after;
            const auto realized_delta = ni_cols[k].select(0, b) - ni_before_b;
            capture_native_ice_selected_scalar(native_ice_stage.c_str(), "state_roundoff_residual_ni", projection, k, static_cast<unsigned long>(n));
            capture_native_ice_selected_scalar(native_ice_stage.c_str(), "realized_delta_ni", realized_delta, k, static_cast<unsigned long>(n));
            if (k == 0) {
                auto zero = torch::zeros_like(ni_before_b);
                capture_native_ice_selected_scalar(native_ice_stage.c_str(), "previous_actual_out_ni", zero, k, static_cast<unsigned long>(n));
            } else {
                capture_native_ice_selected_scalar(native_ice_stage.c_str(), "previous_actual_out_ni", prev_out_ni.select(0, b), k, static_cast<unsigned long>(n));
            }
        }
        if (std::getenv("KDM6_ICE_BOUNDARY_TRACE") != nullptr) {
            trace_factorial_ice_layer(n, k, dtcld, mstep_col_safe, gate_col,
                dend_col(k), dend_safe_col(k), delz_col(k), delz_safe_col(k),
                in.work1_qi.select(-1,k), in.workn_qi.select(-1,k), qi_before_k, ni_before_k,
                falk_qi, falk_ni, dqi_out_attempt, dni_out_attempt, dqi_out, dni_out,
                dqi_in, dni_in, qi_cols[k], ni_cols[k]);
        }
        prev_out_qi = dqi_out;
        prev_out_ni = dni_out;
    }

    return IceSubstepOutputs{
        IceSubstepState{
            torch::stack(qi_cols, /*dim=*/-1),
            torch::stack(ni_cols, /*dim=*/-1),
        },
        torch::stack(fall_qi_cols, /*dim=*/-1),
        torch::stack(fall_ni_cols, /*dim=*/-1),
    };
}

}  // namespace sed
}  // namespace kdm6
