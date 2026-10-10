# PR400: actual input compatibility and native source lineage

## Outcome

The PR399 review's three immediate investigations are now executed: actual product/coefficient compatibility, fixed gas/surface inputs and existing K inventory, and a bounded original-case IC/BC lineage search. The [checklist](../CHECKLIST_pr400_input_compatibility_2026-10-10.md) separates completed investigations from unresolved scientific evidence. Production physics, AD, solver, observed BT, channels, costs, sigma and bias remain unchanged.

## Sensor finding

All nine pinned AMI LA files declare and numerically match NMSC v3.0 calibration metadata. The installed coefficient README identifies the shifted KMA IR133 SRF and v3.1 center. The NMSC workbook comparison separately establishes the changed Teff-to-BT polynomial; this is not a polynomial extracted from RTTOV metadata. The sole selected-channel difference is IR133: 753.590621 versus 752.792488 cm⁻¹. Channels 10–15 align in these table/center comparisons. See [full audit](SENSOR_COMPATIBILITY_REPORT.md), [receipt](SENSOR_COMPATIBILITY.json) and [coefficient utility output](RTTOV_COEF_INFO.txt).

The LA headers do not identify the upstream SRF payload. This is an established calibration-coordinate mismatch with unresolved upstream SRF identity, not a proof of physical sensor error, quantified BT error or the cause of all seven residuals. The official [NMSC listing](https://nmsc.kma.go.kr/enhome/html/base/cmm/selectPage.do?page=static.utilization.software) supplies both calibration versions. No table or coefficient was silently replaced. A product-specific compatibility decision is still required before representing IR133 as a fully verified matchup; a justified correction would require a separately identified baseline.

## Actual fixed inputs and retained derivatives

The [fixed-input report](REPORT.md) and [receipt](FIXED_INPUTS.json) verify all nine saved active profiles/surfaces. Each case retains 27 upper reference and 39 native layers. O3/CO2 originate in the same 69-layer reference fixture and are interpolated in log pressure. Six native levels per column exceed its 931.65625 hPa source maximum and use the held endpoint. These are reproducible assumptions, not independently validated gas profiles.

Eight new neighbor and one reused center direct RTTOV K files already exist. They include gas, temperature/humidity and selected surface sensitivities. Their nonzero values do not establish input error or model-composed sensitivity; zero emissivity/FASTEM outputs do not prove global insensitivity. There was no new radiation evaluation. Fixed-input perturbation experiments should use explicitly sourced or explicitly exploratory ranges and preserve the existing result.

## Original IC/BC source search

The [read-only helper](audit_ic_bc_lineage.py) follows canonical `host/lc05_da_run` IC/BC symlinks to the original SS directory. [IC_BC_LINEAGE.json](IC_BC_LINEAGE.json) records file size/mtime, selected headers, Times, dimensions, namelist hashes and missing preprocessing records. Only Times and metadata were read from these NetCDFs; large files were not rehashed.

Current IC/BC are July 19, 2025, on a 234×282 native grid. Two met_em files in the original case directory contain February 16, 2023 times and a 199×249 grid with a different center. They are incompatible as matching direct met_em candidates for the current IC/BC; their presence establishes neither two independent dates nor independent native cases. This does not rule out every other upstream preprocessing path. The forecast namelists and a `real.exe` symlink do not recover the original preprocessing provenance. `namelist.wps`, Vtable, ungrib/metgrid/real logs are absent from the inspected top-level directory.

The general [UCAR initialization workflow](https://www2.mmm.ucar.edu/wrf/site/users_guide/real_initialization.html) explains how met_em feeds real.exe to produce IC/BC; it does not identify this case's meteorological provider. That provider and matching upstream inputs remain **UNVERIFIED**. The search is bounded to the original case neighborhood, not a claim of absence across the user's devices or institutional archive. No external model/reanalysis was acquired or substituted. The prior archive-path request remains pending without being asked again.

## Validation and limits

Green examined sensor metadata and Red independently examined actual fixed inputs and the sensor conclusion. Root executed the bounded lineage helper. Final team findings and validation receipt accompany this report. This phase runs no native integration, preprocessing, KDM, radiation H, composed Model_H or optimization. The coefficient metadata utility only reads coefficient information. Previous numerical and physical results remain immutable and distinct from these provenance checks.

Graphify queries were used before edits and its structural/semantic relationships refreshed afterward. Generic lineage query coverage was incomplete; NetCDF/source evidence remains authoritative. Research management score stays **56/75 (74.7%)**, with independent native dates, product-specific SRF identity, physical input validation and full flux budgets open.
