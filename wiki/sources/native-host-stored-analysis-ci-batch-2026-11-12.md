---
title: Host-column saved analysis and evidence CI batch
type: source
date: 2026-11-12
---

# Host-column saved analysis and evidence CI batch

The [batch report](../../docs/NATIVE_HOST_STORED_ANALYSIS_CI_BATCH_20261112.md) reuses [[native-host-column-f64-da-2026-11-12]] without new KDM calls. One TH16 direction supplies 2,808 full-output FD–JVP diagnostics across two interior centers and three steps. At the smallest step, six lower-side and seven upper-side output words resolve, all at native level 16; equal-word signals remain unresolved. Exact f32 input widening and separate baseline output comparison give 101/468 rounded f32/f64 mismatches spread across fields and levels, with no stage-cause claim.

Archived #583 CI logs show the required Oracle job took 25m44s, including 10m17s and 10m12s for serial evidence suite modes; installation took 24s. A checked-in suite registry and isolated two-worker runner aim to shorten wait while preserving the single required Oracle status, complete normal/optimized coverage and explicit failures/skips. Pinned requirement files key the pip download cache; every run still installs and verifies packages. Actual post-change speed remains a CI measurement, not a promised ratio. The [shared capture plan](../../docs/NATIVE_HOST_COLUMN_SHARED_CAPTURE_PLAN_20261112.md) inventories the next branch, physical-budget and state+forcing fields for the same selected host input. Scientific and physical-unit statuses remain `INCONCLUSIVE`.
