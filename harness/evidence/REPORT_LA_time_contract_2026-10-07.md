# LA time contract: source behavior and remaining uncertainty

This audit pins Satpy v0.57.0 (`pytroll/satpy`, peeled commit
`70e3d3b728ed630c2d7e0df5512ee5d243c48581`) and executes only its
`AMIL1bNetCDF.start_time` and `end_time` property definitions against the
retained LA IR105 header. The runner is
[LA_time_candidates_source_2026-10-07.py](LA_time_candidates_source_2026-10-07.py);
the complete machine-readable receipt is
[LA_time_contract_result_2026-10-07.json](LA_time_contract_result_2026-10-07.json).
The source properties add numeric observation seconds to a naive
`2000-01-01 12:00:00` datetime. The pinned unit test also expects naive
`datetime` objects. The inspected properties do not consume the scene-time,
mission-reference, or synchronization attributes and do not attach a timezone.
This reproduces Satpy's source behavior; it does not certify the epoch or clock
interpretation for this file. The audited reader and test are pinned by commit and
SHA-256 in the [machine-readable receipt](LA_time_contract_result_2026-10-07.json);
the corresponding [reader source](https://github.com/pytroll/satpy/blob/70e3d3b728ed630c2d7e0df5512ee5d243c48581/satpy/readers/ami_l1b.py) and [test](https://github.com/pytroll/satpy/blob/70e3d3b728ed630c2d7e0df5512ee5d243c48581/satpy/tests/reader_tests/test_ami_l1b.py) are source references. The [NMSC metadata guide](https://datasvc.nmsc.kma.go.kr/resources/common/pdf/%EC%B2%9C%EB%A6%AC%EC%95%88%EC%9C%84%EC%84%B1%202A%ED%98%B8%20%20%EC%9E%90%EB%A3%8C%ED%99%9C%EC%9A%A9%20QA.pdf) labels scene acquisition time as OBT and mission reference time as planned UTC.

| Header field | Retained value | Supported interpretation |
| --- | --- | --- |
| Filename slot | `202507190534` | Filename-derived OBT slot label |
| `scene_acquisition_time` | `20250719_053442` | OBT according to the NMSC metadata guide |
| `mission_reference_time` | `20250719_053000` | Planned UTC according to the NMSC metadata guide; not actual scan time |
| `observation_start_time`, `observation_end_time` | `806175282.4338461`, `806175343.6724635` | Numeric seconds; this header has no unit/epoch attributes |
| `time_synchro_utc`, `time_synchro_obt` | `806175282.4398186`, `806175282.4338461` | Raw synchronization pair; difference is about 0.0059725 s, without an established conversion rule |

Applying Satpy's hard-coded epoch conditionally yields naive calendar values
`2025-07-19T05:34:42.433846` through `2025-07-19T05:35:43.672464`, a 61.23861742-second interval. These strings intentionally have no `Z` or UTC label. Applying the synchronization difference to the start would require additional assumptions about common epoch, units, clock rate, and whether synchronization is already applied; the receipt records that as a conditional calculation only.

| Readiness item | Evidence | What remains unresolved |
| --- | --- | --- |
| LA reader | Current `oracle/kdm6/obs/gk2a_l1b_la.py` SHA-256 `67c4d2abd1c16f55d6909edeef1549b0ce2e8e449b9b3f64e7185b4d34b083db`; raw times remain in the sidecar | `payload.valid_time_utc` remains `None`; pixel UTC is unverified |
| Time consumer | Ingestion passes `valid_time_utc` through. Full-domain analysis requires caller-supplied `obs_offset_s` if times are missing | No automatic inference from OBT or planned UTC |
| Existing native model | IC/BC are dated July 19 and boundary records span 00–09 UTC; existing pinned C5 output has only 00:00, 00:00:20, 00:00:40 | No saved state at the conditional LA interval; no pixel/footprint correspondence |
| Independent cloud data | MODIS metadata candidate exists for 00:45–00:50 UTC; anonymous data access was denied (403/redirect/401 evidence) and no data were read. EarthCARE remains catalogue metadata only | Credentials/access, actual science product, QA, phase, footprint and time correspondence remain open |

The current LA reader source hash is recorded in the result JSON; its payload keeps `valid_time_utc` unset. The LA header inventory, sanitized access/readiness receipts and native-domain envelope are summarized there as well. No MODIS or EarthCARE science file was acquired, no cloud phase was
classified, and no model or RTTOV run was performed. The time and matching
substeps remain open; this source-level result is not a collocated
observation/model case.

[Property execution](LA_time_property_execution_2026-10-07.json),
[native input/output readiness](NATIVE_model_readiness_2026-10-07.json), and
[sanitized CLI access readiness](MODIS_auth_availability_2026-10-07.json) are
separate receipts. [Reproducibility packet](LA_time_contract_receipts_2026-10-07.zip)
contains the producer and these records; external Satpy sources are identified
by immutable URL/SHA rather than redistributed. This is an extracted-property
execution, not a full Satpy reader/package or new model run.

No noninteractive Earthdata credentials were detected; browser/keychain access
was not inspected, so account existence is not inferred. The selected MODIS
candidate at 00:45–00:50 is not demonstrated concurrent with the LA label near
05:34. Once access is available it can establish a separate case, or another
granule must be selected for the LA interval after its clock is validated.

Public readiness/source-cache paths are logical root aliases. The original
absolute input/executable paths remain in the local read-only audit receipt;
byte sizes, saved Times, source identifiers and hashes are not changed by this
path sanitization. Boundary-window inclusion is conditional on establishing
the candidate clock as UTC, not an already-verified time match.
