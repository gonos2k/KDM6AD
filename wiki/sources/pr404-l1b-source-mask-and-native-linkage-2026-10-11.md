---
title: AMI L1B source-mask repair and same-date native-input boundary
type: source
date: 2026-10-11
---

# Source-mask capture and native-date linkage

PR403's raw sidecar read disabled automatic masking before calling getmaskarray, losing NetCDF source-missing semantics. Actual netCDF4 reproduces this P3. A separately versioned future writer now preserves exact uint16 words, library source masks (including validity attrs), image-edge padding and packed DQF independently. The executed PR403 helper, frozen plan, result, CSV and private payload remain unchanged.

A one-time additive sidecar capture read only eighteen existing5×5 raw slices. All450 actual cells have source-mask=false and padding=false; words and embeddedDQF match the original saved payload. This is corrected metadata preservation, not a new BT decode, acquisition, RTTOV/KDM/optimizer or model run. Nine actual-NetCDF regressions and sixteen unchanged LA-reader tests pass. [Result](../../harness/evidence/pr404_l1b_source_mask_2026-10-11/MASK_REPAIR_RESULT.json) and [report](../../harness/evidence/pr404_l1b_source_mask_2026-10-11/COORDINATOR_REPORT.md) bind the executed path and limits.

The [bounded availability audit](../../harness/evidence/pr404_l1b_source_mask_2026-10-11/NATIVE_AVAILABILITY_REPORT.md) found only July19 original native IC/BC in the named roots/retained receipts; BC ends July19 09UTC. No matching original July20/21 inputs were located there. This is not a global archive-absence claim. New-date baseline/analysis/audit and physical interpretation remain pending in the [checklist](../../harness/evidence/CHECKLIST_pr404_l1b_source_mask_2026-10-11.md); neither date relabeling nor external model/reanalysis substitution is allowed, and the existing archive question is not repeated.

[[pr403-l1b-heldout-scenes-2026-10-11]] remains the two observation-scene intake evidence. GK2A AMI L1B is the only satellite input; other sensors/L2 are deferred extensions. The [user78/100 rubric](../../harness/evidence/AMI_L1B_MANAGEMENT_RUBRIC_2026-10-11.md) is a new management baseline atPR403, not a conversion of56/75 or a performance statistic. This fix assigns no score increase.

## Independent audit follow-up

Three new reviewers found future-writer download-provenance and completion-order gaps, plus empty-schema/external-plan and axis/validation metadata omissions. [Team resolution](../../harness/evidence/pr404_l1b_source_mask_2026-10-11/audit_20261011/TEAM_AUDIT_RESOLUTION.md) records the bounded priorities and repairs. Newv3 is the future writer; originalv2/raw-capture sources and all original manifest hashes remain unchanged. Thirty-six local cases cover9 actual-NetCDF masks,11 synthetic publication/provenance cases and16 unchanged LA-reader tests. Synthetic integration is separate from real scene/model execution; same-date native analyses remain pending and no score increase is assigned.
