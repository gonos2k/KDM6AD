---
title: Native QNC producer and QI boundary writer — 2026-10-28
type: source
date: 2026-10-28
---
# Native QNC producer and QI boundary writer

Following [[native-qnc-representative-boundaries-2026-10-28]], four
full-domain READY40→60 s host runs traced the rejected α=0.25 T/Q candidate
and its control with recording off/on. Forward KDM heating and radiation were
active. Both off/on endpoint pairs and application ACKs match by bytes, and
the endpoints match PR #468. The canonical host source was not changed.

At native `(113,70,12)`, the RK2 ordinary advection trace records the first
control/candidate **applied tendency** difference after the X flux update.
The Y lower face already differs, but both cumulative tendency words remain
equal after Y. The Z update carries the difference to the QNC RK input. A
source-compatible FMA candidate reproduces both stored axis sequences;
the compiler instruction sequence is not identified. RK3's outgoing limiter
is active in both cases and has the same scale word, while its availability,
flux and tendency words differ. This selected-cell trace is not a general
positivity rule or a domain conservation budget.

At native `(1,168,33)`, both cases write QI `00000007` in the RK3 moist-state
update. The following conditional `flow_dep_bdy` call leaves control QI zero
and candidate QI `00000002`; the candidate's positive result is consistent
with its interior-copy branch. The donor value and boundary velocity were not
directly recorded. At `(155,120,15)`, both cases write QC from zero to
`354ECF22` in the RK1 moist update while NC is still zero.

The candidate still loses 54 fixed-M0 profiles and 378 channel cells. Its
full-support RTTOV cost and a second accepted analysis remain unavailable.
Raw number units, a physical mass/number budget and a full-host derivative
are not certified. See the [report](../../docs/NATIVE_QNC_ADVECT_QI_PRODUCER_20261028.md)
and [hash-bound packet](../../harness/evidence/native_qnc_advect_qi_2026-10-28/README.md).
