# Fixed-error objective and artifact acceptance

Baseline: PR #383 merge `810c9486`. The two review counterexamples reproduce:

| Synthetic case | Raw O-B / O-A [K] | Initial / final total objective |
| --- | --- | --- |
| Observation correction +2 K | 0 / 2 | 1.5 / 0.1 |
| Channel scales 1 / 10 K | 1 / 1.5 | 1.5 / 0.145 |

The examples are embedded in the supported nine-channel layout with only one
or two active mask entries. They are not new weather/model experiments.

`evaluate_artifact_gates(..., expected_fixed_obs_errors=True)` now explicitly
selects numerical acceptance of the fixed-error normalized KMA objective. It
requires the correct report marker, source label, normalized KMA coordinate,
nine ordered scales, bias shape matching `n_subspace`, bias-definition/signature
and standardized-residual declaration. Raw/corrected/standardized innovations
must be finite and nonnegative; their individual monotonicity is not required.
Total objective descent, pathology/nonfinite checks, final audited components
and gradients, and any applicable conserving requirements remain enforced.

Without an explicit True selector the historical raw O-A <= O-B policy remains;
the report cannot opt itself out of that policy. The LC05 stress runner explicitly
declares False. A corrected unweighted MAE gate would still be inconsistent with
nonuniform scales/prior tradeoffs, so it is not used as a substitute.

Both counterexamples pass the new numerical policy and fail legacy acceptance.
Both archived PR #381 reports also pass numerical fixed-objective evaluation.
That re-evaluates reports; it does not rerun KDM, RTTOV or an actual DA window.
Scientific observation, calibrated B/R/bias and operational approval remain false.

Final focused tests: **68 passed / 2 private-asset skips**. The broader pre-final
row-shape-guard run passed **1687 / 93 skips / 51 warnings**; its counts overlap
and are not summed. Final-revision CI is reported separately. Green/Red review
also required coordinate/channel-count and profile-count checks; wrong or missing
metadata cannot silently enable the fixed-objective policy.

[Machine-readable counterexamples](FIXED_error_artifact_gates_result_2026-10-07.json)
pin the source used for this numerical report evaluation. Original A1/A2 live
execution receipts and the legacy stress criteria remain attributed to their
original sources/configurations.
