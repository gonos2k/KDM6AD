# KDM6AD 10-step full-variable bitwise parity ACHIEVED (2026-07-02)

**Result: 10/10 frames STRICT BITWISE PASS** — mp37 (Fortran KDM6) vs mp137 (C++ libtorch KDM6AD),
SS real case `klfs_lc05_fcst.202507190000`, all 254 output variables, frames 1..10
(verify_10step.sh, 2026-07-02 17:57 JST). Supersedes the 2026-06-30 "§48 floor / prognostic-parity"
verdict — the user re-set the goal to full bitwise and the "floor" decomposed into ~15 fixable
1:1 deviations.

## Fix ladder (all measured-verified, in order)
| Tag | Root cause | Fix site |
|-----|-----------|----------|
| rain-sed | falk_nr missing f32 store; vtn f64 | sedimentation.cpp, slope.cpp:77 |
| §53 | brs keep-sweep (6 sites, Fortran ProgB active-cell-only writes) | runtime/coordinator |
| §53b | persistent rhox + Fortran NaN/±Inf collapse (0/0→fmaxnm→0) | coordinator/progb/melt_freeze |
| §53c/h/l | f32-STEPWISE scalar prefixes (bigg; nsacw/niacw; praci/piacr/psaci/pgaci/pracs π·cmX) | melt_freeze/cold.cpp |
| §53d | ProgB 18-array retention bundle threaded runtime→sed→one_step | coordinator.h/cpp, runtime |
| §53e | Fortran `rslopecdmax` NEVER ASSIGNED (save=0) — replicated bug | runtime build_default_aux |
| §53f | rescale-source sequential adds (paacw split positions) | coordinator scale_rates |
| §53k | **UNCONDITIONAL rate-loop vt2r/s/i/g** (F:1952-1956 no q<=0 zeroing; sed vt separate) | slope.cpp/coordinator views (C1+C2) |
| §53n | **wilt ratios RAW q/q** (19 sites; qcrmin floors distorted tails by ORDERS — piacr 1e-25 vs 6e-17) | cold.cpp wilt_arg |
| §53o | qv budget source order per Fortran cold arm F:2741 | coordinator dqv_sum |
| §53p | Picons/avedia Γ via gfortran GAMMLN f32 mirror (Γ_f32(4)=6.0000019≠6.0) | coordinator/runtime |
| §53q | Picons: NO ni>0 gate (ni=0 → clamp-bound avedia → FIRES); final ice limiter per-cell ncmin (F:3228) | coordinator |
| §53r | RHO_ICE diag snap at BOTH clamp bounds (Δ=ULP(100)=2^-17 names the bound) | both trees' export |
| §53s | **Nrevp IN-LOOP transfer** (F:1935-1938 complete-rain-evap `nccn+=nr; nr=0` BEFORE later rate gates/budgets) | coordinator one_step |

## Method (what actually worked)
- Per-step dump-bisection (entry/postmelt/postfreeze/poststateupdate/final) + paired RATE-level
  dumps (fort/cpp_ncrates 25/19 fields, cpp_ncacc, cpp_d5diag) + per-cell factor-ratio isolation
  (C/F ratio == |Δvt2| ratio ⇒ vt2; F=0-vs-C≠0 ⇒ gate; Δ==ULP(bound) ⇒ clamp straddle).
- Fortran-side ephemeral `dbg_*` captures (ifdef KDM6_SUBSTEP_DUMP) to read GATE ARGUMENTS at
  rate time — decisive for §53s (rate-time nrs=0 vs postfreeze dump nr=153).
- Harness traps fixed: run_ss_case cleans `{prefix}_*.bin` (stale-append schema corruption);
  KDM6_SUBSTEP_DUMP must be ABSOLUTE (relative path silently kills only the C++ dumps).

## State / caveats
- Forensic dumps remain in both trees, ALL ifdef KDM6_SUBSTEP_DUMP + env-gated (production-dormant):
  Fortran dbg_vt2s/vt2i/acr_s/acr_g/nsacr(gate-args)/ngacr + 9107/9108 extensions;
  C++ cpp_ncacc/cpp_d5diag/cpp_ncrates qv-tail. Fortran dbg_nsacr/dbg_ngacr currently hold
  GATE ARGS (nrs/qrs2), not rates — re-purpose or remove before further rate forensics.
- AD safety maintained: every op-path raw form (÷, wilt, vt2) is dtype-conditional
  (f32 op = Fortran-faithful; f64 DA = clamped-safe, adjoint finite).
- Transferable traps recorded: fortran-pytorch-port lessons-learned §53-§59.
