#pragma once

#include "kdm6/constants.h"
#include <torch/torch.h>

namespace kdm6 {
namespace slope {

struct SlopeParams {
    double pidnr, pidn0s, pidni;
    double pvtr, pvtrn, pvti, pvtin, pvts;
    double rslopermax, rslopesmax, rslopegmax, rslopeimax;
    double rsloperbmax, rslopesbmax, rslopeibmax;
    double rslopermmax, rslopesmmax, rslopegmmax, rslopeimmax;
    double rsloperdmax, rslopesdmax, rslopegdmax, rslopeidmax;
    double rsloper2max, rslopes2max, rslopeg2max, rslopei2max;
    double rsloper3max, rslopes3max, rslopeg3max, rslopei3max;
};

SlopeParams default_slope_params();

torch::Tensor compute_supcol(const torch::Tensor& t);
torch::Tensor n0sfac(const torch::Tensor& supcol);

struct SlopeOutputs {
    torch::Tensor rslope_r, rslope_s, rslope_g, rslope_i;
    torch::Tensor rslopeb_r, rslopeb_s, rslopeb_g, rslopeb_i;
    torch::Tensor rslopemu_r, rslopemu_s, rslopemu_g, rslopemu_i;
    torch::Tensor rsloped_r, rsloped_s, rsloped_g, rsloped_i;
    torch::Tensor rslope2_r, rslope2_s, rslope2_g, rslope2_i;
    torch::Tensor rslope3_r, rslope3_s, rslope3_g, rslope3_i;
    torch::Tensor vt_r, vt_s, vt_g, vt_i;
    torch::Tensor vtn_r, vtn_i;
    torch::Tensor n0sfac_field;
};

struct SlopeKdm6Inputs {
    torch::Tensor qr, qs, qg, qi;
    torch::Tensor nr, ni;
    torch::Tensor den, denfac, t;
    torch::Tensor pidn0g, pvtg, bvtg, rslopegbmax;
};

SlopeOutputs slope_kdm6_torch(const SlopeKdm6Inputs& inputs, const SlopeParams& params);

struct SlopeRainOutputs {
    torch::Tensor rslope, rslopeb, rslopemu, rsloped;
    torch::Tensor rslope2, rslope3;
    torch::Tensor vt, vtn;
};

SlopeRainOutputs slope_rain_torch(
    const torch::Tensor& qr,
    const torch::Tensor& nr,
    const torch::Tensor& den,
    const torch::Tensor& denfac,
    const torch::Tensor& t,
    const SlopeParams& params
);

}  // namespace slope
}  // namespace kdm6
