# AMI integration team audit — 2026-10-04

Baseline: PR #367, `0b6852a943224c16b5e1c41eadb41907566880ed`.
Green reviewed calibration/reader consistency, Red reproduced counterexamples,
and a separate source audit checked evidence provenance. This is a bounded audit
of the recent AMI decoding, coordinate replay and metadata tools; it is not a
whole-project certification. No new production KDM/RTTOV physics defect was found
in these reviewed paths. Four verification/evidence issues were resolved.

## Checklist and counterexamples

| Status | Issue | Trigger and resolution |
| --- | --- | --- |
| CLOSED | P2: FD measurement used the external calibration as its expectation and omitted the effective BT center from its match claim | A synthetic IR105 file with its own 1000 cm⁻¹ center gave about 290.064426 K; the verifier expected 286.160921 K and called the calibration matched. The independent verifier now reads file coefficients, uses its explicit center or an exact audited package-tuple fallback, and compares the effective center too. |
| CLOSED | P2: coordinate replay trusted reported support counts without validating raw radiances | A negative window radiance with a matching clipped legacy BT could reach a COMPLETE result containing NaN. The replay now requires finite positive raw window/model radiances and saved BTs, and forbids NaN JSON output. |
| CLOSED | P2: epoch receipt did not enforce FD object/channel identity | A wrong manifest key or an IR112 variable label inside an IR105 filename still completed. The generator now checks the exact expected object key, filename, channel label and duplicate manifest filenames. |
| CLOSED | P2: reader-boundary evidence lacked a saved generator and complete replay command | A small frozen replay now pins the immutable original record, reader/calibration sources and input bytes; verifies the whole KO QC array and original reported values; and records its own source hash and argv. The separate 2023 FD sample is explicitly not 2025 KO lineage. |

The archived inputs themselves satisfy the new checks. These counterexamples
do not establish corruption of the existing records. Original result JSON files
remain unchanged; corrected generators write new audit-rerun records.

## Validation

The following focused public tests passed: **100 passed**. They include existing
AMI word/QC tests and regressions for the reproduced verifier/domain/identity
issues. Synthetic FD tests exercise explicit and fallback centers, changed file
coefficients, unknown-tuple rejection, QC and nonmutation of the reference table.

```sh
python3 -m pytest oracle/tests/test_measure_ami_bits.py \
  oracle/tests/test_ami_word_contract.py \
  oracle/tests/test_ami_bt_coordinate_domain.py \
  oracle/tests/test_ami_epoch_identity.py -q
```

Three local replays used retained observations or saved radiation outputs:

| Replay | Result |
| --- | --- |
| [BT coordinate](AMI_bt_coordinate_audit_rerun_2026-10-04.json) | All values, derivative transforms and diagnostics equal the original result after excluding updated provenance. |
| [Epoch metadata](AMI_epoch_metadata_audit_rerun_2026-10-04.json) | All metadata and input-hash fields equal the original receipt after excluding updated provenance. |
| [Reader boundary](AMI_reader_boundary_audit_rerun_2026-10-04.json) | Exact original center BTs, identical 900×900 KO QC arrays, and the separate FD stamp/stride/usable count; pinned sources and object hashes match. |

These are reader, header and saved-output replays. No new KDM integration,
RTTOV/C-DISORT engine run, native build or MPI experiment was performed for this
audit. Engine evidence retains its original source/build/input attribution.

## Replay instructions

Each new JSON records its exact `provenance.cli_argv`, source hash and inputs.
Run from the repository root with the recorded private files available. For the
reader boundary:

```sh
python3 harness/evidence/AMI_reader_boundary_source_2026-10-04.py \
  --record harness/evidence/AMI_reader_boundary_result_2026-10-04.json \
  --output /tmp/ami-reader-boundary-replay.json
```

The historical local-support record used the old nominal calibration at a path
now occupied by the paired table. Its byte-identical archive is
`AMI_legacy_nominal_calibration_202507190000.json`, SHA-256
`f519149e3ea3538866bad9f3e28cc0ddef741b6b4cdbf8febb7988aff6c08d40`.
To reproduce its declared historical BT coordinate rather than silently using
the current table:

```sh
python3 harness/evidence/AMI_local_support_source_2026-10-04.py \
  --input-root /Users/yhlee/KDM6AD-k/GK2A/00 \
  --calibration harness/evidence/AMI_legacy_nominal_calibration_202507190000.json \
  --diagnostic harness/evidence/C5_matched_observation_diagnostic_2026-10-03.json \
  --output /tmp/ami-local-support-historical-replay.json
```

Private data availability and recorded source versions are requirements, not
portable public-clone guarantees. The original calibration-pairing receipt's
unavailable-2025-header statement describes that earlier workspace; the recovered
epoch receipt supersedes it without rewriting the historical record.

## Remaining limitations

The live `RttovObsOp` forward/K path still uses native RTTOV BT. Offline common-KMA
coordinate JVP replay does not establish common-coordinate live DA loss/VJP or
`DAWindow` integration. Such adoption must transform values, Jacobians, bias and
the supported error model together. This is an existing unapproved path, not a
new claim that the offline diagnostics were wrong.

S2's historical 100/10 calibration basis, selected KO source/SRF compatibility,
S11 physical optics/observation errors and scientific cost approval remain OPEN.
No thresholds, QC, observation weights, operational defaults or release policy
were changed to close these items. Closed NCCN arithmetic, density AD checks,
17-digit output and bounded independent IR105 transport results stay closed.

Graph queries and source inspection were both used. Structural and bounded
semantic graph updates cover this audit; private-host and whole-project semantic
coverage remains partial. Large-graph HTML visualization is omitted by the
existing node limit. Source and executed evidence remain authoritative.
