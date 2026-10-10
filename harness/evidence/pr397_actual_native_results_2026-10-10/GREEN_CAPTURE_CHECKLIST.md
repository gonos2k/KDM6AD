# PR397 actual-result review checklist

Use this checklist only after the root supplies the completed native intake,
capture `RESULT`, driver `DRIVER`, and private checkpoint paths. Inspect those
saved artifacts without starting a consumer, model, KDM6 transition, or RTTOV
call. Do not infer matchup or scientific acceptance from numerical return.

## Run and input binding

- Confirm the native runner's own exit code is zero, validity/completion flags
  are true, and all eight actual `Times` equal the declared sequence from
  05:55:40 through 05:58:00.
- Confirm the intake manifest/NPZ paths and SHA-256 values match the capture
  receipt. Check the selected column remains `(j=86, i=48, K=39)` and the clock
  remains nominal 05:56:00 with pixel time unverified.
- Confirm host eta-layer dry mass is finite, positive float32 `[8,39]`, its
  `[39]` first-frame vector equals window frame 0, and source metadata gives
  units/formula/orientation. In the capture NPZ, require the first-frame key
  `host_dry_mass_background_kg_m2` to retain float32 `[39]` values.
- Keep raw `PH` and `PHB` labeled geopotential `m2 s-2`; pressure values belong
  to the separate center and P8W interface arrays.

## Initial cost and probe separation

- In capture `objective.initial_zero_control_closure`, check `trace_index=0`,
  `Jb_state=0`, `Jtheta=0`, `Jtotal = Jb_state + Jtheta + Jo`, `n_valid=7`,
  and the recorded operator signature.
- Confirm `Jo` matches the first successful `grad=True` callback's Huber cost,
  and the initial signature/mask match the accepted audit signature/mask.
- In `background_quality_probe`, inspect the raw first `grad=False` cost and its
  zero mask, BT, quality flags, and target. Keep this `raw_J_huber` separate
  from zero-control `Jo`.
- In the driver receipt, require `objective_audit.status == "CROSSCHECKED"`,
  `h_or_m_re_evaluations_for_crosscheck == 0`, and inspect its comparisons of
  raw probe cost under the zero mask and probe BT under the frozen seven-channel
  mask.

## Final analysis and optimizer record

- Reconcile final `Jb_state`, `Jtheta`, `Jo`, and `Jtotal` with the final trace
  and verify `n_audit_evals == 1`, seven frozen channels, zero final model
  quality flags, and a stable 64-character observation signature.
- Read the total control-space gradient norms and hashes separately from H
  adjoints. Confirm private NPZ gradient vectors resolve to the public
  `private_npz_key` metadata and match recorded hashes/shapes.
- Inspect actual `n_iter`, `func_evals`, `max_iter`, `max_eval`, `step_t`, and
  tolerances. Preserve termination status as `UNKNOWN`; do not call it
  converged from the iteration count or tolerance flag alone.

## Private state checkpoint

- Verify the private directory/file modes (`0700`/`0600`) and checkpoint SHA.
- Verify full 12-field records for `background_initial_state`,
  `returned_analysis_initial_state`, `background_slot_state`, and
  `final_slot_state`, plus input/final forcing and frozen `rho_d`.
- Verify native centers, REAL(4)-transcribed P8W interfaces, raw PH/PHB, Exner,
  host dry mass, observations, four control blocks (`v_state`, `v_theta`, all
  12 `b_sigma`, fixed eta markers/values), full final gradients, and pre-audit
  optimizer-state arrays against the receipt's key/hash/shape metadata.
- Keep initial analysis state distinct from observation-slot state. Any saved
  state diagnostic remains a derived saved-array comparison; it does not
  establish forecast closure or physical attribution.

## Reporting boundary

Report separately whether native inputs validated, the numerical minimizer
returned, and the physical matchup/science review accepted. The expected capture
classification is diagnostic-only; pixel-time, footprint, height-datum, and
scientific acceptance remain unassessed unless their own evidence changes.
