# What is open after PR #167, and what each would take

A reading list for the next review, assembled from the findings' own "not
established" sections rather than from memory. Ordered by what the evidence
says is load-bearing, not by what is cheap.

## 1. The graupel melt: a fix exists on paper and is not made

`REQUEST_freeze_lift_graupel_melt_guard.md` is filed and unanswered. The
mechanism is settled -- `rhox` is computed only under
`qg > qcrmin .or. brs > brs_min` and clamped to `[100, 900]` once computed, so
the only route to infinity is it not being computed, while the melt asks
`qg > 0.` -- and the operands were read from the stream: `qg = 8.29644e-13`,
`brs = 9.21827e-16`, `t = 286.117 K`.

**Open:** the fix itself, which is frozen-code and not self-authorised. And one
measurement the request names as a prediction rather than a property: whether
the rain-NUMBER ledger moves at all. In the window the `nr` line is guarded off
but `qr`, `qg`, `t` and `brs` do change, and `qr` feeds later processes in the
same call.

**Scope of exposure is also open.** Four of five land columns fail; no sea
column does; `(100,142)` fails at the OPERATIONAL 20 s step and `(71,147)` only
at 30 s. The threshold belongs to the column. Nothing says where the next column
fails, and no WRF run has been checked for it -- only harness replays.

## 2. What `QNCCN` is decomposition-dependent THROUGH

Three implementations, none decomposition-invariant, and they disagree with each
other at `np = 1` (`FINDING_ccn_onetime_reference_v1`). The zeros are made
during the first step, never in the initial state, and `np = 1` produces 11 152
of them across every column while `np = 2` and `np = 4` produce 3 557 in the two
edge columns -- identical to each other, so it is not a trend in rank count.

**Open:** which stage assigns the zero. The sentinel established that nothing is
unwritten; it cannot say who wrote it. That needs per-stage instrumentation
recording writer stage, rank and tile -- the only item here that requires new
kernel code.

The halo-exchange question is also unsettled: `HALO_EM_INIT_5.inc` carries
`scalar` and appears both before the CCN block at `start_em.F:1435` and after it
at 2016 and 2562, possibly on different branches. That needs a branch trace, not
a grep.

## 3. Whether the `np = 4` seam matters

`FINDING_mpi_growth_is_not_distinguishable_v1` bounds the SIZE argument: a
one-ULP perturbation of one prognostic reaches as many fields as the
decomposition does. **That is not "no defect"** -- it withdraws only the
inference from "large at ten minutes" to "wrong in the dynamics".

**Open:** whether the seam difference is harmless, which the size argument does
not decide; the processor-grid control (`1x4`, `2x2`, `4x1` at the same rank
count) that would separate seam direction, which `run_ss_case` cannot express
today; and a matched-magnitude ENSEMBLE rather than one realisation.

## 4. Ice, which needs a different fixture and not another arm

Per-call admissibility is empty on every base available -- `legacy`,
`conservative` and `cons_nmass` all admit 0 of 36 while `qr` admits 22, so the
instrument works and ice does not close. The conservative correction collapses
the tail by two orders (max 1.000 to 9.3e-03) and barely moves the median.

**Open:** a fixture where ice sediments without converting -- cold enough that
melting is off, thin enough that riming and aggregation do not fire -- or a
ledger carrying the conversion terms. Building `cons_nmass_dry` first would
produce an arm with nothing to be judged over.

## 5. Provenance the campaign cannot yet show

`run_ss_case.py` now writes `wrf_exe_sha256`, so future comparisons are
checkable. Every run made BEFORE 2026-08-24 has none, and the perturbation
baseline is one of them: an independent run shows the binary held over 08-22 to
08-23, and nothing spans 08-24.

**Open:** whether to re-run the perturbation comparison now that runs record
their binary. It is one 10-minute run and would convert an argued premise into a
shown one.

## What is NOT open

Deliberately, so the next review does not re-litigate them:

- **The metric protocol.** Duplicate, misplaced, unknown-value and
  unknown-arm declarations all refuse, and the measure is part of run identity.
- **`TRUSTED_REFS`.** `refs/tags/` stays out; a pushed tag is established as an
  anchor by `_commit_states` through `remote_tags()`, one layer up.
- **The screen's width.** Every call site takes the stream's declared real
  width, and a stream declaring two is refused.
- **Whether the `-inf` was contamination.** It was not; that retraction is in
  `FINDING_shared_fixture_contaminates_v1`.
