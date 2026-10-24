---
title: Restricted full-domain KO7 confirmation
type: source
date: 2026-10-25
---

# Restricted full-domain KO7 confirmation

The [report](../../harness/evidence/native_satellite_restricted_2026-10-25/REPORT.md)
records one actual restricted T/Q confirmation over all 65,988 native columns.
It keeps the original 381,528 baseline-supported channel cells and freezes
both controls in 25 original B512 blocks. The parent PR447 result remains
`COMPLETED_NO_ACCEPTABLE_UPDATE`; this is a separate post-hoc candidate on the
same scene.

The source-bound candidate uses alpha=1 and control z SHA-256
`1177f076e4d8421bfe855f3fd9e064d54bedcf353fcda211c35a4d7059710c38`.
Its actual cost is 11.144979224162192 versus the parent 11.153458878209252,
with all frozen support retained. This is acceptance under the declared local
fixed-support cost rule; it is not convergence, held-out validation, forecast
skill, or an operational analysis cycle.

The call ledger records 129 KDM value-only forwards and 129 fresh RTTOV direct
calls, with no K, JVP/VJP, host, or RK calls. A saved-output audit checks all
129 partitions against the parent baseline in frozen blocks and the original
alpha=1 proposal elsewhere. The public [50-artifact bundle](../../harness/evidence/native_satellite_restricted_2026-10-25/data/publication_manifest.json)
passes the NumPy arithmetic replay without executing private physics.

Full-domain H_RATE, QV_RATE and QC_RATE arrays include baseline, candidate and
candidate-minus-baseline fields. Candidate finish formulas match all 2,573,532
values per rate bitwise; baseline QV/QC relations also match, while baseline
H_RATE remains qualified by the pinned parent applied-physics audit. The
reported `t_new_after` is a moist-theta perturbation relative to t0, not
physical temperature. The actual-call DEN×DELZ water diagnostics are
unweighted sums over columns, not regional mass; precipitation and closed
water, energy, and number budgets are absent. Legacy number units, pixel UTC,
provider navigation, and IR133 identity remain qualified.
