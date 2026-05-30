#pragma once
//
// KDM6 melting / freezing — Step D.
// Python oracle: kdm6_torch/kdm6/melt_freeze.py
//
//   D1 melting (1317-1392): psmlt + pgmlt + pimlt + sfac/gfac/delta_brs
//   D2-D5: contact freezing, Bigg cloud/rain freezing, enhanced melting (TBD)
//

#include "kdm6/constants.h"
#include <torch/torch.h>

namespace kdm6 {
namespace melt {

// ─── Step D1: Melting ────────────────────────────────────────────────────────

struct MeltingParams {
    double precs1, precs2;
    double precg1;
    double xlf;       // latent heat of fusion (J/kg)
    double t0c;
    double qcrmin;
};

inline constexpr double DEFAULT_XLF = 3.50e5;  // Fortran XLF (module_model_constants.F:56)

MeltingParams default_melting_params(double xlf = DEFAULT_XLF);

struct MeltingOutputs {
    torch::Tensor psmlt, pgmlt;
    torch::Tensor pimlt_qi, pimlt_ni;
    torch::Tensor sfac, gfac;
    torch::Tensor delta_brs;
};

struct MeltingInputs {
    torch::Tensor qs, qg, qi, ni;
    torch::Tensor t, p, den, rhox;
    torch::Tensor n0so, n0go, n0sfac;
    torch::Tensor work2;
    torch::Tensor precg2;
    torch::Tensor rslope_s, rslope2_s, rslopeb_s, rslopemu_s;
    torch::Tensor rslope_g, rslope2_g, rslopeb_g, rslopemu_g;
};

MeltingOutputs melting_torch(
    const MeltingInputs& inputs,
    const MeltingParams& params,
    double dtcld
);

// ─── Step D2: Contact freezing (Meyers) ──────────────────────────────────────

struct ContactFreezingParams {
    double cmc, muc;
    double g1pmc, g4pmc;
    double rcn, boltzmann;
    double xlf;
    double qmin, ncmin;
    double supcol_threshold;
    // Per-cell ncmin override (operational xland path; see runtime.cpp).
    c10::optional<torch::Tensor> ncmin_tensor;
};

ContactFreezingParams default_contact_freezing_params(double xlf = DEFAULT_XLF);

struct ContactFreezingOutputs {
    torch::Tensor pinuc, ninuc;
};

struct ContactFreezingInputs {
    torch::Tensor qc, nc;
    torch::Tensor t, p, den;
    torch::Tensor n0c;
    torch::Tensor rslopec, rslopec2, rslopec3, rslopecmu;
    torch::Tensor supcol;
};

ContactFreezingOutputs contact_freezing_torch(
    const ContactFreezingInputs& inputs,
    const ContactFreezingParams& params,
    double dtcld
);

// ─── Step D3: Bigg cloud freezing ────────────────────────────────────────────

struct BiggCloudParams {
    double cmc, denr, muc;
    double pfrz1, pfrz2;
    double g1p2dcomuc1, g1pdcomuc1;
    double qmin, ncmin;
    // Per-cell ncmin override (operational xland path; see runtime.cpp).
    c10::optional<torch::Tensor> ncmin_tensor;
};

BiggCloudParams default_bigg_cloud_params();

struct BiggCloudOutputs {
    torch::Tensor pfrzdtc, nfrzdtc;
};

struct BiggCloudInputs {
    torch::Tensor qc, nc;
    torch::Tensor den;
    torch::Tensor n0c;
    torch::Tensor rslopec, rslopecd, rslopecmu;
    torch::Tensor supcol;
};

BiggCloudOutputs bigg_cloud_freezing_torch(
    const BiggCloudInputs& inputs,
    const BiggCloudParams& params,
    double dtcld
);

// ─── Step D4: Bigg rain freezing ─────────────────────────────────────────────

struct BiggRainParams {
    double cmr, denr;
    double pfrz1, pfrz2;
    double g1pdrmr, g1p2drmr;
    double qmin, nrmin;
};

BiggRainParams default_bigg_rain_params();

struct BiggRainOutputs {
    torch::Tensor pfrzdtr, nfrzdtr;
    torch::Tensor delta_brs;
};

struct BiggRainInputs {
    torch::Tensor qr, nr;
    torch::Tensor den;
    torch::Tensor n0r;
    torch::Tensor rslope_r, rsloped_r, rslopemu_r;
    torch::Tensor supcol;
};

BiggRainOutputs bigg_rain_freezing_torch(
    const BiggRainInputs& inputs,
    const BiggRainParams& params,
    double dtcld
);

// ─── Step D5: Enhanced melting ───────────────────────────────────────────────

struct EnhancedMeltingParams {
    double cliq;
    double xlf;
    double qcrmin;
};

inline constexpr double DEFAULT_CLIQ = 4190.0;  // Fortran cliq (module_model_constants.F:27)

EnhancedMeltingParams default_enhanced_melting_params(
    double cliq = DEFAULT_CLIQ, double xlf = DEFAULT_XLF
);

struct EnhancedMeltingOutputs {
    torch::Tensor pseml, nseml;
    torch::Tensor pgeml, ngeml;
};

struct EnhancedMeltingInputs {
    torch::Tensor qs, qg;
    torch::Tensor paacw, psacr, pgacr;
    torch::Tensor n0so, n0go, n0sfac;
    torch::Tensor rslope_s, rslope_g;
    torch::Tensor supcol;
};

EnhancedMeltingOutputs enhanced_melting_torch(
    const EnhancedMeltingInputs& inputs,
    const EnhancedMeltingParams& params,
    double dtcld
);

}  // namespace melt
}  // namespace kdm6
