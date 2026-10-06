---
title: Native host dry-mass coordinate audit (2026-10-06)
type: source
date_modified: 2026-10-06
---

The [source/snapshot audit](../../harness/evidence/REPORT_native_host_mass_reference_2026-10-06.md)
binds the layer dry-mass reference to active hybrid-coordinate equations and the
retained frame's MU/MUB, C1H/C2H and DNW. It uses the same selected C5 column as
the signed analysis inventories; it does not add another meteorological case.

Decoded-f64 coordinate weights total 9706.015299 kg/m²; the earlier diagnostic
rho_d*dz weights total 9711.775806 kg/m². Logarithmic hypsometric pressure depth
totals 9711.774791 kg/m² and explains the dominant difference. Its remaining
disagreement with the diagnostic is reported, without claiming a complete
roundoff or stage attribution. Explicit NumPy f32 arithmetic is separate from
captured live Fortran arithmetic.

The initial analysis water increment is 0.101509463 kg/m² on this coordinate
reference, versus the earlier 0.101512531 kg/m² on diagnostic weights. Earlier
numbers and their conventions remain preserved. Identifying the host snapshot
reference does not automatically change optics/runtime policy, certify a
historical build's current-source identity or close net boundary budgets.

Map factors belong to horizontal geometry/divergence, while this measure is per
physical m². Physical cell totals were not evaluated. Future S17 accounting
requires stage-bound mass fields, compatible enthalpy and net flux/work terms;
number/threshold calibration and product/error policies remain separate.

A subsequent Green/Red audit reproduced a crossed-input counterexample in the
historical generator; the actual retained pair matches. The
[guarded replay](../../harness/replay_native_host_mass_reference.py) pins the
execution receipt and checks grid/column identity and all twelve background
state components before invoking the unchanged original arithmetic. The
[regression tests](../../harness/tests/test_replay_native_host_mass_reference.py)
reject crossed columns and background components. This hardening leaves the
original executed source/result and physical approval limits unchanged.
