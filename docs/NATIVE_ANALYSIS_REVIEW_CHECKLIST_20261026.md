# Native analysis review resolution — 2026-10-26

Base: main `1c077608e8728bad3a53a868483dbd5916eec214` (PRs 451–453).
This is a follow-up checklist, not a revision of the immutable H1 execution
record or an acceptance of any full-host analysis candidate.

## Completed foundations retained

- [x] Prepare actual binary32 T/Q changes and bind the complete READY checkpoint.
- [x] Apply each candidate once, then independently advance the same READY40
  origin to 60 s with configured full physics enabled. `NO_MP_HEATING=0`,
  `USE_THETA_M=1`, `USE_Q_DIABATIC=0` do not disable the forward's microphysical
  water updates or latent heating. The latter switch omits only the separate
  RK water-tendency correction.
- [x] Evaluate the full control checkpoint directly through the native
  profile-to-RTTOV path without repeating KDM/cleanup/finish.
- [x] Preserve all three rejected candidates, their undefined observation
  costs, and the unchanged baseline M0. Confirmed pre-RTTOV losses are
  53/63/55 profiles for alpha 1/0.5/0.25 respectively.

## Review actions

| ID | State | Action and completion criterion |
| --- | --- | --- |
| R1 | Fixed; local verification passed | FP environment compatibility requires measured FE nearest, available raw FPCR, rounding bits zero and FZ disabled. Missing or contradictory evidence cannot certify the half-ULP bound. Numeric comparisons and old receipts remain separate. |
| R2 | Saved-data diagnosis complete | Requested-direction block22 Q65 cannot meet its frozen coordinate tolerance at epsilon 1e-6: even the closest binary64 endpoint gap gives ratio 43.87. At 1e-3 and 1e-2 this coordinate passes. The independent 80-digit Q unit-conversion chain derivative agrees with the saved profile tangent to relative 1.32e-16. Historical common33 failures and effective-direction C4 remain unchanged. |
| R3 | Source tracing complete; measurement pending | The [boundary plan](NATIVE_QC_NC_TRACE_PLAN_20261026.md) locates READY/apply, actual host KDM entry, FP64 output, REAL4 return/cleanup and final checkpoint boundaries. Existing trace files cover another column and cannot answer these witnesses. Reuse actual host tiles/order; observation B512 chunks are not host integration partitions. |
| R4 | Pending R3 execution | Record the same QC/NC coordinates at those boundaries for control and relevant candidates. Demonstrate instrumentation noninterference within the executed variant before attributing a cause or changing physics. |
| R5 | Pending a demonstrated cause | Obtain a candidate preserving all of M0 with no arbitrary NC/Q floor and no mask shrink. Candidate costs remain undefined until admissible. |
| R6 | Pending R5 | Evaluate that full checkpoint directly with RTTOV and compare fixed-support cost and actual native T/Q/cloud changes. |
| R7 | Pending | Connect representable candidate preparation/evaluation to the general trial runner. Use candidate/applied delta/z_eff from one preparation result, including its fixed-background prior. The existing runner still uses continuous requested z. |
| R8 | Pending R7 and admissible candidates | Implement fixed-prior cumulative inner iterations with relinearization and the nonzero prior gradient away from z=0. A conditional microphysics gradient is a proposal, not a full-host Jacobian. |
| R9 | Pending an accepted analysis and timing policy | Actually compute a second analysis from the carried state. No accepted full-host analysis, convergence or cycling result exists yet. |

Witnesses use native one-based `(i,j,k)`, mass levels bottom first:
`(155,25,19)`, `(221,63,6)`, `(91,94,4)`. Initial QC-positive/NC-zero pairs
already exist in some READY40 columns. Smaller alpha does not monotonically
improve profile admission; endpoint values alone do not identify the responsible
process or storage boundary. Raw NC units remain uncertified.

## Evidence and scope

- [Current full-physics execution record](NATIVE_ANALYSIS_PROGRESS_20261025.md)
- [Review evidence and reproducible calculations](../harness/evidence/fp_environment_review_2026-10-26/README.md)
- [Historical H1 source resolution](../harness/evidence/native_full_physics_forward_2026-10-25/historical_source_resolution.json)

The repeated public baseline arithmetic gives 65,988 columns, 377,342 supported
channel cells and `J=11.007963317242059`. Local verification: 151 tests across
analysis control, objective, live stepper, checkpoint observation, precision
boundary and runner. This is not a new native/RTTOV run. The full-host trial
costs and the effective-direction C4 common33 certificate remain unavailable.
