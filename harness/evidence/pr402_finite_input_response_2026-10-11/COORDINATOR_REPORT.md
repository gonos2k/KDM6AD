# PR402: actual finite input response and independent-input availability

Basis: merged main `6adb8049`. The [checklist](../CHECKLIST_pr402_finite_input_response_2026-10-11.md) continues PR401 without repeating its stored-K response calculation or the completed native/optimization/spatial campaigns.

## Actual execution

The coordinator executed the exact Red-reviewed [final-v4 plan](final_v4/K_RESPONSE_PLAN.json) once with the pinned executor. Skin T±0.5K and common reference O3±1% were applied in four new isolated cases, retaining the same pressure, T/Q, CO2, cloud, surface context, geometry, channels and assets except for the single designated input file. Each trial has21 unchanged input siblings and fresh outputs; the original central case was preserved.

All four wrappers returned fresh direct and K outputs, with seven quality flags zero. Direct and K-path native BT agree exactly per case. Wrapper count is4, fresh direct output count4, fresh K output count4; internal RTTOV H/AD calls are uninstrumented and remain unknown. Native integration, KDM M, optimization, automatic retry and a fifth baseline call are0.

The [numerical report](final_v4/NUMERICAL_REPORT.md), [actual result](final_v4/FINITE_RESULT.json) and [channel table](final_v4/FINITE_CHANNELS.csv) compare actual finite BT changes with the saved K in the common KMA coordinate. Maximum one-sided linearization error is0.000359254K for Skin T±0.5K and0.000425317K for O3±1%. Central derivative discrepancies are at most1.63822e−6 and1.91032e−6K per respective declared unit direction. Costs are dimensionless normalized Huber values, not Kelvin.

The O3 IR112 response is tiny: about0.65% relative discrepancy corresponds to only1.02e−8K/unit absolute error. The frozen1e−6K/unit relative-reporting cutoff does not suppress absolute errors or change derivative acceptance criteria. Actual serialized input contractions are reported separately from ideal hK0d.

## Interpretation limits

This result shows local finite-step agreement for two fixed-input directions at the preserved central direct-H state. It is not a new T/Q minimization, proof of actual input error, corrected baseline, cloud restoration or independent-event validation. It does not disambiguate O3 and upper-temperature responses or change the seven-channel/sigma/bias policy.

Executable and coefficient hashes match the historical center records. The old hydrotable and dynamic-library hashes were not recorded; the current versions are frozen and rechecked before/after the four trials. libSystem is a dyld shared-cache install name with no regular-file SHA. One-sided E uses the preserved baseline under these limits; the central pair difference cancels that baseline. No extra run was added to conceal this limitation.

## Independent evidence investigated in parallel

[Independent-input scope](INDEPENDENT_INPUTS_SCOPE.md) and its [availability receipt](INDEPENDENT_INPUTS_AVAILABILITY.json) identify a NOAA-20 SST-subskin swath candidate and daily MLS O3/T metadata. They do not establish a valid collocated SST value or a profile at the required point/time. MLS data access returned unauthenticated HTTP401; V005 metadata is paired with official V5 quality guidance, not silently treated under V6 thresholds. Native39 levels and upper27 reference levels remain distinct; upper observations can assess reference inputs where retrieval range/sensitivity supports them.

Actual independent measurements/QA, product-specific IR133 upstream SRF, original IC/BC provider and other initial dates remain open. The existing archive-path request is not repeated. No external model/reanalysis was acquired or substituted, and catalog footprints are not measured profiles or two independent native events.

## Evidence and completion

Preflight-only drafts and the pre-call preparation failure remain separately attributed with zero wrapper calls. Final-v4 is the execution plan; no draft is represented as a successful forward experiment. The actual source, plan, inputs, four isolated cases, raw/converted K and private payload are preserved with hashes. Final Green/Red reviews and validation accompany the packet; Graphify source/semantic relationships are refreshed.

Research-management score stays **56/75 (74.7%)**. The selected finite-step checks are complete, while physical input-error calibration, actual independent matchups, independent native events and full water/heat external/boundary budgets remain unfinished.
