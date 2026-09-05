# Follow-up audit of merged PR #205

Baseline: `b771d0d4df3a2f64d2eaa45372c8e1aff7f18469`, 2026-09-05.
PR #205 is merged, with its five CI checks successful. This audit revisits its
review checklist, number-record producers and consumers, linked evidence and
portable/local regression coverage. It found omissions after the earlier audit;
neither audit is a proof of correctness for the entire repository or host.

## Corrections

- [x] B1 — **A second arrival consumer bypassed validation.**
  `g33_metric_trajectory` accepted old conservative CAPIN records and silently
  accepted missing CAPIN/TOPOUT. On unequal layers it could report -2 where the
  applied residual is zero. Both arrival consumers now share
  `require_applied_interface_records`; all conservative variants require the
  `capin_applied` marker, while old applied legacy records remain readable.
- [x] B2 — **The trajectory report still called the density term the full
  residual.** Its text and linked findings now distinguish the metric/trajectory
  split of the density contribution from the additional transfer-mismatch term.
  The report prints all three quantities. Follow-up C3 below changes the main
  decomposition to full residuals and explicitly identifies the output quantity.
- [x] B3 — **An incomplete comparison could look complete.** Counterfactuals
  now reject changed layer geometry, retain missing whole columns as incomparable
  rows, and refuse unknown arrivals rather than dropping their contributions.
- [x] B4 — **Zero denominators and cancellation were mishandled.** A zero
  density baseline now prints an undefined ratio without a formatting exception.
  Absolute interface mismatches accompany the net sum; `measure_only` means net
  agreement under its existing threshold, not cap inactivity at every interface.
- [x] B5 — **The old conservative ice zero-mismatch test hid producer rounding.**
  The local Fortran leg initially failed: the corrected producer emits a 1-ULP
  arrival difference at inverted/call 2/column 2/interface 1→2. The test now
  verifies 540 actual arrival operands bitwise against `(dn_out*dz_up)/dz_lo`
  in f32 and pins the nonzero residual `-0.05458984465803951`. Its former
  exact-zero expectation was removed on this measured evidence; no tolerance
  was widened to conceal the discrepancy. The ice finding records the correction.
- [x] B6 — **Related explanations overstated their checks.** Evidence and test
  descriptions now distinguish ideal profile arithmetic from f32 rounding,
  aggregate agreement from per-interface agreement, and extension to another
  chain from an independent measurement apparatus. Historical tables are labeled
  as historical; the archived claim ledger was not rewritten.

## Validation at 8efdcb2

- Full portable harness: `python3 -m pytest harness/tests -q` — **1,410 passed,
  58 skipped, 308 deselected**. The new portable capture/decomposition module
  contributes 22 tests, including the retained 1-ULP counterexample.
- Local Fortran trajectory and ice-density modules: **23 passed** after
  correcting the measured false-zero expectation (initial run: 22 passed,
  1 failed). This compiles the existing multisubcycle fixture and exercises the
  perturbed profiles. No host source was edited; the temporary host link was
  removed after each run.
- Reanalysis of the previously captured legacy/conservative/cons_nmass
  moisture-gradient streams: all **18 chain/column comparisons** give exactly
  the same full interface residual in the two Python analyzers. This verifies
  agreement of the readers on retained synthetic Fortran output, not a new
  evolving-host measurement or an independent physical validation.
- Local evidence: `graphify-out/audit-pr205/trajectory_fortran_reanalysis.json`
  records those 18 comparisons. `conservative_ice_rounding.json` records the
  driver hash, operands, 540 bit checks and the density matrix; its six raw
  streams are retained beside it. Local generated artifacts are not in the
  public evidence corpus.
- Undefined-name lint (ruff 0.14.4) and `git diff --check` passed.
  `graphify update .` refreshed the derived structural graph. No new oracle or
  C++ run is claimed for this Python-diagnostic/documentation follow-up; their
  PR #205 CI results and the known private four-frame oracle fixture limitation
  retain their previous scope.

## Still open

The original checklist's M1 (paired applied residuals in the ten-minute evolving
host run), M2 (first-negative QIB scalar-update operands), and host/kernel number
unit contract remain open. The synthetic-column Fortran runs here do not close
those questions. Production f32 physics, host sources, and the packed AD ABI have
no changes in this follow-up. No new mp37/mp137 host parity run is claimed.

The canonical wiki is maintained separately from this isolated public-code
worktree. Its session log records the audit, local evidence, PR state and pending
measurements, preserving unrelated user edits.

## Follow-up review: complete call and mathematical contracts

- [x] C1 — **Explicit LC05 initialization at the remaining callers.** The
  full-domain runner, real-innovation fixture and regime-2 bootstrap now request
  `init_profile`, matching both full-domain smoke modes. Forecast-output replay
  and coordinate/observation inspection retain stored data. A substitute reader
  observes all six actual initialization call paths before external asset I/O;
  no GK2A or RTTOV execution is needed for this contract test.
- [x] C2 — **One applied-interface pairing implementation.** Both analyzers now
  use `g33_number_transport.applied_interfaces`, which validates capture and
  applied units, then pairs TOPOUT/CAPIN departures with lower-cell arrivals.
  No consumer silently skips unknown arrivals.
- [x] C3 — **Full residual decomposition, not just corrected density labels.**
  One `R(w,F)` function computes baseline, counterfactual and actual residuals.
  The counterfactual fixes both applied transfers. The offset counterexample
  yields weight effect -.50 and transport response 0; a separate fixed-departure
  case checks response to a changed arrival. Output identifies its full-residual
  quantity so historical density-only JSON cannot be read as the same result.
  Original upper density is used directly, rather than reconstructed from a
  rounded density difference. The report and JSON share one analysis execution.
- [x] C4 — **Theory before patching.** Root AGENTS.md now requires mathematical,
  engineering and numerical consistency checks before implementation: identify
  units and the full quantity, trace every producer/consumer/call boundary, and
  distinguish real arithmetic from executed f32/f64 operations. This user-requested
  rule is also present in the canonical worktree.

Follow-up validation:

- Full portable harness: **1,414 passed, 58 skipped, 308 deselected**. The
  portable trajectory module now has 26 tests, including the offset, changed
  arrival, original-density rounding and single-analysis CLI cases.
- Actual Fortran trajectory/ice-density and unequal-layer state-ledger tests:
  **26 passed**. These exercise both consumers' common pairing, independent
  endpoint/surface budgets, and the 540-arrival f32 check described above.
- LC05 caller and reader tests: **34 passed, 5 skipped**. Six actual call
  boundaries request explicit initialization. The broader related oracle set
  gives **77 passed, 12 skipped**; live GK2A/RTTOV tests remain asset-gated.
- Full local oracle: **820 passed, 31 skipped, 1 failed**. The failure is the
  same `test_sharded_forward_window_bitwise` read beyond the existing four-frame
  private file, previously reproduced on unchanged canonical code. No data or
  assertion was altered to hide it.
- Reanalysis of retained conservative ice streams gives 15 comparable rows and
  zero observed rounding gap in `weight_effect+trajectory=residual_change`.
  This finite fixture check does not prove bit-exact algebra for arbitrary
  inputs. Local results are in `graphify-out/audit-pr205/full_residual_decomposition.json`.
- Undefined-name lint, diff checks and Graphify updates passed. The canonical
  and PR worktrees contain identical Theory Before Patching instructions.
