# Positive synthetic-H capture, without a new consumer

Basis: main `a42024a8`, PR407 user review, GK2A AMI L1B-only internal research scope. This packet adds one positive integration case. It keeps the V4 consumer, case adapter/driver, time/provenance gates, physics, AD, solver and prior/error settings unchanged.

## Executed path

The test reuses `pr407.../test_case_analysis_adapter.py::bound_ready_case` for explicitly synthetic native-style NetCDF, case/run receipts and nine-channel point data. It uses the existing `oracle/tests/test_da_single_column.py::_install_synthetic_allsky` fixture and `InlinePool`. Only the H boundary is replaced by that fixture. The default real `run_single_column_analysis`, normalized-dry20s KDM step, AD pullback, L-BFGS, final accepted-point audit, capture validators and checkpoint writer execute. No fake minimizer result, audit trace or gradient is supplied.

The source requires local pinned P8W/upper-reference assets to build the synthetic intake. It is exposed by a tiny oracle-test facade and explicitly skips when those assets are absent. A public skip does not demonstrate this success path; local execution and the persisted receipt/checkpoint provide that evidence. The test is repeatable in temporary paths. The separately persisted run `PR408_SYNTHETIC_ALLSKY_TQ_20261011_01` uses the same helper with fresh output IDs and private canonical checkpoint, and is not repeated on its existing paths.

This calls the existing case capture adapter directly with inputs built by the driver. The top-level `run_case_analysis.execute()` fixture-copy/execution-asset/spawned-worker path is not invoked, and actual RTTOV worker execution remains outside this synthetic check.

## Results and interpretation

[Result](SYNTHETIC_CAPTURE_RESULT.json) and [capture receipt](runs/PR408_SYNTHETIC_ALLSKY_TQ_20261011_01/CAPTURE.json) report `RETURNED_DIAGNOSTIC_ONLY`, five logical synthetic-H callbacks and one final audit. L-BFGS step instrumentation records one step call, two iterations and three window evaluations. Nonzero state control produces Jb0.228225844439; fixed parameter prior is inactive. Initial Jtotal23.2603290391 becomes23.0297987783, with final Jo22.8015729339. The independent initial-objective recomputation isCROSSCHECKED, and all seven channels retain the frozen mask and synthetic quality0.

The private checkpoint contains all four initial/slot states, control/prior arrays, the complete optimizer gradient, BT/quality and coordinate provenance. Hash verification and permissions are0600 under0700. Reusing output paths is refused before analysis; hashes remain unchanged. The code snapshot remains unchanged. [Local validation](LOCAL_VALIDATION.json) also compares H/L-BFGS object identity after pytest teardown; the test does not separately assert pointer identity immediately inside capture's `finally` boundary.

Final gradient Linf1.5642977119201262e-7 exceeds the1e-10 threshold; L-BFGS termination attribution isUNKNOWN. Normal diagnostic return and saved accepted state therefore do not establish strict convergence. The temporary repeatable test, facade and persisted call share **one unique positive case**; neither callback count nor test repetition is an independent weather-case count.

The first post-capture summary serialization script omitted a Path import and raised NameError after successful receipt/checkpoint publication. Green reconstructed the report from those existing files. [Postprocessing note](POSTPROCESSING_NOTE.json) records the failure and no-rerun recovery; the serializer traceback was not independently replayed. Captured outputs are independently hash-verifiable.

## Boundaries and remaining dependency

No RTTOV executable, native WRF integration, new satellite acquisition or real July20/21 native analysis ran. H returns directly constructed synthetic BT/adjoints, so this does not test RTTOV execution, sensor calibration/SRF, or physical observation matchup. The native-style state and synthetic observation date labels are test data, not new-date weather evidence. Scratch inputs/reference-bearing NPZs stay private/ignored; original source-binding paths are retained locally and a restricted canonical preservation copy is kept.

Both actual July20/21 cases remainPENDING_NATIVE_INPUT. No new archive candidate was supplied and neither repeated directory search nor archive question was used to claim progress. Actual new-date M→RTTOV→minimization→final audit remains required when that native input arrives. Extra host diagnostics remain optional. Existing clock/mask/K-response/finite-step checks remain closed; there is no V5, new solver or new external-observation gate.

See [Green report](SYNTHETIC_CAPTURE_REPORT.md), [Red review](RED_SYNTHETIC_SUCCESS_REVIEW.md) and [checklist](../CHECKLIST_pr408_synthetic_capture_success_2026-10-11.md). User assessment **79/100** remains unchanged; this closes the synthetic success-wiring question without new-date science points. Remote CI is attributed separately to its PR head and skips are explicit.
