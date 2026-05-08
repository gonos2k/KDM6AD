#include "kdm6/thermo.h"

#include <cmath>

namespace kdm6 {
namespace thermo {

ThermoParams default_thermo_params() {
    const double cpd = 1004.5;
    const double cpv = 1846.0;
    const double cliq = 4218.0;
    const double cice = 2106.0;
    const double rv = 461.5;
    const double rd = 287.04;
    const double t0c = 273.15;
    const double ttp = t0c + 0.01;
    const double xlv0 = 2.5e6;
    const double xls = 2.83e6;
    const double psat = 610.78;
    const double ep2 = rd / rv;

    const double dldt = cliq - cpv;
    const double xa = -dldt / rv;
    const double xb = xa + xlv0 / (rv * ttp);
    const double dldti = cice - cpv;
    const double xai = -dldti / rv;
    const double xbi = xai + xls / (rv * ttp);

    return ThermoParams{
        cpd, cpv, cliq, cice, rv, rd,
        t0c, ttp, xlv0, xls,
        xa, xb, xai, xbi, psat, ep2,
        constants::DEN0, constants::QCRMIN,
    };
}

torch::Tensor compute_cpm(const torch::Tensor& q, const ThermoParams& p) {
    auto q_safe = torch::clamp(q, /*min=*/p.qmin);
    return p.cpd * (1.0 - q_safe) + q_safe * p.cpv;
}

torch::Tensor compute_xl(const torch::Tensor& t, const ThermoParams& p) {
    const double xlv1 = p.cliq - p.cpv;
    return p.xlv0 - xlv1 * (t - p.t0c);
}

torch::Tensor compute_supcol(const torch::Tensor& t, const ThermoParams& p) {
    return p.t0c - torch::clamp(t, /*min=*/153.15, /*max=*/393.15);
}

torch::Tensor compute_qs_water(const torch::Tensor& t, const torch::Tensor& pres, const ThermoParams& p) {
    auto t_safe = torch::clamp(t, /*min=*/1.0);
    auto tr = p.ttp / t_safe;
    auto es = p.psat * torch::exp(torch::log(tr) * p.xa) * torch::exp(p.xb * (1.0 - tr));
    es = torch::minimum(es, 0.99 * pres);
    auto qs = p.ep2 * es / torch::clamp(pres - es, /*min=*/p.qmin);
    return torch::clamp(qs, /*min=*/p.qmin);
}

torch::Tensor compute_qs_ice(const torch::Tensor& t, const torch::Tensor& pres, const ThermoParams& p) {
    auto t_safe = torch::clamp(t, /*min=*/1.0);
    auto tr = p.ttp / t_safe;
    auto es_ice = p.psat * torch::exp(torch::log(tr) * p.xai) * torch::exp(p.xbi * (1.0 - tr));
    auto es_water = p.psat * torch::exp(torch::log(tr) * p.xa) * torch::exp(p.xb * (1.0 - tr));
    auto es_raw = torch::where(t < p.ttp, es_ice, es_water);
    auto es = torch::minimum(es_raw, 0.99 * pres);
    auto qs = p.ep2 * es / torch::clamp(pres - es, /*min=*/p.qmin);
    return torch::clamp(qs, /*min=*/p.qmin);
}

torch::Tensor compute_rh(const torch::Tensor& q, const torch::Tensor& qs, const ThermoParams& p) {
    auto qs_safe = torch::clamp(qs, /*min=*/p.qmin);
    return torch::clamp(q / qs_safe, /*min=*/p.qmin);
}

torch::Tensor compute_supsat(const torch::Tensor& q, const torch::Tensor& qs1, const ThermoParams& p) {
    auto qmin_t = torch::full_like(q, p.qmin);
    return torch::maximum(q, qmin_t) - qs1;
}

torch::Tensor compute_denfac(const torch::Tensor& den, const ThermoParams& p) {
    auto den_safe = torch::clamp(den, /*min=*/p.qmin);
    auto den0_t = torch::full_like(den, p.den0);
    return torch::sqrt(den0_t / den_safe);
}

torch::Tensor compute_work2_venfac(
    const torch::Tensor& pres, const torch::Tensor& t, const torch::Tensor& den,
    const ThermoParams& p
) {
    auto diffus = 8.794e-5 * torch::exp(torch::log(t) * 1.81) / pres;
    auto viscos = 1.496e-6 * (t * torch::sqrt(t)) / (t + 120.0) / den;
    auto den0_t = torch::full_like(t, p.den0);
    auto den_safe = torch::clamp(den, /*min=*/p.qmin);
    return torch::exp(torch::log(viscos / diffus) / 3.0) / torch::sqrt(viscos)
         * torch::sqrt(torch::sqrt(den0_t / den_safe));
}

}  // namespace thermo
}  // namespace kdm6
