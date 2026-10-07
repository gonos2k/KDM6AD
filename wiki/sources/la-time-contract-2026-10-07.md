---
title: Conditional Satpy LA clock interpretation and native readiness
type: source
date_modified: 2026-10-07
---

The [time-contract audit](../../harness/evidence/REPORT_LA_time_contract_2026-10-07.md)
pins Satpy v0.57.0 and executes its original start/end properties on the retained
LA header. The noon epoch gives a matching naive calendar label; it does not
verify UTC, synchronization application or per-pixel scan time. The LA payload
continues to leave `valid_time_utc` unset.

Current native July 19 boundaries span 00–09 UTC, which would cover the naive
candidate interval only if its clock interpretation is confirmed as UTC,
but exact matched output, phase and sensor/model correspondence are absent.
Credential availability and missing science data are independent of the
closed decoder and artifact-acceptance numerical checks.
