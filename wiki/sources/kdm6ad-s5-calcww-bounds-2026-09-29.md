---
title: S5 calc_ww_cp bounds counterfactual
source: harness/evidence/REPORT_S5_calcww_bound_counterfactual_2026-09-29.md
---

# S5 calc_ww_cp bounds counterfactual

The public exact2 caller-word projection and pinned private `calc_ww_cp`
source support an isolated same-input bounds comparison. Recompiling the
extracted routine with the baseline optimization reproduces all 45,120
selected archived stage-2 `ww` words exactly. Changing only `its:ite` yields
the same 9,890/9,970 differences at i=117/234. Disabling vectorization for
the routine removes those selected bound differences; disabling contraction
also removes them but produces a different common answer.

This identifies a selected numerical layout mechanism, not a whole-host fix.
S5 remains open until an isolated one-object WRF build is exercised in local
1×1/2×1 MPI runs and the full saved trajectory is compared. See the
[run report](../../harness/evidence/REPORT_S5_calcww_bound_counterfactual_2026-09-29.md).
