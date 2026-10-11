# PR404 matching native-input availability

Read-only scope: canonical `/Users/yhlee/KDM6AD-k/host/lc05_da_run` IC/BC/forecast entries, their resolved symlink targets, the linked original SS case directory for exact July 20/21 met_em/wrfinput/wrfbdy/wrfout filename patterns, and existing PR398/PR400/October 7–10 inventory receipts. No whole-device search, broad recursive rescan, forecast-state read, acquisition, model run, or question to the original provider was performed.

The canonical `wrfinput_d01` and `wrfbdy_d01` are symlinks into the existing SS case at `/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS/`. Their previously recorded NetCDF metadata binds the initial state to `2025-07-19_00:00:00` and the boundary file to 00, 03, 06 and 09 UTC on July 19. The boundary metadata ends at 09:00 UTC that day. No July 20 or July 21 initial or boundary time is represented by these inputs. In the resolved original SS case directory, bounded top-level filename checks found no July 20/21 `met_em`, `wrfinput`, `wrfbdy`, or `wrfout` files.

The existing bounded retained-forecast inventory reports 84 forecast paths: 83 ordinary artifacts and one quarantined/clobbered artifact. All share initialization suffix `202507190000`; this inventory did not identify a second initialization date. The separately recorded successful native run also saved July 19 times only (05:55:40–05:58:00). The current `lc05_da_run/klfs_lc05_fcst.202507190000` file is a July 19 forecast artifact, not a July 20/21 initial condition or a continuation that can be relabeled as those dates.

A previously noted `met_em` pair is from 2023-02-16 and has a different start date and a 249×199 horizontal grid, versus 282×234 for the July 19 inputs. It is not a compatible July 20/21 native case. No new model or reanalysis input was acquired or proposed.

**Finding:** No matching original July 20/21 IC/BC or native states were found in the named canonical case roots and existing retained-inventory receipts. This does not establish global absence from archives or from uninspected locations. The meteorological provider and original preprocessing lineage for the July 19 REAL_EM-labeled files remain unverified in PR400. The existing provider/path request is already outstanding and is not repeated.

The two held-out July 20/21 AMI L1B scenes are valid observation-only intake results. They do not support same-date native baseline, analysis or final-audit runs without corresponding original native inputs. This native-input gap blocks only model-connected analyses for those dates; it does not block the L1B mask/reader work.

The user supplied a **78/100** management-rubric assessment. It is recorded as the user's assessment, not recomputed, transferred from 56/75, or changed by this availability audit.

## Evidence used

- `harness/evidence/pr400_input_compatibility_2026-10-10/IC_BC_LINEAGE.json`: direct canonical IC/BC symlink and NetCDF metadata, exact July 19 Times, current incompatible 2023 met_em candidates and provider/preprocessing uncertainty.
- `harness/evidence/NATIVE_model_readiness_2026-10-07.json`: existing July 19 IC/BC and retained forecast metadata; no state arrays were reread here.
- `harness/evidence/pr398_spatial_representativeness_2026-10-10/NATIVE_5KM_AVAILABILITY_v3.json`: bounded existing inventory count/suffix summary and explicit inventory limits.
- `harness/evidence/pr397_actual_native_results_2026-10-10/NATIVE_COMPLETION.json`: separate valid July 19 run identity and saved-time range; science acceptance remains false.
- The direct read-only check in this audit confirms the current canonical symlink targets and file sizes/mtimes; it does not hash large files or inspect model arrays.
