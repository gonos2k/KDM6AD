# Case-driven native core and bounded analysis connection

Basis: main `2a7c09d8`, PR405 user review, 2026-10-11. GK2A AMI L1B is the only satellite-observation input. This packet implements the next case-consumer boundary; it does not claim July20/21 analysis or award management points.

## Result and executed scope

The historical PR395 July19 intake is unchanged. The current `intake_native_case_v2.py` accepts a case-bound run ID, initialization/background valid time, native column and original decoded L1B bindings. It reads exact saved background hyperslabs, with optional saved diagnostics kept separate. The local20s observation slot is derived by M rather than fabricated as a saved host frame.

Actual native I/O was confined to a fresh core intake replay of the retained July19 archive. It selected only saved frame index0, `2025-07-19_05:55:40`. The 70 common arrays matched the historical PR395 intake at that same first saved time: static arrays compare directly, and 42 time-dependent arrays compare the new singleton frame with the historical eight-frame array's first slice. The v2 NPZ has one additional native background dry-density array. The bound PR397 completion receipt records launcher exit0 and `model_completed=true`, while also retaining outer-harness exit120 (cause unconfirmed) and `science_accepted=false`. This replay validates consumer intake only; it does not resolve that harness status or grant scientific acceptance. Native-only readiness is refused by the default analysis loader because it has no bound held-out L1B observation.

July20/21 case processing retained the original PR403 result, payload and reader-metadata hashes and returned `PENDING_NATIVE_INPUT`. Neither case opened a forecast or created a native NPZ. Matching native run/state/forcing and actual baseline→analysis→final-audit remain outstanding. Existing archive requests and inventories were not repeated. No external model/reanalysis input was acquired or substituted.

The initially executed `intake_native_case.py` and its CORE_REPLAY19/PENDING records are retained as frozen v1 evidence. V2 adds the team-review provenance fix and has separate replay/pending records and output paths. Its ready-case gate requires a separate SHA-bound completion receipt identifying the exact archive and binding the archived identity/validity receipt hashes. The historical PR397 receipt supplies this link; original producer receipts remain unchanged. V1 is not the future analysis consumer.

## Analysis connection and fixed contract

`case_capture_adapter.py` imports an isolated legacy capture module, replacing only its case-input validator and extending source snapshots. The production M/H, cost, minimizer, accepted-point audit and state/control/full-gradient checkpoint body remain unchanged. `run_case_analysis.py` constructs the existing sea-column, 39-native/27-reference-layer configuration with native-preserving pressure suffixes and one frozen20s forcing. All-sky, channels10–16, T/Q-only control, fixed physics, sigma1K, bias0, Huber1 and existing T/Q prior remain fixed.

Analysis admission requires the original decoded L1B payload/result/metadata, seven finite DQF0 point values, a native-to-L1B distance within2.5km and the established GK2A-AMI template. Before/after immutable digests include prepared pressure/T/Q/gas/cloud inputs, channels, static skin, namelist/scripts, coefficient and executable. Dynamic T/Q/cloud/surface/geometry are supplied through the existing per-H isolated writer. Historical fixture/run paths containing `viirs` are names, not new VIIRS observations consumed by this adapter.

Synthetic tests exercise real NetCDF hyperslab semantics and case admission. Adapter tests bind a synthetic different valid date, verify State/Forcing mutation refusal and geometry/payload/fixture rejection, then deliberately stop at the analysis entry before M, H or optimizer. These are not executed new-date geophysical analyses. The portable oracle-CI facade exposes only receipt/case/pending/L1B/fixture tests; private reference/native intake and capture-admission tests remain local coverage.

## Team findings resolved

1. V1 could accept an archive whose identity/valid producer receipts omitted run ID. The actual historical schema also lacks these fields. V2 requires a separately named, SHA-bound completion receipt declaring the exact run ID and directory and binding both archived receipt hashes. The existing PR397 record supplies this linkage without changing producer files. Missing, changed or wrong completion bindings are rejected.
2. An arbitrary caller fixture could be relabeled as the established AMI pair. The driver now rejects a different template path before loading intake or creating output directories.
3. The first immutable-asset list omitted T/Q/channel files. The final list covers all prepared atmospheric vectors, cloud templates, channel selection and static skin as well as executable/configuration assets.

See [Green](GREEN_CASE_REVIEW.md) and [Red](RED_CASE_REVIEW.md) reviews for demonstrated coverage and counterexamples, and [validation](VALIDATION.json) for24 unique local cases; the14 portable cases are a repeated subset. The current executed records are [v2 intake](CORE_REPLAY19_V2_INTAKE.json), [comparison](CORE_REPLAY19_V2_COMPARISON.json), [July20](PENDING_20250720_V2.json) and [July21](PENDING_20250721_V2.json). No changed production microphysics/AD path was involved.

## Remaining limits and next operation

Run identity and input reproducibility do not establish physical truth. Pixel UTC, actual footprint correspondence and IR133 upstream product SRF remain conditional; nominal-filename-as-model-UTC and existing upper atmosphere/gas/surface assumptions are explicit. Local20s held forcing is not full-host advancement and does not assert lateral-boundary coverage or flux closure. Defined water/heat changes retain their existing measure and unmeasured-flux limitations.

Create a new case/output ID when real native inputs become available; do not modify the preserved pending records, rename July19 states or manufacture host frames. Run the first ready date independently, retain fixed support and stop on quality loss, then compare costs/gradients, BT, T/Q and modeled water/heat responses across dates. No cloud-generation outcome is forced and no residual-based sigma/bias tuning is introduced.

The user-owned **79/100** assessment is unchanged. External SST/MLS/VIIRS/L2 are deferred extensions, not current gates. Focused validation details and exact execution evidence are recorded in the packet; broad CI is attributed separately to its head and is not private native/RTTOV coverage.
