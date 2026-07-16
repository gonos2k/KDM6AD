# KDM6AD — capability status

Single source of truth for **what is implemented and validated today**, separate from the
chronological audit trail in the wiki/parity logs. Baseline: `origin/main@e1c701e`.

Legend: ✓ implemented & tested · partial · – not present · diag = diagnostic-only (not a
seedable AD output) · host = validated only on the private WRF/KIM-meso host (not public CI).

## Differentiation surface

| Capability | Python oracle | C++ fp64 | C++ f32 | C ABI | Public CI | Host-validated |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Forward step (12 state, 4 forcing) | ✓ | ✓ | ✓ | ✓ | ✓ | host (12h bitwise) |
| State VJP  `Mₓᵀu` | ✓ | ✓ | diag | ✓ | ✓ | – |
| State JVP  `Mₓv` (Pearlmutter double-VJP) | ✓ | ✓ | diag | ✓ | ✓ | – |
| HVP  `∇²J·v` (branch-local) | ✓ | ✓ | – | – (C++ only) | partial | – |
| Forcing VJP  `M_fᵀu` (ρ, Π, p, Δz) | – | – | – | – | – | – |
| Parameter VJP  `M_θᵀu` | ✓ | – | – | – | partial | – |
| Precip / ρ_g / reflectivity / r_eff seed | diag | diag | diag | – | – | – |

## Observation operator (RTTOV)

| Capability | Status |
|---|---|
| Clear-sky T/Q Jacobian (RTTOV-K) | ✓ |
| All-sky cloud content (qc→clw, qi+qs→ciw) + Deff | partial (host RTTOV) |
| Rain / snow / graupel as separate hydrotable species | – |
| Cloud fraction | binary, non-differentiable passthrough (`cfrac`) |
| Continuous / probabilistic cloud occurrence | – (pseudo-RH bootstrap only) |
| Radar reflectivity / Z_DR operator | – |

## Assimilation window

| Capability | Status |
|---|---|
| Microphysics-only variational window (fixed forcing) | ✓ |
| Checkpoint/recompute adjoint over the window | ✓ |
| Conserving/bounded CVT (log-CVT, partition channels) | ✓ |
| L-BFGS / dual-loop minimizer | ✓ |
| Full-model outer loop (re-integrate dynamics/forcing) | – |
| Coupled host adjoint (pressure/density/Exner/metric) | – |
| Multivariate background error B (T–qv–qcond, mass–number, phase) | – (diagonal, tuned start) |

## Library / packaging

| Capability | Status |
|---|---|
| Stable C ABI v2 (`struct_size`+`abi_version` framing) | ✓ |
| Hidden visibility, exactly 9 exported C symbols, SOVERSION 2 | ✓ |
| Thread-determinism fail-closed fence | ✓ |
| `KMP_DUPLICATE_LIB_OK` caller-owned (PR1-B) | ✓ |
| fp64 AD entry as a v2 descriptor (`struct_size`, strides, masks) | – |
| C-ABI scientific-domain validation (dt>0, ρ/p/Π/Δz>0, finiteness) | partial (Python side ✓) |
| LICENSE / SPDX / third-party notices | – (owner/provenance decision) |

## Known scope boundaries (see README → Scope & differentiation contract)

- The differentiated map is the **branch-local fp64** map, not the literal f32 adjoint.
- Gradients across jumps/kinks and across CFL `mstep` changes are not sensitivities through the switch.
- `threshold cleanup` zeroes sub-threshold hydrometeor mass **and** paired number without
  returning mass to `qv` or applying a latent-heat/T correction. Measured (P0-4): at the
  single-step level this sink is roundoff-small (`~0`), not a meaningful bias — microphysics
  conserves column water to fp64 (`max|ΔW_micro| = 7e-15`). See [`P0-4_water_budget.md`](P0-4_water_budget.md).
- The operator-implied column-water loss (`sed_column_loss = −ΔW_sed`) and the WRF `rain_increment`
  total-fallout diagnostic **disagree** by a non-constant O(1) amount (e.g. 6.80 vs 2.00 kg/m² for a
  heavy-rain column). **Attributed (P0-4b): 100% is the internal interface defect from the
  post-update-reservoir inflow cap** — reference-faithful (verbatim in Fortran
  `module_mp_kdm6.F`; oracle/C++/Fortran identical), identity closes to the fp64 floor; the bottom
  diagnostic itself is accurate (`B ≈ 0`). Any fix is a freeze-lift decision (changes trajectories).
  See [`P0-4b_sedimentation_attribution.md`](P0-4b_sedimentation_attribution.md).
  **Prevalence measured (P0-4b.1)**: fires in 53–61% of real LC05 columns every step (steady-state
  ≈ 2–5% of fallout, p99 tail 1.3 kg/m²/3 h; analysis-IC states lose up to 41%/step); a
  conservative counterfactual (`kdm6/sed_conservative.py`, analysis-only opt-in) closes the budget
  to fp64 and yields +34% cumulative precip on heavy columns. Decision package:
  [`P0-4b1_interface_sink_prevalence.md`](P0-4b1_interface_sink_prevalence.md).
- Column water budget is `ρΔz`-weighted (`oracle/kdm6/water_budget.py`, opt-in, byte-identical
  default); the earlier "water budget" was an unweighted layer-sum.

Provenance for the closed hardening line: [`RELEASE_ABI_V2_HARDENED.md`](RELEASE_ABI_V2_HARDENED.md),
[`PR1B_OPENMP_DIAGNOSTIC.md`](PR1B_OPENMP_DIAGNOSTIC.md). External deep review that motivated
this table: [`../wiki/sources/kdm6ad-deep-review-2026-07-15.md`](../wiki/sources/kdm6ad-deep-review-2026-07-15.md).
