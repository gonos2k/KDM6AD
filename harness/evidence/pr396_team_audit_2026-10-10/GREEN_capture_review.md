# PR396 capture-boundary independent audit

Audit scope: source-level review of the PR395 capture adapter, its actual
production package/optimizer contract, and its private/public persistence
boundary. No native, KDM6 M, RTTOV H, or analysis execution was performed.
Graphify query returned generic graph nodes rather than this complete recovery
path, so conclusions below come from direct source inspection.

## Confirmed production semantics

`run_single_column_analysis` returns the concrete `DualMinimizeResult`,
`b_sigma`, `cvt`, `param_prior`, and adapter metadata. The existing
`run_dual_minimizer` constructs `torch.optim.LBFGS([v_x, v_th], ...)`, calls
its original `step(closure)`, then executes one accepted-control closure. That
closure assigns `v_x.grad` and `v_th.grad`; the minimizer then reconstructs
`x_analysis` and `theta_analysis` from the same controls. The capture wrapper
observes the original optimizer class and delegates to its original bound step.
It saves optimizer state after `step` and before the final audit, then reads
parameter gradients after the adapter returns. It checks returned controls and
gradient norms, and exactly reconstructs the returned analysis and parameters
without another M, H, or closure. Five synthetic storage/optimizer tests pass
under Torch 2.13.0; Ruff also passes.

The observation signature is constructed from fixed H inputs, returned by the
existing evaluator, and checked against the frozen signature throughout
minimization. The final audit closure appends that signature to
`result.j_trace[-1]`. The updated capture helper now validates all trace
signatures and seven-channel counts, binds the accepted signature to the final
mask digest, and records both in private metadata and success/failure receipts.

The initial optimizer objective is now reported from the existing
`result.j_trace[0]` entry, with `Jb_state=0`, `Jtheta=0`, `Jo`, `Jtotal`,
`n_valid`, and the initial/final signature relation checked against the first
`grad=True` callback. The separate first `grad=False` all-sky probe preserves
its raw zero-mask `J_huber`, BT, quality, target, and mask; it is explicitly not
called optimizer initial Jo. The capture helper verifies the initial trace's
Jo against that first H callback without another M/H call. It also requires the intake's
float32 host dry-mass window/background arrays and their source metadata,
preserving the frame-zero `[39]` array into its private NPZ. Raw `PH`/`PHB` are
now labeled as geopotential `m2 s-2`, separately from pressure.

## Findings and repairs

The P2 initial-cost reporting issue is resolved by the trace-derived
zero-control objective above; no extra H/M evaluation is used. The P3
`PH`/`PHB` unit-label issue is resolved. The P3 host eta-layer dry-mass measure
is preserved in float32 with the intake's stated units and source metadata.
The remaining P3 `ncmin` provenance
cross-check gap is recorded below.

1. **Receipt could survive checkpoint cleanup after a post-link temp unlink
   error.** This was reproduced with an injected `Path.unlink` error. The writer
   now treats the successful hard link as the commit point and makes temp-name
   cleanup best-effort, so it returns success with the referenced checkpoint
   intact. The private NPZ digest is computed from the fsynced temp file before
   publication, and post-link hash reads are no longer needed.

2. **Failure status and privacy needed stage-specific handling.** Failure
   receipts now distinguish a runner return with a minimizer result from
   pre-return failure, record `failure_stage`, retain any available final
   signature, and omit raw optimizer-state arrays. The complete optimizer
   vectors remain in the private NPZ.

3. **P3 namelist provenance cross-check remains indirect.** The intake producer
   checks the archived effective namelist's `ncmin_land`/`ncmin_sea` values
   against 10/10 and checks the host wrapper's forwarding source; it stores
   this under `model_data_provenance.kdm6_moment_floor_inputs`. The analysis
   driver and capture helper bind the intake manifest by SHA and separately pin
   M/H values to 10/10, but neither consumer explicitly rechecks that nested
   provenance field against those values. I found no evidence of a value
   mismatch in the produced intake path; this is a provenance-gate completeness
   gap, not a demonstrated production mismatch.

These repairs alter only the capture adapter and its synthetic tests; solver,
native, RTTOV, and original historical artifacts remain untouched. No native,
KDM6 M, or RTTOV execution was used for this repair audit.

## Evidence consulted

- Green evidence: `harness/evidence/pr395_native_tq_case_2026-10-10/REPORT.md`,
  `harness/evidence/pr395_tq_state_capture_2026-10-10/README.md`, and
  `graphify-out/pr395-tq-capture-green/semantic.json`.
- Red evidence: `graphify-out/pr395-red/REVIEW.md`.
- Source: capture helper, `oracle/kdm6/da_single_column.py`,
  `oracle/kdm6/da_dual.py`, `oracle/kdm6/da_fulldomain.py`, and
  `oracle/kdm6/obs/allsky_shard.py`.
- Synthetic validation: 9 storage/control/objective tests passed; Ruff passed. These do
  not establish the pending native run, RTTOV result, pixel-time matchup, or
  scientific acceptance.
