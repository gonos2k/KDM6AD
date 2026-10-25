# Historical source inventory

The original `manifest.json` and all numeric products remain unchanged.
Its two C ABI files predate the opt-in native FP64 value entry. Its original
test source is also self-pinned by that historical inventory.

[historical_source_resolution.json](historical_source_resolution.json) maps
exactly those three paths to byte-identical source archives. Every archive
must match the original manifest SHA-256; all other source and artifact paths
still use the original direct checksum checks. The available Git revisions
identify matching source bytes, not a later execution of the old experiment.

Current validation code is free to evolve while retaining the exact historical
test/source record. This source resolution does not relax numerical, derivative,
or legacy bit-parity criteria, or claim a new native execution.
