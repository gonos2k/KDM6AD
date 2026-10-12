# GK2A AMI L1B internal research execution baseline

Frozen evidence baseline: main `b07af3fe` (PR417), observed on 2026-10-12.
The follow-up adds explicit nine-channel support and an additive geometry
correction. This is a functional closeout of the internal research execution
path, with the scientific claims below bounded by their individual runs.

## Completed functionality and executed evidence

| Scope | Status and evidence |
|---|---|
| AMI L1B → native T/Q analysis → KDM/RTTOV → accepted-point audit → State/control/full-gradient checkpoint | Executed for the original seven-channel research path; [PR412 case and capture](../harness/evidence/pr412_native_process_case_2026-10-12/REPORT.md). A returned/audited point is distinct from strict convergence. |
| Natural-QC case joint microphysics/observation response | Completed at the recorded point; [PR412 process response](../harness/evidence/pr412_native_process_case_2026-10-12/PROCESS_RESPONSE.json). Attribution is joint M response, not an isolated process or observed cloud truth. |
| Three-time joint observation window and one bounded budget comparison | Completed; [PR414](../harness/evidence/pr414_ami_window_2026-10-12/REPORT.md), [PR415](../harness/evidence/pr415_window_numerical_finish_2026-10-12/REPORT.md). The 61-step held-forcing local window is separate from full-host evolution. |
| Historical native hourly state change and actual 06/07 radiative response | Completed; [PR416](../harness/evidence/pr416_hourly_column_2026-10-12/REPORT.md), [PR417](../harness/evidence/pr417_hourly_rttov_2026-10-12/REPORT.md). Joint snapshot T/Q/hydrometeors/pressure/density/surface response; no observation fit. [Geometry description corrected additively](../harness/evidence/pr418_nine_channels_2026-10-12/GEOMETRY_CORRECTION.md). |
| Optional WV063/WV069 support | Follow-up [PR418 report](../harness/evidence/pr418_nine_channels_2026-10-12/REPORT.md) records implementation, saving-path tests and added-channel execution separately. Seven-channel defaults and archived BT remain preserved. |

This closes the implemented internal workflow and the requested bounded
experiments. Additional scientific questions do not retroactively make these
completed functions incomplete. Conversely, successful execution does not
certify a new build, different-date analysis, strict minimization, atmospheric
truth or operational readiness. No new solver, Hessian/SVD, external satellite,
L2/SST/reanalysis, packaging or platform acceptance is added to this closeout.

## Separate follow-up validation

| Question | Current evidence limit and next admissible action |
|---|---|
| Strict convergence and T/Q stability | PR415 full-gradient L∞ 0.002606100 exceeds the unchanged 1e-10 criterion, termination UNKNOWN. No larger-budget run is silently started. |
| Other-date repeatability | Jul20/21 records declare no selected native producer/input. Preserve their pending receipts; they do not prove current institutional archive absence. Run the first available valid native–AMI pair under the established setup without waiting for a second date. |
| Actual 06/07 observed temporal fit | No paired observations entered PR417. Filename nominal time, raw OBT, planned UTC and actual pixel UTC are distinct; the retained 05:56/06:06/06:16 scenes do not automatically supply a 07 UTC matchup. |
| Truth, process attribution, forecast skill or cycling | Unassessed. These remain separate claims rather than new internal execution gates. |

For an actual observed two-time comparison, freeze the time rule, allowed time
offset, geography/distance, channel/DQF rules and viewing-point convention
before looking at residuals. If actual pixel UTC remains unknown, any comparison
must name its conditional timing assumption. Do not attach a nearby scene as
ground truth just because it is available. When admissible, reuse existing BT
without H or optimization replay and report O−B at each time together with
`(y07-y06)-(B07-B06)` in K. Uncalibrated temporal correlation does not justify
assigning sqrt(2)*sigma to the difference.

Historical four-rank MP137 hourly inputs and the retained MP337 local analysis
have distinct lineage, map, forcing and time interval. A one-hour BT difference
is not divided by three to become a local twenty-minute target. Whole hourly
host differences also include microphysics and cannot be added as “external
tendency” alongside local M without a separate process/coordinate contract.

## Identity and preservation

Claims above cite immutable experiment records, not the newest workspace
library as a substitute for old executed code. The geometry correction changes
descriptions only; the angle-choice BT effect was not calculated. PR418's added
channel records disclose new versus reused channels, quality flags and the
absence of an analysis in that campaign. Private assets, checkpoints and native host inputs
remain private; portable/synthetic CI is separately attributed.

## Additive nine-channel execution — 2026-10-13 KST

[PR420](../harness/evidence/pr420_nine_channel_analysis_2026-10-13/REPORT.md)
completes an actual nine-channel analysis/audit/checkpoint and matched
seven-channel comparison on the retained PR412 natural-QC case using explicitly
opt-in RTTOV DOM1, with unchanged controls/M/prior/budget. All selected model
quality flags are zero. Joint M-response and one independent total-gradient
direction are verified. The original Edd3 default and historical flagged
results remain preserved; the separate 07:00 MP137 trace localizes its
20km⁻¹ extinction cap and is not relabeled as the 05:55:40 MP337 analysis.

The returned DOM9 gradient L∞0.2929647968 still exceeds 1e−10. Pixel UTC,
interface identity, the original pair's unbound calibration-JSON history,
other dates and scientific truth remain stated limits. This adds the requested
optional execution evidence without reopening seven-channel functional closure.
