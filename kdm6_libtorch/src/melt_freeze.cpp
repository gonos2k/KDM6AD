#include "kdm6/melt_freeze.h"

#include <cmath>

namespace kdm6 {
namespace melt {
namespace {

constexpr double PI = 3.14159265358979323846;

double rgmma_scalar(double x) {
    // Fortran rgmma = Γ(x) (review6 audit fix).
    return std::exp(std::lgamma(x));
}

torch::Tensor xka(const torch::Tensor& t, const torch::Tensor& den) {
    auto viscos = 1.496e-6 * (t * torch::sqrt(t)) / (t + 120.0) / den;
    return 1.414e3 * viscos * den;
}

}  // namespace

MeltingParams default_melting_params(double xlf) {
    const double g2pms = rgmma_scalar(2.0 + constants::MUS);
    const double g2pmg = rgmma_scalar(2.0 + constants::MUG);
    const double bvts2 = 2.5 + 0.5 * constants::BVTS + constants::MUS;
    const double g5pbso2 = rgmma_scalar(bvts2);
    const double precs1 = 4.0 * 0.65 * g2pms;
    const double precs2 = 4.0 * 0.44 * std::pow(constants::AVTS, 0.5) * g5pbso2;
    const double precg1 = 4.0 * 0.78 * g2pmg;
    return MeltingParams{
        /*precs1=*/precs1, /*precs2=*/precs2,
        /*precg1=*/precg1,
        /*xlf=*/xlf,
        /*t0c=*/273.15,
        /*qcrmin=*/constants::QCRMIN,
    };
}

MeltingOutputs melting_torch(
    const MeltingInputs& in,
    const MeltingParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(in.qs);
    auto warm = in.t > p.t0c;
    auto den_safe = torch::clamp(in.den, /*min=*/p.qcrmin);

    auto xka_val = xka(in.t, in.den);

    // ── psmlt ──────────────────────────────────────────────────────────
    auto snow_active = torch::logical_and(warm, in.qs > 0);
    auto coeres_s = in.rslope2_s
                  * torch::sqrt(torch::clamp(in.rslope_s * in.rslopeb_s, /*min=*/p.qcrmin))
                  * in.rslopemu_s;
    auto psmlt_raw = xka_val / p.xlf * (p.t0c - in.t) * in.n0sfac
                     * PI / 2.0
                     * (p.precs1 * in.n0so * in.rslope2_s * in.rslopemu_s
                        + p.precs2 * in.n0so * in.work2 * coeres_s)
                     / den_safe;
    auto psmlt_dt = psmlt_raw * dtcld;
    auto psmlt_capped = torch::minimum(torch::maximum(psmlt_dt, -in.qs), zero);
    auto psmlt = torch::where(snow_active, psmlt_capped, zero) / dtcld;

    auto sfac_raw = in.rslope_s * in.n0so * in.n0sfac
                    / torch::clamp(in.qs, /*min=*/p.qcrmin);
    auto sfac = torch::where(
        torch::logical_and(snow_active, in.qs > p.qcrmin),
        sfac_raw, zero
    );

    // ── pgmlt ──────────────────────────────────────────────────────────
    auto graupel_active = torch::logical_and(warm, in.qg > 0);
    auto coeres_g = in.rslope2_g
                  * torch::sqrt(torch::clamp(in.rslope_g * in.rslopeb_g, /*min=*/p.qcrmin))
                  * in.rslopemu_g;
    auto pgmlt_raw = xka_val / p.xlf * (p.t0c - in.t)
                     * PI / 2.0
                     * (p.precg1 * in.n0go * in.rslope2_g * in.rslopemu_g
                        + in.precg2 * in.n0go * in.work2 * coeres_g)
                     / den_safe;
    auto pgmlt_dt = pgmlt_raw * dtcld;
    auto pgmlt_capped = torch::minimum(torch::maximum(pgmlt_dt, -in.qg), zero);
    auto pgmlt = torch::where(graupel_active, pgmlt_capped, zero) / dtcld;

    auto gfac_raw = in.rslope_g * in.n0go / torch::clamp(in.qg, /*min=*/p.qcrmin);
    auto gfac = torch::where(
        torch::logical_and(graupel_active, in.qg > p.qcrmin),
        gfac_raw, zero
    );

    auto rhox_safe = torch::clamp(in.rhox, /*min=*/constants::DENS);
    auto delta_brs = torch::where(graupel_active, pgmlt / rhox_safe, zero);

    // ── pimlt: instantaneous ───────────────────────────────────────────
    auto ice_active = torch::logical_and(warm, in.qi > 0);
    auto pimlt_qi = torch::where(ice_active, in.qi, zero);
    auto pimlt_ni = torch::where(ice_active, in.ni, zero);

    return MeltingOutputs{
        psmlt, pgmlt, pimlt_qi, pimlt_ni, sfac, gfac, delta_brs,
    };
}

// ═══════════════════════════════════════════════════════════════════════════
// D2: Contact freezing (Meyers)
// ═══════════════════════════════════════════════════════════════════════════

ContactFreezingParams default_contact_freezing_params(double xlf) {
    const double cmc = PI * constants::DENR / 6.0;
    const double g1pmc = rgmma_scalar(1.0 + 1.0 / (constants::MUC + 1.0));
    const double g4pmc = rgmma_scalar(1.0 + 4.0 / (constants::MUC + 1.0));
    return ContactFreezingParams{
        cmc, constants::MUC, g1pmc, g4pmc,
        /*rcn=*/0.1e-6, /*boltzmann=*/1.38e-23,
        xlf, constants::QCRMIN, constants::NCMIN, /*supcol_threshold=*/2.0,
    };
}

ContactFreezingOutputs contact_freezing_torch(
    const ContactFreezingInputs& in,
    const ContactFreezingParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(in.qc);
    auto active = torch::logical_and(in.supcol > p.supcol_threshold, in.qc > p.qmin);
    auto den_safe = torch::clamp(in.den, /*min=*/p.qmin);
    auto supcolt = torch::clamp(in.supcol, /*min=*/-1e30, /*max=*/70.0);
    auto Nic = torch::exp(-2.80 + 0.262 * supcolt) * 1000.0;

    auto ele1 = 7.37 * in.t / (288.0 * 10.0 * in.p) / 100.0;
    const double ele2 = 4.0 * PI * p.boltzmann / (6.0 * PI * p.rcn);
    auto viscos_t = 1.496e-6 * (in.t * torch::sqrt(in.t)) / (in.t + 120.0) / in.den;
    auto difa = ele2 * in.t * (1.0 + ele1 / p.rcn) / (viscos_t * in.den);

    auto pinuc_raw = p.cmc * difa * 2.0 * PI * Nic * in.n0c / den_safe / (p.muc + 1.0)
                     * p.g4pmc * in.rslopecmu * in.rslopec3 * in.rslopec2 * dtcld;
    auto pinuc = torch::where(active, torch::minimum(pinuc_raw, in.qc), zero);

    auto nc_active = torch::logical_and(active, in.nc > p.ncmin);
    auto ninuc_raw = difa * 2.0 * PI * Nic * in.n0c / (p.muc + 1.0)
                     * p.g1pmc * in.rslopecmu * in.rslopec2 * dtcld;
    auto ninuc = torch::where(nc_active, torch::minimum(ninuc_raw, in.nc), zero);
    return ContactFreezingOutputs{pinuc, ninuc};
}

// ═══════════════════════════════════════════════════════════════════════════
// D3: Bigg cloud freezing
// ═══════════════════════════════════════════════════════════════════════════

BiggCloudParams default_bigg_cloud_params() {
    const double cmc = PI * constants::DENR / 6.0;
    const double g1p2dcomuc1 = rgmma_scalar(1.0 + 2.0 * constants::DMC / (constants::MUC + 1.0));
    const double g1pdcomuc1 = rgmma_scalar(1.0 + constants::DMC / (constants::MUC + 1.0));
    return BiggCloudParams{
        cmc, constants::DENR, constants::MUC,
        constants::PFRZ1, constants::PFRZ2,
        g1p2dcomuc1, g1pdcomuc1,
        constants::QCRMIN, constants::NCMIN,
    };
}

BiggCloudOutputs bigg_cloud_freezing_torch(
    const BiggCloudInputs& in,
    const BiggCloudParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(in.qc);
    auto active = torch::logical_and(in.supcol > 0, in.qc > p.qmin);
    auto den_safe = torch::clamp(in.den, /*min=*/p.qmin);
    auto supcolt = torch::clamp(in.supcol, /*min=*/-1e30, /*max=*/70.0);
    auto bigg_factor = torch::exp(p.pfrz2 * supcolt) - 1.0;

    auto pfrzdtc_raw = p.cmc * p.cmc * p.pfrz1 * in.n0c / den_safe / p.denr
                       / (p.muc + 1.0) * bigg_factor * p.g1p2dcomuc1
                       * in.rslopecmu * in.rslopecd * in.rslopecd * in.rslopec * dtcld;
    auto pfrzdtc = torch::where(active, torch::minimum(pfrzdtc_raw, in.qc), zero);

    auto nc_active = torch::logical_and(active, in.nc > p.ncmin);
    auto nfrzdtc_raw = p.cmc * p.pfrz1 * in.n0c / p.denr / (p.muc + 1.0)
                       * bigg_factor * p.g1pdcomuc1 * in.rslopecmu * in.rslopec
                       * in.rslopecd * dtcld;
    auto nfrzdtc = torch::where(nc_active, torch::minimum(nfrzdtc_raw, in.nc), zero);
    return BiggCloudOutputs{pfrzdtc, nfrzdtc};
}

// ═══════════════════════════════════════════════════════════════════════════
// D4: Bigg rain freezing
// ═══════════════════════════════════════════════════════════════════════════

BiggRainParams default_bigg_rain_params() {
    const double cmr = PI * constants::DENR / 6.0;
    const double g1pdrmr = rgmma_scalar(1.0 + constants::DMR + constants::MUR);
    const double g1p2drmr = rgmma_scalar(1.0 + 2.0 * constants::DMR + constants::MUR);
    return BiggRainParams{
        cmr, constants::DENR,
        constants::PFRZ1, constants::PFRZ2,
        g1pdrmr, g1p2drmr,
        constants::QCRMIN, constants::NRMIN,
    };
}

BiggRainOutputs bigg_rain_freezing_torch(
    const BiggRainInputs& in,
    const BiggRainParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(in.qr);
    auto active = torch::logical_and(in.supcol > 0, in.qr > 0);
    auto den_safe = torch::clamp(in.den, /*min=*/p.qmin);
    auto supcolt = torch::clamp(in.supcol, /*min=*/-1e30, /*max=*/70.0);
    auto bigg_factor = torch::exp(p.pfrz2 * supcolt) - 1.0;

    auto pfrzdtr_raw = p.cmr * p.cmr * p.pfrz1 * in.n0r / den_safe / p.denr
                       * bigg_factor * in.rsloped_r * in.rsloped_r * in.rslopemu_r
                       * in.rslope_r * p.g1p2drmr * dtcld;
    auto pfrzdtr = torch::where(active, torch::minimum(pfrzdtr_raw, in.qr), zero);

    auto nr_active = torch::logical_and(active, in.nr > p.nrmin);
    auto nfrzdtr_raw = p.cmr / p.denr * p.pfrz1 * in.n0r * bigg_factor
                       * p.g1pdrmr * in.rslope_r * in.rsloped_r * in.rslopemu_r * dtcld;
    auto nfrzdtr = torch::where(nr_active, torch::minimum(nfrzdtr_raw, in.nr), zero);

    auto delta_brs = pfrzdtr / p.denr;
    return BiggRainOutputs{pfrzdtr, nfrzdtr, delta_brs};
}

// ═══════════════════════════════════════════════════════════════════════════
// D5: Enhanced melting
// ═══════════════════════════════════════════════════════════════════════════

EnhancedMeltingParams default_enhanced_melting_params(double cliq, double xlf) {
    return EnhancedMeltingParams{cliq, xlf, constants::QCRMIN};
}

EnhancedMeltingOutputs enhanced_melting_torch(
    const EnhancedMeltingInputs& in,
    const EnhancedMeltingParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(in.qs);
    auto warm = in.supcol < 0;

    auto snow_active = torch::logical_and(warm, in.qs > 0);
    auto pseml_raw = p.cliq * in.supcol * (in.paacw + in.psacr) / p.xlf;
    auto pseml_capped = torch::minimum(torch::maximum(pseml_raw, -in.qs / dtcld), zero);
    auto pseml = torch::where(snow_active, pseml_capped, zero);

    auto snow_active_qcr = torch::logical_and(snow_active, in.qs > p.qcrmin);
    auto sfac = in.rslope_s * in.n0so * in.n0sfac / torch::clamp(in.qs, /*min=*/p.qcrmin);
    auto nseml = torch::where(snow_active_qcr, -sfac * pseml, zero);

    auto graupel_active = torch::logical_and(warm, in.qg > 0);
    auto pgeml_raw = p.cliq * in.supcol * (in.paacw + in.pgacr) / p.xlf;
    auto pgeml_capped = torch::minimum(torch::maximum(pgeml_raw, -in.qg / dtcld), zero);
    auto pgeml = torch::where(graupel_active, pgeml_capped, zero);

    auto graupel_active_qcr = torch::logical_and(graupel_active, in.qg > p.qcrmin);
    auto gfac = in.rslope_g * in.n0go / torch::clamp(in.qg, /*min=*/p.qcrmin);
    auto ngeml = torch::where(graupel_active_qcr, -gfac * pgeml, zero);

    return EnhancedMeltingOutputs{pseml, nseml, pgeml, ngeml};
}

}  // namespace melt
}  // namespace kdm6
