#include "kdm6/thermo.h"
#include "kdm6/ops.h"

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

    // Fortran kdm6.F:901-908 — note cvap = cpv (line 901), so dldt sign is
    //   dldt  = cvap - cliq = cpv - cliq   (NOT cliq-cpv as Python oracle has it).
    // Python oracle kdm6_torch/kdm6/thermo.py:73 inverted this sign, and C++
    // mirrored Python. That made xa/xai negative where Fortran has them positive,
    // shifting qs by O(1.7×) at T<200K (cold tropopause cells).
    // STEP-75 SEED (D-A): gfortran evaluates these in REAL(4) stepwise (F:901-908);
    // the double-demote of xai is 1 ULP high (0x3F0FF8E7 vs Fortran 0x3F0FF8E6),
    // and the qs2 shift amplifies through the (rh2-1) cancellation into pidep.
    // Compute all four f32-stepwise, held as doubles (fconst pattern). xa/xb/xbi
    // happen to be bit-identical either way today; xai is the live 1-ULP fix.
    const float cpv_f = 1846.4f, cliq_f = 4190.0f, cice_f = 2106.0f, rv_f = 461.6f;
    const float ttp_f = 273.16f, xlv0_f = 2.5e6f, xls_f = 2.85e6f;
    const double xa    = static_cast<double>(-(cpv_f - cliq_f) / rv_f);
    const double xb    = static_cast<double>(static_cast<float>(xa) + xlv0_f / (rv_f * ttp_f));
    const double xai   = static_cast<double>(-(cpv_f - cice_f) / rv_f);   // 0x3F0FF8E6
    const double xbi   = static_cast<double>(static_cast<float>(xai) + xls_f / (rv_f * ttp_f));

    return ThermoParams{
        cpd, cpv, cliq, cice, rv, rd,
        t0c, ttp, xlv0, xls,
        xa, xb, xai, xbi, psat, ep2,
        constants::DEN0,
        constants::EPS,      // Fortran qmin = epsilon = 1e-15 (model_constants.F:10). 1:1 fix #1.
                             // Faithful floors: cpm clamp(q) F:760, qs floor F:916/927, rh floor
                             // F:917, supsat max(q,qmin) F:1695 (all match Fortran at 1e-15). The
                             // div-safety clamps (pres-es: es<=0.99p ⇒ pres-es>=0.01p; den~1; pres~1e4)
                             // never reach any floor, so 1e-15 vs 1e-9 is inert there. qs is floored at
                             // 1e-15 UPSTREAM (F:916/927); diffac (F:778) then divides by that floored
                             // qs — so this is fully 1:1.
    };
}

torch::Tensor compute_cpm(const torch::Tensor& q, const ThermoParams& p) {
    auto q_safe = torch::clamp(q, /*min=*/p.qmin);
    // Fortran F:760 cpmcal: cpd*(1.-q)+q*cpv — every op individually rounded in
    // source order (-ffp-contract=off; fma_acc is two-rounding).
    auto ab = p.cpd * (1.0 - q_safe);            // first product (scalar*tensor, individually rounded)
    auto cpv_t = torch::full_like(q_safe, p.cpv);
    return ops::fma_acc(ab, q_safe, cpv_t);    // ab + q_safe*cpv  (mul rounds, add rounds)
}

torch::Tensor compute_xl(const torch::Tensor& t, const ThermoParams& p) {
    // Fortran kdm6.F:761 xlcal(x)=xlv0-xlv1*(x-t0c), with xlv1=cl-cpv
    // (kdm6.F:3102). xlv1 is POSITIVE — distinct from `dldt = cvap-cliq`
    // (NEGATIVE) used in qs's xa/xb formula. Two related-looking expressions,
    // opposite signs — don't conflate (see feedback-dldt-sign-convention).
    const double xlv1 = p.cliq - p.cpv;
    // Fortran F:761 xlcal: xlv0 - xlv1*(x-t0c) — multiply rounds, subtract rounds
    // (strict IEEE source order).
    auto dt = t - p.t0c;
    auto acc = torch::full_like(t, p.xlv0);
    auto xlv1_t = torch::full_like(t, xlv1);
    return ops::fma_acc(acc, dt, xlv1_t, -1.0);  // xlv0 - (t-t0c)*xlv1
}

torch::Tensor compute_supcol(const torch::Tensor& t, const ThermoParams& p) {
    // Fortran F:1274/3477 supcol = t0c - t (raw, no clamp). Removing the [153.15,393.15]
    // clamp restores dsupcol/dt at extreme T (AD-faithful) and is a no-op for tropospheric T.
    // 1:1 parity fix #2.
    return p.t0c - t;
}

torch::Tensor compute_qs_water(const torch::Tensor& t, const torch::Tensor& pres, const ThermoParams& p) {
    auto t_safe = torch::clamp(t, /*min=*/1.0);
    auto tr = p.ttp / t_safe;
    // libm exp/log on the float32 operational path so qs1 bit-matches gfortran (the activation
    // seed: a single exp where Sleef!=libm by 1 ULP, amplified by the (q/qs1-1) cancellation).
    auto es = p.psat * ops::libm_exp(ops::libm_log(tr) * p.xa) * ops::libm_exp(p.xb * (1.0 - tr));
    es = torch::minimum(es, 0.99 * pres);
    auto qs = p.ep2 * es / torch::clamp(pres - es, /*min=*/p.qmin);
    return torch::clamp(qs, /*min=*/p.qmin);
}

torch::Tensor compute_qs_ice(const torch::Tensor& t, const torch::Tensor& pres, const ThermoParams& p) {
    auto t_safe = torch::clamp(t, /*min=*/1.0);
    auto tr = p.ttp / t_safe;
    auto es_ice = p.psat * ops::libm_exp(ops::libm_log(tr) * p.xai) * ops::libm_exp(p.xbi * (1.0 - tr));
    auto es_water = p.psat * ops::libm_exp(ops::libm_log(tr) * p.xa) * ops::libm_exp(p.xb * (1.0 - tr));
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
    // Fortran F:919-925: VREC (tvec1 = 1/den, f32) -> tvec1*den0 (f32) -> VSQRT.
    // sqrt(f32(f32(1/den)*den0)), NOT sqrt(den0/den) — the reciprocal-then-multiply
    // tree rounds differently (step-72 cell-B sediment ULP residual).
    auto den_safe = torch::clamp(den, /*min=*/p.qmin);
    auto recip = 1.0 / den_safe;
    return torch::sqrt(recip * p.den0);
}

torch::Tensor compute_work2_venfac(
    const torch::Tensor& pres, const torch::Tensor& t, const torch::Tensor& den,
    const ThermoParams& p
) {
    // Clamp t>=1K (matching compute_qs_water/compute_diffac) so log(t)/sqrt(t) stay finite —
    // AD-hardening for the 4D-Var control th (t=th*pii could transiently go <=0 -> NaN grad).
    // Inert at all physical T (>1K); mirrors the Python venfac fix (sec.20).
    auto t_safe = torch::clamp(t, /*min=*/1.0);
    // libm exp/log on the float32 operational path to bit-match gfortran (Sleef != libm
    // by ~1 ULP). diffus/viscos = A*exp(log(t)*1.81)/y form (F:775-776).
    auto diffus = 8.794e-5 * ops::libm_exp(ops::libm_log(t_safe) * 1.81) / pres;
    auto viscos = 1.496e-6 * (t_safe * torch::sqrt(t_safe)) / (t_safe + 120.0) / den;
    auto den0_t = torch::full_like(t, p.den0);
    auto den_safe = torch::clamp(den, /*min=*/p.qmin);
    // Fortran F:779 venfac uses the truncated literal `.3333333` (NOT 1./3.) — same
    // literal-fidelity class as the rain/ice avedia exponent (#4/#11). 1:1 fix.
    return ops::libm_exp(ops::libm_log(viscos / diffus) * 0.3333333) / torch::sqrt(viscos)
         * torch::sqrt(torch::sqrt(den0_t / den_safe));
}

torch::Tensor compute_diffac(
    const torch::Tensor& xl, const torch::Tensor& pres, const torch::Tensor& t,
    const torch::Tensor& den, const torch::Tensor& qs,
    const ThermoParams& p
) {
    // Fortran kdm6.F:775-778 — diffac = d*a²/(xka*rv*c²) + 1/(e*diffus)
    auto t_safe = torch::clamp(t, /*min=*/1.0);
    auto viscos = 1.496e-6 * (t_safe * torch::sqrt(t_safe)) / (t_safe + 120.0) / torch::clamp(den, /*min=*/p.qmin);
    auto xka = 1.414e3 * viscos * den;
    // libm exp/log on the float32 operational path to bit-match gfortran (F:775 diffus form).
    auto diffus = 8.794e-5 * ops::libm_exp(ops::libm_log(t_safe) * 1.81) / torch::clamp(pres, /*min=*/p.qmin);
    auto qs_safe = torch::clamp(qs, /*min=*/p.qmin);
    auto term1 = den * xl * xl / (xka * p.rv * t_safe * t_safe);
    auto term2 = 1.0 / (qs_safe * diffus);
    // Fortran F:778 diffac = d*a*a/(...) + 1./(...): plain source-order add of two
    // division results — nothing is fused under -ffp-contract=off.
    return term1 + term2;
}

}  // namespace thermo
}  // namespace kdm6
