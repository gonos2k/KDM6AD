---
title: Native QNC representative moment boundaries — 2026-10-28
type: source
date: 2026-10-28
---
# Native QNC representative moment boundaries

Following [[native-qnc-control-witnesses-2026-10-28]], four full-domain
READY40→60 s host steps recorded control and the rejected α=0.25 candidate
with QC/NC and QI/NI at four native layers. The same PR #465 target donor-scale
variant was used in every run. Trace off/on checkpoints and application ACKs
match within each case; the endpoint hashes match PR #465. Forward microphysics
heating and radiation remained enabled.

At `(153,111,4)`, `(113,70,12)` and `(155,120,15)`, both cases have negative
NC after RK1. NC first differs in the recorded RK2-after state. After RK3,
control has small positive NC and the candidate has negative NC; KDM then
returns zero candidate NC while QC stays positive. At RK3 the saved numerator
inputs other than `ADVECT_TEND` match bitwise. Exact-real arithmetic on the
saved binary32 inputs agrees with the observed sign split, without certifying
the compiled f32 operation order or a named transport process.

At `(1,168,33)`, candidate QI is zero after RK2 and the subnormal word
`00000002` by RK3-before, while control QI is zero and NI remains zero. The
creating operation is bracketed but not identified.

The entire fixed M0 still loses 54 candidate profiles and 378 channel cells;
no full-support cost or accepted second assimilation follows. Raw NC physical
units and domain conservation remain unverified. See the
[report](../../docs/NATIVE_QNC_REPRESENTATIVE_BOUNDARIES_20261028.md) and
[hash-bound packet](../../harness/evidence/native_qnc_representative_boundaries_2026-10-28/README.md).
