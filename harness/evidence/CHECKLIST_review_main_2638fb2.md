# Review resolution — main 2638fb2

Baseline: `2638fb20bdb84139d9f77620132bbd8d312c558e` (PR #203).
Requested 2026-09-05. Preserve the operational f32 equations and packed AD ABI.
Independent counterexamples verify mathematical limits; they do not rerun the
private WRF campaign. Existing host measurements keep their original provenance.

## Checklist

- [x] R1 — Reject masked and non-finite frame inputs before tensor conversion;
  cover stored-zero CCN, explicit synthesis, nonzero preservation, invalid policy,
  layout preservation, masks and NaN/Inf with portable synthetic inputs.
- [x] R2 — Correct the g4 zero-volume condition including `max(bg0, tiny(f32))`;
  add the in-band subnormal counterexample and correct the G3 comment.
- [x] R3 — Replace the unique-volume claim with the integer candidate interval;
  test `qg = 500*eta` and preserve the measured 280/271 existence split.
- [x] R4 — Distinguish the measured unclipped density-contrast proxy from actual
  number residual; use emitted actual outflow/inflow in diagnostic accounting;
  test the sign reversal and clipping-weight counterexamples.
- [x] R5 — Make host per-dry-mass versus kernel per-volume interpretations
  explicit and conditional; remove unconditional physical-number conclusions.
- [x] R6 — Scope QIB conclusions to counter equality, the scalar-update interval,
  both moments' negativity and weak boundary enrichment; retain causal questions.
- [x] R7 — Run relevant portable oracle/harness regressions, inspect the final
  diff, and update Graphify.

## Measurement follow-through

These remain open scientific measurements, not implied by the portable fixes or
the fixed-forcing fixture check below. The physical host/kernel unit choice also
remains OPEN; no production conversion was selected or inserted.

- [ ] M1 — Recompute the ten-minute host residual from paired, actually applied
  outflow/inflow and explicitly identified density. Old proxy totals cannot
  reconstruct these quantities.
- [ ] M2 — Identify the first negative cell's scalar-update operands/tendencies
  before attributing the surviving negatives to a specific operator.

## Validation

- Frame-reader tests: **28 passed, 5 skipped** (the skips require the private
  SS wrfout). A separate temporary NetCDF4 file with a finite `_FillValue`
  confirmed that an actual masked `QNCCN` read raises `ValueError`.
- Focused number/melt tests: **163 passed, 7 skipped** (real-source generator
  tests require a host tree in the worktree).
- Full portable harness command, `python3 -m pytest harness/tests -q`:
  **1366 passed, 58 skipped, 305 deselected**. Undefined-name checks with
  ruff 0.14.4 and the C++ overlay static four-check also passed.
- Oracle, `cd oracle && python3 -m pytest -q`: **814 passed, 31 skipped,
  1 failed**. `test_sharded_forward_window_bitwise` requests 12 frames from
  the local forecast file, which has only 4, and raises `IndexError`. The same
  test fails at the same read with the unchanged canonical code. This is a
  reproduced local-fixture limitation, not a green full-suite claim; its
  assertions and input file were not altered to hide it.
- Actual Fortran `--nflux` validation: compiled the existing canonical legacy
  reference with `g33_fixture_multisubcycle_v1`, ran `12 rezero`, and analyzed
  all **255 interfaces** with the modified analyzer. Actual signed residual
  equals the density term plus the transfer-mismatch term within diagnostic
  roundoff in all six chain/column rows. For example, ice/2 gives
  `-2942159.980535507 = 102960.03818511963 - 3045120.018720627` on the operator
  measure. This is a fixed-forcing synthetic-column run, not the ten-minute
  evolving WRF case. Local JSON and build records are under
  `graphify-out/review-2638fb2/` (outside the public evidence corpus).
- Generated g1–g5 executable Fortran statements match the baseline exactly.
  Full generated source bytes match for g1/g2/g4/g5; g3 differs only in comments.
  Production `libtorch/`, runtime/coordinator physics and the packed AD ABI
  were not changed. No new mp37/mp137 host parity run is claimed.
- `git diff --check` passed. `graphify update .` rebuilt the worktree's derived
  graph (10,571 nodes / 17,671 edges at the first validation update). The
  canonical worktree's pre-existing wiki edits were left intact.

## Exhaustive follow-up audit (2026-09-05)

Scope: every changed file above, its diagnostic producers/readers, portable
tests, and the cited evidence supporting the review claims. This audit found
real omissions in the first correction; the checks above alone were insufficient.
It is not a repository-wide correctness proof or a rerun of the private WRF
campaign.

- [x] A1 — **Missing capture passed silently.** `g33_cap_interface._walk` skipped
  absent CAPIN/TOPOUT and returned an empty result. It now requires both feature
  families and validates the basis and registered arm before analyzing records.
- [x] A2 — **Conservative CAPIN used source units.** Its arrival fields omitted
  the destination metric factors. With upper/lower thickness 2/1, raw departure
  2 and actual arrival 4, the old reader reported -2 instead of zero. The
  producer now emits the applied mass and number operands, including the
  conservative N arms' density factors. The `capin_applied` feature marks this
  meaning. Old conservative streams must be re-emitted; old legacy streams
  remain valid. No transport update was changed.
- [x] A3 — **A local outflow/inflow difference was called a cap count.** The
  historical `interior_cap` key compares different interfaces around one cell.
  The report now labels it `diff` and explains what is counted. Surface-total
  agreement is no longer described as proof that every cap was inactive.
- [x] A4 — **Frozen size comparisons used the wrong denominator formula.**
  With `eps=R/N_observed`, comparison against `N_observed-R` gives mean-mass
  bias `-eps` and diameter bias `(1-eps)^(1/3)-1`, provided both inventories are
  positive. The old reciprocal formula treated eps as though its denominator
  were the corrected inventory. An independent q/N example (N=100, R=10)
  pins -10%, rather than the former -9.09%. These remain conditional aggregate
  comparisons at fixed mass, not measured forecast effects or bounds.
- [x] A5 — **Contradictory prose remained behind correction banners.** The
  profile coefficient finding still asserted per-dry-kg units and full-residual
  improvement; the transport finding still certified inactive caps from one
  surface ratio. Both are now conditional. QIB table labels, separate maxima
  versus paired transitions, and G3's unchanged-volume behavior are explicit.
  Historical numeric tables retain their original measurement/reconstruction
  scope; no new ten-minute result is inferred from them.
- [x] A6 — **Tests bypassed the producer/parser boundary.** Added real text-stream
  tests, old/new record compatibility checks, both diagnostic measures with a
  humidity gradient, endpoint/surface closure comparisons, and local Fortran
  round trips on the existing unequal-layer moisture-gradient fixture. The
  denominator fixture now supplies its actual interface records rather than
  passing because the reader silently omitted them.

Follow-up validation:

- Portable harness: **1,388 passed, 58 skipped, 308 deselected**; the local build tests are
  selected separately. Oracle again reports **814 passed, 31 skipped, 1 failed**
  on the same four-frame fixture limitation described above.
- Local `test_applied_interfaces_match_state_ledger_on_unequal_layers`:
  **3 passed** (legacy, conservative, cons_nmass). Each builds and runs both
  instrumented and uninstrumented variants for 12 calls. All **348 G33R records
  per arm** match as raw text/hex values. This certifies only these fixture runs.
- An additional operand check on those three arms verifies **432 conservative
  applied mass/number pairs** against the update's f32 metric arithmetic, bit
  for bit. All three arms emit **216 interfaces each**. Across both density
  measures and both moments, the largest endpoint/surface-ledger versus
  interface-sum gap is **1.23e-8** of the inventory/outflow scale; f32 state
  update rounding is retained rather than described as exact algebraic closure.
- Local build paths/provenance and numeric results:
  `graphify-out/review-2638fb2/audit-build-root.txt` and
  `audit_fortran_results.json`. No host sources were edited. The temporary host
  link was removed after the builds.
- Undefined-name lint, the C++ overlay static check and `git diff --check`
  passed. Production f32 physics and the packed AD ABI still have no diff.
- `graphify update .` completed: **10,585 nodes / 17,694 edges / 866 communities**.
  This updates the derived code graph; it is not a semantic verification of the
  scientific claims.

M1, M2 and the host/kernel number-unit contract remain open. Finding and fixing
these diagnostic errors does not substitute for those measurements.
