#pragma once
//
// KDM6 warm rain processes — Lim & Hong / Cohard-Pinty 더블모멘트.
//
// 원본: module_mp_kdm6.F: 1739-1855 (warm rain block 5 process)
//
// Python oracle: kdm6_torch/kdm6/warm.py — 본 헤더와 1:1 정합.
//
// Sub-steps (procedures/kdm62d-port-decomposition.md):
//   B1 autoconv          (Fortran 1758-1769) — autoconv_torch
//   B2 accretion         (Fortran 1771-1794) — accretion_torch
//   B3 self-collection   (Fortran 1799-1826) — self_collection_torch
//   B4 rain evap         (Fortran 1828-1853) — rain_evap_torch
//

#include "kdm6/constants.h"
#include <torch/torch.h>

namespace kdm6 {
namespace warm {

// ─── Step B1: Autoconversion ─────────────────────────────────────────────────

struct WarmAutoconvParams {
    double qck1;         // .104 * 9.8 * peaut / denr^(1/3) / xmyu * den0^(4/3)
    double nraut_coeff;  // 3.5e9
    double qcrmin;
    double ncmin;
};

WarmAutoconvParams default_warm_autoconv_params(double den0 = constants::DEN0);

struct AutoconvOutputs {
    torch::Tensor praut;
    torch::Tensor nraut;
};

AutoconvOutputs autoconv_torch(
    const torch::Tensor& qc,
    const torch::Tensor& nc,
    const torch::Tensor& qr,
    const torch::Tensor& nr,
    const torch::Tensor& den,
    const torch::Tensor& qcr,
    const torch::Tensor& lenconcr,
    const WarmAutoconvParams& params,
    double dtcld
);

// ─── Step B2: Accretion ──────────────────────────────────────────────────────

struct WarmAccretionParams {
    double ncrk1, ncrk2;
    double cmc;          // pi * denr / 6
    double g3pmc, g6pmc, g9pmc;
    double g1pmr, g4pmr, g7pmr;
    double di100;
};

WarmAccretionParams default_warm_accretion_params();

struct AccretionOutputs {
    torch::Tensor pracw;
    torch::Tensor nracw;
};

AccretionOutputs accretion_torch(
    const torch::Tensor& qc,
    const torch::Tensor& nc,
    const torch::Tensor& qr,
    const torch::Tensor& nr,
    const torch::Tensor& den,
    const torch::Tensor& avedia_r,
    const torch::Tensor& rslopec3,
    const torch::Tensor& rslope3_r,
    const torch::Tensor& lenconcr,
    const WarmAccretionParams& params,
    double dtcld
);

// ─── Step B3: Self-collection ────────────────────────────────────────────────

struct WarmSelfCollectionParams {
    double ncrk1, ncrk2;
    double eccbrk;
    double g3pmc, g6pmc;
    double g1pmr, g4pmr, g7pmr;
    double di100, di600, di2000;
};

WarmSelfCollectionParams default_warm_self_collection_params();

struct SelfCollectionOutputs {
    torch::Tensor nccol;
    torch::Tensor nrcol;
};

SelfCollectionOutputs self_collection_torch(
    const torch::Tensor& nc,
    const torch::Tensor& nr,
    const torch::Tensor& qr,
    const torch::Tensor& avedia_c,
    const torch::Tensor& avedia_r,
    const torch::Tensor& rslopec3,
    const torch::Tensor& rslope3_r,
    const torch::Tensor& lenconcr,
    const WarmSelfCollectionParams& params
);

// ─── Step B4: Rain evaporation ───────────────────────────────────────────────

struct WarmRainEvapParams {
    double precr1;       // 2*pi*0.78*g2pmr
    double precr2;       // 2*pi*0.31*sqrt(avtr)*g7pbro2
    double fac_evap;     // 1.0 (yhlee 변경, 원본 1.2)
};

WarmRainEvapParams default_warm_rain_evap_params(double fac_evap = 1.0);

torch::Tensor rain_evap_torch(
    const torch::Tensor& qr,
    const torch::Tensor& rh_w,
    const torch::Tensor& supsat,
    const torch::Tensor& n0r,
    const torch::Tensor& work1_r,
    const torch::Tensor& work2,
    const torch::Tensor& rslope_r,
    const torch::Tensor& rslopeb_r,
    const torch::Tensor& rslope2_r,
    const torch::Tensor& rslopemu_r,
    const WarmRainEvapParams& params,
    double dtcld
);

}  // namespace warm
}  // namespace kdm6
