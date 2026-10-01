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
