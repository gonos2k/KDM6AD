# PR #348–#349 follow-up checklist

Baseline: `f88bb977`. Scope: selector 2 / dry-number 1, fp64 microphysics diagnostic. Deployment and new selectors are deferred.

- [x] N1: Preserve the actual failed input, direction, FD width and thresholds. Separate zero and nonzero NCCN applied volume; evaluate a return-arithmetic candidate with value/JVP/VJP and complete-consumption checks in isolation.
- [x] N2: Run the unchanged external-path command with the isolated candidate on the same input-selected column. Require graph/value equality, JVP/VJP duality, independent directional differences for every field, valid output and stored result; preserve the baseline failure.
- [x] N3: Repeat the same command from a clean worktree; document the candidate, success/failure commands and bounded support. This is diagnostic reproducibility, not deployment or physical approval.

Keep physical number basis, operational approval and observation-cost approval unresolved. Do not remove NCCN from the gate, change `h=1e-4`, relax thresholds or select a different column to pass.

All three items are closed only for the isolated diagnostic experiment described in [the report](REPORT_nccn_return_candidate_2026-10-01.md). The arithmetic patch is not adopted by main. Its half-change arithmetic switch has a measured rounding counterexample; general branch accuracy and production adoption are unresolved. S2/S8 and physical/operational/observation gates remain OPEN.

## PR #350 follow-up (2026-10-02)

Keep N1–N3 as bounded completed evidence. The remaining sequence is:

- [x] N4: Compare direct, zero-change and hybrid returns; reject bare equality bypass if it drops a nonzero tangent. Select a bounded NCCN-only candidate and retain all rounding counterexamples.
- [ ] N5: Execute the selected candidate with the same offline column command and a native-staged forward/JVP/VJP/independent-FD probe. Preserve support, h, direction and thresholds; require native instrumentation noninterference.
- [ ] N6: Fix the supported diagnostic settings and successful/failed examples after N5. Deployment/release publication remains deferred until algorithm completion, as requested by the user.

No generalization to NC/NI/NR, new framework or larger release prerequisites.

N4 result: [three-way comparison](REPORT_nccn_zero_return_comparison_2026-10-02.md)
selects the live-delta, exact-zero-only expression for the next isolated native
probe. It rejects a bare identity bypass and removes the arbitrary 50% switch.
This is not production adoption or proof that the floating map is smooth.
N5 remains OPEN until its own actual native per-field FD and noninterference
records are inspected. N6 remains deferred accordingly.

N5 measured result: [native FD and state-admission report](REPORT_nccn_native_fd_2026-10-02.md).
The same zero-only library passes all 12 native-staged field FD gates and the
OFF/ON noninterference comparison. However the staged input and returned state
fail the existing column command's moment admission; the replay exits 1 as
`NUMERICAL_PASS_UNADMITTED_STATE`. N5 remains OPEN/FAIL for supported-candidate
acceptance, and N6 remains deferred. Counts are not synthesized, the sampled
column/direction/h are not replaced, and no new system gate is added.

## PR #351–#352 review: next N5 steps (2026-10-02)

Keep numerical execution evidence and strict pair-state support separate; neither
is observation/DA science approval. Existing failures and admission rejection
remain preserved. No new system gates or deployment scope are added.

- [x] N5.1: Report numerical input preconditions/executed numerical checks, strict paired-state admission, and unapproved observations separately. Inspect pre-step native inputs across calls; distinguish first-call missing number fields from later states.
- [x] N5.2: Before any AD/FD result, select one active native input by a deterministic whole-owned-domain rule. Keep native levels and all species; no synthetic counts or output-based selection. Require the existing strict full-profile pair rule and an interior active ice level (`qi>1e-14`, `rho_d*ni>ncmin(xland)`). This is an active hydrometeor criterion, not evidence of a named rate.
- [x] N5.3: On the selected input run the unchanged mixed direction and a separate 1% NCCN-only direction, h=1e-4, same 12 field/duality gates. Capture raw NCCN volume delta and actual BASE/PLUS/MINUS zero masks inside the return before division; separate same-return-branch FD from crossing increments. Check OFF/ON forecast noninterference.
- [ ] N5.4: Only after supported-state and numerical evidence pass, judge Python/C++ fp64 NCCN candidate adoption together; preserve f32 and other number fields. Rebuild the chosen main version and repeat the user command from a clean checkout. Release/deployment remains deferred.

The source gates and the selected case's support boundaries must be recorded.
Clear columns and default/fallback branches cannot be counted as an active-case
success. If no eligible input is measured, report that negative result without
changing criteria to manufacture a pass.

N5.1/N5.2: [admission axes and input-only selection](REPORT_native_admission_selection_2026-10-02.md)
measured both complete owned domains at calls 1/2. First call has no eligible
active-ice profile; the second has two. Earliest-call/global maximum input qi
selects (142,50), XLAND=2 before AD/FD. This closes classification and input
selection only; N5.3 branch/direct-NCCN native evidence and N5.4 adoption remain
open. A positive pair is a necessary support check, not full DSD or observation
approval; source-floor activity is not named-process attribution.

N5.3: [supported native two-direction/mask evidence](REPORT_supported_native_nccn_2026-10-03.md)
passes at the frozen input-only selected (142,50), call2. All ten input/output
states satisfy strict pair support. Both 12-field FD/duality checks pass;
BASE/MIX±/NCCN± share the same 39-level return mask. This closes the selected
supported native numerical and return-branch condition, not all physical process
branches, units or observations. N5.4 main adoption and clean user-command run
remain open; N6 and deployment remain deferred.
