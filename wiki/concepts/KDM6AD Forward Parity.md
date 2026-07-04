---
title: KDM6AD Forward Parity
type: concept
date_modified: 2026-07-02
---
# KDM6AD Forward Parity

## Why This Matters

[[KDM6AD]] can only be trusted as a differentiable port if its operational forward path remains aligned with [[KDM6]]. The project therefore treats mp37 vs mp137 bitwise agreement as a core guardrail before relying on AD functionality.

## Current Status (2026-07-04 — 12h × MPI(np4) ACHIEVED)

- **12-hour × MPI(np4) bitwise parity achieved.** mp37 (tcp) vs mp137 (vader, §53x dylib) over a full
  12-hour (2160-step) SS real-case integration agree **STRICT BITWISE across all 254 output variables at
  all 12 output frames (0–11h)** — the campaign goal. mp137 completed "SUCCESS COMPLETE WRF" at 12:00.
  See `wiki/log.md` 2026-07-04 MILESTONE entry.
- **10-step np1 parity (earlier milestone, superseded scope):** the same STRICT-BITWISE agreement was
  first established at np1 over 10 steps (§53t qv-clamp, §53u/§60 raw coeres sqrt, §53s Nrevp in-loop);
  see [[kdm6ad-10step-bitwise-achieved-2026-07-02]]. The 12h×np4 result above extends this to the maximum
  window and to MPI parallel.
- **Root fixes that unlocked the 12h/MPI gate (2026-07-03/04):** (a) `flow_dep_bdy_qnn` OOB in
  `share/module_bc.F` (transposed `dz8w`, wrong `xland` decl, row-accumulated `z_sum`) — the true root
  cause of np≥2 nondeterminism/NaN, misattributed earlier to an "mp137 MPI structure" defect (see
  `BUGREPORT_module_bc_flow_dep_bdy_qnn.md`); (b) §53w clamp NaN-propagation → `fmax/fmin`; (c) NN-init
  tile-restrict; (d) §53x branch-verbatim `dqv_sum` (cold `pinud` residual contaminating the warm arm),
  the last step-10 seed.
- The current mp137 wrapper mirrors the mp37 host argument surface.
- The C++ port includes f32-stepwise-constant, evaluation-order, raw-division, and mid-rate-loop-state-mutation fixes to reproduce the Fortran reference exactly (fix ladder §53–§53u; transferable traps in `fortran-pytorch-port` lessons-learned §53–§61).
- MPI note (revised 2026-07-04): the real blocker for `-np ≥ 2` was NOT the transport but the
  `flow_dep_bdy_qnn` OOB NaN (fixed — see root fixes above). Once fixed, the **vader (shared-memory) BTL
  completed the full 12-hour np4 run**; the earlier `--mca btl self,tcp` attempt had died at ~3h23m with a
  `readv` transport error that was itself downstream of the NaN abort. np1 and npN produce bit-identical
  output when paired at the same rank count (confirmed at 12h×np4). Transport choice is numerics-neutral.

> [!warning] Superseded framing (pre-2026-07-02)
> Earlier revisions of this page stated that "the documented strict gate is frame index 1 (the `history_interval_s=20` step-1 frame): 254 common, 253 bitwise, 0 diff" and that step-1 was THE gate. That was never an intended gate — it was merely the last fully-bitwise step before the rain-sedimentation port seed activated. As of 2026-07-02, EVERY step is bitwise, so no single-frame gate is privileged. `strict_bitwise_nc.py` still requires an explicit **0-based** frame index (omitting it compares the last common frame); loop `seq 0 $((NF-1))` over the actual `Times` length rather than a hardcoded frame — a 1-based/out-of-range index reports a phantom "frame oob" FAIL (lessons-learned §61).

## Rationale

Forward parity is enforced at multiple layers rather than by a single direct translation:

- `-ffp-contract=off` reduces FMA contraction differences.
- C++ helper functions reproduce Fortran evaluation order and f32 rounding where necessary.
- **Dtype-conditional op-raw / DA-clamped numerics** (see [[KDM6AD Differentiability Audit]]): Fortran evaluates the operational rates with RAW divisions/`sqrt` and NO positivity clamps in many places (Wilt collection-efficiency ratios, coeres `sqrt`, qv mass-balance, rate-loop fall speeds). Bitwise parity required matching those raw forms on the f32 **operational** path while keeping the smooth clamped forms ONLY on the f64 **DA** path (finite adjoint). This dtype-conditional dual-path idiom (`x.scalar_type()==kFloat32 ? raw : clamped`) is now used ~25× and is the load-bearing technique of the port — clamps are NOT uniformly safe to keep.
- The wrapper reuses KDM6's `effectRad_kdm6` and `refl10cm_kdm6` routines for selected diagnostics.
- `diag_rhog` (graupel density / RHO_ICE) is excluded from the packed AD ABI because it is a diagnostic with no meaningful derivative — **not** because it is an irreducible parity floor. Its RHO_ICE `[100,900]` clamp-boundary divergence was a sub-ULP straddle at BOTH bounds and was made bitwise by a symmetric export-side snap (fix §53r); diag_rhog now matches mp37 exactly.

> [!warning] Superseded framing (2026-06-30 decision)
> [[kdm6ad-frame2-rain-sed-bitwise-fix-2026-06-30]] concluded "accept prognostic-field parity; treat the §48 graupel-density clamp floor as an irreducible out-of-scope limit." That decision is SUPERSEDED: the goal was re-set to full bitwise, and the "floor" decomposed into ~20 fixable 1:1 deviation classes. There is no irreducible floor in the operational forward path.

## Evidence

- [[kdm6ad-10step-bitwise-achieved-2026-07-02]] — fix ladder, method, caveats (full 10-step/12h bitwise)
- [[kdm6ad-frame2-rain-sed-bitwise-fix-2026-06-30]] — rain-sed root cause (superseded "floor" framing)
- [[kdm6-vs-kdm6ad-code-comparison-2026-06-25]]
- [[kdm6ad-final-code-location-verification-2026-06-25]]
