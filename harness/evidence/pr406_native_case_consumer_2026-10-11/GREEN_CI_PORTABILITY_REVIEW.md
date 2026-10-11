# Green review: portable Oracle CI facade

## Disposition

The corrected facade is consistent with its public-CI scope. The earlier
failure was caused by one local-only observation-to-native intake test being
collected as a portable test. The fix changes only the facade/test boundary:
it excludes five native/reference-dependent cases, adds a direct synthetic
receipt-admission case, and installs a guard that rejects `_load_legacy()` or
`netCDF4.Dataset` access in every facade test. No intake consumer, capture
adapter, analysis driver, native replay, or historical record changed for this
portability correction.

## Demonstrated coverage and counts

The corrected combined local command completed **38 passed**:

```sh
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_THREAD_LIMIT=1 VECLIB_MAXIMUM_THREADS=1 \
  PYTHONPATH=oracle \
  /private/tmp/KDM6AD-research-rc-20261007/env/bin/python -m pytest -q \
  harness/evidence/pr406_native_case_consumer_2026-10-11/test_native_case_intake.py \
  harness/evidence/pr406_native_case_consumer_2026-10-11/test_case_analysis_adapter.py \
  oracle/tests/test_native_case_consumer_contract.py
```

The 24 focused local tests and 14 portable facade tests share 13 test IDs; the
new direct L1B receipt test is the only portable-only ID. Thus the combined
run exercised 38 test instances across **25 unique cases**, not 38 distinct
cases. The standalone portable facade also passed 14/14. The five excluded
tests cover NetCDF hyperslabs, selected-frame reading, core intake, optional
diagnostics, and observation binding through the full native intake path. The
deeper local observation test remains in the 24-test focused suite.

The new facade test exercises `_load_result_binding()` using temporary
hash-bound result, metadata, and synthetic payload files, admits seven DQF0
analysis channels, then changes IR105 DQF and confirms rejection. The payload
is provenance-only test data; it is not decoded or represented as a real
observation. The test creates no intake NPZ. The autouse guard provides a
regression check that this facade cannot silently reach the private P8W/native
reader or instantiate NetCDF datasets, even where those assets happen to exist
locally.

## Historical CI and limits

At first head `7824d28ca55aa0a7727daabb5079b59b364de8d7`, Oracle CI run
`38114357249` reported 1 failed, 1748 passed, 95 skipped, and 33 warnings. The
failure was the portable facade invoking the private-input full intake path;
it did not identify a production physics failure. The corrected facade passes
locally. This review does not claim a remote Oracle CI rerun passed; final
remote CI must be attributed to its actual PR head separately.

`CI_FIX_VALIDATION.json` records corrected local counts, first-failure context,
and source hashes. `VALIDATION.json`, the initial Green/Red reports,
`COORDINATOR_REPORT.md`, and `ARTIFACT_MANIFEST.json` remain historical
first-head evidence where their recorded counts predate the added facade test.
At that head the portable cases were a subset; for the corrected facade the
portable-only test raises the combined unique count from 24 to 25. The
additive portability report and validation record control current facade
claims without rewriting historical artifacts.

No model data, private forecast, P8W asset, RTTOV asset, or large array was
read or rewritten for this review. No native/model run, M/H, or optimizer was
executed. User assessment 79/100, July20/21 pending status, and native replay
records remain unchanged.
