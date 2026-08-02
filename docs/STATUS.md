# KDM6AD — capability status

Single source of truth for **what is implemented and validated today**, separate from the
chronological audit trail in the wiki/parity logs. Baseline: current `main` at the C4
evidence closeout — the authoritative commit is pinned in
`docs/c4_evidence_manifest.json` → `public_repo.producer_commit` (updated per closeout,
not a frozen historical tag).

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

### Experimental physics variants

Landed variants are opt-in and carry NO release/default eligibility until their
full gate set (docs/FREEZE_LIFT_CONSERVATIVE_INTERFACE_V1.md) is green:

| Variant | C++ implementation | Public v2 selector | Fortran reference variant | 12h × MPI certification | Release / default-DA eligibility |
|---|---|---|---|---|---|
| conservative-interface-v1 | experimental | implemented | implemented (**scope: water-mass-conservative interface; NUMBER transport (nr) is reference-faithful, NOT certified column-number-conserving** — nr is a number MIXING ratio [# kg-1] (Registry.EM_COMMON:122) so the physical column measure is rho*dz*nr, while the reference-faithful rung uses the dz ratio only; a dedicated number-budget science gate on the rho*dz*nr measure is required before any column-number-conservation claim. C4: host mp237/mp337; Gates A/C PASS; Gate D SS-short 237↔337 STRICT BITWISE post the merged C4-S1 `piacw` `pi_t` fix, PR #26; Gate B G1/G2/G3.1/G3.2/G3.4 PASS but **G3.3 legacy-ULP-envelope OPEN** (unchanged by the fix; closure via the G3.3-M mechanism-provenance gate, not the withdrawn relative-envelope); legacy 12h×np4 37↔137 recert **STRICT BITWISE PASS on all generated frames** (both runs fail-closed verified; 12 frames × 254 vars incl `Times` raw-bit identical — the fix did not perturb legacy f32 parity), **and terminal 12:00:00-state parity PASS** (dedicated exact-hourly re-run, 13 frames 00:00:00…12:00:00, 12:00 terminal frame raw-bit + `Times` exact). C4 HOLD until G3.3 attributed. See FREEZE_LIFT §Current-status.) | pending (C5) | no |

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
  **Prevalence measured (P0-4b.1, artifacts corrected in P0-4b.2** — operational xland/ncmin,
  fixed vertical-coordinate mapping, 36-interval convention, decision-grade provenance**)**:
  fires (>1e-9 kg/m²) in 51–61% of real LC05 columns every step (2.1–4.6% of fallout once
  precipitation is equilibrated, fr ≥ 6 — up to 12.4% during spin-up, p99 tail 1.3 kg/m²/3 h;
  the unspun initial-condition frame shows a 41%-of-hydrometeor one-step sink susceptibility —
  a stress case, not a measured post-analysis state; analysis-output replay pending); summed
  figures are sums of column water-equivalents over 65,988 columns, not per-area domain
  masses; worst interfaces at ~274–305 hPa half-level
  (upper-troposphere ice region — qi carries 65.6% of the sink); positivity projection A is
  exactly 0 on frames 1–36 and 1.9e-3 kg/m² (6.4e-7 of the defect) on frame 0. A conservative
  counterfactual (`kdm6/sed_conservative.py`, analysis-only opt-in) closes the budget to fp64
  and yields ≈ +29% aggregate cumulative precip on heavy columns (1.306/1h, 1.285/3h); combined
  single-step VJP norm 1.86× on the synthetic case (obs-space adjoint unmeasured). Decision
  package: [`P0-4b1_interface_sink_prevalence.md`](P0-4b1_interface_sink_prevalence.md).
- Column water budget is `ρΔz`-weighted (`oracle/kdm6/water_budget.py`, opt-in, byte-identical
  default); the earlier "water budget" was an unweighted layer-sum.
- The **number-transport measure mismatch is now measured**, not only reasoned about
  (owner §7). Mass moves with `ρΔz` and number with the legacy `Δz`-only measure, so a
  transferred population's mean particle mass shifts by `ρ_u/ρ_l`. Predicted 1.0330 /
  1.0319 / 1.0309 for the three column-3 transfers; **measured 1.0331 / 1.0296 / 1.0126**
  against the legacy run at the same cell, with the no-inflow top level at exactly
  1.0000 as the control. **The mechanism is real and it is ~3% per transfer.** The much
  larger differences at coarse steps (up to 8.7×) are dominated by branch-topology
  divergence, not by the transport arithmetic, and the effect vanishes at the finest
  step. No column-number CLOSURE is possible from the current drivers — the surface
  NUMBER flux is not emitted, only mass precipitation — and the measurement is the
  **ice** channel: the interface never touches `nr`/`qr` on the available fixtures, so
  the rain-number channel this row names is still unexercised.
  See [`../harness/evidence/FINDING_number_budget_v1.md`](../harness/evidence/FINDING_number_budget_v1.md).
- **`ncmin` column non-locality now fails two independent acceptance gates**, both
  `xfail(strict=True)` in `harness/tests/test_g33_column_separability.py`. Column
  permutation moves 46 of 144 final-state cells. Tile decomposition, exhaustive over the
  contiguous partitions of the domain, moves **16/144 at (1,1,1) and 31/144 at (2,1)** —
  up to 21% of the state decided by where the tile boundary falls, with all twelve
  prognostics moving in the affected columns. A tile ending on the sea column gates *all*
  of its columns on `ncmin_sea`, which is why `(2,1)` is worse than isolating the sea
  column, and why an even split misses it. **An MPI rank boundary is a tile boundary**, so
  this is the rank-count dependence as well. Both gates are inert on the all-land
  arithmetic fixtures and require `boundary_mapping_v1`. A mixed coastal **real** case
  remains untested. See [`../harness/evidence/FINDING_ncmin_scalar_vs_percell.md`](../harness/evidence/FINDING_ncmin_scalar_vs_percell.md).
- **Both §8 energy ledgers are built and they agree.** The conservative interface closes
  the physical moist-enthalpy budget ~74× better than the reference and the
  operator-consistency budget ~2200× better; the sub-cycle-refreshed coefficient policy
  closes **both** ~1.5× worse than the reference's call-fixed policy. The trade-off §8
  anticipated — better on one ledger, worse on the other — does not occur here. This
  compares implementations, not policies: isolating the policy needs the
  reference-faithful C++ counterfactual, which is inside frozen code.
  See [`../harness/evidence/FINDING_moist_enthalpy_ledger_v1.md`](../harness/evidence/FINDING_moist_enthalpy_ledger_v1.md).

Provenance for the closed hardening line: [`RELEASE_ABI_V2_HARDENED.md`](RELEASE_ABI_V2_HARDENED.md),
[`PR1B_OPENMP_DIAGNOSTIC.md`](PR1B_OPENMP_DIAGNOSTIC.md). External deep review that motivated
this table: [`../wiki/sources/kdm6ad-deep-review-2026-07-15.md`](../wiki/sources/kdm6ad-deep-review-2026-07-15.md).
