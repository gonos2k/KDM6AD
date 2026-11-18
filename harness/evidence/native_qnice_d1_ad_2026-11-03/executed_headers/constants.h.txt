#pragma once
//
// KDM6 상수 — module_mp_kdm6.F (라인 56-186)에서 직역.
// Python prototype의 constants.py와 정확히 일치해야 함 (oracle 검증).
// yhlee 변경 사항(PEAUT 0.55→0.40 등) 반영.
//
namespace kdm6 {
namespace constants {

// ── timestep / sub-cycling ─────────────────────────────────────
inline constexpr double DTCLDCR = 120.0;

// ── intercept parameters ───────────────────────────────────────
inline constexpr double N0S    = 2.0e6;
inline constexpr double N0SMAX = 1.0e11;
inline constexpr double N0G    = 4.0e6;   // graupel (hail_opt=0 default)

// ── densities ──────────────────────────────────────────────────
inline constexpr double DENR = 1000.0;
inline constexpr double DENS = 100.0;
inline constexpr double DENI = 500.0;
inline constexpr double DENG = 500.0;
inline constexpr double DEN0 = 1.28;

// ── DSD shape parameters (gamma) ───────────────────────────────
inline constexpr double ALPHA = 0.12;
inline constexpr double MUR = 1.0;
inline constexpr double MUS = 0.0;
inline constexpr double MUG = 0.0;
inline constexpr double MUI = 0.0;
inline constexpr double MUC = 2.0;   // cloud water (Cohard-Pinty 2000)
inline constexpr double DMR = 3.0;
inline constexpr double DMI = 3.0;
inline constexpr double DMS = 3.0;
inline constexpr double DMG = 3.0;
inline constexpr double DMC = 3.0;

// ── terminal velocity coefficients ─────────────────────────────
inline constexpr double AVTR = 841.9;
inline constexpr double BVTR = 0.8;
inline constexpr double FVTR = 0.0;
inline constexpr double AVTS = 11.72;
inline constexpr double BVTS = 0.41;
inline constexpr double AVTI = 2710.0;
inline constexpr double BVTI = 1.0;

// ── slope parameter limits ─────────────────────────────────────
inline constexpr double LAMDACMAX = 5.0e5;
inline constexpr double LAMDACMIN = 1.2e4;
inline constexpr double LAMDARMAX = 3.5e4;
inline constexpr double LAMDARMIN = 9.61e2;
inline constexpr double LAMDASMAX = 1.8e5;
inline constexpr double LAMDAGMAX = 1.8e5;
inline constexpr double LAMDAIMAX = 1.82e6;
inline constexpr double LAMDAIMIN = 9.08e3;

// ── activation / autoconversion ────────────────────────────────
inline constexpr double R0    = 0.8e-5;
inline constexpr double PEAUT = 0.40;  // yhlee 변경 (원본 0.55)
inline constexpr double XNCR  = 3.0e8;
inline constexpr double XNCR0 = 5.0e7;
inline constexpr double XNCR1 = 5.0e8;
inline constexpr double XMYU  = 1.718e-5;
inline constexpr double DICON = 11.9;
inline constexpr double DIMAX = 500.0e-6;

// ── Bigg freezing ──────────────────────────────────────────────
inline constexpr double PFRZ1 = 100.0;
inline constexpr double PFRZ2 = 0.66;

// ── thresholds ─────────────────────────────────────────────────
inline constexpr double QCRMIN = 1.0e-9;
inline constexpr double NRMIN  = 1.0e-2;
inline constexpr double NRMAX  = 5.0e7;
inline constexpr double NCMAX  = 5.0e10;
inline constexpr double NCMIN  = 1.0e-2;
// CCN reservoir clamp — Fortran module_mp_kdm6.F:801 (entry) and :3006 (cleanup).
// Mirrored at coordinator.cpp entry-prologue and post-rate cleanup; tested at test_c_abi.cpp.
inline constexpr double NCCN_MIN = 1.0e8;
inline constexpr double NCCN_MAX = 2.0e10;

// ── collection efficiencies ────────────────────────────────────
inline constexpr double EACRC = 1.0;
inline constexpr double EACIC = 1.0;
inline constexpr double EACSC = 1.0;
inline constexpr double EACGC = 1.0;
inline constexpr double EACRI = 1.0;
inline constexpr double EACIR = 1.0;
inline constexpr double EACSR = 1.0;
inline constexpr double EACGR = 1.0;
inline constexpr double EACRS = 1.0;

// ── aggregation / saturation ───────────────────────────────────
inline constexpr double QS0    = 6.0e-4;
inline constexpr double SATMAX = 1.0048;
inline constexpr double ACTK   = 0.6;
inline constexpr double ACTR   = 1.5;

// ── Long collection kernel coefficients ───────────────────────
inline constexpr double NCRK1  = 3.03e3;
inline constexpr double NCRK2  = 2.59e15;
inline constexpr double ECCBRK = 1.0;

// ── characteristic diameters ──────────────────────────────────
inline constexpr double DI50   = 0.5e-4;
inline constexpr double DI100  = 1.0e-4;
inline constexpr double DI125  = 1.25e-4;
inline constexpr double DI150  = 1.5e-4;
inline constexpr double DI600  = 6.0e-4;
inline constexpr double DI2000 = 2.0e-3;

// ── melt heat balance factor ──────────────────────────────────
inline constexpr double F2S = 0.44;

// ── numerical floors (ops 공유) ───────────────────────────────
inline constexpr double EPS        = 1.0e-15;  // Fortran qmin과 정합
inline constexpr double SMOOTH_EPS = 1.0e-4;   // limiter sign-transition

}  // namespace constants
}  // namespace kdm6
