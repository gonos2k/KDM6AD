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

The earlier G2/S3 replay required raw REAL4 face fluxes, metrics, RK operands,
and observed advective-tendency and scalar-store bits for ordinary Y→X→Z
face-pair operations. It evaluated numerator prefixes using each source-grouped
face difference. Its build/history hashes were caller-supplied without an
external receipt manifest, so it returned `UNVERIFIED_RECEIPT`; accepted-step
values after microphysics and boundary processing received classification only.
That trace lacked adjacent shared-face words and established no exchange
conservation. QN units remain unresolved, and S3 remains open.

The bounded face-backoff prototype was corrected after the Fortran PD limiter
showed that vertical `fqz(k+1)<0` and `fqz(k)>0` are outgoing. The earlier
four-face synthetic acceptance claim is withdrawn: the fifth, vertical
receiver is negative in the six-cell replay, so the candidate rejects the
change. That old synthetic replay alone cannot judge a conservative correction.

A later mp237 capture on the same retained input, but a **different executable
trajectory** from G2, measures one selected QNCLOUD RK3 donor and its four
interior outgoing-face receivers. All five stores replay and each interior
face's high/low words match on both sides. The donor RK word matches the saved
east-boundary QNCLOUD word, while the donor itself is zero in history. No
direct boundary-copy tap or corrected trajectory was run. These operands
support the next local repair test; whole-host positivity and the physical
number basis remain open. See [[REPORT_S3_native_qn_neighbors_2026-09-28]].

An isolated opt-in follow-up reduces only that donor's positive east xR face
correction after the ordinary PD limiter. In the selected 40-s mp237 run, its
RK store and saved east-boundary QNCLOUD word both change from negative to
positive, while four interior receiver records remain unchanged; the 40-s
QNCLOUD negative count falls from three to two. Logging OFF/ON is raw-bit
identical within each physics mode. This is one fixed external-face experiment,
not a general positivity rule or a closed physical number budget. See
[[REPORT_S3_QN_xr_shadow_2026-09-28]].

The separate S15 native face-neighbor capture concerns QIB rime-ice volume,
not a particle-number field; it does not supply S3 number evidence.

See [[kdm6ad-s3-first-negative-face-plan-2026-09-26]],
[[REPORT_number_face_flux_2026-09-24]],
[[REPORT_negative_number_origin_2026-09-24]], and
[[REPORT_S3_face_budget_backoff_candidate_2026-09-25]].
