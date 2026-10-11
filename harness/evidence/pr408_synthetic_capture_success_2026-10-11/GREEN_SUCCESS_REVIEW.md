# Green review: synthetic capture success

## Disposition

No consistency blocker remains in the current PR408 packet. It adds one
positive synthetic integration test around the existing PR407 V4 case path
and PR395 capture implementation. It does not add a native-case consumer,
alter V4, or change production KDM6/AD, optimizer, audit, or physics sources.

## Evidence and preservation checks

The local validation record reports one passing temporary-path integration
case. The Oracle facade points to that same case and skips when pinned local
P8W/reference inputs are missing, so the facade is not an independent positive
case. `LOCAL_VALIDATION.json` separately records object-identity checks after
pytest teardown: the production `sharded_allsky` and `torch.optim.LBFGS`
objects are restored. The capture `finally` restores objects to their
call-entry values (the synthetic H within this test); the test does not claim
to check object identity at that intermediate boundary.

The persisted run `PR408_SYNTHETIC_ALLSKY_TQ_20261011_01` is hash-consistent
across [result summary](SYNTHETIC_CAPTURE_RESULT.json), [public receipt](runs/PR408_SYNTHETIC_ALLSKY_TQ_20261011_01/CAPTURE.json), and its private checkpoint. I rechecked the current test-source hash, public-receipt hash, checkpoint hash, production-source snapshot flag, and checkpoint permissions. The NPZ is mode `0600` in a mode `0700` directory. The same-output no-overwrite guard is recorded and the persisted files remain unchanged.

The original synthetic case inputs (`CASE.json`, observation payload, L1B
result, decode receipt and completion receipt) have byte-identical SHA-256
values in the local ignored scratch directory and the restricted canonical
preservation copy. Scratch `inputs/` and `*.npz` are Git-ignored. Original
V4 source-binding paths remain recorded in the capture evidence.

## Limits

The persisted result is `RETURNED_DIAGNOSTIC_ONLY`, with five synthetic H
callbacks, one final audit, seven valid frozen channels, and a
`CROSSCHECKED` initial-objective audit. H uses the existing synthetic
BT/adjoint fixture, so no RTTOV call, actual July20/21 native input, sensor
matchup, or science acceptance is demonstrated. Both actual new-date cases
remain pending.

The final control-gradient infinity norm is approximately `1.5643e-7`, above
the configured `1e-10` threshold, and L-BFGS termination attribution is
`UNKNOWN`; the diagnostic return does not demonstrate strict convergence.
The post-capture serializer `NameError` and reconstruction from the existing
receipt/checkpoint are recorded in `POSTPROCESSING_NOTE.json`; this review
verified the resulting hashes without rerunning capture. The user-owned
assessment remains **79/100** on the same rubric.
