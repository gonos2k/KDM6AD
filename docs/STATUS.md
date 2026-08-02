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
  larger differences at coarse steps (up to 8.7×) are **unattributed** — an earlier
  "dominated by branch-topology divergence" is withdrawn, since the flipping species
  is 3.99e-06 of the column. The finest-step endpoint shows little difference, which
  makes the *final-state manifestation* small at a fine step and does **not** make
  the measure mismatch non-structural: the transfer still uses ρΔz for mass and
  Δz-only for number, in the source, independent of timestep. No column-number CLOSURE is possible from the current drivers — the surface
  NUMBER flux is not emitted, only mass precipitation; it is `falln(i,kts,1:2)`
  (rain and ice number), a kernel **local** at `module_mp_kdm6.F:719` with no
  `intent`, so it is reachable only through the SHA-pinned macro-gated overlay that
  recovered `mstep`, **not** by a driver edit as an earlier note claimed — and the measurement is the
  **ice** channel: the interface never touches `nr`/`qr` on the available fixtures, so
  the rain-number channel this row names is still unexercised.
  See [`../harness/evidence/FINDING_number_budget_v1.md`](../harness/evidence/FINDING_number_budget_v1.md).
- **A correction to the refinement work's own reasoning.** The graupel presence flip
  used to argue that column 3 is "not a valid convergence domain" carries
  **3.88e-06 of that column's water** — parts per million, far too small to produce
  the O(1) swings in its convergence exponents (−5.86, +3.88, −1.02, +0.41). The
  flip is real; the attribution was asserted from its existence without checking its
  magnitude, and is **withdrawn**. Column 3's erratic orders are now
  **attributed to the sedimentation sub-step count**, recovered from the kernel's own
  records (instrumented run verified bit-identical to the plain build). `mstep` is a
  rounded integer, so the quantity actually refined is `dtcld/mstep`, not `dtcld`:
  column 1 has `mstep ≡ 1` and converges cleanly (+1.002), column 3 runs
  `mstep` 10→5→3→2 so its effective step never halves and its range *widens*
  (10–14.3 s at h=100 against 10–25 s at h=50) — measured order −5.86, +3.88, −1.02,
  +0.41. **The ordering of columns by how well `mstep` tracks the chain is the
  ordering by how well they converge.** Consequence: §9's obstacle is a
  **sweep-design** problem — but making `mstep` constant is **necessary and not
  sufficient**, and the "a chain over which `mstep` is constant would give column 3 a
  valid domain" that stood here is **withdrawn**. Measured: `mstep` reaches 1 at
  h = 12.5 s (col 2) and h = 6.25 s (col 3), while extending the chain to h = 0.39 s
  shows the successive differences **stop falling and start growing** below
  h = 3.125 s (`th` 1.46e-3 → 2.69e-3 → 6.41e-3; members bit-identical on re-run, so
  accumulated f32 roundoff, not nondeterminism). Since an order needs three members,
  the finest clean order is 12.5→6.25, leaving column 1 **four** clean orders
  (`+1.969, +1.002, +1.000, +1.002`), column 2 **one** (`+0.066`) and column 3
  **none**. A usable fixture needs `mstep` to reach 1 by h ≈ 25 s — ~4× slower fall
  speeds — which merges this with the §6 smooth-cold-fixture requirement rather than
  being a separate need. Column 3's ρΔz **ice number** does converge throughout
  (`+1.121, +1.029, +1.052`), so that channel has an order where column water has
  none.
  See [`../harness/evidence/FINDING_refinement_noise_floor_v1.md`](../harness/evidence/FINDING_refinement_noise_floor_v1.md).
- **Column 3 DOES have a valid convergence domain — in the ice chain, and the
  domain is per-CHAIN not per-column.** The kernel runs two sedimentation
  sub-cycles with separate counts (F:1179-1180): `mstep` governs **qr, nr, qs, qg**
  and `mstep_i` governs **qi, ni**. `mstep_i` was a kernel local nothing emitted;
  reached through a new anchored overlay site, it reaches 1 at **h = 25 s** in
  column 3 where the main chain needs **h = 6.25 s**. `ni` column number never
  meets the noise floor (successive differences fall monotonically 1.76e8 → 9.72e5,
  relative signal ~1e-2 against `th`'s ~5e-6), so inside that window it has **five
  clean successive orders — `+1.461, +0.863, +1.121, +1.029, +1.052`** — first
  order, tightening at the fine end. Column *water* still gets none, now for a
  stated reason: it contains qr/qs/qg and so inherits the **main** chain's h ≤ 6.25
  against a noise floor at h ≥ 3.125. This explains what the previous row recorded
  as an unexplained positive result. **The surface number flux is now emitted too**
  (`falln(i,kts,1:2)` + den/delz/dtcld as operands), validated at the same site
  against `bottom_fall_qr`: mean rain-drop mass 5.4–8.6e-10 kg (0.10–0.12 mm),
  consistent across columns. It measures that **every column loses all its rain
  number while the surface accounts for only 1.4–5.8%** — so a transport-side `nr`
  defect would sit under a sink 1–2 orders larger. **Still not a closure**: `R_N`
  is defined, not checked; the microphysical number tendencies are per-cell locals.
  Both emissions sit under their own `KDM6_G33_NUMBER_DUMP`, never defined by
  `fortran_build.sh` — the decision-path stream is **bit-identical** to before, and
  the instrumented run is **bit-identical** to the plain build.
  See [`../harness/evidence/FINDING_two_sedimentation_chains_v1.md`](../harness/evidence/FINDING_two_sedimentation_chains_v1.md). The analyzer now prints each flip's share of
  column water beside it so the record cannot be re-read as a sufficient
  explanation.
- **The refinement bundle is reproducible, and the reproduction was run.** Its
  provenance previously named the compiler as a string the caller typed and carried
  an empty `compile_commands` list, which is indistinguishable from a build nobody
  recorded; members were admitted on a BEGIN-line regex rather than the strict
  parser. The **build** now writes what only it knows — compiler path/sha256/version,
  the commands as it compiles them, build-script and source digests, commit and
  `tree_dirty` — and `_member()` goes through `g33_refine_analyze.read()`. Rebuilt
  from a clean tree at `29c5119`, all six members reproduce with an **insertion-only
  diff (0 removed, 0 changed, 180 added)**: every committed record is bit-identical,
  and the additions are 144 `INITIAL` + 36 `FORCING` records the driver gained later.
  Compared against `budget/`, a separately-compiled bundle over the same six members,
  **all six outputs are byte-identical across builds 7.5 hours apart** — so the
  Fortran refinement leg is bit-reproducible on this host, and every ρΔz column-budget
  order STATUS cites (col 1 `+1.002`; col 3 `−5.860, +3.884, −1.017, +0.407`)
  reproduces exactly from the fresh build.
  The bundle was refreshed to the rebuilt streams — not cosmetic, since without
  `FORCING` there is no ρΔz and the old streams could not support the column water
  budget, either ledger, or the diagnostic-trust table. **Limits**: one host and one
  compiler, so cross-host reproduction is enabled but untested; and this producer
  *records* `tree_dirty` where the decision-bundle producers *refuse* it — deliberate
  for a `decision_eligible: false` artifact, but an owner call.
  See [`../harness/evidence/FINDING_refinement_provenance_v1.md`](../harness/evidence/FINDING_refinement_provenance_v1.md).
- **The conservative variant does not satisfy time-step composition, and the cause is
  localised.** `Φ_cons(300) ≠ Φ_cons(100)∘Φ_cons(100)∘Φ_cons(100)` (18 records,
  ΔT ≤ 2.67e-03 K) while the legacy composition holds **bitwise** (132/132). Both
  arms refresh `cpm`/`xl` three times, so it is not the thermodynamic policy.
  Exhaustive over the partitions dtcld permits, the whole effect is **one boundary at
  t = 200 s**. Of the ten per-call entry clamps (`runtime.cpp:424-436`) exactly one is
  out of range there — **`ni ∈ [0,1e6]`, extreme 4.8151e+06 at 4 cells** — and it
  fires identically under legacy, so it is necessary and not sufficient. The
  diverging cells are **exactly the clamped cells that receive inflow**: clamped
  {col3 k0,k1,k2,k3}, diverging {k0,k1,k2}, and the omitted k3 is the top level,
  independently shown to have no inflow. Sufficiency is untested — suppressing the
  clamp needs a change inside frozen C++. **Operationally**: a host that splits a
  microphysics call (DA window, checkpoint/recompute adjoint, different tile or rank
  decomposition) changes how often that clamp fires; free under legacy, not under the
  conservative interface. **Open before C5.**
  See [`../harness/evidence/FINDING_conservative_call_composition_v1.md`](../harness/evidence/FINDING_conservative_call_composition_v1.md).
- **`ncmin` column non-locality now fails two independent acceptance gates**, both
  `xfail(strict=True)` in `harness/tests/test_g33_column_separability.py`. Column
  permutation moves 46 of 144 final-state cells. Tile decomposition, exhaustive over the
  contiguous partitions of the domain, moves **16/144 at (1,1,1) and 31/144 at (2,1)** —
  up to 21% of the state decided by where the tile boundary falls, with all twelve
  prognostics moving in the affected columns. A tile ending on the sea column gates *all*
  of its columns on `ncmin_sea`, which is why `(2,1)` is worse than isolating the sea
  column, and why an even split misses it. **An MPI rank boundary is a tile boundary**, so there is a strong
  mechanism for rank-count dependence — but that is a **prediction, not a
  measurement**: a real host adds halo width, the `its:ite` against `ims:ime`
  relationship, per-rank land/sea layout and exchange timing. A genuine gate needs
  the same global mixed-coastal case at np = 1/2/4, reassembled in one ordering and
  compared raw-bit. Both gates are inert on the all-land
  arithmetic fixtures and require `boundary_mapping_v1`. A mixed coastal **real** case
  remains untested. See [`../harness/evidence/FINDING_ncmin_scalar_vs_percell.md`](../harness/evidence/FINDING_ncmin_scalar_vs_percell.md).
- **The P0-4b diagnostic/column-loss disagreement is a strong function of timestep,
  and the conservative interface removes it entirely.** Under the conservative
  interface the total fallout equals the column water loss **exactly at every
  timestep** (total/−ΔW = 1.0000). Under legacy the diagnostic is **6.56× its own
  fine-step limit at dtcld = 100 s** while the water loss is only 1.31×, converging
  only near 3 s — and the departure **changes sign with phase**: the pure-liquid
  column 1 UNDER-reports by 19% (0.808) while the 97–99% frozen columns 2 and 3
  over-report by 9.2× and 3.9×, which a column-summed figure hides. So STATUS's
  "non-constant O(1) amount" is a strong function of the step. **Not** a claim that
  the variants precipitate differently by 6× — the column water losses differ by
  ~14%. Column 1 (warm, no ice) is bit-identical at five of six steps but NOT at the
  coarsest, where 5 records differ (`nccn`, `qv`, `th` — never a condensate). Synthetic fixture, microphysics
  only. (Species note: WRF's `rain` is the TOTAL fallout and `snow`/`graupel` are
  components of it, F:1462-1464 — summing the three double-counts.)
  See [`../harness/evidence/FINDING_precipitation_timestep_sensitivity_v1.md`](../harness/evidence/FINDING_precipitation_timestep_sensitivity_v1.md).
- **Both §8 energy ledgers are built. Corrected twice after adversarial review**,
  which found two independent defects: the enthalpy flux was taken from the
  known-defective fallout diagnostic (P0-4b), and the frozen species were
  double-counted — WRF's `rain` is the TOTAL fallout while `snow` and `graupel` are
  **components of it** (F:1462-1464), so summing the three over-counts. With both
  fixed: **the conservative interface closes the column water budget EXACTLY at every
  timestep** (total/−ΔW = 1.0000), while legacy over-reports ~5× at coarse steps and
  converges only near 3 s — the P0-4b defect measured as a function of resolution.
  On the ledgers the conservative interface is **~10× better in column 2** (the
  the one whose sedimentation sub-step count is nearest constant) and **neutral in
  column 3**. The coefficient-policy
  contrast is **1.6× in column 2 and nil in column 3** — a weak single-column signal
  that does not separate the policies, and which compares implementations rather than
  policies in any case. The earlier ~74×/~2200× figures are withdrawn.
  See [`../harness/evidence/FINDING_moist_enthalpy_ledger_v1.md`](../harness/evidence/FINDING_moist_enthalpy_ledger_v1.md).

Provenance for the closed hardening line: [`RELEASE_ABI_V2_HARDENED.md`](RELEASE_ABI_V2_HARDENED.md),
[`PR1B_OPENMP_DIAGNOSTIC.md`](PR1B_OPENMP_DIAGNOSTIC.md). External deep review that motivated
this table: [`../wiki/sources/kdm6ad-deep-review-2026-07-15.md`](../wiki/sources/kdm6ad-deep-review-2026-07-15.md).
