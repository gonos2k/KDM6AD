---
title: Native target artifact diagnostic (2026-10-08)
type: source
date_modified: 2026-10-08
---

# Native target artifact diagnostic

The [native target report](../../harness/evidence/REPORT_native_target_artifact_2026-10-08.md)
and its [evidence packet](../../harness/evidence/native358_artifact_diag_2026-10-08/)
record the first eight-state comparison at native `(j=86,i=48)` and one retained
AMI pixel `(row=320,col=48)`. This extends the prior
[[sources/first-observation-collection-2026-10-07]] evidence with a real saved
5 km trajectory and actual RTTOV calls.

The run receipt reports `COMPLETE` because the launcher ended, but the experiment
is invalid: WRF printed `SUCCESS COMPLETE WRF` and wrote the requested times while
the runner returned 1, `experiment_valid=false`, `model_completed_flag=false`,
and `prterun` reported improper MPI termination. The forecast hash, duplicate
case-file hash, input hashes, executable and library hashes are recorded. Its
635,785,640 numeric values across 253 numeric variables are finite. That artifact
verification does not make the run a valid experiment or close
[[sources/fixed-error-artifact-gates-2026-10-07]].

The lower-scope comparison evaluates saved profiles through H and the existing
RTTOV K path. RTTOV produced K matrices, but no adjoint/backward, KDM state step,
minimizer, or optimizer consumed them. The output is explicitly
`DIAGNOSTIC_ONLY_FAILED_NATIVE_RUN`, with native validity, experiment validity,
and artifact eligibility all false. Retry 2 disabled solar and set only the
per-frame fixture `simple_cloud` fraction to zero while retaining its CTP; its
eight BT, quality and cost arrays were bitwise identical to retry 1. This is a
result for these inputs, not a general simple-cloud noninterference claim.

The fixed mask retains RTTOV channels 10–16; channels 8/9 carry quality value
32768 with a Delta-Eddington message whose cause remains unknown. Huber costs use
sigma 1 K, zero bias and delta 1. The selected saved column has zero model
hydrometeor amount paths and the executed eight-slot RTTOV hydro and fraction
inputs are zero, while fixture CTP metadata remains. This is not a claim that the
gas atmosphere is clear or that the nearby VIIRS retrieval is wrong. AMI time,
pixel footprint and full retrieval QA remain unresolved, so the repeated-pixel
comparison is conditional and R2 remains OPEN. Related distinctions remain in
[[KDM6AD Forward Parity]], [[KDM6AD Differentiability Audit]], and
[[sources/native-analysis-inventory-2026-10-05]].
