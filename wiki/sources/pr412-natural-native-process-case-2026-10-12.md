---
title: PR412 natural native warm-QC case
type: source
date: 2026-10-12
---
# PR412 natural native warm-QC case

The existing Jul19 native run supplied a different naturally QC-bearing column `(j=103,i=48)` selected before residual inspection from one declared 41×41/time slice. Its geographically selected AMI L1B row 289 / column 49 is 425.935 m away with seven supported analysis-channel L1B DQFs equal to 0. This is a model-state target, not independently observed liquid phase or a new weather date.

One unchanged V4 T/Q analysis returned/audited/stored: Jo = 8.461861 → 6.321446, Jb = 0.109348, J = 6.430793 (dimensionless costs); gradient L∞ = 0.304159 exceeds 1e−10. The background retained QC increases slightly; accepted-initial QC is fixed at background but disappears after local 20 s M. Endpoint changes alone do not identify named process rates. [[pr409-problem-evidence-alignment-2026-10-11]] separates these claims; [[pr411-v4-actual-integration-2026-10-12]] remains the closed central integration reference.

Two separately declared value-only initial-state H calls, with identical H auxiliaries/support, give IR105 R_M(background) = −0.000389 K, R_M(accepted) = +0.689020 K and I_M = +0.689410 K. Same-pair cost gains are G_M = 2.140416 versus bypass diagnostic G_0 = 0.205407, difference = 1.935008 (dimensionless normalized Huber cost under sigma = 1 K). This demonstrates joint endpoint observation-space response, not isolated QC/NC effects, no-M reoptimization, a same-valid-time host forecast or forecast skill.

The selector's NumPy-int JSON failure remains preserved; recovery serialized the stored slice without a new native-field scan. Native QN mass basis is not independently revalidated; NC is a recorded coordinate under the declared dry-number runtime. Fixed-host-measure local total-water changes are 0; initial DA water change = −0.114977 kg/m² is not an external-flux budget. July20/21 remain pending; the historical management reference 79 is not rescored. No native integration or closed derivative campaign was repeated.

Evidence: [case report](../../harness/evidence/pr412_native_process_case_2026-10-12/REPORT.md), [paired response](../../harness/evidence/pr412_native_process_case_2026-10-12/PROCESS_RESPONSE.json), [channel table](../../harness/evidence/pr412_native_process_case_2026-10-12/CASE_CHANNELS.csv).
