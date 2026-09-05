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
  The report prints all three quantities. Existing JSON keys retain their names
  for compatibility, with their meanings documented.
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

## Validation

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
