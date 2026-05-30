#include "kdm6/slope.h"

#include "kdm6/ops.h"

#include <cmath>

namespace kdm6 {
namespace slope {
namespace {

constexpr double DOMAIN_FLOOR = 1.0e-30;
constexpr double RAIN_RSLOPE_LIMIT = 1.0e-3;
constexpr double PI = 3.14159265358979323846;

torch::Tensor scalar_like(double value, const torch::Tensor& ref) {
    return torch::full_like(ref, value);
}

torch::Tensor domain_clamp(const torch::Tensor& x) {
    return torch::clamp(x, /*min=*/DOMAIN_FLOOR);
}

torch::Tensor lamda_from_ratio(const torch::Tensor& ratio, double exponent) {
    return torch::exp(torch::log(domain_clamp(ratio)) / exponent);
}

double pow_or_one(double base, double exponent) {
    return exponent == 0.0 ? 1.0 : std::pow(base, exponent);
}

SlopeRainOutputs rain_slope_components(const torch::Tensor& qr,
                                       const torch::Tensor& nr,
                                       const torch::Tensor& den,
                                       const torch::Tensor& denfac,
                                       const SlopeParams& params,
                                       bool include_den_gate) {
    auto rain_mask = (qr <= constants::QCRMIN) | (nr <= constants::NRMIN);
    if (include_den_gate) {
        rain_mask = rain_mask | (den <= 0.0);
    }

    auto pidnr = scalar_like(params.pidnr, qr);
    auto lamdar = lamda_from_ratio(pidnr * nr / domain_clamp(qr * den), constants::DMR);
    auto rslope_raw = torch::minimum(1.0 / lamdar, scalar_like(RAIN_RSLOPE_LIMIT, qr));

    auto rslope = torch::where(rain_mask, scalar_like(params.rslopermax, qr), rslope_raw);
    auto rslopeb = torch::where(
        rain_mask,
        scalar_like(params.rsloperbmax, qr),
        ops::safe_pow(rslope, constants::BVTR)
    );
    auto rslopemu = torch::where(
        rain_mask,
        scalar_like(params.rslopermmax, qr),
        ops::safe_pow(rslope, constants::MUR)
    );
    auto rsloped = torch::where(
        rain_mask,
        scalar_like(params.rsloperdmax, qr),
        ops::safe_pow(rslope, constants::DMR)
    );
    auto rslope2 = torch::where(rain_mask, scalar_like(params.rsloper2max, qr), rslope * rslope);
    auto rslope3 = torch::where(rain_mask, scalar_like(params.rsloper3max, qr), rslope2 * rslope);

    auto vt = scalar_like(params.pvtr, qr) * rslopeb * denfac;
    auto vtn = scalar_like(params.pvtrn, qr) * rslopeb * denfac;
    auto zeros = torch::zeros_like(qr);
    vt = torch::where(qr <= 0.0, zeros, vt);
    vtn = torch::where(nr <= 0.0, zeros, vtn);

    return SlopeRainOutputs{rslope, rslopeb, rslopemu, rsloped, rslope2, rslope3, vt, vtn};
}

}  // namespace

SlopeParams default_slope_params() {
    const auto rgmma = [](double x) {
        // Fortran rgmma = Γ(x) (review6 audit fix).
        return std::exp(std::lgamma(x));
    };

    const double cmr = PI * constants::DENR / 6.0;
    const double cms = PI * constants::DENS / 6.0;
    const double cmi = PI * constants::DENI / 6.0;

    const double g1pmr = rgmma(1.0 + constants::MUR);
    const double g1pdrmr = rgmma(1.0 + constants::DMR + constants::MUR);
    const double g1pdrbrmr = rgmma(1.0 + constants::DMR + constants::BVTR + constants::MUR);
    const double g1pbrmr = rgmma(1.0 + constants::BVTR + constants::MUR);

    const double g1pms = rgmma(1.0 + constants::MUS);
    const double g1pdsms = rgmma(1.0 + constants::DMS + constants::MUS);
    const double g1pdsbsms = rgmma(1.0 + constants::DMS + constants::BVTS + constants::MUS);

    const double g1pmi = rgmma(1.0 + constants::MUI);
    const double g1pdimi = rgmma(1.0 + constants::DMI + constants::MUI);
    const double g1pdibimi = rgmma(1.0 + constants::DMI + constants::BVTI + constants::MUI);
    const double g1pbimi = rgmma(1.0 + constants::BVTI + constants::MUI);

    const double pidnr = cmr * g1pdrmr / g1pmr;
    const double pidn0s = cms * constants::N0S * g1pdsms / g1pms;
    const double pidni = cmi * g1pdimi / g1pmi;

    const double pvtr = constants::AVTR * g1pdrbrmr / g1pdrmr;
    const double pvtrn = constants::AVTR * g1pbrmr / g1pmr;
    const double pvts = constants::AVTS * g1pdsbsms / g1pdsms;
    const double pvti = constants::AVTI * g1pdibimi / g1pdimi;
    const double pvtin = constants::AVTI * g1pbimi / g1pmi;

    const double rslopermax = 1.0 / constants::LAMDARMAX;
    const double rslopesmax = 1.0 / constants::LAMDASMAX;
    const double rslopegmax = 1.0 / constants::LAMDAGMAX;
    const double rslopeimax = 1.0 / constants::LAMDAIMAX;

    const double rsloperbmax = std::pow(rslopermax, constants::BVTR);
    const double rslopesbmax = std::pow(rslopesmax, constants::BVTS);
    const double rslopeibmax = std::pow(rslopeimax, constants::BVTI);

    const double rslopermmax = pow_or_one(rslopermax, constants::MUR);
    const double rslopesmmax = pow_or_one(rslopesmax, constants::MUS);
    const double rslopegmmax = pow_or_one(rslopegmax, constants::MUG);
    const double rslopeimmax = pow_or_one(rslopeimax, constants::MUI);

    const double rsloperdmax = std::pow(rslopermax, constants::DMR);
    const double rslopesdmax = std::pow(rslopesmax, constants::DMS);
    const double rslopegdmax = std::pow(rslopegmax, constants::DMG);
    const double rslopeidmax = std::pow(rslopeimax, constants::DMI);

    const double rsloper2max = rslopermax * rslopermax;
    const double rslopes2max = rslopesmax * rslopesmax;
    const double rslopeg2max = rslopegmax * rslopegmax;
    const double rslopei2max = rslopeimax * rslopeimax;

    const double rsloper3max = rsloper2max * rslopermax;
    const double rslopes3max = rslopes2max * rslopesmax;
    const double rslopeg3max = rslopeg2max * rslopegmax;
    const double rslopei3max = rslopei2max * rslopeimax;

    return SlopeParams{
        pidnr, pidn0s, pidni,
        pvtr, pvtrn, pvti, pvtin, pvts,
        rslopermax, rslopesmax, rslopegmax, rslopeimax,
        rsloperbmax, rslopesbmax, rslopeibmax,
        rslopermmax, rslopesmmax, rslopegmmax, rslopeimmax,
        rsloperdmax, rslopesdmax, rslopegdmax, rslopeidmax,
        rsloper2max, rslopes2max, rslopeg2max, rslopei2max,
        rsloper3max, rslopes3max, rslopeg3max, rslopei3max
    };
}

torch::Tensor compute_supcol(const torch::Tensor& t) {
    return scalar_like(273.15, t) - torch::clamp(t, /*min=*/153.15, /*max=*/393.15);
}

torch::Tensor n0sfac(const torch::Tensor& supcol) {
    auto capped = torch::clamp(
        torch::exp(constants::ALPHA * supcol),
        /*min=*/1.0,
        /*max=*/constants::N0SMAX / constants::N0S
    );
    return ops::isfinite_else(capped, 1.0);
}

SlopeOutputs slope_kdm6_torch(const SlopeKdm6Inputs& inputs, const SlopeParams& params) {
    auto n0sfac_out = n0sfac(compute_supcol(inputs.t));

    auto rain = rain_slope_components(
        inputs.qr, inputs.nr, inputs.den, inputs.denfac, params, /*include_den_gate=*/true);

    auto snow_mask = (inputs.qs <= constants::QCRMIN) | (inputs.den <= 0.0);
    auto pidn0s = scalar_like(params.pidn0s, inputs.qs);
    auto lamdas = lamda_from_ratio(
        pidn0s * n0sfac_out / domain_clamp(inputs.qs * inputs.den),
        constants::DMS + 1.0
    );
    auto rslope_s_raw = 1.0 / lamdas;
    auto rslope_s = torch::where(snow_mask, scalar_like(params.rslopesmax, inputs.qs), rslope_s_raw);
    auto rslopeb_s = torch::where(
        snow_mask,
        scalar_like(params.rslopesbmax, inputs.qs),
        ops::safe_pow(rslope_s, constants::BVTS)
    );
    auto rslopemu_s = torch::where(
        snow_mask,
        scalar_like(params.rslopesmmax, inputs.qs),
        ops::safe_pow(rslope_s, constants::MUS)
    );
    auto rsloped_s = torch::where(
        snow_mask,
        scalar_like(params.rslopesdmax, inputs.qs),
        ops::safe_pow(rslope_s, constants::DMS)
    );
    auto rslope2_s = torch::where(snow_mask, scalar_like(params.rslopes2max, inputs.qs), rslope_s * rslope_s);
    auto rslope3_s = torch::where(snow_mask, scalar_like(params.rslopes3max, inputs.qs), rslope2_s * rslope_s);

    auto graupel_mask = (inputs.qg <= constants::QCRMIN) | (inputs.den <= 0.0) | (inputs.pidn0g <= 0.0);
    auto lamdag = lamda_from_ratio(inputs.pidn0g / domain_clamp(inputs.qg * inputs.den), constants::DMG + 1.0);
    auto rslope_g_raw = 1.0 / lamdag;
    auto rslope_g = torch::where(graupel_mask, scalar_like(params.rslopegmax, inputs.qg), rslope_g_raw);
    auto rslopeb_g = torch::where(graupel_mask, inputs.rslopegbmax, ops::safe_pow(rslope_g, inputs.bvtg));
    auto rslopemu_g = torch::where(
        graupel_mask,
        scalar_like(params.rslopegmmax, inputs.qg),
        ops::safe_pow(rslope_g, constants::MUG)
    );
    auto rsloped_g = torch::where(
        graupel_mask,
        scalar_like(params.rslopegdmax, inputs.qg),
        ops::safe_pow(rslope_g, constants::DMG)
    );
    auto rslope2_g = torch::where(graupel_mask, scalar_like(params.rslopeg2max, inputs.qg), rslope_g * rslope_g);
    auto rslope3_g = torch::where(graupel_mask, scalar_like(params.rslopeg3max, inputs.qg), rslope2_g * rslope_g);

    // Fortran slope_kdm6 (kdm6.f90:3477) gates ice slope with `qci .le. qmin`
    // where qmin = epsilon = 1e-15 (passed in from driver). EPS matches this.
    // (kdm6.f90:1417,1602 use a DIFFERENT 1e-14 gate for the n0i/lamda snap
    // outside slope_kdm6 — that lives in apply_dsd_number_limiters land, not
    // here. Don't conflate the two.)
    auto ice_mask = (inputs.qi <= constants::EPS) | (inputs.den <= 0.0) | (inputs.ni <= 0.0);
    auto pidni = scalar_like(params.pidni, inputs.qi);
    auto lamdai = lamda_from_ratio(pidni * inputs.ni / domain_clamp(inputs.qi * inputs.den), constants::DMI);
    auto rslope_i_raw = torch::clamp(
        1.0 / lamdai,
        /*min=*/1.0 / constants::LAMDAIMAX,
        /*max=*/1.0 / constants::LAMDAIMIN
    );
    auto rslope_i = torch::where(ice_mask, scalar_like(params.rslopeimax, inputs.qi), rslope_i_raw);
    auto rslopeb_i = torch::where(
        ice_mask,
        scalar_like(params.rslopeibmax, inputs.qi),
        ops::safe_pow(rslope_i, constants::BVTI)
    );
    auto rslopemu_i = torch::where(
        ice_mask,
        scalar_like(params.rslopeimmax, inputs.qi),
        ops::safe_pow(rslope_i, constants::MUI)
    );
    auto rsloped_i = torch::where(
        ice_mask,
        scalar_like(params.rslopeidmax, inputs.qi),
        ops::safe_pow(rslope_i, constants::DMI)
    );
    auto rslope2_i = torch::where(ice_mask, scalar_like(params.rslopei2max, inputs.qi), rslope_i * rslope_i);
    auto rslope3_i = torch::where(ice_mask, scalar_like(params.rslopei3max, inputs.qi), rslope2_i * rslope_i);

    auto vt_s = scalar_like(params.pvts, inputs.qs) * rslopeb_s * inputs.denfac;
    auto vt_g = inputs.pvtg * rslopeb_g * inputs.denfac;
    auto vt_i = scalar_like(params.pvti, inputs.qi) * rslopeb_i * inputs.denfac;

    vt_s = torch::where(inputs.qs <= 0.0, torch::zeros_like(inputs.qs), vt_s);
    vt_g = torch::where(inputs.qg <= 0.0, torch::zeros_like(inputs.qg), vt_g);
    vt_i = torch::where(inputs.qi <= 0.0, torch::zeros_like(inputs.qi), vt_i);

    auto vtn_i = scalar_like(params.pvtin, inputs.qi) * rslopeb_i * inputs.denfac;
    vtn_i = torch::where(inputs.ni <= 0.0, torch::zeros_like(inputs.ni), vtn_i);

    return SlopeOutputs{
        rain.rslope, rslope_s, rslope_g, rslope_i,
        rain.rslopeb, rslopeb_s, rslopeb_g, rslopeb_i,
        rain.rslopemu, rslopemu_s, rslopemu_g, rslopemu_i,
        rain.rsloped, rsloped_s, rsloped_g, rsloped_i,
        rain.rslope2, rslope2_s, rslope2_g, rslope2_i,
        rain.rslope3, rslope3_s, rslope3_g, rslope3_i,
        rain.vt, vt_s, vt_g, vt_i,
        rain.vtn, vtn_i,
        n0sfac_out
    };
}

SlopeRainOutputs slope_rain_torch(const torch::Tensor& qr,
                                  const torch::Tensor& nr,
                                  const torch::Tensor& den,
                                  const torch::Tensor& denfac,
                                  const torch::Tensor& t,
                                  const SlopeParams& params) {
    (void)t;
    return rain_slope_components(qr, nr, den, denfac, params, /*include_den_gate=*/false);
}

}  // namespace slope
}  // namespace kdm6
