# G4.2 selected-profile surface handoff plan

## Status and scope

This is a source-backed plan for the next bounded S6 diagnostic. It is not a
new WRF run, a cause finding, or a resolution of restart divergence. No native
build/run was performed for this plan; S6 remains **OPEN**. The earlier G4
continuous/restart evidence and its measured failure remain unchanged.

The planned comparison carries the existing five preselected G4 profiles from
the caller's pre-surface snapshot through the active SFCLAY and Noah-MP calls,
then to the surface-driver return. It records selected operands and outputs at
each boundary. A mismatch identifies the earliest observed boundary among
those records; it does not establish that every routine input, module
variable, or lookup-table dependency has been captured.

## Evidence already established

The retained checkpoint/common saved state agrees 235/235 between the parent
and restarted child. The same shadow binary reproduces both retained histories
bitwise. At the first resumed RK step, the five profiles match after physics
preparation and radiation. The first relevant differences in the existing
trace occur after the surface driver: `HFX`, `LH`, `QFX`, and `UST` differ for
the clear, ice, and rain profiles; PBL tendency differences occur later. The
existing trace does not contain a complete surface-driver input set.

I read the retained input file with SHA-256
`5a9ae8da992028dbf3a2a7652eb61532c1efab2acea7ea0e393e4cac8fd4c970`. Its
selected profile metadata are:

| Profile | `XLAND` | `IVGTYP` | `VEGFRA` |
| --- | ---: | ---: | ---: |
| clear | 2 | 17 | 0 |
| warm liquid | 1 | 12 | 60.35637 |
| mixed | 1 | 12 | 62.85215 |
| ice | 2 | 17 | 0 |
| rain | 2 | 17 | 0 |

All three profiles with the first observed surface-output difference have
`XLAND=2`; both profiles without a stage-3 difference have `XLAND=1`. The
surface-layer source documents XLAND 1 as land and 2 as water, and the current
live Noah-MP `MPTABLE.TBL` maps `ISWATER=17` (line 194). This is an
**association with the water-class surface path**, not a causal result. The
atmospheric labels (clear/ice/rain) do not themselves identify which
downstream producer changed. The retained G4 run receipt does not contain a
hash of the table that its process loaded.

The retained namelist records `sf_sfclay_physics=1`,
`sf_surface_physics=2`, `sf_urban_physics=1`, `isfflx=1`, and `bldt=0`, with
adaptive timestep disabled. `module_surface_driver.F` returns early only when
`sf_sfclay_physics=0` (line 1518); `bldt=0` selects every-step surface work
(lines 1874–1925). The call path includes SFCLAY at line 2093, Noah-MP at line
3231, and the Noah-MP urban routine at line 3289 when the urban option is
positive. The Noah-MP driver has a separate `IVGTYP == ISWATER_TABLE` path
(`module_sf_noahmpdrv.F`, line 2166). These source facts make a water-path
input difference worth testing. They do not prove which branch produced the
three observed differences. `fractional_seaice` is not explicit in the
retained `namelist.input` text or current S6 run receipt, so the next event
schedule must obtain and record its actual configured value rather than
assuming a default.

## Source pins and provenance limit

The public plan pins five current live private source files and the active
Noah-MP table in `g4_surface_handoff_probe.py`: the first-RK call site, surface
driver, SFCLAY routine, Noah-MP driver/LSM, and `MPTABLE.TBL`. The current live
files pass the SHA and anchor-count audit. The private source bytes are not
copied into the public repository.

The selected anchor locations are `module_first_rk_step_part1.F` before the
surface call (line 602) and after it (line 1111); `module_surface_driver.F`
around the normal SFCLAY call (lines 2093–2104), its sea-ice wrapper (lines
2075–2091), Noah-MP case entry (line 3147), the conditional sea-ice input
conversion (lines 3188–3222), Noah-MP call/return (lines 3231–3285), and urban
call/return (lines 3289–3342). Anchor occurrence counts are code-fixed so
source drift fails the audit instead of shifting a snapshot silently.

Those live-source hashes do **not** prove that these exact versions produced
the retained G4 executable. Before a capture is interpreted causally, the
shadow build receipt must connect each instrumented source to the archived
object/library and demonstrate that only the intended capture objects changed.
The established first-RK source pin remains
`108a82b213c423acf916b91a0dd5f8084dc79288a01ca82d9f8d0ccb8febd53f`; the
current live surface-driver pin is
`45543da3d3842985053d3d35cadccbd897aa4655c5f155d514133ce34f5524d5`.

The existing first-RK overlay still has an exact source-strip test. The new
plan adds source-anchor audit and capture-key tests, but it does not claim a
compiled surface-driver overlay or native noninterference result.

## Event and operand schedule

The expected schedule is computed from a predeclared run contract and fixed
profile list, never from rows received. The contract rejects a missing
`fractional_seaice` setting and only accepts the retained G4 step-2 surface
configuration. The base events are:

1. The caller's pre-surface input boundary and returned surface state.
2. Immediately before and after the selected SFCLAY call (the standard call
   or sea-ice wrapper, chosen from the declared config).
3. Noah-MP dispatch entry, before any fractional-sea-ice conversion.
4. After that conversion only when fractional sea ice is configured, then
   immediately before and after the Noah-MP call.
5. Before and after the Noah-MP urban call for the pinned `sf_urban_physics=1`
   configuration. The current plan records `urban_branch_active` and
   `seaice_adjustment_branch_active` as null for every profile, meaning those
   outcomes are unobserved. A future native capture must add and validate a
   per-profile active/inactive mask from the routine's branch conditions;
   this plan's `EVENT_FIELDS` and `CaptureRow` do not validate branch coverage.
6. Surface-driver return.

The declared selected-operand set is grouped around each step's actual inputs:

| Boundary | Inputs/outputs to capture at the five sites |
| --- | --- |
| SFCLAY | Low-level `u_phytmp/v_phytmp`, temperature, vapor, pressure and layer thickness; `XLAND`/land-use class; skin temperature and the SST/ice inputs when present; roughness and stability inputs; existing fluxes; surface exchange coefficients and the `UST/HFX/LH/QFX` outputs. |
| Noah-MP | The SFCLAY handoff fluxes; atmospheric forcing; land/soil/snow/canopy state; land-use and soil categories; albedo/emissivity; water/ice and timestep controls; and the post-call flux and state fields. |
| Urban / fractional sea ice | Current plan: configured activation flags, incoming/outgoing fluxes, skin temperature, albedo/emissivity, roughness, and ice fraction at the associated boundary. Per-profile branch-active outcomes are explicitly unobserved/null; a native capture must add and validate that mask before claiming branch coverage. |

`EVENT_FIELDS` in the verifier gives a fixed diagnostic subset and exact
levels. It is not a proof of the entire callee read set. If all declared
operands match but outputs differ, the correct classification is
“producer output differs with unobserved dependencies still possible”; the
next capture must widen the read set or inspect module/static state.

## Mismatch classification and validity gates

The verifier distinguishes these outcomes within its current operand schema; it
does not validate per-profile urban or sea-ice branch activity:

| Earliest differing record | Result label | Interpretation |
| --- | --- | --- |
| Entry or `*_pre` operand | Input/state operand difference | The consumer receives different captured values; trace their producer. |
| `sfclay_post` after matching `sfclay_pre` | Producer-output or unobserved-dependency difference | SFCLAY output differs, but omitted inputs or hidden state remain possible. |
| `noahmp_pre` after SFCLAY | Handoff difference | Identify which SFCLAY output or intervening conversion changed. |
| `noahmp_post` after matching `noahmp_pre` | Producer-output or unobserved-dependency difference | Noah-MP or its uncaptured state/lookup dependencies remain candidates. |
| Urban, sea-ice, or surface-return boundary | Later surface-path difference | Localize to that observed phase only. |

Every classification keeps `cause_established=false`. The validator requires
the full fixed profile×event×field×level key universe in each arm and rejects
missing or extra rows even when a mutation preserves row count. Its synthetic
tests exercise event selection, source anchors, existing overlay strip
identity, missing operands, cardinality-preserving substitution, and bounded
classification.

Before interpreting any new capture, use the same shadow executable and
retained inputs for continuous and restarted runs, archive the exact
checkpoint/configuration/source/object hashes, and run a dump-off control with
that executable. Require its history to match the retained G4 history by the
existing strict comparator. Preserve the seven history-only diagnostics
separately. Do not alter the operational path or default, and do not call a
bounded selected-profile result a full-domain first cause.

The machine-readable source and operand plan is
`g4_surface_handoff_plan_2026-09-26.json`. It marks the schedule not ready
because the retained S6 run receipt does not record `fractional_seaice`; obtain
its runtime value before freezing the conditional event universe. The Python checker is
`harness/g4_surface_handoff_probe.py`; its synthetic tests do not represent a
new host run.
