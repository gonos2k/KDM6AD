---
title: Saved native host states bounded by the independent producer stop
type: source
date: 2026-10-11
---

# Saved host time and local model time

The [PR407 report](../../harness/evidence/pr407_native_saved_time_bound_2026-10-11/COORDINATOR_REPORT.md) resolves a conditional P2 in [[pr406-native-case-consumer-2026-10-11]]: V2 checked saved Times against initialization but not the completed producer's effective stop. A synthetic one-minute July19 run could therefore admit a July20 background107,680 seconds later than stop. The current V4 consumer derives the window from the hashed numeric producer clocks/run-duration components and checks all saved Times at both initial intake and bound reload.

The producer interval is inclusive for stored terminal states. A separate local20s held-forcing M slot may follow a valid terminal background; it is not labeled stored host output or lateral-boundary coverage. String date aliases cannot create producer start/stop and must agree with numeric components. V3's draft source/replay is preserved as superseded after this source-format correction; historical PR406 records remain unchanged.

Actual V4 July19 intake confirms producer stop05:58, all8 saved timestamps within range, and70 common arrays equal to the historical core at05:55:40. This is intake reproducibility, not M/H/optimizer or a new native forecast. Tests include the exact reported counterexample and terminal-host/local-slot admission. The41 focused cases include15 reused portable cases, not56 distinct cases.

Both new L1B dates remain pending native input and analysis. The [checklist](../../harness/evidence/CHECKLIST_pr407_native_saved_time_bound_2026-10-11.md) retains actual first-ready-date analysis/audit as the next completion point. User79/100 and GK2A AMI L1B-only scope remain unchanged; no external model/reanalysis, satellite or L2 input is substituted.
