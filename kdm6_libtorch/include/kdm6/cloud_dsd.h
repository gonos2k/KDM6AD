#pragma once
//
// KDM6 cloud DSD diagnostics — Cohard-Pinty modified-gamma cloud distribution.
// Python oracle: kdm6_torch/kdm6/cloud_dsd.py
//
// Functions:
//   - diag_cloud_slope     rslopec = 1/lamdac (with [1/lamdacmax, 1/lamdacmin] clamp)
//   - diag_avedia_cloud    avedia_c = rslopec · g3pmc^(1/3)         (Fortran 1620)
//   - diag_avedia_rain     avedia_r = rslope_r · (g4pmr/g1pmr)^(1/3)(Fortran 1621)
//   - diag_sigma_cloud     sigma_c  = rslopec · (g6pmc - g3pmc²)^(1/6) (Fortran 1623)
//   - diag_lencon          autoconv→accretion threshold (Fortran 1653-1655)
//   - diag_qcr             sea/land DSD critical mass (Fortran 792-795)
//
// `_rgmma` 부호: review6 audit 후 Γ(x) (= exp(lgamma(x))). Fortran rgmma와 일치.
//
#include "kdm6/constants.h"
#include <torch/torch.h>

namespace kdm6 {
namespace cloud_dsd {

struct CloudDsdParams {
    double pidnc;            // cmc · Γ(1+dmc/(muc+1))
    double dmc;
    double muc;
    double lamdacmax;
    double lamdacmin;
    double g3pmc;            // Γ(1+3/(muc+1))
    double g6pmc;            // Γ(1+6/(muc+1))
    double g4pmr_over_g1pmr; // Γ(4+mur)/Γ(1+mur)
    double qc0;              // continental critical (4/3·π·denr·r0³·xncr0/den0)
    double qc1;              // maritime    critical
};

CloudDsdParams default_cloud_dsd_params(double den0 = constants::DEN0);

// General species DSD slope: rslope = 1/lamda with clamp to [1/lamdamax, 1/lamdamin],
// where lamda = (pidn · n / (q·den))^(1/dm). This is the elementwise core shared by
// cloud/rain/ice (Fortran lamdac/lamdar/lamdai). Used to derive n0 intercepts in
// runtime build_default_aux: n0 = n / (rslope · rslope^mu · g1pm)  (Fortran 1385-1387,
// no-clamp branch — identical to the gated lamda-recompute except for the rare
// clamp-fired number back-mutation, which is a second-order effect).
torch::Tensor diag_species_slope_torch(
    const torch::Tensor& q,
    const torch::Tensor& n,
    const torch::Tensor& den,
    double pidn,
    double dm,
    double lamdamax,
    double lamdamin
);

// rslopec = 1/lamdac with clamp to [1/lamdacmax, 1/lamdacmin].
torch::Tensor diag_cloud_slope_torch(
    const torch::Tensor& qc,
    const torch::Tensor& nc,
    const torch::Tensor& den,
    const CloudDsdParams& params
);

// avedia_c = rslopec · g3pmc^(1/3).
torch::Tensor diag_avedia_cloud_torch(
    const torch::Tensor& rslopec,
    const CloudDsdParams& params
);

// avedia_r = rslope_r · (g4pmr/g1pmr)^(1/3).
torch::Tensor diag_avedia_rain_torch(
    const torch::Tensor& rslope_r,
    const CloudDsdParams& params
);

// sigma_c = rslopec · max(g6pmc - g3pmc², EPS)^(1/6).
torch::Tensor diag_sigma_cloud_torch(
    const torch::Tensor& rslopec,
    const CloudDsdParams& params
);

// (lencon, lenconcr) — autoconv-accretion 전환 임계.
struct LenconOutputs {
    torch::Tensor lencon;
    torch::Tensor lenconcr;
};

LenconOutputs diag_lencon_torch(
    const torch::Tensor& qc,
    const torch::Tensor& den,
    const torch::Tensor& avedia_c,
    const torch::Tensor& sigma_c,
    double qcrmin = constants::QCRMIN
);

// qcr: sea(slmsk==2) → qc0, land → qc1. Mirrors Fortran module_mp_kdm6.F:792-797.
// Naming caveat: qc0 (continental) is the LOW-CCN scalar used for SEA;
// qc1 (maritime) is the HIGH-CCN scalar used for LAND. See cloud_dsd.cpp
// (and Python kdm6_torch/kdm6/cloud_dsd.py) for the physical reasoning.
// ref tensor의 dtype/device 따라감.
torch::Tensor diag_qcr_torch(
    const torch::Tensor& sea_mask,
    const CloudDsdParams& params,
    const torch::Tensor& ref
);

}  // namespace cloud_dsd
}  // namespace kdm6
