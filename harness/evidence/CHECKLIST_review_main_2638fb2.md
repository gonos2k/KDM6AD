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
