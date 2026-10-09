# PR388–389 local resolution checklist

## Dated follow-up: 2026-10-09

The [team completeness audit](REPORT_completeness_pr390_2026-10-09.md) adds
actual minimum-MPI forwarding, a valid initial-time 20-second experimental
mp337 pair and measured RTTOV extinction for saved `case_00` in a separate
diagnostic build. **Q2 is measured for that one profile/build**; the other seven
profiles were not internally instrumented. L1's historical exit-1 cause, L2's
target-time validity and R2 remain OPEN. The original rows below preserve their
PR388–389 review-time scope; they do not supersede this later measurement.

Baseline `ac3a4ec7`; [supplied review identity](REVIEW_REQUEST_PR388_389_2026-10-08.md) on 2026-10-08. Work is local,
in an isolated worktree. Canonical source, operational installs and historical
inputs/results/receipt archives remain unchanged. The user requested a PR at 18:37 JST; this bounded source/metadata change is
submitted for review. New raw private-data publication and long native reruns
remain outside that request.
No criteria, sigma/bias, channel support, candidate selection or physics are relaxed.

| ID | Priority / item | Evidence required | Current state |
| --- | --- | --- | --- |
| L1 | 1: native launcher termination | Observe final output close, actual MPI finalize entry/return, rank exit code/signal; distinguish PMIx startup failures | OPEN — WRF success message precedes shutdown; rank exit/signal is missing. A fresh 60-second bounded observer attempt timed out without an observed WRF-start marker; it does not explain the historical termination |
| L2 | 1: valid target experiment | Cause/conditions resolved, then independently attributed valid target run | OPEN — eight finite saved states are diagnostic artifacts, not normal-exit evidence |
| O1 | 2: selected scan timing | Same selected sample and explicit clock assumption, not full-granule overlap | BOUNDED CHECK COMPLETE — conditional AMI−VIIRS 45.398366–107.029631 s; actual pixel UTC remains OPEN |
| O2 | 2: QA/height/footprint | Version-specific packed QA; height datum; retained view angles and common footprint | OPEN — EQualityFlag17, edge geometry and parallax are not physical ground truth |
| D1 | 2: model/observed cloud mismatch | Distinguish no model condensate from a liquid retrieval category; no NC-only explanation | INTERPRETATION CORRECTED — no state/NC update; causal meteorology remains OPEN |
| D2 | 2: residual attribution | Declare KMA-coordinate BT and non-native gas/surface assumptions | BOUNDED CHECK COMPLETE — IR096 contributes 24.4063% of first Huber cost; does not identify ozone or cloud as the cause |
| Q1 | 3: flag32768 definition | Actual source branch and limit, distinguish layer extinction from total column OD | BOUNDED SOURCE CHECK COMPLETE — bit15/value32768, any total layer extinction >20 km⁻¹; distinct from column OD. No warning-channel readmission |
| Q2 | 3: actual warning layers | Actual ext/ltick arrays or source-attributed run trace, separate measured values from proxies | PARTIAL — saved gas-OD and thickness proxy identify thin lower-layer candidates; actual RTTOV ext/ltick arrays were not retained, so exact trigger layers remain OPEN |
| G1 | 4: endpoint metadata | Three explicit coordinate pairs, immutable historical source and regression | CLOSED — correction sidecar + next-producer patch; five focused tests passed; no native/RTTOV rerun |
| M1 | review follow-up: documentation consistency | BT coordinate declared; target-state inventory distinguishes existence/validity | CLOSED — original report clarified and acquisition checklist superseded where stale |

The [geometry sidecar](NATIVE_geometry_correction_result_2026-10-08.json) binds
original result/observation hashes and preserves all failed-run flags. Its three
new distances come from actual retained coordinates. The original mislabeled
field is retained as historical evidence. [Next-producer patch](NATIVE_geometry_next_producer_2026-10-08.patch)
uses distinct endpoints; it is applied and syntax/routing tested on a new copy,
not applied to the historical execution source. The full next producer was not run.

The [conditional interpretation arithmetic](NATIVE_review_interpretation_result_2026-10-08.json)
uses stored result metadata: all 56 retained residuals are in the Huber linear
region, so MAE and cost are linearly related. IR105 varies only 0.0097643664 K
within the eight saved times; this does not bound actual cloud evolution.

Existing A1/A2/A3 and earlier numerical closures remain closed. R2 remains OPEN.
Physical mass/enthalpy budgets, calibrated B/R/bias and independent forecast skill
are separate unresolved objectives; they are not silently assigned to these flags.

[Warning source audit](NATIVE_warning_source_audit_result_2026-10-08.json) distinguishes
20 km⁻¹ layer extinction from the separate OD30 limit. Gas absorption in thin
lower layers is a candidate mechanism, not a measured extinction reconstruction.

[Bounded exit observer result](NATIVE_exit_observer_probe_result_2026-10-08.json)
records observer load only: no MPI finalize entry/return, WRF-start or completion marker
was observed. The 60-second deadline sent SIGTERM to its own process group; -15
is our interruption, not a new model failure code. No native process remains.
C `_Exit` tracing was tested on a tiny control; Fortran finalize hook forwarding
and numerical noninterference were not demonstrated. Do not retry a long model
case merely because the observer library loaded.

Green/Red reviews found no blocking geometry defect. Pair consistency is not a
native-run allowlist: this metadata helper can correct any explicitly matched
result/observation pair and does not authenticate or approve that experiment.
Tests also verify rejection of mismatched endpoints and preservation of an
existing output. No full next-producer invocation or new cost/adjoint was run.
