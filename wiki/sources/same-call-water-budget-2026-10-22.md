---
title: Same-call fp64 water accounting
type: source
date: 2026-10-22
---

# Same-call fp64 water accounting

The [experiment](../../harness/evidence/same_call_water_budget_2026-10-22/REPORT.md)
captures before/after state, actual fp64 forcing and total surface export from
one legacy KDM call. The native 39-level result is bit-identical to #433's
kernel output. Water decreases by 0.0012985492047658913 kg m-2 while surface
export is zero: **closure fails**. Cleanup removes a further
5.449926229476307e-7 kg m-2 and is accounted separately.

`rain_increment` already includes rain/snow/graupel/ice; snow/ice and graupel
diagnostics overlap it. The weights are this call's DEN×DELZ, not previous
captured f32 weights or MU/g. These are [[KDM6AD]] research-path water
measurements, distinct from [[KDM6AD Forward Parity]] and local derivative
certification. Historical number payloads, full-host RK and energy/number
budgets remain outside the result.

The [contract](../../docs/SAME_CALL_WATER_BUDGET.md) distinguishes complete
diagnostic recording from conservation. An independently attributed fp64
runtime overlay preserves the full response bitwise. After correcting the
top-first pre-sedimentation orientation, it localizes about 0.00129795977 kg m-2
loss to sedimentation, entirely QI, and 5.89432541e-7 kg m-2 to microphysics.
Internal departure/arrival and bottom-flux attribution remain open.
