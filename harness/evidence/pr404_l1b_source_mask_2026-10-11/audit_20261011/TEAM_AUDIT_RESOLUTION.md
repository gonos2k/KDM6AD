# Independent team audit and resolution

Reviewed PR404 head `4b65577f7c2062ab99dffe50ced233a092457184`, with three independent agents covering raw/source-mask counterexamples, future writer integration, and evidence/coverage. This audit does not certify the whole KDM6AD codebase.

## Findings and disposition

| Finding | Scope / priority | Resolution and evidence |
|---|---|---|
| Decode did not require a successful download receipt or match progress records to planned/local objects | P2, unexecuted future observation writer | v3 requires success status, exact counts/bytes/key coverage/path/ETag and local SHA-256 before reader invocation. Failed status, incorrect counts, duplicate progress entries, swapped paths/ETag and hash mismatch are rejected in synthetic integration tests. The downloader writes its failures separately in `DOWNLOAD_FAILURE.json`; the audit injected a failed status into `DOWNLOAD_RECEIPT.json` to reproduce the consumer gate omission. |
| RESULT could claim completion before CSV publication failed | P2, future writer result reporting | v3 refuses conflicting output paths before source intake and publishes RESULT only after both CSV writes succeed. Injected CSV failure preserves partial artifacts without a success marker; no automatic retry or overwrite is introduced. |
| Empty CSVs lacked the normal schema; no-scene interpretation still claimed two scenes | P3, future missing-data reporting | Explicit point/patch field lists remain stable for empty outputs. No-scene status and decoded count/interpretation are explicit. Zero and nonempty synthetic cases verify the schema and interpretation. |
| External `--plan` failed late when converting its path to repository-relative form | P3, future CLI/I/O interface | v3 records an external resolved path and its hash; the successful synthetic case covers an external plan. |
| Sidecar did not explicitly store its channel axis or raster center | P3, artifact self-description | Additive `SIDECAR_AXIS_CONTRACT.json` binds the unchanged private NPZ hash, channels8–16 with DN widths, dates, raster rows318–322/columns46–50 and center320/48. Independent Red checked the source headers and byte-identical restricted private copy. |
| Prior25-test record lacked exact command/environment | Evidence-reporting omission | Additive `AUDIT_VALIDATION.json` records the prior command, current36-test command, interpreter/packages and thread settings. Old-head CI evidence is separated from current-head checks. |

The source-mask algorithm itself passed independent actual-netCDF counterexamples and actual18-slice checks. Current PR403 BT/DQF, the original source files and the PR404 additive mask payload were not found to be incorrect. The gaps concern future workflow gates and metadata, not production microphysics/AD.

## Preservation and executed scope

All10 entries in the original PR404 manifest and all21 entries in the PR403 manifest remain unchanged. Executed v2 and `repair_source_mask.py`, receipts and private NPZ are immutable. `heldout_l1b_v3.py` is a new future version requiring a new frozen plan; its raw/canvas function ASTs match v2 exactly. No existing capture was rerun or replaced.

The current local run passed36 cases:9 actual-NetCDF source-mask regressions,11 synthetic writer/publication/provenance tests, and16 unchanged production LA-reader tests. The nonempty writer test uses a clearly synthetic reader payload and temporary NetCDF inputs. It does not establish a real full-scene v3 decode, new satellite acquisition, native integration, RTTOV H/K, KDM M or optimization. Successful write-order checks are not a crash-durability guarantee.

Matching July20/21 native inputs and analyses remain pending in the bounded availability audit. No new archive request, external observation, L2 product or model/reanalysis substitute was introduced. User78/100 remains the recorded management baseline with no automatic point increase.
