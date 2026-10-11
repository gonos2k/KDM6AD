# PR404: source-mask correction and same-date native linkage

Basis: main `6bdcdccc` (PR403), the user's 2026-10-11 review, and the [AMI L1B-only contract](CURRENT_OBSERVATION_DATA_CONTRACT.md). The [78/100 rubric](AMI_L1B_MANAGEMENT_RUBRIC_2026-10-11.md) records the user's assessment; no points are automatically added by this change.

- [x] Reproduce the source-mask loss with actual netCDF4, not an interface stub.
- [x] Preserve the entire executed PR403 helper/plan/result/CSV/NPZ and hashes. Introduce a versioned future writer; do not patch old results or rerun its frozen acquisition plan.
- [x] Keep raw uint16 words, NetCDF source missingness, image-edge padding and packed DQF separate. Disable scaling for packed reads; preserve source masking independently.
- [x] Check `_FillValue`, scalar/vector `missing_value`, scale attributes, DQF3 without missingness, valid zero DN, malformed dtype and edge padding using real NetCDF fixtures.
- [x] Capture a separate mask sidecar from the existing 18 raw 5×5 slices. Verify source/original payload hashes and unchanged words/DQF; no new acquisition or full-scene BT decode.
- [x] Audit the named canonical native-input roots and retained receipts for matching July20/21 inputs. Record search limits and missing matches; do not repeat the archive request or claim a global absence.
- [ ] Connect each scene to its own original native input ID, valid time, forcing, pressure/interface, surface and declared nominal-time assumption. **Pending matching original native inputs in the inspected environment.** July19 IC/BC cannot be relabeled; its BC ends July19 09UTC.
- [ ] Execute same-configuration baseline → T/Q analysis → final audit for both dates, preserving quality/failure outcomes, total gradient and state. Do not substitute a new external model/reanalysis source.
- [ ] Interpret per-date BT, T/Q, saturation/hydrometeor response and defined water/heat diagnostics. Do not infer phase/SST truth from BT or source DQF.
- [x] Finish Green/Red consistency/counterexample review, graph code/semantic refresh and checks for this change.

See [mask result](pr404_l1b_source_mask_2026-10-11/MASK_REPAIR_RESULT.json), [native availability](pr404_l1b_source_mask_2026-10-11/NATIVE_AVAILABILITY_REPORT.md) and [coordinator report](pr404_l1b_source_mask_2026-10-11/COORDINATOR_REPORT.md). Existing finite-input K/RTTOV and spatial/vertical campaigns stay closed. Other sensors and all L2 products remain deferred extensions.

Verification: [Green](pr404_l1b_source_mask_2026-10-11/GREEN_REVIEW.md), [Red](pr404_l1b_source_mask_2026-10-11/RED_REVIEW.md), [validation](pr404_l1b_source_mask_2026-10-11/VALIDATION.json). Code AST and scoped semantic graph updated; raw graph reports remain ignored under graphify-out.

## Independent team follow-up

- [x] Check future decode/publication paths independently of raw-helper tests; reject failed/incomplete/mismatched download provenance.
- [x] Verify successful RESULT publication follows CSV completion, conflicting outputs stop before source intake, and empty/external-plan cases retain a consistent contract.
- [x] Add channel/raster-axis metadata and exact local command/environment without modifying original manifests/receipts.

Current future writer is [v3](pr404_l1b_source_mask_2026-10-11/heldout_l1b_v3.py); frozen v2 remains historical helper/repair evidence. See [team resolution](pr404_l1b_source_mask_2026-10-11/audit_20261011/TEAM_AUDIT_RESOLUTION.md) for findings,36 scoped tests and execution limits. Same-date native analyses are still pending.
