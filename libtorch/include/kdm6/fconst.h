#pragma once
// Fortran-faithful runtime constants (kdm6init, module_mp_kdm6.F:3100-3300).
//
// gfortran evaluates the kdm6init constant block in REAL(4) STEPWISE — float32
// rounding after every operation — and rgmma(x) = EXP(GAMMLN(x)) is the float
// expf of the float32-rounded double-precision Lanczos GAMMLN (F:3439-3461).
// The C++ port previously computed these constants in double and demoted at
// tensor-op time, which differs by 1 ULP for non-exact values (e.g. pidnc:
// f32-stepwise 0x4402E653 vs double-demote 0x4402E652) — measured to be the
// step-45 first-divergence seed (DSD-snap nc differs 2 ULP). Every constant
// here is computed f32-stepwise and STORED AS A DOUBLE holding the exact
// float32 value, so the single scalar->f32 demotion at the tensor op
// reproduces gfortran bit-for-bit (same pattern as PCACT_MASS_CONST).
//
// fp64 oracle note: these constants now carry f32-level values on BOTH the
// C++ fp64 path and (mirrored) the Python oracle — parity preserved.
#include <cmath>

namespace kdm6 {
namespace fconst {

// Exact port of Fortran GAMMLN (REAL function, DOUBLE PRECISION internals,
// module_mp_kdm6.F): returns float32(ln Gamma(x)).
inline float gammln_f(float x) {
    const double STP = 2.5066282746310005;
    const double COF[6] = {76.18009172947146, -86.50532032941677,
                           24.01409824083091, -1.231739572450155,
                           .1208650973866179e-2, -.5395239384953e-5};
    double xx = x;
    double y = xx;
    double tmp = xx + 5.5;
    tmp = (xx + 0.5) * std::log(tmp) - tmp;
    double ser = 1.000000000190015;
    for (int j = 0; j < 6; ++j) { y += 1.0; ser += COF[j] / y; }
    return static_cast<float>(tmp + std::log(STP * ser / xx));
}
// Fortran rgmma(x) = EXP(GAMMLN(x)) in REAL(4): expf of the f32 gammln.
inline float rgmma_f(float x) { return std::exp(gammln_f(x)); }

// f32-stepwise constant family (kdm6init order). Values held in double
// (exactly representing the float32 result).
struct F32Consts {
    double pi;        // 4.*atan(1.)                       F:3133
    double cmc;       // pi*denr/6.                        F:3156
    double cmr;       // pi*denr/6.                        F:3157
    double cmi;       // pi*deni/6.                        F:3159
    double g1pmc;     // rgmma(1.+1./(muc+1.))             F:3172 (muc1)
    double g3pmc;     // rgmma(1.+3./(muc+1.))
    double g4pmc;     // rgmma(1.+4./(muc+1.))
    double g6pmc;     // rgmma(1.+6./(muc+1.))
    double g1pmr;     // rgmma(1.+mur)                     F:3181
    double g2pmr;     // rgmma(2.+mur)
    double g4pmr;     // rgmma(4.+mur)
    double g7pmr;     // rgmma(7.+mur)
    double g1pdrmr;   // rgmma(1.+dmr+mur)                 F:3206
    double g1pmi;     // rgmma(1.+mui)                     F:3246
    double g4pmi;     // rgmma(4.+mui)
    double g1pdimi;   // rgmma(1.+dmi+mui)                 F:3258
    double g1p2dcomuc1; // rgmma(1.+2.*dmc/(muc+1.)) = Γ(3) F:3207 (D3 pfrzdtc)
    double g1pdcomuc1;  // rgmma(1.+dmc/(muc+1.))   = Γ(2) F:3208 (D3 nfrzdtc)
    double pidnc;     // cmc*rgmma(1.+dmc/(muc+1.))        F:3205
    double pidnr;     // cmr*g1pdrmr/g1pmr                 F:3235
    double pidni;     // cmi*g1pdimi/g1pmi                 F:3263
    double pidn0s;    // cms*n0s*g1pdsms/g1pms (snow)      F:3326
    double ele2;      // 4.*pi*1.38e-23/(6.*pi*Rcn)        F:1521 (REAL stepwise; loop-invariant)
};

inline const F32Consts& get() {
    static const F32Consts C = [] {
        F32Consts c{};
        // Fortran REAL(4) inputs (decimal literals -> f32)
        const float denr = 1000.0f;
        const float deni = 500.0f;
        const float muc  = 2.0f, mur = 1.0f, mui = 0.0f;
        const float dmc  = 3.0f, dmr = 3.0f, dmi = 3.0f;
        const float pi   = 4.0f * std::atan(1.0f);
        const float cmc  = pi * denr / 6.0f;
        const float cmr  = pi * denr / 6.0f;
        const float cmi  = pi * deni / 6.0f;
        const float g1pmc = rgmma_f(1.0f + 1.0f / (muc + 1.0f));
        const float g3pmc = rgmma_f(1.0f + 3.0f / (muc + 1.0f));
        const float g4pmc = rgmma_f(1.0f + 4.0f / (muc + 1.0f));
        const float g6pmc = rgmma_f(1.0f + 6.0f / (muc + 1.0f));
        const float g1pmr = rgmma_f(1.0f + mur);
        const float g2pmr = rgmma_f(2.0f + mur);
        const float g4pmr = rgmma_f(4.0f + mur);
        const float g7pmr = rgmma_f(7.0f + mur);
        const float g1pdrmr = rgmma_f(1.0f + dmr + mur);
        const float g1pmi = rgmma_f(1.0f + mui);
        const float g4pmi = rgmma_f(4.0f + mui);
        const float g1pdimi = rgmma_f(1.0f + dmi + mui);
        const float g1p2dcomuc1 = rgmma_f(1.0f + 2.0f * dmc / (muc + 1.0f));  // Γ(3) — arg exactly 3.0f
        const float g1pdcomuc1  = rgmma_f(1.0f + dmc / (muc + 1.0f));         // Γ(2) — arg exactly 2.0f
        const float pidnc = cmc * rgmma_f(1.0f + dmc / (muc + 1.0f));
        const float pidnr = cmr * g1pdrmr / g1pmr;
        const float pidni = cmi * g1pdimi / g1pmi;
        // snow pidn0s = cms*n0s*g1pdsms/g1pms (REAL, f32-stepwise; F:3326). dens=100 (snow).
        // double-then-round differs 1 ULP (gfortran 4E15CD86 vs double 4E15CD85) — §44.
        const float dens = 100.0f, n0s = 2.0e6f, mus = 0.0f, dms = 3.0f;
        const float cms = pi * dens / 6.0f;
        const float g1pms = rgmma_f(1.0f + mus);
        const float g1pdsms = rgmma_f(1.0f + dms + mus);
        const float pidn0s = cms * n0s * g1pdsms / g1pms;
        // ele2 = 4.*pi*1.38E-23/(6.*pi*Rcn) — Fortran F:1521 evaluates this REAL(4)
        // stepwise inside the D2 loop (loop-invariant): (4*pi)*kB / ((6*pi)*Rcn).
        const float rcn = 0.1e-6f;
        const float ele2 = (4.0f * pi * 1.38e-23f) / ((6.0f * pi) * rcn);
        c.pi = pi; c.cmc = cmc; c.cmr = cmr; c.cmi = cmi;
        c.g1pmc = g1pmc; c.g3pmc = g3pmc; c.g4pmc = g4pmc; c.g6pmc = g6pmc;
        c.g1pmr = g1pmr; c.g2pmr = g2pmr; c.g4pmr = g4pmr; c.g7pmr = g7pmr;
        c.g1pdrmr = g1pdrmr;
        c.g1pmi = g1pmi; c.g4pmi = g4pmi; c.g1pdimi = g1pdimi;
        c.g1p2dcomuc1 = g1p2dcomuc1; c.g1pdcomuc1 = g1pdcomuc1;
        c.pidnc = pidnc; c.pidnr = pidnr; c.pidni = pidni;
        c.pidn0s = pidn0s;
        c.ele2 = ele2;
        return c;
    }();
    return C;
}

}  // namespace fconst
}  // namespace kdm6
