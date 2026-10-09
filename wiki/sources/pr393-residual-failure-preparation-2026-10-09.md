---
title: PR393 saturation residual, optimizer failure and next-case preparation
type: source
date_modified: 2026-10-09
---
# PR393 residual, failure and next-case preparation

The [checklist](../../harness/evidence/CHECKLIST_pr393_review_resolution_2026-10-09.md)
and [report](../../harness/evidence/REPORT_pr393_review_resolution_2026-10-09.md)
retain strict fixed-support closure and reuse public stage data. The uncapped
water saturation derivative gives Dexact>Dimpl at four recorded points. Later
residuals reverse sign with about 2.1% damping, consistent with the local frozen
L/cp prediction. The finite first update differs more; this is no global
stability or timestep-order result. Legacy/normalized physics is unchanged.

A scalar installed-PyTorch 2.13.0 probe leaves the rejected x=1 after a closure
exception. Existing project minimizers publish results only after step and final
audit, so current fail-closed policy remains appropriate. Retry/accepted-point
restoration is a separate future contract, not an implemented solver feature.

The nominal original-IC target case is staged separately with fixed mp337,
variant2/dry-number/value-only, 1 rank/thread, dt20 and eight target outputs.
Preparation is not a successful run. Archived build head, current review head
and fresh consumed-artifact matching remain distinct. Observation QA, AMI epoch
and pixel time, cloud-height datum and common footprint still limit R2; they do
not permanently prohibit a new nominal model diagnostic.

The first actual T/Q analysis specification uses Jb+Jo, declared prior/control
support, fixed 7-channel quality, final accepted-point audit and explicit failure.
No actual native/analysis experiment is inferred from the new scalar probes.
The user-supplied 53/75 main and 54/75 with PR393 are management judgments,
not probabilities/coverage/time, and this followup adds no score.

Related: [[pr392-branch-coordinate-support-2026-10-09]],
[[pr391-saturation-control-resolution-2026-10-09]].
