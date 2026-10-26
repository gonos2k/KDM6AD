---
title: FP environment and saved Q65 review
type: source
date: 2026-10-26
---

# FP environment and saved Q65 review

This follow-up reviews a conservative FP-environment gate and one saved
block22 Q65 finite-difference coordinate. It uses captured inputs and saved
outputs only: no KDM, host, RTTOV, or optimizer call was made.

## FP-environment roundoff gate

The roundoff-compatibility predicate now requires positive evidence that FE is
round-to-nearest, raw FPCR is available, the FPCR rounding bits are integer zero,
and float32 FZ is disabled. A contradictory redundant nearest flag or a present
but malformed/failed float32 roundtrip probe refuses compatibility. Missing
roundoff evidence cannot validate the half-ULP storage bound.

Saved same-thread snapshots for block40 and the nonsquare B8 case satisfy the
predicate. Block34's capture metadata was not persisted, so its environment
remains unconfirmed; its saved numerical comparisons do not supply an FP
capture. This gate concerns rounding controls; it does not claim preservation
of the caller's original exception-status flags.

## Original requested-direction Q65 coordinate

The offline replay concerns block22 row368, flat index11632, native horizontal
`(i=167, j=50)`. RTTOV layer65 corresponds to native mass level2 in this
column, distinct from its activation witness at level18. This is the original continuous requested direction, not the later
post-binary32 effective C4 direction.

At epsilon `1e-6`, the measured endpoint gap is 74 local binary64 ULPs and the
saved JVP implies 72.3364 ULPs. The coordinate's frozen-tolerance ratio is
215.5597; even the closest representable endpoint gap gives ratio 43.8733, so
no nearby representable endpoint can pass. Epsilons `1e-5` and `1e-4` also fail;
`1e-3` and `1e-2` pass for this coordinate. No tolerance was changed. An
independent 80-digit Decimal chain-rule calculation matches the saved Q tangent
to relative `1.32e-16`; it validates only the Q unit-conversion chain, not the
upstream KDM tangent or a full profile/BT/cost directional gate.

## Open actions

The current checklist keeps the READY/apply→host-entry→FP64 map→REAL4 return and
cleanup boundary trace, paired instrumentation noninterference, an admissible
candidate preserving M0 support, full candidate RTTOV cost, general runner
wiring, cumulative fixed-prior optimization, and a second analysis open. This
saved-coordinate resolution does not change historical common33 results or
C4's effective-direction status.

## Evidence

- [Review checklist](../../docs/NATIVE_ANALYSIS_REVIEW_CHECKLIST_20261026.md)
- [FP-environment and Q65 review evidence](../../harness/evidence/fp_environment_review_2026-10-26/README.md)
- [Saved Q65 resolution](../../harness/evidence/fp_environment_review_2026-10-26/block22_q65_resolution.json)
- [H1 source resolution](../../harness/evidence/native_full_physics_forward_2026-10-25/historical_source_resolution.json)
