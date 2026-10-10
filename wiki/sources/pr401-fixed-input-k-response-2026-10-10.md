---
title: PR401 fixed-input response from preserved center RTTOV K
date: 2026-10-10
type: source
status: stored-k-response-complete-external-input-evidence-open
---

# Fixed-input response in the common KMA BT coordinate

This follows [[pr400-input-compatibility-2026-10-10]]. The central direct-H state at nominal05:56, j86/i48, is retained; it is not the accepted T/Q analysis. Same-run raw BT/radiance and K replay through the production parser and `transform_rttov_to_kma`, with zero difference from the old central KMA BT. Gas/source/Q2 units are bound as ppmv over moist air and the saved `adk_bt`/`use_q2m` options checked.

## Actual conditional results

All six declared unit directions were contracted with the converted saved K. The dimensionless first-order Huber deltaJo is +2.303125 for skinT+1K, −0.141807 for referenceO3+1%, −0.044500 for referenceCO2+1%, −0.00299964 for Q2ppmv+1%, +0.234693 for upperT+1K and −0.00008136 for upperQ+1%. Native T/Q stay fixed in the upper-reference directions. These sizes are exploratory directions, not actual error estimates, corrections or a cross-input importance ranking.

The 66×69 log-pressure interpolation matrix preserves the common gas-source endpoint. Six layers fully hold it, while two additional layers carry partial weights0.202599/0.866922. Source-K includes both supports coherently; squared independent-layer errors would represent a different problem.

## Interpretation and evidence

The existing BT coordinate path already compares modeled and observed values in the same representation. Upstream LA SRF identity remains unresolved; table/header changes alone do not create a different spectral-response coefficient. First-six/IR133 cost terms are a split of the same seven-channel result, not a six-channel analysis. No native, preprocessing, radiation H, new K, KDM M or optimizer was run.

- [Coordinator report](../../harness/evidence/pr401_fixed_input_k_response_2026-10-10/COORDINATOR_REPORT.md)
- [Final-v2 response](../../harness/evidence/pr401_fixed_input_k_response_2026-10-10/final_v2/REPORT.md)
- [Structured evidence](../../harness/evidence/pr401_fixed_input_k_response_2026-10-10/final_v2/K_RESPONSE.json)
- [Checklist](../../harness/evidence/CHECKLIST_pr401_fixed_input_k_response_2026-10-10.md)
- [Initial execution limitations](../../harness/evidence/pr401_fixed_input_k_response_2026-10-10/initial_read_only_audit/EXECUTION_HISTORY.json)

Exact K/input/perturbation arrays remain private and hash-bound; final-v2 executed source is preserved. The initial superseded source bytes were not preserved, as its history explicitly records. Product-specific SRF, physically supported input-error ranges, original IC/BC lineage, independent native dates and full flux budgets remain open. User research-management basis stays56/75; this does not estimate accuracy probability or coverage.
