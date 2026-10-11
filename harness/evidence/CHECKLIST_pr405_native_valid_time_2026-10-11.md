# PR405: valid-time linkage and boundary interval correction

Basis: main `cc0a2edb` (PR404), user review2026-10-11, GK2A AMI L1B-only edition. Writer/source-mask/provenance/publication checks are closed and are not repeated here.

- [x] Separate initialization date, model valid time and forecast lead. An earlier initialization is admissible in principle when a lineage-bound valid state and necessary inputs cover the target.
- [x] Resolve the boundary record-start/interval-end distinction using actual `THISBDYTIME`/`NEXTBDYTIME` metadata and authoritative host source. Correct last record09UTC versus last interval endpoint12UTC; do not infer advance at/past12.
- [x] Reuse cached forecast horizons rather than rescan the same84 paths. Initialization suffixes alone cannot prove valid-time absence. No documented candidate reaches July20/21; this is not a global archive-absence claim.
- [x] Bind both existing L1B scenes to explicit nominal-time assumptions and required native background/slot/output times. Record `PENDING_NATIVE_INPUT` with no selected native run/state ID.
- [x] Record the user's updated79/100 on the same100-point rubric; no extra point for this correction or test count.
- [ ] Obtain a provenance-complete native state/forcing/pressure/surface at either declared valid date, from the existing native input series and sufficient boundary coverage. The already-outstanding archive/source request is not repeated; no external model/reanalysis substitute is introduced.
- [ ] Run the first ready date's existing seven-channel all-sky T/Q-only baseline→analysis→final audit; do not wait for both dates if one is ready. Keep fixed physics,1K,zero bias, prior and quality policy.
- [ ] Run the other ready date and compare per-date BT, cost/gradient, T/Q, saturation/hydrometeors and defined water/heat diagnostics. No forced cloud or residual-fitted sigma/bias adjustment.

The [time-linkage result](pr405_native_valid_time_2026-10-11/NATIVE_TIME_LINKAGE.json) is metadata-only, not an analysis receipt. See [report](pr405_native_valid_time_2026-10-11/COORDINATOR_REPORT.md), [Green](pr405_native_valid_time_2026-10-11/GREEN_VALID_TIME_REVIEW.md) and [Red](pr405_native_valid_time_2026-10-11/RED_BC_REVIEW.md). No archive question, broad file rescan, model run or satellite acquisition occurred.
