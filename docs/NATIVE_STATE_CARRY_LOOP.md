# Native state carry with H-rate and T/Q controls

This follow-up connects sequential native execution without restarting WRF at
each checkpoint. It is value-only. The live stepper supports a retained-rate
H probe (`H_RATE`, the default) and an opt-in prognostic moist-theta/QV analysis
increment (`ANALYSIS_TQ`). It does not implement observation optimization, a
general balanced full-host encoder, full-host AD, or an equilibrium test.

## Applied map and physical scope

### H_RATE diagnostic probe

At a completed, noninitial timestep, `H_DIABATIC` is retained heating-rate memory
in the audited `USE_THETA_M=1` host coordinate, K/s. It is not the prep-phase copy
of full dry potential temperature. A sparse control applies

\[
 R_H^{new}=\operatorname{fl}_{32}(R_H^{old}+\delta R_H).
\]

The hook changes this memory only. Other prognostic and working arrays receive
no direct change at that boundary. Direct water mass/number departures from the
injection are zero; subsequent microphysics and transport evolve them through
their normal maps. A nonempty control must be finite and produce a representable
memory change. Its old, requested and actual new binary32 values are recorded.
The empty command performs no floating-point update, including no addition of zero.

The next full host step is

\[
 X_{n+1}=\Phi_{20s}(\operatorname{inject}_H(X_n,\delta R_H), U_n).
\]

The host's existing RK/dynamics, thermodynamics, MP137 writeback and finish
operations determine the response. The controller never reconstructs temperature
as `theta += dt * delta_rate`, and never applies an already consumed KDM change
a second time. There is no assumption that the final thermal departure equals
`dt * delta_rate` or that one step establishes equilibrium. Applied heating
budgets in the host mass/energy coordinate remain a separate validation task.

In real arithmetic, the injection's tangent is
`dR_new = dR_old + ddelta`; its pullback copies the output cotangent to both
inputs. This elementary relation does not supply native RK/forcing derivatives
or certify differentiation of the binary32 path. Native JVP/VJP remain unavailable.

## Boundary and ownership

The isolated source overlay inserts a hook at the end of
`med_before_solve_io`, immediately before its terminal `RETURN`: after the
normal history/restart output and lateral-boundary input, before the next solve.
The same native process retains U/V/W, thermodynamic/moisture states, retained
physics rates, boundary/halo work arrays and its model clock. The timestep's
serialized checkpoint is exposed for inspection, but is not presented as a
complete copyable working-state snapshot.

The H_RATE family is restricted to warm completed timesteps; ANALYSIS_TQ also
supports a cold valid-time start after input/checkpoint binding. Both families
require MP137, fixed 20 s, domain 1, one MPI rank, one thread,
`NO_MP_HEATING=0`, `USE_THETA_M=1`, and `USE_Q_DIABATIC=0`. WRF's internal tile
count is unrestricted: the hook runs once outside tile loops and addresses the
domain-global state on the single rank. An absent control-root environment
variable leaves the normal model path without a floating-point control update.
The operational source/install remains untouched; the hook and transport are
opt-in.

`NativeLiveStepper.advance(current, controls)` consumes exactly the currently
exposed `LiveState`. A stale, forged, foreign or already consumed state cannot
advance the process. The next state is the result of the previous native solve;
it is never replaced by the original background. An invalid packet, clock,
checkpoint, acknowledgement or process exit fails the session and reaps its
owned process group.

`run_state_carry_loop` connects proposal → native adjustment → explicit
adjustment acceptance → next-state handoff. Its caller must supply both a
proposal function and a documented adjustment criterion. It has no default
balance certificate. Rejected adjustment ends the live session before another
native step can execute. Replaying alternative optimizer trials from an accepted
working state requires a separately validated reset/replay mechanism; a live
state cannot be forked by copying its checkpoint filename.

## Native evidence

`LIVE_IDENTITY_V2` ran in one persistent WRF process from 120 through 180 s,
with an empty control at every boundary. At 140, 160 and 180 s, all 652
checkpoint variables matched the inactive-control reference bit for bit; the
comparison reported zero mismatches and no metadata differences or
normalizations. The run used one MPI rank and one thread. WRF retained its
normal two internal tiles; the hook executes once outside the tile loops. The
first hook guard incorrectly required one internal tile and refused the valid
two-tile setup after its first computed step. That metadata-only guard was
removed without changing the model tiling, and the identity run then completed.

This is evidence that the live empty-command path preserves the tested native
trajectory over these three steps. It is not restart equivalence, a complete
balanced-state encoder, observational assimilation, or a derivative test.
The separate `LIVE_H_UPDATE` trial applied `+0.001 K s-1` to retained
`H_DIABATIC` at the 140 s boundary (saved step 7), at `(i=156,k=6,j=21)`. It
was an artificial memory intervention, not a data-assimilation increment. The
next microphysics call (call 8) differed from its control at six TH levels and
21 QV levels; DEN, PII, P and DELZ differed at 23, 23, 23 and 21 levels.
Call 7 was unchanged, and call 9 also showed changed inputs. The sampled
finish replay had zero arithmetic or packing mismatches across 117
level-step samples. These results show the H memory perturbation affected
later native forcing and tendencies. They do not show balance, convergence,
assimilation, or a valid analysis update.

### ANALYSIS_TQ posterior increment

`ANALYSIS_TQ` applies a saved posterior increment to the current prognostic
`grid%t_2` and vapor mixing ratio. In the audited `USE_THETA_M=1` path, the
in-memory `t_2` is a perturbation of moist potential temperature and is stored
as NetCDF `THM_2`. NetCDF `T` is diagnostic dry potential temperature and is
not the prognostic field to update. Startup checks found `THM_2` and `THM_1`
bit-identical to `THM` at the initial time; `QVAPOR` also matched. An earlier
T-field selection was rejected at source binding before any command was
applied, then corrected to use `THM_2`.

The public value encoder in [`native_analysis_increment.py`](../harness/native_analysis_increment.py)
maps dry-theta/QV posterior and background arrays to `delta_t_2` and `delta_qv`,
bound to valid time, geometry, layout, units, and background checkpoint. It
uses the active host's captured binary32 `Rv/Rd` coefficient, bit pattern
`3FCDDED2`; the nominal-ratio f64 reader is a different coordinate. The
native hook applies only these two prognostic increments. It leaves `t_1`,
`H_DIABATIC`, pressure, density, and other diagnostics alone; the next host
integration and MP prep/finish compute the resulting physics response. The
wire boundary skips exact zero pairs and does not add zero to an unchanged
field.

`encode_native_increment` checks units, alpha coordinate, valid time, geometry,
layout and checkpoint binding before it returns the increment carrier.
`NativeAnalysisIncrement` is a public data class and can also be constructed
manually; the live stepper independently checks array shape, time, geometry,
layout and current background hash but trusts the caller to use the checked
encoder for units and alpha provenance.

The corrected cold identity command completed one 20-second native step with
no T/Q rows. Against a helper-disabled run with the same executable, inputs and
radiation cadence, all 652 fields (322,426,586 numeric values) matched at
00:00:20; metadata had no differences or normalizations. The saved-DA run then
applied 39 T/Q rows from one unaccepted offline
KO7 diagnostic column at valid time `2025-07-19_00:00:00`, native
`(i=156,j=21)`, across all 39 levels. Its background T/Q matched the cold
native input, and the starting checkpoint matched the identity run. The
analysis came from one saved posterior; no observations were reevaluated and
no new RTTOV cost or optimizer was run.

At the first MP137 call, all 39 levels changed in TH, QV, DEN, PII, P and
DELZ; maximum absolute differences were 0.527313 K, `4.35878e-5` kg/kg,
`5.52177e-4` kg/m³, `9.59635e-5`, 11.046875 Pa and 1.125977 m respectively.
The MP137 driver ran twice across the two internal tiles. The resulting state
had differences in 136 of 652 complete finite variables, comprising 48,264
numeric values versus the identity control. `H_DIABATIC` was not directly
incremented; native finish produced a changed H rate at 28 levels, maximum
`1.32772e-4 K s-1`, and QV rate changes at 10 levels, maximum
`3.54601e-8 kg kg-1 s-1`. Sampled finish arithmetic and packing replay had
zero mismatches over all 39 levels. This confirms the saved T/Q change entered
the actual native forcing and produced native tendencies for this one step.
There was no next MP call, and the result is not a converged/accepted analysis,
physical balance certificate, conservation proof, or full-host derivative.

### Radiation cadence

The live stepper defaults to `radiation_every_step=True`. For 20-second steps
this writes `radt=1/3` minute and requires an explicit `STEPRA=1` seed for a
restart-origin run. The separate two-step radiation variant executed four
RRTMG longwave and four shortwave calls across two internal tiles, with
`STEPRA=1` at 120, 140, and 160 seconds. This is a cadence-specific physical
variant; it does not claim raw-bit equality with the prior five-minute
radiation schedule. In the saved-DA one-step run, the namelist also had
`bldt=0`, `cudt=0`, `STEPRA=STEPBL=STEPCU=1`; the two internal tiles produced
two calls each to RRTMG LW/SW, Shin-Hong PBL, KSAS cumulus, and KDM6AD. The
outer PBL, cumulus, and microphysics drivers each ran once. These counts are
specific to that case, not arbitrary templates. The cadence variant adds no
RTTOV observation run or derivative evidence.

## Time and assimilation

The native model clock advances by 20 s per physical solve. This transport does
not choose the analysis loop's timestamp or which observations to reuse. The
choice between analysis iterations at one valid time and advancing assimilation
cycles remains explicit work; observation acquisition times must be checked
before observations are evaluated. The old KO assimilation stays paused.

The one-step saved-DA result establishes state-to-physics-to-tendency causality
for this specific T/Q update. A separate H_RATE state-carry run accepted three
state transitions using finite pressure, positive specific volume, and
nonnegative water checks. Those checks are not physical balance, conservation,
a usable adjoint, observation assimilation, or completed cycling.
The public [`REPORT.md`](../harness/evidence/native_state_carry_2026-10-20/REPORT.md)
and compact summary record the bounded results and their limits.
