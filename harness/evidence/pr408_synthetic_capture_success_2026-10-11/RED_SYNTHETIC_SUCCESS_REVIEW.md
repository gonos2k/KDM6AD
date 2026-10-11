# Red review: PR408 synthetic capture success

## Disposition

No blocking defect found in the positive synthetic capture path. The test calls
the existing case builder and V4 intake, prepares a fresh isolated capture
module, and calls `capture.run_capture` without overriding its default
`run_single_column_analysis`. Its only numerical operator substitution is the
existing `oracle/tests/test_da_single_column.py::_install_synthetic_allsky`
fixture at `kdm6.da_fulldomain.sharded_allsky`. The returned analysis, real
KDM6/AD path, L-BFGS step, final accepted-state audit, capture validators and
private checkpoint writer remain executable. The result is correctly labeled
diagnostic-only and synthetic; it is not evidence of real RTTOV, an RTTOV
adjoint, or a new-date native analysis. The synthetic fixture supplies its own
BT and adjoint contract.

## Evidence checked

The packet records a synthetic Jul20 state and observation slot built with the
PR407 V4 case helper, not an actual July20 forecast. The capture receipt binds
the case intake manifest and NPZ. The result/source hashes match their current
files; I independently checked the private checkpoint hash against both the
result and capture receipt. The checkpoint is mode `0600` under a mode `0700`
directory, and the public receipt contains a checkpoint reference rather than
the private arrays. The generated synthetic inputs are ignored by the packet's
`.gitignore`, including its private upper-reference NPZ.

The capture has five logical synthetic-H calls, three window evaluations, one
L-BFGS `step()` return, and one final audit evaluation. The seven-channel
background mask is all ones, all final quality values are zero, observation
sigma is 1 K, bias is 0 K, and the parameter prior is inactive. Its objective
and initial-objective cross-check are internally consistent
(`Jb=0.2282258`, `Jtheta=0`, final `Jo=22.8015729`, initial `Jo=23.2603290`).
The captured control vector is nonzero (`||v_state||₂≈0.676`; returned
temperature differs from background by `||Δth||₂≈0.540`). L-BFGS reports one
returned step, two iterations and three function evaluations. The captured
control-space gradient has shape `[12,1,39]` plus four inactive parameter
controls; its values and norms are read from the original optimizer instance
and checked against the reported gradient summary. These details support that
the real optimizer/audit/capture path ran with a deliberately synthetic H.

The source snapshot before and after analysis is byte-identical. In
`capture_tq_state.py`, the `try/finally` restores `sharded_allsky` to the
object captured at call entry (the synthetic callback for this test) and
restores `torch.optim.LBFGS` to the original factory. Pytest's `monkeypatch`
fixture restores the production H callback at test teardown. The test does not
assert those in-memory object identities directly; source-file hash checks and
the existing `finally` are the available evidence for this run.

The recorded optimizer termination status is `UNKNOWN`, and the final gradient
does **not** meet the configured `tolerance_grad` (`||g||∞ ≈ 1.56e-7` against
`1e-10`). Therefore this review supports a returned numerical diagnostic and
checkpoint, not optimizer convergence or analysis acceptance. The initial
objective audit `CROSSCHECKED` refers to objective arithmetic only.

The one-shot reporting process recorded a `NameError` after successful capture
and checkpoint publication because its separate summary serializer omitted a
`Path` import. The `POSTPROCESSING_NOTE.json` records that no capture or
optimizer rerun occurred and that the summary was reconstructed from the
existing receipt/checkpoint. This report relies on the hash-verifiable
artifacts; the original serializer traceback was not independently replayed.

## CI and limits

The small Oracle test facade imports this local integration test. If the
private P8W source or upper-reference vectors are absent, the test explicitly
skips before creating case outputs or opening a forecast. This local dependency
is intentional. The Graphify query found generic capture/audit nodes but no
specific PR408 path, so the review verified behavior directly against the
capture implementation, integration test, and persisted artifacts.

No actual July20/21 native input, WRF model, RTTOV call, or science-acceptance
assessment was used. The result preserves the user's 79/100 assessment without
recomputation or increase.
