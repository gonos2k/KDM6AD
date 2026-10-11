# PR406 native case intake schema

This describes the explicit input consumed by `intake_native_case_v2.py`. The
consumer extracts one native background state for a declared 20-second
analysis step. It is a reader and
provenance gate, not a model launcher, KDM6/RTTOV executor, retry mechanism, or
archive inventory tool.

## Case JSON

Required top-level fields:

```json
{
  "schema": "kdm6ad_native_case_v2",
  "case_id": "ami_20250720_0556_native_column",
  "observation": {
    "source_result_path": "harness/evidence/pr403_l1b_heldout_2026-10-11/RESULT.json",
    "source_result_sha256": "<sha256 of exact RESULT.json bytes>",
    "source_payload_path": "<the bound private PR403 payload path>",
    "source_payload_sha256": "<the exact private PR403 payload SHA-256>",
    "source_metadata_path": "<the original canonical PR403 DECODE_RECEIPT.json>",
    "source_metadata_sha256": "<sha256 of exact DECODE_RECEIPT.json bytes>",
    "scene_date": "20250720",
    "nominal_slot_obt": "202507200556",
    "nominal_obs_model_time": "2025-07-20_05:56:00",
    "time_assumption": "NOMINAL_FILENAME_TIME_AS_MODEL_UTC_RESEARCH_MODE",
    "observed_pixel_utc": null,
    "nearest_pixel": {
      "row": 320,
      "column": 48,
      "latitude_deg": 35.41925069326254,
      "longitude_deg": 122.13724164654832
    }
  },
  "native": {
    "run_id": "<the exact run archive ID or null while pending>",
    "run_dir": "<the exact run archive directory or null while pending>",
    "initial_time": "<the archived initialization time, or null while pending>",
    "completion_receipt_path": "<hash-bound run completion receipt or null while pending>",
    "completion_receipt_sha256": "<receipt SHA-256 or null while pending>",
    "background_valid_time": "2025-07-20_05:55:40",
    "column": {
      "j": 86,
      "i": 48,
      "expected_latitude_deg": 35.4156608581543,
      "expected_longitude_deg": 122.143310546875,
      "coordinate_tolerance_deg": 0.00005
    },
    "diagnostic_times": []
  },
  "analysis": {
    "dt_s": 20,
    "obs_time": 1,
    "nominal_obs_model_time": "2025-07-20_05:56:00",
    "all_sky": true,
    "channel_ids_1based": [10, 11, 12, 13, 14, 15, 16],
    "require_source_dqf_zero": true,
    "control_fields": ["th", "qv"],
    "ncmin_land": 10.0,
    "ncmin_sea": 10.0,
    "use_adaptive_time_step": false,
    "step_to_output_time": false
  },
  "output": {
    "manifest_path": "harness/evidence/pr406_native_case_consumer_2026-10-11/cases/ami_20250720_0556_native_column.json",
    "private_npz_path": "graphify-out/pr406-native-case-consumer/private/ami_20250720_0556_native_column.npz"
  }
}
```

The example coordinates and dates illustrate field shape only; the L1B nearest
pixel and selected native column are separate positions and both must be
recorded. `run_id` and `run_dir` may both be `null` while a case is pending;
`initial_time`, `completion_receipt_path`, and its SHA may also be `null` then.
That path returns `PENDING_NATIVE_INPUT` from case metadata alone and does not
inspect a run path or create an NPZ. For a ready case, these fields and the
completion receipt are required. Supplying only one of `run_id` and `run_dir`
is invalid.

Every ready case must explicitly bind a completion receipt by path and SHA-256.
The receipt's `run_id` and `run_dir` must match the case, and its identity and
valid-receipt hashes must match the archived files. If `run_identity.json`
declares a `run_id`/`archive_run_id`, it must also match. The original PR397
schema omits IDs from both `run_identity.json` and `experiment_valid.json`, so
the matching ID comes from the explicit, hash-bound completion receipt; it is
not inferred or added to the archived files. Missing or stale completion
binding is rejected.

The result/payload/metadata bundle is optional for a native-core readiness
intake, such as a same-date PR395 adapter fixture. If any field from that bundle
is supplied, result and private payload path/hash must all be supplied. The
original `DECODE_RECEIPT.json` path/hash is optional at intake, but analysis
loading with `load_bound_intake(..., require_observation=True)` requires all
three artifact bindings and the seven analysis-channel DQF0 check. A
native-only case is a consumer-readiness artifact, not an observation matchup
or analysis authorization.

The nominal observation time is an explicit research assumption. It must match
the scene's nominal slot, be exactly 20 seconds after `background_valid_time`,
and must not populate `observed_pixel_utc`. `initial_time` must be no later than
the background time and must match archived initialization metadata. The first
saved forecast frame may be later than initialization; archived `Times` must
not precede the verified initial time, and the required background must appear
exactly. The
observation slot is the 20-second model/analysis target; the consumer does not
require a native forecast frame at that slot. The core reads one background
state and constructs its one-forcing 20-second input from that background.
`diagnostic_times` are optional requests separate from the required background;
unavailable diagnostic frames are reported as omitted and do not block a valid
core intake. No fixed number of saved frames is required.

`analysis` freezes the existing one-step, seven-channel, all-sky, T/Q-only
contract. Case-specific run label, run duration, and history cadence are read
from the archived identity and effective namelist and cross-checked against
each other; they are recorded as case details, not universal expected values.
The loader still enforces scheme/`mp_physics=337`, one rank / `1x1` actual
processor grid, 20-second model time step, `ncmin_land=ncmin_sea=10`, and both
adaptive/output-time-step flags false.

## Intake output and API

- `validate_case(case_dict)` checks and normalizes the case contract without
  opening native files.
- `load_case(case_path)` reads the case file, binds its byte hash, and returns
  `{"manifest": manifest, "arrays": arrays}`. A pending case returns
  `arrays: null`; it never opens a forecast or emits an NPZ.
- `load_bound_intake(manifest_path, npz_path, require_observation=True)` accepts
  only `READY_CORE_NATIVE_INTAKE`, verifies manifest and NPZ bindings, and
  returns `(manifest, arrays)`. The default `True` requires the full held-out
  L1B source/metadata/payload contract; only explicitly labeled native intake
  verification may pass `False`.

The private NPZ keeps PR395-compatible core aliases for the background state
and initial forcing. Its dynamic selected-time arrays have leading dimension
`Nselected`, containing the required background plus successfully read optional
diagnostics (`Nselected=1` when none are requested). The observation slot is not
represented as a native frame unless separately requested as a diagnostic and
present exactly in the forecast. Core selected times are not replaced by fake
or interpolated frames. The NPZ includes native State/Forcing fields, float32 host
dry layer mass `[Nselected,39]`, selected surface data, raw `PH`/`PHB`, native
center/interface pressure `[39]`/`[40]`, and the same pinned upper reference
profiles. Extended RTTOV arrays keep 27 upper reference layers plus the 39
native layers (`p_lay` length 66) and 27+40 interfaces (`p_half` length 67);
their native bottom-up suffixes must match the selected column exactly.

The manifest records the case JSON hash, observation-result identity, exact
run ID and archive paths, runner/identity/namelist hashes and controls,
forecast size/mtime, selected WRF times, reader and P8W source hashes,
reference-asset hashes, selected-column identities, optional diagnostic
omissions, and every NPZ array's shape/dtype/hash. `PENDING_NATIVE_INPUT` and
`READY_CORE_NATIVE_INTAKE` are distinct outcomes.

## Running a prepared case

Use a fresh case ID and fresh output paths; the archived v1/v2 cases and their
receipts in this packet are immutable execution evidence.

```sh
PYTHONPATH=oracle python harness/evidence/pr406_native_case_consumer_2026-10-11/intake_native_case_v2.py /path/to/new_CASE.json
PYTHONPATH=oracle python harness/evidence/pr406_native_case_consumer_2026-10-11/run_case_analysis.py \
  --intake-manifest /path/to/new_INTAKE.json \
  --intake-npz /path/to/private/new_core.npz \
  --output-root /path/to/fresh_analysis_output \
  --template-fixture /private/tmp/KDM6AD-viirs-native-run-20261007/comparison/results_failed_native_artifact_diag_055540_055800_retry2/case_00
```

Run these commands from the repository root.
The fixture path is the established **GK2A AMI** template; its historical
directory name does not authorize another satellite input. The analysis driver
rejects any different template. A pending intake or native-only readiness
artifact cannot be passed to analysis. The driver has no native launcher or
data-acquisition fallback and does not retry or overwrite existing outputs.
