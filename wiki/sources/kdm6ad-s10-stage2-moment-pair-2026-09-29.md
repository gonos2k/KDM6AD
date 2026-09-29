---
title: KDM6AD S10 selected cold graupel pair
type: source-note
date: 2026-09-29
---
# S10 selected cold graupel pair

An isolated mp237 20-second capture follows one cold stage-2 cell from
`qg=brs=0` to positive graupel mass and zero stored bulk volume. The sole
nonzero captured mass rate is `paacw`; its paired `denr`-converted volume rate
`baacw` is also positive. The source volume expression additionally contains
`pgdep/rhox`; `pgdep=0` here, but preceding inactive `ProgB_param` does not
define the `INTENT(OUT)` density. The tap intentionally never reads that
undefined value. It cannot establish the quotient's numeric result or a full
volume budget.

The corrected logger removed inherited numeric S10SHAPE writes of unassigned
outputs. Log OFF/ON histories match raw-bit on both saved frames. The earlier
unsafe-logger runs are diagnostic only. The old C-arm predicate also requires
current `qg==0`; it misses this event because the mass store makes qg positive
before the volume quotient. See [the pair report](../../harness/evidence/REPORT_S10_stage2_pair_2026-09-29.md).

A subsequent exact-zero opt-in guard preserves `baacw` while skipping the
undefined quotient for zero `pgdep`. Its first native logging-OFF attempt
stopped before the selected pair cell: at `(j,i,k)=(84,117,17)`, a negative
nonzero applied `pgdep` encountered an unassigned density from the preceding
`ProgB` call. The failure-only record did not read that density. Current
`qg=2.7578711524256505e-5` is after the mass store; it cannot be treated as
the earlier `ProgB` input. The producer permits a smaller positive graupel
mass than the density gate, so the two activation contracts can differ.
The experiment has no completed guarded history or OFF/ON parity. A physical
rule for nonzero deposition/sublimation in that state remains open, alongside
other ProgB outputs and the full moment/AD path. See [the stopping-witness
report](../../harness/evidence/REPORT_S10_exact_zero_pgdep_2026-09-29.md).

A later opt-in experiment combined the existing midpoint ProgB policy with
exact-zero-rate bypasses at all four graupel-density quotient consumers. Its
one-rank, 20-second mp237 logging-OFF/ON pair completed with identical raw-bit
histories and finite saved fields. Against the earlier midpoint-only control,
only QIB differs at 20 seconds; QGRAUP does not. This establishes a bounded
executable candidate, not the physical validity of 400 kg m⁻³, a process
budget, or a differentiable contract. The action counts and applied heat/volume
terms were not captured for this run, so S10 remains OPEN. See [the hybrid
report](../../harness/evidence/REPORT_S10_midpoint_rate_zero_2026-09-29.md).

The Python oracle and C++ ProgB leaf now have a default-off form of this
midpoint trace rule. For inactive positive qg it returns `rhox=400`, projects
`brs=qg/400`, and creates the density-derived bundle; for inactive zero qg it
returns a zero bundle. The checked derivatives are local to a fixed branch.
The later coordinator extensions below carry this option beyond the leaf,
but the leaf check itself does not replay the native hybrid trajectory.

The Python oracle now threads the same default-off option through its own
ProgB preambles, sedimentation reslopes and four rate/density quotients. A
small mixed-state one-step check remains finite and preserves a separately
recorded default-off f64 baseline. The oracle has an extra post-D1 `pre1`
re-slope, so this is a port-specific experimental trajectory, not an exact
replay of all seven native ProgB call sites. The validity check is eager and
value-only; checked derivatives remain local to unchanged branches. Physical
policy approval remains open.

The C++ coordinator now has the same default-off experimental path at its
existing ProgB calls. It replaces the persistent inactive-output bundle only
when opted in and guards the four density quotients, including the D1 capped
volume amount used by the inline state update. Selected f32/f64 value and
local-gradient checks pass. This does not establish equality with the native
seven-call schedule, full applied budgets, transformed AD, or approval of the
midpoint density; S10 remains OPEN.

A subsequent isolated mp237 pair added bounded success-action records to the
same hybrid. Its 0 and 20-second logging-OFF/ON histories remain raw-bit equal;
all saved numeric cells are finite. The selected stream contains 135 guarded
actions: 24 nonzero `pgmlt` divisions and 111 exact-zero bypasses across
`pgdep`, `pgevp` and `pgeml`. One `pgdep` bypass after ProgB producer site 5
at the cold pair `(j,i,k)=(2,142,17)` has zero density before the stage-2 mass gain. The
recorded numerator is zero, so this bypass does not cause the positive mass
or volume change in that row. No action row was observed there after ProgB
producer site 6 or 7. These facts identify executed branches in selected cells, while physical
density choice, all applied mass–volume–heat terms, native seven-call parity
and AD remain open. See [the success-action report](../../harness/evidence/REPORT_S10_hybrid_success_2026-09-29.md)
and its [path-redacted receipt](../../harness/evidence/S10_midpoint_rate_zero_run2/receipt.json).
