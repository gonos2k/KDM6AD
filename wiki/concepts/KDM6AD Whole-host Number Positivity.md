---
title: KDM6AD Whole-host Number Positivity
type: concept
date_modified: 2026-09-26
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
observed advective-tendency and scalar-store bits before it reports an
arithmetic match. A face-pair result remains conditional on exact closure of
the mapped advection amount and RK store. Accepted-state classification stays
`UNVERIFIED_ARITHMETIC` until the intervening process and boundary deltas are
recorded. The captured QN unit basis is unresolved, so dry-mass-weighted scalar
amounts are not absolute particle counts. The S3 gate remains open.

See [[kdm6ad-s3-first-negative-face-plan-2026-09-26]],
[[REPORT_number_face_flux_2026-09-24]],
[[REPORT_negative_number_origin_2026-09-24]], and
[[REPORT_S3_face_budget_backoff_candidate_2026-09-25]].
