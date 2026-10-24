# Readable repeatable controller and named global count

The original #443 `execution_sources/*.txt`, prepared/result JSON and their
hashes are immutable historical evidence. Their feasibility-era top-level scope
strings were not rewritten or silently reclassified.

`harness/run_native_candidate_observation.py` is the repeatable source. Paths
are gathered in `PATHS`, and `EXPERIMENT` defines the actual one native target,
three directions, epsilons, scope and eligibility scope. Preparation and result
records copy that same definition. Plain `prepare_inputs`, `verify_case` and
`save_result` steps reuse the established numerical operators; no framework,
configuration class or state-management subsystem was introduced. The archive
is not represented as the new source's execution record.

The runner writes prepared source/input identity before any model call, rejects
input/output overlap, pins the candidate library/build/overlay, preserves failed
FD results before nonzero exit, and saves quality, mask, cloud fraction and
finish/cleanup signature arrays at every endpoint. Actual QR cap masks and KDM
integer schedules are **not** endpoint eligibility diagnostics; this limitation
is explicit in `EXPERIMENT`. Ambient trace paths are cleared/restored. Existing
number-receipt field names and exact packet/checkpoint QV equality are checked
before evaluating KDM.

`GLOBAL_SUBSTEPS=5` replaces repeated fixed global counts in the existing QR
reader's production defaults/loops/metadata. Local column counts4/1 retain
their different meaning. Existing helper `steps` arguments and small tests are
preserved. The pre-edit analyzer and its old hash-pinned evidence-test source
are archived under `executed_sources`; the historical #442 manifest is not
modified. Its source audit resolves those two immutable executed snapshots;
other old source/artifact pins are checked as before.

All four original QR archives were replayed from the already captured raw
traces with the new constant-based analyzer. The complete summary JSON and all
NPZ fields match the previous evidence exactly. See `constant_replay.json`.
This arithmetic replay added **zero KDM/RTTOV calls**. The separate actual-QR
candidate campaign uses the new runner and is attributed in its own evidence.

An initial runner preparation attempt rejected incorrectly renamed number
receipt keys before KDM/RTTOV. That source/log is preserved with the candidate
execution history. The required existing keys were restored and actual-data
prepare-only validation passed with zero forwards. Original source data and
fixed historical evidence were not changed.
