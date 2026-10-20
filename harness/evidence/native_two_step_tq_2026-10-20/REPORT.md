# Two-step cold T/Q state carry

This report records a paired 40-second MP137 cold-start comparison. The probe
applies one saved, unaccepted offline T/Q posterior at 00:00, then sends an
empty T/Q command at the next boundary. The matched baseline sends empty
commands at both boundaries. The purpose is to verify that the changed native
state and its generated tendency memory reach the following step in the same
WRF process.

The one-step evidence at [`native_state_carry_2026-10-20`](../native_state_carry_2026-10-20/REPORT.md)
remains historical and unchanged.
The compact metrics are in [`summary.json`](summary.json).

## Cases and attribution

Both cases start from the same cold `wrfinput` and captured 00:00 checkpoint,
run `mp_physics=137` for two fixed 20-second steps, use one MPI rank and one
thread, and use every-step radiation (`radt=1/3` minute). They share the same
actual namelist SHA256, v4 executable
`a6879994ed91d5f1964dd16e788eb7c469a80a36c59f215b4cb03ec43f885e78`, and
installed KDM library `7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7`.
The build replaced the mediation object and step-control helper in an existing
isolated build; remaining archive members were reused. This is not a clean
full-host rebuild.

`TWO_STEP_ZERO` sent empty `ANALYSIS_TQ` commands at both steps and completed
checkpoints at 00:00:00, 00:00:20 and 00:00:40. The saved-DA probe applied 39
T/Q rows at 00:00:00 to `(i=156,j=21)` across all 39 levels, then sent an empty
command at 00:00:20. Both ran in one persistent native process. In the probe,
the 00:00:20 output checkpoint SHA equals the second-step input SHA. There
were no direct `H_DIABATIC` updates. The baseline had zero rows at both
boundaries; the probe had 39 then 0.

The v4 baseline's 00:00:20 frame also matched the prior v3 one-step reference:
all 652 variables and 322,426,586 numeric values were raw-bit equal, finite,
and complete. Metadata matched except for the two documented output-alarm
Boolean normalizations `WRF_ALARM_ISRINGING_01` and `_07` under the timer
override policy. This is a first-step cross-build check; it is not a historical
40-second terminal reference.

## T/Q response through both native steps

The saved posterior is an unaccepted offline KO7 diagnostic result at valid
time 00:00:00, column 4835 / native `(i=156,j=21)`. Its source background T/Q
matched the cold input across the domain. It changed one column and all 39
levels; maximum requested coordinate increments were `|delta_theta_m|=0.553983 K` and
`|delta_qv|=4.58875e-5 kg/kg dry air`. The posterior was bound to the cold
checkpoint, geometry, valid time and captured host-f32 moist-theta coordinate.
The updated prognostic source is `THM_2` plus `QVAPOR`; NetCDF `T` is a
diagnostic dry potential temperature.

Probe/control comparisons covered all 652 fields (322,426,586 numeric values)
at both saved times. At 00:00:20, 48,264 numeric values differed across 136
fields; at 00:00:40, 238,989 differed across 153 fields. Both outputs were
finite and complete. These are expected differences between the T/Q probe and
its empty-control baseline, not a pass/fail comparison between the two states.

At the first MP137 call, all 39 levels changed in TH, QV, DEN, PII, P and DELZ;
maximum absolute differences were 0.527313 K, `4.35878e-5` kg/kg,
`5.52177e-4` kg/m³, `9.59635e-5`, 11.046875 Pa and 1.125977 m. At the second
MP137 call, all 39 levels also changed in these inputs; maxima were 0.498199 K,
`4.18350e-5` kg/kg, `4.77344e-4` kg/m³, `5.63860e-5`, 9.074219 Pa and
0.975586 m. The second command was empty, so this shows that the first-step
state reached the following MP call without another T/Q increment.

Each case's finish replay covered 78 level-step samples and 312 trace records,
with zero arithmetic and packing mismatches. Finish-to-checkpoint comparisons
had 312 comparisons per case and zero mismatches for the recorded state and
tendency fields. In the probe, second-step finish changed H rate at 11 levels
(maximum `2.11078e-4 K s-1`) and QV rate at 5 levels (maximum
`5.62854e-8 kg kg-1 s-1`). There was no direct H control. T/Q state and
retained tendency memory evolve together in this two-step experiment; the
separate causal contribution of the H memory was not isolated.

The saved posterior is unaccepted and nonconverged. It updates one column and
39 levels. QV increments are external water sources; no global water/energy
budget, equilibrium, or conservation certificate was evaluated. This is not a
new observation, RTTOV, optimizer, full-host derivative, or cycling-skill run.

## Source guards and verification

The origin-bound replay input guard rejects case-insensitive collisions with
runner-owned `native_trace.hex`, `transition.json`, `namelist.output`, and the
`prefix_compare_*` output family before staging or launch. `namelist.output` is
also a WRF output written with replacement semantics. Synthetic regressions
cover eight exact/mixed-case names and assert no runner call, no staged case,
and unchanged caller-owned asset bytes. The live stepper also reserves its
`validation` child-work directory: exact and mixed-case collisions are refused
before case creation or child launch. The Fortran T/Q preflight rejects
negative old QV even if a positive increment would make the new value
nonnegative; its standalone regression confirms rejection before
acknowledgement or partial application.

Final local verification: **2,490 passed, 59 skipped, 309 deselected** in the
full harness suite (142.20 s), including the final output-name variants. The
seven focused native test files passed **183 tests** (27.46 s). Undefined-name
lint and `git diff --check` passed. The default run excludes the 309 local-marked
tests; unavailable dependencies account for the skips. The active host tree is private
and absent from the public graph; host-path claims were checked against active
source and run receipts, not private-host AST coverage.
