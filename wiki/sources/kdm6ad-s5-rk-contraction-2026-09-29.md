---
title: S5 RK boundary and contraction counterfactual
source: harness/evidence/REPORT_S5_rk_boundary_contraction_2026-09-29.md
---

# S5 RK boundary and contraction counterfactual

Selected owned `u_2/v_2` inputs agree immediately before the first RK
`small_step_prep` and acquire nonzero, layout-dependent residuals at its
exit. Selected owned `mu_2` remains equal through `advance_mu_t` entry and
differs at its exit. An isolated one-object compile with the same saved
source and `-ffp-contract=off` makes the sampled RK1 U/V exit words exactly
zero in both 1×1 and 2×1 layouts, but 28/254 saved host variables still
differ after 20 s. The output is a local arithmetic explanation, not a
whole-host or default-path fix. See the [run report](../../harness/evidence/REPORT_S5_rk_boundary_contraction_2026-09-29.md).
