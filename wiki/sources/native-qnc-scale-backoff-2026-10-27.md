---
title: Native QNC saved donor-scale backoff probe — 2026-10-27
type: source
date: 2026-10-27
---
# Native QNC saved donor-scale backoff probe

An offline counterfactual on the immutable [[native-qnc-seven-state-2026-10-27]] and [[native-qnc-saved-state-budget-2026-10-27]] packets lowers only the target outgoing limiter scale by one binary32 ULP. Six shared correction faces are recomputed and paired with the six neighbors; five stored face words actually change in alpha0.25. The seven-cell operator-weighted perimeter and outer face incidences stay exactly the same.

The alpha target's exact saved-input RK3 expression changes from `−1.838040504` to `+1.648786290` raw NC, and its arithmetic modes that matched the original run predict `+1.991152167`. All seven selected RK3 QNC states are nonnegative in the probe. This is not a new host run or a general one-ULP limiter rule. Physical NC units, domain-wide admissibility, a conservative applied number budget, KDM-after-RK response, candidate RTTOV cost and a second assimilation remain open.

See [report](../../docs/NATIVE_QNC_SAVED_SCALE_BACKOFF_20261027.md) and [hash-bound packet](../../harness/evidence/native_qnc_scale_backoff_2026-10-27/README.md).
