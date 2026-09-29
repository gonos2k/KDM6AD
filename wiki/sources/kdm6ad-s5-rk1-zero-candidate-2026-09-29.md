---
title: S5 RK1 zero-store candidate
source: harness/evidence/REPORT_S5_rk1_zero_candidate_2026-09-29.md
---

# S5 RK1 zero-store candidate

An isolated opt-in host build replaced only the two first-RK
`small_step_prep` U/V cancellation stores with exact zero. The selected
owned perturbations become +0 in both local 1×1 and 2×1 mp237 runs, while
same-executable logging stays raw-bit noninvasive. After 20 s, 28/254
saved variables still differ across MPI layouts. This is a local negative
candidate, not a default fix or whole-host approval. See the
[run report](../../harness/evidence/REPORT_S5_rk1_zero_candidate_2026-09-29.md).
