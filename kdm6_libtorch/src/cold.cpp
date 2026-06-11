#include "kdm6/fconst.h"
#include "kdm6/cold.h"
#include "kdm6/ops.h"

#include <cmath>

namespace kdm6 {
namespace cold {
namespace {

constexpr double PI = 3.14159265358979323846;

double rgmma_scalar(double x) {
    // Fortran rgmma(x)=EXP(GAMMLN(x)) in REAL(4): f32 expf of the f32-rounded
    // double Lanczos — differs from exp(lgamma(double)) for NON-INTEGER args
    // (e.g. Γ(4/3), Γ(7/3) in D2/D3 freezing — the step-67 qi/ni seed class).
    return static_cast<double>(fconst::rgmma_f(static_cast<float>(x)));
}

torch::Tensor wilt_reduction(const torch::Tensor& ratio) {
    auto clamped = torch::clamp(ratio, /*min=*/0.0, /*max=*/1.0);
    return clamped * clamped;
}

}  // namespace

// ═══════════════════════════════════════════════════════════════════════════
// C1: Ice mass accretion (praci + piacr)
// ═══════════════════════════════════════════════════════════════════════════

IceAccretionParams default_ice_accretion_params() {
    const double cmi = PI * constants::DENI / 6.0;
    const double cmr = PI * constants::DENR / 6.0;

    const double g1pmr = rgmma_scalar(1.0 + constants::MUR);
    const double g2pmr = rgmma_scalar(2.0 + constants::MUR);
    const double g3pmr = rgmma_scalar(3.0 + constants::MUR);
    const double g1pdrmr = rgmma_scalar(1.0 + constants::DMR + constants::MUR);
    const double g2pdrmr = rgmma_scalar(2.0 + constants::DMR + constants::MUR);
    const double g3pdrmr = rgmma_scalar(3.0 + constants::DMR + constants::MUR);

    // mui=0 → g1pmi short-circuit
    const double g1pmi = (constants::MUI == 0.0) ? 1.0 : rgmma_scalar(1.0 + constants::MUI);
    const double g2pmi = rgmma_scalar(2.0 + constants::MUI);
    const double g3pmi = rgmma_scalar(3.0 + constants::MUI);
    const double g1pdimi = rgmma_scalar(1.0 + constants::DMI + constants::MUI);
    const double g2pdimi = rgmma_scalar(2.0 + constants::DMI + constants::MUI);
    const double g3pdimi = rgmma_scalar(3.0 + constants::DMI + constants::MUI);

    return IceAccretionParams{
        /*cmi=*/cmi,
        /*cmr=*/cmr,
        /*g1pmr=*/g1pmr, /*g2pmr=*/g2pmr, /*g3pmr=*/g3pmr,
        /*g1pdimi=*/g1pdimi, /*g2pdimi=*/g2pdimi, /*g3pdimi=*/g3pdimi,
        /*g1pmi=*/g1pmi, /*g2pmi=*/g2pmi, /*g3pmi=*/g3pmi,
        /*g1pdrmr=*/g1pdrmr, /*g2pdrmr=*/g2pdrmr, /*g3pdrmr=*/g3pdrmr,
        /*eacri=*/constants::EACRI,
        /*eacir=*/constants::EACIR,
        /*qmin=*/constants::EPS,        // Fortran qmin=epsilon=1e-15 — GATE threshold only; div-safety clamps use qcrmin=1e-9. 1:1 fix #13-17.
        /*qcrmin=*/constants::QCRMIN,
    };
}

IceAccretionOutputs ice_accretion_torch(
    const IceAccretionInputs& in,
    const IceAccretionParams& p,
    double dtcld
) {
    auto active = torch::logical_and(in.qi > p.qmin, in.qr > p.qcrmin);
    auto zero = torch::zeros_like(in.qi);

    auto den_safe = torch::clamp(in.den, /*min=*/p.qcrmin);
    auto qi_safe = torch::clamp(in.qi, /*min=*/p.qcrmin);
    auto qr_safe = torch::clamp(in.qr, /*min=*/p.qcrmin);

    // ── praci: cloud ice collected by rain ──────────────────────────────
    // Fortran acrfac = T1 + 2*T2 + T3 (F:1839-1841). gfortran fuses each term's LAST
    // multiply into the preceding '+' (-ffp-contract=fast) → addcmul chain.
    auto common_i = in.rsloped_i * in.rslopemu_i;
    auto acrfac_pr_t1 =
        p.g3pmr * in.rslopemu_r * in.rslope3_r * p.g1pdimi * common_i * in.rslope_i;
    auto acrfac_pr_t2h = 2.0 * p.g2pmr * in.rslopemu_r * in.rslope2_r * p.g2pdimi * common_i;
    auto acrfac_pr_t3h = p.g1pmr * in.rslopemu_r * in.rslope_r * p.g3pdimi * common_i;
    auto acrfac_pr = ops::fma_acc(
        ops::fma_acc(acrfac_pr_t1, acrfac_pr_t2h, in.rslope2_i),
        acrfac_pr_t3h, in.rslope3_i);

    // n0i is f64 (Fortran DOUBLE, F:697): the chain runs f64 from that factor and
    // rounds ONCE at the rate-array store (F:1876) — wilt/min caps then act on the
    // stored f32 value. No-op .to on the fp64 oracle path. (Applies to every
    // n0i/n0c-consuming rate below.)
    auto praci_raw = (PI * p.cmi * in.n0i * in.n0r * torch::abs(in.vt2r - in.vt2i)
                     / (4.0 * den_safe) * acrfac_pr * p.eacri).to(in.qi.scalar_type());
    auto praci_wilt = praci_raw * wilt_reduction(qr_safe / qi_safe);
    auto praci_capped = torch::minimum(praci_wilt, in.qi / dtcld);
    auto praci = torch::where(active, praci_capped, zero);

    // ── piacr: rain collected by cloud ice ──────────────────────────────
    // F:1854-1856 — last-multiply fusion into each '+'.
    auto common_r = in.rsloped_r * in.rslopemu_r;
    auto acrfac_pi_t1 =
        p.g3pmi * in.rslopemu_i * in.rslope3_i * p.g1pdrmr * common_r * in.rslope_r;
    auto acrfac_pi_t2h = 2.0 * p.g2pmi * in.rslopemu_i * in.rslope2_i * p.g2pdrmr * common_r;
    auto acrfac_pi_t3h = p.g1pmi * in.rslopemu_i * in.rslope_i * p.g3pdrmr * common_r;
    auto acrfac_pi = ops::fma_acc(
        ops::fma_acc(acrfac_pi_t1, acrfac_pi_t2h, in.rslope2_r),
        acrfac_pi_t3h, in.rslope3_r);

    auto piacr_raw = (PI * p.cmr * in.n0i * in.n0r * torch::abs(in.vt2i - in.vt2r)
                     / (4.0 * den_safe) * acrfac_pi * p.eacir).to(in.qr.scalar_type());  // f32 store F:1892
    auto piacr_wilt = piacr_raw * wilt_reduction(qi_safe / qr_safe);
    auto piacr_capped = torch::minimum(piacr_wilt, in.qr / dtcld);
    auto piacr = torch::where(active, piacr_capped, zero);

    return IceAccretionOutputs{/*praci=*/praci, /*piacr=*/piacr};
}

// ═══════════════════════════════════════════════════════════════════════════
// C2: Ice → snow / graupel mass accretion (psaci + pgaci)
// ═══════════════════════════════════════════════════════════════════════════

namespace {

torch::Tensor exp_eac_from_supcol(const torch::Tensor& supcol) {
    auto arg = torch::clamp(0.07 * (-supcol), /*min=*/-80.0, /*max=*/80.0);
    return ops::libm_exp(arg);
}

}  // namespace

IceToSnowGraupelParams default_ice_to_snow_graupel_params() {
    const double cmi = PI * constants::DENI / 6.0;
    const double g1pms = (constants::MUS == 0.0) ? 1.0 : rgmma_scalar(1.0 + constants::MUS);
    const double g2pms = rgmma_scalar(2.0 + constants::MUS);
    const double g3pms = rgmma_scalar(3.0 + constants::MUS);
    const double g1pmg = (constants::MUG == 0.0) ? 1.0 : rgmma_scalar(1.0 + constants::MUG);
    const double g2pmg = rgmma_scalar(2.0 + constants::MUG);
    const double g3pmg = rgmma_scalar(3.0 + constants::MUG);
    const double g1pdimi = rgmma_scalar(1.0 + constants::DMI + constants::MUI);
    const double g2pdimi = rgmma_scalar(2.0 + constants::DMI + constants::MUI);
    const double g3pdimi = rgmma_scalar(3.0 + constants::DMI + constants::MUI);

    return IceToSnowGraupelParams{
        /*cmi=*/cmi,
        /*g1pms=*/g1pms, /*g2pms=*/g2pms, /*g3pms=*/g3pms,
        /*g1pmg=*/g1pmg, /*g2pmg=*/g2pmg, /*g3pmg=*/g3pmg,
        /*g1pdimi=*/g1pdimi, /*g2pdimi=*/g2pdimi, /*g3pdimi=*/g3pdimi,
        /*qmin=*/constants::EPS,        // Fortran qmin=epsilon=1e-15 — GATE threshold only; div-safety clamps use qcrmin=1e-9. 1:1 fix #13-17.
        /*qcrmin=*/constants::QCRMIN,
    };
}

IceToSnowGraupelOutputs ice_to_snow_graupel_torch(
    const IceToSnowGraupelInputs& in,
    const IceToSnowGraupelParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(in.qi);
    auto den_safe = torch::clamp(in.den, /*min=*/p.qcrmin);
    auto qi_safe = torch::clamp(in.qi, /*min=*/p.qcrmin);
    auto qs_safe = torch::clamp(in.qs, /*min=*/p.qcrmin);
    auto qg_safe = torch::clamp(in.qg, /*min=*/p.qcrmin);
    auto common_i = in.rsloped_i * in.rslopemu_i;

    auto eac_temp = exp_eac_from_supcol(in.supcol);

    // ── psaci: snow collects cloud ice ──────────────────────────────────
    auto active_s = torch::logical_and(in.qs > p.qcrmin, in.qi > p.qmin);
    // F:1869-1871 — last-multiply fusion into each '+'.
    auto acrfac_s_t1 =
        p.g3pms * in.rslopemu_s * in.rslope3_s * p.g1pdimi * common_i * in.rslope_i;
    auto acrfac_s_t2h = 2.0 * p.g2pms * in.rslopemu_s * in.rslope2_s * p.g2pdimi * common_i;
    auto acrfac_s_t3h = p.g1pms * in.rslopemu_s * in.rslope_s * p.g3pdimi * common_i;
    auto acrfac_s = ops::fma_acc(
        ops::fma_acc(acrfac_s_t1, acrfac_s_t2h, in.rslope2_i),
        acrfac_s_t3h, in.rslope3_i);

    auto psaci_raw =
        (PI * p.cmi * in.n0i * in.n0so * in.n0sfac * torch::abs(in.vt2s - in.vt2i)
        / (4.0 * den_safe) * acrfac_s * eac_temp).to(in.qi.scalar_type());  // f64 n0i chain, f32 store F:1906
    auto psaci_wilt = psaci_raw * wilt_reduction(qs_safe / qi_safe);
    auto psaci_capped = torch::minimum(psaci_wilt, in.qi / dtcld);
    auto psaci = torch::where(active_s, psaci_capped, zero);

    // ── pgaci: graupel collects cloud ice ───────────────────────────────
    auto active_g = torch::logical_and(in.qg > p.qcrmin, in.qi > p.qmin);
    // F:1883-1885 — last-multiply fusion into each '+'.
    auto acrfac_g_t1 =
        p.g3pmg * in.rslopemu_g * in.rslope3_g * p.g1pdimi * common_i * in.rslope_i;
    auto acrfac_g_t2h = 2.0 * p.g2pmg * in.rslopemu_g * in.rslope2_g * p.g2pdimi * common_i;
    auto acrfac_g_t3h = p.g1pmg * in.rslopemu_g * in.rslope_g * p.g3pdimi * common_i;
    auto acrfac_g = ops::fma_acc(
        ops::fma_acc(acrfac_g_t1, acrfac_g_t2h, in.rslope2_i),
        acrfac_g_t3h, in.rslope3_i);

    auto pgaci_raw =
        (PI * p.cmi * in.n0i * in.n0go * torch::abs(in.vt2g - in.vt2i)
        / (4.0 * den_safe) * acrfac_g * eac_temp).to(in.qi.scalar_type());  // f64 n0i chain, f32 store F:1921
    auto pgaci_wilt = pgaci_raw * wilt_reduction(qg_safe / qi_safe);
    auto pgaci_capped = torch::minimum(pgaci_wilt, in.qi / dtcld);
    auto pgaci = torch::where(active_g, pgaci_capped, zero);

    return IceToSnowGraupelOutputs{/*psaci=*/psaci, /*pgaci=*/pgaci};
}

// ═══════════════════════════════════════════════════════════════════════════
// C2b: Number accretion (nraci + niacr + nsaci + ngaci)
// ═══════════════════════════════════════════════════════════════════════════

NumberAccretionParams default_number_accretion_params() {
    const double g1pmr = rgmma_scalar(1.0 + constants::MUR);
    const double g2pmr = rgmma_scalar(2.0 + constants::MUR);
    const double g3pmr = rgmma_scalar(3.0 + constants::MUR);
    const double g1pmi = (constants::MUI == 0.0) ? 1.0 : rgmma_scalar(1.0 + constants::MUI);
    const double g2pmi = rgmma_scalar(2.0 + constants::MUI);
    const double g3pmi = rgmma_scalar(3.0 + constants::MUI);
    const double g1pms = (constants::MUS == 0.0) ? 1.0 : rgmma_scalar(1.0 + constants::MUS);
    const double g2pms = rgmma_scalar(2.0 + constants::MUS);
    const double g3pms = rgmma_scalar(3.0 + constants::MUS);
    const double g1pmg = (constants::MUG == 0.0) ? 1.0 : rgmma_scalar(1.0 + constants::MUG);
    const double g2pmg = rgmma_scalar(2.0 + constants::MUG);
    const double g3pmg = rgmma_scalar(3.0 + constants::MUG);
    return NumberAccretionParams{
        /*g1pmr=*/g1pmr, /*g2pmr=*/g2pmr, /*g3pmr=*/g3pmr,
        /*g1pmi=*/g1pmi, /*g2pmi=*/g2pmi, /*g3pmi=*/g3pmi,
        /*g1pms=*/g1pms, /*g2pms=*/g2pms, /*g3pms=*/g3pms,
        /*g1pmg=*/g1pmg, /*g2pmg=*/g2pmg, /*g3pmg=*/g3pmg,
        /*eacri=*/constants::EACRI, /*eacir=*/constants::EACIR,
        /*n0s_const=*/constants::N0S, /*n0g_const=*/constants::N0G,
        /*ncmin=*/constants::NCMIN, /*nrmin=*/constants::NRMIN, /*qcrmin=*/constants::QCRMIN,
        /*ncmin_tensor=*/c10::nullopt,
    };
}

NumberAccretionOutputs number_accretion_torch(
    const NumberAccretionInputs& in,
    const NumberAccretionParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(in.qi);

    // Per-cell ncmin (xland-derived, see runtime.cpp). nullopt → scalar fallback.
    auto ni_above_ncmin = p.ncmin_tensor.has_value()
        ? in.ni > p.ncmin_tensor.value()
        : in.ni > p.ncmin;
    auto cold_active = torch::logical_and(in.supcol > 0, ni_above_ncmin);
    auto rain_active = in.nr > p.nrmin;
    auto snow_active = in.qs > p.qcrmin;
    auto graupel_active = in.qg > p.qcrmin;

    auto qi_safe = torch::clamp(in.qi, /*min=*/p.qcrmin);
    auto qr_safe = torch::clamp(in.qr, /*min=*/p.qcrmin);
    auto qs_safe = torch::clamp(in.qs, /*min=*/p.qcrmin);
    auto qg_safe = torch::clamp(in.qg, /*min=*/p.qcrmin);

    auto eac_temp = exp_eac_from_supcol(in.supcol);

    // ── nraci: rain collects ice (number) ───────────────────────────────
    // F:1899-1901 — last-multiply fusion into each '+'.
    auto acrfac_nra_t1 =
        p.g3pmr * in.rslopemu_r * in.rslope3_r * p.g1pmi * in.rslopemu_i * in.rslope_i;
    auto acrfac_nra_t2h = 2.0 * p.g2pmr * in.rslopemu_r * in.rslope2_r * p.g2pmi * in.rslopemu_i;
    auto acrfac_nra_t3h = p.g1pmr * in.rslopemu_r * in.rslope_r * p.g3pmi * in.rslopemu_i;
    auto acrfac_nra = ops::fma_acc(
        ops::fma_acc(acrfac_nra_t1, acrfac_nra_t2h, in.rslope2_i),
        acrfac_nra_t3h, in.rslope3_i);
    auto nraci_raw = (PI * in.n0i * in.n0r * p.eacri * torch::abs(in.vt2r - in.vt2i)
                     * acrfac_nra / 4.0).to(in.ni.scalar_type());  // f64 n0i chain, f32 store F:1902
    auto nraci_wilt = nraci_raw * wilt_reduction(qr_safe / qi_safe);
    auto nraci_capped = torch::minimum(nraci_wilt, in.ni / dtcld);
    auto nraci = torch::where(cold_active & rain_active, nraci_capped, zero);

    // ── niacr: ice collects rain (number) ───────────────────────────────
    // F:1910-1912 — last-multiply fusion into each '+'.
    auto acrfac_nia_t1 =
        p.g3pmi * in.rslopemu_i * in.rslope3_i * p.g1pmr * in.rslopemu_r * in.rslope_r;
    auto acrfac_nia_t2h = 2.0 * p.g2pmi * in.rslopemu_i * in.rslope2_i * p.g2pmr * in.rslopemu_r;
    auto acrfac_nia_t3h = p.g1pmi * in.rslopemu_i * in.rslope_i * p.g3pmr * in.rslopemu_r;
    auto acrfac_nia = ops::fma_acc(
        ops::fma_acc(acrfac_nia_t1, acrfac_nia_t2h, in.rslope2_r),
        acrfac_nia_t3h, in.rslope3_r);
    auto niacr_raw = (PI * in.n0i * in.n0r * p.eacir * torch::abs(in.vt2i - in.vt2r)
                     * acrfac_nia / 4.0).to(in.ni.scalar_type());  // f64 n0i chain, f32 store F:1913
    auto niacr_wilt = niacr_raw * wilt_reduction(qi_safe / qr_safe);
    auto niacr_capped = torch::minimum(niacr_wilt, in.nr / dtcld);
    auto niacr = torch::where(cold_active & rain_active, niacr_capped, zero);

    // ── nsaci: snow collects ice (number) ───────────────────────────────
    // F:1924-1926 — last-multiply fusion into each '+'.
    auto acrfac_nsa_t1 =
        p.g3pms * in.rslopemu_s * in.rslope3_s * p.g1pmi * in.rslopemu_i * in.rslope_i;
    auto acrfac_nsa_t2h = 2.0 * p.g2pms * in.rslopemu_s * in.rslope2_s * p.g2pmi * in.rslopemu_i;
    auto acrfac_nsa_t3h = p.g1pms * in.rslopemu_s * in.rslope_s * p.g3pmi * in.rslopemu_i;
    auto acrfac_nsa = ops::fma_acc(
        ops::fma_acc(acrfac_nsa_t1, acrfac_nsa_t2h, in.rslope2_i),
        acrfac_nsa_t3h, in.rslope3_i);
    auto nsaci_raw = (PI * in.n0i * p.n0s_const * in.n0sfac * eac_temp
                     * torch::abs(in.vt2s - in.vt2i) * acrfac_nsa / 4.0).to(in.ni.scalar_type());  // f32 store F:1927
    auto nsaci_wilt = nsaci_raw * wilt_reduction(qs_safe / qi_safe);
    auto nsaci_capped = torch::minimum(nsaci_wilt, in.ni / dtcld);
    auto nsaci = torch::where(cold_active & snow_active, nsaci_capped, zero);

    // ── ngaci: graupel collects ice (number) ────────────────────────────
    // F:1938-1940 — last-multiply fusion into each '+'.
    auto acrfac_nga_t1 =
        p.g3pmg * in.rslopemu_g * in.rslope3_g * p.g1pmi * in.rslopemu_i * in.rslope_i;
    auto acrfac_nga_t2h = 2.0 * p.g2pmg * in.rslopemu_g * in.rslope2_g * p.g2pmi * in.rslopemu_i;
    auto acrfac_nga_t3h = p.g1pmg * in.rslopemu_g * in.rslope_g * p.g3pmi * in.rslopemu_i;
    auto acrfac_nga = ops::fma_acc(
        ops::fma_acc(acrfac_nga_t1, acrfac_nga_t2h, in.rslope2_i),
        acrfac_nga_t3h, in.rslope3_i);
    auto ngaci_raw = (PI * in.n0i * p.n0g_const * eac_temp
                     * torch::abs(in.vt2g - in.vt2i) * acrfac_nga / 4.0).to(in.ni.scalar_type());  // f32 store F:1941
    auto ngaci_wilt = ngaci_raw * wilt_reduction(qg_safe / qi_safe);
    auto ngaci_capped = torch::minimum(ngaci_wilt, in.ni / dtcld);
    auto ngaci = torch::where(cold_active & graupel_active, ngaci_capped, zero);

    return NumberAccretionOutputs{/*nraci=*/nraci, /*niacr=*/niacr, /*nsaci=*/nsaci, /*ngaci=*/ngaci};
}

// ═══════════════════════════════════════════════════════════════════════════
// C2c: Cloud water riming (8 processes)
// ═══════════════════════════════════════════════════════════════════════════

CloudWaterRimingParams default_cloud_water_riming_params() {
    const double g3pbs = rgmma_scalar(3.0 + constants::BVTS + constants::MUS);
    const double g3pbi = rgmma_scalar(3.0 + constants::BVTI + constants::MUI);
    return CloudWaterRimingParams{
        /*avts=*/constants::AVTS,
        /*avti=*/constants::AVTI,
        /*g3pbs=*/g3pbs,
        /*g3pbi=*/g3pbi,
        /*eacsc=*/constants::EACSC,
        /*eacgc=*/constants::EACGC,
        /*eacic=*/constants::EACIC,
        /*muc=*/constants::MUC,
        /*di50=*/constants::DI50,
        /*qmin=*/constants::EPS,        // Fortran qmin=epsilon=1e-15 — GATE threshold only; div-safety clamps use qcrmin=1e-9. 1:1 fix #13-17.
        /*qcrmin=*/constants::QCRMIN,
        /*ncmin=*/constants::NCMIN,
        /*qsum_floor=*/1.0e-15,
        /*ncmin_tensor=*/c10::nullopt,
    };
}

CloudWaterRimingOutputs cloud_water_riming_torch(
    const CloudWaterRimingInputs& in,
    const CloudWaterRimingParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(in.qc);
    auto qc_safe = torch::clamp(in.qc, /*min=*/p.qcrmin);  // div-safety floor stays 1e-9 (NOT the gate qmin); lowering THIS is the documented flush cause. 1:1 fix #16/#17.

    // ── psacw ──────────────────────────────────────────────────────────
    auto snow_active_qc = torch::logical_and(in.qs > p.qcrmin, in.qc > p.qmin);
    auto psacw_raw =
        in.rslope3_s * in.rslopeb_s * in.rslopemu_s
        * PI * in.n0so * in.n0sfac * p.avts * p.g3pbs * 0.25 * p.eacsc
        * wilt_reduction(in.qs / qc_safe)
        * in.qc * in.denfac;
    auto psacw_capped = torch::minimum(psacw_raw, in.qc / dtcld);
    auto psacw = torch::where(snow_active_qc, psacw_capped, zero);

    // ── nsacw ──────────────────────────────────────────────────────────
    // Per-cell ncmin (xland-derived, see runtime.cpp). nullopt → scalar fallback.
    auto nc_above_ncmin_riming = p.ncmin_tensor.has_value()
        ? in.nc > p.ncmin_tensor.value()
        : in.nc > p.ncmin;
    auto snow_active_nc = torch::logical_and(in.qs > p.qcrmin, nc_above_ncmin_riming);
    // n0c is f64 (Fortran DOUBLE, F:697): number-riming chains run f64 from the
    // n0c factor, rounding ONCE at the rate-array store (no-op .to on fp64 path).
    auto nsacw_raw =
        (PI * p.avts * 0.25 * p.eacsc * in.n0so * in.n0sfac * in.n0c / (p.muc + 1.0)
        * p.g3pbs
        * in.rslope3_s * in.rslopeb_s * in.rslopemu_s
        * in.rslopec * in.rslopecmu
        * wilt_reduction(in.qs / qc_safe)
        * in.denfac).to(in.nc.scalar_type());
    auto nsacw_capped = torch::minimum(nsacw_raw, in.nc / dtcld);
    auto nsacw = torch::where(snow_active_nc, nsacw_capped, zero);

    // ── pgacw ──────────────────────────────────────────────────────────
    auto graupel_active_qc = torch::logical_and(in.qg > p.qcrmin, in.qc > p.qmin);
    auto pgacw_raw =
        in.rslope3_g * in.rslopeb_g * in.rslopemu_g
        * in.qc * PI * in.n0go * in.avtg * in.g3pbg * 0.25 * p.eacgc
        * wilt_reduction(in.qg / qc_safe)
        * in.denfac;
    auto pgacw_capped = torch::minimum(pgacw_raw, in.qc / dtcld);
    auto pgacw = torch::where(graupel_active_qc, pgacw_capped, zero);

    // ── ngacw ──────────────────────────────────────────────────────────
    // Reuse nc_above_ncmin_riming from nsacw block (same per-cell ncmin).
    auto graupel_active_nc = torch::logical_and(in.qg > p.qcrmin, nc_above_ncmin_riming);
    auto ngacw_raw =
        (PI * in.avtg * 0.25 * p.eacgc * in.n0go * in.n0c / (p.muc + 1.0)
        * in.g3pbg
        * in.rslope3_g * in.rslopeb_g * in.rslopemu_g
        * in.rslopec * in.rslopecmu
        * wilt_reduction(in.qg / qc_safe)
        * in.denfac).to(in.nc.scalar_type());  // f64 n0c chain, f32 store
    auto ngacw_capped = torch::minimum(ngacw_raw, in.nc / dtcld);
    auto ngacw = torch::where(graupel_active_nc, ngacw_capped, zero);

    // ── paacw + naacw (qsum-weighted) ──────────────────────────────────
    auto qsum_safe = torch::clamp(in.qs + in.qg, /*min=*/p.qsum_floor);
    auto qsum_active = (in.qs + in.qg) > p.qsum_floor;
    // Fortran (qs*psacw + qg*pgacw)/qsum (F:2001) — gfortran fuses the 2nd product
    // (qg*pgacw) into the add; the /qsum is NOT fused.
    auto paacw_raw = ops::fma_acc(in.qs * psacw, in.qg, pgacw) / qsum_safe;
    auto paacw = torch::where(qsum_active, paacw_raw, zero);
    auto naacw_raw = ops::fma_acc(in.qs * nsacw, in.qg, ngacw) / qsum_safe;
    auto naacw = torch::where(qsum_active, naacw_raw, zero);

    // ── piacw / niacw (PK97 + cold) ────────────────────────────────────
    auto cold_ice = torch::logical_and(
        torch::logical_and(in.supcol > 0, in.qi > p.qcrmin),
        in.avedia_i >= p.di50
    );
    auto piacw_active = torch::logical_and(cold_ice, in.qc > p.qmin);
    auto piacw_raw =
        (in.rslope3_i * in.rslopeb_i * in.rslopemu_i
        * PI * in.n0i * p.avti * p.g3pbi * 0.25 * p.eacic
        * wilt_reduction(in.qi / qc_safe)
        * in.qc * in.denfac).to(in.qc.scalar_type());  // f64 n0i chain, f32 store
    auto piacw_capped = torch::minimum(piacw_raw, in.qc / dtcld);
    auto piacw = torch::where(piacw_active, piacw_capped, zero);

    // Reuse nc_above_ncmin_riming from nsacw block (same per-cell ncmin).
    auto niacw_active = torch::logical_and(cold_ice, nc_above_ncmin_riming);
    auto niacw_raw =
        (PI * p.avti * 0.25 * p.eacic * in.n0i * in.n0c / (p.muc + 1.0)
        * p.g3pbi
        * in.rslope3_i * in.rslopeb_i * in.rslopemu_i
        * in.rslopec * in.rslopecmu
        * wilt_reduction(in.qi / qc_safe)
        * in.denfac).to(in.nc.scalar_type());  // f64 n0i·n0c chain, f32 store
    auto niacw_capped = torch::minimum(niacw_raw, in.nc / dtcld);
    auto niacw = torch::where(niacw_active, niacw_capped, zero);

    return CloudWaterRimingOutputs{
        /*psacw=*/psacw, /*nsacw=*/nsacw, /*pgacw=*/pgacw, /*ngacw=*/ngacw,
        /*paacw=*/paacw, /*naacw=*/naacw, /*piacw=*/piacw, /*niacw=*/niacw,
    };
}

// ═══════════════════════════════════════════════════════════════════════════
// C2d: Rain-snow-graupel collection (6 processes)
// ═══════════════════════════════════════════════════════════════════════════

RainSnowGraupelCollectionParams default_rain_snow_graupel_collection_params() {
    const double cms = PI * constants::DENS / 6.0;
    const double cmr = PI * constants::DENR / 6.0;
    const double g1pms = (constants::MUS == 0.0) ? 1.0 : rgmma_scalar(1.0 + constants::MUS);
    const double g2pms = rgmma_scalar(2.0 + constants::MUS);
    const double g3pms = rgmma_scalar(3.0 + constants::MUS);
    const double g1pmr = rgmma_scalar(1.0 + constants::MUR);
    const double g2pmr = rgmma_scalar(2.0 + constants::MUR);
    const double g3pmr = rgmma_scalar(3.0 + constants::MUR);
    const double g1pmg = (constants::MUG == 0.0) ? 1.0 : rgmma_scalar(1.0 + constants::MUG);
    const double g2pmg = rgmma_scalar(2.0 + constants::MUG);
    const double g3pmg = rgmma_scalar(3.0 + constants::MUG);
    const double g1pdsms = rgmma_scalar(1.0 + constants::DMS + constants::MUS);
    const double g2pdsms = rgmma_scalar(2.0 + constants::DMS + constants::MUS);
    const double g3pdsms = rgmma_scalar(3.0 + constants::DMS + constants::MUS);
    const double g1pdrmr = rgmma_scalar(1.0 + constants::DMR + constants::MUR);
    const double g2pdrmr = rgmma_scalar(2.0 + constants::DMR + constants::MUR);
    const double g3pdrmr = rgmma_scalar(3.0 + constants::DMR + constants::MUR);
    return RainSnowGraupelCollectionParams{
        /*cms=*/cms, /*cmr=*/cmr,
        /*g1pms=*/g1pms, /*g2pms=*/g2pms, /*g3pms=*/g3pms,
        /*g1pmr=*/g1pmr, /*g2pmr=*/g2pmr, /*g3pmr=*/g3pmr,
        /*g1pmg=*/g1pmg, /*g2pmg=*/g2pmg, /*g3pmg=*/g3pmg,
        /*g1pdsms=*/g1pdsms, /*g2pdsms=*/g2pdsms, /*g3pdsms=*/g3pdsms,
        /*g1pdrmr=*/g1pdrmr, /*g2pdrmr=*/g2pdrmr, /*g3pdrmr=*/g3pdrmr,
        /*eacrs=*/constants::EACRS, /*eacsr=*/constants::EACSR, /*eacgr=*/constants::EACGR,
        /*qcrmin=*/constants::QCRMIN, /*nrmin=*/constants::NRMIN,
    };
}

RainSnowGraupelCollectionOutputs rain_snow_graupel_collection_torch(
    const RainSnowGraupelCollectionInputs& in,
    const RainSnowGraupelCollectionParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(in.qr);
    auto den_safe = torch::clamp(in.den, /*min=*/p.qcrmin);
    auto qr_safe = torch::clamp(in.qr, /*min=*/p.qcrmin);
    auto qs_safe = torch::clamp(in.qs, /*min=*/p.qcrmin);
    auto qg_safe = torch::clamp(in.qg, /*min=*/p.qcrmin);

    auto common_r_d = in.rsloped_r * in.rslopemu_r;
    auto common_s_d = in.rsloped_s * in.rslopemu_s;
    auto snow_r_active = torch::logical_and(in.qs > p.qcrmin, in.qr > p.qcrmin);

    // ── pracs (cold-only) ───────────────────────────────────────────────
    auto cold = in.supcol > 0;
    // F:2043-2048 — last-multiply fusion into each '+'.
    auto acrfac_pracs_t1 =
        p.g3pmr * p.g1pdsms * in.rslope3_r * in.rslopemu_r * common_s_d * in.rslope_s;
    auto acrfac_pracs_t2h = 2.0 * p.g2pmr * p.g2pdsms * in.rslope2_r * in.rslopemu_r * common_s_d;
    auto acrfac_pracs_t3h = p.g1pmr * p.g3pdsms * in.rslope_r * in.rslopemu_r * common_s_d;
    auto acrfac_pracs = ops::fma_acc(
        ops::fma_acc(acrfac_pracs_t1, acrfac_pracs_t2h, in.rslope2_s),
        acrfac_pracs_t3h, in.rslope3_s);
    auto pracs_raw =
        PI * p.cms * in.n0so * in.n0sfac * in.n0r * torch::abs(in.vt2r - in.vt2s)
        / (4.0 * den_safe) * acrfac_pracs * p.eacrs;
    auto pracs_wilt = pracs_raw * wilt_reduction(qr_safe / qs_safe);
    auto pracs_capped = torch::minimum(pracs_wilt, in.qs / dtcld);
    auto pracs = torch::where(snow_r_active & cold, pracs_capped, zero);

    auto nracs = zero.clone();  // commented-out in Fortran

    // ── psacr ──────────────────────────────────────────────────────────
    // F:2081-2086 — last-multiply fusion into each '+'.
    auto acrfac_psacr_t1 =
        p.g3pms * p.g1pdrmr * in.rslope3_s * in.rslopemu_s * common_r_d * in.rslope_r;
    auto acrfac_psacr_t2h = 2.0 * p.g2pms * p.g2pdrmr * in.rslope2_s * in.rslopemu_s * common_r_d;
    auto acrfac_psacr_t3h = p.g1pms * p.g3pdrmr * in.rslope_s * in.rslopemu_s * common_r_d;
    auto acrfac_psacr = ops::fma_acc(
        ops::fma_acc(acrfac_psacr_t1, acrfac_psacr_t2h, in.rslope2_r),
        acrfac_psacr_t3h, in.rslope3_r);
    auto psacr_raw =
        PI * p.cmr * in.n0r * in.n0so * in.n0sfac * torch::abs(in.vt2s - in.vt2r)
        / (4.0 * den_safe) * acrfac_psacr * p.eacsr;
    auto psacr_wilt = psacr_raw * wilt_reduction(qs_safe / qr_safe);
    auto psacr_capped = torch::minimum(psacr_wilt, in.qr / dtcld);
    auto psacr = torch::where(snow_r_active, psacr_capped, zero);

    // ── nsacr ──────────────────────────────────────────────────────────
    auto snow_nr_active = torch::logical_and(in.qs > p.qcrmin, in.nr > p.nrmin);
    // F:2101-2106 — last factor (rslopemu_r) of each term fuses into the '+'.
    auto acrfac_nsacr_t1 =
        p.g3pms * p.g1pmr * in.rslope3_s * in.rslopemu_s * in.rslope_r * in.rslopemu_r;
    auto acrfac_nsacr_t2h = 2.0 * p.g2pms * p.g2pmr * in.rslope2_s * in.rslopemu_s * in.rslope2_r;
    auto acrfac_nsacr_t3h = p.g1pms * p.g3pmr * in.rslope_s * in.rslopemu_s * in.rslope3_r;
    auto acrfac_nsacr = ops::fma_acc(
        ops::fma_acc(acrfac_nsacr_t1, acrfac_nsacr_t2h, in.rslopemu_r),
        acrfac_nsacr_t3h, in.rslopemu_r);
    auto nsacr_raw =
        PI / 4.0 * in.n0r * in.n0so * in.n0sfac * torch::abs(in.vt2s - in.vt2r)
        * acrfac_nsacr * p.eacsr;
    auto nsacr_wilt = nsacr_raw * wilt_reduction(qs_safe / qr_safe);
    auto nsacr_capped = torch::minimum(nsacr_wilt, in.nr / dtcld);
    auto nsacr = torch::where(snow_nr_active, nsacr_capped, zero);

    // ── pgacr ──────────────────────────────────────────────────────────
    auto graupel_r_active = torch::logical_and(in.qg > p.qcrmin, in.qr > p.qcrmin);
    // F:2121-2126 — last-multiply fusion into each '+'.
    auto acrfac_pgacr_t1 =
        p.g3pmg * p.g1pdrmr * in.rslope3_g * in.rslopemu_g * common_r_d * in.rslope_r;
    auto acrfac_pgacr_t2h = 2.0 * p.g2pmg * p.g2pdrmr * in.rslope2_g * in.rslopemu_g * common_r_d;
    auto acrfac_pgacr_t3h = p.g1pmg * p.g3pdrmr * in.rslope_g * in.rslopemu_g * common_r_d;
    auto acrfac_pgacr = ops::fma_acc(
        ops::fma_acc(acrfac_pgacr_t1, acrfac_pgacr_t2h, in.rslope2_r),
        acrfac_pgacr_t3h, in.rslope3_r);
    auto pgacr_raw =
        PI * p.cmr * in.n0r * in.n0go * torch::abs(in.vt2g - in.vt2r)
        / (4.0 * den_safe) * acrfac_pgacr * p.eacgr;
    auto pgacr_wilt = pgacr_raw * wilt_reduction(qg_safe / qr_safe);
    auto pgacr_capped = torch::minimum(pgacr_wilt, in.qr / dtcld);
    auto pgacr = torch::where(graupel_r_active, pgacr_capped, zero);

    // ── ngacr ──────────────────────────────────────────────────────────
    auto graupel_nr_active = torch::logical_and(in.qg > p.qcrmin, in.nr > p.nrmin);
    // F:2141-2146 — last factor (rslopemu_r) of each term fuses into the '+'.
    auto acrfac_ngacr_t1 =
        p.g3pmg * p.g1pmr * in.rslope3_g * in.rslopemu_g * in.rslope_r * in.rslopemu_r;
    auto acrfac_ngacr_t2h = 2.0 * p.g2pmg * p.g2pmr * in.rslope2_g * in.rslopemu_g * in.rslope2_r;
    auto acrfac_ngacr_t3h = p.g1pmg * p.g3pmr * in.rslope_g * in.rslopemu_g * in.rslope3_r;
    auto acrfac_ngacr = ops::fma_acc(
        ops::fma_acc(acrfac_ngacr_t1, acrfac_ngacr_t2h, in.rslopemu_r),
        acrfac_ngacr_t3h, in.rslopemu_r);
    auto ngacr_raw =
        PI / 4.0 * in.n0r * in.n0go * torch::abs(in.vt2g - in.vt2r)
        * acrfac_ngacr * p.eacgr;
    auto ngacr_wilt = ngacr_raw * wilt_reduction(qg_safe / qr_safe);
    auto ngacr_capped = torch::minimum(ngacr_wilt, in.nr / dtcld);
    auto ngacr = torch::where(graupel_nr_active, ngacr_capped, zero);

    return RainSnowGraupelCollectionOutputs{
        /*pracs=*/pracs, /*nracs=*/nracs, /*psacr=*/psacr, /*nsacr=*/nsacr, /*pgacr=*/pgacr, /*ngacr=*/ngacr,
    };
}

// ═══════════════════════════════════════════════════════════════════════════
// C2e: Hallett-Mossop ice multiplication
// ═══════════════════════════════════════════════════════════════════════════

namespace {

torch::Tensor hm_fmul(const torch::Tensor& t, const HallettMossopParams& p) {
    auto fmul_upper = (p.t_hi - t) / 2.0;
    auto fmul_lower = (t - p.t_lo) / 3.0;
    auto in_upper = torch::logical_and(t > p.t_mid, t <= p.t_hi);
    auto in_lower = torch::logical_and(t >= p.t_lo, t <= p.t_mid);
    auto zero = torch::zeros_like(t);
    return torch::where(in_upper, fmul_upper, torch::where(in_lower, fmul_lower, zero));
}

}  // namespace

HallettMossopParams default_hallett_mossop_params() {
    return HallettMossopParams{
        /*rispl=*/5.0e-6,
        /*deni=*/constants::DENI,
        /*qs_threshold=*/0.1e-3,
        /*qg_threshold=*/0.1e-3,
        /*qc_threshold=*/0.5e-3,
        /*qr_threshold=*/0.1e-3,
        /*t_lo=*/265.16,
        /*t_hi=*/270.16,
        /*t_mid=*/268.16,
    };
}

HallettMossopOutputs hallett_mossop_torch(
    const HallettMossopInputs& in,
    const HallettMossopParams& p
) {
    auto zero = torch::zeros_like(in.paacw);
    // STEP-86 SEED class: these ice mass constants are REAL(4),save in Fortran
    // (F:179) and evaluated f32-STEPWISE (pi = 4.*atan(1.) f32; **3 -> x*x*x);
    // f64-compute-then-demote lands 1-2 ULP off (Minud 2C136145 vs 2C136144).
    const float pi_f_hm = static_cast<float>(fconst::get().pi);
    const float rispl_f = static_cast<float>(p.rispl);
    const double Mispl = static_cast<double>(
        (4.0f / 3.0f) * pi_f_hm * static_cast<float>(p.deni) * (rispl_f * rispl_f * rispl_f));
    auto fmul = hm_fmul(in.t, p);

    auto droplet_mass = torch::logical_or(in.qc >= p.qc_threshold, in.qr >= p.qr_threshold);
    auto t_in_band = torch::logical_and(in.t > p.t_lo, in.t < p.t_hi);

    // ── Snow side ──────────────────────────────────────────────────────
    auto snow_outer = torch::logical_and(
        torch::logical_and(
            torch::logical_and(in.qs >= p.qs_threshold, droplet_mass),
            torch::logical_or(in.paacw > 0, in.psacr > 0)
        ),
        t_in_band
    );

    auto paacw_branch = torch::logical_and(snow_outer, in.paacw > 0);
    auto nmul_pre_cs = 35.0e4 * in.paacw * fmul * 1000.0;
    auto pmulcs_raw = nmul_pre_cs * Mispl;
    auto pmulcs_capped = torch::minimum(pmulcs_raw, in.paacw);
    auto pmulcs = torch::where(paacw_branch, pmulcs_capped, zero);
    auto nmulcs = torch::where(paacw_branch, nmul_pre_cs * in.den, zero);

    auto psacr_branch = torch::logical_and(snow_outer, in.psacr > 0);
    auto nmul_pre_rs = 35.0e4 * in.psacr * fmul * 1000.0;
    auto pmulrs_raw = nmul_pre_rs * Mispl;
    auto pmulrs_capped = torch::minimum(pmulrs_raw, in.psacr);
    auto pmulrs = torch::where(psacr_branch, pmulrs_capped, zero);
    auto nmulrs = torch::where(psacr_branch, nmul_pre_rs * in.den, zero);

    // ── Graupel side (uses paacw_after_snow) ───────────────────────────
    auto paacw_after_snow = in.paacw - pmulcs;

    auto graupel_outer = torch::logical_and(
        torch::logical_and(
            torch::logical_and(in.qg >= p.qg_threshold, droplet_mass),
            torch::logical_or(in.paacw > 0, in.pgacr > 0)
        ),
        t_in_band
    );

    auto paacw_branch_g = torch::logical_and(graupel_outer, paacw_after_snow > 0);
    auto nmul_pre_cg = 35.0e4 * paacw_after_snow * fmul * 1000.0;
    auto pmulcg_raw = nmul_pre_cg * Mispl;
    auto pmulcg_capped = torch::minimum(pmulcg_raw, paacw_after_snow);
    auto pmulcg = torch::where(paacw_branch_g, pmulcg_capped, zero);
    auto nmulcg = torch::where(paacw_branch_g, nmul_pre_cg * in.den, zero);

    auto pgacr_branch = torch::logical_and(graupel_outer, in.pgacr > 0);
    auto nmul_pre_rg = 35.0e4 * in.pgacr * fmul * 1000.0;
    auto pmulrg_raw = nmul_pre_rg * Mispl;
    auto pmulrg_capped = torch::minimum(pmulrg_raw, in.pgacr);
    auto pmulrg = torch::where(pgacr_branch, pmulrg_capped, zero);
    auto nmulrg = torch::where(pgacr_branch, nmul_pre_rg * in.den, zero);

    auto paacw_adj = in.paacw - pmulcs - pmulcg;
    auto psacr_adj = in.psacr - pmulrs;
    auto pgacr_adj = in.pgacr - pmulrg;

    return HallettMossopOutputs{
        /*pmulcs=*/pmulcs, /*pmulrs=*/pmulrs, /*pmulcg=*/pmulcg, /*pmulrg=*/pmulrg,
        /*nmulcs=*/nmulcs, /*nmulrs=*/nmulrs, /*nmulcg=*/nmulcg, /*nmulrg=*/nmulrg,
        /*paacw_adj=*/paacw_adj, /*psacr_adj=*/psacr_adj, /*pgacr_adj=*/pgacr_adj,
    };
}

// ═══════════════════════════════════════════════════════════════════════════
// C3: Ice nucleation from vapor (pinud + ninud)
// ═══════════════════════════════════════════════════════════════════════════

IceNucleationParams default_ice_nucleation_params() {
    return IceNucleationParams{
        /*rinud=*/10.0e-6,
        /*deni=*/constants::DENI,
        /*cooper_a=*/0.005,
        /*cooper_b=*/0.304,
        /*cooper_unit=*/1000.0,
        /*nid_max=*/500.0e3,
        /*supcol_threshold=*/8.0,
        /*rh_ice_threshold=*/1.08,
    };
}

IceNucleationOutputs ice_nucleation_torch(
    const IceNucleationInputs& in,
    const IceNucleationParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(in.supcol);
    // STEP-86 SEED: F:2344 Minud f32-stepwise (see Mispl note).
    const float pi_f_nu = static_cast<float>(fconst::get().pi);
    const float rinud_f = static_cast<float>(p.rinud);
    const double Minud = static_cast<double>(
        (4.0f / 3.0f) * pi_f_nu * static_cast<float>(p.deni) * (rinud_f * rinud_f * rinud_f));

    auto cold_super = torch::logical_and(in.supcol > p.supcol_threshold, in.supsat > 0);
    auto high_rh = in.rh_ice > p.rh_ice_threshold;
    auto nuc_active = torch::logical_or(cold_super, high_rh);

    auto satdt = in.supsat / dtcld;
    auto supice = satdt - in.prevp;

    auto nid_raw = p.cooper_a * ops::libm_exp(p.cooper_b * in.supcol) * p.cooper_unit;
    auto nid = torch::clamp(nid_raw, /*min=*/0.0, /*max=*/p.nid_max);

    auto inner_active = nid > in.nci_ice;

    auto den_safe = torch::clamp(in.den, /*min=*/constants::QCRMIN);
    auto ninud_raw = (nid - in.nci_ice) / dtcld;
    auto pinud_raw = ninud_raw / den_safe * Minud;

    auto half_satdt = 0.5 * satdt;
    auto pinud_capped = torch::minimum(torch::minimum(pinud_raw, half_satdt), supice);
    auto ninud_capped = pinud_capped * den_safe / Minud;

    auto active = torch::logical_and(nuc_active, inner_active);
    auto pinud = torch::where(active, pinud_capped, zero);
    auto ninud = torch::where(active, ninud_capped, zero);

    auto ifsat = torch::abs(in.prevp + pinud) >= torch::abs(satdt);

    return IceNucleationOutputs{/*pinud=*/pinud, /*ninud=*/ninud, /*ifsat=*/ifsat};
}

// ═══════════════════════════════════════════════════════════════════════════
// C4: Deposition / Sublimation (pidep + psdep + pgdep)
// ═══════════════════════════════════════════════════════════════════════════

namespace {

torch::Tensor dep_sub_capped(
    const torch::Tensor& rate_raw, const torch::Tensor& source_mass,
    const torch::Tensor& half_satdt, const torch::Tensor& supice, double dtcld
) {
    auto sub_path = torch::maximum(rate_raw, -source_mass / dtcld);
    sub_path = torch::maximum(torch::maximum(sub_path, half_satdt), supice);
    auto dep_path = torch::minimum(torch::minimum(rate_raw, half_satdt), supice);
    return torch::where(rate_raw < 0, sub_path, dep_path);
}

}  // namespace

DepSubParams default_dep_sub_params() {
    const double g2pmi = rgmma_scalar(2.0 + constants::MUI);
    const double g2pms = rgmma_scalar(2.0 + constants::MUS);
    const double g2pmg = rgmma_scalar(2.0 + constants::MUG);
    const double bvts2 = 2.5 + 0.5 * constants::BVTS + constants::MUS;
    const double g5pbso2 = rgmma_scalar(bvts2);
    const double precs1 = 4.0 * 0.65 * g2pms;
    const double precs2 = 4.0 * 0.44 * std::pow(constants::AVTS, 0.5) * g5pbso2;
    const double precg1 = 4.0 * 0.78 * g2pmg;
    return DepSubParams{
        /*g2pmi=*/g2pmi,
        /*precs1=*/precs1, /*precs2=*/precs2,
        /*precg1=*/precg1,
        /*qcrmin=*/constants::QCRMIN,
    };
}

DepSubOutputs dep_sub_torch(
    const DepSubInputs& in,
    const DepSubParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(in.qi);
    auto cold = in.supcol > 0;
    auto satdt = in.supsat / dtcld;
    auto half_satdt = 0.5 * satdt;
    auto work1_safe = torch::clamp(in.work1_ice, /*min=*/p.qcrmin);
    auto not_ifsat_in = torch::logical_not(in.ifsat_in);

    // ── pidep ──────────────────────────────────────────────────────────
    auto pidep_active = torch::logical_and(
        torch::logical_and(cold, in.qi > 0),
        not_ifsat_in
    );
    // STEP-67 SEED (C4 pidep, F:2367): the RHS is a DOUBLE chain — n0i DOUBLE
    // (F:697), g2pmi=Γ(2)=1, rslopemu(:,4)≡1 (DOUBLE), rslope2 f32-promoted,
    // (rh-1.) computed f32 THEN promoted, work1(:,2) DOUBLE holding the f32
    // diffac value (upcast, NOT recomputed). ONE f32 rounding at the rate store;
    // the satdt/2 + supice caps below act on the stored f32 value (F:2380-2383).
    auto pidep_raw = (4.0 * in.n0i * p.g2pmi * in.rslopemu_i * in.rslope2_i
                     * (in.rh_ice - 1.0) / work1_safe).to(in.qi.scalar_type());
    auto supice_pidep = satdt - in.prevp - in.pinud;
    auto pidep_capped = dep_sub_capped(pidep_raw, in.qi, half_satdt, supice_pidep, dtcld);
    auto pidep = torch::where(pidep_active, pidep_capped, zero);

    auto qi_cap = -in.qi / dtcld;
    auto ice_complete_sublim = torch::logical_and(
        torch::logical_and(pidep_active, pidep <= qi_cap + 1.0e-30),
        pidep < 0
    );

    auto ifsat_after_pidep = torch::logical_or(
        in.ifsat_in,
        torch::abs(in.prevp + in.pinud + pidep) >= torch::abs(satdt)
    );

    // ── psdep ──────────────────────────────────────────────────────────
    auto psdep_active = torch::logical_and(
        torch::logical_and(cold, in.qs > 0),
        torch::logical_not(ifsat_after_pidep)
    );
    auto coeres_s = in.rslope2_s
                  * torch::sqrt(torch::clamp(in.rslope_s * in.rslopeb_s, /*min=*/p.qcrmin))
                  * in.rslopemu_s;
    // F:2361-2362 inner sum (A + B): gfortran fuses B's last multiply (*coeres) into the add.
    auto psdep_inner = ops::fma_acc(
        p.precs1 * in.n0so * in.rslope2_s * in.rslopemu_s,
        p.precs2 * in.n0so * in.work2, coeres_s);
    auto psdep_raw = (in.rh_ice - 1.0) * in.n0sfac * psdep_inner / work1_safe;
    auto supice_psdep = satdt - in.prevp - in.pinud - pidep;
    auto psdep_capped = dep_sub_capped(psdep_raw, in.qs, half_satdt, supice_psdep, dtcld);
    auto psdep = torch::where(psdep_active, psdep_capped, zero);

    auto ifsat_after_psdep = torch::logical_or(
        ifsat_after_pidep,
        torch::abs(in.prevp + in.pinud + pidep + psdep) >= torch::abs(satdt)
    );

    // ── pgdep ──────────────────────────────────────────────────────────
    auto pgdep_active = torch::logical_and(
        torch::logical_and(cold, in.qg > 0),
        torch::logical_not(ifsat_after_psdep)
    );
    auto coeres_g = in.rslope2_g
                  * torch::sqrt(torch::clamp(in.rslope_g * in.rslopeb_g, /*min=*/p.qcrmin))
                  * in.rslopemu_g;
    // F:2380-2381 inner sum (A + B): gfortran fuses B's last multiply (*coeres) into the add.
    auto pgdep_inner = ops::fma_acc(
        p.precg1 * in.n0go * in.rslope2_g * in.rslopemu_g,
        in.precg2 * in.n0go * in.work2, coeres_g);
    auto pgdep_raw = (in.rh_ice - 1.0) * pgdep_inner / work1_safe;
    auto supice_pgdep = satdt - in.prevp - in.pinud - pidep - psdep;
    auto pgdep_capped = dep_sub_capped(pgdep_raw, in.qg, half_satdt, supice_pgdep, dtcld);
    auto pgdep = torch::where(pgdep_active, pgdep_capped, zero);

    auto ifsat_final = torch::logical_or(
        ifsat_after_psdep,
        torch::abs(in.prevp + in.pinud + pidep + psdep + pgdep) >= torch::abs(satdt)
    );

    return DepSubOutputs{/*pidep=*/pidep, /*psdep=*/psdep, /*pgdep=*/pgdep,
                         /*ifsat=*/ifsat_final, /*ice_complete_sublim=*/ice_complete_sublim};
}

// ═══════════════════════════════════════════════════════════════════════════
// C5: Aggregation (psaut + nsaut) — Ryan 2010
// ═══════════════════════════════════════════════════════════════════════════

IceAggregationParams default_ice_aggregation_params() {
    return IceAggregationParams{
        /*deni=*/constants::DENI,
        /*di125=*/constants::DI125,
        /*t_split=*/255.66,
        /*qcrmin=*/constants::QCRMIN,
    };
}

IceAggregationOutputs ice_aggregation_torch(
    const torch::Tensor& qi,
    const torch::Tensor& ni,
    const torch::Tensor& t,
    const torch::Tensor& den,
    const torch::Tensor& supcol,
    const IceAggregationParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(qi);
    auto cold = supcol > 0;
    auto active = torch::logical_and(torch::logical_and(cold, qi > 0), ni > 0);

    auto neg_supcol = -supcol;
    auto base = torch::full_like(t, 10.0);
    // Fortran: 10**(-6.0-0.0413*(-supcol)) — gfortran fuses the 0.0413*(-supcol) multiply
    // into the '-6.0 -' subtract (single rounding). base=10 → safe_pow clamp harmless (libm pow).
    auto exp_warm = ops::fma_acc(torch::full_like(neg_supcol, -6.0), neg_supcol,
                                   torch::full_like(neg_supcol, 0.0413), -1.0);
    auto exp_cold = ops::fma_acc(torch::full_like(neg_supcol, -4.0), neg_supcol,
                                   torch::full_like(neg_supcol, 0.0519), 1.0);
    auto qi0_warm = 0.4632 * ops::safe_pow(base, exp_warm) * den;
    auto qi0_cold = 0.2316 * ops::safe_pow(base, exp_cold) * den;
    auto qi0 = torch::where(t > p.t_split, qi0_warm, qi0_cold);

    auto alpha1 = 0.005 * ops::libm_exp(0.025 * neg_supcol);
    // STEP-86 SEED class: F:2436 Miaut = pi*deni*di125**3/6. f32-stepwise (2 ULP off as double).
    const float pi_f_ag = static_cast<float>(fconst::get().pi);
    const float di125_f = static_cast<float>(p.di125);
    const double Miaut = static_cast<double>(
        pi_f_ag * static_cast<float>(p.deni) * (di125_f * di125_f * di125_f) / 6.0f);

    auto psaut_raw = alpha1 * (qi - qi0);
    auto psaut_pos = torch::clamp(psaut_raw, /*min=*/0.0);
    auto psaut_capped = torch::minimum(psaut_pos, qi / dtcld);
    auto psaut = torch::where(active, psaut_capped, zero);

    auto nsaut_raw = psaut * den / Miaut;
    auto nsaut_capped = torch::minimum(nsaut_raw, ni / dtcld);
    auto nsaut = torch::where(active, nsaut_capped, zero);

    return IceAggregationOutputs{/*psaut=*/psaut, /*nsaut=*/nsaut};
}

// ═══════════════════════════════════════════════════════════════════════════
// C6: Snow evaporation (psevp)
// ═══════════════════════════════════════════════════════════════════════════

SnowEvapParams default_snow_evap_params() {
    const double g2pms = rgmma_scalar(2.0 + constants::MUS);
    const double bvts2 = 2.5 + 0.5 * constants::BVTS + constants::MUS;
    const double g5pbso2 = rgmma_scalar(bvts2);
    const double precs1 = 4.0 * 0.65 * g2pms;
    const double precs2 = 4.0 * 0.44 * std::pow(constants::AVTS, 0.5) * g5pbso2;
    return SnowEvapParams{/*precs1=*/precs1, /*precs2=*/precs2, /*qcrmin=*/constants::QCRMIN};
}

torch::Tensor snow_evap_torch(
    const SnowEvapInputs& in,
    const SnowEvapParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(in.qs);
    auto active = torch::logical_and(
        torch::logical_and(in.supcol < 0, in.qs > 0),
        in.rh_w < 1.0
    );
    auto work1_safe = torch::clamp(in.work1_water, /*min=*/p.qcrmin);
    auto coeres = in.rslope2_s
                * torch::sqrt(torch::clamp(in.rslope_s * in.rslopeb_s, /*min=*/p.qcrmin))
                * in.rslopemu_s;

    // F:2427-2428 inner sum (A + B): gfortran fuses B's last multiply (*coeres) into the add.
    auto psevp_inner = ops::fma_acc(
        p.precs1 * in.n0so * in.rslope2_s * in.rslopemu_s,
        p.precs2 * in.n0so * in.work2, coeres);
    auto psevp_raw = (in.rh_w - 1.0) * in.n0sfac * psevp_inner / work1_safe;
    auto psevp_capped = torch::minimum(torch::maximum(psevp_raw, -in.qs / dtcld), zero);
    auto psevp = torch::where(active, psevp_capped, zero);
    return psevp;
}

// ═══════════════════════════════════════════════════════════════════════════
// C6': Graupel evaporation (pgevp) — Fortran 2435-2441 (codex#4 / Task #53)
// ═══════════════════════════════════════════════════════════════════════════

GraupelEvapParams default_graupel_evap_params() {
    const double g2pmg = rgmma_scalar(2.0 + constants::MUG);
    const double precg1 = 4.0 * 0.78 * g2pmg;
    return GraupelEvapParams{/*precg1=*/precg1, /*qcrmin=*/constants::QCRMIN};
}

torch::Tensor graupel_evap_torch(
    const GraupelEvapInputs& in,
    const GraupelEvapParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(in.qg);
    auto active = torch::logical_and(
        torch::logical_and(in.supcol < 0, in.qg > 0),
        in.rh_w < 1.0
    );
    auto work1_safe = torch::clamp(in.work1_water, /*min=*/p.qcrmin);
    auto coeres = in.rslope2_g
                * torch::sqrt(torch::clamp(in.rslope_g * in.rslopeb_g, /*min=*/p.qcrmin))
                * in.rslopemu_g;

    // Note: NO n0sfac (graupel has no ice-fraction scaling; matches Python).
    // F:2438-2439 inner sum (A + B): gfortran fuses B's last multiply (*coeres) into the add.
    auto pgevp_inner = ops::fma_acc(
        p.precg1 * in.n0go * in.rslope2_g * in.rslopemu_g,
        in.precg2 * in.n0go * in.work2, coeres);
    auto pgevp_raw = (in.rh_w - 1.0) * pgevp_inner / work1_safe;
    auto pgevp_capped = torch::minimum(torch::maximum(pgevp_raw, -in.qg / dtcld), zero);
    auto pgevp = torch::where(active, pgevp_capped, zero);
    return pgevp;
}

}  // namespace cold
}  // namespace kdm6
