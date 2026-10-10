# PR397 saved-result capture review

This is a read-only review of capture `RESULT_3d2e97f159.json`, its matching
`DRIVER_3d2e97f159.json`, and the private accepted-state NPZ named by the
capture receipt. No model, KDM6 transition, RTTOV H, consumer, retry, or waiter
was started.

## Execution and input status

The intake manifest reports the expected fresh run ID, runner `exit_code=0`,
`experiment_valid=true`, `model_completed_flag=true`, and the exact eight saved
times from 2025-07-19 05:55:40 through 05:58:00 UTC. The selected column is
`j=86, i=48, K=39`; the evaluated slot is the nominal 05:56:00 sample and
`pixel_time_verified=false`. The capture receipt's manifest and intake NPZ
hashes match the intake binding, and the driver receipt's capture SHA matches
the persisted RESULT file.

The process observers recorded WRF rank exit 0 and MPI launcher exit 0. The
separate outer harness observer recorded exit 120, and its receipt says no
`MPI_Finalize` call was observed. Therefore the archived native runner's
validity and saved-frame gates passed, while the overall harness process is
not reported as a normal zero exit.

## Objective and audit evidence

The first existing zero-control closure reports `Jb_state=0`, `Jtheta=0`,
`Jo=26.588575903055926`, and `Jtotal=26.588575903055926`, with `n_valid=7`.
Its Jo matches the first `grad=True` callback and the operator signature matches
the accepted audit. The separate first `grad=False` zero-mask quality probe
reports raw `J_huber=0`; the driver's saved-array cost audit reapplies the
frozen seven-channel mask to its BT and reproduces the initial Jo with zero
additional H or M evaluations (`objective_audit.status=CROSSCHECKED`).

The returned final objective is `Jb_state=0.2284737909127953`,
`Jtheta=0`, `Jo=26.135616402715186`, and `Jtotal=26.36409019362798`, matching
the final trace total. The result records exactly one final audit, seven valid
channels, an all-one support mask, all-zero final rad-quality flags, and stable
operator-signature SHA-256
`2564e3298a383f3b9bdb348cc5abbd68156653b633f4963551fdc799132d1e59`.

The total control-space gradient has state L2 norm `0.00020011374514061956`
and L-infinity norm `0.00007817358308397082`; the parameter-control gradient is
zero. The actual optimizer snapshot reports `n_iter=2`, `func_evals=3`,
`max_iter=3`, `max_eval=3`, `step_t=1`, and `tolerance_grad=1e-10`. The final
audit maximum gradient is above that tolerance, and the stop reason remains
`UNKNOWN`; no convergence claim is made. Parameter `v_theta` and `sigma_log`
are zero, and saved parameter analysis equals the fixed background parameter
vector `[0.4, 3030.0, 2590000000000000.0, 1.0]` in
`[peaut, ncrk1, ncrk2, eccbrk]` order. The T/Q background scales have
`th=0.8` on 39 levels and `qv=0.08` on
12 levels; other state-field scales are zero. Fixed `eta`/`eta_pre` are absent.

## Private checkpoint verification

The accepted-state NPZ exists at its receipt path, has mode `0600` in a `0700`
directory, and matches its recorded SHA-256. It contains all 12 fields for
`background_initial_state`, `returned_analysis_initial_state`,
`background_slot_state`, and `final_slot_state`; every saved state hash matches
the public receipt. The initial state and forcing are exactly equal to the
validated intake NPZ. Control/gradient and optimizer-history arrays resolve to
the public key/shape/dtype/hash metadata. Saved parameter prior and analysis
arrays match, and the private `v_theta` is zero.

The checkpoint preserves the float32 `[39]` host eta-layer dry mass, equal to
frame 0 of the intake's float32 `[8,39]` window. Center pressure is a separate
float64 pressure array; P8W interfaces are the declared float32 transcription.
Raw PH and PHB are retained and labeled geopotential `m2 s-2` in the receipt.
Exner, native pressure, forcing, observations, and the four State records are
present.

The actual NPZ is missing `final_slot_frozen_mask` and `final_slot_bt_K`: the
executed helper looked for legacy callback keys `mask`/`bt`, while this run's
callback receipt contains `fixed_mask`/`BT_K`. `final_slot_rad_quality` exists,
and the public callback/receipt contains mask, BT, quality, and signature. A
receipt-derived sidecar now contains the missing mask/BT arrays and rad-quality
and matches all three values against the public final callback. Its hash is
`3ae28d0d3a8782524ace1f8024d58be560a1ec72e8c5464ebb63177488e46a07`; the
historical RESULT and NPZ remain unchanged, and the sidecar performs no new
RTTOV execution. The capture producer has also been corrected for production
and legacy callback key spellings; its synthetic storage regressions pass.

The saved-array diagnostic returned `DERIVED_FROM_SAVED_ARRAYS`, with zero
additional model/RTTOV calls. It reports a fixed-frame host eta-mass-weighted
water increment of `+0.2216824149154899 kg m-2`, while boundary/external fluxes
remain `NOT_MEASURED` and `closed_water_budget=false`. This is an array
decomposition, not a conservation or process-attribution claim.

## Scope and acceptance

The capture is `RETURNED_DIAGNOSTIC_ONLY`. Physical matchup/science acceptance
remains `NOT_ASSESSED`; pixel time is unverified. The saved temperatures and
qv/qs ratios are model-state summaries under the recorded forcing and
thermodynamic formulas, not observed vapor-pressure RH. QC/NC sums are
unweighted vertical-level sums. These records do not establish a column budget,
process attribution, forecast skill, or operational validity.

The capture helper hash executed for this result is the preserved `eec82d65`
blob SHA-256 `32391d7750ad54c4c2aee64a5d30cde9f9d98822fcc569650aeef9c334c50311`.
The current PR397 helper includes only a future NPZ-key mapping fix; the old
result and checkpoint were not rewritten. No solver or historical 933 artifact
was changed.
