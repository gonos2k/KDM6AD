# Independent Red review: case-driven native intake and analysis adapter

## Disposition

The case-driven v2 consumer addresses the fixed-date/eight-frame assumptions without changing the frozen PR395 intake or capture helpers. I found no remaining actionable architecture blocker in the reviewed v2 intake/capture boundary. The only permitted ready-state core is one saved background `State` plus its same-time forcing snapshot; the nominal observation slot is explicitly derived by one local 20-second KDM6 step.

## Provenance and counterexample review

- **Legacy run-ID omission is closed in v2.** The actual legacy July 19 `run_identity.json` and `experiment_valid.json` omit run ID fields. V2 therefore requires a separate case-declared, SHA-bound `NATIVE_COMPLETION.json` that names the case run ID and run directory, records successful exit/valid/model completion, and binds the exact hashes of both archived receipts. The V2 July19 replay binds the existing PR397 completion receipt; its actual hash matches the V2 manifest. V2 tests reject missing, changed, wrong-ID, and mismatched-identity completion bindings. The original v1 consumer and its intake/result/pending records remain unchanged.
- **Fixture relabeling is closed.** `run_case_analysis.execute()` checks the requested fixture against the exact established GK2A-AMI template before loading intake or creating the analysis output root. A wrong-fixture test verifies early refusal. Before/after digest lists include prepared pressure, temperature, humidity, gas, cloud, channel-selection, static-skin, configuration/script, coefficient, and executable assets.
- **Observation source binding is explicit.** The consumer binds the original GK2A L1B result, private payload, and decode-metadata receipt by path and SHA-256; it checks scene date/nominal slot, reader metadata, selected pixel, channels 10–16, and all seven DQFs. Before capture, the driver independently compares the seven BT/DQF point values and coordinates against the original private 5×5 payload and refuses native/L1B geolocation separation beyond 2.5 km. Synthetic tests exercise observation-value and geometry counterexamples before the capture entry.
- **The local time contract stays scoped.** V2 requires initialization no later than the native background time, the exact background WRF `Times` record, and nominal slot = background + 20 s. Optional diagnostic `Times` are read only when specifically requested and present; they are not required for core intake. The 20-second forcing is explicitly a frozen background snapshot for one local KDM6 step. The consumer does not claim lateral-boundary support at the observation slot or full-host advancement; it makes no boundary-coverage gate for this local step.
- **The capture path has no fabricated slot frame.** A fresh capture-module instance replaces only its input validator and extends the source snapshot. State time index 0 is marked `SAVED_NATIVE_BACKGROUND`; index 1 is marked `DERIVED_LOCAL_M_SLOT_NOT_SAVED_HOST`. `_validate_predeclared_run()` retains the existing one-forcing, `obs_time=1`, 20-second, max-3, seven-channel T/Q control contract. `_private_payload()` uses background host dry mass `[39]` and does not require the old `[8,39]` history for its core capture.

## Demonstrated evidence

The actual V2 replay selected only the retained July19 05:55:40 background frame. Its readiness manifest records one selected time, the exact case-linked completion receipt, no bound observation (`NATIVE_CORE_INTAKE_ONLY`), and `analysis_executed=false`. It matches all **70 common arrays** against the historical PR395 frame-zero intake; V2 also contains one additional native-window density array. The comparison records zero model, H, M, optimizer, or acquisition calls. This is a same-input intake-reproducibility replay, not a new-date result.

The distinct July20 and July21 V2 outputs remain `PENDING_NATIVE_INPUT`; each has no selected run ID, no NPZ, and no analysis. Their case contracts retain the same three bound PR403 observation artifacts. No new native archive search, acquisition, or new-date model/observation analysis was performed.

The focused suite re-run for this review was:

```text
python3 -m pytest -q harness/evidence/pr406_native_case_consumer_2026-10-11/test_native_case_intake.py harness/evidence/pr406_native_case_consumer_2026-10-11/test_case_analysis_adapter.py oracle/tests/test_native_case_consumer_contract.py
```

Result: **38 passed** using `/opt/local/bin/python3` (Python 3.10.11). The repository validation record separately attributes 24 focused intake/adapter cases and a 14-case portable facade that reuses an overlapping subset. No full historical suite was run.

## Evidence limits

The replay only proves core intake reproducibility for the retained July19 run. The adapter test deliberately stops at analysis-runner entry before M, H, or the optimizer. No native forecast was run for July20/21, and neither pending case supports an analysis conclusion. Fixture/source hash checks are implemented and unit-exercised; no actual H call was run to demonstrate runtime asset immutability. The nominal filename-time-as-model-UTC assumption remains explicit, observed pixel UTC remains unset, and science/physical-matchup acceptance remains false.
