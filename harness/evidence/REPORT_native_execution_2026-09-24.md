# G4: owned execution, spatial holdouts, decomposition and restart

## Result: execution pairing passes; two trajectory gates fail

Seven new native runs extend the isolated **normalized mp237** experiment to
MPI 2×1 and 1×2 decompositions and a 20-second restart. Every captured owned
column has one selection and its expected actual ice consumer, with the correct
rank territory. Instrumentation preserves each configuration's history bytes.

However, **x decomposition and restart are not trajectory-invariant**. At
40 seconds, 2×1 differs from serial in 71 of 253 numeric variables; restart
20→40 differs in 60. The 1×2 trajectory matches all 253 numeric variables at
0/20/40. These failures remain open; no tolerance, clipping, physical equation,
operational default or historical source pin is changed to turn them green.

## Fixed experiment and distinct controls

Use the retained 5 km model input, 39 mass levels, dt=20 s, one thread per rank,
`mp_physics=237` with the already documented two-line ice normalization variant.
Only a private read-only KDM source copy is compiled. It emits rank-qualified
SELECT and actual top-ice-gate CONSUME rows and strips exactly to normalized
source SHA `405f543447b4185847d9615827b478e7b6c90064ca02b7226e4acfa7502a63c8`.
No installed source, executable or archive is replaced.

| Run | MPI grid | Physical window | New capture |
| --- | --- | --- | --- |
| serial | 1×1 | 0→40 s, checkpoint at 20 s | Yes |
| x-control / x-capture | 2×1 | 0→40 s | Same executable, logging off / on |
| y-control / y-capture | 1×2 | 0→40 s | Same executable, logging off / on |
| restart-control / restart | 1×1 | Exact serial checkpoint at 20 s →40 s | Logging off / on |

All seven runs exit successfully. The serial capture's full history SHA is
`a065598b870815220ba36f7b2fbcdc6f65f8d69910c2e261961203b78d6683d8`, exactly the
retained normalized control. Each MPI control/capture pair has identical history
SHA as well. Cross-configuration comparisons use exact corresponding **Times
and raw numeric field bits**, not complete-file hashes (parallel metadata and
restart frame counts differ). Within-configuration instrumentation preservation
and cross-configuration trajectory agreement are separate checks.

A separate logging-off restart control also has the same complete history
hash as the restart capture. Thus the restart trajectory discrepancy persists
without the diagnostic writes. The later control uses the metadata-only runner
guards described below; its executable, effective namelist and resolved input
identities are identical to the capture's. Full effective namelist text is
published with its digest; the replay permits only the declared grid, I/O and
restart-window differences. Ordinary arms must share serial's initial input,
and all arms retain the same boundary/auxiliary forcing identities.

## Complete ownership and actual consumption

The independent mass-grid microphysics domain is i=2..233, j=2..281: 64,960
columns per call. The physical specified strip is excluded. Configured patch
territories are checked separately from the observed event coordinates:

| Grid | Rank 0 owned i / j | Rank 1 owned i / j |
| --- | --- | --- |
| 1×1 | 2..233 / 2..281 | — |
| 2×1 | 2..117 / 2..281 | 118..233 / 2..281 |
| 1×2 | 2..233 / 2..141 | 2..233 / 142..281 |

Host patch announcements match these independently specified decomposition
bounds. The public six compressed rank logs contain **909,440 rows**: 454,720
SELECT and 454,720 CONSUME. Serial/x/y captures have steps 1 and 2; restart has
step 2 only. The step is copied directly from the host's `itimestep`, not a new
counter. Actual restart data confirms its preservation.

Every selected mstep is 1. Hence this extends native ownership/restart coverage,
**not native n≥2 coverage**. CONSUME is emitted inside the executed top-cell
`n<=mstep_i(i)` gate once per column, rather than repeating for all 39 layers.
A consumed loop may have zero hydrometeor or zero flux; the census does not
claim 454,720 active physical-process observations.

`native_execution_contract.py` separates this fixed regression from a reusable
validator. Expected global coordinates, steps, ranks and territories come from
the caller's configuration. Missing/duplicate owners, halo coordinates, wrong
rank files, missing ordinals and work after a column finishes are rejected.
The selected mstep itself is measured, not recomputed from velocity. Consistently
falsifying SELECT and CONSUME counts is outside this arithmetic witness and is
explicitly demonstrated as a limitation in a synthetic test.

## Input-selected spatial holdouts

Before any G4 comparison, a fixed selector chooses the median row-major eligible
interior column for each of five input predicates, excludes already chosen
points and the old column 35711, and saves the native profiles. Flat index 35711
is zero-based (j152,i143), **Fortran (j153,i144)**; that is the excluded point.
There is no vertical remapping, external atmosphere, output-cost selection or
post-result replacement of a candidate.

| Input class | Candidate count | Selected Fortran j / i |
| --- | ---: | --- |
| Clear | 24,020 | 145 / 11 |
| Warm liquid | 16,493 | 139 / 106 |
| Mixed column | 7,556 | 124 / 144 |
| Ice | 12,463 | 130 / 209 |
| Rain | 6,135 | 112 / 212 |

Thresholds and unique-selection rules are in `native_input_selection.py`.
Mixed column means cold cloud water and ice/snow occur somewhere in the column;
it does not require same-level colocation. Classification uses condensate and
input temperature reconstructed with the host constants R/cp=2/7. All initial
number arrays are zero before host initialization, so the labels do not assert
active number, a measured process rate, surface export or observational skill.

The public JSON preserves seven input profiles for every selected column and
13 output fields at the saved times for serial, both MPI captures and restart.
The profiles retain their original native levels. These are held-out spatial
samples of **one** forecast, not five independent weather events.

A useful negative result: all five selected columns' saved 13-field profiles
match serial under both MPI decompositions, even though the **whole domain**
x-split comparison fails. Thus successful sample comparisons do not replace the
full-domain gate, and the candidates are not changed after seeing that failure.
All five show at least one restart difference at 40 s.

A final synthetic counterexample found that converting a masked array with
`np.asarray` could select its hidden zero storage as clear sky. The selector
now rejects masked inputs first. This validation-only change was made after
the native runs: re-reading the original complete input reproduces all original
counts and choices. Both selector hashes are retained; no candidate was replaced.

## Exact trajectory comparisons and their unresolved cause

| Comparison | Numeric differences at 0 s | At 20 s | At 40 s |
| --- | ---: | ---: | ---: |
| Retained normalized control → new serial | 0 | 0 | 0 |
| x-control → x-capture | 0 | 0 | 0 |
| y-control → y-capture | 0 | 0 | 0 |
| restart-control → restart capture | Not a restart frame | 0 | 0 |
| serial → 1×2 | 0 | 0 | 0 |
| serial → 2×1 | 0 | 28 | 71 |
| continuous → restart | Not a restart frame | 7 | 60 |

Every compared frame checks the same complete set of 253 numeric variables;
variable-set, dtype and shape equality are required. This is raw-bit comparison,
not a claim that every diagnostic value is physically valid. Differences are
reported on their full population, not just the subset that differs.

At 20 s, x-split T differences occupy i=110..123 and 227..233; QNCLOUD
differences occupy i=112..122,125 and 228..233. This is a saved-time support
near the i seam and eastern side, **not the first internal divergent operation**.
It is consistent with the previously documented i-seam concern but does not
independently re-establish that old mechanism on this executable. The next
localization should compare upstream geometry/forcing before the first KDM
call, not assume the correct ownership census certifies numerical equivalence.

Restart's immediate 20-s differences are FOGFRAC_SFC, NOAHRES, REFL_10CM,
RHO_ICE, VIS_SFC, VIS_SFC_CAPPED and VIS_SFC_RAW. Prognostic history fields
match at that saved instant. At 40 s, the difference includes prognostic state
as well (for example maximum difference in WRF `T`, the potential-temperature
perturbation, is 0.6151123046875 K). It cannot be dismissed
as merely missing output diagnostics. Conversely, the present comparison does
not identify KDM, surface/PBL initialization, hidden host state or timer coupling
as the sole cause. A first-divergence trace is still required; this PR does not
broaden into a general host-physics repair.

## Restart identity was a real runner gap, now fixed

The previous input resolver always recorded `input_inname` and omitted the
checkpoint even when `restart=.true.`. It now resolves `rst_inname` using explicit
start-date components (or an exact literal filename), hashes it before and after
the run, and keeps the declared boundary/active-auxiliary envelope. It does not
claim every declared auxiliary file was read at each restart instant.

The 20-s checkpoint Times and inherited alarm metadata are recorded. Its SHA is
`2ad545592a9a2a29afbaeb6eab7dcbca636f749c9060e814e8168470373b6a44`, unchanged
before/after the child run and linked to the serial parent. The same boundary
file brackets the restart window. `restart_interval=0`, `restart_interval_s=20`
produce the checkpoint without inheriting a nonzero minute interval;
`write_hist_at_0h_rst=true` emits the child's 20-s initial frame. Default
`override_restart_timers=false` retains the checkpoint alarm state.

Additional metadata tests mirror WRF's `nocolons` filename transformation,
including a stale colon-form file beside the actual underscore-form file.
Rank-split restart I/O forms 100–199 are rejected until all rank artifacts can
be authenticated. The present experiment uses single-file form 2 and default
nocolons=false. These two guards were added after the first six native runs; resolving
all seven archived namelists with the final code produces exactly the same input
specifications. Run receipts preserve the actual earlier runner hash.

## Reproduction and remaining checklist

`python harness/replay_native_execution.py` reads the complete public compressed
census, verifies recorded provenance/paired-run facts and rechecks the published
held-out vectors. It does not reopen the private NetCDF files or independently
rebuild the host. Full-domain comparison statistics are recorded execution
results; only the published profiles and census are publicly recalculated.
Selector-revision and checkpoint-alarm digests bind their fixed metadata receipts;
this is not an independent reconstruction of private source or timer state.

G4 ownership/consumption and input-stratified sampling are demonstrated in this
bounded campaign. X-decomposition trajectory independence, restart equivalence,
native n≥2, coupled time accuracy, thread-count changes, full normalized AD/ABI,
physical number units and independent radiative/observational validation remain
open. No new RTTOV run was made; inherited liquid acceptance remains 0/9.

Validation: **66 focused Python 3.12 tests passed** (50 new execution/selection/
restart/replay checks and 16 retained run-identity checks). One existing
NetCDF/NumPy import warning appeared in the invalid-history test; no test failed.
Ruff passed for new files and the runner's existing undefined-name gate. A green
replay confirms complete records and faithfully retained **failed** trajectory
gates, not scientific approval of decomposition or restart equivalence.
