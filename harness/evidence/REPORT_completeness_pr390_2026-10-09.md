# Team completeness audit: PR390 and local diagnostic follow-up

2026-10-09. Baseline: PR390 `ada6fc42` plus the separately recorded diagnostic
packet in this isolated worktree. Green and Red (`gpt-6-luna`, reasoning high)
cross-reviewed each other's evidence. This is a bounded evidence/completeness
audit, not a fresh validation of every production process or a release decision.

## Judgment

The requested minimum MPI and single-profile RTTOV diagnostics are complete in
their stated scopes. The separate initial-time host pair also establishes
normal shutdown and saved-output observer noninterference for its experimental
mp337 path. The broader differentiable KDM→GK2A–RTTOV research is **not complete**:
the first valid fixed-candidate native/independent-observation case, physical
admission/budgets and additional numerical/spatial evidence remain open.

No required production P1/P2 defect was found in this bounded audit. Red
identified a **P2 evidence-provenance limit**: the exact pre-edit MPI Python
orchestration hash was not retained. It is separate from a production defect;
the limitation is explicitly disclosed and cannot be repaired retroactively.
To obtain a fully captured current witness, Red ran a **new isolated minimum
MPI control replay** with Python/Fortran hashes pinned before and after. All
four launcher and two singleton controls passed, without modifying the October
8 result or ten original compile/run logs. This closes availability of a
current pinned witness, not the missing historical orchestration hash.
P3 wording refinements were corrected without changing numerical results.
A1/A2/A3 and earlier bounded derivative results retain their
original source/input/build attribution; this review does not recertify them
for the fixed VIIRS/native target or untested regimes.

## Independent evidence checks

Green checked the private RTTOV source/object/library copies, raw internal dump,
channel mapping and saved profile against the receipts. Of 506 Fortran sources,
only the diagnostic Eddington setup source differs; of 507 objects, only its
object differs. Eleven direct/K products match the saved case, original rerun
and diagnostic rerun by hash. The 4,752 dump rows cover two calls, one profile,
nine channel slots, 66 layers and categories 0/1. Actual clipping follows the
unchanged `MIN(total,20)` rule and both calls' measured arrays agree. These are
new diagnostic-build arrays, not historical binary internals. The actual channel
8/9 trigger layers and zero additional hydrometeor contribution are supported.
The logged clear-sky base is after the 1e-10 km^-1 minimum floor, not an unfloored
base at every layer. The reported >20 km^-1 triggering values are unaffected.

Red checked minimum-control source, library-load logs, status markers and the
paired host's actual input/namelist/binary receipts. It independently reran only
the offline strict frame comparator: 254 variables match at each saved time,
with none skipped. Each file has 253 numeric variables and 158,946,410 numeric
values across 00:00:00/00:00:20; all are finite with masks/scales disabled. Times
is the remaining character variable and compares exactly. No new native model
or RTTOV process was launched during this audit.

The [fresh pinned MPI witness](MPI_pinned_witness_2026-10-09.json) identifies
current runner/source/config/library pins, exact compile/launch argv, binaries,
logs and before/after hashes. Each process has a 20-second wall bound; no process
timed out. Its separately attributed current-run result preserves all October
8 evidence and does not replace the historical missing source capture.

The host pair is **experimental mp337**, normalized variant 2, dry-number 1,
value-only 1. It is not operational mp137, legacy mp37/mp137 parity, a host-AD
run or evidence at the target period 05:55:40–05:58:00. The MPI-launched status
is the launcher/harness outcome; direct-child wait status is available only in
the separate singleton controls. `_Exit(0)` logs the requested exit status.

Detailed independent reviews:
[Green](GREEN_completeness_pr390_2026-10-09.md),
[Red](RED_completeness_pr390_2026-10-09.md).
Their machine-readable offline checks remain under
`graphify-out/pr390-completeness-green/` and `pr390-completeness-red/`.

## Corrected refinements and retained limitations

| Item | Resolution |
| --- | --- |
| Ambiguous “hydrometeor inputs zero” | Specify zero **content and fraction**. Size parameters contain nonzero entries. Rename the derived-summary boolean accordingly; extinction values and raw inputs remain unchanged. |
| Host path insufficiently explicit in the main report | State mp337/variant2/dry-number1/value-only1 and its initial-time scope explicitly. |
| MPI Python runner hash timing | State that it hashes current post-run metadata-corrected source. The exact pre-edit Python orchestration hash was not retained; Fortran source, commands, binaries and logs are separately available. No retroactive pre-execution pin is claimed. |
| Minimum-floor scope of the RTTOV dump | Recorded `ext_clear` is after `MAX(base,1e-10 km^-1)` and before the later 20 km^-1 maximum cap. Unfloored bases/sub-floor components were not retained for non-triggering layers. All measured trigger values and warnings are unchanged. |
| Older checklist says actual warning layers unresolved | Retain that dated snapshot. The new measurement supersedes it only for `case_00` in the attributed diagnostic build. Seven other saved profiles were not internally instrumented; no extra-profile generalization is made. |

Prior changed document/derived-receipt bytes are preserved with SHA-256 in
`graphify-out/pr390-completeness-root/correction_manifest.json`. Threshold,
quality, triggering-layer values, channel maxima, build hashes and original
preservation records are unchanged. Executed source captures and failed-run
flags are preserved. The closed distance P3 remains closed.

## Research completion matrix

The current scope follows [the internal research checklist](CHECKLIST_internal_research_2026-10-07.md)
and [the research guide](../../docs/INTERNAL_RESEARCH.md). Historical checklists
are dated evidence, not silently updated claims.

| Area | Assessment | What is still required |
| --- | --- | --- |
| Minimum MPI observer forwarding | Complete for tested controls | Other paths/rank counts are outside this result. |
| Short native termination/noninterference | Complete for the paired experimental 20-second run | Target-time validity is separate. |
| RTTOV warning attribution | Complete for one stored profile and its diagnostic-build direct/K calls | No individual-gas, other-profile or historical-source-build claim. |
| A1/A2/A3: fixed-error, CVT prior and selected cost/VJP wiring | Existing bounded closure maintained | This audit adds no AD/FD evidence for the current independent candidate. |
| R1: physical coordinates/state admission/density roles | Conditional definitions available; approval open | Supported units, admissible moment pairs and runtime/optical/inventory roles must remain explicit. |
| R2: first valid independent native case | Open | An independently attributed valid target run plus product QA, actual time/geometry/surface and common footprint. |
| P1/S17: applied physical budgets | Partial | Actual staged mass/number/enthalpy and applicable external/boundary/work terms; inventories alone do not close a budget. |
| T1: same-final-time timestep dependence | Open | Declared native 20/10/5-second comparison with branch/substep scope; accuracy/convergence is distinct from each map's derivative correctness. |
| C1/V1: native multicolumn and unused validation | Open | Per-column native grids/geometry and appropriate worker agreement; independently preselected validation data/initializations. |

Representative process/regime coverage and named-process attribution remain
bounded by the existing executed derivative records. First-order RTTOV K is
not higher-derivative or parameter-identifiability certification. Calibrated
sigma/bias are not required to start this internal first attempt: 1 K/zero bias
can remain an explicit exploratory assumption. Installation/distribution,
forecast skill, unattended cycling and a full host-model adjoint are not added
as completion gates here.

## Next priorities

1. Obtain an independently attributed **valid target-time run** for the fixed
   candidate, with observable shutdown and actual saved times. The old exit-1
   cause remains an unresolved historical question; a new valid experiment
   need not retroactively certify or explain that old run.
2. Resolve selected observation QA, pixel/scan clock, parallax datum and common
   footprint. Explain the fixed candidate's clear-model/liquid-retrieval
   disagreement using applicable native trajectory evidence; do not select a
   better neighboring column or tune sigma/bias to its residual.
3. Continue R1/P1/T1/C1/V1 under declared physical/numerical assumptions. Retain
   earlier closures and their source identities rather than repeating closed
   geometry/cost arithmetic or introducing a new generic framework.

The audit itself performed no commit, push or publication. The user subsequently
requested a PR at 2026-10-09 09:10 JST including audit status and pending
[research decisions](DECISIONS_pr390_followup_2026-10-09.md). This submission
does not approve those decisions, a physical observation case or operations.
Public-code graph coverage and bounded documentation semantics are refreshed;
private host/RTTOV paths still depend on source/build/execution receipts. Raw
graph reports remain under `graphify-out/`, with synthesized wiki evidence links.
