# Internal KDM6AD research checklist — one item at a time

Baseline: PR #379 `f4a13de0`. Installation, licensing, releases and independent
user acceptance are outside this research checklist. Source/input/coefficient
identity remains mandatory. Closed NCCN, BT, first-order cost/VJP and recipe
results remain closed within their demonstrated scope.

| ID | Work type | Item | Completion evidence | Status |
| --- | --- | --- | --- | --- |
| R1 | Data / physical decision | Declare dry mass/number coordinates, thresholds, admissible states and the separate runtime/optical/inventory density roles for one supported regime | Explicit source/units/state-domain record; unapproved assumptions labelled; no tuning to the residual | OPEN — existing conditional conventions available, physical approval remains separate |
| R2 | Data / case selection | Bind one native model case to observation product, pixel/scan time, geometry/surface and footprint | Identified inputs and actual correspondence, with unresolved lineage/time fields explicit | OPEN / COLLECTION STARTED — actual public metadata, nine AMI thermal originals and four sounding records acquired; QA/pixel correspondence/aligned native model remain missing; CHECKLIST_first_observation_collection_2026-10-07.md |
| A1 | Code integration | Carry fixed channel sigma and observation-additive bias through upper analysis, frozen closure, clear/all-sky cost and worker | Same ordered weights/correction in value, VJP, final innovations and saved output; old diagnostic route unchanged | CLOSED — bounded integration; REPORT_fixed_obs_errors_2026-10-07.md |
| A2 | Code / prior decision | Expose existing diagonal CVT control/prior choices without inventing a new B model | Predeclared controlled fields and prior scales reach the minimizer and result metadata; NC-fixed versus NC-enabled comparison can be specified | CLOSED — bounded state-prior integration and actual one-iteration comparison; REPORT_state_prior_controls_2026-10-07.md; scientific B remains uncalibrated |
| A3 | Verification | Verify the A1 objective and its snapshots | Nonuniform sigma/nonzero bias AD–FD, mutation resistance, channel/column ordering, worker-route loss consistency and rejection tests; source/code evidence attributed | CLOSED — 89 focused / 2 skips, selected actual KDM→RTTOV cost FD; REPORT_fixed_obs_errors_2026-10-07.md |
| P1 | Physical experiment | Separate analysis water/heat inventory from each integration leg and net external/boundary terms | Signed increments and declared measures; missing terms remain unknown; applicable moment pairs checked | PARTIAL — prior signed inventories closed; full S17 budget remains OPEN |
| T1 | Numerical experiment | Same-final-time timestep dependence | Predeclared 20/10/5 s study, native profiles, substep/branch scope, vertical species/size/T and export differences | OPEN — distinct from past fixed-20-s long-window checks |
| C1 | Code / spatial study | Preserve different native grids in multiple columns | Each column's own pressure/interfaces/geometry/surface; serial versus worker agreement | OPEN |
| V1 | Data / independent study | Separate setting-design data and unused validation data/initializations | Preselected eligible retained initializations/time sets and fixed policy; no adjacent-pixel independence claim | OPEN — eligible inventory to be checked |
| H1 | Optional prediction study | Supervised one-time host application and paired forecast | Applied/read-back increment once; matched boundary/physics and unused validation | DEFERRED unless prediction is the chosen research objective |

A1 reuses `compute_obs_loss`: `r=(H-(y+b))/sigma`, where bias is added to the
observation. Sigma/bias are fixed snapshots for the inner objective. Connecting
those inputs is not estimating or approving R, B or bias. The original
normalized mode remains 1 K/zero-bias/H-delta=1 regression; a separate explicit
research selection permits caller-supplied error assumptions.

A1/A2/A3 are closed within the executed integration scope. Continue R1/R2;
finalize scientific error/prior choices only
after the observation/physical target is defined.
Mark only executed, verified scope CLOSED and link its source/tests/receipt.
No new solver, Hessian, VAE or generic policy framework is required.

User clarification: no additional internal calibration/error data exists; this
is the first attempt. Nonunit sigma/bias are therefore predeclared assumptions
or engineering tests, not estimates. The [retained-data inventory](INTERNAL_research_case_inventory_2026-10-07.md)
records the unresolved pixel/product/geometry evidence explicitly.

First collection follows independent observation availability: warm liquid
comparison first, ice/mixed-phase collection in parallel. Preserve 1 K/zero bias
as diagnostic regression. Catalogue candidates are not phase-certified cases;
read science QA, actual time/footprint and native model correspondence before R2
can close. Do not acquire or substitute external model/reanalysis profiles.

See the [first acquisition checklist](CHECKLIST_first_observation_collection_2026-10-07.md)
for separately tracked catalogue, raw-file, QA, correspondence and model steps.
