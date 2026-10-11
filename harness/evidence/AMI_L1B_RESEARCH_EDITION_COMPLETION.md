# AMI L1B research-edition completion criteria

Scope revised by the user on2026-10-11. The current target is a repeatable native/KDM6AD/RTTOV analysis system using **GK2A AMI L1B as its only satellite-observation input**. This document supersedes broader external-observation prerequisites in historical collection checklists; it does not rewrite their executed evidence.

## In-scope completion matrix

| Requirement | Actual completion evidence | Current limit / next result |
|---|---|---|
| L1B source, decoding and calibration | Original file hashes, DN/radiance/BT/DQF, missingness, exact file/calibration pairing and unchanged input checks; production LA reader and PR382–384/398/400 records; PR403 decoded two held-out dates with unchanged reader/calibration | Held-out observation intake is executed; matching native inputs and analysis remain separate. Do not silently replace paired calibration |
| RTTOV comparison coordinate/configuration | Same-run radiance/native BT replay into bundled KMA coordinate for all K fields; channel/coefficient/SRF provenance and actual finite trials (PR365/400–402) | IR133 upstream product SRF identity remains unverified; describe the current fixed pairing conditionally rather than invent a correction |
| Time, geolocation and spatial admission | Preserved OBT/scene/planned-UTC/raw numeric fields; GEOS origin and original indices; fixed nominal location, strict DQF0 support and documented point/patch rules | Pixel UTC and footprint identity remain unverified. Declare explicit nominal-time/geometry assumptions and do not promote filename labels to observed UTC |
| Declared analysis/control configuration | New single-column all-sky helper with fixed physics and T/Q-only initial controls; current native39 layers/pressures and modeled cloud response retained (PR394–397) | No forced cloud seed, pseudo-RH, channel removal or residual-fitted parameter change |
| Repeatable baseline/analysis/final audit | Normal native rank/launcher and valid selected output evidence; actual KDM→RTTOV→cost/minimization→accepted-state/gradient preservation; bounded failure contracts (PR395–398) | One initial-date native case. New-date observed scenes alone do not demonstrate new-date DA. Stop on quality loss; accepted return, convergence and scientific interpretation remain distinct |
| Numerical/physical diagnostics | Stored initial/slot state pairs, control/total gradient, saturation/cloud response, water-change decomposition, host/local differences and finite input steps (PR396–402) | Explain the defined measure, reservoir terms and unmeasured boundaries. Algebraic decomposition is not closed flux conservation; a finite step check is not global/high-order validity |
| Held-out date/scene repeatability | PR403 acquired/decoded preselected July20/21 exact nominal05:56 scenes:18 files,8,555,216 bytes; hashes, point/patch values and original time/navigation attributes retained | Observation intake complete; matching native inputs and same-configuration analyses remain pending. Separate scene dates do not prove independent meteorological events |
| Prior/error/bias interpretation | Existing1K sigma, zero bias and T/Q prior are explicit exploration assumptions; modeled states and conditional residuals are reported as such | Multiple scene residual statistics can be accumulated, but are not automatically pure observation error R. No mandatory external truth or new B/R architecture gate |

## Deferred extensions, not present-edition penalties

External SST, MLS temperature/ozone, VIIRS phase, other sensors and L2 products; external independent cloud/height/number truth; cross-sensor verification. Their absence is not a current completion deduction or prerequisite. Required gas/surface/upper-atmosphere inputs remain labeled research assumptions; no external observations are required to use them.

Better BT fit does not independently prove phase, height or NC. Those inferred model states can still be valid research outputs of this edition. Native model initial/boundary data remain necessary for model-connected cases and are not excluded by the satellite-data restriction.

## Evaluation accounting

The earlier **56/75 (~75%)** was a broader management score. Keep it as a historical reference, **not an automatically transferred or raised AMI-only score**. A next scope-specific assessment must map the evidence above to explicit weights/completion states before assigning a new number. Do not increase a score merely because requirements moved to the extension phase, files/tests/PRs grew, or nearby pixels were counted as independent events.

Current work separates observation intake from model-connected analysis and marks executed, conditional and pending stages explicitly. No production physics, solver, observation support, sigma/bias or prior was changed by this scope revision.

## User assessment at PR403

The user subsequently supplied a new8-area,100-point rubric at main6bdcdccc: **78/100**. See the [dated management rubric](AMI_L1B_MANAGEMENT_RUBRIC_2026-10-11.md) for exact weights/scores and evidence limits. This is an explicit new assessment, not an automatic scope-based conversion of56/75. PR404 fixes source-mask capture without assigning additional points; matching new-date native analyses remain pending.

Future raw-patch acquisition/decode uses the versioned [PR404 v3 writer](pr404_l1b_source_mask_2026-10-11/heldout_l1b_v3.py) with a new frozen plan and output directory. The PR403 helper remains immutable executed evidence, not the current source-mask writer. PR404's actual execution was limited to its raw/canvas helpers and an additive sidecar from existing slices; no full acquisition/decode workflow or new-date analysis is claimed.

The [independent team audit](pr404_l1b_source_mask_2026-10-11/audit_20261011/TEAM_AUDIT_RESOLUTION.md) supersedes the earlier v2 future-writer declaration. V2/actual sidecar evidence stays frozen. V3 adds validated download provenance, stable empty schemas and completion-last publication; only synthetic writer integration was executed, with no real full-scene v3 decode or new-date model analysis.

## Native valid-time follow-up at PR404

The [PR405 linkage record](pr405_native_valid_time_2026-10-11/NATIVE_TIME_LINKAGE.json) and [report](pr405_native_valid_time_2026-10-11/COORDINATOR_REPORT.md) correct the existingBC final record09UTC versus interval endpoint12UTC. This file still does not reach July20/21. A matching native valid state may come from an earlier initialization; initialization suffixes are not a forecast-horizon census. New-date cases remainPENDING_NATIVE_INPUT, with no native run selected or analysis executed. The user's same-scale assessment is now79/100, without further points for this follow-up.

## Case-consumer follow-up at PR406

The [case consumer and checklist](CHECKLIST_pr406_native_case_consumer_2026-10-11.md) separate the case/run/time identifiers from the unchanged historical intake. Its bounded core needs one saved native background plus declared20s forcing; additional host frames are optional diagnostics. The isolated capture adapter reuses the existing analysis and final audit. Actual evidence is a July19 core intake replay and synthetic admission/failure tests, not a new-date analysis. Both July20/21 cases remain pending native input. The79/100 assessment is unchanged.

The [PR407 correction](CHECKLIST_pr407_native_saved_time_bound_2026-10-11.md) binds every saved host Times to the independent effective producer start/stop at intake and reload. Current V4 consumes numeric producer clocks, preserving a terminal background's separate local20s slot. Same-date intake verifies unchanged arrays; no new-date M/H/analysis or completion-score increase is claimed. Use V4 for new cases; historical V2 and superseded V3 evidence remain preserved.

The [PR408 positive synthetic test](CHECKLIST_pr408_synthetic_capture_success_2026-10-11.md) exercises unchanged V4/capture through real KDM/AD/minimizer/final audit/checkpoint using the existing synthetic H fixture. It establishes one diagnostic success/storage path, not actual RTTOV, convergence or new-date analysis. Local private dependencies are explicit and the public facade skips without them. Both actual new dates and79/100 remain unchanged; no new consumer version or extra time gate is introduced.
