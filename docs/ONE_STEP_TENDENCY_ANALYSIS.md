# Fixed-time analysis using a one-step tendency operator

The one microphysics step is used to diagnose the applied tendency and its
sensitivity. Advancing a host forecast clock is not a completion condition for
this analysis goal. This distinction does not make the existing one-shot
experiment an effective cloud initialization: physical T/Q/cloud increments
and residual reduction at the relevant native locations must be assessed
separately.

## Implemented operator

For a control state `x`, the native batch adapter evaluates one 20 s KDM map,
cleanup and finish. Write its applied-state output as

```
r_tau(x) = applied mean tendency diagnosed using tau = 20 s
x_applied = A_tau(x, r_tau(x))
J(x) = fixed-support loss(H(x_applied), observation)
```

For QV and QC, `r_tau` is cleaned-after minus before, divided by tau.
`H_RATE` is a moist-theta heating-memory rate, not a physical-temperature rate
or simply the raw dry-theta difference divided by tau. The native finish
coordinate conversion and limiter remain part of `A_tau`.

In the corresponding applied native coordinates the continuous first-order
relation is `d x_applied = d x + tau * d r_tau`, with the documented floating
point recovery residuals. The direct old-state terms in the tendency and
finish derivatives are required. The step-mean tendency is not an
instantaneous named-process RHS; it includes the selected integrated KDM and
cleanup/finish operations.

After finish, `NativeBatchMicrophysics._evaluate` calls `_prep_batch` again to
diagnose pressure/density for the updated state. This is EOS/profile
preparation, not a second KDM integration. Actual temperature for comparison
is diagnosed from updated moist theta, QV and live pressure:

```
T = (theta_m_pert + T0) / (1 + alpha * QV) * (P / p0)**kappa
```

The prescribed geometry, MU/PH and external configuration stay fixed in the
current T/Q experiment. Derived native prep forcing must still be recomputed:
PII and P depend on the updated control. DEN/DELZ are constant for this fixed
geometry. Freezing all four forcing rows would remove a required path.

## What the executed one-shot runner does

`run_native_satellite_case.evaluate_block` copies the original block T/Q,
adds one proposed input delta, then executes the operator once. Each spatial
chunk is loaded again by `_execute_chunk_job`; no checkpoint is overwritten.
`run_trials` assembles one gradient direction, tests alpha 1, .5 and .25 from
the same background, and returns after acceptance. The restricted confirmation
likewise evaluates its one projected candidate from the original background.
The finite-difference probes rebuild `x_background +/- epsilon * direction`
independently. These are candidate/probe evaluations, not successive physical
timesteps or successive accepted analysis iterations. Alpha and epsilon scale
the input perturbation; they do not change the 20 s microphysics cadence.

Sources: [runner](../harness/run_native_satellite_case.py),
[batch adapter](../harness/native_batch_microphysics.py),
[finish contract](APPLIED_FINISH_AD.md).

## Required outer analysis loop, not yet executed

Keep an immutable background and control scale:

```
x_k = x_background + S * z_k
r_k, x_applied_k = tendency_and_application(x_k)
J_k, g_k = objective_and_gradient(x_applied_k, fixed_observation_support)
z_trial = project_original_box(z_k + eta * preconditioned_direction(g_k))
```

After accepting `z_trial`, retain it as the next `z_k` and recompute tendency,
objective and gradient at that new control. Do not reset `z` to zero or reuse
`g_0`. Do not replace the background by `x_applied_k` and thereby accumulate an
extra microphysics step at each minimizer iteration. The background/prior
anchor and `S_q = .02 * qv_background` remain fixed. Evaluate each trial with
one tendency application; never add that tendency again to an already applied
state. Preserve the original observation mask and weights.

The current job helper ties `record` to whether a baseline record is supplied.
An outer optimizer must separate fresh gradient recording from the immutable
baseline support; calling `evaluate_block(record=True, baseline=original_baseline_arrays,
delta=...)` expresses this distinction. Its incidental fixed-direction JVP
must not be relabeled as the optimizer's proposed direction.

Physical efficacy requires co-located native actual-temperature, QV, QC, QI,
QS and LWP/IWP changes, together with O-B/O-A changes in baseline-defined
regions. A small global cost decrease, a selected-column response or execution
coverage alone does not establish that goal. Continuous cloud fraction is not
a current control: the existing CFRAC is a detached binary condensate gate.
It is recomputed in each forward evaluation and may change at a finite
optimizer trial. Fixed CFRAC is an FD-neighborhood diagnostic, not an optimizer
constraint that would prohibit new clouds; the fixed observation mask is a
different contract.

## Separate host-transition prototype

`NativeHostTransition` has an origin-bound continuous-prefix replay for its
value-only host-step tests: requested logical step n executes a prefix of
(n+1)*dt and verifies the supplied intermediate frames. It does not relabel a
step-one checkpoint as step zero. This prototype is not invoked by the
satellite tendency experiment, and a complete accepted-analysis host cycle is
not claimed here. See [transition scope](NATIVE_MP137_TRANSITION.md).

## Requested and representable directions

The block22 activation packet tests the original continuous requested T/Q
proposal. Its signed-zero lineage comparison does not make it a test of the
later binary32 effective native displacement. PR #451 adds that preparation
boundary; the separate C4 effective-direction campaign remains pending here.
The older common-epsilon joint33 failure is retained for its own vector.
