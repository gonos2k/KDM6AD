#include "kdm6/sedimentation_conservative.h"

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

std::vector<torch::Tensor> split_columns(const torch::Tensor& x, int64_t K) {
    std::vector<torch::Tensor> cols;
    cols.reserve(K);
    for (int64_t k = 0; k < K; ++k) {
        cols.push_back(x.select(/*dim=*/-1, k));
    }
    return cols;
}

}  // namespace

SubstepAdvectionOutputs substep_advection_conservative(
    const SubstepAdvectionInputs& in,
    const torch::Tensor& mstep_col,
    int /*mstepmax*/,
    int n,
    double dtcld,
    const SubstepAdvectionParams& p
) {
    const int64_t K = in.state.qr.size(-1);
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
        // ── mass species (qr/qs/qg/brs): ρΔz-conserving interface transfer ──
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
        // (no ρΔz mass conversion on numbers — oracle keeps the legacy form)
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
    const int64_t K = in.state.qi.size(-1);
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
        auto falk_qi = (dend_col(k) * qi_cols[k] * in.work1_qi.select(-1, k)
                        / mstep_col_safe * gate_col).to(in.state.qi.scalar_type());
        auto falk_ni = (ni_cols[k] * in.workn_qi.select(-1, k)
                        / mstep_col_safe * gate_col).to(in.state.qi.scalar_type());
        // ACTUAL entry-capped outflows.
        auto dqi_out = torch::minimum(falk_qi * dtcld / dend_safe_col(k), qi_cols[k]);
        auto dni_out = torch::minimum(falk_ni * dtcld, ni_cols[k]);
        // actual-outflow rates into the accumulators.
        fall_qi_cols[k] = fall_qi_cols[k] + dqi_out * dend_safe_col(k) / dtcld;
        fall_ni_cols[k] = fall_ni_cols[k] + dni_out / dtcld;
        if (k == 0) {
            qi_cols[k] = qi_cols[k] - dqi_out;
            ni_cols[k] = ni_cols[k] - dni_out;
        } else {
            // mass: ρΔz-conserving transfer; number: legacy Δz-only measure.
            auto dqi_in = prev_out_qi * (dend_safe_col(k - 1) * delz_col(k - 1))
                          / (dend_safe_col(k) * delz_safe_col(k));
            auto dni_in = prev_out_ni * delz_col(k - 1) / delz_safe_col(k);
            qi_cols[k] = qi_cols[k] - dqi_out + dqi_in;
            ni_cols[k] = ni_cols[k] - dni_out + dni_in;
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
