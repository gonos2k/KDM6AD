# PR #348–#349 follow-up checklist

Baseline: `f88bb977`. Scope: selector 2 / dry-number 1, fp64 microphysics diagnostic. Deployment and new selectors are deferred.

- [x] N1: Preserve the actual failed input, direction, FD width and thresholds. Separate zero and nonzero NCCN applied volume; evaluate a return-arithmetic candidate with value/JVP/VJP and complete-consumption checks in isolation.
- [x] N2: Run the unchanged external-path command with the isolated candidate on the same input-selected column. Require graph/value equality, JVP/VJP duality, independent directional differences for every field, valid output and stored result; preserve the baseline failure.
- [x] N3: Repeat the same command from a clean worktree; document the candidate, success/failure commands and bounded support. This is diagnostic reproducibility, not deployment or physical approval.

Keep physical number basis, operational approval and observation-cost approval unresolved. Do not remove NCCN from the gate, change `h=1e-4`, relax thresholds or select a different column to pass.

All three items are closed only for the isolated diagnostic experiment described in [the report](REPORT_nccn_return_candidate_2026-10-01.md). The arithmetic patch is not adopted by main. Its half-change arithmetic switch has a measured rounding counterexample; general branch accuracy and production adoption are unresolved. S2/S8 and physical/operational/observation gates remain OPEN.
