# Paired native full-physics forward before broader analysis claims

> **Historical status:** the body below is the H1 plan/audit at UTC 2026-10-25 13:23:54. Its pending/unlaunched statements describe that cutoff. For current results and open work, use [the current progress record](NATIVE_ANALYSIS_PROGRESS_20261025.md).
> Original source bytes and historical manifest pins are preserved in the [H1 source-resolution record](../harness/evidence/native_full_physics_forward_2026-10-25/historical_source_resolution.json).

## Historical H1 snapshot

## Priority and scope

The paired full-host value-forward execution is complete for control and T/Q
candidate: both independent sessions started from the same 40 s origin, passed
through initialization/LBC, matched across all retained ready-state values, and
ran one 20 s solve to 60 s. The configured path included every enabled
nonadiabatic process. Independent paired saved-field arithmetic review now
passes; candidate physical interpretation and direct checkpoint-to-RTTOV remain
pending before paired `J_host` or efficacy claims.
The four-column effective-direction test and fixed-scene optimization remain
separate, incomplete work.

The host clock advances from 40 s to 60 s. This is one physical timestep used
to diagnose an analysis response for the intended scene; do not retimestamp the
60 s output as a fixed-time state. It is not an unattended forecast cycle or
an optimizer iteration. The microphysics-only `g_micro` is a
partial/surrogate sensitivity through the KDM/cleanup/finish and observation
path. It is not a certified full-host `g_host`; a full-host derivative is not
implemented.

## Configuration that the run must retain

The bounded saved-DA reference run used the following values; the new run must
pin and report its own effective namelist, restart metadata, executable and
library rather than inheriting values by assumption. These selectors were
verified against that saved run's actual namelist. The previous measured call
counts and cadence are summarized in
[`native_state_carry`](../harness/evidence/native_state_carry_2026-10-20/REPORT.md)
and its [compact receipt](../harness/evidence/native_state_carry_2026-10-20/summary.json).

| Component | Required value for the paired run | Meaning |
| --- | --- | --- |
| Microphysics | `mp_physics=137`, `NO_MP_HEATING=0` | Native KDM6AD dispatch with MP heating enabled |
| Thermal coordinate | `USE_THETA_M=1`, `USE_Q_DIABATIC=0` | Prognostic `THM_2` is moist-theta perturbation; QV/QC tendencies are not separately added to RK |
| Radiation | longwave `ra_lw_physics=4`, shortwave `ra_sw_physics=4`, `radt=1/3` minute, `STEPRA=1` | RRTMG calls on this 20 s cadence |
| Surface layer / land / urban | `sf_sfclay_physics=1`, `sf_surface_physics=2`, `sf_urban_physics=1` | Keep the configured surface schemes active |
| PBL | `bl_pbl_physics=11`, `STEPBL=1`, `bldt=0` | Shin-Hong PBL on the selected cadence |
| Cumulus | `cu_physics=37`, `STEPCU=1`, `cudt=0` | KSAS cumulus on the selected cadence |
| Integration | 20 s, domain 1, one MPI rank, one thread, two internal tiles | Match the bounded native reference execution shape |

The earlier saved-DA case measured two calls total across the two internal
tiles for each of RRTMG longwave, RRTMG shortwave, Shin-Hong PBL, KSAS, and
MP137; its outer PBL, cumulus, and microphysics drivers ran once. Those
measurements are a reference for attribution, not evidence that this new paired
run has already executed. Record the actual per-run calls and all selected
options.

## Explicit KDM precision boundary

The admitted actual-QR candidate receives REAL4 state/forcing arrays at the
native Fortran ABI. The normal `kdm6_step_c` still computes in native float32.
The paired experiment instead requires the separate forward-only
`kdm6_native_fp64_value_c` symbol, compiled only when
`KDM6_ENABLE_NATIVE_FP64_VALUE_BRIDGE` is explicitly enabled in the isolated
build. This is an explicit symbol binding, not a hidden environment precision
mode. The normal public build leaves the macro off; the operational
`kdm6_step_c` body, default 14-symbol export set, packed AD signatures, and
public ISO source remain unchanged.

That entry decodes twelve REAL4 state fields and four REAL4 forcing fields,
widens them exactly to float64, evaluates the existing selected FP64 KDM map,
then writes twelve state results, three precipitation increments and RHOG back
to REAL4 once. XLAND keeps its discrete REAL4 values. WRF finish, radiation,
land surface, PBL, cumulus, dynamics, boundaries and the rest of the host
remain in the configured native REAL4 path. The bridge creates no AD handle,
packed AD field, full-host JVP/VJP, or output clipping rule.

The private build receipt records one additional experimental export and the
unchanged default export set. Its isolated DSO SHA-256 is
`6524bcfedbf75b2ebfc95e9603dd2cd702be3f213d2759bfaa571d1be5121d4e`; the
private host-link DSO copy is
`8e57e5e29112ff735e4bf2e3f5fe974b9728171fcaf5f149fda4d7f137da4e63` and its
executable is
`faf7ec5f66c89acdea20ea0cef1ca38030071020ff5ebec6f2d4b4da37291ca0`. The
private Fortran overlay binds only the ISO call to the new symbol. Its host
archive has one changed `kdm6_iso_c.o`; the other 376 members are unchanged.
The operational install is untouched. The v7 private executable loaded the
host-link DSO and completed one no-analysis control step from time 40 s to
60 s. It recorded two KDM value calls across two internal tiles, zero RTTOV,
and no AD or optimizer calls. This tests one value path, not paired candidate
behavior, bridge rejection boundaries or operational REAL4 physics parity.

The control receipt uses `norm_actual` and `actual_departure`, and verifies
`mp_physics=137`, `NO_MP_HEATING=0`, `USE_THETA_M=1`, `USE_Q_DIABATIC=0`,
RRTMG LW/SW 4/4 at `radt=1/3` minute, PBL 11, cumulus 37 and surface physics
2. Its actual per-step markers show two calls each across the two internal
tiles to RRTMG longwave, RRTMG shortwave, Noah, Shin-Hong PBL, KSAS and the
KDM6AD wrapper. The outer radiation/PBL/cumulus/finish drivers ran once.

The control's 40 s origin SHA is
`7a353f1fa4f6636864ac169c9ee8d16869d1f38c8e998762c19659404cbb9c8e`, its
post-LBC ready capture SHA is
`0c4836a2a44531c98d38d3ded15cab5048679b1139f3e4fd96fb62eff84bfad3`, and the
60 s / step-3 output SHA is
`225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070`. The
control receipt is `bb5a718a1e72373ba85bc65ff141057f560ccadfdf0d53056bdc1623d9c6ac86`;
the full-state summary is
`eef293a2a5df513893f58b13fc04c373aaac5c79da23c62a7d9d46f51b8b4bb0`. Its
pre-solve ready capture differs from the pinned origin only in the serialized
`WE_JUST_D01_LBC` marker (0 to 1), recording boundary input. This is a
control-vs-origin observation, not a control-vs-candidate ready-state match.

The 40 s origin restart contains history from a previous unaccepted
single-column KO7 T/Q diagnostic. “No-analysis control” means no new T/Q
increment was applied in this step; it does not mean a pristine, never-adjusted
atmosphere. The candidate was launched from the same pinned origin and control
history.

The candidate session v1 reached the post-LBC ready boundary. Its comparison
with control passed bitwise across all 652 serialized variables and 322,426,586
numeric elements; there were zero mismatches and both full ready hashes were
`0c4836a2a44531c98d38d3ded15cab5048679b1139f3e4fd96fb62eff84bfad3`. The
candidate command ACK reports 561,407 applied T/Q rows, 855,443 changed
components, zero remaining requested no-op pairs and 2,012,125 empty points.
The candidate full-physics host step completed at 60 s / step 3 with output
checkpoint SHA
`ff3c101e3b352594471ac5dfd0daab07c0daff3b6d406c88e2461283389978b5`. The
control and candidate host forward executions are complete; independent paired
field arithmetic review now also passes. Physical interpretation and the paired
observation-cost comparison remain pending.

The candidate runtime audit verifies the required namelist and both nonsecret
runtime selectors. Its RSL markers record two calls across the two internal
tiles to each configured LW/SW radiation, Noah, Shin-Hong PBL, KSAS and KDM6AD
wrapper, with outer drivers once. This confirms the configured forward path
was reached, not the numerical paired effect.

## Independent paired saved-field audit

An offline audit reread the control and candidate output checkpoints and
recomputed the selected field summaries from their saved values. All 652
serialized variables and 322,426,586 numeric elements were checked; the two
outputs differ in 26,454,541 stored numeric values. All 13 selected per-field
changed-cell counts, maximum absolute differences and binary64 signed sums
match the corrected v2 response summary. This verifies the saved
arithmetic/aggregation, not physical-process attribution.

For the analysis-input-only QV diagnostic, applying the effective QV increment
to READY40 with READY40 dry density, layer geometry and AREA2D yields
25,669,966.556135986 kg signed added water. This is not a closed forecast water
budget or a candidate endpoint budget. The audit uses the declared stored
REAL4 operations for dry density and reconstructed DELZ. `T` and `THM_2` remain
perturbation-potential-temperature coordinates; no physical-temperature
reconstruction is claimed. The independent audit made zero model calls.

The corrected v2 summary and independent arithmetic result are in the interim
evidence packet. The unreviewed predecessor summary is not included.

The fresh 60 s direct-observation pilot v2 passed for four original chunks on
the control output:
0, 34, 40 and 128 (1,988 input columns total, including the 452-column tail).
It made four direct RTTOV calls, selected 8,218 fresh `M_host0` channel cells,
and reused no old microphysics-only support. All recorded profile fields match
their preflight values. It made zero KDM, RTTOV-K, extra KDM, cleanup, finish or
host calls; the profiles came directly from output checkpoint
`225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070`. This is a
four-block pilot, not a full-domain cost or gradient result. The remaining 125
observation chunks are still in progress. Candidate checkpoint-to-RTTOV calls
and the paired `J_host` comparison remain pending. The pilot audit SHA is
`09bb9567eb01548139539ecc59450c5e95ce77c0f139061cb39a26b3477c780e`.

The four B512/B452 chunks are observation-profile packaging, not host KDM
batch sizes. The no-analysis control step called KDM6AD twice, once per
internal tile. The separate B512 `g_micro` observation harness has a different
scheduler context and is not established as an exact component gradient of
the full-host `F_20s` transition.

The separate C API precision-boundary gate v2 has status
`ARITHMETIC_AND_ABI_CHECKS_PASS; BLOCK34_FP_ENV_CAPTURE_UNAVAILABLE`. It covers
three input cases: block34 B512, block40 B512 and a nonsquare 2x4 subset. Its
cumulative accounting is 22 positive-dt requests (including prior C API
requests and saved direct-runtime references; not 22 successful new C API
calls), 12 fresh completed C API forward requests, four dt=0 identities and
nine refusal entries. The arithmetic,
writeback, default-entry and refusal comparisons pass. Thread FP-environment
capture passes for block40, the nonsquare subset and dt=0, but is unavailable
for block34 and remains unclaimed. The gate made zero WRF host and RTTOV calls.
This limitation applies to the gate's environment-coverage claim; it does not
erase the separately receipted C8 host executions. It is not C4 direction
evidence or a paired observation-cost result. See [the bridge contract](NATIVE_FP64_VALUE_BRIDGE.md).

## Whole-host endpoint tendency from the completed control

The saved endpoint audit computes `(output60 - ready40) / 20 s` for each
serialized REAL4 state value over the full 65,988-column, 39-level grid
(2,573,532 cells per mass-level field). These are whole-host, unweighted
elementwise state-change rates. They include dynamics, LBC, all enabled
nonadiabatic physics and finish; they do not isolate MP137 or close a mass or
energy budget.

| Saved field | Units of endpoint change / 20 s | Mean | Range |
| --- | --- | ---: | ---: |
| `THM_2` | K/s | -5.994e-5 | -0.124020 to 0.224591 |
| `QVAPOR` | kg kg-1 s-1 | 1.013e-8 | -5.060e-5 to 1.758e-5 |
| `QCLOUD` | kg kg-1 s-1 | 8.181e-9 | -4.039e-5 to 5.188e-5 |
| `QICE` | kg kg-1 s-1 | 1.702e-9 | -2.711e-5 to 4.062e-5 |
| `QSNOW` | kg kg-1 s-1 | -1.502e-9 | -1.378e-5 to 4.250e-5 |
| `H_DIABATIC` field change / 20 s | K/s2 | -2.441e-6 | -0.006549 to 0.005251 |

`THM_2` is the saved moist-potential-temperature perturbation coordinate, not
physical temperature. No `T` reconstruction is claimed because the exact
temperature-coordinate constant contract for this saved endpoint is not
available. `H_DIABATIC` delta divided by 20 s has units K/s2; it is not a
temperature tendency, an MP heating rate, or the sum of radiation/PBL/cumulus
heating. `NO_MP_HEATING=0` enables the MP thermal path, not every host heating
source. Use the phase-aware H interpretation above.

This saved-array arithmetic audit calls no KDM or RTTOV. V2 audit SHA-256 is
`68ffd56ce031efba2052bb23dbcfda2596a4ccd91b2205f2ba453a4afedd7ece`, producer
SHA-256 `063af5168c28a21e175ed7875bcb7dcda3c570bddd05ee2d62deef7e98aaed9b`, and
summary SHA-256 `2eb01f33f26de5c8dbb395051d16ff1dd8c63453ca832c7b903c5e8cc666db6e`.
V2 reproduces all six V1 field metrics exactly; V1 remains preserved as
history. The interim evidence packet preserves redacted receipt copies and
original private hashes; full checkpoint data and raw model streams remain
private.

## Common origin, ready-state comparison, LBC coverage, and H memory

Start both independent host sessions from the same pinned 40 s origin and the
same input, boundary assets, executable and initialization recipe. Do not use
the 40 s origin file itself as proof of the state at the later ready boundary;
the old saved restart may not represent the current working state after
boundary input. In each session, run the normal startup and lateral-boundary
input and capture the complete in-memory state at the ready hook, immediately
before solve. Do not restart from, rewind to, or treat either ready capture as a
Markov-complete checkpoint.

Hash each ready capture and compare its entire retained schema and state:
every variable's name, type, dimensions and value, plus T/Q, H memory, boundary
and other evolving state. Record differing fields explicitly. Only if the two
ready states agree across the retained state may the forward difference be
called paired from a common background. If they differ, keep both results but
do not claim a controlled candidate-minus-control response. Bind the C1
increment to the candidate session's own full ready-state hash. The opt-in
capture is diagnostic and does not establish restart equivalence.

The capture must cover all 65,988 horizontal centers, the updated boundary
values, forcing context and retained physics memory. Hash the common 40 s origin,
boundary assets, namelist, executable, linked KDM DSO, each ready capture and
both run receipts. Do not infer pre-solve T/Q from the origin checkpoint or the
saved observation packet.

Run the two sessions from the same pinned origin with identical boundary assets
and cadence, and compare their actual post-LBC ready captures before applying
the candidate:

1. **Control:** empty T/Q command, then the complete 40-to-60 s host solve.
2. **Candidate:** apply the prepared representable T/Q increment once at the
   same ready boundary, then the same complete solve.

Capture the full 60 s output from each session. Report every native-grid
column, including the lateral-boundary cells. With `SPECIFIED=T` and
`SPEC_ZONE=1`, the direct MP work crop is 64,960 interior columns. The outer
1,028 one-cell-ring columns are outside that direct MP crop but remain in the
full 65,988-column host forward output. `RELAX_ZONE=4` does not define the MP
crop. Do not trim the ring from the host result or describe the MP crop as the
forward-output domain.

`H_DIABATIC` is MP retained work/memory, not a sum of all host heating. Its
stored value is phase-dependent: MP preparation may use temporary dry-potential
temperature in K; finish writes a heating-rate memory in K s-1. At the ready
boundary, record the retained prior-step value; within the step, record its
actual stage and units. Keep it distinct from radiation, surface, PBL and
cumulus contributions. `NO_MP_HEATING=0` enables the MP thermal
preparation/finish path; it is not an all-physics heating switch.
`USE_Q_DIABATIC=0` disables only the extra RK QV/QC diabatic add/subtract path.
Normal MP water updates and latent heating still occur. Do not count H as a T/Q
analysis increment.

## Checkpoint-to-observation connection

After each completed host forward, build observation profiles directly from
the saved 60 s native checkpoint and run the pressure-aware RTTOV operator.
Do not call MP137 again to construct those profiles. Preserve native
center/interface pressure, physical temperature reconstructed from the
checkpoint's moist theta and vapor, QV and hydrometeors, surface state,
geometry and fixed upper-reference assumptions. First derive fresh `M_host0`
from the completed CONTROL 60 s profiles and their RTTOV quality==0, intersected
with the original observation/source-valid mask and finite control BTs. Freeze
its observation values and source weights for both arms. The historical
microphysics-only support count (381,528) is not assumed to survive the full
host path. Candidate quality cannot shrink `M_host0`: any invalid candidate
profile or channel on that mask is reported as a failed comparison, not dropped.
Report newly valid candidate rows outside `M_host0` separately; do not add them
to the fixed objective.

The source header/nominal scene time is 00:00 UTC while the host state advances
from model time 40 s to 60 s. Pixel-specific observation time/UTC remains
unknown here. Treat reuse of this single scene across that model-time interval
as an explicit assumption, not verified pixel-time collocation.

After independent review of the completed candidate checkpoint and its direct
RTTOV evaluation on fixed `M_host0`, compare `J_host` between the two host
states. That candidate evaluation is still pending. Define the maps separately:

```
J_micro(x) = loss(RTTOV(profile(finish(KDM(x)))), observation)
J_host(x)  = loss(RTTOV(profile(checkpoint(F_20s(x; radiation, surface,
                              PBL, cumulus, dynamics, LBC, ...)))), observation)
```

`F_20s` includes the selected full-host timestep and its nonadiabatic
processes. The current `g_micro` does not include derivatives through those
processes or the full host state transition. A paired value forward measures
the response but does not create `g_host`. Do not use `g_micro` as if it were
the host gradient or claim an optimizer step from a value-only comparison. A
fixed-prior inner optimizer iteration and full-host AD remain unimplemented.

For the intended one-step tendency diagnostic, the full-host mean state change
is `r_host = (x_60 - x_40) / 20 s`. It includes dynamics, LBC, radiation,
surface, PBL, cumulus, MP and finish. It is not a KDM-only or `H_DIABATIC`
rate. Report it at the actual 60 s endpoint; do not retimestamp it to 40 s.
The endpoint tendency audit reports control-only rates. The paired candidate
raw state difference is independently checked, but a paired `r_host` rate
summary and physical-process attribution are not established.

## Evidence required before calling the paired forward complete

- Exact common-origin time/hash, separate post-LBC ready-capture hashes and
  retained schema/value comparison; native T/Q/H entry values for both arms.
- Explicit ready-state equality decision. If any retained state differs, do
  not report a common-background paired effect.
- Matching control/candidate binaries, linked DSO hashes, boundary assets,
  namelist, radiation/PBL/cumulus/surface options and call counts. The host
  must explicitly bind to `kdm6_native_fp64_value_c`; the default `kdm6_step_c`
  remains native REAL4 KDM.
- Verified 40 s to 60 s output time for both arms and complete finite
  65,988-column output, including lateral-boundary cells.
- Fresh `M_host0` from CONTROL 60 s profile/RTTOV quality, original source mask
  and finite control BT; fixed observation values/weights and candidate
  non-drop gate.
- Candidate ACK and applied T/Q bit evidence at the actual ready boundary;
  no-op points must remain at baseline. Record H-entry and H-exit separately.
- Preserve the C API boundary gate's three cases and cumulative call accounting.
  Arithmetic/ABI comparisons pass, but block34's FP-environment snapshot is
  unavailable; do not label that part of the gate complete.
- Direct checkpoint-to-RTTOV profile, support, quality and cost receipts with
  no additional MP call; report baseline/candidate differences and limitations.
- Record two C8 host steps total (one per arm), zero AD and optimizer calls,
  and zero extra host steps. This result is a 40-to-60 s one-step response
  diagnostic, not a fixed-time retimestamp, forecast skill, balance,
  conservation, full-host gradient, or a second assimilation.

The no-analysis control and T/Q candidate full-physics host steps are complete
from the exactly matched post-LBC ready state. Both output checkpoints are
pinned and independent saved-field arithmetic review passes, but physical
interpretation and candidate RTTOV remain pending. The four-block control
direct-RTTOV pilot is complete; full-domain C7, C4 effective-direction calls
and any full-host derivative remain incomplete. At this status snapshot, the
full-domain runner has 125 non-pilot observation blocks in progress.
