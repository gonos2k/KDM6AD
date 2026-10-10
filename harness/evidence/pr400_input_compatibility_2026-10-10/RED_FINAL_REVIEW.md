# PR400 final Red review: coordinator report and IC/BC lineage

## Disposition

No blocking integrity issue found in the refreshed lineage helper/receipt or the coordinator report/checklist. The source hash in `IC_BC_LINEAGE.json` matches the current `audit_ic_bc_lineage.py`. I re-read the current canonical IC, BC, and both listed met_em candidates using the helper’s header path; each receipt record matches the live file path, resolved target, symlink status, size, mtime, selected attributes, dimensions, and Times.

I exercised `lineage_differences` with three in-memory cases. Same initialization day and same tested grid returned no differences; a different date returned `INITIAL_DATE_DIFFERS`; a dimension and center-longitude mismatch returned both expected grid flags. The two real met_em entries reproduce the recorded February 2023 versus July 2025 date difference, horizontal dimensions, and center coordinates. These checks used metadata and Times only. No model arrays, native integration, M/H, optimization, preprocessing, or acquisition was performed.

## Claim boundary

The evidence supports ruling out these two 2023 files as *matching direct met_em candidates for the current 2025 IC/BC grid/date*. The helper compares the initialization day and selected horizontal grid dimensions/attributes; its own docstring correctly calls these necessary checks rather than proof of lineage. Keep the report’s bounded neighborhood scope and its explicit statement that upstream provider, actual preprocessing execution, and independent native cases remain unverified. The UCAR workflow reference describes the general WPS/real workflow; it does not establish this case’s provider or inputs.

The coordinator report and checklist do not claim the two met_em files establish independent dates or current IC/BC ancestry. The retained `real.exe` symlink and forecast namelists are identified as context only. The listed missing WPS/real inputs are explicitly scoped to the inspected top-level SS directory, so this is not a whole-device archive absence claim.

One wording safeguard for any later summary: describe the two files as incompatible direct candidates by date/grid, rather than claiming their upstream data could not have contributed through another preprocessing path. No evidence in this packet identifies such a path.

## Hash and scope verification

`IC_BC_LINEAGE.json.audit_source_sha256` currently matches the final helper source. Its IC/BC and met_em metadata match the source files when re-read. The receipt’s zero native/preprocessing/M/H/optimizer-call counts are consistent with this read-only check. Green’s other sensor audit remains separately scoped: IR133 has the declared calibration/RTTOV difference and unresolved upstream SRF identity, with no pixel BT calculation or numerical error estimate.
