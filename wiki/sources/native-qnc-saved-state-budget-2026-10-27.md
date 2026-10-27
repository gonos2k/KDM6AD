---
title: Native QNC saved seven-cell state budget — 2026-10-27
type: source
date: 2026-10-27
---
# Native QNC saved seven-cell state budget

This is an offline companion to [[native-qnc-seven-state-2026-10-27]] and [[native-qnc-weighted-ledger-2026-10-27]]. It uses the immutable PR461 binary32 trace. The hardened aggregate pass requires both RK3 QNC and unchanged `SCALAR_OLD`; a one-ULP old-buffer mutation is rejected in each saved case.

Exact rational decomposition of the target `(221,63,6)` gives four terms: saved-face/PD baseline, PD old-buffer storage, recorded-versus-face advection arithmetic, and final RK arithmetic/storage. Their sums exactly equal QNC `+3.442540646` (control) and `−3.814399242` (alpha0.25). For the candidate, even the exact fixed-input baseline is slightly negative (`−0.062541972`). The seven-cell operator-weighted ledger cancels 12 internal face-component pairs, retains 30 outer incidences and explicitly accounts for PD source plus nonzero arithmetic differences; its residual is exactly zero.

The saved target KDM FP64 records show candidate NC `−3.8143992424 → 0` between KDM input and output while QC remains positive. This locates a call boundary, not an individual process. The ledger uses raw NC coordinates and an operator-derived weight; physical particle-number units, full-step/domain conservation, actual FMA instructions, candidate RTTOV cost and an accepted analysis remain open. There were no new model or RTTOV calls.

See [report](../../docs/NATIVE_QNC_SAVED_STATE_BUDGET_20261027.md) and [hash-bound packet](../../harness/evidence/native_qnc_state_budget_2026-10-27/README.md).
