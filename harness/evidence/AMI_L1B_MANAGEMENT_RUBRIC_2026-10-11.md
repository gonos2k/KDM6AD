# AMI L1B research-edition management rubric

This transcribes the reviewer-proposed 2026-10-11 management assessment in the conversation reviews relayed through user messages (PR403 at main `6bdcdccc`). Relaying that review does not make its score a user-defined scientific criterion. The eight areas and scores are historical management context; this note neither independently awards points nor measures completion of the broader hydrometeor-process goal. See the [current problem/evidence distinction](AMI_L1B_RESEARCH_EDITION_COMPLETION.md).

| Review management area | Maximum | Review score | Current evidence basis and remaining limit |
|---|---:|---:|---|
| L1B provenance/decoding/calibration/missingness | 15 | 14 | Two held-out GK2A AMI L1B scenes were acquired and decoded. PR404 addresses the PR403 sidecar's source-mask handling. That correction does not increment the review score without a new assessment. |
| RTTOV coordinate/channel/configuration | 15 | 12 | Existing July 19 direct-H/K evidence uses the paired KMA coordinate; the upstream product-specific IR133 SRF identity remains unverified. |
| Time/location/spatial usage | 10 | 8 | Fixed-point geolocation and point/patch use are retained; observed pixel UTC and footprint correspondence remain unverified. |
| T/Q controls/fixed physics | 10 | 10 | The current declared T/Q control and fixed-physics configuration remains explicit. This is a reviewer-proposed management score. |
| Baseline/analysis/final audit/failure | 15 | 13 | A bounded July 19 analysis and its returned state/gradient/failure boundaries are documented; July 20/21 native inputs and analyses remain pending. |
| Numerical/physical diagnostics | 15 | 11 | Saved-state, control and finite-response diagnostics are available with stated limits; they are not a closed flux budget or a claim of global validity. |
| Other-date model-connected repeatability | 15 | 5 | Two new-date L1B scene intakes are complete, but same-configuration analyses with matching original native inputs remain pending. Separate scene dates are not asserted as independent meteorological events. |
| Prior/sigma/bias assumption management | 5 | 5 | The 1 K sigma, zero bias and T/Q prior remain identified as exploratory assumptions. |
| **Total** | **100** | **78** | **Review-proposed total; no new score is computed here.** |

This 78/100 score is a conversation-review management proposal, not a correctness probability, validation statistic or model-performance measure. The historical 56/75 assessment belongs to a broader rubric and is not converted into or averaged with this scale. External SST, MLS, VIIRS and L2 products are deferred extensions, not current completion deductions.

PR404's packed-source-mask sidecar correction is a data-preservation fix within the first rubric area. No incremental score is assigned for that fix; later review reassessment must remain separate from scientific acceptance. The evidence map is the [current completion matrix](AMI_L1B_RESEARCH_EDITION_COMPLETION.md) and [PR403 held-out checklist](CHECKLIST_pr403_l1b_heldout_2026-10-11.md). The [PR404 checklist](CHECKLIST_pr404_l1b_source_mask_2026-10-11.md) records the mask correction, bounded verification and pending model-connected steps.

## Review update at PR404 main cc0a2edb

The subsequent review conveyed in the conversation keeps the same8-area100-point rubric and changes the first L1B area14→15, for **79/100**. The score vector is `[15,12,8,10,13,11,5,5]`; all other areas are unchanged. This supersedes78 as the historical review-management reference, while the table above remains its historical PR403 transcription. Source-mask repair is the review's stated basis for+1; boundary-time clarification and file/test/PR counts add no automatic points. See the [valid-time checklist](CHECKLIST_pr405_native_valid_time_2026-10-11.md) for actual remaining native input/analysis dependencies.

## Attribution correction and use

The later problem-definition review clarifies that79/100 was proposed by the reviewer, not established by the user as a mathematical, physical or scientific performance criterion. Previous user-owned/user-supplied labels in dated records are superseded by this attribution note; executed code/receipts are not rewritten. The vector `[15,12,8,10,13,11,5,5]` and historical78→79 arithmetic remain unchanged. No new overall research-completion percentage is assigned. Calculation, numerical validation and claim-matched research interpretation are assessed separately in the current completion document. A score, repository citation, test count or repeated date execution cannot certify process contribution by itself.
