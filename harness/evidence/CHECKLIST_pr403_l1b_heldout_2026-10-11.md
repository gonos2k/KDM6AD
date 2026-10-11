# PR403: held-out AMI L1B observation scenes

Basis: main `3e67ca00` and the [current observation contract](CURRENT_OBSERVATION_DATA_CONTRACT.md). Completion uses the [AMI L1B research-edition matrix](AMI_L1B_RESEARCH_EDITION_COMPLETION.md); outside sensors/L2 are later extensions, not current prerequisites.

- [x] Preselect observation dates2025-07-20 and2025-07-21, distinct from the July19 setup case, with nominal OBT filename slot05:56. These are separated scene dates, not proof of independent meteorological events.
- [x] Fix the geographic target35.415660858N122.143310547E and nine thermal channels8–16, retaining analysis channels10–16. Geometric point/5×5 patch selection does not depend on observed BT, DQF or residual fit.
- [x] Freeze a source-bound acquisition/processing plan before values are inspected. Exact05:56 is preferred; if missing, choose a complete nine-channel slot within±10nominal minutes by timestamp alone, tie earlier. Record the missing exact slot; do not change dates or use another scene family silently.
- [x] Obtain at most18 small LA020GE originals from the declared public L1B prefixes, size/hash-check and preserve original bytes privately. No L2/VIIRS/MLS/external-observation input.
- [x] Read both new scenes through the unchanged production LA reader and exact paired calibration. Preserve DN/radiance/BT/DQF, original row/column, geolocation, raw time/navigation/calibration attributes and failure outcomes.
- [x] Apply the same strict DQF0 policy for the seven analysis channels. Report all raw quality categories/invalid flags separately; DQF0 is not a clear-sky or liquid-cloud label.
- [x] Keep nominal OBT, planned UTC and unverified actual pixel UTC distinct. Use conditional time assumptions only when stated, not as automatic model correspondence.
- [x] Report fixed-location point/patch statistics and any radiance-first aggregation as descriptive observation evidence, not calibrated R or a validated footprint. Preserve off-scene/no-support results without replacing the point by a better pixel.
- [x] Complete relevant selection/source/shape/time tests and independent Green/Red review; update code/semantic graph relationships and source custody.
- [ ] Obtain matching original native inputs for the new dates and run the same declared baseline/analysis/audit configuration. This is a separate model-connected step; July19 native state cannot become a valid July20/21 analysis merely by relabeling or attaching new BT.

No new H/KDM M/native run/optimizer is part of the observation-only stage. Existing Skin/O3 finite checks and stored-K arithmetic remain closed. External SST/profiles/phase are deferred; no credential response is needed for the withdrawn external/L2 questions.

Evidence: [execution report](pr403_l1b_heldout_2026-10-11/REPORT.md), [Green](pr403_l1b_heldout_2026-10-11/GREEN_REVIEW.md), [Red](pr403_l1b_heldout_2026-10-11/RED_REVIEW.md), [coverage](pr403_l1b_heldout_2026-10-11/COVERAGE_REVIEW.md), [validation](pr403_l1b_heldout_2026-10-11/VALIDATION.json). Local21 tests passed; graph code and scoped semantic relationships refreshed. No new score assigned.
