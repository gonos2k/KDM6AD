#include "kdm6/slope.h"
#include "kdm6/fconst.h"

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
    // Fortran F:3441 lamdar(x,y,z)= exp(log(((pidnr*z)/(x*y)))*(1./dmr)).
    // Route exp/log through system libm (ops::libm_*) to match gfortran's libm
    // rounding (Sleef-vs-libm last-ULP divergence on the operational float32 path).
    // Fortran form is `*(1./dmr)` — multiply by the f32 reciprocal (step-65 class).
    const double inv = static_cast<double>(1.0f / static_cast<float>(exponent));
    return ops::libm_exp(ops::libm_log(domain_clamp(ratio)) * inv);
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
    // Fortran F:3551-3554: the `if(nrs<=0) vtn=0` zeroing is a DEAD STORE — F:3553 then
    // reassigns vtn=pvtrn*rslopeb*denfac unconditionally, so Fortran always uses nonzero vtn
    // (vt zeroing at F:3547-3550 comes AFTER its assignment, so vt zeroing IS kept above). 1:1 fix #5.

    return SlopeRainOutputs{/*rslope=*/rslope, /*rslopeb=*/rslopeb, /*rslopemu=*/rslopemu,
                            /*rsloped=*/rsloped, /*rslope2=*/rslope2, /*rslope3=*/rslope3,
                            /*vt=*/vt, /*vtn=*/vtn};
}

}  // namespace

SlopeParams default_slope_params() {
    const auto rgmma = [](double x) {
        // Fortran rgmma = Γ(x) (review6 audit fix).
        return static_cast<double>(fconst::rgmma_f(static_cast<float>(x)));  // Fortran-faithful f32 (step-67 class)
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

    const double pidnr = fconst::get().pidnr;   // f32-stepwise (kdm6init F:3235)
    const double pidn0s = cms * constants::N0S * g1pdsms / g1pms;
    const double pidni = fconst::get().pidni;   // f32-stepwise (kdm6init F:3263)

    const double pvtr = constants::AVTR * g1pdrbrmr / g1pdrmr;
    const double pvtrn = constants::AVTR * g1pbrmr / g1pmr;
    const double pvts = constants::AVTS * g1pdsbsms / g1pdsms;
    const double pvti = constants::AVTI * g1pdibimi / g1pdimi;
    const double pvtin = constants::AVTI * g1pbimi / g1pmi;

    // STEP-79 SEED (cell-2): Fortran kdm6init builds the whole rslope*max family
    // REAL(4)-STEPWISE (F:3297-3340) — f32 reciprocal, f32 squares/cubes, powf for
    // the b/m/d powers. Double-then-demote differs 1 ULP (rslopei2max 2AA9F3C9 vs
    // gfortran 2AA9F3C8), consumed raw by inactive-branch rates (pidep). fconst idiom.
    const float lamdarmax_f = static_cast<float>(constants::LAMDARMAX);
    const float lamdasmax_f = static_cast<float>(constants::LAMDASMAX);
    const float lamdagmax_f = static_cast<float>(constants::LAMDAGMAX);
    const float lamdaimax_f = static_cast<float>(constants::LAMDAIMAX);
    const float rslopermax_f = 1.0f / lamdarmax_f;
    const float rslopesmax_f = 1.0f / lamdasmax_f;
    const float rslopegmax_f = 1.0f / lamdagmax_f;
    const float rslopeimax_f = 1.0f / lamdaimax_f;
    const double rslopermax = rslopermax_f;
    const double rslopesmax = rslopesmax_f;
    const double rslopegmax = rslopegmax_f;
    const double rslopeimax = rslopeimax_f;

    const double rsloperbmax = std::powf(rslopermax_f, static_cast<float>(constants::BVTR));
    const double rslopesbmax = std::powf(rslopesmax_f, static_cast<float>(constants::BVTS));
    const double rslopeibmax = std::powf(rslopeimax_f, static_cast<float>(constants::BVTI));

    const double rslopermmax = (constants::MUR == 0.0) ? 1.0 : std::powf(rslopermax_f, static_cast<float>(constants::MUR));
    const double rslopesmmax = (constants::MUS == 0.0) ? 1.0 : std::powf(rslopesmax_f, static_cast<float>(constants::MUS));
    const double rslopegmmax = (constants::MUG == 0.0) ? 1.0 : std::powf(rslopegmax_f, static_cast<float>(constants::MUG));
    const double rslopeimmax = (constants::MUI == 0.0) ? 1.0 : std::powf(rslopeimax_f, static_cast<float>(constants::MUI));

    const double rsloperdmax = std::powf(rslopermax_f, static_cast<float>(constants::DMR));
    const double rslopesdmax = std::powf(rslopesmax_f, static_cast<float>(constants::DMS));
    const double rslopegdmax = std::powf(rslopegmax_f, static_cast<float>(constants::DMG));
    const double rslopeidmax = std::powf(rslopeimax_f, static_cast<float>(constants::DMI));

    const float rsloper2max_f = rslopermax_f * rslopermax_f;
    const float rslopes2max_f = rslopesmax_f * rslopesmax_f;
    const float rslopeg2max_f = rslopegmax_f * rslopegmax_f;
    const float rslopei2max_f = rslopeimax_f * rslopeimax_f;
    const double rsloper2max = rsloper2max_f;
    const double rslopes2max = rslopes2max_f;
    const double rslopeg2max = rslopeg2max_f;
    const double rslopei2max = rslopei2max_f;

    const double rsloper3max = rsloper2max_f * rslopermax_f;
    const double rslopes3max = rslopes2max_f * rslopesmax_f;
    const double rslopeg3max = rslopeg2max_f * rslopegmax_f;
    const double rslopei3max = rslopei2max_f * rslopeimax_f;

    return SlopeParams{
        /*pidnr=*/pidnr, /*pidn0s=*/pidn0s, /*pidni=*/pidni,
        /*pvtr=*/pvtr, /*pvtrn=*/pvtrn, /*pvti=*/pvti, /*pvtin=*/pvtin, /*pvts=*/pvts,
        /*rslopermax=*/rslopermax, /*rslopesmax=*/rslopesmax, /*rslopegmax=*/rslopegmax, /*rslopeimax=*/rslopeimax,
        /*rsloperbmax=*/rsloperbmax, /*rslopesbmax=*/rslopesbmax, /*rslopeibmax=*/rslopeibmax,
        /*rslopermmax=*/rslopermmax, /*rslopesmmax=*/rslopesmmax, /*rslopegmmax=*/rslopegmmax, /*rslopeimmax=*/rslopeimmax,
        /*rsloperdmax=*/rsloperdmax, /*rslopesdmax=*/rslopesdmax, /*rslopegdmax=*/rslopegdmax, /*rslopeidmax=*/rslopeidmax,
        /*rsloper2max=*/rsloper2max, /*rslopes2max=*/rslopes2max, /*rslopeg2max=*/rslopeg2max, /*rslopei2max=*/rslopei2max,
        /*rsloper3max=*/rsloper3max, /*rslopes3max=*/rslopes3max, /*rslopeg3max=*/rslopeg3max, /*rslopei3max=*/rslopei3max
    };
}

torch::Tensor compute_supcol(const torch::Tensor& t) {
    // Fortran F:3477 supcol = t0c - t (raw, no clamp). 1:1 parity fix #7 (AD-faithful).
    return scalar_like(273.15, t) - t;
}

torch::Tensor n0sfac(const torch::Tensor& supcol) {
    // Fortran F:3479 n0sfac = max(min(exp(alpha*supcol),n0smax/n0s),1.).
    // Route exp through system libm to match gfortran libm rounding.
    auto capped = torch::clamp(
        ops::libm_exp(constants::ALPHA * supcol),
        /*min=*/1.0,
        /*max=*/constants::N0SMAX / constants::N0S
    );
    return ops::isfinite_else(capped, 1.0);
}

SlopeOutputs slope_kdm6_torch(const SlopeKdm6Inputs& inputs, const SlopeParams& params) {
    auto n0sfac_out = n0sfac(compute_supcol(inputs.t));

    auto rain = rain_slope_components(
        inputs.qr, inputs.nr, inputs.den, inputs.denfac, params, /*include_den_gate=*/true);

    auto snow_mask = (inputs.qs <= constants::QCRMIN);
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

    auto graupel_mask = (inputs.qg <= constants::QCRMIN);
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

    // Fortran slope_kdm6 (kdm6.F:3527) gates ice slope with `qci .le. qmin`
    // where qmin = epsilon = 1e-15 (passed in from driver). EPS matches this.
    // (kdm6.F:1467,1652 use a DIFFERENT 1e-14 gate for the n0i/lamda snap
    // outside slope_kdm6 — that lives in apply_dsd_number_limiters land, not
    // here. Don't conflate the two.)
    auto ice_mask = (inputs.qi <= constants::EPS);
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
    // Fortran F:3578: vt(:,:,4) = DBLE(pvti)*rslopeb*denfac — the vt array is
    // DOUBLE PRECISION (class-7), so the ice fall speed is an f64 VALUE consumed
    // unrounded by work1(4)/falk (falk applies the single f32 rounding). Step-72
    // cell-B vtprec residual.
    auto vt_i = params.pvti * rslopeb_i.to(torch::kFloat64) * inputs.denfac;

    vt_s = torch::where(inputs.qs <= 0.0, torch::zeros_like(inputs.qs), vt_s);
    vt_g = torch::where(inputs.qg <= 0.0, torch::zeros_like(inputs.qg), vt_g);
    vt_i = torch::where(inputs.qi <= 0.0, torch::zeros_like(vt_i), vt_i);

    auto vtn_i = params.pvtin * rslopeb_i.to(torch::kFloat64) * inputs.denfac;  // workn(2) DOUBLE — same class
    // Fortran F:3553-3554: vtn_i dead-store (reassigned unconditionally after the ni<=0 zeroing). 1:1 fix #5.

    return SlopeOutputs{
        /*rslope_r=*/rain.rslope, /*rslope_s=*/rslope_s, /*rslope_g=*/rslope_g, /*rslope_i=*/rslope_i,
        /*rslopeb_r=*/rain.rslopeb, /*rslopeb_s=*/rslopeb_s, /*rslopeb_g=*/rslopeb_g, /*rslopeb_i=*/rslopeb_i,
        /*rslopemu_r=*/rain.rslopemu, /*rslopemu_s=*/rslopemu_s, /*rslopemu_g=*/rslopemu_g, /*rslopemu_i=*/rslopemu_i,
        /*rsloped_r=*/rain.rsloped, /*rsloped_s=*/rsloped_s, /*rsloped_g=*/rsloped_g, /*rsloped_i=*/rsloped_i,
        /*rslope2_r=*/rain.rslope2, /*rslope2_s=*/rslope2_s, /*rslope2_g=*/rslope2_g, /*rslope2_i=*/rslope2_i,
        /*rslope3_r=*/rain.rslope3, /*rslope3_s=*/rslope3_s, /*rslope3_g=*/rslope3_g, /*rslope3_i=*/rslope3_i,
        /*vt_r=*/rain.vt, /*vt_s=*/vt_s, /*vt_g=*/vt_g, /*vt_i=*/vt_i,
        /*vtn_r=*/rain.vtn, /*vtn_i=*/vtn_i,
        /*n0sfac_field=*/n0sfac_out
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
