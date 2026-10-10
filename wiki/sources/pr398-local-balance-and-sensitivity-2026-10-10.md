---
title: PR398 local control balance and bounded sensitivity
type: source
date: 2026-10-10
---

# PR398 local control balance and bounded sensitivity

The [follow-up checklist](../../harness/evidence/CHECKLIST_pr398_followup_2026-10-10.md)
separates stored-array arithmetic, a new same-objective local analysis, and
direct observation-operator sensitivity on saved native host states.
These use the completed PR397 native input and preserve prior records.

The immutable PR397 checkpoint gives the normalized prior gradient `v`.
Subtracting it from the final total gradient yields the complete CVT–KDM–H
observation contribution, not the direct RTTOV state adjoint. The temperature
and water-vapor blocks have prior/observation cosine approximately -1;
their remaining total-gradient L2 norms are 9.17e-5 and 1.78e-4 respectively.
The [layer calculation](../../harness/evidence/pr398_followup/CONTROL_BALANCE_PR397.json)
uses no model or RTTOV call.

The separately identified max_iter8 run returns total cost
26.364090171757063, approximately 2.19e-8 below PR397, with final gradient
Linf1.18e-6 still above its 1e-10 declared threshold. It is a bounded
numerical result, not demonstrated convergence or cloud recovery. Raw
cross-run signatures differ because their isolated fixture paths differ;
the original comparison failure is retained for a separate interpretation
audit. The [separate audit](../../harness/evidence/pr398_followup/POSTRUN_INTERPRETATION.json)
confirms matching effective configuration and bound assets while preserving
the raw mismatch. See the [actual-run report](../../harness/evidence/pr398_followup/ACTUAL_RUN_REPORT.md).

The predeclared direct-H batch returned all6 cases at saved host frames1/4/6
and both fixed centroid viewing geometries, with all7 quality flags zero.
Same-column native HGT is preserved. Temporal BT changes are at most0.010811K
in these three frames and centroid-viewing changes at most0.001107K.
This uses H(host(t)), not the analysis H(M(xb)), and does not measure parallax
or establish pixel UTC/footprint. See the
[V2 result report](../../harness/evidence/pr398_followup_2026-10-10/REPORT_v2.md).

The user-reviewed PR397 management basis is now 56/75 (74.7%). This
supersedes the earlier54/75 assessment because a valid native baseline,
analysis and actual physical-state diagnostics were obtained in PR397.
The change is attributed to those results, not this wiki entry or repeated CI.
Pixel-time/footprint admission, flux closure and held-out native warm-liquid
cases remain separate open research questions. Historical source notes keep
their dated scores rather than being rewritten.
