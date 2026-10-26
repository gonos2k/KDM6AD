# Interim full-physics control and checkpoint-observation pilot

**Status:** control and T/Q candidate full-host steps from the same exact
post-LBC ready state are complete, and independent saved-field arithmetic has
passed. Four direct-RTTOV control-pilot blocks also passed. Candidate physical
interpretation, candidate RTTOV, and the remaining 125 observation blocks are
pending. This is an interim snapshot, not a completed paired observation-cost
or full-domain result.

## Completed control

The control ran one real host step from model time 00:00:40 (step 2) to
00:01:00 (step 3), with no new T/Q analysis rows at the 40 s boundary. The
40 s origin restart contains a prior unaccepted single-column KO7 diagnostic
T/Q update; “no-analysis control” means no *new* update for this step, not a
pristine initialization. The post-LBC ready capture differs from the origin
in one serialized marker, `WE_JUST_D01_LBC` changing 0 to 1; this documents LBC
input, not by itself a control/candidate match. The candidate ready comparison
now shows the same SHA-256
`0c4836a2a44531c98d38d3ded15cab5048679b1139f3e4fd96fb62eff84bfad3`, with all
652 serialized variables and 322,426,586 numeric elements equal bitwise and
zero mismatches. This establishes a common pre-command state. The candidate
C1 command ACK passed with 561,407 applied rows, 855,443 changed components,
zero remaining requested no-op pairs and 2,012,125 empty points. The candidate
host step completed at 60 s / step 3 with output checkpoint SHA
`ff3c101e3b352594471ac5dfd0daab07c0daff3b6d406c88e2461283389978b5`. The
private candidate receipt is status `CANDIDATE_STEP_COMPLETE`. A separate
offline audit now verifies the full serialized comparison and selected field
arithmetic. It does not provide a physical-process attribution or budget
closure.

The candidate runtime audit records a valid one-step host exit, the expected
loaded private DSO, selectors `norm_actual`/`actual_departure`, and two internal
tile calls for LW/SW radiation, Noah, Shin-Hong PBL, KSAS and KDM6AD. This is
execution-path attribution only; candidate RTTOV and independent field
interpretation remain pending.

The control used the explicit `kdm6_native_fp64_value_c` entry with
`norm_actual` and `actual_departure`. Its 12 REAL4 state and 4 REAL4 forcing
inputs were widened for the selected FP64 KDM map, and outputs returned to
REAL4. The other host physics ran in the configured REAL4 path. The operational
`kdm6_step_c` and install were not changed. The linked private DSO and host
executable are hash-pinned in `interim_snapshot_manifest.json`.

The recorded namelist gate was `mp_physics=137`, `NO_MP_HEATING=0`,
`USE_THETA_M=1`, `USE_Q_DIABATIC=0`, RRTMG LW/SW 4/4 with `radt=1/3` minute,
surface physics 2, PBL 11 and cumulus 37. Logs show two calls total across two
internal tiles to each of LW, SW, Noah, Shin-Hong PBL, KSAS and the KDM6AD
wrapper; outer radiation/PBL/cumulus/finish drivers ran once. This was one
control step, not a paired analysis response.

The full 234×282×39 saved state has 65,988 horizontal columns, including the
lateral-boundary ring. The direct MP crop was 64,960 interior columns; the
outer 1,028 columns remain in the full host checkpoint/output.

## Whole-host endpoint tendency audit

The read-only audit computes `(output60-ready40)/20 s` for six saved fields
over 2,573,532 cells per field. The statistics are unweighted elementwise
whole-host responses, including dynamics, LBC and all active physics; they do
not isolate KDM or close a physical budget.

| Field | Endpoint-change rate units | Mean | Range |
| --- | --- | ---: | ---: |
| `THM_2` | K/s | -5.994e-5 | -0.124020 to 0.224591 |
| `QVAPOR` | kg kg-1 s-1 | 1.013e-8 | -5.060e-5 to 1.758e-5 |
| `QCLOUD` | kg kg-1 s-1 | 8.181e-9 | -4.039e-5 to 5.188e-5 |
| `QICE` | kg kg-1 s-1 | 1.702e-9 | -2.711e-5 to 4.062e-5 |
| `QSNOW` | kg kg-1 s-1 | -1.502e-9 | -1.378e-5 to 4.250e-5 |
| `H_DIABATIC` field change / 20 s | K s-2 | -2.441e-6 | -0.006549 to 0.005251 |

`THM_2` is moist-potential-temperature perturbation, not actual temperature;
no `T` reconstruction was performed because the exact constant contract for
that endpoint is unavailable. `H_DIABATIC` change divided by 20 s is K s-2,
not a temperature tendency, MP heating rate or sum of all host heating.
`NO_MP_HEATING=0` enables the MP thermal preparation/finish path; it does not
disable other nonadiabatic schemes. `USE_Q_DIABATIC=0` disables only the extra
RK QV/QC diabatic add/subtract, not MP water updates or latent heating.

The V2 audit made no model calls and reproduces all six V1 metrics exactly. Its
audit SHA-256 is
`68ffd56ce031efba2052bb23dbcfda2596a4ccd91b2205f2ba453a4afedd7ece`, producer
SHA-256 `063af5168c28a21e175ed7875bcb7dcda3c570bddd05ee2d62deef7e98aaed9b`,
and summary SHA-256
`2eb01f33f26de5c8dbb395051d16ff1dd8c63453ca832c7b903c5e8cc666db6e`. V1
remains preserved as an earlier audit source/result.

For the control/candidate output pair, the corrected v2 summary SHA-256 is
`5ca7bfa824c2cb952117cda2c2d3844d130080e5b1a85174bb060778e9d2d742`. The
independent arithmetic review status is `SAVED_PAIR_ARITHMETIC_REVIEW_PASS`;
its result SHA-256 is
`645d25695454d586437c684fdf3a3c11e9f30aee6190501ad71db7239610119d` and its
producer SHA-256 is
`c1b88f8b8a5e6cb81fa665d461f1b0f998481a44d5c774443eccfa8d8beb729b`. It
rechecked 652 variables and 322,426,586 numeric elements, including 26,454,541
raw value differences, and independently reproduced all 13 selected-field
change-count/max/fsum metrics.

The READY40 analysis-input QV diagnostic is `25,669,966.556135986 kg` signed
added water using READY40 dry density, reconstructed DELZ and AREA2D. This is
an analysis-input-only diagnostic, not a closed full-step water budget. The
paired output summary is redacted into the interim packet; no raw restart or
large state arrays are published.

The v2 summary describes WRF `T` and `THM_2` as perturbation-potential-
temperature coordinates; actual physical temperature is not reconstructed.
The independent arithmetic review validates saved values and aggregation only;
it does not certify a KDM process cause, mass/energy closure, cloud truth or
forecast efficacy.

## Four-block checkpoint-to-RTTOV pilot

The pilot used the actual 60 s output checkpoint directly, with no extra MP,
cleanup or finish call. It processed original observation-package chunks
0, 34, 40 and 128: 1,988 source columns and four direct RTTOV calls
(`do_direct=true`, `do_k=false`). Nine recorded profile fields matched their
preflight values. Fresh control-derived `M_host0` contained 8,218 channel cells;
the previous microphysics-only support count was not reused. The source scene's
nominal/header time is 00:00 UTC; the same-slot 00:00:33 value is only a header
cross-check, and pixel-specific UTC is unknown. No time resampling is claimed.

This pilot does not complete C7's full-domain checkpoint-to-RTTOV assessment,
produce a full-domain cost or gradient, or validate a candidate/control
difference. It evaluated only the control output checkpoint; candidate RTTOV
remains pending. At this status snapshot the other 125 observation chunks
remain in progress.

## Separate bridge gate and open claims

The C API precision-boundary gate v2 covers three input cases (block34 B512,
block40 B512, nonsquare 2×4). Arithmetic/ABI checks pass. Cumulative
accounting records 22 positive-dt requests (including prior requests and saved
direct-runtime references), 12 fresh completed C API forwards, four dt=0
identities and nine refusal entries. The FP-environment capture for block34
is unavailable; it remains unclaimed. The gate made no host or RTTOV calls.

The paired host value executions and independent saved-field arithmetic review
are complete, but the candidate RTTOV/observation-cost evaluation, C4 v6
effective-direction calls, fixed-prior optimizer iteration, full-host gradient
and cloud-efficacy claim are not complete. The prior
requested-direction joint33 failure belongs to that older continuous vector
and is not C4 v6 evidence. No operational REAL4 physics parity or full-host AD
is claimed.

The redacted metadata receipts and interim hash/source manifest are provided
beside this report. Full restart/checkpoint files, raw host streams, private
executable/DSO copies and large profile/RTTOV arrays remain in the private host
evidence tree. The compact public copies do not independently reconstruct the
full host execution.
