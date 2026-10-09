# GREEN review — fixed-support trial quality and evidence scope

## Scope inspected

Reviewed current `HEAD` `ce77afa24c02a8e08f0f9e7aec6ee7d75340fc84` plus the uncommitted working-tree changes to `oracle/kdm6/da_fulldomain.py` and `oracle/kdm6/da_dual.py`, and the new `oracle/tests/test_frozen_trial_quality.py`. The reviewed source SHA-256 values were `da_fulldomain.py` `fcd783ec9efed50fe8c3a89e11b4f162447df32c5109e79e06a5f0bf71bfa984`, `da_dual.py` `57ff5a832cc6b011d394f3b462dd344cb93177cb1a81af59edcb04c040fd256e`, and test `a1c7e4967d64781d2a9f69204d77a649d4efe5cb3babfc56817aff140f9d47c8`. These identify this review snapshot; they do not identify a committed fix.

The saved fake-QC receipt is pre-fix evidence. Its full source hashes (`25b94aba00c889a504876e27ed98abf9c38f6174da791b4dc0a04d5c029c1c60` and `1e807e228fb0bb86a769ad93c9d0ff1b29521bc8ebed55f48218dd2cea76521d`) match `git show ce77afa2:...`, the merged PR392 source. Keep the historical evaluator gap and its synthetic cost result attributed to that old source. The current diff adds the guard; the old receipt does not establish behavior of the current source or real RTTOV.

## Green findings

- The full-domain factory has an explicit `require_frozen_quality=False` default. `run_fulldomain_analysis` enables it exactly when `normalized_dry=True`, and the report receives the callback's actual flag. In strict mode, both all-sky and clear background quality arrays are shape/type/finiteness/non-negativity checked. The frozen mask is still constructed once from background, observation quality, and any declared gate.
- The background check passes an all-zero support mask. Therefore an already-flagged nonzero background `rad_quality` is permitted when the numeric field is valid; it stays excluded from S. Trial checks compare quality only where the frozen mask is positive. A previously excluded channel may clear or become flagged without changing S or the objective.
- At every strict full-domain trial, all-sky and chunked clear quality must have the expected full partition shape and valid nonnegative real values. Any nonzero QC value on S raises before the evaluator returns its cost/adjoint record. The objective mask, `n_valid`, and signature remain fixed; the strict policy is included in the signature when enabled.
- The companion dual factory applies the same support rule under `normalized_dry=True`. The existing optimizer boundary checks the mode tag. The default/legacy path stays opt-out, with its prior signature behavior retained.
- The L-BFGS call has no catch/retry path for these quality exceptions. Full-domain pool cleanup runs in `finally`, then the error propagates. State only that the invalid trial fails closed; do not claim automatic backtracking or that the fake receipt shows an optimizer accepted an invalid point.

## Demonstrated coverage

`python3 -m pytest -q oracle/tests/test_frozen_trial_quality.py` passed: **18 passed**. The cases exercise support replacement and malformed trial quality in full-domain all-sky and clear partitions; preflagged background channels staying excluded; trial changes outside S; fixed valid-trial count/signature/cost; the legacy full-domain opt-out; normalized-dry dual trial rejection and allowed excluded-quality changes; malformed dual trial quality; and the legacy dual opt-out.

The graphify queries were run before review but returned unrelated/stale nodes for this new path. Source inspection was authoritative for this review; no graph edge is claimed. No KDM6, RTTOV binary, host, forecast, or new numerical analysis was run. The regression tests use synthetic callback/quality values.

## Remaining low-priority test gap

The tests directly cover trial shape and NaN rejection, but do not parameterize negative, boolean, or complex quality values, nor malformed background quality. The inspected source rejects these cases in strict mode, and I found no accepted-path counterexample. Add such cases only if the maintainer wants broader input-validation regression coverage; this is not a blocker to the frozen-support contract.
