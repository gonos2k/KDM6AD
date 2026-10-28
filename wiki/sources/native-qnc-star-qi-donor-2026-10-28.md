---
title: Native QNC seven-cell star and QI donor — 2026-10-28
type: source
date: 2026-10-28
---
# Native QNC seven-cell star and QI donor

Following [[native-qnc-saved-face-residual-2026-10-28]], four accepted
READY40→60 s full-host steps recorded the same control/α=0.25 comparison
with QNC shared faces at `(113,70,12)` and a QI boundary donor at
`(1,168,33)`. Forward KDM heating and radiation stayed active. Trace off/on
checkpoint and ACK hashes match within each case and match the prior
PR #469 endpoints. Two additional process attempts failed validation and
are recorded separately rather than counted as completed steps.

All six internal correction faces and all six low-order faces have identical
raw words on the two neighboring cells. Each of seven source-compatible
directional tendencies joins its RK3 QNC input; PD and RK output words are
also reproduced by compatible arithmetic. This is a selected numerical
star, not a physical number-unit or whole-domain conservation certificate.

A frozen one-ULP lower target scale mirrors each changed correction face to
its receiver. Five distinct α face words change; the exact weighted
internal-face change is zero and all six receivers retain positive exact and
binary32 NC. The target remains the counterexample: exact saved-face
residual **−111.694129**, while source-compatible binary32 QNC is positive
**+0.001692894381**. No host variant executed this second target scale
change.

At the QI boundary, both control and α use the same negative raw `ru_m`
input and the X-start copy branch. The donor `(2,168,33)` is zero in control
and subnormal `00000002` in α; the target after `flow_dep_bdy` matches that
donor in each run. This identifies the immediate source of the different
target word without explaining where the α donor acquired its subnormal
value.

The unchanged α endpoint still loses 54 fixed-M0 profiles and 378 channel
cells. Its full-support RTTOV cost and a second accepted analysis remain
unavailable. See the [report](../../docs/NATIVE_QNC_STAR_QI_TRACE_20261028.md)
and [hash-bound packet](../../harness/evidence/native_qnc_star_qi_2026-10-28/README.md).
