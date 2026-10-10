---
title: PR400 actual product and fixed-input compatibility
date: 2026-10-10
type: source
status: bounded-audit-complete-scientific-input-evidence-open
---

# Actual product and fixed-input compatibility

After [[pr399-vertical-and-neighbor-h-2026-10-10]], the completed 3×3 vertical and direct-H comparisons remain fixed. The next audit reads existing product metadata, coefficient information, saved active profiles/K outputs and original-case input headers; it does not repeat radiation or native integration.

## Sensor definition

The actual nine LA files match their receipt and NMSC v3.0 calibration tuple. Installed RTTOV metadata names the shifted KMA IR133 SRF and v3.1 center; the NMSC workbook comparison separately gives the changed conversion polynomial. Channels10–15 agree in these comparisons; IR133 differs. The actual upstream LA SRF is not named in its headers, so the evidence is a calibration-coordinate mismatch with upstream SRF unverified, not a quantified BT error or a physical explanation for all channels.

## Fixed inputs

Saved nine active profiles and surfaces were reconstructed and compared. Each extended profile has27 reference layers plus39native levels. O3/CO2 use a common reference fixture; six native levels per column exceed its maximum pressure and hold its interpolation endpoint. Nine existing direct RTTOV K products contain gas/selected surface sensitivity. These are not model-composed control gradients, external physical truth or proof of input error.

## Native source lineage

Current July2025 IC/BC resolve to the original SS case directory. Its two February2023 met_em files differ in date/grid/center and cannot be attributed as parents. Forecast namelists and a real.exe link do not identify the original raw meteorological provider. Original preprocessing records and independent native initial dates remain unavailable in this bounded inventory; there is no full-device absence claim or substitute external model data.

## Evidence and next action

- [Coordinator report](../../harness/evidence/pr400_input_compatibility_2026-10-10/COORDINATOR_REPORT.md)
- [Checklist](../../harness/evidence/CHECKLIST_pr400_input_compatibility_2026-10-10.md)
- [Sensor audit](../../harness/evidence/pr400_input_compatibility_2026-10-10/SENSOR_COMPATIBILITY.json)
- [Fixed inputs](../../harness/evidence/pr400_input_compatibility_2026-10-10/FIXED_INPUTS.json)
- [Lineage](../../harness/evidence/pr400_input_compatibility_2026-10-10/IC_BC_LINEAGE.json)

Resolve product-specific upstream SRF/calibration compatibility and original matching IC/BC lineage before a separately identified corrected baseline or independent-date analysis. Existing channel/prior/bias assumptions and artifacts remain unchanged. Score56/75 is the user's research-management basis, not coverage or correctness probability.
