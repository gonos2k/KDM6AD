# Native MP137 state carry and T/Q increment evidence

This report summarizes bounded value-only MP137 runs that test whether native
state can flow through a persistent WRF process and whether a saved T/Q
posterior increment reaches MP137 forcing and the host tendency path. It does
not report a converged analysis, an observation optimizer, RTTOV cost, or a
full-host derivative.

The compact metrics and private receipt names are in [`summary.json`](summary.json).
The detailed NetCDFs, model logs, and host build remain in the local private
`host/research_evidence/mp137_state_carry_20261020/` tree and are not copied
into this public evidence folder.

## State carry and control families

The public live stepper is value-only and operates one native process at fixed
20 s steps. `H_RATE` remains the default control family for the retained
`H_DIABATIC` tendency-memory probe. `ANALYSIS_TQ` is the separate opt-in family
for a bound prognostic moist-theta/QV increment. The Python transport contracts
are in [`native_step_control.py`](../../native_step_control.py),
[`native_analysis_control.py`](../../native_analysis_control.py), and
[`native_analysis_increment.py`](../../native_analysis_increment.py).

With empty `H_RATE` commands, the live path ran 120→140→160→180 s. At each of
140, 160 and 180 s, all 652 checkpoint variables matched the inactive-control
reference bit for bit; metadata had no differences or normalizations. The run
used one MPI rank, one thread and two internal WRF tiles. This establishes
empty-control noninterference over these three steps, not arbitrary restart
equivalence.

The separate H probe applied `+0.001 K s-1` to retained `H_DIABATIC` at
`(i=156,k=6,j=21)` at 140 s (saved step 7). That is an artificial tendency
memory intervention, not a T/Q analysis update. MP call 7 was unchanged. On
call 8, TH differed at 6 levels, Q at 21, DEN/PII/P at 23 each, and DELZ at 21.
Call 9 also showed changed inputs. The sampled host-finish replay checked 117
level-step samples with zero arithmetic and packing mismatches. This shows the
retained H memory affected later forcing and tendency; it is not evidence of
analysis balance or convergence.

A separate three-transition `ACCEPTED_STATE_CARRY` run accepted each returned
state using finite-pressure, positive-specific-volume and nonnegative-water
checks. These are admissibility checks only. They do not certify equilibrium,
conservation or physical balance.

## Saved T/Q posterior through the native physics

The native prognostic temperature field is the in-memory `grid%t_2`, persisted
as NetCDF `THM_2` for this audited moist-theta configuration. NetCDF `T` is a
diagnostic dry potential temperature and is not the native prognostic source.
At startup, `THM_1`, `THM_2`, and history `THM` matched bit for bit, as did
`QVAPOR`. A prior cold-start source selection using `T` was rejected at the
background binding check before any command was applied; the corrected run
bound to `THM_2`.

The corrected cold `ANALYSIS_TQ` identity command completed one 20 s step with
no rows. Against a helper-disabled run using the same binary, inputs and
radiation cadence, all 652 fields (322,426,586 numeric values) matched at
00:00:20; metadata had no differences or normalizations. For the actual
saved-DA one-step case, `radt=1/3` minute, `bldt=0`, `cudt=0`, and
`STEPRA=STEPBL=STEPCU=1`. The two internal tiles produced two calls each to
RRTMG longwave, RRTMG shortwave, Shin-Hong PBL, KSAS cumulus, and KDM6AD; the
outer PBL, cumulus and microphysics drivers each ran once. These are the
measured settings and counts for this run, not a claim about arbitrary
namelist templates.

The actual update used one saved, unaccepted KO7 offline diagnostic posterior
at valid time 00:00, column index 4835 / native `(i=156,j=21)`, across 39
levels. The full-domain background T/Q matched the cold input. The posterior
had maximum `|delta_theta_m|=0.553983 K` and `|delta_qv|=4.58875e-5 kg/kg dry
air`; the native packet applied only `T_2` and QV, with zero direct
`H_DIABATIC` updates. The transform uses the host's captured binary32
`Rv/Rd` coefficient (`3FCDDED2`), keeping it distinct from the nominal-ratio
f64 reader coordinate.

`encode_native_increment` checks these unit and coordinate stamps. The
`NativeAnalysisIncrement` object is a public value carrier and can be manually
constructed; the live stepper checks shape, time, geometry, layout and current
background hash, but trusts the caller to use the checked encoder for units
and alpha provenance.

After one 20 s cold native step, all 39 levels changed at the MP137 input in
TH, Q, DEN, PII, P and DELZ. Their maximum absolute changes were 0.527313 K,
`4.35878e-5 kg/kg`, `5.52177e-4 kg/m3`, `9.59635e-5`, 11.046875 Pa and
1.125977 m. The complete 652-variable terminal frame was finite and complete;
136 fields had differences, with 48,264 numeric values differing from the
identity control. Native finish produced changed H tendency at 28 levels (maximum
`1.32772e-4 K s-1`) and changed QV tendency at 10 levels (maximum
`3.54601e-8 kg kg-1 s-1`). The sampled 39-level finish replay had zero
arithmetic and packing mismatches. This is direct evidence that this saved T/Q
increment entered actual MP137 forcing and produced native tendencies.

The posterior was not science-accepted or converged. This was one step, so it
did not test a later MP call after the generated tendencies. The QV increment
is an external water source; this evidence does not certify a global water or
energy budget. No new observations, RTTOV cost, optimizer, full-host JVP/VJP or
HVP ran.

## Radiation cadence and attribution

The live stepper currently defaults to `radiation_every_step=True`. For
20-second steps this sets `radt=1/3` minute; restart-origin sessions require an
explicit `STEPRA=1` seed. A separate two-step cadence variant had `STEPRA=1`
at 120, 140 and 160 s and executed four RRTMG longwave and four shortwave
calls (two internal tiles times two steps). This is a distinct radiation
schedule from the prior five-minute variant; no cross-schedule raw-bit parity
is claimed, and the cadence run adds no RTTOV or derivative evidence.

The cold ANALYSIS_TQ runs used v3 executable hash
`911541b9060b3d5aec0179c685a5d3d2905e233fdf721cc19cf342a2938e1f86`. The
warm zero-control, H_RATE, accepted-carry and radiation cases used v2 hash
`a53888758b983cdff698fd149757524e7a060d88425b8b1204c2dfc472af6459`; the
inactive-control reference used v1 hash
`d01ef67a1ed6f928fe301f30785d6470cd00104d80abdecffbfbed721fc272a1`. All
used the installed KDM library hash
`7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7`. This
was an isolated update to an existing build: the mediation object and helper
were rebuilt while the remaining archive members were reused. It was not a
clean full host rebuild. The encoder bytes used for the saved-DA launch were
preserved under the private evidence tree at the hash recorded in `summary.json`;
the current public encoder also supports NumPy-only imports when Torch is absent.

Final local validation: **2,479 passed, 59 skipped, 309 deselected** in the
full harness suite (110.68 s). The seven focused native files passed **172
tests** (11.93 s), including the Torch-free NumPy subprocess and the standalone
Fortran protocol checks. Undefined-name lint and `git diff --check` passed.
The 309 local-marked tests were excluded by the default run; skipped tests
retain their dependency-specific reasons. No new C++ port build is claimed.

An expanded harness run exposed an intermittent macOS process-group `EPERM`
after the runner leader had exited. Cleanup now ignores that error only when
an independent `ps` snapshot confirms no live group members; live groups or
failed/ambiguous inspection preserve the original error. Mock regressions cover
absent, zombie-only, live and unavailable/failed inspection cases. This cleanup
change does not alter the successful native forward path recorded above.

Graph coverage includes the public AST and refreshed document semantics. The
active host tree is private and absent from the public graph, so the native
source paths and phase relationships cited here were checked against the
active private sources and run receipts; this is not private-host AST coverage.

The model clock advances by 20 seconds per solve. The analysis/observation time
policy for future repeated DA cycles remains caller-owned. These runs do not
establish unattended cycling, a general balance-adjusted state encoder, or a
usable host adjoint.
