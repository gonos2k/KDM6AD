#include "kdm6/sedimentation.h"

namespace kdm6 {
namespace sed {

// ═══════════════════════════════════════════════════════════════════════════
// E1: work / delz normalization
// ═══════════════════════════════════════════════════════════════════════════

torch::Tensor normalize_work_by_delz(const torch::Tensor& work, const torch::Tensor& delz) {
    return work / torch::clamp(delz, /*min=*/constants::QCRMIN);
}

// ═══════════════════════════════════════════════════════════════════════════
// E2: substep advection (qr/nr/qs/qg/brs)
// ═══════════════════════════════════════════════════════════════════════════

SubstepAdvectionParams default_substep_advection_params() {
    return SubstepAdvectionParams{constants::QCRMIN};
}

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

SubstepAdvectionOutputs substep_advection_torch(
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
    // mstep_col: (B,) float, integer-valued, clamped [1,100] by caller.
    // Per-column divisor inv_mstep_col = 1/mstep(i)  (Fortran .../mstep(i)).
    // Per-column gate gate_col = 1 if n<=mstep(i) else 0  (Fortran if(n.le.mstep(i))).
    // Both are (B,) and broadcast against (B,) per-level slices x.select(-1,k).
    // NOTE: the gate is per-COLUMN (level-independent) exactly as Fortran; do NOT
    // index it by k. A (B,1) mask + mask.select(-1,k) would be both physically
    // wrong and an out-of-bounds runtime crash for k>=1.
    auto mstep_col_safe = torch::clamp(mstep_col, /*min=*/1.0);
    auto inv_mstep_col = torch::reciprocal(mstep_col_safe);                 // (B,)
    auto gate_col = (mstep_col_safe >= static_cast<double>(n)).to(in.state.qr.dtype()); // (B,)
    auto falk_scale = inv_mstep_col * gate_col;                             // (B,): divisor*gate

    auto qr_cols = split_columns(in.state.qr, K);
    auto nr_cols = split_columns(in.state.nr, K);
    auto qs_cols = split_columns(in.state.qs, K);
    auto qg_cols = split_columns(in.state.qg, K);
    auto brs_cols = split_columns(in.state.brs, K);
    auto fall_qr_cols = split_columns(in.fall_qr_in, K);
    auto fall_nr_cols = split_columns(in.fall_nr_in, K);
    auto fall_qs_cols = split_columns(in.fall_qs_in, K);
    auto fall_qg_cols = split_columns(in.fall_qg_in, K);
    auto fall_brs_cols = split_columns(in.fall_brs_in, K);

    auto dend_col = [&](int64_t k) { return in.dend.select(-1, k); };
    auto dend_safe_col = [&](int64_t k) { return dend_safe.select(-1, k); };
    auto work1_qr_col = [&](int64_t k) { return in.work1_qr.select(-1, k); };
    auto workn_qr_col = [&](int64_t k) { return in.workn_qr.select(-1, k); };
    auto work1_qs_col = [&](int64_t k) { return in.work1_qs.select(-1, k); };
    auto work1_qg_col = [&](int64_t k) { return in.work1_qg.select(-1, k); };
    auto delz_col = [&](int64_t k) { return in.delz.select(-1, k); };
    auto delz_safe_col = [&](int64_t k) { return delz_safe.select(-1, k); };

    // falk_*_prev carries the cell-above's STORED falk (from ITS entry q) into the interior
    // inflow — Fortran F:1144 stores falk(k) from PRE-update qrs(k), and F:1148-1149/1159-1160/
    // 1165-1166/1171-1172 feed cell k from that STORED falk(k+1), NOT a recompute from the
    // depleted neighbour. (Mirrors the Python sedimentation fix; audit round-2.)
    torch::Tensor falk_qr_prev, falk_nr_prev, falk_qs_prev, falk_qg_prev, falk_brs_prev;

    // Top cell
    {
        const int64_t k = 0;
        auto falk_qr_top = dend_col(k) * qr_cols[k] * work1_qr_col(k) * falk_scale;
        auto falk_nr_top = nr_cols[k] * workn_qr_col(k) * falk_scale;
        auto falk_qs_top = dend_col(k) * qs_cols[k] * work1_qs_col(k) * falk_scale;
        auto falk_qg_top = dend_col(k) * qg_cols[k] * work1_qg_col(k) * falk_scale;
        auto falk_brs_top = dend_col(k) * brs_cols[k] * work1_qg_col(k) * falk_scale;

        fall_qr_cols[k] = fall_qr_cols[k] + falk_qr_top;
        fall_nr_cols[k] = fall_nr_cols[k] + falk_nr_top;
        fall_qs_cols[k] = fall_qs_cols[k] + falk_qs_top;
        fall_qg_cols[k] = fall_qg_cols[k] + falk_qg_top;
        fall_brs_cols[k] = fall_brs_cols[k] + falk_brs_top;

        qr_cols[k] = torch::clamp(qr_cols[k] - falk_qr_top * dtcld / dend_safe_col(k), 0.0);
        nr_cols[k] = torch::clamp(nr_cols[k] - falk_nr_top * dtcld, 0.0);
        qs_cols[k] = torch::clamp(qs_cols[k] - falk_qs_top * dtcld / dend_safe_col(k), 0.0);
        qg_cols[k] = torch::clamp(qg_cols[k] - falk_qg_top * dtcld / dend_safe_col(k), 0.0);
        brs_cols[k] = torch::clamp(brs_cols[k] - falk_brs_top * dtcld / dend_safe_col(k), 0.0);

        falk_qr_prev = falk_qr_top;  falk_nr_prev = falk_nr_top;
        falk_qs_prev = falk_qs_top;  falk_qg_prev = falk_qg_top;  falk_brs_prev = falk_brs_top;
    }

    // Interior cells
    for (int64_t k = 1; k < K; ++k) {
        auto falk_qr_k = dend_col(k) * qr_cols[k] * work1_qr_col(k) * falk_scale;
        auto falk_nr_k = nr_cols[k] * workn_qr_col(k) * falk_scale;
        auto falk_qs_k = dend_col(k) * qs_cols[k] * work1_qs_col(k) * falk_scale;
        auto falk_qg_k = dend_col(k) * qg_cols[k] * work1_qg_col(k) * falk_scale;
        auto falk_brs_k = dend_col(k) * brs_cols[k] * work1_qg_col(k) * falk_scale;

        fall_qr_cols[k] = fall_qr_cols[k] + falk_qr_k;
        fall_nr_cols[k] = fall_nr_cols[k] + falk_nr_k;
        fall_qs_cols[k] = fall_qs_cols[k] + falk_qs_k;
        fall_qg_cols[k] = fall_qg_cols[k] + falk_qg_k;
        fall_brs_cols[k] = fall_brs_cols[k] + falk_brs_k;

        auto dqr_k = torch::minimum(falk_qr_k * dtcld / dend_safe_col(k), qr_cols[k]);
        auto dnr_k = torch::minimum(falk_nr_k * dtcld, nr_cols[k]);
        auto dqs_k = torch::minimum(falk_qs_k * dtcld / dend_safe_col(k), qs_cols[k]);
        auto dqg_k = torch::minimum(falk_qg_k * dtcld / dend_safe_col(k), qg_cols[k]);
        auto dbrs_k = torch::minimum(falk_brs_k * dtcld / dend_safe_col(k), brs_cols[k]);

        // Inflow from the cell above: STORED falk of the cell above (falk_*_prev, from ITS entry
        // q), capped by the cell-above's POST-update reservoir — Fortran min(falk(k+1)*delz_ratio
        // *dtcld/dend, qrs(k+1)) with the stored falk(k+1). The earlier port recomputed falk from
        // the depleted qx_cols[k-1], under-advecting interior mass + attenuating the fall gradient.
        auto delz_ratio = delz_col(k - 1) / delz_safe_col(k);
        auto dqr_above = torch::minimum(
            falk_qr_prev * delz_ratio * dtcld / dend_safe_col(k), qr_cols[k - 1]);
        auto dnr_above = torch::minimum(
            falk_nr_prev * delz_ratio * dtcld, nr_cols[k - 1]);
        auto dqs_above = torch::minimum(
            falk_qs_prev * delz_ratio * dtcld / dend_safe_col(k), qs_cols[k - 1]);
        auto dqg_above = torch::minimum(
            falk_qg_prev * delz_ratio * dtcld / dend_safe_col(k), qg_cols[k - 1]);
        auto dbrs_above = torch::minimum(
            falk_brs_prev * delz_ratio * dtcld / dend_safe_col(k), brs_cols[k - 1]);

        qr_cols[k] = torch::clamp(qr_cols[k] - dqr_k + dqr_above, 0.0);
        nr_cols[k] = torch::clamp(nr_cols[k] - dnr_k + dnr_above, 0.0);
        qs_cols[k] = torch::clamp(qs_cols[k] - dqs_k + dqs_above, 0.0);
        qg_cols[k] = torch::clamp(qg_cols[k] - dqg_k + dqg_above, 0.0);
        brs_cols[k] = torch::clamp(brs_cols[k] - dbrs_k + dbrs_above, 0.0);

        // carry this cell's STORED falk (entry q) as the next cell's "above" inflow flux
        falk_qr_prev = falk_qr_k;  falk_nr_prev = falk_nr_k;
        falk_qs_prev = falk_qs_k;  falk_qg_prev = falk_qg_k;  falk_brs_prev = falk_brs_k;
    }

    return SubstepAdvectionOutputs{
        SubstepAdvectionState{
            torch::stack(qr_cols, /*dim=*/-1),
            torch::stack(nr_cols, /*dim=*/-1),
            torch::stack(qs_cols, /*dim=*/-1),
            torch::stack(qg_cols, /*dim=*/-1),
            torch::stack(brs_cols, /*dim=*/-1),
        },
        torch::stack(fall_qr_cols, /*dim=*/-1),
        torch::stack(fall_nr_cols, /*dim=*/-1),
        torch::stack(fall_qs_cols, /*dim=*/-1),
        torch::stack(fall_qg_cols, /*dim=*/-1),
        torch::stack(fall_brs_cols, /*dim=*/-1),
    };
}

// ═══════════════════════════════════════════════════════════════════════════
// E4: Ice substep
// ═══════════════════════════════════════════════════════════════════════════

IceSubstepOutputs ice_substep_advection_torch(
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
    // Per-column divisor*gate (Fortran .../mstep_i(i) and if(n.le.mstep_i(i))).
    auto mstep_col_safe = torch::clamp(mstep_col, /*min=*/1.0);
    auto inv_mstep_col = torch::reciprocal(mstep_col_safe);                 // (B,)
    auto gate_col = (mstep_col_safe >= static_cast<double>(n)).to(in.state.qi.dtype()); // (B,)
    auto falk_scale = inv_mstep_col * gate_col;                            // (B,)

    auto qi_cols = split_columns(in.state.qi, K);
    auto ni_cols = split_columns(in.state.ni, K);
    auto fall_qi_cols = split_columns(in.fall_qi_in, K);
    auto fall_ni_cols = split_columns(in.fall_ni_in, K);

    auto dend_col = [&](int64_t k) { return in.dend.select(-1, k); };
    auto dend_safe_col = [&](int64_t k) { return dend_safe.select(-1, k); };
    auto work1_qi_col = [&](int64_t k) { return in.work1_qi.select(-1, k); };
    auto workn_qi_col = [&](int64_t k) { return in.workn_qi.select(-1, k); };
    auto delz_col = [&](int64_t k) { return in.delz.select(-1, k); };
    auto delz_safe_col = [&](int64_t k) { return delz_safe.select(-1, k); };

    // falk_*_prev carries the cell-above's STORED falk (entry q) — same Fortran fix as the
    // rain substep (F:1228-1232). (audit round-2)
    torch::Tensor falk_qi_prev, falk_ni_prev;

    // Top
    {
        const int64_t k = 0;
        auto falk_qi_top = dend_col(k) * qi_cols[k] * work1_qi_col(k) * falk_scale;
        auto falk_ni_top = ni_cols[k] * workn_qi_col(k) * falk_scale;
        fall_qi_cols[k] = fall_qi_cols[k] + falk_qi_top;
        fall_ni_cols[k] = fall_ni_cols[k] + falk_ni_top;
        qi_cols[k] = torch::clamp(qi_cols[k] - falk_qi_top * dtcld / dend_safe_col(k), 0.0);
        ni_cols[k] = torch::clamp(ni_cols[k] - falk_ni_top * dtcld, 0.0);
        falk_qi_prev = falk_qi_top;  falk_ni_prev = falk_ni_top;
    }

    for (int64_t k = 1; k < K; ++k) {
        auto falk_qi_k = dend_col(k) * qi_cols[k] * work1_qi_col(k) * falk_scale;
        auto falk_ni_k = ni_cols[k] * workn_qi_col(k) * falk_scale;
        fall_qi_cols[k] = fall_qi_cols[k] + falk_qi_k;
        fall_ni_cols[k] = fall_ni_cols[k] + falk_ni_k;

        auto dqi_k = torch::minimum(falk_qi_k * dtcld / dend_safe_col(k), qi_cols[k]);
        auto dni_k = torch::minimum(falk_ni_k * dtcld, ni_cols[k]);

        // Inflow from above: STORED falk_*_prev (entry q of the cell above), capped by its
        // POST-update reservoir — not a recompute from the depleted neighbour.
        auto delz_ratio = delz_col(k - 1) / delz_safe_col(k);
        auto dqi_above = torch::minimum(
            falk_qi_prev * delz_ratio * dtcld / dend_safe_col(k), qi_cols[k - 1]);
        auto dni_above = torch::minimum(
            falk_ni_prev * delz_ratio * dtcld, ni_cols[k - 1]);

        qi_cols[k] = torch::clamp(qi_cols[k] - dqi_k + dqi_above, 0.0);
        ni_cols[k] = torch::clamp(ni_cols[k] - dni_k + dni_above, 0.0);

        falk_qi_prev = falk_qi_k;  falk_ni_prev = falk_ni_k;  // carry stored falk
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

// ═══════════════════════════════════════════════════════════════════════════
// E5: Surface accumulation
// ═══════════════════════════════════════════════════════════════════════════

SurfaceAccumOutputs surface_accumulation_torch(
    const torch::Tensor& fall_qr_bottom,
    const torch::Tensor& fall_qs_bottom,
    const torch::Tensor& fall_qg_bottom,
    const torch::Tensor& fall_qi_bottom,
    const torch::Tensor& delz_bottom,
    double dtcld
) {
    auto fallsum = fall_qr_bottom + fall_qs_bottom + fall_qg_bottom + fall_qi_bottom;
    auto fallsum_qsi = fall_qs_bottom + fall_qi_bottom;
    auto factor = delz_bottom / constants::DENR * dtcld * 1000.0;
    return SurfaceAccumOutputs{
        /*rain_increment=*/torch::clamp(fallsum, 0.0) * factor,
        /*snow_increment=*/torch::clamp(fallsum_qsi, 0.0) * factor,
        /*graupel_increment=*/torch::clamp(fall_qg_bottom, 0.0) * factor,
    };
}

}  // namespace sed
}  // namespace kdm6
