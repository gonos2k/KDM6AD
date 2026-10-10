# PR401 follow-up: four finite-input forward comparisons

Basis: merged main `6adb8049`. The [stored K response](pr401_fixed_input_k_response_2026-10-10/final_v2/REPORT.md) is complete. This phase checks its local linear prediction against finite changes in two representative fixed inputs; it does not repeat native integration, KDM M, optimization or the six-direction matrix audit.

## Predeclared bounded experiment

- [x] Retain the central direct-H baseline at nominal2025-07-19 05:56, j86/i48, its exact seven channels10–16, KMA coordinate, sigma1K, bias0 and fixed support. No fifth baseline call.
- [x] Select only Skin T−0.5K, Skin T+0.5K, reference69-layer O3−1% and O3+1% passed through the saved66×69 interpolation matrix. These scales are linearization probes, not measured input errors or proposed corrections.
- [x] Prepare four isolated cases with fresh outputs, source/input/runtime hashes and a frozen plan. Verify only the designated input changes, including any ASCII serialization difference. Preserve the original case and all PR401 results.
- [x] Complete independent Red preflight before the coordinator's one-shot execution. Retain a maximum of four wrapper launches, no automatic retry; quality loss on any fixed channel is a failed trial, never a smaller objective.
- [x] Execute four declared trials with the existing bounded production runner. Record returned direct and K outputs separately from uninstrumented internal RTTOV calls.
- [x] Report actual channel BT/quality/cost, central finite-difference sensitivity and E± against preserved baseline/K predictions. Show absolute K errors as well as relative errors with an explicit small-response rule.
- [x] Preserve actual trial inputs, raw/converted K, outputs and diagnostics locally with hashes. Complete relevant tests, Green consistency and Red numerical/counterexample review.

## Independent evidence in parallel

- [x] Inspect primary-source SST, upper-temperature and ozone observation definitions/availability. Distinguish skin/subskin/depth/foundation SST and vertical profile sensitivity from column ozone. Mark an actual matched measurement only when its time/location/QA/definition are returned.
- [ ] Obtain actual collocated independent SST/T/O3 values and version-matched QA/sensitivity; catalog metadata inspection above does not complete this.
- [ ] Resolve product-specific upstream IR133 SRF processing history. Common KMA BT representation is already confirmed; no polynomial/header-only correction or one-sided coordinate change.
- [ ] Identify original-provider/archive native IC/BC for two other initial dates; existing archive-path request remains pending without repetition. Do not count same-date variants or two winter met_em times as independent native events.
- [ ] If another input supply is proposed, make it a separately identified research-design decision. Current authorization does not permit silently acquiring/substituting external model/reanalysis under the native-data contract.
- [ ] Apply unchanged seven-channel/all-sky/TQ-prior/fixed-physics assumptions to independent cases only after their original inputs and observation conditions exist; retain failed/clear/stagnant outcomes.

Research-management basis remains **56/75 (74.7%)** until actual new evidence justifies reassessment. Inspection of availability can complete while physical validation and matched observations remain open.
