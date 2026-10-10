# PR400 final Green review

## Disposition

The coordinator report, checklist, sensor and fixed-input audits, and IC/BC lineage receipt are consistent in their stated scope. The completed work is correctly described as bounded metadata, saved-input and output investigations. I found no blocker that changes the reported conclusions or the remaining open evidence.

## Evidence and claim boundaries

The sensor audit binds the nine actual LA files to their receipt and supports the v3.0 calibration tuple. The refreshed sensor helper hash matches the audit receipt; the RTTOV coefficient hash remains the same coefficient recorded by the PR399 run plan. The mismatch is isolated to IR133: the product's v3.0 calibration values differ from the v3.1 NMSC polynomial, while RTTOV metadata identifies the shifted center and KMA SRF. The coordinator report now attributes the polynomial comparison to the NMSC workbooks, not the RTTOV coefficient README. The LA headers still do not identify the upstream SRF payload, and no image BT error or cause for all seven residuals is claimed.

The fixed-input report and Red review support the stated profile and surface comparisons and the inventory of eight new neighbor plus one reused center direct RTTOV K products. These outputs are not presented as KDM6AD Model_H, control-space derivatives or evidence that an input is wrong. The endpoint-held O3/CO2 values remain reproducible fixture assumptions. The report correctly leaves physical validity of the fixture atmosphere and surface model open.

The IC/BC helper hash matches `IC_BC_LINEAGE.json`. I independently confirmed the live IC/BC symlink targets, sizes and mtimes against the receipt, and rechecked the saved dimensions and Times. The receipt explicitly says whole-file hashes were not computed. It identifies the July 19, 2025, 234×282×39 IC/BC metadata and two February 16, 2023 met_em candidates on a 199×249 grid with a different center. Those files are incompatible as matching direct candidates; this does not exclude every other preprocessing path. The missing WPS/real records are bounded to the inspected original SS directory, not the user's device or archive as a whole.

## Completed work and open evidence

The completed investigations are actual LA calibration/RTTOV compatibility, reconstruction and comparison of saved fixed profiles and surfaces with existing direct K outputs, and a bounded read-only IC/BC source-directory inventory. Their unresolved questions remain open: upstream IR133 SRF identity, physical support for fixed gas/surface ranges, the original meteorological provider and preprocessing trail, matching IC/BC for other dates, independent native events, observation cloud height/optics and QA, and complete water/heat closure. The score remains 56/75 as a research-management score, not a correctness probability.

The wiki source is a faithful short synthesis of these results and open limits. The current Graphify query covers the coordinator and sensor report but remains incomplete for the lineage helper and checklist; the scoped semantic fragment below records those relationships and distinguishes extracted facts from the direct-candidate inference.

## Validation scope

This review read saved JSON/reports and checked source hashes and existing file metadata only. No observation pixel arrays, meteorological arrays, model runs, preprocessing, RTTOV H, M, optimizer or external data acquisition were used.
