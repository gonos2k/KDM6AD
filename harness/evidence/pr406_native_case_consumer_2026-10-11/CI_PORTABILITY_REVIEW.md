# Independent Red review: Oracle CI portability fix

## Disposition

The revised portable facade removes the local-only observation test that enters `load_case()` and extracts a native core using the private P8W/reference assets. It replaces that coverage with a source-only synthetic test of `_load_result_binding()` and prevents `_load_legacy()` from loading native readers. The targeted facade passes locally; this review does not claim that a remote Oracle CI rerun passed.

## What the facade now exercises

- The facade excludes the four tests requiring private native/reference input, plus `test_observation_source_binding_checks_metadata_payload_slot_and_seven_dqf`, which calls the full intake path and therefore depends on the private P8W reference source.
- Its new synthetic test builds temporary L1B result, payload, and decode-receipt files, binds their paths and SHA-256 values, verifies the exact scene date and nominal slot, validates GEOS reader metadata, and admits seven DQF0 channels. It then updates the bound result and metadata with an invalid `ir105` DQF and confirms rejection.
- The test replaces `_load_legacy()` with a failure sentinel. It calls only `validate_case()` and `_load_result_binding()`, so it does not open native forecast data or private reference assets. It also confirms the unused native-output directory remains absent.
- The existing wrong-fixture case remains portable: the driver refuses before intake loading or output-directory creation.

## Verification

I ran these independent local commands with `/opt/local/bin/python3` (Python 3.10.11):

```text
python3 -m pytest -q oracle/tests/test_native_case_consumer_contract.py
```

Result: **14 passed**.

```text
python3 -m pytest -q harness/evidence/pr406_native_case_consumer_2026-10-11/test_native_case_intake.py harness/evidence/pr406_native_case_consumer_2026-10-11/test_case_analysis_adapter.py
```

Result: **24 passed**. `git diff --check` also passed.

The new portable case is additive to the 24 focused evidence tests: **25 distinct focused cases** across those sources. Preserve the earlier 24-focused/14-facade report as first-commit history; the new v2 validation record should distinguish current counts from that historical snapshot. The portable facade itself still has 14 passing cases, including one new case and 13 existing cases.

## Limits

The synthetic binding test validates file identity and metadata gates without decoding or comparing actual L1B payload arrays; local focused tests retain the deeper payload-to-point comparison. The facade does not validate P8W, select native hyperslabs, produce a native NPZ, execute M/H/optimizer, or establish successful remote CI. V1/V2 intake source files and the archived v1 result/pending records remain unchanged by this review.
