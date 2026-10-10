# PR398 bounded convergence follow-up

This is a separate, predeclared eight-iteration optimizer trajectory experiment
using the validated PR395 native input, fixed candidate, seven-channel
all-sky operator, original background state, zero controls, forcing, prior,
observation uncertainty, bias, and support gates. The experiment tests whether
the fixed short run's objective and total control gradient continue to change
when the optimizer iteration ceiling rises from 3 to 8. It is not cloud
seeking, a second native run, or a scientific-matchup acceptance test.

`PREDECLARATION.json` freezes the experiment before execution. Running
`run_convergence.py` without flags builds an input/source preflight only. The
single actual analysis path requires `--execute-after-review`; it has an
exclusive PR398 lock and separate result/checkpoint locations. It never deletes
or reuses the PR395 lock, result, checkpoint, or run output.

The capture gate preserves PR395's default `max_iter=3`. It admits 8 only with
the exact PR398 experiment ID and the declared PyTorch default `max_eval`
policy. The runner does not pass `max_eval`; the receipt records the actual
optimizer group's value, expected to be 10 with the pinned PyTorch version.
No optimizer, solver, or physics source is changed.

After preparation, review `graphify-out/pr398-convergence-8iter-20261010/run-PR398_CONVERGENCE_8ITER_20261010-sourcechecked7/preflight.json`
and source hashes before coordinating the one actual H/M analysis call with the
root. A successful result remains `RETURNED_DIAGNOSTIC_ONLY`; convergence,
cloud retrieval, pixel-time matchup, and science acceptance are separate.

The stored manifest label `pytorch_lbfgs_default_ceil_1.25_max_iter` is
historical protocol metadata. With pinned PyTorch 2.13, the actual default is
computed as `int(max_iter*1.25)`; it is 10 for `max_iter=8`. The one authorized
run and its immutable receipts are documented in `ACTUAL_RUN_REPORT.md`.
`POSTRUN_INTERPRETATION.json` explains the source-verified path-sensitive raw
signature difference without changing the original failed assertion. The
post-run endpoint summaries report saved-array QC/NC/hydrometeor counts and
qv/qs ratios, not physical-attribution evidence.
