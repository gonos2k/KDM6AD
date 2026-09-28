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
unsafe-logger runs are diagnostic only. The next opt-in correction should
bypass an exact-zero numerator without dropping the positive `baacw` transfer,
then check the resulting mass, volume and downstream process path. S10 and
physical trace-graupel policy remain open. See
[the native report](../../harness/evidence/REPORT_S10_stage2_pair_2026-09-29.md).
