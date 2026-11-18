---
title: Native host-column TH16 f32 activation transition
type: source
date: 2026-11-12
---

# Native host-column TH16 f32 activation transition

The [packet](../../harness/evidence/native_host_column_f32_boundary_2026-11-12/README.md) uses the complete selected `(203,149)` host-call column from [[native-host-column-f32-2026-11-11]] as the fixed baseline for separate B=1 f32 value calls. It changes only initial potential temperature TH16. A coupled-mask search retains 23 sampled words and checks the activation `pow`/fraction comparison and the raw-rate/NCCN-cap comparison separately, while keeping the other four observed Boolean masks fixed.

Both sampled predicates, `sw_percent >= 0.48` and recorded fraction `>= 1`, transition across adjacent f32 TH16 words `43a00285`→`43a00286`. Final NC16 changes by −25,808 (3,226 output ULP). Complete installed/capture-off/capture-on 510-word outputs agree at each endpoint. This is a local discrete B=1 transition for the actual host-column *input*, not a perturbed WRF tile, a continuous boundary derivative or f32 AD. The source of `cloud_complete_evap`, physical budgets, host f64 DA and GK2A–RTTOV cost sensitivity remain open. Scientific and physical-unit statuses remain `INCONCLUSIVE`.
