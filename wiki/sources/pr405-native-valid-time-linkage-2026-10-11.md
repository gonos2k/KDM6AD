---
title: Native valid-time linkage and boundary record-start correction
type: source
date: 2026-10-11
---

# Native valid time and represented boundary interval

The current canonicalBC `Times` ends at July19 09UTC, but source THIS/NEXT metadata represents the final interval09→12. Runnable host `input_wrf.F`/`output_wrf.F` treats these as interval start/end; applicability is `[09,12)` under ordinary selection, not extrapolated forcing beyond12. A terminal saved state at12 can be reached by a preceding step. This dated [report](../../harness/evidence/pr405_native_valid_time_2026-10-11/COORDINATOR_REPORT.md) corrects older record-start-as-end interpretations without altering their archived receipts or certifying an old compiled run.

A retained state need not have the observation's initialization date: lineage-bound valid time, forecast lead, required native state/forcing/pressure/surface and boundary coverage determine eligibility. Cached84initialization suffixes are not84forecast-horizon measurements. The known cached candidates end July19, including a separate hourly12h artifact; no named candidate demonstrates July20/21. This is not a global archive absence claim.

[Linkage result](../../harness/evidence/pr405_native_valid_time_2026-10-11/NATIVE_TIME_LINKAGE.json) preserves the existing L1B hashes/slots and states explicit nominal-time-as-model-UTC assumptions with uncertified pixelUTC. Both dates remainPENDING_NATIVE_INPUT, with null selectednative data/run andnoanalysis. CurrentBC gaps after12 are17h56/41h56 to nominalslot; existing8frame intake wouldrequire05:58 output, separately from05:56 observation and05:55:40 background.

[[pr404-l1b-source-mask-and-native-linkage-2026-10-11]] writer/mask work stays closed. No source inventory, archive request, acquisition or model/H/K/M/optimizer was repeated. The [checklist](../../harness/evidence/CHECKLIST_pr405_native_valid_time_2026-10-11.md) allows the first readydate to proceed independently of the second. The userPR404review updates the same100point rubric78→79; this correction assigns no newpoint and does not convert the historical56/75scale.
