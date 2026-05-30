#include "kdm6/thermo.h"

#include <cmath>

namespace kdm6 {
namespace thermo {

ThermoParams default_thermo_params() {
    // Values mirror WRF share/module_model_constants.F (significant-digit precision):
    //   r_d=287., r_v=461.6, cp=7*r_d/2=1004.5, cpv=4*r_v=1846.4,
    //   cliq=4190., cice=2106., psat=610.78, XLV=2.5E6, XLS=2.85E6.
    const double cpd = 1004.5;
    const double cpv = 1846.4;     // Fortran: cpv = 4.*r_v = 4*461.6
    const double cliq = 4190.0;    // Fortran cliq (was 4218 in C++)
    const double cice = 2106.0;
    const double rv = 461.6;       // Fortran r_v (was 461.5 in C++)
    const double rd = 287.0;       // Fortran r_d (was 287.04 in C++)
    const double t0c = 273.15;
    const double ttp = t0c + 0.01;
    const double xlv0 = 2.5e6;
    const double xls = 2.85e6;     // Fortran XLS (was 2.83e6 in C++)
    const double psat = 610.78;
    const double ep2 = rd / rv;

    // Fortran kdm6.f90:851-858 — note cvap = cpv (line 851), so dldt sign is
    //   dldt  = cvap - cliq = cpv - cliq   (NOT cliq-cpv as Python oracle has it).
    // Python oracle kdm6_torch/kdm6/thermo.py:73 inverted this sign, and C++
    // mirrored Python. That made xa/xai negative where Fortran has them positive,
    // shifting qs by O(1.7×) at T<200K (cold tropopause cells).
    const double dldt  = cpv - cliq;
    const double xa    = -dldt / rv;                      // = (cliq-cpv)/rv > 0
    const double xb    = xa + xlv0 / (rv * ttp);          // hvap = xlv0
    const double dldti = cpv - cice;
    const double xai   = -dldti / rv;                     // = (cice-cpv)/rv > 0
    const double xbi   = xai + xls / (rv * ttp);          // hsub = xls

    return ThermoParams{
        cpd, cpv, cliq, cice, rv, rd,
        t0c, ttp, xlv0, xls,
        xa, xb, xai, xbi, psat, ep2,
        constants::DEN0,
        constants::QCRMIN,   // TODO: Fortran qmin=epsilon=1e-15 (model_constants.F:10);
                             // switching to EPS broke wrfout flush — deferred.
    };
}

torch::Tensor compute_cpm(const torch::Tensor& q, const ThermoParams& p) {
    auto q_safe = torch::clamp(q, /*min=*/p.qmin);
    return p.cpd * (1.0 - q_safe) + q_safe * p.cpv;
}

torch::Tensor compute_xl(const torch::Tensor& t, const ThermoParams& p) {
    // Fortran kdm6.f90:711 xlcal(x)=xlv0-xlv1*(x-t0c), with xlv1=cl-cpv
    // (kdm6.f90:3052). xlv1 is POSITIVE — distinct from `dldt = cvap-cliq`
    // (NEGATIVE) used in qs's xa/xb formula. Two related-looking expressions,
    // opposite signs — don't conflate (see feedback-dldt-sign-convention).
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

torch::Tensor compute_diffac(
    const torch::Tensor& xl, const torch::Tensor& pres, const torch::Tensor& t,
    const torch::Tensor& den, const torch::Tensor& qs,
    const ThermoParams& p
) {
    // Fortran kdm6.f90:725-728 — diffac = d*a²/(xka*rv*c²) + 1/(e*diffus)
    auto t_safe = torch::clamp(t, /*min=*/1.0);
    auto viscos = 1.496e-6 * (t_safe * torch::sqrt(t_safe)) / (t_safe + 120.0) / torch::clamp(den, /*min=*/p.qmin);
    auto xka = 1.414e3 * viscos * den;
    auto diffus = 8.794e-5 * torch::exp(torch::log(t_safe) * 1.81) / torch::clamp(pres, /*min=*/p.qmin);
    auto qs_safe = torch::clamp(qs, /*min=*/p.qmin);
    auto term1 = den * xl * xl / (xka * p.rv * t_safe * t_safe);
    auto term2 = 1.0 / (qs_safe * diffus);
    return term1 + term2;
}

}  // namespace thermo
}  // namespace kdm6
