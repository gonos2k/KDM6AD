# Superseded v2 flow findings

This file preserves the initial v2-only audit trail. It is superseded by the final v3 review in [`FLOW_RED_AUDIT.md`](FLOW_RED_AUDIT.md), which records the corrected severity, actual downloader failure-file name, v3 fixes, and final verification. Do not use the initial recommendations below as current v3 status.

Scope: read-only audit of `heldout_l1b_v2.py` at PR404 head `4b65577f7c2062ab99dffe50ced233a092457184`. The repository record says only the raw-word/source-mask helpers and repair script ran; this audit did not perform preflight against S3, download observations, decode any full scene, or call model, RTTOV, H/K/M, or optimizer code. Synthetic checks used temporary files and monkeypatched frozen-source verification.

## Findings

### P2 — RESULT.json could claim a completed decode when CSV publication failed in v2

`decode()` writes the private NPZ and receipt, then publishes `RESULT.json` before opening either CSV (`heldout_l1b_v2.py:615-660`). A pre-existing `POINT_SAMPLES.csv` or a later CSV write error raises after the result is already visible. The result has status `DECODED_GK2A_L1B_SCENES_ONLY` and names both CSVs, although one or both are absent or stale. Since all writes use exclusive creation, the next run also refuses to replace the already-published result, leaving the packet in a misleading partial state.

Reproduction: called `decode()` with a two-scene synthetic plan whose scenes were both missing, a matching temporary download receipt, and an existing `POINT_SAMPLES.csv`. `_verify_frozen_sources` was replaced with a no-op; no network or production reader ran. `decode()` raised `FileExistsError: refusing to overwrite .../POINT_SAMPLES.csv`, while `RESULT.json` remained with status `DECODED_GK2A_L1B_SCENES_ONLY`; `FIXED_PATCH_SAMPLES.csv` did not exist.

The impact is limited to an unexecuted future writer and its local evidence packet, so this is P2 rather than a system-wide P1. V3 closes the false-success condition by checking output conflicts before intake validation and publishing `RESULT.json` only after both CSV writes succeed. A CSV write error can still leave private outputs or an earlier CSV, but no success marker is published and the no-clobber policy blocks automatic rerun.

### P2 — Decode accepts a failure receipt as successful download provenance

`decode()` in v2 checked only that `DOWNLOAD_RECEIPT.json` existed and its `plan_sha256` matched (`heldout_l1b_v2.py:471-475`). It did not require `status == ALL_PLANNED_FILES_DOWNLOADED`, check `downloaded_files`/`downloaded_bytes`, or validate per-object `DOWNLOAD_PROGRESS.jsonl` records. The negative-status counterexample below is synthetic: the downloader writes failure details to `DOWNLOAD_FAILURE.json`, not to `DOWNLOAD_RECEIPT.json`; no real producer path creating a failure-status receipt was observed. Still, a receipt with a matching plan hash and failure status was consumed in v2. V3 now requires success status and exact planned totals, exact progress-key coverage, expected paths/sizes/ETags, and a matching local SHA-256 for each source file.

Reproduction: in a temporary directory, passed a plan with both scenes marked missing and a matching `DOWNLOAD_RECEIPT.json` containing `status=FAILED_NO_AUTOMATIC_RETRY`; with only `_verify_frozen_sources` stubbed, v2 returned `DECODED_GK2A_L1B_SCENES_ONLY`. No source file or network access was used. This tests the consumer gate against an injected receipt, not an actual downloader failure artifact.

V3's `validate_download_receipt()` applies the suggested fail-closed gate before calling the production reader.

### P3 — Empty CSVs in v2 did not have the normal schema

CSV headers are inferred from the first emitted row; when a row collection is empty, both files fall back to `date,status` (`heldout_l1b_v2.py:651-659`). A valid preflight with no selected scenes can therefore publish empty CSVs whose columns do not match the point/patch schemas emitted when rows exist. The corresponding per-scene missing status is in `RESULT.json`, not in either CSV. This makes downstream CSV consumers branch on whether observations happened to be available, and `status` has no row value in the empty file.

The synthetic missing-scenes path reached this branch with temporary outputs; the P1 conflict run stopped before CSV publication. Static path inspection confirms the v2 empty case used the two-column fallback. This is a low-impact machine-readability issue in an unexecuted local writer, so P3. V3 uses explicit field lists for both CSVs and returns `NO_SCENES_AVAILABLE` with count zero when no planned scenes can be decoded.

The v3 integration suite checks stable empty CSV headers, `NO_SCENES_AVAILABLE`, zero decoded scenes, and an interpretation string based on the actual decoded/planned counts.

## Contract checks

- The normal patch-row writer carries `raw_word_uint16`, `dn`, `embedded_dqf`, `source_missing`, and `padding`; these values are joined to BT and reader DQF by date, row, column, and channel (`heldout_l1b_v2.py:548-583`). Point rows carry date, row, column, channel, BT, and reader DQF, but not packed-word or mask fields. They can be joined to patch rows only when a within-radius patch is emitted.
- The patch and point row dictionaries are internally consistent for nonempty outputs. `DictWriter` receives keys from the first row and the subsequent generated rows use the same shape; this audit found no extra-key failure in those paths.
- Plan/source binding pins the helper, calibration, production-reader files, and saved listing hashes. V3 also verifies the successful download receipt and progress records against each local source file before decode.
- `--plan` is exposed by the CLI. V2's `plan_path.relative_to(ROOT)` failed late on external plan paths; v3 serializes a root-relative path when possible and otherwise records the resolved absolute path. Its synthetic integration case covers an external plan path.
- The plan schema and generated `plan_id` retain the `pr403` prefix despite being PR404 v2. This is confusing provenance text, but not by itself a demonstrated data-path failure.

## Evidence limits

No real preflight, S3 listing/download, or `read_la_slot` full-scene decode was executed. The repository's PR404 validation remains accurately described as helper/repair coverage only. Findings above concern source-level flow and the two isolated synthetic integration counterexamples; they do not imply a defect in the already executed PR403 artifacts or the PR404 source-mask helper tests.
