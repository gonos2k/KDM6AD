# Isolated mp237 short native trajectory and measured ice transfers

## Outcome and limits

The existing opt-in Fortran conservative variant (`mp_physics=237`) completed
40 seconds on the retained 5-km input with 39 mass layers, dt=20 s, one MPI rank
and one thread. Its separately built read-only capture variant produced the
same history bytes. This is a coupled native host trajectory, not only a local
Python/C++ substep. It is **not mp337, mp137 ABI validation, operational adoption,
physical number-unit resolution or whole-model positivity approval**.

The same column 35711 is retained (zero-based j=152, i=143; Fortran 153,144).
At its second ice call, native layer 24's actual number departure is 436223.375.
The layer-23 arrival reconstructed in source binary32 order is **432432.1875**,
and the independently captured receiver post-state is exactly reproduced.
The value differs from PR232's 432462.810639 local calculation because the
conservative full trajectory has already changed its state and geometry.
These are deliberately not presented as identical-input substep results.

Operational legacy transfer **P1 remains OPEN**. The raw first-ice velocity
handoff is preserved by this existing variant; its physical normalization is
still unresolved. No default, physics formula, ABI, QC or tolerance changed.
Liquid observation approval remains 0/9; there was no RTTOV execution.

## Execution, source scope and failed attempts

Three native model integrations completed: one exploratory direct launch saved
only the initial history frame, then standard-runner control and capture runs
saved 0,20,40 seconds. Only the latter two support trajectory/noninterference
claims. Two additional starts did not reach a useful model integration: one
stalled in MPI_Init/PMIx connection (sampled and terminated), one rejected a
loopback interface unavailable to PMIx. Explicitly selecting available `en8`
for PMIx/PRTE resolved startup. These failures are not scientific runs.

Both accepted runs use the repository runner:

```
harness/run_ss_case.py --mp 237 --minutes 0 --seconds 40 --history 0 \
  --history-s 20 --np 1 --fixed-dt --proc-grid 1x1 --case <isolated case>
```

Only `mp_physics` differs from the retained mp37 namelist. Active input hash
records match. The capture/control namelists and active input records match
exactly. Run validity records both report completed/valid with a 1x1 grid.
The current conservative microphysics module was freshly compiled with
`-ffp-contract=off`, RWORDSIZE=4; existing other host objects/libraries were reused.
It is not a clean rebuild of the entire host. The canonical installed executable
and archive hashes retain their prior identities. Commands and hashes are in
`conservative_native_2026-09-21.json`.

The historical source-scope checker **does not pass its old legacy SHA pin**.
Its four exact permitted edit clusters and both raw-handoff blocks do match.
The failure is retained verbatim in the evidence; no pin or assertion was
weakened. This establishes the current pair's structural difference, not a
successful historical freeze certification.

## Noninterference

Read-only capture additions strip back to the exact canonical conservative
source. Work arrays are recorded as binary64; state/geometry stores as binary32.
At each of the three frames all **253 numeric variables plus `Times`** match
raw bytes, with identical variable sets/shapes/types. The complete history
files also share SHA-256:

`7d2afb3236ea6ea53a1df5c75f17b2b1da27f963ace697a8a912eda871c0f750`.

This exact count is 254 total variables, not 254 numeric variables. The
comparison is within mp237. Legacy-versus-conservative differences are expected
and are reported separately, never tested as a bitwise acceptance condition.

## What was measured and what was reconstructed

There are 156 records: two calls × 39 layers × before/after. Each records qi,ni,
work1,workn,rho,dz,dt,mstep and, after update, the actual capped departures and
stored upper-layer departures. **Receiver arrival is reconstructed**, not a
separately instrumented temporary: the source has no such stored temporary.
For number it is `f32(f32(upper_departure*upper_dz)/dz)`; for mass it uses
source-rounded `rho*dz` metrics. Applying that arrival to the separately captured
pre-state and departure reproduces all 156 qi/ni post values exactly.
Upper departure records must equal the adjacent donor's stored departure.

The conditional measures remain dz for number and rho*dz for qi. In the table,
relative interface residual is (arrival−departure)/departure; storage rounding
is kept separate. No physical number unit is inferred from small residuals.

| Call | Field | Internal departure | Relative interface residual | Bottom outflow |
|---|---|---:|---:|---:|
| 1 | qi | 0.09779185748 | −3.5090103e-8 | 1.9147461e-15 |
| 1 | ni | 0 | undefined (zero transfer) | 0 |
| 2 | qi | 0.007810332489 | +3.8117381e-8 | 0 |
| 2 | ni | 415470113.8004 | +3.7711410e-8 | 0 |

Call-2 number inventory change is +15.6679638332 in the declared measure;
interface mismatch is +15.6679638028. This is binary32 residual, not exact
real-arithmetic conservation. The signed budget closes to 3.04e-8 absolutely
(about 7.3e-17 of the internal departure). Other signed residuals are smaller.
Call-1 has nonzero qi transfer while its ni transfer is zero; this is not a
certificate of physically admissible moment pairs. The tiny measured qi
bottom export is not a representative precipitation/number outflow case.

## Coupled trajectory changes and positivity limitation

All 253 numeric fields are finite at the three frames. Relative to mp37,
changed numeric-variable counts are 0,74,93 at 0,20,40 s. Selected-column maximum
absolute differences at 40 s include:

| History variable | Maximum absolute change over 39 layers |
|---|---:|
| QICE | 1.28349484e-5 |
| QNICE | 325562.453125 |
| QRAIN | 2.38482971e-6 |
| QNRAIN | 20.4250488281 |
| QCLOUD | 1.31900248e-4 |
| QNCLOUD | 292600064 |
| T (perturbation potential temperature) | 0.0287170410 K |

These are changes between coupled numerical trajectories, not forecast error
or evidence of better meteorology. The variant changes main-chain transfers
as well as ice transfers, so the table is not ice-only causal attribution.
Mass/number units retain the unresolved host/kernel contract. Size and fall
speed can feed back; physical effective-size accuracy was not independently
measured. Full selected-column arrays and domain extrema are public in the JSON.

The five hydrometeor mass fields are nonnegative throughout saved frames.
**Whole-host number positivity does not pass**: at 40 s both tracks contain
small negative number values. No clipping or omission is applied here.

| Variable | Legacy negative cells / minimum | Conservative negative cells / minimum |
|---|---:|---:|
| QNCLOUD | 3 / −0.0007976927 | 4 / −0.0285397433 |
| QNRAIN | 3 / −2.1558991e-8 | 4 / −3.7787910e-8 |
| QNICE | 4 / −4.8991808e-7 | 3 / −7.1682134e-6 |

Their origin is not localized to microphysics versus later host transport by
this capture. Therefore local nonnegative ice updates and small paired-transfer
residuals do not close full-host positivity. QIB also has tiny negative saved
values in both tracks. Negative T is not treated as a positivity failure since
T is a perturbation variable.

## Reproduce and remaining gates

```
python3.12 harness/replay_conservative_native.py
python3.12 -m pytest oracle/tests/test_conservative_native.py -q
```

Eight focused tests pass: real measured updates/budgets plus seven missing/changed
record, run/source evidence or approval mutations. They replay public arithmetic; they do not build
or run the private host or authenticate its original files.

This closes the narrow missing **isolated mp237 40-s trajectory measurement**.
It does not close operational P1, raw-handoff normalization, physical number
basis, full-host positivity, meaningful number surface export, coupled time
convergence, mp337 ABI validation, or independent radiation accuracy. The formal
frozen-coefficient curves are described separately in
`REPORT_ice_time_accuracy_2026-09-20.md`.
