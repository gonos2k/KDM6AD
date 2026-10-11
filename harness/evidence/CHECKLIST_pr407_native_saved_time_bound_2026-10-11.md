# PR407: bound saved host times to the producer run

Basis: main `2d7d1000`, PR406 user review, GK2A AMI L1B-only research edition.

- [x] Reproduce the conditional P2 with a synthetic one-minute July19 producer and July20 saved background:107,680 seconds beyond producer stop. Keep this separate from actual native evidence.
- [x] Derive start/stop from independent effective namelist fields. Combine run_days/hours/minutes/seconds; numeric end_* is used only when duration is zero. String-only clocks cannot supply a producer time.
- [x] Check every advertised saved host Times in inclusive [start,stop] at intake and bound reload; record ordered Times metadata/hash.
- [x] Preserve terminal saved backgrounds and the separate local20s observation slot. Local M is not constrained by the host stop and is not relabeled a saved host frame.
- [x] Correct the synthetic earlier-initialization fixture to a valid30-hour producer run. Reject the exact out-of-range counterexample before private reader/P8W access or output publication.
- [x] Verify fresh V4 July19 core intake against all70 shared historical arrays, without M/H/optimizer/native execution. Retain V3 as superseded pre-correction evidence and PR406 records unchanged.
- [x] Review Green/Red and expose15 public regressions separately from private intake tests. Report41 unique focused cases, not56 distinct cases.
- [ ] Connect actual native state/forcing/pressure/surface for the first available July20/21 valid date. No new candidate was supplied; prior archive requests are not repeated and no external model/reanalysis is substituted.
- [ ] Complete that date's baseline→analysis→final audit/checkpoint using fixed seven-channel all-sky T/Q configuration.
- [ ] Complete the other available date and compare numerical, BT and defined water/heat responses.

Both [V4 pending records](pr407_native_saved_time_bound_2026-10-11/COORDINATOR_REPORT.md) remain pending/no NPZ/no analysis. User assessment **79/100** is unchanged. The time fix does not supply new meteorological data.
