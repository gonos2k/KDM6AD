# PR395 native T/Q state capture

`capture_tq_state.py` wraps the existing `run_single_column_analysis` adapter
for the predeclared one-column, one-step case. The caller supplies an intake
manifest and NPZ that have already passed the native-input gate. The helper
checks their identities, verifies the selected initial `State` and `Forcing`
arrays against those files, calls the adapter once, and records the final
accepted-state audit through the all-sky callback that the adapter already
executes. It does not rerun the model step or replay the observation operator.

The private NPZ stores the complete 12-field background initial state, returned
analysis initial state, background slot state and final audit slot state; the
input and audit forcing; frozen dry-air density; native center/interface
pressures; Exner; observations; and the caller's RTTOV grid/reference arrays.
The private directory and file are set to mode `0700` and `0600`. Publication
uses a same-directory, no-clobber atomic link. The public `RESULT.json` keeps
state hashes and metric summaries; configuration arrays are represented by
shape, dtype and SHA-256 rather than full state arrays.

The NPZ also stores final `v_state`/`v_theta`, all 12 `b_sigma` fields,
parameter background/analysis values and log-prior widths, and the fixed
`eta`/`eta_pre` presence and values (empty arrays plus `present=false` when
the adapter pins them to `None`). The final full control-space gradient is
read from the original LBFGS parameters after the existing accepted-state
audit; the helper checks those controls against the returned result and its
state and parameter gradient norms. Public output contains control and
gradient hashes, shapes, and L2/L-infinity norms. These are total-objective
gradients in control space, including prior and CVT/log-parameter chain terms;
they are not RTTOV H-adjoint norms.

The helper pins this run to `obs_time=1`, one 20-second forcing, three optimizer
iterations, seven AMI channels, observation sigma/bias `1/0 K`, state priors
`0.8 K` and `0.08` log-qv over the lowest 12 levels, inactive parameters,
zero-initialized control, `ncmin_land=ncmin_sea=10`, and exactly one final
accepted-state audit. The observer wraps the original PyTorch LBFGS instance's
`step` call and records its actual counters, last line-search step, and
tolerances. PyTorch does not return the stop condition, so the receipt marks
the termination status unknown and reports the final-audit gradient/tolerance
flag separately. Any callback quality loss or validation/analysis error leaves
no successful checkpoint. A failure receipt may record the failure. The compact
optimizer state is preserved as pre-audit provenance, not as a resumable
optimizer checkpoint.

Receipt sections distinguish validated input, numerical return, and physical
matchup/science acceptance. A successful numerical return remains diagnostic:
nominal-slot timing with unverified pixel time does not establish an accepted
GK2A matchup or scientific result. The metric named phase-aware RH is KDM6's
`qv/qs(T,p)` ratio; the separate liquid-water ratio is `qv/qs_water(T,p)`.
Neither is reported as observed vapor-pressure `e/es` RH. `qc` and `nc` sums
are unweighted sums across native levels, not column-integrated budgets.

`test_capture_tq_state_storage.py` uses synthetic data only. It checks private
file permissions, exclusive publication, four distinct 12-field state
roundtrips plus control arrays, and that a pre-analysis failure does not create
a state checkpoint. A synthetic quadratic compares the observed original
LBFGS step with an unobserved step for exact value/gradient and counter parity.
These checks do not execute the native model, RTTOV, or the single-column
analysis.
