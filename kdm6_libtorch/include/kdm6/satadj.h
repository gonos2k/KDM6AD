#pragma once
//
// KDM6 saturation adjustment — Step B5.
// 원본: module_mp_kdm6.F: 2990-3011
// Python oracle: kdm6_torch/kdm6/satadj.py
//
// pcond rate만 산출. nccond / state mutation은 caller 처리 (rain_evap와 동일 패턴).
//

#include "kdm6/constants.h"
#include <torch/torch.h>

namespace kdm6 {
namespace satadj {

inline constexpr double DEFAULT_RV = 461.5;  // J/kg/K, water vapor gas constant

struct SatAdjParams {
    double rv;
    double qmin;
};

SatAdjParams default_satadj_params(double rv = DEFAULT_RV);

struct SatAdjOutputs {
    torch::Tensor pcond;
    torch::Tensor cloud_complete_evap;
};

SatAdjOutputs saturation_adjustment_torch(
    const torch::Tensor& t,
    const torch::Tensor& q,
    const torch::Tensor& qc,
    const torch::Tensor& qs1,
    const torch::Tensor& xl,
    const torch::Tensor& cpm,
    const SatAdjParams& params,
    double dtcld
);

}  // namespace satadj
}  // namespace kdm6
