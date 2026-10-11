# PR404 source-mask repair and native-input boundary

The PR403 review's P3 is reproducible with actual netCDF4: reading packed words after `set_auto_maskandscale(False)` produces an ordinary array and `getmaskarray` reports false even at declared `_FillValue` or `missing_value` words. Production `_read_ami_bt` is a separate mask-aware path and is unchanged.

## Implemented and executed

`heldout_l1b_v2.py` is a separately versioned future writer. PR403's executed helper and all original artifacts remain unchanged, including its public manifest and private NPZ. The v2 helper reads exact uint16 raw words with scaling/masking disabled, then independently reads NetCDF masking with scaling disabled. Source missingness includes library-applied fill/missing/validity rules; it is not inferred from DQF or zero DN. The fixed 5×5 canvas stores `source_missing_mask` and `padding_mask` separately, preserving packed DQF and setting only padding's decoded DN/DQF placeholders to NaN/255. Signed or non-word dtype is rejected rather than coerced.

Nine focused tests use the actual netCDF4 library. They exercise fill, scalar/vector missing values, scale/offset metadata with raw-word preservation, valid zero DN, DQF3 source-present words, production quality's separate missingness, edge padding, declared valid-range exclusions and malformed dtypes. Existing production reader/calibration/AD/physics/solver/prior/sigma/bias/support are unchanged.

`repair_source_mask.py` executed once against 18 existing raw 5×5 slices at the fixed PR403 row320/column48. It verified original source SHA-256 before/after each read and compared raw words and embedded DQF with the original saved payload. A separate `SOURCE_MASK_PATCH.npz` and receipt were created in the restricted canonical PR404 archive. All 450 source/channel cells in these interior patches have no source missingness or padding; this does not invalidate the original BT/DQF result. The original payload hash stayed `d24bb3a5d029ec13d1b25d0afdae95637a971d6d304f38bcc73dae461220bd90`.

Only the v2 raw-read/canvas helpers were executed. Its new preflight/download/full-decode workflow was not run. No original NPZ, plan, public CSV or executed helper was replaced. No acquisition, new full-scene BT decode, native run, KDM M, RTTOV H/K or optimizer occurred.

## Matching native inputs

The bounded [availability audit](NATIVE_AVAILABILITY_REPORT.md) identifies the canonical IC/BC and retained forecasts as July19 only. Their recorded BC times end at July19 09UTC, not July20/21. Current symlink/file identity and exact-date patterns in the resolved original case were checked; prior inventories were reused rather than rescanned. No corresponding original July20/21 native inputs were found in the named roots. This is not a claim that no such archive exists anywhere.

The user's next objective remains two same-date analyses under the existing all-sky, T/Q-only, seven-channel,1K,zero-bias, fixed-physics configuration. Those analyses were not started because matching native states/forcing/pressure/surface data are unavailable in the inspected environment. July19 cannot be relabeled or used as a valid same-date background. No external model/reanalysis substitute was acquired; the already-outstanding archive request was not repeated.

When inputs become available, retain original input/run IDs and saved valid times, and declare the nominal-time assumption explicitly. Current L1B OBT/mission planned UTC metadata does not certify actual pixel UTC. Intake must reconstruct pressure/interfaces/surface from each date's native data. Quality loss, bounded optimizer return, gradient criterion, audit and storage failure remain separate outcomes.

## Scope and management

GK2A AMI L1B remains the only admitted satellite observation. External SST, MLS, VIIRS and L2 remain extensions, not completion gates. The [new rubric](../AMI_L1B_MANAGEMENT_RUBRIC_2026-10-11.md) records the user's78/100 assessment at PR403; it is neither a conversion of56/75 nor a model-performance statistic. This repair and availability audit assign no additional score. New-date analysis and physical interpretation remain open in the [checklist](../CHECKLIST_pr404_l1b_source_mask_2026-10-11.md).
