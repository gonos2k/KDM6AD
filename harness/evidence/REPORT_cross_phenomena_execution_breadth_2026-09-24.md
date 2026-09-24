# X12: input-selected breadth and execution gates

## Result and attribution

This report connects the cross-phenomenon checklist to the G4 evidence from
PR #237, commit `4b3c20af3bfbe94f71f1688a05406ba88aef3b01`. Its files were
cherry-picked without altering the recorded experiment. The authoritative
execution account is `REPORT_native_execution_2026-09-24.md`. Its seven runs
use an isolated **normalized mp237** variant, not the operational mp37/mp137
path. The complete
public metadata, selected profiles and compressed owner/consumer census are
`native_execution_2026-09-24.json` and its six named `.txt.gz` companions.

Five spatial columns were chosen from the **initial input** by fixed clear,
warm-liquid, mixed, ice and rain predicates. Selection excludes the former
column 35711 and did not use forecast differences, cost or QC. The stored
profiles keep 39 native levels. Serial, 2×1 and 1×2 runs save the same
predeclared 0, 20 and 40 s lead times; restart saves 20 and 40 s. Thus the
20/40 s profiles are held out from input-based **selection**, but all belong
to one short forecast. They are not independent weather dates or five native
simulation cases.

## Additional public-value temporal check

For each selected serial profile, compare every published field at adjacent
saved lead times. A vector element contributes one changed value if its JSON
number differs; the scalar `RAINNC` contributes at most one. This is a
decimal-value comparison of published profiles, not a raw-bit NetCDF check.

| Input category | 0→20 s changed fields / values | 20→40 s changed fields / values |
| --- | ---: | ---: |
| Clear | 3 / 117 | 3 / 117 |
| Warm liquid | 8 / 159 | 6 / 143 |
| Mixed | 12 / 214 | 11 / 197 |
| Ice | 12 / 200 | 11 / 171 |
| Rain | 12 / 206 | 11 / 180 |

For clear sky the changed fields are `QVAPOR`, `T` and `P` at both intervals.
For the four condensate categories, multiple hydrometeor or number fields
change. This confirms temporal evolution in the stored selected samples; it
does not measure the first internal divergent operation or a numerical time
convergence rate. The calculation can be repeated by reading
`heldout['serial']` in the public JSON, indexing `(category,time)`, and counting
unequal field elements for the fixed pairs (0,20) and (20,40) seconds.

## Gate separation

G4 reports seven completed isolated native runs and 909,440 public SELECT /
CONSUME records. Each selected owned column has one selection and one actual
top-ice-gate consumer in this `mstep=1` experiment. The new serial capture
matches the retained normalized control; the new x/y and restart runs each
have a same-configuration logging-off control that matches their capture.
These within-configuration checks are distinct from cross-configuration
raw-bit field comparisons, which have different results:

| Comparison against serial | 0 s | 20 s | 40 s |
| --- | ---: | ---: | ---: |
| 1×2 MPI, different of 253 numeric fields | 0 | 0 | 0 |
| 2×1 MPI, different of 253 numeric fields | 0 | **28** | **71** |
| Continuous versus restarted, different of 253 numeric fields | — | **7** | **60** |

The five selected columns happen to match serial under both MPI layouts at
all saved times. This is a measured counterexample to replacing the
full-domain gate with selected-profile success. The same five restart profiles
match the 20 s checkpoint and all differ at 40 s. The restarted logging-off
control matches the captured restart, so diagnostic writes do not explain that
failure. The observed 20 s i-seam support and the seven immediate restart
diagnostic differences are **saved-time symptoms**, not first-operation
causal localization.

In addition to the public replay, this review reopened four retained **private**
history files from the recorded G4 run directories: serial, x-capture,
y-capture and restart. Their complete-file SHA-256 digests each match the
respective `history_sha256` in the public JSON. A separate `netCDF4`/NumPy
reader required the same 253 numeric variable names, dtype and shape in each
paired frame, then compared each array's bytes. It reproduced 0/28/71,
0/0/0 and 7/60 different-field counts in the table. The seven restart
differences at 20 s are `FOGFRAC_SFC`, `NOAHRES`, `REFL_10CM`, `RHO_ICE`,
`VIS_SFC`, `VIS_SFC_RAW` and `VIS_SFC_CAPPED`; the 40 s difference also
includes `U`, `V`, `W`, `PH`, `T`, `MU` and `P`. All 55 published held-out
profile records (15 each for serial/x/y, 10 for restart), with 13 fields per
record, were also extracted at their declared one-based `j/i` coordinates
from these retained files. All **715 field instances** match the public
binary32 values. The JSON-derived temporal counts above therefore agree with
the retained serial file's sampled values. This is an independent read of
retained output files, **not** an independent native model execution or a
first-operation trace. It also does not establish a cause for either failed
gate.

The public replay validates the recorded manifest, input identities, selected
profiles and the complete owner/consumer census. It does not reopen private
NetCDF or rebuild the host. In this worktree, its four new focused test modules
and the retained run-identity suite passed **67 tests**; one local NetCDF/NumPy
import warning appeared in the invalid-file test. The complete public replay
also passed and verified all 909,440 SELECT/CONSUME records. The additional
temporal count above uses the public JSON only; it is not a new native run.

## Acceptance boundary

X12 is complete as a **bounded breadth and failure-characterization item**:
input-selected spatial conditions and predeclared lead times were retained,
execution coverage was measured, and all failed gates remain explicit. The
following are separate open objectives: first-operation localization and
repair for 2×1 MPI and restart, native `mstep>1`, another meteorological input
time or case, thread/restart breadth, physical time convergence with correctly
normalized dynamic velocity, the real mp337 ABI, independent radiance accuracy,
and QC-accepted liquid BT/cost sensitivity (inherited 0/9). Operational ice
transport P1 and the number-basis contract also remain open. None is inferred
from the 67 local tests, public replay or temporal counts.
