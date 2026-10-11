# AMI L1B research-edition management rubric

This records the user-supplied 2026-10-11 assessment for the PR403 review at main `6bdcdccc`. The eight headings, maximum points and awarded points below follow the user's rubric in the same order as the current [AMI L1B research-edition matrix](AMI_L1B_RESEARCH_EDITION_COMPLETION.md). This note transcribes that assessment; it does not recalculate or independently award points.

| User rubric area | Maximum | User score | Current evidence basis and remaining limit |
|---|---:|---:|---|
| L1B provenance/decoding/calibration/missingness | 15 | 14 | Two held-out GK2A AMI L1B scenes were acquired and decoded. PR404 addresses the PR403 sidecar's source-mask handling. That correction does not increment the user score without a new assessment. |
| RTTOV coordinate/channel/configuration | 15 | 12 | Existing July 19 direct-H/K evidence uses the paired KMA coordinate; the upstream product-specific IR133 SRF identity remains unverified. |
| Time/location/spatial usage | 10 | 8 | Fixed-point geolocation and point/patch use are retained; observed pixel UTC and footprint correspondence remain unverified. |
| T/Q controls/fixed physics | 10 | 10 | The current declared T/Q control and fixed-physics configuration remains explicit. This rubric score is user-supplied. |
| Baseline/analysis/final audit/failure | 15 | 13 | A bounded July 19 analysis and its returned state/gradient/failure boundaries are documented; July 20/21 native inputs and analyses remain pending. |
| Numerical/physical diagnostics | 15 | 11 | Saved-state, control and finite-response diagnostics are available with stated limits; they are not a closed flux budget or a claim of global validity. |
| Other-date model-connected repeatability | 15 | 5 | Two new-date L1B scene intakes are complete, but same-configuration analyses with matching original native inputs remain pending. Separate scene dates are not asserted as independent meteorological events. |
| Prior/sigma/bias assumption management | 5 | 5 | The 1 K sigma, zero bias and T/Q prior remain identified as exploratory assumptions. |
| **Total** | **100** | **78** | **User-assigned total; no new score is computed here.** |

This 78/100 score is a user-owned research-management assessment, not a correctness probability, validation statistic or model-performance measure. The historical 56/75 assessment belongs to a broader rubric and is not converted into or averaged with this scale. External SST, MLS, VIIRS and L2 products are deferred extensions, not current completion deductions.

PR404's packed-source-mask sidecar correction is a data-preservation fix within the first rubric area. No incremental score is assigned for that fix; any changed score requires a later user rubric assessment. The evidence map is the [current completion matrix](AMI_L1B_RESEARCH_EDITION_COMPLETION.md) and [PR403 held-out checklist](CHECKLIST_pr403_l1b_heldout_2026-10-11.md). The [PR404 checklist](CHECKLIST_pr404_l1b_source_mask_2026-10-11.md) records the mask correction, bounded verification and pending model-connected steps.

## User update at PR404 main cc0a2edb

The subsequent user review keeps the same8-area100-point rubric and changes the first L1B area14→15, for **79/100**. The score vector is `[15,12,8,10,13,11,5,5]`; all other areas are unchanged. This supersedes78 as the current user-owned management baseline, while the table above remains its historical PR403 transcription. Source-mask repair is the user's stated basis for+1; boundary-time clarification and file/test/PR counts add no automatic points. See the [valid-time checklist](CHECKLIST_pr405_native_valid_time_2026-10-11.md) for actual remaining native input/analysis dependencies.
