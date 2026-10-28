---
title: Native QNC applied-face guard replay — 2026-10-28
type: source
date: 2026-10-28
---
# Native QNC applied-face guard replay

Following [[native-qnc-star-qi-donor-2026-10-28]], a bounded offline replay
checks the recorded RK3 QNC target `(113,70,12)` and its six neighbors. Each
trial donor scale produces rounded correction-face words used identically on
both sides. The test requires positive exact saved-face residuals and positive
source-compatible binary32 RK results for all seven cells.

The recorded control passes without a scale change. In the α=0.25 record,
one ULP decrease produces a positive binary32 target NC but leaves an exact
saved-face residual of −111.694129. Two ULP decrease is the first tested
scale passing this seven-cell predicate: the target exact residual becomes
+218.030351 and its compatible binary32 NC is +0.001692894381. Six receiver
residuals and binary32 values remain positive. The exact numerical weighted
internal-face change cancels, while the weighted rounded RK-state change is
+33.4951201411. Five receiver NC words remain unchanged; the south receiver
`(113,69,12)` decreases one binary32 ULP (`453A568C → 453A568B`). The weight
is not a certified physical number inventory.

The probe freezes the recorded inputs and does not run a changed host
executable. It cannot certify tile/halo behavior, whole-domain moment
validity, optical response or an accepted analysis. The executed α checkpoint
still loses 54 fixed-M0 profiles and 378 channel cells. See the
[report](../../docs/NATIVE_QNC_APPLIED_FACE_GUARD_20261028.md) and
[packet](../../harness/evidence/native_qnc_applied_face_guard_2026-10-28/README.md).
