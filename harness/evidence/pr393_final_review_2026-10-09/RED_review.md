# RED review — PR393 report, checklist, analysis specification, and run packet

Reviewed the PR393 report, checklist, limited T/Q analysis specification, observation summary, completeness receipt, residual analysis, and target-preparation packet on head `c543b98c`. No host run was launched; the execution-scope question remains open. This pass did not read or hash the forecast, run KDM/RTTOV/native code, or execute an optimizer.

## Claims that are correctly bounded

- The report distinguishes the pre-fix evaluator receipt from the current fail-closed callback. The optimizer probe is identified as one scalar synthetic experiment with installed PyTorch 2.13.0; it does not claim equivalence to the user's 2.10.0 experiment. The current callback failure contract is abort/no successful result, with no retry or restore claim.
- The residual derivation is explicitly conditional: `Dexact` differentiates the uncapped water-saturation formula with captured `L/cp` fixed. It is not described as the full KDM or thermodynamic Jacobian. The finite endpoint ratios are separated from the local first-order prediction, and the report rejects convergence-order, stability, or new-production-defect claims.
- The limited analysis specification calls `th_sigma=0.8 K` potential-temperature uncertainty and `qv_sigma=0.08` a log-space prior for the lower 12 levels. It separates those prior assumptions from observation `sigma=1 K`, labels them uncalibrated, starts controls at zero, and predeclares all non-T/Q state sigmas as zero only for that analysis. The operational builder defaults are stated unchanged.
- The 49/75, 53/75, and 54/75 values are explicitly attributed to the user-supplied reviewer's five-area rubric. Their arithmetic is correct; the documents disclaim interpreting the score as probability, coverage, or remaining time.
- RUN1 remains unlaunched and separate from OPT1. The case uses the original `wrfinput_d01`, `wrfbdy_d01`, and `wrfchainp_d01` inputs in an isolated fresh case with an empty `runs/` directory. The packet says it has no prior forecast, restart, RSL, `wrfout`, or `namelist.output` links and does not treat the prior exit-1 output as a restart or successful experiment. It does not claim a successful native run or T/Q optimization.
- The packet correctly says there is no full private host-tree hash or build gate, the current runtime-loaded libraries have not been observed, and the prior wall time is not a duration estimate. The open QA/time/parallax/footprint questions remain R2 limitations, not new native-run results.

## Actionable provenance clarification

The staged executable and library hashes match the saved 2026-10-07 receipt, whose public source head is `30931e52…`; the reviewed PR393 head is `c543b98c`. The markdown says the source/build/input identities came from archived receipts rather than a fresh build inspection, and the JSON records `public_review_head=c543…` separately. However, `PREPARATION.json` names the old value `build_identity.public_source_head_current_at_preparation`. That label can be read as the source head for the 2026-10-09 preflight, despite its mismatch with `public_review_head` and the packet's historical-only evidence. Before treating this packet as run admission, rename or explain that field as the source head associated with the historical build/receipt, and label the new preflight strictly as rechecking staged artifacts against that prior receipt. State explicitly that it is not a build from PR393 `c543b98c`, not a full host-source verification, and not a runtime loader observation. This is a documentation/provenance clarification; it does not add a full-tree hash or current-head build as a mandatory gate.

No other unsupported completion claim was found. Keep execution-scope pending; this review does not authorize or launch the prepared case.

## Probe correction

The reproducible LBFGS probe now calls `zero_grad(set_to_none=True)` at closure entry, catches only the expected synthetic `ValueError`, records the runner SHA-256, and writes through exclusive creation. The first result and installed LBFGS source are preserved under ignored `graphify-out/pr393-optimizer-red/`; the final receipt was regenerated at a new ignored path before replacing the evidence copy. The observed closure states remain `[0.0, 1.0]`.


## Coordinator resolution of the provenance label

The observation/preparation owner renamed the ambiguous source-head key to
`archived_build_receipt_source_head` and explicitly limited fresh preflight to
matching consumed artifacts against the historical receipt. Review head c543
and archived build head 30931 are separate. A read-only tracked-libtorch diff
is empty, which is not proof of the installed binary's build source. Runtime
loading is still unobserved for the prepared case. This resolves the wording
finding without a full private-tree hash gate or any host launch.
