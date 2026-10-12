# PR418 post-merge audit: two verification omissions resolved

Audit baseline: merged main `569892ae`, tree-identical to PR418 head
`94b6d567`. PR418 was merged at 2026-10-12T14:44:39Z; its five head checks
had succeeded. The earlier “before merge” report described its then-current
state, not a continuing pending condition.

This audit started on Oct12 KST and continued past midnight on Oct13; the
packet name records its start date. Validation timestamps identify completion.

## Findings and fixes

1. **Unbound viewing-geometry producer.** The new driver used
   `legacy.NATIVE_READER.ami_geometry()` but omitted the reader from its
   preflight/capture source hashes. Red reproduced an accepted synthetic driver
   return after changing a staged reader after its use; no H/RTTOV or original
   reader mutation was involved. The shared direct-source list now includes
   that reader. Initial bindings survive preparation into capture; live hashes
   are checked during the final source audit and reported in failure receipts.
   Changed bytes or disappearance of the reader prevent checkpoint publication
   in the real capture body; an unavailable after-hash is recorded as null.
   This affects future driver provenance, not the saved PR417/418 H results,
   whose separate PLAN already bound the reader.

2. **Nine-channel capture/audit tests outside CI discovery.** Core adapter tests
   ran in oracle CI, but the nine-channel checkpoint/audit regressions lived
   under `harness/evidence/`. The workflows select `oracle/` and
   `harness/tests`; the old seven-channel local capture test additionally needs
   private reference inputs and skips in public CI. New portable oracle tests
   exercise nine-channel capture, final audit, receipt/checkpoint roundtrip,
   quality32768 rejection and geometry-reader mutation. They use synthetic H
   and an explicitly mocked provenance gate; no private native/reference input
   or actual RTTOV is required. Source-guard driver tests use staged files and
   fake capture/pool, with no M/H/optimizer calls.

No new production physics, AD map, solver, coefficient, quality waiver or
scientific acceptance criterion was introduced. These are execution-evidence
and regression-coverage fixes.

## Independent checks and preservation

Green verified private two-channel H06/H07 and the public composite agree,
with the one-shot marker's plan hash matching. Nine-channel L1B payload order,
hash, bound point values and source DQF0 match the actual retained data. PR417's
fourteen preserved packet files and original PR407 driver remain unchanged.

The complete driver was additionally exercised locally with real KDM/L-BFGS
and synthetic H, using the existing private reference/template as test inputs:
`RETURNED_CASE_DIAGNOSTIC`, selected-count audit `CROSSCHECKED`, all nine IDs
saved and the geometry reader bound. This local test used five synthetic H
callbacks and zero actual RTTOV calls. It is separate from the portable tests
and does not demonstrate a real nine-channel retrieval.

PR418's artifact manifest is a historical record of its committed source
version. It matches `569892ae`; this follow-up intentionally changes the
nine-channel driver, which has not run an actual nine-channel analysis. Old manifest/hash/BT/flag
records are preserved and must be checked against that recorded commit, not
treated as an eternal assertion about future edited source files.

The saved WV063/WV069 flags remain32768 at both times. No additional actual
H, H05, scientific-case M/optimization, native run, L1B acquisition or hourly
observed-time pairing was performed. Strict convergence, different-date
repeatability and true temporal matchup remain the previously declared
limits. This audit found no further demonstrated physics/AD/solver defect
within the inspected and tested paths.

Focused/full verification results are recorded separately in `VALIDATION.json`.
Green/Red review distinguish directly executed tests from source inspection.

Full local oracle before the final missing-reader guard refinement: **1846
passed,33 skipped**; combined focused set at that stage: **39 passed**. Seven
new portable cases are now collected by the ordinary oracle command, including
both reader content changes and removal; the final focused recheck is recorded
separately in `VALIDATION.json`.
The full run skipped the older PR408 private-reference capture test because
the pinned temporary `share/wrf_timeseries.F/.f90` path was unavailable when
it ran. The earlier focused/private-reference checks succeeded before that
current absence was observed. Both files were then checked and found absent;
no cause of their absence is established here. The old PR417 PLAN binds the
`.F` path, so full current replay of that historical source guard is unavailable.
This is a current dependency limit, not a change to saved BT/flag or proof that
the past successful execution was invalid. The source is not silently replaced
with a different host tree; portable regressions do not require it.
