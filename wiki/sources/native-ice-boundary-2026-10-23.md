---
title: Native ice boundary attribution
type: source
date: 2026-10-23
---

# Native ice boundary attribution

The [follow-up](../../harness/evidence/ice_boundary_attribution_2026-10-23/REPORT.md)
fixes diagnostic reduction order with a versioned binary64-products/`math.fsum`
contract. It preserves the #432/#434 captures and records ULP differences in
additive v2 ledgers. The same-call physical balance is unchanged.

Executed internal ice records on the same native 39-level column show
normalized velocity inputs selecting one substep, followed by raw velocity
consumption at the first ice handoff. Five post-update-reservoir arrival caps
leave source departure exceeding receiver arrival by
0.0012979597722250025 kg m-2, with zero bottom export. This accounts for the
QI sedimentation loss from [[same-call-water-budget-2026-10-22]].

The physical legacy map is unchanged and water closure still fails. The NI
ledger is conditional on the kernel volume coordinate, not a certification of
historical host payload units. Instrumented value/JVP/VJP and the existing
cleanup/applied-finish products are bit-identical to the control at one point
and fixed seeds; this is not a new FD/full-host/RTTOV certificate. It is distinct
from [[KDM6AD Forward Parity]] and accepted local AD milestones.
