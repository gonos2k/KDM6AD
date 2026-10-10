---
title: PR399 lower-layer structure and neighbor H
type: source
date: 2026-10-10
---

# PR399 lower-layer structure and neighbor H

The [checklist](../../harness/evidence/CHECKLIST_pr399_vertical_neighbor_2026-10-10.md)
continues merged PR398 main `c81eab38`. The same stored native3×3 is used for
vertical diagnostics, and the fixed05:56 AMI geometry is used for eight new
neighbor H calls plus the input-identical reused center. No model M,
optimization, new forecast or observation acquisition occurred.

The saturation maximum lies near261m AGL and977hPa. Above it, the center
profile warms and dries between383m and536m, while virtual potential
temperature increases. This is a state description, not a measured PBL or
transport tendency. Native nonuniform heights are preserved. Endpoint q/T/p
partial terms and a finite-step remainder describe S changes, not process rates.

The raw vertical V2 record wrongly says891 adjacent pairs. The separate
count audit establishes297 valid pairs in324 lower-level rows, with51
temperature inversions and216 positive theta-v-gradient flags. Original
source/results/aliases remain intact; the future V3 correction was not run.

All nine H rows retain seven zero-quality channels. Model IR105 ranges
296.082–296.271K; even its minimum exceeds the observed patch maximum by
2.373946K. The difference is regional within the stated fixed geometry,
gas/reference/surface and paired-BT assumptions. It does not prove a unique
cloud/process cause or physical footprint matchup. The most favorable
neighbor was not selected as a new candidate.

Neighbor attempt1 omitted required fixture gas inputs and failed before H.
Manual source recovery used a separate attempt2 plan with actual offline
fixture checks; only the originally authorized eight H calls were made.
There was no automatic retry or repetition of completed H.

The canonical IC/BC symlinks point to REAL_EM V4.6.0 outputs forJuly19,5km
and39levels. Original upstream meteorological inputs and other-day archive
paths are not identified by those headers. The optional request for another
native archive remains open. Management score stays56/75, with independent
events, calibrated B/R, physical matchup and full flux budgets separate.

See the [report](../../harness/evidence/pr399_vertical_neighbor_2026-10-10/REPORT.md),
[range comparison](../../harness/evidence/pr399_vertical_neighbor_2026-10-10/NEIGHBOR_RANGE_COMPARISON.json),
[count correction](../../harness/evidence/pr399_vertical_neighbor_2026-10-10/VERTICAL_COUNT_AUDIT.json)
and [preservation check](../../harness/evidence/pr399_vertical_neighbor_2026-10-10/PRESERVATION_VERIFICATION.json).
