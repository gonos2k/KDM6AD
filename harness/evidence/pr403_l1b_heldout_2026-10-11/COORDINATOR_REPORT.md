# PR403 coordinator report

The current edition admits only GK2A AMI Level-1B satellite observations. External SST, MLS, VIIRS and all Level-2 products are deferred extensions, not completion prerequisites or score deductions. The native model, its original IC/BC, KDM6AD and RTTOV assets remain separately documented model inputs in the edition; none was used to produce these observation-only scene results. See the [observation contract](../CURRENT_OBSERVATION_DATA_CONTRACT.md), [completion matrix](../AMI_L1B_RESEARCH_EDITION_COMPLETION.md) and [checklist](../CHECKLIST_pr403_l1b_heldout_2026-10-11.md).

## Executed work

Two dates were fixed before observed values, DQF or residuals were inspected:2025-07-20 and2025-07-21. Their exact nominal05:56 LA020GE slots each contained all nine requested thermal channels8–16. No fallback slot, scene-family change or fit-based location selection was used. The analysis subset stays10–16; no support, prior,1K sigma, zero bias, physics or solver default changed.

The frozen plan selected18 objects totaling8,555,216 bytes. Original bytes and the selected5×5 payload are preserved in the restricted canonical host archive. The unchanged production LA reader and paired calibration decoded both dates. The nearest geometric pixel is zero-based AMI row320/column48,679.55m from the fixed target, with all nine channel DQFs0. Each fixed patch has25 geolocated cells; all source quality counts and missingness outcomes are retained. DQF0 is L1B source quality, not cloud/phase/SST truth.

Original DN, packed DQF, BT, navigation/calibration attributes and source hashes are retained. Radiance is additionally replayed from retained DN and the same gain/offset in a separately identified CSV; it was not originally present in the executed payload. Neither pixel selection nor reporting changes the observation to a best-fitting pixel or average. No R was estimated.

Filename/scene acquisition OBT and mission planned UTC are preserved separately. Raw synchronization numbers are retained without inferred epoch/offset; actual pixel UTC remains uncertified and production valid_time_utc is unset. A future model-connected run must declare its temporal/geometric assumptions and retain these limits.

## Verification and preserved failures

The coordinator verified all18 local SHA-256 values, sizes and MD5/ETag pairs, frozen plan/helper hashes, private payload hash and0700/0600 custody. Local pytest passed21 tests:five held-out selection/geolocation tests plus16 unchanged production LA-reader tests. Ruff passed both new Python files. The extra-band regression checks the observed metadata failure: a complete nine-channel subset remains complete when the source listing includes three other LA020GE bands.

Two metadata-only preflight failures are preserved separately. Attempt1 failed XML namespace parsing; attempt2 falsely rejected complete slots because it demanded equality with the listing's full band set. Neither downloaded granules or decoded observations. The final executed helper and plan remain unchanged. Independent review chronology is reported as it occurred; a post-acquisition Red review is not retroactively described as pre-acquisition approval.

## Remaining current-edition work

Observation-only held-out intake is complete. Matching original native IC/BC and baseline/analysis/final-audit results for these dates are not available in this packet. July19 model state must not be relabeled or attached to July20/21 observations as a valid new analysis. Consecutive separated scene dates do not establish independent meteorological events.

Product-specific IR133 upstream SRF, actual pixel UTC and footprint correspondence remain recorded assumptions/limits. Model-connected repeatability and defined numerical/physical diagnostics remain current completion requirements. External truth sources do not. No RTTOV H/K, KDM M, optimizer or native model was executed here, and no external model/reanalysis substitute was acquired.

The old56/75 (~75%) score remains a historical broader-scope management reference. The current scope/evidence matrix changes no weights or denominator and assigns no new numeric score. File/test/PR counts and the scope reduction do not raise it automatically.
