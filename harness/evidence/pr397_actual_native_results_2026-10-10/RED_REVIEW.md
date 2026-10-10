# PR396 actual-result Red interpretation

Reviewed read-only after native run 99158 and continuation v4 completed. The
graph query surfaced general water-budget concepts but not the current
PR395/396 producer-to-consumer chain; source and receipts were checked
directly. No model, M, H, RTTOV, or consumer execution was performed for this
review.

## Provenance and scope

The intake records runner exit code 0, `experiment_valid=true`,
`model_completed=true`, actual process grid `1x1`, and all eight exact saved
times from `2025-07-19_05:55:40` through `05:58:00` at 20-second spacing. It
uses native column `(j=86,i=48)` with 39 levels. The capture receipt is
`RETURNED_DIAGNOSTIC_ONLY` on `VALIDATED_NATIVE_INPUT`; the driver and
diagnostic are also present. Intake-manifest, native-NPZ, capture-receipt,
capture-NPZ, diagnostic-source, and diagnostic-NPZ hashes cross-check against
the referenced files. Continuation `FINISH.json` records intake, analysis,
and saved-array diagnostic return codes `[0,0,0]`, with scientific acceptance
false.

The coordinating agent separately reported outer-harness `OS 120`. I preserve
that status as reported; the native run receipt itself reports exit code 0
and valid completion. The evidence does not establish a cause or a causal
relationship between those two statuses, so none is inferred here.

Science acceptance remains explicitly false. The fixed matchup receipt still
has per-pixel time, footprint overlap, and height datum unverified. The model
slot is the nominal `obs_time=1` evaluation at `05:56:00`; that does not prove
the selected AMI pixel's exact UTC or spatial footprint.

## Cost and optimizer interpretation

The actual first zero-control closure has `Jb=0`, `Jtheta=0`, and `Jo0=26.5885759031` over the
same seven-channel frozen support and accepted-audit signature. The raw
zero-mask background quality probe is `0`, by design. The driver receipt
crosschecks the saved probe BT and state against the first closure and
recomputes its BT cost under the frozen mask without another H/M evaluation.
Thus the raw zero-mask probe must not be presented as `Jo0`.

The returned final objective is `Jb=0.2284737909`, `Jtheta=0`,
`Jo=26.1356164027`, `Jtotal=26.3640901936`, with seven valid channels. Total
cost fell by `0.2244857094` (about `0.8443%`) relative to the first closure.
This is a modest objective decrease for this fixed short run; it is not a
convergence or scientific-skill result. Captured L-BFGS state reports
`actual_n_iter=2`, `actual_func_evals=3`, `max_iter=3`, and termination status
and reason `UNKNOWN` / `NOT_EXPOSED_BY_PYTORCH_LBFGS`. The final audit gradient
does not satisfy the captured `tolerance_grad` predicate. Do not label this
run converged or infer which stopping condition ended it.

## Cloud state and control scope

The adapter classifies the local background at the observation slot as clear:
unweighted native-level `qc+qi+qs` sum is `0`, and
`physical_background_cloudy_at_obs_time=false`. The operator still routes
through all-sky H, and all seven channels remain supported with zero recorded
model radiance-quality flags. State controls are only theta and qv, with
captured nonzero sigma counts of 39 theta and 12 qv cells; hydrometeor and
number fields are pinned. The result therefore does not retrieve cloud or
number fields. This clear-slot classification is for the local background
slot, not evidence about a satellite footprint cloud scene.

Seven observed channel values provide at most seven rows to a local observation
Jacobian. The realized state-control support has 51 nonzero-sigma cells, so
the Jacobian rank is bounded above by seven; no singular-value, conditioning,
or identifiability analysis was performed. A cost reduction, prior-regularized
solution, or small gradient cannot be called an independent retrieval. The
captured final gradient is a total objective control gradient, including prior
and CVT/log-parameter chain terms, not an H-only adjoint.

## Saved state, coordinate differences, and mass measure

The saved-array diagnostic reports a fixed-first-frame host eta-mass-weighted
water analysis increment of `+0.2216824149 kg m-2`; model-analysis and
model-background increments are both zero in the stored local arrays. The
slot analysis-minus-background increment is also `+0.2216824149 kg m-2`, and
the decomposition residual is exactly zero in the reported precision. This
residual checks the algebraic identity
`(ma-mb)=(xa-xb)+(ma-xa)-(mb-xb)` under one fixed measure. It is not a closed
water budget, conservation proof, or evidence that boundary/external fluxes
vanish; those fluxes are marked `NOT_MEASURED`.

The measure is the original float32 `[8,39]` host eta dry-mass array, with
frame 0 used for every local increment. I independently checked that the
capture's saved background mass exactly equals native frame 0. Native mass
does change over the eight frames: maximum levelwise relative difference from
frame 0 grows from `1.62e-5` at frame 1 to `6.99e-5` at frame 7. The diagnostic
therefore intentionally uses a fixed reference measure; its algebraic
identity cannot be recast as a moving-mass host budget. The source formula is
`-(C1H*(MU+MUB)+C2H)*DNW/9.81` using the selected reader's REAL(4) operations,
distinct from EOS `rho_m*delz` (`intake_native_tq.py`, `model_data_provenance.host_dry_mass`).

The diagnostic compares native frame 1 against the local background-slot
state. It reports maximum absolute host/local differences of `0.01687 K` in
physical temperature, `0.03830` in dry potential temperature, and
`5.72e-6 kg kg-1` in qv; listed hydrometeor mixing-ratio differences are zero
in the saved column. These are coordinate/state comparisons, not causal
process attribution: the host and local path differ in processes, splitting,
and forcing. The temperature theta/Exner terms close to `4.5e-14 K` residual,
which validates an algebraic identity only; it does not isolate physical
heating processes. The large `nccn` number-field difference is reported as a
state difference only and is not interpreted as a mass or microphysics error.

The profiles and aggregates above are valid only for the hash-bound saved
arrays and fixed candidate. Keep the predeclared time, column, channels, and
sigmas unchanged; do not select an alternate time, candidate, or sigma after
viewing these costs. The result is diagnostic, not science accepted.

### Evidence files

- `harness/evidence/pr395_native_tq_intake_2026-10-10/INTAKE.json`
- `harness/evidence/pr395_tq_state_capture_2026-10-10/RESULT_3d2e97f159.json`
- `harness/evidence/pr395_tq_state_capture_2026-10-10/DRIVER_3d2e97f159.json`
- `graphify-out/pr396-saved-state-diagnostic/private/DIAGNOSTIC.json`
- `graphify-out/pr395-case-continuation-v4/FINISH.json`

## Final sidecar, mass-split, and producer-fix review

The original checkpoint omission is confirmed: the hash-bound actual NPZ has
`final_slot_rad_quality`, but no `final_slot_bt_K` or
`final_slot_frozen_mask`. This does not invalidate the receipt's cost: its
public `logical_h_calls` includes the final returned grad=True callback. The
receipt-derived local sidecar hash matches `ACTUAL_ARRAY_CALCULATIONS.json`;
its BT, `fixed_mask`, and radiance-quality arrays exactly match the final
receipt callback. That callback is call index 5, returned successfully, and
its state hashes match the receipt's `final_slot`; its mask equals
`frozen_mask` and its f64 byte hash equals the final accepted audit mask
digest. The sidecar itself is not a new operator run and does not rewrite the
historical NPZ or public receipt. Independently recomputing the Huber sums from
saved observed BT and sidecar/probe BT gives initial `Jo0=26.5885759031` and
final `Jo=26.1356164027`, matching the capture receipt exactly.

I independently recomputed host water changes from the original native NPZ
and confirmed the recipe values: fixed `w0` mixing-ratio term
`-0.0028296854158 kg m-2`, changing-mass term
`+0.0004696494283 kg m-2`, and actual `w1*q1-w0*q0`
`-0.0023600359875 kg m-2`, with residual `-9.0e-16`. This identity uses two
saved native endpoints and a moving eta mass measure; it remains a decomposition
of stored totals, not a closed flux budget. The local diagnostic's separate
fixed-`w0` increment remains `+0.2216824149 kg m-2` and cannot be substituted
for the host's two-time total change.

The future producer patch maps current event keys (`fixed_mask`/`BT_K`, with
the validated legacy `mask`/`bt` and `rq` aliases) into the final private
checkpoint. The actual-schema round-trip test checks saved keys and values;
the legacy-alias test checks backwards compatibility. Source review found the
mapping consistent with the capture event schema, including the fact that
the final event's fixed and frozen masks are validated equal before the
private payload is written. This is a forward storage fix only; the historical
checkpoint and receipt hashes remain intact. Root reports ten focused tests
and Ruff passed; I did not rerun them.

I also reviewed the current actual-result report and root checklist. They keep
the rank/launcher zero statuses separate from outer-harness OS 120 and leave
the latter's cause unconfirmed; distinguish valid numerical return from
convergence; preserve the clear local background / pinned hydrometeor control
scope; and label both water identities as non-closure. The seven-row Jacobian
rank bound is presented as a dimensional upper bound with no SVD or
identifiability claim. Candidate, nominal time, channel support, and declared
sigmas remain fixed. No new actionable Red finding remains. Native validity
and numerical-return evidence are stronger now, while pixel-time/footprint/
height correspondence, convergence, process attribution, and closed-budget
claims remain unestablished.
