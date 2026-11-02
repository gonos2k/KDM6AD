---
title: Native QNICE pre-C3 net intervals and endpoint density — 2026-11-02
type: source
date: 2026-11-02
---
# Native QNICE pre-C3 intervals and endpoint density

The same pinned native C5 packet gives numerical NI at ingress, after
sedimentation, at C3 input and at final DSD. Level 21 changes from
`0.1376752108335495` to `40.72736922974132` before C3; level 23 changes
from `116719.8203125` to `116548.15443662195`. Post-sedimentation step entry
and C3 input are equal in recorded f64 bits. These are net intervals only:
sedimentation, freezes, slope/number rewrites and rounding are not separately
attributed by the two selected cells.

The retained private endpoint's file hash matches the run receipt. Its selected
f32 AL, ALB, RHO, QV and QNICE words are public. At the **saved endpoint**,
source-order `1/(AL+ALB)` matches RHO bits, and RHO matches the earlier call's
DEN bits at both levels. Endpoint QV differs from ingress Q. A post-microphysics
routine can recalculate AL, so this cross-time equality does not certify
AL/ALB at the microphysics call.

The next capture must bind same-call AL/ALB/DEN/QV/QNICE and ordered applied
NI changes to the actual instrumented host build. Physical QNICE units and a
full-column applied number budget remain inconclusive.

See [selected evidence and recipe](../../harness/evidence/native_qnice_prec3_2026-11-02/README.md)
and the [QNICE unit audit](../../docs/NATIVE_QNICE_UNIT_COORDINATE_AUDIT_20261031.md).
