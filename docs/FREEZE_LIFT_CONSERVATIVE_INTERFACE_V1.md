# Freeze-lift authorization — conservative-interface-v1

**Status**: AUTHORIZED (owner, 2026-07-17) · **Branch**: `physics/conservative-interface-v1`
**Decision basis**: P0-4b attribution + P0-4b.1/b.2 corrected decision package
([`P0-4b_sedimentation_attribution.md`](P0-4b_sedimentation_attribution.md),
[`P0-4b1_interface_sink_prevalence.md`](P0-4b1_interface_sink_prevalence.md); PRs #14–#17).

This is the first scoped lift of the frozen-code discipline since
`abi-v2-hardened@a53503e`. It authorizes exactly one physics change — the
sedimentation **interface transfer** — as a **new, separately selectable
variant**. The legacy path stays byte-identical everywhere and forever.

## What the variant fixes

Legacy NISLFV-PLM re-caps the stored raw interface flux by the source cell's
POST-update reservoir (`dqs(i,k+1) = min(falk·Δz(k+1)/Δz(k)·dtcld/dend, qrs(k+1))`
with `qrs(k+1)` post-update — verbatim in reference Fortran), deleting mass at
internal interfaces whenever the per-substep fall ratio exceeds ½. The
conservative variant hands the lower cell the mass **actually removed** from
the source cell (entry-capped outflow, per-species ρΔz-converted), and the
surface diagnostic reports the actual bottom outflow. Per-column closure
`Wⁿ⁺¹ − Wⁿ + P_actual = O(ε)` becomes an enforced gate. The oracle
counterfactual (`oracle/kdm6/sed_conservative.py`) is the numerical reference.

## Scope — INCLUDED

- Pass the source cell's actual capped removed mass to the cell below
- Inter-layer mass conversion via ρΔz (per species)
- Bottom diagnostic = actual bottom outflow
- Species: `qr`, `qs`, `qg`, `qi`
- Consistent movement of the paired `nr`, `ni`, `brs/bg` bookkeeping
- Corrected Fortran variant (new scheme module)
- Corrected C++/LibTorch variant
- Append-only ABI variant-selection plumbing (below)
- New WRF/KIM scheme identifier, recorded in outputs and manifests

## Scope — EXPLICITLY EXCLUDED

- Any change to legacy mp37/mp137 equations
- Raw ice-velocity handoff (the qi-dominant *pathway* stays as-is — changing
  it here would make conservation-fix and fall-speed effects inseparable)
- `mstep` selection rule
- DSD, fall-speed, or saturation-adjustment changes
- warm/cold/melt/freeze process changes
- P0-4c energy work

## ABI selection contract (append-only, v2)

```c
typedef enum {
    KDM6_PHYSICS_LEGACY = 0,
    KDM6_PHYSICS_CONSERVATIVE_INTERFACE = 1
} kdm6_physics_variant;

/* appended at the end of kdm6_step_v2_args */
uint32_t physics_variant;
```

- Callers with the smaller existing `struct_size` → automatically legacy
- `physics_variant = 0` → legacy; `= 1` → conservative interface variant
- Any other value → `KDM6_ERR_INVALID_ARG` (fail-loud)
- v1 `kdm6_step_c` → permanently legacy
- Exactly 9 exported symbols, ABI major and SOVERSION 2 unchanged

## Acceptance gates

### Legacy invariance (all mandatory)

- v1 results byte-identical
- Existing v2 struct-size callers byte-identical
- New v2 with `physics_variant = 0` byte-identical
- Existing mp37↔mp137 12 h × MPI parity preserved
- 9-symbol export surface preserved
- `abi-v2-hardened@a53503e` tag permanently immovable

### Conservative variant

Per-column `Wⁿ⁺¹ − Wⁿ + P_actual = O(ε)` across:

- single-layer capped/uncapped · variable ρ/Δz · multiple interfaces
- multi-`mstep` · multi-KDM-subcycle · qr/qs/qg/qi isolation
- number/rime (`nr`/`ni`/`brs`) bookkeeping consistency · nonnegativity
- corrected Fortran ↔ corrected C++ parity · 12 h × np4
- surface precipitation closure · smooth-regime VJP/JVP parity

The variant gets its own scheme ID, release evidence, parity report, and tag;
no legacy tag or result is overwritten.

### Science gates before production / default-DA promotion

- LC05 1 h/3 h precipitation impact · independent precipitation validation
- hydrometeor vertical profiles · replay of actual accepted analysis states
- all-sky BT and observation-cost comparison
- conservative oracle ↔ C++ fp64 derivative smooth-regime parity

## P0-4c status

HOLD until BOTH: (1) conservative Fortran ↔ C++ forward parity, and
(2) conservative column-water closure green from single-column through
12 h × MPI. Actual analysis-state replay and all-sky BT/obs-cost remain the
production-promotion gates, not implementation preconditions.
