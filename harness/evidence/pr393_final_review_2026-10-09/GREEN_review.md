# Green consistency and coverage review: PR393

Review basis: merged main `ce77afa24c02a8e08f0f9e7aec6ee7d75340fc84` and PR393
head `c543b98cc42f0e906b63568df209d974300d771d`. The checkout is at that head;
`git status` shows the review packet as untracked and no tracked production diff.
This review audits the current evidence packet and does not rerun the closed
179/2 local suite or execute KDM6, RTTOV, the host, or a native case.

## Checklist audit

| Area | Green finding |
| --- | --- |
| Fixed-support policy and failure contract | The report and checklist keep the guard opt-in for normalized-dry evaluation. They distinguish an exception that prevents result publication from an accepted-step restore or automatic backtrack. The independent PyTorch probe is clearly limited to an installed 2.13.0 scalar LBFGS example; it is not represented as a project optimizer or KDM6 run. |
| Local saturation residual | The residual reader's script hash and both public-input hashes match the final `RESULT.json`. Recomputed call-two and call-three values match the rounded published values. The separate scalar `compute_qs_water` AD receipt has matching current `thermo.py` and `fconst.py` hashes; its four-point maximum relative difference is `2.1367e-15`. Both records limit the conclusion to the uncapped scalar water saturation expression with captured `L/cp` held fixed. |
| First-order versus finite change | The report preserves the implemented left-associated `Dimpl`, labels `Dexact` as a local derivative comparison, and separates the linear residual prediction from endpoint ratios. It calls out the larger first-call finite-update discrepancy and call-four near-saturation rounding. It makes no whole-KDM stability, convergence-order, or new arithmetic-defect claim. |
| N1 activation inventory | The residual receipt distinguishes captured third-call NC/NCCN volume inputs from reconstructed `F`, `b`, and `a`. The arithmetic `F=0.022022771 < NC/(NC+NCCN)=0.668149012` gives `b=0`, consistent with stored reconstructed `b=0`, `ncact=0`, and `a=0` despite the true activation gate. The report leaves physical reservoir policy open. |
| Budget and physics | The water/latent totals are explicitly limited to captured satadj stages; number-coordinate changes, NCCN floor departure, full host budgets, external fluxes, and S17 remain separate or open. No process equation or denominator was changed. |
| Limited T/Q specification | The prior values match `make_default_cvt`: additive potential-temperature sigma `0.8 K`; lower-12-level multiplicative qv log-space sigma `0.08`. The spec keeps these distinct from observation sigma `1 K`, declares zero overrides for non-T/Q controls in that proposed analysis, uses initial control zero, fixed background support, and the full `Jb+Jo`. It warns that these priors are not calibrated and that the former `−0.8 K` point is not a new background. |
| Observation scope | The observation packet maintains D1/D2/D3/D4/R1/R2/S17 as open where evidence is missing. It distinguishes metadata and nominal-coordinate context from validated pixel time, QA, datum, footprint overlap, and accepted R2 correspondence. It does not read/hash the large forecast or acquire replacement data. |
| Native target preparation | The preparation receipt says `PREPARED_NOT_LAUNCHED`, records exact staged files and a fresh isolated case, and leaves runtime-loaded paths, actual `Times`, successful completion, and a separate launch decision outstanding. The report calls it a future model experiment, not an analysis result. The historical exit-1 run remains unresolved and is not used as a restart. |
| Completeness score | Recomputed area totals are 49/75, 53/75, and 54/75; rounded percentages are 65.3%, 70.7%, and 72.0%. The source is named as the user's ordinal review, the follow-up adds zero points, and the score is not treated as a correctness probability, coverage measure, or time estimate. |
| Test/CI provenance | The 179 passed/2 skipped result is retained from the PR392 follow-up validation record; this audit did not rerun it or present it as new evidence. A read-only GitHub check query returned five successful PR393 checks for exact head `c543b98cc42f0e906b63568df209d974300d771d`: macOS arm64 build/symbol/smoke, Ubuntu build/ctest, G33 harness, changed-path detection, and oracle pytest. Those are existing head-scoped CI evidence, not a test run performed by this audit. |

The key receipt checks passed: residual reader/input hashes, scalar thermo/fconst
source hashes, optimizer probe script hash, score arithmetic, and the prepared-
not-launched status. PR393 was still open at the reviewed head. The user's long
native-run scope decision remains pending; no launch is implied by the prepared
case or by this review.

The initial graph query returned generic claim/source nodes and did not expose
these receipt-to-report paths. The companion semantic fragment is scoped to
this final review packet; it is not a complete code or research graph and does
not replace source/receipt checks.

## Remaining boundaries

The bounded derivative check is not a full KDM6 Jacobian, model-level
conservation proof, optimizer acceptance, or physical adoption. The observation
screen is not independent matchup validation. The prepared case is not runtime
verification or a completed forecast. The T/Q specification is not an executed
analysis. D1–D4, R1/R2, and S17 do not close from these receipts.
