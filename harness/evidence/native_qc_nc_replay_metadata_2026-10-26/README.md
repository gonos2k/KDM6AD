# Strict integer metadata in the saved QC/NC replay

Base: main `6787d3c926981e603de6585caae50407ac2c7fd0` / PR455. The replay now requires JSON integer types for native levels, dimensions, coordinates, timestep, selected levels, wrapper call count and asset byte count. `int()` previously accepted `levels=39.9` as 39. Boolean values, numeric strings and integral-looking JSON floats are also rejected. No model or RTTOV call is part of this change.

The original PR455 [inventory](../native_qc_nc_trace_2026-10-26/manifest.json) is preserved. Its two changed source entries resolve to byte-identical snapshots in [source_resolution.json](source_resolution.json); the other 50 entries still match the current tree. The revised replay returns output byte-identical to the original [analysis.json](../native_qc_nc_trace_2026-10-26/analysis.json). Twelve focused tests pass, including fractional examples at each consumer field; the historical source snapshot remains available for audit.

Run from the repository root:

```sh
python3 -m harness.evidence.native_qc_nc_trace_2026-10-26.replay
```
