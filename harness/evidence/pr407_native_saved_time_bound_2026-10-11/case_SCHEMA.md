# Current native case consumer: V4

The case JSON contract is the [PR406 case schema](../pr406_native_case_consumer_2026-10-11/case_SCHEMA.md), with schema name `kdm6ad_native_case_v4`. The current manifest schema is `kdm6ad_native_case_intake_v4`. Completion receipt, original decoded L1B bindings, fixed single-column configuration and no-overwrite rules remain required. Do not edit the preserved pending or executed case files: create a fresh case ID/output directory when a real archive becomes available.

Producer clocks are derived from actual one-domain numeric `start_*` and `end_*` namelist fields; minute/second omitted defaults are0. Nonnegative integer run_days/hours/minutes/seconds combine, and positive duration takes precedence over the end tuple. String start_date/end_date may only agree with numeric components; they cannot replace them. The parser is limited to unambiguous separate assignments, not arbitrary WRF namelist formats or multi-domain clocks.

Every actual saved host Times must lie in the inclusive producer range. The manifest records effective start/stop/basis/duration and ordered Times count/first/last/SHA. Bound reload rechecks these against the current hashed producer configuration and actual Times. Requested but absent optional diagnostic frames remain omitted. The local20s observation slot is calculated and may lie after a valid terminal saved background; it does not claim a saved host state or full-host boundary support there.

From the repository root:

```sh
PYTHONPATH=oracle python harness/evidence/pr407_native_saved_time_bound_2026-10-11/intake_native_case_v4.py /path/to/fresh_CASE.json
PYTHONPATH=oracle python harness/evidence/pr407_native_saved_time_bound_2026-10-11/run_case_analysis.py \
  --intake-manifest /path/to/fresh_INTAKE.json --intake-npz /path/to/private/core.npz \
  --output-root /path/to/fresh_analysis_output \
  --template-fixture /private/tmp/KDM6AD-viirs-native-run-20261007/comparison/results_failed_native_artifact_diag_055540_055800_retry2/case_00
```

The historical fixture directory name is not another satellite input: the established template is GK2A AMI, and different templates are refused. Pending or observation-less readiness cannot authorize analysis. This packet provides no native launcher, new data source, retry or overwrite fallback. V3 here is frozen superseded evidence; V4 is the only current consumer selected by the adapter/driver.
