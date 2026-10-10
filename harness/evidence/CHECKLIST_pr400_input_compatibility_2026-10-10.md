# PR399 review follow-up: input compatibility and independent-case checklist

Basis: merged PR399 `7ff5a38d`. Evidence packet: [PR400](pr400_input_compatibility_2026-10-10/COORDINATOR_REPORT.md).
Checks are marked complete when the stated investigation was executed; a completed investigation may leave its scientific question open.

## Completed investigations

- [x] Preserve the completed vertical/neighbor-H diagnostics and the corrected 297-pair denominator. No repeated optimization, native integration or neighboring radiation calculation.
- [x] Bind the actual nine AMI LA files to the saved acquisition receipt, then inspect product processing/calibration headers. All nine declare v3.0 and match its eight stored conversion values.
- [x] Compare official NMSC v3.0/v3.1 calibration tables and published IR133 SRFs with the installed RTTOV coefficient metadata and channel order. Channels 10–15 align; IR133's declared calibration tuple differs. See [sensor audit](pr400_input_compatibility_2026-10-10/SENSOR_COMPATIBILITY_REPORT.md).
- [x] Trace the actual upper reference atmosphere, O3/CO2 interpolation and nine surface/near-surface inputs. Preserve the six endpoint-held gas levels per column as an assumption. See [fixed-input audit](pr400_input_compatibility_2026-10-10/REPORT.md).
- [x] Inventory existing direct RTTOV K files rather than call radiation again. Distinguish these products from a KDM-composed or control-space derivative.
- [x] Follow current IC/BC symlinks and inspect the original SS directory for preprocessing evidence. The two February 2023 met_em files differ from July 2025 IC in date and grid; no parentage or independent native case is inferred. See [lineage receipt](pr400_input_compatibility_2026-10-10/IC_BC_LINEAGE.json).

## Open evidence and next actions, in order

- [ ] **IR133 product/operator compatibility:** establish the actual upstream LA SRF and applicable calibration history from a product-specific authoritative record. Closure requires more than the v3.0 label. Preserve the current seven-channel exploratory result; any justified table/coefficient correction must create a separately identified baseline, not overwrite it or remove a channel silently.
- [ ] **Fixed-input physical ranges:** obtain external, case-relevant support for gas/reference-atmosphere and surface assumptions before declaring numerical perturbation ranges physically justified. Existing K products can guide a separately declared sensitivity experiment; they do not prove any input is wrong.
- [ ] **Original IC/BC lineage:** identify matching-date/grid met_em, original namelist.wps/Vtable/logs or acquisition manifest tied to July 19 IC/BC. Raw provider remains unknown. Existing archive-path request remains pending; do not repeat it or substitute external model data.
- [ ] **Independent native dates:** obtain original native IC/BC for two other initial dates, selected by observation QA/phase/time/location and data availability rather than BT fit. Other-date met_em alone, same-date restarts and physics variants do not close this item.
- [ ] **Independent analysis:** after the preceding inputs exist, apply the same seven channels, 1 K sigma, zero bias, T/Q prior, fixed physics and all-sky operator; preserve failures, clear endpoints and accepted states/gradients.
- [ ] **Cloud height/optics:** inspect available same-granule products with their QA, geolocation and time; do not copy the center height or equate sample phase fractions with area cloud fraction.
- [ ] **Water/heat closure and generality:** retain conditional budget status until boundary/external terms and independently attributed experiments are available.

## Completion accounting

Research score remains **56/75 (74.7%)**. Metadata audits strengthen provenance; they do not add independent events, validated B/R, physical flux closure or forecast skill. Final Green/Red findings are in the evidence packet. No native, M, H or optimizer calls are made by this follow-up; the coefficient information utility is metadata-only.
