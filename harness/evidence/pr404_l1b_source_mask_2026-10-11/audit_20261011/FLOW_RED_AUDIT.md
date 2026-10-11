# PR404 future-writer flow audit — final disposition

## Scope and execution boundary

Reviewed additive `heldout_l1b_v3.py` and `test_decode_publication.py` against the previous v2 flow findings. The frozen `heldout_l1b_v2.py`, repair helper, PR403 files, raw capture, original payload/result, and packet manifest were not edited. No S3 preflight/listing/download, real observation scene decode, native model, RTTOV, H/K/M, or optimizer ran. Integration evidence below uses temporary files, synthetic NetCDF inputs, and a synthetic LA-reader payload.

## Disposition

The two P2 flow findings from the v2 audit are closed in v3:

- **P2 — publication ordering.** V3 checks all five destination paths before source-receipt/progress validation and before image-byte hashing. It serializes the public JSON in memory, writes both CSVs with fixed field lists, and writes `RESULT.json` last. A synthetic injected CSV writer error leaves no `RESULT.json`. A pre-existing CSV triggers before `validate_download_receipt()` and preserves the existing file. A failed write can leave private artifacts or an earlier CSV; preserve those partial artifacts, and use fresh, separately identified output paths for any later attempt. There is no automatic retry. Consumers must treat `RESULT.json` as the completion marker.
- **P2 — download provenance gate.** V3 requires `ALL_PLANNED_FILES_DOWNLOADED`, exact planned file/byte totals, unique planned keys, exact progress key coverage, expected progress path and source paths, matching sizes and ETags, and current file SHA-256 values matching progress. Tests reject negative status, wrong counts/bytes, hash mismatch, duplicate-key coverage, swapped paths, and wrong ETag before the LA reader runs.

The old failed-status reproduction injected `FAILED_NO_AUTOMATIC_RETRY` into `DOWNLOAD_RECEIPT.json`. The actual downloader writes failures to `DOWNLOAD_FAILURE.json` and does not create `DOWNLOAD_RECEIPT.json` on failure, so the injected object was a consumer-gate counterexample, not an observed producer artifact. V3 still correctly refuses that status if it appears at the receipt path.

The P3 empty-CSV schema issue is closed: `POINT_FIELDS` and `PATCH_FIELDS` define stable headers even with zero rows. An all-missing-scene plan returns `NO_SCENES_AVAILABLE`, `decoded_scene_count: 0`, and an interpretation string using actual decoded and planned counts. Tests cover those values. For a nonempty synthetic case, fixed-patch CSV rows carry packed word, DN, embedded DQF, `source_missing`, and `padding`; existing point/patch row keys remain joinable by date, row, column, and channel when a patch is emitted.

V3 handles an external `--plan` path by recording its resolved absolute path; the temporary integration case covers this path. The immutable v2 helper functions `read_packed_source_patch()` and `source_patch_canvas()` are AST-identical to v3. The additive `SIDECAR_AXIS_CONTRACT.json` parses and declares nine ordered channels, 5×5 patch rows/columns, and center/canvas coordinates; its claims remain bound to the recorded payload hashes and do not imply a new observation or model run.

## Remaining evidence boundary

No actionable P1/P2 flow issue remains in the reviewed v3 paths. V3 is a future writer and its integration evidence does not establish successful live S3 I/O or full-scene `read_la_slot()` decoding. [`V2_FINDINGS_SUPERSEDED.md`](V2_FINDINGS_SUPERSEDED.md) preserves the historical findings with corrected severities, the distinct `DOWNLOAD_FAILURE.json` path, and the exact injected-receipt reproduction.

## Verification

The exact focused local command run for this review was:

```text
python3 -m pytest -q harness/evidence/pr404_l1b_source_mask_2026-10-11/test_source_mask.py harness/evidence/pr404_l1b_source_mask_2026-10-11/test_decode_publication.py oracle/tests/test_gk2a_l1b_la.py
```

Result: **36 passed** (9 source-mask regressions, 11 v3 publication/provenance integration cases, and 16 existing LA-reader tests). I separately confirmed AST identity for the two frozen mask/canvas helpers, parsed and checked the axis-contract JSON, and ran `git diff --check` successfully.

The independent invocation used `/opt/local/bin/python3` (Python 3.10.11). The repository's root audit records its own exact command and environment in `AUDIT_VALIDATION.json`; this report does not conflate the two interpreter environments.
