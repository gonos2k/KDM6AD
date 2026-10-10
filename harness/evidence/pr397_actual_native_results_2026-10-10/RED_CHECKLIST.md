# PR396 saved-result Red interpretation checklist

Prepared against merged PR396 (`eec82d65`) while native run 99158 was still
reported active and continuation v4 had not run. This is a checklist for a
later review of saved arrays and receipts; it is not an interpretation of an
actual analysis result. No native, H, M, or RTTOV work was performed here.

## Verify provenance before interpreting values

- [ ] Confirm archived completion evidence says runner exit code 0 and both
  `experiment_valid` and `model_completed` are true. Intake also requires the
  exact run ID and one archived forecast (`intake_native_tq.py:127-147`).
- [ ] Confirm all eight actual `Times` match the predeclared list and the
  selected column is the fixed zero-based native `(j=86, i=48)` with the
  required 39 center and 40 interface levels. Do not treat successful process
  exit alone as a valid intake (`intake_native_tq.py:310-324, 442-450`).
- [ ] Bind the analysis to the intake manifest/NPZ hashes and the capture
  receipt/checkpoint hashes before reading profiles. The saved-state tool
  checks those hashes and requires the declared first pair
  `2025-07-19_05:55:40`, `2025-07-19_05:56:00`
  (`diagnose_saved_state.py:84-103`).
- [ ] Keep the nominal time interpretation fixed: `obs_time=1`, `dt=20 s`,
  and the nominal slot `05:56:00`. This is not a verified per-pixel AMI UTC
  match; do not switch to another saved frame after seeing the result
  (`intake_native_tq.py:442-445`; observation receipt says
  `pixel_time_verified=false`).
- [ ] Preserve the declared candidate pair: VIIRS `(205,27)`, AMI `(320,48)`,
  native `(86,48)`, channels AMI 10–16. Report any correspondence limitations
  from the receipt (pixel time, footprint overlap, height datum); do not choose
  a different column, pixel, or channel subset post hoc
  (`run_analysis.py:215-237`; `RECEIPT.json:90-102`).
- [ ] Keep the run's fixed settings in the interpretation: observation sigma
  1 K, Huber delta 1 K, theta sigma 0.8 K, qv log sigma 0.08, qv control
  limited to the lowest 12 levels, no active parameter prior, `max_iter=3`,
  no retry. Do not tune sigma, channel support, or candidate selection after
  inspecting costs (`run_analysis.py:298-326`; `capture_tq_state.py:976-1010`).

## Interpret the saved-array diagnostics narrowly

- [ ] Report the four water increments separately, with signs and units:
  `analysis = xa - xb`, `model_analysis = ma - xa`,
  `model_background = mb - xb`, and `slot_analysis_minus_background = ma - mb`.
  Each is a layerwise sum of saved water mixing ratios over `qv,qc,qr,qi,qs,qg`
  multiplied by the first native frame's host eta dry-mass vector
  (`diagnose_saved_state.py:46-71`).
- [ ] Treat the reported decomposition residual as an algebraic identity check:
  `(ma-mb) = (xa-xb) + (ma-xa) - (mb-xb)`. A near-zero residual follows from
  using these four differences; it does **not** show a closed water budget,
  conservation by the host or KDM process, or absence of boundary/external
  fluxes. Those fluxes are unmeasured and the receipt explicitly says the
  budget is not closed (`diagnose_saved_state.py:69-80,121-124`).
- [ ] Describe `host_minus_local__*` as the native frame-1 state minus the
  capture's local background-slot state. The local value is the existing
  one-step `M(xb)` slot state; the host and local paths differ in included
  processes, splitting, and forcing. Do not call the difference a KDM
  microphysics error, a process attribution, or `R`
  (`diagnose_saved_state.py:27-35`; `run_analysis.py:620-632`).
- [ ] Interpret the temperature terms only as a coordinate identity:
  `pi1*theta_host - pi0*theta_local = pi1*(theta_host-theta_local) +
  theta_local*(pi1-pi0)`. Label them theta and Exner contributions under this
  decomposition; do not claim they isolate causal heating or a physical
  process (`diagnose_saved_state.py:36-45`).
- [ ] Use only the specified fixed mass measure in these summaries: original
  bottom-up float32 `[8,39]` host eta mass from
  `-(C1H*(MU+MUB)+C2H)*DNW/9.81`, with frame 0 selected for weighting. It is
  distinct from EOS `rho_m*delz`; do not relabel it as an observed mass budget
  (`intake_native_tq.py:358-364,454-460`; `diagnose_saved_state.py:46-52`).

## Do not infer independent retrieval or parameter identification

- [ ] State that the observation vector has seven AMI channel values and the
  local state-control space contains more than seven potential components:
  39 theta levels plus at most 12 qv levels under the frozen support rules.
  The actual nonzero qv count can be reduced by source-state/headroom masking;
  use the captured `active_counts_from_built_sigma` and control-array shapes
  for the realized count (`da_single_column.py:208-212,242-278`;
  `da_cvt.py:248-270`).
- [ ] A local observation Jacobian with seven rows has rank at most seven,
  regardless of how small the final cost or gradient is. This dimensional
  bound does not establish the rank actually attained, independent retrieval,
  or parameter identifiability. No singular-value/conditioning result is
  included in this capture.
- [ ] Do not use the captured total-objective control gradient as an H-only
  sensitivity or rank certificate: it includes prior and CVT/log-parameter
  chain terms (`capture_tq_state.py:676-683`). Parameter priors are inactive
  for this fixed run; their inactive control slots do not add identified
  degrees of freedom (`da_single_column.py:203-210,281-287`).
- [ ] Keep optimization outcome language literal: a returned result after a
  three-iteration L-BFGS allowance is a numerical return, not proof of
  convergence. The capture records termination status/reason as unknown
  (`capture_tq_state.py:643-656`).

## Required conclusion boundary

Even if intake, analysis, and diagnostic receipts all validate, classify the
result as a saved-array diagnostic with `science_accepted=false`. A cost
reduction, algebraic identity, fixed-support gradient, or native/local state
difference does not repair the unresolved pixel-time, footprint, or height
datum correspondence and does not establish forecast skill or unattended
cycling.
