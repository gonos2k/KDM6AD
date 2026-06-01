#pragma once
//
// KDM6 thermodynamics 진단 — Step F0.
// Python oracle: kdm6_torch/kdm6/thermo.py
//

#include "kdm6/constants.h"
#include <torch/torch.h>

namespace kdm6 {
namespace thermo {

struct ThermoParams {
    double cpd, cpv, cliq, cice;
    double rv, rd;
    double t0c, ttp;
    double xlv0, xls;
    double xa, xb, xai, xbi;
    double psat, ep2;
    double den0;
    double qmin;
};

ThermoParams default_thermo_params();

torch::Tensor compute_cpm(const torch::Tensor& q, const ThermoParams& p);
torch::Tensor compute_xl(const torch::Tensor& t, const ThermoParams& p);
torch::Tensor compute_supcol(const torch::Tensor& t, const ThermoParams& p);
torch::Tensor compute_qs_water(const torch::Tensor& t, const torch::Tensor& p, const ThermoParams& params);
torch::Tensor compute_qs_ice(const torch::Tensor& t, const torch::Tensor& p, const ThermoParams& params);
torch::Tensor compute_rh(const torch::Tensor& q, const torch::Tensor& qs, const ThermoParams& p);
torch::Tensor compute_supsat(const torch::Tensor& q, const torch::Tensor& qs1, const ThermoParams& p);
torch::Tensor compute_denfac(const torch::Tensor& den, const ThermoParams& p);
torch::Tensor compute_work2_venfac(
    const torch::Tensor& p, const torch::Tensor& t, const torch::Tensor& den,
    const ThermoParams& params
);

// Fortran diffac(a,b,c,d,e) = d*a*a/(xka(c,d)*rv*c*c) + 1/(e*diffus(c,b)) where
//   a=xl (latent heat), b=p (pressure), c=t (temp), d=den, e=qs (sat ratio).
// xka(t,den) = 1.414e3*viscos(t,den)*den.  diffus(t,p) = 8.794e-5*t^1.81/p.
// Reference: module_mp_kdm6.F:775-778. Used in prevp/psevp/pgevp via work1.
torch::Tensor compute_diffac(
    const torch::Tensor& xl, const torch::Tensor& pres, const torch::Tensor& t,
    const torch::Tensor& den, const torch::Tensor& qs,
    const ThermoParams& params
);

}  // namespace thermo
}  // namespace kdm6
