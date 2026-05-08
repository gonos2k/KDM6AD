#include "kdm6/warm.h"

#include "kdm6/ops.h"

#include <cmath>

namespace kdm6 {
namespace warm {
namespace {

constexpr double PI = 3.14159265358979323846;

double rgmma_scalar(double x) {
    // Fortran rgmma(x) = exp(GAMMLN(x)) = Γ(x). review6 audit fix
    // (이전 구현 exp(-lgamma) = 1/Γ는 부호 잘못).
    return std::exp(std::lgamma(x));
}

}  // namespace

// ═══════════════════════════════════════════════════════════════════════════
// B1: Autoconversion (praut + nraut)
// ═══════════════════════════════════════════════════════════════════════════

WarmAutoconvParams default_warm_autoconv_params(double den0) {
    const double qck1 =
        0.104 * 9.8 * constants::PEAUT
        / std::pow(constants::DENR, 1.0 / 3.0)
        / constants::XMYU
        * std::pow(den0, 4.0 / 3.0);

    return WarmAutoconvParams{
        /*qck1=*/qck1,
        /*nraut_coeff=*/3.5e9,
        /*qcrmin=*/constants::QCRMIN,
        /*ncmin=*/constants::NCMIN,
    };
}

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
) {
    auto active = torch::logical_and(qc > qcr, nc > params.ncmin);
    auto zero = torch::zeros_like(qc);

    // praut: mass autoconversion
    auto qc_term = ops::safe_pow(qc, 7.0 / 3.0);
    auto nc_term = ops::safe_pow(nc, -1.0 / 3.0);
    auto praut_raw = params.qck1 * qc_term * nc_term;
    auto praut_capped = torch::minimum(praut_raw, qc / dtcld);
    auto praut = torch::where(active, praut_capped, zero);

    // nraut: number autoconversion
    auto nraut_default = params.nraut_coeff * den * praut;
    auto rain_swap = qr > lenconcr;
    auto nraut_swap = ops::safe_div_pos(nr, qr) * praut;
    auto nraut_unswap = torch::where(rain_swap, nraut_swap, nraut_default);
    auto nraut_capped = torch::minimum(nraut_unswap, nc / dtcld);
    auto nraut = torch::where(active, nraut_capped, zero);

    return AutoconvOutputs{praut, nraut};
}

// ═══════════════════════════════════════════════════════════════════════════
// B2: Accretion of cloud water by rain (pracw + nracw)
// ═══════════════════════════════════════════════════════════════════════════

WarmAccretionParams default_warm_accretion_params() {
    const double cmc = PI * constants::DENR / 6.0;
    const double g3pmc = rgmma_scalar(1.0 + 3.0 / (constants::MUC + 1.0));
    const double g6pmc = rgmma_scalar(1.0 + 6.0 / (constants::MUC + 1.0));
    const double g9pmc = rgmma_scalar(1.0 + 9.0 / (constants::MUC + 1.0));
    const double g1pmr = rgmma_scalar(1.0 + constants::MUR);
    const double g4pmr = rgmma_scalar(4.0 + constants::MUR);
    const double g7pmr = rgmma_scalar(7.0 + constants::MUR);

    return WarmAccretionParams{
        /*ncrk1=*/constants::NCRK1,
        /*ncrk2=*/constants::NCRK2,
        /*cmc=*/cmc,
        /*g3pmc=*/g3pmc,
        /*g6pmc=*/g6pmc,
        /*g9pmc=*/g9pmc,
        /*g1pmr=*/g1pmr,
        /*g4pmr=*/g4pmr,
        /*g7pmr=*/g7pmr,
        /*di100=*/constants::DI100,
    };
}

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
) {
    auto rain_active = qr >= lenconcr;
    auto zero = torch::zeros_like(qc);

    auto cmc_over_den = params.cmc / torch::clamp(den, /*min=*/constants::QCRMIN);
    const double g4pmr_over_g1pmr = params.g4pmr / params.g1pmr;
    const double g7pmr_over_g1pmr = params.g7pmr / params.g1pmr;

    // Mode 1 (big drops): avedia_r >= di100
    auto pracw_mode1 = cmc_over_den * params.ncrk1 * nc * nr * rslopec3
        * (rslopec3 * params.g6pmc + rslope3_r * params.g3pmc * g4pmr_over_g1pmr);
    auto nracw_mode1 = params.ncrk1 * nc * nr
        * (rslopec3 * params.g3pmc + rslope3_r * g4pmr_over_g1pmr);

    // Mode 2 (small drops): avedia_r < di100
    auto pracw_mode2 = cmc_over_den * params.ncrk2 * nc * nr * rslopec3
        * (rslopec3 * rslopec3 * params.g9pmc
           + rslope3_r * rslope3_r * params.g3pmc * g7pmr_over_g1pmr);
    auto nracw_mode2 = params.ncrk2 * nc * nr
        * (rslopec3 * rslopec3 * params.g6pmc + rslope3_r * rslope3_r)
        * g7pmr_over_g1pmr;

    auto big_drop = avedia_r >= params.di100;
    auto pracw_raw = torch::where(big_drop, pracw_mode1, pracw_mode2);
    auto nracw_raw = torch::where(big_drop, nracw_mode1, nracw_mode2);

    auto pracw_capped = torch::minimum(pracw_raw, qc / dtcld);
    auto nracw_capped = torch::minimum(nracw_raw, nc / dtcld);

    auto pracw = torch::where(rain_active, pracw_capped, zero);
    auto nracw = torch::where(rain_active, nracw_capped, zero);

    return AccretionOutputs{pracw, nracw};
}

// ═══════════════════════════════════════════════════════════════════════════
// B3: Self-collection (nccol + nrcol)
// ═══════════════════════════════════════════════════════════════════════════

WarmSelfCollectionParams default_warm_self_collection_params() {
    const double g3pmc = rgmma_scalar(1.0 + 3.0 / (constants::MUC + 1.0));
    const double g6pmc = rgmma_scalar(1.0 + 6.0 / (constants::MUC + 1.0));
    const double g1pmr = rgmma_scalar(1.0 + constants::MUR);
    const double g4pmr = rgmma_scalar(4.0 + constants::MUR);
    const double g7pmr = rgmma_scalar(7.0 + constants::MUR);

    return WarmSelfCollectionParams{
        /*ncrk1=*/constants::NCRK1,
        /*ncrk2=*/constants::NCRK2,
        /*eccbrk=*/constants::ECCBRK,
        /*g3pmc=*/g3pmc,
        /*g6pmc=*/g6pmc,
        /*g1pmr=*/g1pmr,
        /*g4pmr=*/g4pmr,
        /*g7pmr=*/g7pmr,
        /*di100=*/constants::DI100,
        /*di600=*/constants::DI600,
        /*di2000=*/constants::DI2000,
    };
}

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
) {
    auto zero = torch::zeros_like(nc);

    // nccol (cloud self-collection): 2-mode
    auto nccol_big = params.ncrk1 * nc * nc * rslopec3 * params.g3pmc;
    auto nccol_small = params.ncrk2 * nc * nc * rslopec3 * rslopec3 * params.g6pmc;
    auto big_cloud = avedia_c >= params.di100;
    auto nccol = torch::where(big_cloud, nccol_big, nccol_small);

    // nrcol (rain self-collection + break-up): 4-mode
    const double g4pmr_over_g1pmr = params.g4pmr / params.g1pmr;
    const double g7pmr_over_g1pmr = params.g7pmr / params.g1pmr;

    auto nrcol_small = params.ncrk2 * nr * nr * rslope3_r * rslope3_r * g7pmr_over_g1pmr;
    auto nrcol_medium = params.ncrk1 * nr * nr * rslope3_r * g4pmr_over_g1pmr;
    auto coecol = -2.5e3 * params.eccbrk * (avedia_r - params.di600);
    auto nrcol_breakup = torch::exp(coecol) * params.ncrk1 * nr * nr * rslope3_r * g4pmr_over_g1pmr;

    auto is_small = avedia_r < params.di100;
    auto is_medium = torch::logical_and(avedia_r >= params.di100, avedia_r < params.di600);
    auto is_breakup = torch::logical_and(avedia_r >= params.di600, avedia_r < params.di2000);

    auto nrcol_raw = torch::where(
        is_small, nrcol_small,
        torch::where(
            is_medium, nrcol_medium,
            torch::where(is_breakup, nrcol_breakup, zero)
        )
    );

    auto rain_active = qr >= lenconcr;
    auto nrcol = torch::where(rain_active, nrcol_raw, zero);

    return SelfCollectionOutputs{nccol, nrcol};
}

// ═══════════════════════════════════════════════════════════════════════════
// B4: Rain evaporation / condensation
// ═══════════════════════════════════════════════════════════════════════════

WarmRainEvapParams default_warm_rain_evap_params(double fac_evap) {
    const double g2pmr = rgmma_scalar(2.0 + constants::MUR);
    const double g7pbro2 = rgmma_scalar(2.5 + 0.5 * constants::BVTR + constants::MUR);

    const double precr1 = 2.0 * PI * 0.78 * g2pmr;
    const double precr2 = 2.0 * PI * 0.31 * std::pow(constants::AVTR, 0.5) * g7pbro2;

    return WarmRainEvapParams{
        /*precr1=*/precr1,
        /*precr2=*/precr2,
        /*fac_evap=*/fac_evap,
    };
}

RainEvapOutputs rain_evap_torch(
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
) {
    auto zero = torch::zeros_like(qr);
    auto active = qr > 0.0;

    // coeres = rslope2 * sqrt(rslope*rslopeb) * rslopemu
    auto sqrt_arg = torch::clamp(rslope_r * rslopeb_r, /*min=*/constants::QCRMIN);
    auto coeres = rslope2_r * torch::sqrt(sqrt_arg) * rslopemu_r;

    // prevp_raw = (rh-1) * n0r * (precr1*rslope2*rslopemu + precr2*work2*coeres) / work1
    auto work1_safe = torch::clamp(work1_r, /*min=*/constants::QCRMIN);
    auto bracket = params.precr1 * rslope2_r * rslopemu_r + params.precr2 * work2 * coeres;
    auto prevp_raw = (rh_w - 1.0) * n0r * bracket / work1_safe;
    prevp_raw = params.fac_evap * prevp_raw;

    // 부호 분기: evap (negative) vs cond (positive)
    auto satdt = supsat / dtcld;
    auto half_satdt = 0.5 * satdt;

    auto qr_cap = -qr / dtcld;
    auto prevp_evap = torch::maximum(prevp_raw, qr_cap);
    prevp_evap = torch::maximum(prevp_evap, half_satdt);

    auto prevp_cond = torch::minimum(prevp_raw, half_satdt);

    auto is_evap = prevp_raw < 0;
    auto prevp_capped = torch::where(is_evap, prevp_evap, prevp_cond);
    auto prevp = torch::where(active, prevp_capped, zero);
    auto rain_complete_evap = active & is_evap & (prevp == qr_cap);
    return RainEvapOutputs{/*prevp=*/prevp, /*rain_complete_evap=*/rain_complete_evap};
}

}  // namespace warm
}  // namespace kdm6
