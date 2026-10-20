# Two-step cold T/Q state-carry comparison protocol

This is an experiment definition, not a report of model outcomes. It specifies
how to compare one saved T/Q increment at the cold valid time with an empty
control, then verify that the incremented native state carries through a second
uncontrolled step in the same WRF process.

## Paired runs

| Run | At 00:00:00 / step 0 | At 00:00:20 / step 1 |
|---|---|---|
| Inactive control | Empty `ANALYSIS_TQ` command | Empty `ANALYSIS_TQ` command |
| Saved-DA probe | The bound saved posterior increment for column 4835 (`i=156,j=21`) across 39 native levels | Empty `ANALYSIS_TQ` command |

Both cases use the same cold input, external assets, namelist template, WRF
executable, installed KDM library and runner. Use one MPI rank and one thread,
fixed `dt=20 s`, MP137, and the live stepper's every-step radiation setting
(`radt=dt/60`, with the same required STEPRA/STEPBL/STEPCU seeds). Start each
case from its own cold run, let the hook capture the actual time-zero restart,
and keep the process alive across both solves.

The probe's first increment must be bound to the actual startup checkpoint
hash, valid time, and native geometry. The increment source is the saved,
unaccepted offline posterior at 00:00:00. It updates only prognostic `THM_2`
(in-memory `grid%t_2`) and `QVAPOR`; the second empty command must not add zero
to either field. Do not use NetCDF `T`, which is diagnostic dry potential
temperature. The native state after step 0 is the input to step 1; neither run
restarts from the original input between steps.

## Evidence to capture

- Executable, library, source, runner, input and namelist identities for both
  cases; exact start/end times, `ITIMESTEP`, actual radiation cadence and
  physics call counts.
- Ready/command/ack records for both generations. The probe has the 39-row
  T/Q command at generation 0 and an empty command at generation 1; the
  inactive control has empty commands at both generations. Bind generation 1
  to the output checkpoint hash from generation 0.
- Initial and 20/40-second full-state checkpoints: variable inventory,
  dimensions, types, finite/complete status and raw-bit comparisons. Compare
  each run's own no-op identity separately from the intentional probe/control
  difference; raw inequality between probe and control is expected evidence,
  not a failure threshold.
- Actual MP137 input traces for both steps, including TH/Q/DEN/PII/P/DELZ, and
  the resulting finish H/QV tendency fields. Confirm the second step receives
  the carried probe state despite the empty command. Record that pressure and
  density are rebuilt through the host path; do not infer them from the
  increment formula.

## Producer and consumer source anchors

The public producer path is `harness/native_analysis_increment.py::encode_native_increment`
followed by `harness/native_analysis_control.py::encode_analysis_command`. The
live consumer is `harness/native_live_stepper.py::NativeLiveStepper.advance`;
it binds nonempty increments to the current checkpoint and accepts an empty
tuple for a no-op T/Q generation. The isolated source overlay writes the pair
to `grid%t_2` and `grid%moist(...,P_QV)` after validating all rows.

In the active private host, `frame/module_integrate.F:374-394` calls
`med_before_solve_io` before `solve_interface`; the isolated hook is at that
pre-solve boundary. `dyn_em/solve_em.F:3663-3674` passes current `grid%t_2` and
QV to `moist_physics_prep_em` before MP137; `:4088-4100` runs the matching
physics finish. The post-RK diagnostic pressure/density update is at
`:2954-2977`. These source paths explain what the run should inspect; they do
not constitute a result for the two-step cases.

This comparison can establish that the saved increment enters native MP137
physics and its tendency path across the two tested steps. It cannot establish
an accepted or converged analysis, global water/energy balance, conservation,
observation-cost reduction, a full-host adjoint, or cycling skill. QV increments
are external water sources and require a separate mass budget.
