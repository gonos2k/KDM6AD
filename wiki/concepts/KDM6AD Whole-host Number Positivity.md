---
title: KDM6AD Whole-host Number Positivity
type: concept
date_modified: 2026-09-28
---
# KDM6AD Whole-host Number Positivity

## Scope

Whole-host number positivity asks whether prognostic cloud, rain, and ice
number fields remain nonnegative at the model-step accepted state and at saved
history points, across advection, boundary handling, and microphysics. It is a
separate gate from mp37/mp137 forward raw-bit parity: a bitwise reproduced
negative is still negative, and an intermediate Runge–Kutta value is not by
itself an accepted model-step state.

## Evidence and interpretation

The G2 scan locates its earliest sampled QN transition at step 2, RK1, in an
intermediate solver state. Ordinary `advect_scalar` is used at that stage;
the positive-definite flux limiter is scheduled at the final RK stage. Later,
`flow_dep_bdy` can copy a donor value into an edge cell without creating the
negative. Those stages must be traced separately from `STEP_ACCEPTED`, which
follows final RK, microphysics, and boundary processing.

The S3 event parser requires raw REAL4 face fluxes, metrics, RK operands, and
observed advective-tendency and scalar-store bits before replaying the ordinary
Y→X→Z face-pair operations. It evaluates numerator prefixes using each
source-grouped face difference. Its build/history hashes are currently
caller-supplied without an external receipt manifest, so the replay returns
`UNVERIFIED_RECEIPT`; accepted-step values after microphysics and boundary
processing receive classification only. The trace lacks adjacent shared-face
words, so it establishes no exchange conservation. QN units remain unresolved,
and S3 remains open.

The bounded face-backoff prototype was corrected after the Fortran PD limiter
showed that vertical `fqz(k+1)<0` and `fqz(k)>0` are outgoing. The earlier
four-face synthetic acceptance claim is withdrawn: the fifth, vertical
receiver is negative in the six-cell replay, so the candidate rejects the
change. Measured neighboring operands, not a donor-only replay, are needed
before judging a conservative correction.

The separate S15 native face-neighbor capture concerns QIB rime-ice volume,
not a particle-number field; it does not supply S3 number evidence.

See [[kdm6ad-s3-first-negative-face-plan-2026-09-26]],
[[REPORT_number_face_flux_2026-09-24]],
[[REPORT_negative_number_origin_2026-09-24]], and
[[REPORT_S3_face_budget_backoff_candidate_2026-09-25]].
