# PR392 followup validation scope

Base: merged PR392 `ce77afa24c02a8e08f0f9e7aec6ee7d75340fc84`, source tree identical
to the user-reviewed head `5a7701ed`. The earlier arithmetic/counterexample
receipts retain their original source/input identities. Current guard source
snapshot hashes are in [GREEN_review.md](GREEN_review.md).

## Local checks

- New frozen-support suite: **18 passed**. Synthetic all-sky/clear partitions,
  background-excluded channels staying excluded, trial support loss including
  replacement, malformed/nonfinite quality, both normalized-dry factories,
  and legacy opt-out are covered. The tests do not run binary RTTOV or a native
  host, and do not prove automatic invalid-trial recovery.
- Focused integration regression: **165 passed, 2 skipped** in 11.49 s, using
  `/opt/local/bin/python3 -m pytest -q -rs` on the files below. The two existing
  live full-domain tests skip for the declared absence of LC05 wrfinput / GK2A KO /
  calibration table / live RTTOV dependencies. No full pytest campaign or new
  native build was performed locally. There were 43 existing Torch/tuple-callback
  deprecation warnings, unrelated to this patch.

```text
oracle/tests/test_frozen_trial_quality.py
oracle/tests/test_normalized_dry_fulldomain.py
oracle/tests/test_dual_normalized_policy_guard.py
oracle/tests/test_da_fulldomain.py
oracle/tests/test_review208_fulldomain.py
oracle/tests/test_fixed_obs_error_fulldomain.py
oracle/tests/test_da_dual.py
oracle/tests/test_da_dual_bt_coordinate_fingerprint.py
oracle/tests/test_normalized_dry_parallel.py
oracle/tests/test_normalized_dry_shard_execution.py
oracle/tests/test_clear_candidate_diagnostic_guards.py
```

- CI-style ruff `F821,F822,F823` and `git diff --check` pass on changed source,
  tests and the new arithmetic/reproduction readers.
- Coordinator independently reran the cached branch-coordinate and applied
  partition readers into fresh ignored outputs. Branch roots, coordinate JVP,
  14.940788% conditional cost decrease and all three applied partition sums
  reproduce. These readers open small receipts/NPZ checkpoints, not the forecast,
  and do not invoke the model, RTTOV, derivative engine or optimizer.
- The original synthetic lower-cost fake-QC receipt is preserved without rerun.
  Its source hashes match pre-fix `ce77afa2` files; this is distinct from the new
  regression witness for rejection. Historical runner source remains a snapshot;
  do not use it to overwrite the saved original result.
- [Green](GREEN_review.md) and [Red](RED_review.md) reviewed consistency and
  counterexamples. Early Red concerns were checked against pinned historical
  source and the live helper; the final review records the resolved findings.

## Graph and evidence limits

Code was queried before changes and refreshed with `graphify update .`.
Documentation semantic extraction was completed separately: five agent fragments
and a coordinator fragment supplied 46 nodes / 51 edges across 29 cached source
files, followed by merge, code refresh and clustering. Relationships were checked
against source; the graph is an aid rather than an execution-path witness.
Derived reports remain under ignored `graphify-out/`, with visualization skipped
for a graph above 5,000 nodes. Existing graph coverage of private paths and some
new relationships remains incomplete; source and receipts are authoritative.
Agent token usage is not exposed by this runtime, so no exact semantic-token cost
is claimed. No external model/reanalysis or external LLM API was used.

This validates a fail-closed research callback and bounded interpretations. It
does not approve the historical exit1 forecast, a new target-time native run,
physical reservoir policy, observation correspondence, analysis increments,
forecast accuracy, full budgets or timestep convergence order. The existing
operational defaults and legacy callback policy remain unchanged; strict mode is
selected for normalized-dry research evaluation.

GitHub PR-head CI is a separate post-push check; its results are recorded in the
PR and final handoff rather than asserted in advance here.
