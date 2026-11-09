---
title: Native D1-entry graupel slope tangents
type: source
date: 2026-11-09
---

# Native D1-entry graupel slope tangents

The [evidence packet](../../harness/evidence/native_d1_entry_slope_cpp_ad_2026-11-09/README.md) follows initial QG17/BRS17 directions through the native-16 **entry preamble** slope consumed by D1 and #563's `gfac_melt`. This entry `pre` differs from post-D1 `pre1`. The ProgB entry `brs_input` also differs from the later `state_pre.brs` rebind to `pre.progb.bg`.

For the selected f64 branch, source-order ProgB computes density from `qg/max(brs_input,1e-15)`, applies its `[100,900]` clamp, and computes `bg=qg/rhox`; stored values match by raw bits across 25 cases. The slope input-chain JVP has QG, `dend`, and `pidn0g` terms. The entry slope handoff to the D1 factor operand matches by raw bits. `pidn0g` has no separate native D1 producer tap: its value and JVP are isolated C++ source and graph evidence, not an independent native-host handoff.

The earlier upstream native-17 density-cap crossings are distinct from native-16 entry density: at the large QG high endpoint the latter is exactly 900, while the large BRS low endpoint is `899.9999999999999`. Six entry signals have 60 central comparisons over ten accepted pairs; two use a declared four-output-ULP floor. Three small-step pairs lack independent cap capture. This one-column, one-level result does not establish complete `pidn0g` or melt-amount production, active boundary derivatives, physical budgets, operational f32, host AD or GK2A–RTTOV cost sensitivity. Scientific and physical-unit statuses remain `INCONCLUSIVE`.
