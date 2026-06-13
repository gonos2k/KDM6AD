// KDM6 cloud DSD diagnostics — C++ port of kdm6_torch/kdm6/cloud_dsd.py.
// review6 audit fix: rgmma = Γ(x) (= exp(lgamma(x))).
//
#include "kdm6/cloud_dsd.h"
#include "kdm6/fconst.h"
#include "kdm6/ops.h"

#include <cmath>

namespace kdm6 {
namespace cloud_dsd {

namespace {

constexpr double PI = 3.14159265358979323846;

// Fortran rgmma(x) = exp(GAMMLN(x)) = Γ(x). review6 audit 부호 수정.
inline double rgmma_scalar(double x) {
    // Fortran rgmma(x)=EXP(GAMMLN(x)) in REAL(4): f32 expf of the f32-rounded
    // double Lanczos — differs from exp(lgamma(double)) for NON-INTEGER args
    // (e.g. Γ(4/3), Γ(7/3) in D2/D3 freezing — the step-67 qi/ni seed class).
    return static_cast<double>(fconst::rgmma_f(static_cast<float>(x)));
}

constexpr double DOMAIN_FLOOR = 1.0e-30;

}  // namespace

CloudDsdParams default_cloud_dsd_params(double den0) {
    const double cmc = PI * constants::DENR / 6.0;
    const double pidnc = fconst::get().pidnc;   // f32-stepwise (kdm6init F:3205)
    const double g3pmc = fconst::get().g3pmc;   // f32-stepwise
    const double g6pmc = fconst::get().g6pmc;   // f32-stepwise
    const double g1pmr = fconst::get().g1pmr;   // f32-stepwise
    const double g4pmr = fconst::get().g4pmr;   // f32-stepwise

    // STEP-91 latent class: kdm6init F:3135-3136 builds qc0/qc1 in REAL(4)
    // left-to-right — 4./3.*pi*denr*r0**3*xncr/den0 (MULTIPLY by xncr BEFORE
    // dividing by den0; r0**3 is f32 powf). Double chain + reordered ops can
    // differ; these gate praut (qcr threshold).
    const float pi_qc = static_cast<float>(fconst::get().pi);
    const float r0_f = static_cast<float>(constants::R0);
    const float r03_f = std::pow(r0_f, 3.0f);
    const float qc_pre = (((4.0f / 3.0f) * pi_qc) * static_cast<float>(constants::DENR)) * r03_f;
    const double qc0 = static_cast<double>(
        (qc_pre * static_cast<float>(constants::XNCR0)) / static_cast<float>(den0));
    const double qc1 = static_cast<double>(
        (qc_pre * static_cast<float>(constants::XNCR1)) / static_cast<float>(den0));

    return CloudDsdParams{
        /*pidnc=*/pidnc,
        /*dmc=*/constants::DMC,
        /*muc=*/constants::MUC,
        /*lamdacmax=*/constants::LAMDACMAX,
        /*lamdacmin=*/constants::LAMDACMIN,
        /*g3pmc=*/g3pmc,
        /*g6pmc=*/g6pmc,
        /*g4pmr_over_g1pmr=*/g4pmr / g1pmr,
        /*qc0=*/qc0,
        /*qc1=*/qc1,
    };
}

torch::Tensor diag_species_slope_torch(
    const torch::Tensor& q,
    const torch::Tensor& n,
    const torch::Tensor& den,
    double pidn,
    double dm,
    double lamdamax,
    double lamdamin
) {
    auto qden_safe = torch::clamp(q * den, /*min=*/DOMAIN_FLOOR);
    auto ratio = pidn * n / qden_safe;
    // Fortran lamdac(x,y,z)=exp(log((pidnc*z)/(x*y))*(1./dmc)); route exp/log through libm
    // so the float32 forward bit-matches gfortran's libm.
    // Fortran multiplies by the REAL(4) reciprocal `*(1./dmc)` — NOT a division by
    // dm. log(ratio)~36 amplifies the f32(1/3)-vs-true-1/3 difference through exp
    // into ~13 ULP of lamda (the step-65 rslopec seed). Hold the f32 reciprocal in
    // a double so the scalar demotion reproduces gfortran exactly.
    const double inv_dm = static_cast<double>(1.0f / static_cast<float>(dm));
    auto lamda = ops::libm_exp(ops::libm_log(torch::clamp(ratio, /*min=*/DOMAIN_FLOOR)) * inv_dm);
    return torch::clamp(
        1.0 / lamda,
        /*min=*/1.0 / lamdamax,
        /*max=*/1.0 / lamdamin
    );
}

torch::Tensor diag_cloud_slope_torch(
    const torch::Tensor& qc,
    const torch::Tensor& nc,
    const torch::Tensor& den,
    const CloudDsdParams& p,
    const c10::optional<torch::Tensor>& ncmin_tensor
) {
    // STEP-75 SEED (D-B): the Fortran ACTIVE cloud slope is UNCLAMPED — stmt fn
    // lamdac (F:802) has NO bounds, and F:1454-1466 stores rslopec=1/lamdac as-is;
    // the lamdacmax SNAP (F:1485-1497) rewrites only nci/n0c, never the rslopec*
    // arrays. The previous clamp [1/lamdacmax,1/lamdacmin] (parity tracker #6) was
    // a NaN guard for the mask-multiply port; it diverged D2/D3 (rslopec^4..^9) in
    // the lamdac>lamdacmax snap regime. The guard is preserved structurally: the
    // 1e-30 domain floors bound lamdc >= exp(log(1e-30)/3) ~ 1e-10 > 0 (no Inf),
    // and the explosive qc/nc~0 cells are exactly the INACTIVE set overwritten
    // below with 1/lamdacmax (Fortran F:1454 takes the same branch).
    auto qden = torch::clamp(qc * den, /*min=*/DOMAIN_FLOOR);
    auto ratio = torch::clamp(p.pidnc * nc / qden, /*min=*/DOMAIN_FLOOR);
    const double inv_dmc = static_cast<double>(1.0f / static_cast<float>(p.dmc));
    auto lamdc = ops::libm_exp(ops::libm_log(ratio) * inv_dmc);
    auto rslopec_active = 1.0 / lamdc;                  // F:1461 ACTIVE, UNCLAMPED
    // Fortran F:1603-1608 inactive-cloud branch: (qc<=qmin .or. nc<=ncmin) →
    // rslopec = rslopecmax = 1/lamdacmax. Per-cell ncmin via ncmin_tensor.
    auto inactive = (qc <= constants::EPS) |
        (ncmin_tensor.has_value() ? (nc <= ncmin_tensor.value())
                                  : (nc <= constants::NCMIN));
    return torch::where(inactive,
                        torch::full_like(rslopec_active, 1.0 / p.lamdacmax),
                        rslopec_active);
}

torch::Tensor diag_avedia_cloud_torch(
    const torch::Tensor& rslopec,
    const CloudDsdParams& p
) {
    return rslopec * std::pow(p.g3pmc, 1.0 / 3.0);
}

torch::Tensor diag_avedia_rain_torch(
    const torch::Tensor& rslope_r,
    const CloudDsdParams& p
) {
    // Fortran F:1671 rain avedia uses the truncated literal `.3333333` (NOT 1./3.); cloud
    // avedia F:1670 DOES use 1./3. (see line 83). 1:1 parity fix #4.
    return rslope_r * std::pow(p.g4pmr_over_g1pmr, 0.3333333);
}

torch::Tensor diag_sigma_cloud_torch(
    const torch::Tensor& rslopec,
    const CloudDsdParams& p
) {
    const double raw = p.g6pmc - p.g3pmc * p.g3pmc;
    const double var_factor = std::max(raw, 1.0e-30);
    return rslopec * std::pow(var_factor, 1.0 / 6.0);
}

LenconOutputs diag_lencon_torch(
    const torch::Tensor& qc,
    const torch::Tensor& den,
    const torch::Tensor& avedia_c,
    const torch::Tensor& sigma_c,
    double qcrmin
) {
    // Fortran F:1703-1704 lencon = 2.7e-2*den*qci*(1.e20/16.*avedia*(sigma**3)-0.4):
    // (1e20/16)*avedia rounds, *(sigma**3) rounds, then the -0.4 add rounds —
    // strict source order under -ffp-contract=off (fma_acc is two-rounding).
    // sigma**3: gfortran expands the f32 integer power as (sigma*sigma)*sigma
    // (repeated multiplication, objdump-verified — NOT libm powf, which
    // differs on ~26% of f32 samples; IEEE sweep finding).
    auto coef = 1.0e20 / 16.0 * avedia_c;
    auto sigma3 = sigma_c * sigma_c * sigma_c;
    auto factor = ops::fma_acc(torch::full_like(coef, -0.4), coef, sigma3);
    auto lencon = 2.7e-2 * den * qc * factor;
    auto lenconcr = torch::clamp(1.2 * lencon, /*min=*/qcrmin);
    return LenconOutputs{/*lencon=*/lencon, /*lenconcr=*/lenconcr};
}

torch::Tensor diag_qcr_torch(
    const torch::Tensor& sea_mask,
    const CloudDsdParams& p,
    const torch::Tensor& ref
) {
    // Mirrors operational Fortran module_mp_kdm6.F:842-847 and Python oracle
    // kdm6_torch/kdm6/cloud_dsd.py:diag_qcr_torch:
    //   sea (slmsk==2)  → qc0 (low CCN → low qcr threshold, clean marine air)
    //   land (else)     → qc1 (high CCN → high qcr threshold, dusty air)
    // The Param-field names `qc0/continental`, `qc1/maritime` in CloudDsdParams
    // are legacy labels pinned to scalar values, not the regime mapping; the
    // regime wiring is here.
    auto opts = ref.options();
    auto qc0_t = torch::tensor(p.qc0, opts);
    auto qc1_t = torch::tensor(p.qc1, opts);
    return torch::where(sea_mask, qc0_t, qc1_t);
}

}  // namespace cloud_dsd
}  // namespace kdm6
