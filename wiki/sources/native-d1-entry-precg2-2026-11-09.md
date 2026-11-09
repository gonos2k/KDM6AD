---
title: Native D1-entry precg2 production
type: source
date: 2026-11-09
---

# Native D1-entry precg2 production

The [evidence packet](../../harness/evidence/native_d1_precg2_producer_cpp_ad_2026-11-09/README.md) follows initial QG17/BRS17 directions through the selected native-16 entry `pre` ProgB and its `precg2` handoff to the #567 D1 melt producer. This entry is before D1, distinct from later `pre1` and `pre2` rebuilds. The active calculation uses density-interpolated `avtg` and `bvtg`, then `bvtg2=(2.5+bvtg*0.5)+mug`, `g5pbgo2=exp(lgamma(max(bvtg2,EPS)))`, and source-order `precg2=(((4*0.31)*safe_pow(avtg,0.5))*g5pbgo2)`. Its selected JVP separates the `avtg` and gamma-factor input terms, which share upstream state.

Across 25 cases, independent source-order `avtg`/`bvtg` interpolation and `bvtg2` match raw bits, as does the `precg2` product using the captured C++ gamma word. Independent Python gamma evaluation differs by up to five ULP locally; portable arithmetic bounds and raw C++ producer-to-consumer equality are separate checks. Baseline and two joint large-step endpoints have native captures of `avtg`, `bvtg`, and `precg2`; `bvtg2` and `g5pbgo2` have no independent native-host tap, and other endpoints are isolated C++ evaluations.

Of 50 accepted central differences, 36 meet `10^-6` signal-relative error; 14 use a declared four-output-ULP rounding floor, as do 13 one-sided comparisons. Floor acceptance is roundoff-scale evidence, not `10^-6` relative accuracy. Upstream native-17 density-cap crossings and the native-16 entry boundary are distinct. Inactive ProgB, active gamma and interpolation boundaries, other raw-rate operands, QV/T directions, operational f32, physical units and budgets, host AD and GK2A–RTTOV costs remain open. Scientific and physical-unit statuses are `INCONCLUSIVE`.
