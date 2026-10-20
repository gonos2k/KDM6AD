# Native MP137 transition and prefix replay

This note records a bounded native-forward validation and the value-only
restart-prefix adapter now in the public tree. Two final 40-second prefix runs
completed from 120 to 160 seconds: a baseline and a one-element `H_DIABATIC`
probe. Neither is an assimilation run or a full-host derivative result.

## Scope and attribution

The native case uses the existing 5 km input on a 234 × 282 grid, with 39 mass
levels and 40 interface levels, `mp_physics=137`, fixed `dt=20 s`, one MPI rank,
and one thread. The earlier replay campaign covers 0–240 s (12 steps); this
boundary-trace campaign starts from its 120 s checkpoint and targets 160 s (two
steps). No external model data were acquired or substituted. Inputs, source
snapshots, executable/library receipts, and comparisons are local-only under
`host/research_evidence/mp137_native_transition_20261020/`.

The P2 review fixes have distinct scopes:

1. `harness/native_replay_compare.py::compare_frames` now requires a real
   character `Times` variable containing the `Time` dimension and validates each selected
   frame against the expected timestamp. Numeric `Times` and missing `Time`
   axes cannot pass as a valid WRF frame comparison.
2. `harness/patch_restart_state_init.py` now matches complete active code
   lines/blocks instead of counting/replacing substrings. Old or patched code
   appearing only inside comments cannot report `applied` or `already_applied`.
   Ambiguous or changed contexts refuse before either file is written.
   The intended restart initialization patch is unchanged byte for byte; its
   physical scope remains in [`NATIVE_MP137_REPLAY.md`](NATIVE_MP137_REPLAY.md).

The host executable is not a clean source rebuild. The isolated variant
recompiled two host objects in a 377-member helper archive; the reference archive
has 376 members. The KDM library remained the installed library, with a
load-only DYLD receipt. Treat this as evidence for these attributed binaries and
inputs, not general source/build equivalence.

## Controls and restart-chain result

Three separate 160 s control comparisons pass raw-bit equality for all 652
checkpoint variables: the boundary/recompile control, trace compile
off/on control, and trace runtime off/on control. The corresponding local
receipts are `BOUNDARY_RECOMPILE_NONINTERFERENCE_160.json`,
`TRACE_COMPILE_NONINTERFERENCE_160.json`, and
`TRACE_RUNTIME_NONINTERFERENCE_160.json`.

In the initial direct split-restart chain (using the already fixed restart
initializers), the 120→140 s checkpoint matched
all 652 fields. The 140→160 s comparison then differed in 1,385 values across
13 fields: `PH_2`, `QCLOUD`, `QC_DIABATIC`, `QIB`, `QICE`, `QNCLOUD`, `QNICE`,
`QSNOW`, `U_2`, `V_2`, `WW`, `WW_M`, and `W_2`. All values were finite and
present; this is a raw-bit failure, not a missing-data result. The detailed
receipts are `FORWARD_WINDOW_REPLAY_140.json` and
`FORWARD_WINDOW_REPLAY_160.json`.

A separate load-only restart at 140 s wrote a checkpoint with all 652 fields
bit-identical to its input and executed zero model steps. Its expected return
code was 14. That result confirms serialized-field preservation during this
load-only path; it does not show that the subsequent integrated step matches.
The seven entry-history diagnostics in
[`NATIVE_ENTRY_DIAGNOSTIC_CONSUMERS.md`](NATIVE_ENTRY_DIAGNOSTIC_CONSUMERS.md)
remain a separate history-output coverage limit.

## Final origin-bound prefix results

The final baseline and one-element `H_DIABATIC` probe each completed two
20-second `HostForwardWindow` transitions from the 120 s origin checkpoint
through 140 s and 160 s. The final baseline outputs at both times match the
independent contiguous run by raw bits in all 652 checkpoint variables:
322,426,586 numeric values compared per timestamp, zero mismatches, finite and
complete. The baseline and H-probe prefix replay's intermediate 140 s
checkpoint comparisons also pass for all 652 fields.

The prefix audit compares checkpoint metadata as well. After normalization,
there are no metadata differences; the only two recorded normalizations are the
integer-Boolean global attributes `WRF_ALARM_ISRINGING_01` and
`WRF_ALARM_ISRINGING_07` for history and auxhist6 output. The run uses
`override_restart_timers=true`; no prognostic fields, forcing inputs, or other
metadata are normalized. Private
receipts are `FINAL_BASELINE_FORWARD_WINDOW/FINISHED.json`,
`FINAL_H_PROBE_FORWARD_WINDOW/FINISHED.json`, `FINAL_PREFIX_REPLAY_7.json`,
`FINAL_PREFIX_REPLAY_8.json`, and the public
[`native_forward_summary.json`](../harness/evidence/native_mp137_transition_2026-10-20/native_forward_summary.json)
and [`REPORT.md`](../harness/evidence/native_mp137_transition_2026-10-20/REPORT.md).

This evidence covers the baseline's two tested intermediate times and the
probe's origin-bound prefix self-replay over this 40-second window. It does not
prove all restart boundaries, longer-window replay, or arbitrary updated-state
injection. In particular, the accepted-analysis state-carry loop below remains
unimplemented.

## Selected-column tendency/forcing trace

At the selected native column `(i=156,j=21)` and 39 levels, the final
origin-bound baseline/probe traces and independent contiguous reference each
contain 78 level-step samples for steps 7 and 8 (312 records per two-step
execution). Baseline and reference trace records are identical; all three have
zero compiler-profile arithmetic and pack-to-finish replay mismatches. The
probe changes one saved `H_DIABATIC` value at zero-based NetCDF
`(k=5,j=20,i=155)` at 120 s by binary32 approximately `0.001 K s-1`. This is a
value-only intervention, not an optimizer control or derivative test. The
probe-minus-baseline forcing changes show that the memory perturbation reaches
later MP137 calls at this sampled column:

| Call | DEN (kg m⁻³): levels; max absolute difference | PII (1): levels; max absolute difference | P (Pa): levels; max absolute difference | DELZ (m): levels; max absolute difference |
|---|---:|---:|---:|---:|
| 7 | 24; 6.93798e-5 | 24; 2.55704e-5 | 24; 8.640625 | 22; 0.0108643 |
| 8 | 30; 1.35899e-5 | 30; 5.00679e-6 | 30; 1.6640625 | 21; 0.00341797 |

These forcing values are reproduced in the final origin-bound probe trace. The
full-grid baseline comparisons pass at 140 s and 160 s, but this single-column
probe does not test the whole-grid response to the `H_DIABATIC` perturbation.
The trace metrics are in `trace_metrics.json`; units are declared there as
`DEN=kg m-3`, `PII=1`, `P=Pa`, and `DELZ=m`. The KDM/wrapper
`-ffp-contract=off` setting remains in place; the host finish keeps its O2/FMA
profile. The trace checks value arithmetic only. It does not prove a mass/energy
conservation budget, a derivative, or agreement at every column.

## Current origin-bound prefix adapter

`harness/native_host_transition.py::NativeHostTransition` provides a
value-only native step contract over complete, hash-bound NetCDF checkpoints.
It pins the fixed external inputs, executable, library candidate, and runner.
For step `n`, it restarts from the original trial checkpoint and integrates the
whole prefix through step `n`; it then raw-bit compares every prior checkpoint
in that prefix before returning the next state. This is an origin-bound replay,
not a direct one-step continuation from the intermediate NetCDF file. A new
trial must start from its original checkpoint. Intermediate analysis
increments and changes to prescribed inputs within a prefix are not
supported.

Calling this adapter for every step of an N-step window executes prefixes of
length 1 through N, so total integration work grows as O(N²). This trades
runtime for explicit verification that a restart boundary reproduces the
origin's earlier checkpoints. All variable attributes and global attributes
are checked, except the two recorded Boolean ringing-bit normalizations for
output streams 1 (history) and 7 (auxhist6). With
`override_restart_timers=true`, the active `share/input_wrf.F` skips restoring
these output alarms; no boundary, input, prognostic or other metadata is
normalized. The final 40-second baseline and probe receipts are complete; the
verified domain and window limits are stated above.

The generic `HostForwardWindow` and `CoupledHostWindow` are separate contracts.
Their toy-model derivative tests do not certify a native derivative backend.
`NativeHostTransition.vjp()` and `.jvp()` explicitly refuse use: full-host JVP,
VJP, pressure-aware observation closure, observation assimilation, and an
optimizer remain open work.

## Intended one-step state-carrying analysis loop (not implemented)

The requested operational loop is stateful across accepted model steps. The
complete, balance-adjusted host state produced for the next step becomes that
step's initial state; each new step must not restore the same original
background. Inner optimizer trials remain different: every rejected or
line-search trial starts from the same current analysis state, and only the
accepted balanced state is carried forward.

For one accepted loop step, the intended contract is

```text
X_n_analysis = balance_full_host(X_n_prior, increment_n)  # apply once
X_(n+1)      = WRF_MP137_one_step(X_n_analysis, external_n, dt)
X_(n+1)_init = X_(n+1)                                   # carry full state
```

`WRF_MP137_one_step` must execute the native tendency path: current T/Q and
hydrometeors prepare the forcing (including derived pressure, density, Exner,
and layer thickness); MP137 writes its updated state; the host applies the
resulting thermal/moisture tendencies through its normal RK and dynamics
sequence. The next loop receives the full saved state, including U/V and the
retained tendency memory needed by the host. It recomputes state-derived
forcing from that state. It does not add the prior KDM increment again outside
the host integrator. The `H_DIABATIC` prep/finish reuse and its actual later RK
consumption remain governed by the native phase order documented in
[`COUPLED_MP137_DA_DESIGN.md`](COUPLED_MP137_DA_DESIGN.md) and
[`NATIVE_MP137_REPLAY.md`](NATIVE_MP137_REPLAY.md).

This desired loop is not implemented by the current PR backend. Its
`NativeHostTransition` is an origin-bound, fixed-input value reference: it
replays prefixes from one trial origin, verifies earlier checkpoints, and
rejects intermediate analysis increments. That reference does not provide the
stateful accepted-analysis handoff above. A future backend needs a validated
complete-state encoder/balance operation, an explicit accepted-state checkpoint
boundary, and a native one-step transition that consumes that state without
reinitializing it from the original background.

The clock policy is still open. Carrying the full state is required either
way, but the run must explicitly choose whether each model step advances valid
time by `dt` or whether another analysis/iteration is evaluated at the same
analysis timestamp. No timestamp or observation-window policy is inferred
here; the asynchronous clarification must resolve it before implementation.
