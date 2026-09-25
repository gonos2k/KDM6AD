# S12: retained 5 km input inventory and second-initialization blocker

## Result

The surveyed canonical private host exposes one eligible real-data 5 km
initialization for the current KDM6AD validation: the 2025-07-19 00 UTC LC05
SS case. Its `host/lc05_da_run/` inputs are symlinks to the established SS
dataset. This is the input already used by the G4 and S4 native campaigns, not
a newly selected meteorological case. No second coherent 5 km initialization
was found **within the canonical host tree**. S12 remains **OPEN**.

This is a read-only inventory. It adds no model run, native build, RTTOV call,
meteorological representativeness claim or approval of MPI/restart behavior.

## Directly inspected files

The canonical run links, file hashes and NetCDF header were checked directly:

| Role | Header / identity | SHA-256 |
| --- | --- | --- |
| LC05 SS `wrfinput_d01` | real data, 2025-07-19 00 UTC, `DX=DY=5000 m`, 234×282×39 mass grid | `5a9ae8da992028dbf3a2a7652eb61532c1efab2acea7ea0e393e4cac8fd4c970` |
| Paired `wrfbdy_d01` | same 2025-07-19 start/grid; four boundary times at 00/03/06/09 UTC | `d46e5d7117c076956d130b4ff905fc34a5d53dbd5a0d9571311582b0a60c5e6c` |
| Paired `wrfchainp_d01` | 13 Times at 00–12 UTC; its global `START_DATE=2024-07-23_06:00:00` is stale, so use the time records and hash | `c8e300d2aa52f98c9060803438ab6f796bddd1e1cdd6b75a14e39a398cb0c4e3` |

`docs/HOST_RUN_LAYOUT.md` and the retained native manifest identify these
same link targets and distinguish the old ideal runs from LC05. A filename or
run directory by itself is not a new initialization. The `SS_MPI4` and
`SS_MPI4B` `wrfinput_d01` aliases resolve to the same SS input and have the
same `5a9ae8da…` hash; their boundary aliases also resolve to the same SS
boundary. Apart from these aliases, the other distinct canonical-host
`wrfinput*` files found by a no-ignore filename inventory are a 41×41×40,
2 km ideal input (`wrfinput_base`, year 0001) and a 100×100×34, 1 km ideal
input (`wrfinput_d01.37`, 2007-06-01). Neither meets S12's real 5 km criterion.
Saved `wrfrst*` files are continuations, not independently initialized inputs.

The adjacent historical local directory
`/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/em_real/` contains another real-data 5 km
`wrfinput_d01`/`wrfbdy_d01` pair dated 2023-02-16, with hashes
`5a9d7283d9515c8fde2206612d166d0618db6834150062a164d7251edfac0791`
and `df2a93c51faa36b31804797192e46a0797a8d511ec819024f59e20476b78ad5d`.
Its grid is 199×249×40, and its `met_em` symlinks resolve to a separate
`wps_era5_20230216_0000` source. Its inspected boundary file has only one
time record despite the six-hour configured interval, so a complete boundary
sequence for a new forecast is not established. It is recorded as a provenance
lead only:
it is outside the canonical private host, does not match the fixed LC05 grid,
and cannot silently replace the current input under the no-external-substitute
rule. The SS directory also contains neighboring `met_em` names from that
2023 grid; those do not turn the 2025 SS input into a second coherent case.

## Scope and next condition

The filename search covered the canonical host tree, followed by header and
symlink checks on the candidates. It is not a proof that no independent case
exists anywhere in the user's storage. S12 can advance only when a separately
initialized, source-attributed case satisfying the declared input policy is
available and selected **before** inspecting its validation result. Existing
LC05 spatial columns, later history frames, idealized grids and this adjacent
ERA5-derived pair do not close the current S12 gate.

The Graphify dependency query did not resolve a complete private-input lineage,
and an LLM semantic extraction backend was unavailable. The file/header/hash
checks and the linked wiki synthesis provide this inventory's source-based
evidence; the derived code graph alone is not used to assert file identity.
