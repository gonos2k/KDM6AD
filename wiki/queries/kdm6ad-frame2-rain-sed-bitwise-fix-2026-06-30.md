---
title: KDM6AD Frame-2 Rain-Sedimentation Bitwise Fix
type: query
date_modified: 2026-06-30
---
# KDM6AD Frame-2 Rain-Sedimentation Bitwise Fix (2026-06-30)

Investigation into why mp37 ([[KDM6]]) vs mp137 ([[KDM6AD]]) [[KDM6AD Forward Parity]] held only at the
documented SS step-1 frame and diverged from frame 2 onward ("수증기가 응결하기 시작하면 정합성이 어긋남").

## Method

Per-step dump-bisection using the in-tree `KDM6_SUBSTEP_DUMP` harness (Fortran `KDM6_DUMP_STEP`, C++
`KDM6_DUMP_CALL`) + `harness/compare_substep_stage.py`. SS case `ss_real_case_20260619_063620`,
`time_step=20`, so WRF step N = t=20·N s; step 2 = frame 2 (first divergence).

## Key findings

1. **Cross-language heterogeneity is OVERCOME** (verified by me + a Codex review): FMA `-ffp-contract=off`
   both sides, no `-ffast-math`, no real promotion (`RWORDSIZE=4`), f32 end-to-end operational ABI,
   transcendentals routed through system libm (not torch Sleef), constants f32-stepwise. A flagged
   `diffac` f32-vs-DOUBLE "finding" was a FALSE POSITIVE (`module_mp_kdm6.F:746-747` declares `diffac` as
   `real`; `work1` DOUBLE is only storage).

2. **Step 1 is globally bitwise-clean** (both OpenMP tiles, 12/12 fields at final). The frame-2 seed is
   born in **rain/graupel SEDIMENTATION** at step 2 — the post-sed micro entry diverges ONLY in qr/nr/qg.

3. **Two verified 1:1 deviations fixed (rain number sedimentation):**
   - `libtorch/src/sedimentation.cpp` rain-number fall `falk_nr` was missing the `.to(f32)` store cast
     that its mass siblings (`falk_qr/qs/qg`) and the ICE `falk_ni` all had. Fortran `falkn` is `REAL(4)`
     (`module_mp_kdm6.F:686`, stored at `F:1159/1180`). Added cast at the top-cell and interior sites.
   - `libtorch/src/slope.cpp:77` rain number fall speed `vtn` was computed f32; Fortran `vtn` is
     `DOUBLE PRECISION` (`F:3647`, `F:3755` `vtn=DBLE(pvtrn)*rslopeb*denfac`). Added `rslopeb.to(kFloat64)`,
     mirroring the mass `vt` (line 76) and ice `vtn_i` (line 305).
   - **Result (dump-bisection):** nr 16554→0, qr 2178→0 bitwise at step-2 entry. Frame-2 strict_bitwise
     19→16 diverging vars; QNRAIN 12683→63, QRAIN 2916→17; RAINNC / VIS_SFC / VIS_SFC_RAW fully resolved.

4. **Remaining frame-2 divergence = irreducible graupel-density floor** (cell-level proof):
   - RHO_ICE (=`diag_rhog`): 140/208 diverging cells sit exactly on the rhox `[100,900]` clamp bound
     (e.g. mp37=899.9998 vs mp137=900.0000) → §48 clamp-tipping floor (max|Δ|=800 = clamp range).
   - QIB (brs / graupel density): 25787 cells where both ≈0 in no-graupel cells (mp37=0.0 vs
     mp137≈5e-23) → near-zero / denormal-class noise, sub-physical.
   - T/THM/P (43) / QVAPOR / QNICE / QGRAUP are downstream amplification of the above.
   This matches the project's existing exclusion of `diag_rhog` from the AD ABI; decision (2026-06-30):
   **accept prognostic-field parity; treat the graupel-density floor as out-of-scope.**

## Harness bug found & corrected

The C++ dump counter `kdm6_substep_call` increments per (step × OpenMP tile); the Fortran gate counts
WRF steps. Under `numtiles=2` (this run: 141+139=280 j), `KDM6_DUMP_CALL=2` dumped step1/tile2, not
step 2 — fabricating a fake ~3 K "host-coupling divergence". Correct alignment for step-2/tile-1 is
`KDM6_DUMP_CALL=3`. Tile-2 needs a trailing-j comparator (the shipped one assumes leading-tile).

## Artifacts / provenance

- Code edits (working tree, dylib rebuilt + verified): `libtorch/src/sedimentation.cpp`,
  `libtorch/src/slope.cpp`. Rebuild: `cd libtorch/build && cmake --build . -j 4 && cmake --install .`
  (wrf.exe dynamically loads `libtorch/install/lib/libkdm6_c.dylib`; no host relink needed).
- Transferable traps recorded to `fortran-pytorch-port` lessons-learned §50 (statement-fn type),
  §51 (multi-tile dump alignment), §52 (sibling-cast asymmetry in a multi-species sed kernel).

## Graupel-density deep-dive (2026-07-01) — §38/§48 floor confirmed

When the goal was re-scoped to full bitwise (incl. diag_rhog), the graupel residual was op-level bisected:
- qg entry divergence is EXACTLY 1 ULP (qr/qs/qi entry all bitwise-MATCH), traced through
  `vt_g = pvtg·rslopeb·denfac` → `pvtg(avtg(rhox))` → `rhox = qg/brs` at the `[100,900]` clamp (§48).
  Both trees compute rhox with the same f32 ops; the inputs differ sub-ULP from upstream f32
  non-associativity (§38). `rhox=qg/brs` ↔ `brs=qg/rhox` is self-referential, so neither can be made
  bitwise without the other — a genuine §38/§48 floor, NOT a fixable cast/order bug like rain.
- The brs near-zero residue (24151 cells) is the clamp-tipped active-cell brs cascading via the sed
  inflow. The C++ brs-gate scheme is ALREADY extensively measured-tuned by the prior developer
  (coordinator.cpp:1082-1087, 2433-2440 cite "483×1-ULP + 177×catastrophic", "OR-gate regresses ~14k";
  OR-gate upstream + qg-only-zero at the final output). A naive "keep all inactive brs" change
  (runtime.cpp:426) was REVERTED after Codex flagged it incomplete (5 sibling reslope gates
  660/714/864/1088/2443) and worse than the tuned scheme — confirming the issue is a deeply-worked floor.

Verdict: full bitwise INCLUDING the graupel-density (diag_rhog) field is the gfortran↔libtorch f32
non-associativity floor (§38) amplified by the physical density clamp (§48). Achievable scope =
prognostic fields with the rain seed fixed; graupel-density is the documented AD-limit / mathematical floor.

## Links

- [[KDM6AD Forward Parity]]
- [[KDM6AD Differentiability Audit]]
- [[kdm6-vs-kdm6ad-code-comparison-2026-06-25]]
