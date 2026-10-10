---
title: PR402 actual finite fixed-input response
date: 2026-10-11
type: source
status: four-trial-complete-independent-matchups-open
---

# Four actual finite perturbations

Following [[pr401-fixed-input-k-response-2026-10-10]], four isolated RTTOV wrapper launches evaluated Skin T±0.5K and common referenceO3±1% at the same nominal05:56 central direct-H state. The original baseline and inputs remained unchanged. All seven channels retained quality0; fresh direct and K-path BT agree exactly. Four direct output sets and four K sets returned, but internal RTTOV H/AD calls were not instrumented. No native, KDM M or optimizer ran.

## Conditional numerical result

Maximum one-sided linearization errors were0.000359254K for skin and0.000425317K for O3. Central differences normalize by2h, with h=.5 in the+1K skin direction and h=1 in the+1% O3 source direction. Maximum derivative discrepancies were1.63822e−6 and1.91032e−6K per respective unit. Ideal and actual serialized-input errors are separate. The weak O3 IR112 response has about0.65% relative discrepancy yet only1.02e−8K/unit absolute discrepancy; absolute values remain visible.

These results describe two chosen steps at one fixed state, not actual SST/O3 errors, fitting corrections, independent cases or higher derivative accuracy. Historical baseline hydrotable/dylib hashes were not recorded; current assets are frozen across the four runs. E± uses the preserved baseline conditionally, while the central pair difference cancels B0.

## Independent sources and open evidence

Official catalog queries found a NOAA-20 SST-subskin granule candidate and daily MLS V005 T/O3 metadata. No matched SST pixel or MLS profile/QA was obtained; unauthenticated MLS access returned401. Skin and subskin remain different quantities. Upper reference levels may be assessed only where the retrieval covers them with useful sensitivity, separately from39native levels. V005 data need V5 quality guidance, not V6 thresholds.

Original IC/BC provenance, other native initial dates, product-specific upstream IR133 SRF, actual independent input-error ranges and full water/heat external terms remain open. User research-management score stays56/75. No alternate model/reanalysis or residual-fitted input was acquired.

- [Coordinator report](../../harness/evidence/pr402_finite_input_response_2026-10-11/COORDINATOR_REPORT.md)
- [Actual numerical report](../../harness/evidence/pr402_finite_input_response_2026-10-11/final_v4/NUMERICAL_REPORT.md)
- [Frozen plan and execution index](../../harness/evidence/pr402_finite_input_response_2026-10-11/final_v4/REPORT.md)
- [Independent input scope](../../harness/evidence/pr402_finite_input_response_2026-10-11/INDEPENDENT_INPUTS_SCOPE.md)
- [Checklist](../../harness/evidence/CHECKLIST_pr402_finite_input_response_2026-10-11.md)
