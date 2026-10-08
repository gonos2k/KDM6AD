---
title: PR388–389 local review resolution
type: source
date_modified: 2026-10-08
---
# PR388–389 local review resolution

The [resolution checklist](../../harness/evidence/CHECKLIST_review388389_resolution_2026-10-08.md)
and [local report](../../harness/evidence/REPORT_review388389_resolution_2026-10-08.md)
close a metadata endpoint mix-up without changing historical RTTOV H values:
AMI–native is 679.550499 m; AMI–VIIRS is 686.643623 m. The next-producer patch
routes the three explicit coordinate pairs; it is not a new native-run approval.

KMA v3.0 BT coordinate and saved-state versus valid-run distinctions are now
explicit in the prior report and acquisition checklist. Conditional scan-time
bounds remain conditional; a liquid retrieval category and zero model condensate
are a cloud-presence disagreement, not an NC-only result or causal ozone evidence.

Installed RTTOV source applies bit15/value32768 to total layer extinction above
20 km⁻¹; gas absorption can participate. Saved-transmission/thickness proxies
suggest lower-layer candidates but do not recover actual RTTOV ext/ltick arrays.

The native target remains launcher-invalid. A bounded process-only observer
loaded during a new short-case attempt but reached no WRF-start or MPI finalize
marker before its wall deadline. Our SIGTERM is distinct from the historical
exit1. No native process remains. Canonical source and operational installs were
preserved; no long run was performed. The user subsequently requested a bounded
correction PR; raw private host/forecast data are outside its scope. Related scope is in [[native-target-artifact-diagnostic-2026-10-08]].
