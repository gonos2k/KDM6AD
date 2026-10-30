# Direct-run source and observation contract

Each case used the same pilot-on checkpoint in its trace off/on host pair:
Control `8208ea632df784c6f9fc758fe3c24522539463ff2a968af8d469cb1c78eced6c`,
α=0.25 `829893a28166c251c3562d0166aa68bb666ed17b9a9b847ff3351d87ba144bfc`.
These are native 234×282×39 checkpoints at **2025-07-19 00:01:00**, timestep 3.
The fixed KO observation bundle has the nominal **00:00** slot; individual
pixel UTC remains unverified. No time interpolation or correction is applied.
The frozen original M0 is 53,906 profiles and 377,342 channel cells.

The native checkpoint reader preserves the 39 native levels and actual
center pressure fields. The existing profile builder derives interfaces
from saved pressure/geopotential inputs and FNM/FNP; its declared fixed clear
upper prefix and RTTOV background/model-top assumptions remain those of the
[original observation baseline](../native_full_physics_observation_2026-10-25/README.md).
This experiment does not remap to a fixture grid or claim a new independent
observation-time certification.

`data/chunk_artifacts.tar.gz` contains the exact two `binding.json` files,
two completed `summary.json` files, and each of the 258 `attempt.json`,
`result.json`, and `result.npz` files. The binding maps named local source
paths to SHA-256 and records the RTTOV executable, coefficient, template,
calibration and runtime asset hashes. The private direct runner rechecked
its 517-file operational Python source tree and RTTOV assets during execution.
The public replay verifies the binding and chunk records against the
hash-pinned archive, packed arrays and source snapshots. It **does not
reopen the private RTTOV executable, coefficients, full checkpoints, or raw
case directories**; their original bytes remain private. Local path strings
inside the saved JSON receipts are retained and disclosed in the README.

Exact snapshots of the private direct runner and offline packer/exporter are
under `executed_sources/`. Their SHA-256 values are checked against the
binding and producer receipt. The 517-file source-tree digest is a recorded
execution snapshot; the entire tree is not redistributed in this packet.
The host boundary pilot's build and moment-pair scope are documented in the
[parent packet](../native_qi_postmicro_boundary_2026-10-30/README.md).

The reported cost is a fixed-support direct observation diagnostic. It does
not establish physical QI/NI conservation, an AD derivative, analysis
acceptance, forecast skill, or a second assimilation.
