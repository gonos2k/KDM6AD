# Green consistency review

Reviewed on 2026-10-13 KST: `REPORT.md`, the additive closeout section,
`wiki/sources/pr420-dom-nine-channel-analysis-2026-10-13.md`, `SUMMARY.json`,
`CHANNELS.csv`, `PROCESS_PLAN.json` / `PROCESS_RESPONSE.json`,
`DIRECTION_PLAN.json` / `DIRECTION_RESULT.json`, both public captures/audits,
and both retained private checkpoints. No H, M, optimizer, native-model, or
observation-acquisition calls were made during this review.

The report, wiki source, closeout note and numeric summary agree on the bounded
experiment: one retained PR412 MP337 background at 2025-07-19 05:55:40 UTC,
one local 20-second window to nominal 05:56 UTC, same priors/controls and
opt-in DOM1 H. The V4 core array hashes are unchanged. The actual retained
RTTOV inputs contain ordered channels 10–16 for DOM7 and 8–16 for DOM9 in all
six callbacks per run; each uses thermal solver 1 with solar disabled. Both
audits are `CROSSCHECKED`, all source DQFs and all model `rad_quality` entries
are zero, and both public receipts remain `RETURNED_DIAGNOSTIC_ONLY`.

I independently checked every value-only summary against the captures and
checkpoint arrays. Recomputed per-channel Huber sums match the initial and
final objective receipts. The 9-channel final observation cost splits into
6.2137447247 on shared channels 10–16 and 5.1350736129 on WV063/WV069; the
7-channel final observation cost is 6.2246563481. This supports the report's
warning against comparing raw whole-vector costs across different N. The
historical Eddington3 fixture and the new DOM7 prepared fixture have the same
24 files except `out/rttov_test.txt`; that file carries the isolated solver
setting change.

For the paired background probes, I checked the retained native state hashes:
the first `grad=False` probe state matches `background_slot_state`, and the
last `grad=True` state matches `final_slot_state` for every saved state field.
The O−B and O−A rows therefore use the saved observation-slot operators
H(M(x_b)) and H(M(x_a)). The separate process response supplies the three
missing H(x) values, checks its own plan bindings and all-zero quality, and
reports R_M/I_M/G_M/G_0 for both DOM7 and DOM9. The report now includes the
seven-channel same-case response alongside the nine-channel response.

The T/qv/RH/QC/NC profile reductions reproduce the capture summaries from
checkpoint data. I confirmed the reported phase-aware and liquid-only q/qs
maxima coincide numerically at their warm maxima (native levels 3 and 4,
about 295 K); their saturation formulas remain distinct at colder levels.
QC and NC are unchanged by the initial T/Q controls, then reach zero in both
returned local M20 slots while remaining in the background slot. Under the
fixed host dry-layer-mass vector, each returned initial-to-slot finite-water
increment is zero; qv gains 0.0041891880 kg/m² as QC loses the same amount.
These are endpoint diagnostics, not a full conservation proof. The native
number basis and independently verified interface-pressure identity remain
open limitations.

The DOM9 directional receipt agrees with the summary: AD 0.5093536523613577,
FD 0.5093536529727771, relative error 1.20038e−9 and zero quality for both
perturbations. It is one first-order direction, not a full Jacobian or higher
derivative result. Both paired optimizers remain nonconverged: two iterations,
four observed function evaluations, unknown termination and final L∞ above
1e−10. Pixel UTC and scientific acceptance remain unassessed. The original
pair did not pre/post-bind the calibration JSON; later direction/process checks
do, and the post-hoc current hash does not establish its original call-time
bytes.

KST is consistently used for newly authored display timestamps while model
valid times remain UTC. The text edits repaired the missing seven-channel
same-case M-response detail and made no claim of forecast skill, strict
convergence, verified pixel matchup, full water conservation, or an Eddington3
repair. Final CSV has LF line endings; `git diff --check` is clean.
