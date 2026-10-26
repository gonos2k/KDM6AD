# Measured upstream QNC update in one full-domain host step

Base: main `6787d3c926981e603de6585caae50407ac2c7fd0` / PR455. The
model advances the complete 234×282 native domain independently from the
same 00:00:40 READY checkpoint to 00:01:00. New value-only records cover two
selected columns and levels. There is no new RTTOV evaluation, optimizer call,
or assimilation cycle in this experiment.

## Executed forward and source identity

Four actual 20-second steps were completed: control trace-off, control
trace-on, alpha0.25 trace-off, and alpha0.25 trace-on. The first is the
completed V4 result; the remaining three use a V6 run controller and the
**same V4 executable**. Together these steps include eight KDM wrapper
entries. They do not form a four-step forecast. The superseded V5 plan was
never run, and a V4 control trace-on prelaunch path failure started no model.
The [prelaunch history](receipts/prelaunch_history.json) keeps those attempts
separate from the four completed steps.

The V4 executable is SHA-256 `59512e7f3b2e6dfc3887e9ce7497fabafd64d87599d136e5cbd2c6d92b8326a6`.
Its archive changes only `solve_em.o` relative to the prior V3 diagnostic
build. The source-pinned solve overlay changes observations and file output,
not the numerical statements. The existing KDM Fortran/C++ `-ffp-contract=off`
contract and the original solve compiler flags are retained. Runtime
`namelist.output` in all four runs reads `MP_PHYSICS=137`,
`NO_MP_HEATING=0`, `USE_THETA_M=1`, `USE_Q_DIABATIC=0`, RRTMG LW/SW=4/4,
PBL=11, CU=37, and `MP_ZERO_OUT=2`/`MP_ZERO_OUT_ALL=0`.
The [redacted build receipt](receipts/private_build_redacted.json) and
[execution-source snapshots](execution_sources/) retain the compiler, object,
archive, executable, DSO and controller identities. The unredacted build
receipt SHA remains in the execution summary.

Each same-case trace-off/on pair has byte-identical ACKs and a raw-bit match
over **652 checkpoint variables and 322,426,586 numeric elements**. The
endpoints also match their historical V3 control and alpha0.25 results:
control SHA `225d2cabe8a4…`, alpha0.25 SHA `77be4282ef36…`. Each trace-on run
contains 206 QNC operand/state records. The new `PRE_MICROPHYSICS` word equals
the same run's earlier V2 `MP_INPUT` word for both selected targets.
See [execution summary](receipts/execution_summary.json).
The [validation record](receipts/validation.json) distinguishes actual host
calls, offline replay checks and local tests.

## First signed change at the valid READY witness

The first target is native one-based `(i,j,k)=(221,63,6)`. QNC is printed in
the legacy raw coordinate; its physical unit is not certified by this trace.
Both cases start from the same READY40 QNC **13,605,366** (hex `4B4F99F6`).

| QNC state | Control | Alpha0.25 |
| --- | ---: | ---: |
| After ordinary RK stage 1 | +3,424,469.25 | +3,424,466.5 |
| After ordinary RK stage 2 | −1,918,020.375 | −1,917,976.75 |
| After final positive-def preparatory update, `scalar_old` | +22,714,292 | +22,714,292 |
| After ordinary RK stage 3 / before KDM | **+3.4425406456** | **−3.8143992424** |

The final ordinary RK update is the **first measured boundary where the two
cases have opposite NC signs**. Both have a negative intermediate stage-2
state, then the positive-def preparatory update supplies the same
`scalar_old` for stage 3. At stage 3, the recorded `SCALAR_TEND` is zero.
The control and alpha0.25 combined RK tendencies are respectively
`−102,553,681,920` and `−102,553,714,688` in the recorded mass-coordinate
arithmetic, a difference of `−32,768`. With `DT_RK=20`, the rounded
`dt*tendency` term differs by `−655,360`. The old-state mass factor and
`scalar_old` are identical; the actual numerator changes from
`+310,889.0625` (hex `4897CD22`) to `−344,470.9375` (hex `C8A832DE`).
The resulting NC words are `405C5296` and `C0741F1E`.

This is an **applied state-update explanation** of the sign change. The
source-order binary32 replay using an exact FMA contraction candidate reproduces
both output words exactly. The compiler instruction sequence was not separately
recorded. This result does not apportion the earlier `ADVECT_TEND`
between named transport/mixing suboperators or certify a physical number
budget. A source-level `POSITIVEDEF` selector alone did not guarantee that
the final stored QNC stayed nonnegative in this execution.

The second target `(91,94,4)` begins with QNC=0 and QC>0. It is an inherited
QC–NC mismatch, not a newly valid pair that fails. Its final RK numerator is
`+2,115.96337890625` in the control and `−16,316.037109375` in alpha0.25;
the resulting QNC values are `+0.02228504047` and `−0.17183831334`.
For both targets, the negative alpha0.25 `PRE_MICROPHYSICS` word equals the
actual f32 KDM input word. The existing KDM zero clamp then returns NC=0
while QC remains positive at these witness levels. The earlier
[fixed-support trial audit](../native_full_physics_trials_2026-10-25/README.md)
established the profile failures and alpha0.25 inadmissibility; this packet
does not repeat RTTOV quality screening.

## Public arithmetic replay and limits

From the repository root, with NumPy installed:

```sh
python3 -m harness.evidence.native_upstream_nc_2026-10-26.replay
```

The replay verifies nine asset sizes and SHA-256 hashes before parsing saved
traces and context arrays. It validates stage coverage/order, separately
replays the positive-def preparation and ordinary RK updates, checks exact
binary32 operation candidates, and links pre-microphysics values to the
same-run KDM input. Its stdout is byte-identical to [analysis.json](analysis.json)
(SHA-256 `29119dc2d00cd90b14662065aaa507d1a16f2757ecad9b7ef6609a8f45273d10`).
The replay itself makes zero model calls; the four actual steps are recorded
in the [execution receipt](receipts/execution_summary.json).

The executed step-control hook was in a private compiled snapshot of
`mediation_integrate.F`, which directly applied T2/QV only. The canonical
active host source does not contain that experimental hook. The two-step
state/cost cycle remains incomplete: alpha0.25 is still inadmissible on the
fixed observation support, so no candidate RTTOV cost or second assimilation
was computed here. The source-side attribution of the large combined RK
tendency to a particular named process and any physically justified repair
require a separate budget review. No NC floor or observation mask change was
introduced.

The small integer-metadata fix to the older PR455 replay is documented
[separately](../native_qc_nc_replay_metadata_2026-10-26/README.md), with its
historical source hashes preserved.
