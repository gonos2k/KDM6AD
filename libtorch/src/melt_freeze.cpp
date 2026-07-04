#include "kdm6/fconst.h"
#include "kdm6/melt_freeze.h"
#include "kdm6/ops.h"

#include <cmath>
#ifdef KDM6_SUBSTEP_DUMP
#include <fstream>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <string>
#include <vector>
#endif

namespace kdm6 {
namespace melt {
namespace {

constexpr double PI = 3.14159265358979323846;

double rgmma_scalar(double x) {
    // Fortran rgmma(x)=EXP(GAMMLN(x)) in REAL(4): f32 expf of the f32-rounded
    // double Lanczos — differs from exp(lgamma(double)) for NON-INTEGER args
    // (e.g. Γ(4/3), Γ(7/3) in D2/D3 freezing — the step-67 qi/ni seed class).
    return static_cast<double>(fconst::rgmma_f(static_cast<float>(x)));
}

torch::Tensor xka(const torch::Tensor& t, const torch::Tensor& den) {
    // AD-harden: clamp t≥1K — t·sqrt(t) backward = 0·Inf=NaN at t=0 (4D-Var control th can transiently
    // hit ≤0); inert at physical T (>1K). Mirrors thermo.cpp's t_safe. (audit round-3)
    auto t_safe = torch::clamp(t, 1.0);
    auto viscos = 1.496e-6 * (t_safe * torch::sqrt(t_safe)) / (t_safe + 120.0) / den;
    return 1.414e3 * viscos * den;
}

}  // namespace

MeltingParams default_melting_params(double xlf) {
    const double g2pms = rgmma_scalar(2.0 + constants::MUS);
    const double g2pmg = rgmma_scalar(2.0 + constants::MUG);
    const double bvts2 = 2.5 + 0.5 * constants::BVTS + constants::MUS;
    const double g5pbso2 = rgmma_scalar(bvts2);
    const double precs1 = 4.0 * 0.65 * g2pms;
    const float precs2_f32 = ((4.0f * 0.44f)
                              * ::powf(static_cast<float>(constants::AVTS), 0.5f))
                             * static_cast<float>(g5pbso2);  // Fortran precs2 REAL(4) (F:3255); avts**.5=powf (mirror warm.cpp precr2)
    const double precs2 = precs2_f32;
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
    // §1B (whole-chain roadmap FRZ-01): Fortran F:1310-1315 — coeres/precs1/precs2/rslopemu are
    // DOUBLE, psmlt is REAL(f32). The bracket (term1+term2) and the chain evaluate in f64; only the
    // psmlt store rounds to f32 once. C++ previously demoted the double precs1/precs2 scalars to f32
    // (torch weak-scalar) and summed via fma_acc (f32 two-rounding) — an f32-stepwise-vs-double-then-
    // round deviation. Build the bracket/chain in f64 (inner rslope2*sqrt(rslope*rslopeb) kept f32 to
    // match Fortran REAL operands), round once at the store. autograd-safe (.to(dtype) only).
    // §1B (corrected): Fortran precs1/precs2 are REAL(f32) (F:147 `real,save`), rslopemu/coeres are
    // DOUBLE (F:656/725). So the INNER products (precs1*n0so*rslope2), (precs2*n0so*work2) evaluate in
    // f32, and promote to f64 ONLY at the *rslopemu / *coeres step (DOUBLE); the term1+term2 add is f64;
    // psmlt is REAL → ONE f32 round at the store. (Earlier draft over-promoted the inner products to
    // f64 — a "REAL-constant regression"; precs* stay f32 here. torch weak-scalar keeps precs*tensor f32.)
    const auto F64 = torch::kFloat64;
    auto coeres_s = (in.rslope2_s
                  * torch::sqrt(torch::clamp(in.rslope_s * in.rslopeb_s, /*min=*/p.qcrmin))).to(F64)
                  * in.rslopemu_s.to(F64);
    auto psmlt_term1 = (p.precs1 * in.n0so * in.rslope2_s).to(F64) * in.rslopemu_s.to(F64);
    auto psmlt_term2 = (p.precs2 * in.n0so * in.work2).to(F64) * coeres_s;
    auto psmlt_sum = psmlt_term1 + psmlt_term2;
    auto psmlt_raw = ((xka_val / p.xlf * (p.t0c - in.t) * in.n0sfac * PI / 2.0).to(F64)
                     * psmlt_sum
                     / den_safe.to(F64)).to(in.qs.scalar_type());
    auto psmlt_dt = psmlt_raw * dtcld;
    auto psmlt_capped = torch::minimum(torch::maximum(psmlt_dt, -in.qs), zero);
    auto psmlt_capped_g = torch::where(snow_active, psmlt_capped, zero);  // CAPPED AMOUNT (Fortran F:1315)
    auto psmlt = psmlt_capped_g / dtcld;                                  // RATE (for state_update rate-sum)

    auto sfac_raw = in.rslope_s * in.n0so * in.n0sfac
                    / torch::clamp(in.qs, /*min=*/p.qcrmin);
    auto sfac = torch::where(
        torch::logical_and(snow_active, in.qs > p.qcrmin),
        sfac_raw, zero
    );

    // ── pgmlt ──────────────────────────────────────────────────────────
    auto graupel_active = torch::logical_and(warm, in.qg > 0);
    // §1B (FRZ-02): same as psmlt for graupel — F:1334-1338, coeres/precg1/precg2 DOUBLE, pgmlt REAL.
    // NOTE: pgmlt has NO n0sfac factor (snow-only). precg2 is a tensor input here (per-cell).
    // §1B (corrected): precg1/precg2 are REAL(f32) (F:147/F:649); rslopemu_g/coeres_g DOUBLE. Inner
    // products f32, promote to f64 only via *rslopemu_g / *coeres_g; f64 add; one f32 round at pgmlt.
    auto coeres_g = (in.rslope2_g
                  * torch::sqrt(torch::clamp(in.rslope_g * in.rslopeb_g, /*min=*/p.qcrmin))).to(F64)
                  * in.rslopemu_g.to(F64);
    auto pgmlt_term1 = (p.precg1 * in.n0go * in.rslope2_g).to(F64) * in.rslopemu_g.to(F64);
    auto pgmlt_term2 = (in.precg2 * in.n0go * in.work2).to(F64) * coeres_g;
    auto pgmlt_sum = pgmlt_term1 + pgmlt_term2;
    // §35 SEQUENTIAL coupling (Fortran F:1326→1336): psmlt updates t (t += xlf0/cpm·psmlt) BEFORE
    // pgmlt reads it. The C++/oracle previously computed BOTH psmlt & pgmlt from entry-t (parallel)
    // → C++≡oracle but both ≠ Fortran (cross-tree parity passes, WRF bitwise fails — §35 signature).
    // t1 = entry-t in non-snow cells (psmlt_capped_g≡0 there), psmlt-updated-t where snow melted.
    // Only pgmlt's xka(t)·(t0c−t) prefactor depends on t; the bracket (n0go/rslope/precg) is t-free.
    auto t1 = in.t + (p.xlf / in.cpm) * psmlt_capped_g;   // F:1326 (xlf=xlf0 in warm cells, =p.xlf)
    auto xka_val_g = xka(t1, in.den);                     // F:1336 xka(t1,den)
    auto pgmlt_raw = ((xka_val_g / p.xlf * (p.t0c - t1) * PI / 2.0).to(F64)
                     * pgmlt_sum
                     / den_safe.to(F64)).to(in.qs.scalar_type());
    auto pgmlt_dt = pgmlt_raw * dtcld;
    auto pgmlt_capped = torch::minimum(torch::maximum(pgmlt_dt, -in.qg), zero);
    auto pgmlt_capped_g = torch::where(graupel_active, pgmlt_capped, zero);  // CAPPED AMOUNT
    auto pgmlt = pgmlt_capped_g / dtcld;                                     // RATE

    auto gfac_raw = in.rslope_g * in.n0go / torch::clamp(in.qg, /*min=*/p.qcrmin);
    auto gfac = torch::where(
        torch::logical_and(graupel_active, in.qg > p.qcrmin),
        gfac_raw, zero
    );

    // §53b dtype-conditional rhox divisor: the f32 OP path divides by the PERSISTENT rhox RAW
    // (Fortran F:1384 brs += pgmlt/rhox against the F:990-init array — rhox=0 in never-active
    // cells → ±Inf, the documented brs -inf class; 0/0 → canonical qNaN, same on both trees).
    // The f64 DA path keeps the clamped-safe divisor (finite adjoint, no ±Inf into the graph).
    auto rhox_div = (in.rhox.scalar_type() == torch::kFloat32)
        ? in.rhox
        : torch::clamp(in.rhox, /*min=*/constants::DENS);
    auto delta_brs = torch::where(graupel_active, pgmlt / rhox_div, zero);
    auto delta_brs_capped = torch::where(graupel_active, pgmlt_capped_g / rhox_div, zero);  // AMOUNT (Fortran F:1351 brs+=pgmlt/rhox)

    // ── pimlt: instantaneous ───────────────────────────────────────────
    auto ice_active = torch::logical_and(warm, in.qi > 0);
    auto pimlt_qi = torch::where(ice_active, in.qi, zero);
    auto pimlt_ni = torch::where(ice_active, in.ni, zero);

    return MeltingOutputs{
        /*psmlt=*/psmlt, /*pgmlt=*/pgmlt,
        /*psmlt_capped=*/psmlt_capped_g, /*pgmlt_capped=*/pgmlt_capped_g, /*delta_brs_capped=*/delta_brs_capped,
        /*pimlt_qi=*/pimlt_qi, /*pimlt_ni=*/pimlt_ni,
        /*sfac=*/sfac, /*gfac=*/gfac, /*delta_brs=*/delta_brs,
    };
}

// ═══════════════════════════════════════════════════════════════════════════
// D2: Contact freezing (Meyers)
// ═══════════════════════════════════════════════════════════════════════════

ContactFreezingParams default_contact_freezing_params(double xlf) {
    // f32-stepwise kdm6init constants (fconst.h): cmc=(pi_f*1000)/6, g1pmc=Γ_f(1+1/3),
    // g4pmc=Γ_f(1+4/3) with the f32-stepwise argument 1.0f+4.0f/3.0f = 0x40155556
    // (the double-then-demote arg 0x40155555 is 1 ULP low — step-67 seed class).
    const double cmc = fconst::get().cmc;
    const double g1pmc = fconst::get().g1pmc;
    const double g4pmc = fconst::get().g4pmc;
    return ContactFreezingParams{
        cmc, constants::MUC, g1pmc, g4pmc,
        /*rcn=*/0.1e-6, /*boltzmann=*/1.38e-23,
        xlf, /*qmin=*/constants::EPS, constants::NCMIN, /*supcol_threshold=*/2.0,  // qmin=epsilon=1e-15 (Fortran F:1485 qci>qmin gate; den-clamp inert). 1:1 fix #1
        /*ncmin_tensor=*/c10::nullopt,
    };
}

ContactFreezingOutputs contact_freezing_torch(
    const ContactFreezingInputs& in,
    const ContactFreezingParams& p,
    double dtcld
) {
    // STEP-67 SEED: Fortran pinuc/ninuc are DOUBLE PRECISION scalars (F:738) and
    // n0c/rslopecmu are DOUBLE arrays (F:696-697), so the rate chain promotes to
    // f64 at the `*n0c` factor and stays f64 through the min() cap — there is NO
    // f32 rounding until the qci/nci state stores (F:1533-1537). The f32 PREFIX
    // (cmc·difa·2·pi·Nic, all REAL operands) stays f32-stepwise. torch type
    // promotion (f64 tensor ⊗ f32 tensor → f64) mirrors gfortran exactly; in.n0c
    // is the f64 intercept (runtime.cpp/coordinator.cpp).
    auto active = torch::logical_and(in.supcol > p.supcol_threshold, in.qc > p.qmin);
    auto den_safe = torch::clamp(in.den, /*min=*/p.qmin);
    auto supcolt = torch::clamp(in.supcol, /*min=*/-1e30, /*max=*/70.0);
    // Nic = exp(-2.80+0.262*supcolt)*1000 (F:1519): strict IEEE two-rounding in
    // source order — 0.262*supcolt rounds, then -2.80 + (.) rounds (was an fma
    // mirror of the -ffp-contract=fast contraction — step-67 seed class — before
    // the IEEE transition).
    auto nic_arg = ops::fma_acc(torch::full_like(supcolt, -2.80),
                                torch::full_like(supcolt, 0.262), supcolt);
    auto Nic = ops::libm_exp(nic_arg) * 1000.0;

    auto ele1 = 7.37 * in.t / (288.0 * 10.0 * in.p) / 100.0;
    // ele2 (F:1521) is evaluated REAL(4) stepwise by gfortran — fconst.h holds the
    // exact f32 value as a double (single demotion at the tensor op reproduces it).
    const double ele2 = fconst::get().ele2;
    auto t_safe = torch::clamp(in.t, 1.0);  // AD-harden: t·sqrt(t) grad = 0·Inf=NaN at t=0 (mirror thermo)
    auto viscos_t = 1.496e-6 * (t_safe * torch::sqrt(t_safe)) / (t_safe + 120.0) / in.den;
    auto difa = ele2 * in.t * (1.0 + ele1 / p.rcn) / (viscos_t * in.den);

    // f32 prefix h1..h4 = cmc*difa, *2, *pi, *Nic (each op REAL(4), F:1524); the
    // chain goes DOUBLE from `* in.n0c` on (f64 tensor) — Fortran mixed-precision.
    auto pinuc_raw = p.cmc * difa * 2.0 * PI * Nic * in.n0c / den_safe / (p.muc + 1.0)
                     * p.g4pmc * in.rslopecmu * in.rslopec3 * in.rslopec2 * dtcld;
    // min vs DBLE(qc) in f64 (F:1524 min(...,qci)); rate stays f64 to the apply.
    auto zero_d = torch::zeros_like(pinuc_raw);
    auto pinuc = torch::where(active, torch::minimum(pinuc_raw, in.qc.to(pinuc_raw.dtype())), zero_d);

    // Per-cell ncmin (xland-derived, see runtime.cpp). nullopt → scalar fallback.
    auto nc_above_ncmin = p.ncmin_tensor.has_value()
        ? in.nc > p.ncmin_tensor.value()
        : in.nc > p.ncmin;
    auto nc_active = torch::logical_and(active, nc_above_ncmin);
    auto ninuc_raw = difa * 2.0 * PI * Nic * in.n0c / (p.muc + 1.0)
                     * p.g1pmc * in.rslopecmu * in.rslopec2 * dtcld;
    auto ninuc = torch::where(nc_active, torch::minimum(ninuc_raw, in.nc.to(ninuc_raw.dtype())), zero_d);
    return ContactFreezingOutputs{/*pinuc=*/pinuc, /*ninuc=*/ninuc};
}

// ═══════════════════════════════════════════════════════════════════════════
// D3: Bigg cloud freezing
// ═══════════════════════════════════════════════════════════════════════════

BiggCloudParams default_bigg_cloud_params() {
    // f32-stepwise kdm6init constants (fconst.h): cmc=(pi_f*1000)/6,
    // g1p2dcomuc1=Γ_f(3), g1pdcomuc1=Γ_f(2) (integer args ⇒ same as rgmma_scalar,
    // routed through fconst for the single source of truth).
    const double cmc = fconst::get().cmc;
    const double g1p2dcomuc1 = fconst::get().g1p2dcomuc1;
    const double g1pdcomuc1 = fconst::get().g1pdcomuc1;
    return BiggCloudParams{
        cmc, constants::DENR, constants::MUC,
        constants::PFRZ1, constants::PFRZ2,
        g1p2dcomuc1, g1pdcomuc1,
        /*qmin=*/constants::EPS, constants::NCMIN,  // qmin=epsilon=1e-15 (Fortran F:1512 qci>qmin gate; den-clamp inert). 1:1 fix #1
        /*ncmin_tensor=*/c10::nullopt,
    };
}

BiggCloudOutputs bigg_cloud_freezing_torch(
    const BiggCloudInputs& in,
    const BiggCloudParams& p,
    double dtcld
) {
    // STEP-67 SEED (same class as D2): Fortran pfrzdtc/nfrzdtc are DOUBLE scalars
    // (F:755-756); the chain is f64 from `*n0c` on with NO f32 rounding until the
    // qci/nci stores (F:1563-1567). The f32 prefix is cmc*cmc (f1), *pfrz1 (f2) for
    // pfrzdtc and cmc*pfrz1 (k1) for nfrzdtc — gfortran evaluates these REAL(4)
    // stepwise BEFORE the n0c promotion, so compute them in float here (scalar
    // constants; no autograd concern). bigg stays the f32 libm exp (F:1546).
    auto active = torch::logical_and(in.supcol > 0, in.qc > p.qmin);
    auto den_safe = torch::clamp(in.den, /*min=*/p.qmin);
    auto supcolt = torch::clamp(in.supcol, /*min=*/-1e30, /*max=*/70.0);
    auto bigg_factor = ops::libm_exp(p.pfrz2 * supcolt) - 1.0;

    // Scalar prefixes: on the f32 (operational) path gfortran evaluates them
    // REAL(4) stepwise; on the fp64 oracle path the whole chain is f64 (Python
    // oracle parity — it multiplies cmc*cmc*pfrz1 in f64 inside the chain).
    const bool f32_path = (in.qc.scalar_type() == torch::kFloat32);
    const float cmc_f = static_cast<float>(p.cmc);
    const float pfrz1_f = static_cast<float>(p.pfrz1);
    const double f2 = f32_path
        ? static_cast<double>((cmc_f * cmc_f) * pfrz1_f)   // F:1545 (cmc)*cmc*pfrz1, f32 stepwise
        : p.cmc * p.cmc * p.pfrz1;
    const double k1 = f32_path
        ? static_cast<double>(cmc_f * pfrz1_f)              // F:1557 (cmc)*pfrz1, f32
        : p.cmc * p.pfrz1;

    auto pfrzdtc_raw = f2 * in.n0c / den_safe / p.denr
                       / (p.muc + 1.0) * bigg_factor * p.g1p2dcomuc1
                       * in.rslopecmu * in.rslopecd * in.rslopecd * in.rslopec * dtcld;
    // min vs DBLE(qc) — in.qc is the f32-stored POST-D2 cloud water (F:1536 store
    // precedes the F:1545 cap); rate stays f64 to the apply.
    auto zero_d = torch::zeros_like(pfrzdtc_raw);
    auto pfrzdtc = torch::where(active, torch::minimum(pfrzdtc_raw, in.qc.to(pfrzdtc_raw.dtype())), zero_d);

    // Per-cell ncmin (xland-derived, see runtime.cpp). nullopt → scalar fallback.
    auto nc_above_ncmin = p.ncmin_tensor.has_value()
        ? in.nc > p.ncmin_tensor.value()
        : in.nc > p.ncmin;
    auto nc_active = torch::logical_and(active, nc_above_ncmin);
    auto nfrzdtc_raw = k1 * in.n0c / p.denr / (p.muc + 1.0)
                       * bigg_factor * p.g1pdcomuc1 * in.rslopecmu * in.rslopec
                       * in.rslopecd * dtcld;
    auto nfrzdtc = torch::where(nc_active, torch::minimum(nfrzdtc_raw, in.nc.to(nfrzdtc_raw.dtype())), zero_d);
    return BiggCloudOutputs{/*pfrzdtc=*/pfrzdtc, /*nfrzdtc=*/nfrzdtc};
}

// ═══════════════════════════════════════════════════════════════════════════
// D4: Bigg rain freezing
// ═══════════════════════════════════════════════════════════════════════════

BiggRainParams default_bigg_rain_params() {
    // §53c (§40 sibling of the D3 cloud fix): Fortran cmr = pi*denr/6. is REAL(4) f32-stepwise
    // (F:3327, the fconst step-45 class) and g1pdrmr/g1p2drmr are REAL(4) rgmma results
    // (F:3376/F:3393 g1p2drmr = rgmma(drmur1+dmr) = Γ_f32(8) ≈ 5040.002f ≠ exp(lgamma(8.0))).
    // The full-double forms here were 1 ULP off and seeded the 2270-cell freeze-qg class.
    const double cmr = fconst::get().cmr;
    const double g1pdrmr = fconst::get().g1pdrmr;
    const float drmur1_f = 1.0f + static_cast<float>(constants::DMR) + static_cast<float>(constants::MUR);
    const double g1p2drmr = fconst::rgmma_f(drmur1_f + static_cast<float>(constants::DMR));
    return BiggRainParams{
        cmr, constants::DENR,
        constants::PFRZ1, constants::PFRZ2,
        g1pdrmr, g1p2drmr,
        /*qmin=*/constants::EPS, constants::NRMIN,  // qmin only feeds clamp(den,qmin) here (den~1, inert); gate is qr>0. EPS for consistency. 1:1 fix #1
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
    auto bigg_factor = ops::libm_exp(p.pfrz2 * supcolt) - 1.0;

    // §53c f32-stepwise scalar prefixes (mirror of the D3 cloud fix above): gfortran evaluates
    // (cmr)*cmr*pfrz1 (F:1621) and (cmr)/denr*pfrz1 (F:1626) in REAL(4) BEFORE the f64
    // promotion at n0r; the full-double prefix rounds the adjacent f32 at the store (1 ULP,
    // the 2270-cell freeze-qg class). fp64 DA path keeps the all-double chain (oracle parity).
    const bool f32_path_r = (in.qr.scalar_type() == torch::kFloat32);
    const float cmr_f = static_cast<float>(p.cmr);
    const float pfrz1_f = static_cast<float>(p.pfrz1);
    const double f2r = f32_path_r
        ? static_cast<double>((cmr_f * cmr_f) * pfrz1_f)                            // F:1621 f32 stepwise
        : p.cmr * p.cmr * p.pfrz1;
    const double k1r = f32_path_r
        ? static_cast<double>((cmr_f / static_cast<float>(p.denr)) * pfrz1_f)       // F:1626 f32 stepwise
        : p.cmr / p.denr * p.pfrz1;

    auto pfrzdtr_raw = f2r * in.n0r / den_safe / p.denr
                       * bigg_factor * in.rsloped_r * in.rsloped_r * in.rslopemu_r
                       * in.rslope_r * p.g1p2drmr * dtcld;
    auto pfrzdtr = torch::where(active, torch::minimum(pfrzdtr_raw, in.qr), zero);

    auto nr_active = torch::logical_and(active, in.nr > p.nrmin);
    auto nfrzdtr_raw = k1r * in.n0r * bigg_factor
                       * p.g1pdrmr * in.rslope_r * in.rsloped_r * in.rslopemu_r * dtcld;
    auto nfrzdtr = torch::where(nr_active, torch::minimum(nfrzdtr_raw, in.nr), zero);

    auto delta_brs = pfrzdtr / p.denr;
#ifdef KDM6_SUBSTEP_DUMP
    // D4 factor forensics (step-16 seed) — mirror the Fortran dbg captures.
    {
        static long d4_call = 0; ++d4_call;
        static const long d4_target = []{ const char* e = std::getenv("KDM6_DUMP_CALL"); return e ? std::atol(e) : 1L; }();
        const char* env = std::getenv("KDM6_SUBSTEP_DUMP");
        if (env != nullptr && d4_call == d4_target) {
            std::string path = std::string(env) + "/cpp_d4diag.bin";
            std::ofstream f(path, std::ios::binary);
            if (f) {
                auto dump=[&](const torch::Tensor& t){
                    auto c=t.detach().to(torch::kFloat32).contiguous().cpu();
                    const int64_t n=c.numel(); const float* q=c.data_ptr<float>();
                    std::vector<uint32_t> buf(static_cast<size_t>(n));
                    for(int64_t x=0;x<n;++x){uint32_t u;std::memcpy(&u,&q[x],4);buf[static_cast<size_t>(x)]=__builtin_bswap32(u);}
                    f.write(reinterpret_cast<const char*>(buf.data()), n*4);
                };
                int32_t B=static_cast<int32_t>(in.qr.size(0)), K=static_cast<int32_t>(in.qr.size(1));
                uint32_t Bb=__builtin_bswap32(static_cast<uint32_t>(B)), Kb=__builtin_bswap32(static_cast<uint32_t>(K));
                f.write(reinterpret_cast<const char*>(&Bb),4); f.write(reinterpret_cast<const char*>(&Kb),4);
                dump(pfrzdtr); dump(bigg_factor); dump(in.n0r); dump(in.rsloped_r);
                dump(in.rslope_r); dump(in.rslopemu_r); dump(pfrzdtr_raw);
            }
        }
    }
#endif
    return BiggRainOutputs{/*pfrzdtr=*/pfrzdtr, /*nfrzdtr=*/nfrzdtr, /*delta_brs=*/delta_brs};
}

// ═══════════════════════════════════════════════════════════════════════════
// D5: Enhanced melting
// ═══════════════════════════════════════════════════════════════════════════

EnhancedMeltingParams default_enhanced_melting_params(double cliq, double xlf) {
    return EnhancedMeltingParams{/*cliq=*/cliq, /*xlf=*/xlf, /*qcrmin=*/constants::QCRMIN};
}

EnhancedMeltingOutputs enhanced_melting_torch(
    const EnhancedMeltingInputs& in,
    const EnhancedMeltingParams& p,
    double dtcld
) {
    auto zero = torch::zeros_like(in.qs);
    auto warm = in.supcol <= 0;

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

    return EnhancedMeltingOutputs{/*pseml=*/pseml, /*nseml=*/nseml, /*pgeml=*/pgeml, /*ngeml=*/ngeml};
}

}  // namespace melt
}  // namespace kdm6
