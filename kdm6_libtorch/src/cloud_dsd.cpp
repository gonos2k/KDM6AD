// KDM6 cloud DSD diagnostics — C++ port of kdm6_torch/kdm6/cloud_dsd.py.
// review6 audit fix: rgmma = Γ(x) (= exp(lgamma(x))).
//
#include "kdm6/cloud_dsd.h"

#include <cmath>

namespace kdm6 {
namespace cloud_dsd {

namespace {

constexpr double PI = 3.14159265358979323846;

// Fortran rgmma(x) = exp(GAMMLN(x)) = Γ(x). review6 audit 부호 수정.
inline double rgmma_scalar(double x) {
    return std::exp(std::lgamma(x));
}

constexpr double DOMAIN_FLOOR = 1.0e-30;

}  // namespace

CloudDsdParams default_cloud_dsd_params(double den0) {
    const double cmc = PI * constants::DENR / 6.0;
    const double pidnc = cmc * rgmma_scalar(1.0 + constants::DMC / (constants::MUC + 1.0));
    const double g3pmc = rgmma_scalar(1.0 + 3.0 / (constants::MUC + 1.0));
    const double g6pmc = rgmma_scalar(1.0 + 6.0 / (constants::MUC + 1.0));
    const double g1pmr = rgmma_scalar(1.0 + constants::MUR);
    const double g4pmr = rgmma_scalar(4.0 + constants::MUR);

    const double qc_base = (4.0 / 3.0) * PI * constants::DENR
                         * std::pow(constants::R0, 3.0) / den0;
    const double qc0 = qc_base * constants::XNCR0;
    const double qc1 = qc_base * constants::XNCR1;

    return CloudDsdParams{
        /*pidnc=*/pidnc,
        /*dmc=*/constants::DMC,
        /*muc=*/constants::MUC,
        /*lamdacmax=*/constants::LAMDACMAX,
        /*lamdacmin=*/constants::LAMDACMIN,
        /*g3pmc=*/g3pmc,
        /*g6pmc=*/g6pmc,
        /*g4pmr_over_g1pmr=*/g4pmr / g1pmr,
        /*qc0=*/qc0,
        /*qc1=*/qc1,
    };
}

torch::Tensor diag_species_slope_torch(
    const torch::Tensor& q,
    const torch::Tensor& n,
    const torch::Tensor& den,
    double pidn,
    double dm,
    double lamdamax,
    double lamdamin
) {
    auto qden_safe = torch::clamp(q * den, /*min=*/DOMAIN_FLOOR);
    auto ratio = pidn * n / qden_safe;
    auto lamda = torch::exp(torch::log(torch::clamp(ratio, /*min=*/DOMAIN_FLOOR)) / dm);
    return torch::clamp(
        1.0 / lamda,
        /*min=*/1.0 / lamdamax,
        /*max=*/1.0 / lamdamin
    );
}

torch::Tensor diag_cloud_slope_torch(
    const torch::Tensor& qc,
    const torch::Tensor& nc,
    const torch::Tensor& den,
    const CloudDsdParams& p
) {
    return diag_species_slope_torch(qc, nc, den, p.pidnc, p.dmc, p.lamdacmax, p.lamdacmin);
}

torch::Tensor diag_avedia_cloud_torch(
    const torch::Tensor& rslopec,
    const CloudDsdParams& p
) {
    return rslopec * std::pow(p.g3pmc, 1.0 / 3.0);
}

torch::Tensor diag_avedia_rain_torch(
    const torch::Tensor& rslope_r,
    const CloudDsdParams& p
) {
    return rslope_r * std::pow(p.g4pmr_over_g1pmr, 1.0 / 3.0);
}

torch::Tensor diag_sigma_cloud_torch(
    const torch::Tensor& rslopec,
    const CloudDsdParams& p
) {
    const double raw = p.g6pmc - p.g3pmc * p.g3pmc;
    const double var_factor = std::max(raw, 1.0e-30);
    return rslopec * std::pow(var_factor, 1.0 / 6.0);
}

LenconOutputs diag_lencon_torch(
    const torch::Tensor& qc,
    const torch::Tensor& den,
    const torch::Tensor& avedia_c,
    const torch::Tensor& sigma_c,
    double qcrmin
) {
    auto factor = 1.0e20 / 16.0 * avedia_c * sigma_c.pow(3) - 0.4;
    auto lencon = 2.7e-2 * den * qc * factor;
    auto lenconcr = torch::clamp(1.2 * lencon, /*min=*/qcrmin);
    return LenconOutputs{lencon, lenconcr};
}

torch::Tensor diag_qcr_torch(
    const torch::Tensor& sea_mask,
    const CloudDsdParams& p,
    const torch::Tensor& ref
) {
    // Mirrors operational Fortran module_mp_kdm6.F:792-797 and Python oracle
    // kdm6_torch/kdm6/cloud_dsd.py:diag_qcr_torch:
    //   sea (slmsk==2)  → qc0 (low CCN → low qcr threshold, clean marine air)
    //   land (else)     → qc1 (high CCN → high qcr threshold, dusty air)
    // The Param-field names `qc0/continental`, `qc1/maritime` in CloudDsdParams
    // are legacy labels pinned to scalar values, not the regime mapping; the
    // regime wiring is here.
    auto opts = ref.options();
    auto qc0_t = torch::tensor(p.qc0, opts);
    auto qc1_t = torch::tensor(p.qc1, opts);
    return torch::where(sea_mask, qc0_t, qc1_t);
}

}  // namespace cloud_dsd
}  // namespace kdm6
