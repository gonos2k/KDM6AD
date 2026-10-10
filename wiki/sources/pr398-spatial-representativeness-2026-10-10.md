---
title: PR398 fixed-candidate spatial representativeness
type: source
date: 2026-10-10
---

# PR398 fixed-candidate spatial representativeness

The [spatial checklist](../../harness/evidence/CHECKLIST_pr398_spatial_review_2026-10-10.md)
follows the review of PR398 `bf00721b` without reopening its completed
iteration-budget, gradient or viewing-center diagnostics. Selection was
declared before surrounding sample values: native3×3 at frames1/4/6, AMI5×5
at the unchanged candidate and VIIRS nominal geolocation centers inside
the native-center bounding rectangle. No model M/H, optimizer or acquisition.

All27 native column/time samples contain zero QC and NC; maximum liquid
qv/qs lies between95.1460% and95.9879%. They are stored host states, not nine
new analyses or27 independent weather events. The unchanged AMI center
replays exactly and all175 patch values have DQF0. Observed IR105 ranges
288.9325–293.7085K, while all103 selected VIIRS phase/type values are the
same liquid codes. Phase homogeneity therefore does not establish a uniform
radiance field, full cloud cover, height or optical thickness.

The [separate QA audit](../../harness/evidence/pr398_spatial_representativeness_2026-10-10/OBSERVATION_PATCH_QA_AUDIT.json)
preserves raw CloudPhaseFlag0×94 and5×9. The nine5s exceed the field's
advertised[0,1] range, an unresolved packed-byte/metadata discrepancy. Nonzero
bits were not interpreted. The source-family interpretation of byte0 does
not admit all103 samples with the same quality. The model-center box and
AMI patch have different bounds; neither defines verified instrument
footprint weights. Pixel UTC, full cloud-height patch/datum and AMI SRF remain
open. Pixel scatter is not calibrated R, and category proportions are not
area cloud fraction.

The inspected local inventory has84 forecast variants with the same July19
initialization suffix and no two additional independent IC dates. This is a
bounded availability finding, not a complete device-wide inventory or
validation of all84 runs. Further independent events require their own native
input availability and observation selection. The user-reviewed management
basis remains56/75; spatial tables alone do not add forecast-skill, B/R or
flux-closure evidence.

See the [source-grounded report](../../harness/evidence/pr398_spatial_representativeness_2026-10-10/REPORT.md),
[Green review](../../harness/evidence/pr398_spatial_representativeness_2026-10-10/SPATIAL_GREEN_REVIEW.md),
[Red review](../../harness/evidence/pr398_spatial_representativeness_2026-10-10/SPATIAL_RED_REVIEW.md),
and [canonical preservation](../../harness/evidence/pr398_spatial_representativeness_2026-10-10/LOCAL_PRESERVATION.json).
