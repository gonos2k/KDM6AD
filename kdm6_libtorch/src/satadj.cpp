#include "kdm6/satadj.h"

namespace kdm6 {
namespace satadj {

SatAdjParams default_satadj_params(double rv) {
    return SatAdjParams{
        /*rv=*/rv,
        /*qmin=*/constants::QCRMIN,
    };
}

SatAdjOutputs saturation_adjustment_torch(
    const torch::Tensor& t,
    const torch::Tensor& q,
    const torch::Tensor& qc,
    const torch::Tensor& qs1,
    const torch::Tensor& xl,
    const torch::Tensor& cpm,
    const SatAdjParams& params,
    double dtcld
) {
    // work1 = (max(q, qmin) - qs1) / (1 + xl² · qs1 / (rv · cpm · t²))
    auto t_safe = torch::clamp(t, /*min=*/1.0);
    auto denom = 1.0 + xl * xl * qs1 / (params.rv * cpm * t_safe * t_safe);
    auto qmin_t = torch::full_like(q, params.qmin);
    auto q_eff = torch::maximum(q, qmin_t);
    auto work1 = (q_eff - qs1) / denom;

    // Branch on sign:
    //   work1 > 0          → cond_path = min(work1, max(q, 0)) / dtcld
    //   work1 < 0 and qc>0 → evap_path = max(work1, -qc) / dtcld
    //   else               → 0
    auto zero = torch::zeros_like(q);
    auto cond_path = torch::minimum(work1, torch::maximum(q, zero)) / dtcld;
    auto evap_path = torch::maximum(work1, -qc) / dtcld;

    auto is_super = work1 > 0;
    auto is_sub_with_cloud = torch::logical_and(work1 < 0, qc > 0);

    auto pcond = torch::where(
        is_super, cond_path,
        torch::where(is_sub_with_cloud, evap_path, zero)
    );
    auto cloud_complete_evap = is_sub_with_cloud & (pcond == (-qc / dtcld));
    return SatAdjOutputs{/*pcond=*/pcond, /*cloud_complete_evap=*/cloud_complete_evap};
}

}  // namespace satadj
}  // namespace kdm6
