---
title: Calibration binding and DOM comparison qualifications
type: source
date_ingested: 2026-10-13
source_type: source-guard-and-recorded-output-review
tags: [KDM6AD, AMI, RTTOV, DOM, calibration, provenance]
---
# Calibration binding and DOM comparison qualifications

Follow-up to [[pr420-dom-nine-channel-analysis-2026-10-13]] at main741172da.
The [report](../../harness/evidence/pr421_review_followup_2026-10-13/REPORT.md)
records a future-analysis calibration input fix and additive interpretation.
The shared capture and seven/nine-channel case preflight hash the actual JSON
read by the KMA BT/K transform. Missing or changed inputs prevent successful
checkpoint publication. Original PR420 records remain immutable, and their
missing calibration execution history is not retroactively certified.

All twelve retained DOM cases request eight streams, accuracy0, optical-depth
threshold0 and solar off. Configured plane_parallel/lambertian flags are false;
DOM nevertheless uses its own strict plane-parallel and Lambertian thermal
boundary rules. Edd7→DOM7 changes coupled operator behavior, while DOM7→DOM9
changes support within the same variant.

Public arithmetic gives final common-seven Jo plus prior6.3318615336 (DOM7)
and6.3335859423 (DOM9): delta+0.0017244087, so the common-observation decrease
is not a common-objective improvement. The existing minus-direction point
has J11.4681507087, lower than returned11.4686595552; no checkpoint is replaced.
Neither point establishes strict convergence or nine-channel superiority.

This follow-up executes no new native/RTTOV/optimizer/FD experiment. Portable
guard tests and recorded-file arithmetic are distinct from actual PR420
analysis. Existing seven-channel closure and finite-budget DOM9 completion
remain, with timing/interface/number-basis, calibration-history and independent-
date/forecast limits intact.
