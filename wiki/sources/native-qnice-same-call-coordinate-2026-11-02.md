---
title: Native QNICE same-call coordinate boundary — 2026-11-02
type: source
date: 2026-11-02
---
# Native QNICE same-call coordinate boundary

The authenticated C5 packet ties host NI, DEN and QI to their C ABI f32 words
at native levels 21 and 23. It also ties host Q, NI and DEN to C++ converted
f64 inputs, and the final C++ NI to host f32 output. This establishes the
selected call's **numeric raw-number handoff**. ABI Q and AL/ALB were not
captured at the same call.

Current active host source labels QNICE per kilogram and sets the density
passed to microphysics to `1/(AL+ALB)`. The generic public v2 `dry_number=1`
path instead computes `forcing.rho/(1+qv)` and changes the coordinator's
`dend`. Using the captured DEN as input to that option would numerically apply
an extra division by `(1+QV)` under the current source-level interpretation.
The existing native dry-number research boundary uses DEN directly and
keeps the kernel forcing unchanged; it is a separate opt-in coordinate map.

The two candidate volume-number values from captured NI and DEN are
`0.06763468405718331` versus `0.06754571623550572` at level 21, and
`48725.63292667107` versus `48695.57970495081` at level 23. Both comparisons
are conditional. No dry-number alternative was executed in this packet, and
the current private source hashes are not bound to the historical host build.
Original QNICE payload provenance, same-call AL/ALB and a physical applied
number budget remain necessary before certifying a unit basis.

See the [same-call replay](../../harness/evidence/native_qnice_same_call_2026-11-02/README.md),
[unit audit](../../docs/NATIVE_QNICE_UNIT_COORDINATE_AUDIT_20261031.md), and
[native dry-number boundary](../../docs/NATIVE_DRY_NUMBER_BOUNDARY.md).
