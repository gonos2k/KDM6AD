# KDM6AD — capability status

Single source of truth for **what is implemented and validated today**, separate from the
chronological audit trail in the wiki/parity logs.

**`docs/c4_evidence_manifest.json` is an IMMUTABLE HISTORICAL SNAPSHOT** (owner §16-5).
It pins the producer and private-host executions **as they were at that closeout** —
`producer_commit a8cd83cd`, `main_commit abb470f1` — and is never updated in place.
Repointing its producer at a later commit would be false provenance: no later producer
generated those artifacts. Its lineage, and the digest that freezes it, are recorded in
`docs/c4_evidence_lineage.json`.

The authority for the **current** G3.3 research harness is `harness/evidence/SCIENCE_STATUS.md`
together with the experiment manifest each claim pins. A successor C4 package will be
published as a separate addendum carrying the snapshot's full digest as its parent, after
§16-6 and the two correctness items the owner named; C4 remains **HOLD** until then.

Legend: ✓ implemented & tested · partial · – not present · diag = diagnostic-only (not a
seedable AD output) · host = validated only on the private WRF/KIM-meso host (not public CI).

**Two green states, and they are not the same thing** (owner §7.2). `host/**` is
gitignored, so every test that compiles the pinned Fortran, generates the overlay, or
runs a driver **skips** in public CI:

| state | what a green means | where |
|---|---|---|
| `public_static_ci` | Python parsers, schema, macro placement, manifest/provenance contracts, C++ overlay structure | GitHub Actions |
| `private_host_execution` | pinned-Fortran compile, A/B/C non-invasiveness, and every raw numerical result quoted below | local host only, by committed evidence bundles |

A green badge therefore means the **static** contracts hold. It does not mean the
`mstep_i`, flux or closure numbers in this document were reproduced in CI — they were
not, and cannot be until the reference tree is reachable from a runner.

**Current status lives in [`../harness/evidence/SCIENCE_STATUS.md`](../harness/evidence/SCIENCE_STATUS.md)**,
with each result bounded by its pinned experiment manifest. The former
`CLAIMS.yaml` registry and its validation scheme are historical; they are not
an active executable gate. Older findings below retain experiment-specific
numbers and must be read with the current unit and measurement qualifications.

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
| conservative-interface-v1 | experimental | implemented | implemented (**scope: water-mass-conservative interface; NUMBER transport (nr) is reference-faithful, NOT certified column-number-conserving** — under the Registry dry-air mass basis [# kg-1], the column measure is rho_d*dz*nr; under the kernel PSD volume-concentration basis [# m-3], it is dz*nr. The host/kernel unit boundary remains OPEN. Reference-faithful number transfer uses thickness weighting; neither physical basis nor conservation is certified by inheritance. C4: host mp237/mp337; Gates A/C PASS; Gate D SS-short 237↔337 STRICT BITWISE post the merged C4-S1 `piacw` `pi_t` fix, PR #26; Gate B G1/G2/G3.1/G3.2/G3.4 PASS but **G3.3 legacy-ULP-envelope OPEN** (unchanged by the fix; closure via the G3.3-M mechanism-provenance gate, not the withdrawn relative-envelope); legacy 12h×np4 37↔137 recert **STRICT BITWISE PASS on all generated frames** (both runs fail-closed verified; 12 frames × 254 vars incl `Times` raw-bit identical — the fix did not perturb legacy f32 parity), **and terminal 12:00:00-state parity PASS** (dedicated exact-hourly re-run, 13 frames 00:00:00…12:00:00, 12:00 terminal frame raw-bit + `Times` exact). C4 HOLD until G3.3 attributed. See FREEZE_LIFT §Current-status.) | pending (C5) | no |

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
- Number transport uses thickness weighting while mass transport carries density.
  Under the **conditional dry-air mass basis**, the full applied interface residual is
  `rho_d,lower * dz_lower * dn_in - rho_d,upper * dz_upper * dn_out`.
  Its density-contrast and inflow/outflow-mismatch terms must both be retained;
  a density ratio alone is not a general creation rate or particle-mass change.
  The historical column-3 comparisons predicted ratios 1.0330 / 1.0319 / 1.0309
  and measured 1.0331 / 1.0296 / 1.0126 in that experiment. They do not establish
  a universal “3% per transfer” effect. The larger coarse-step endpoint differences
  remain separately attributed in the pinned findings.
  Applied transfer instrumentation and matched fixture closure are available;
  the real 10-minute WRF applied-transfer remeasurement and the host/kernel number
  unit contract remain OPEN. See
  [`FINDING_matched_number_closure_v1.md`](../harness/evidence/FINDING_matched_number_closure_v1.md)
  and [`SCIENCE_STATUS.md`](../harness/evidence/SCIENCE_STATUS.md).
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
  +0.41. **WITHDRAWN — the column-water orders this rested on are precision drift.**
  Turning the f64 instrument on the column budgets: total ρΔz column water varies
  **5.7e-3 / 7.0e-3 / 9.6e-3** relative across the chain at f32 but only
  **1.6e-6 / 2.5e-7 / 8.8e-7** at f64, and at f64 column 3's total is
  `1.352435e-01` at *every* member to seven figures while the species redistribute
  underneath. The f32 variation is ~10⁴× larger and is removed by precision, so
  `−5.860, +3.884, −1.017, +0.407` describe that drift, not a convergence rate.
  What survives: the **refinement-variable mismatch is confirmed at source level**
  (`dtcld/mstep` is what the sedimentation operator integrates, so an
  external-`dtcld` dyadic chain does not dyadically refine it) — that was never an
  inference from these orders. What is **refuted**: that a varying sub-step count
  prevents convergence — at f64 column 3's `ni` converges at first order across the
  *whole* chain (`+1.199, +0.980, +0.954, +0.967, +0.981, +0.990, +0.995`),
  including h = 100 → 25 where `mstep_i` runs 4 → 2 → 1. The analyzer now prints
  this caveat above the budget table on any f32 stream.
  See [`../harness/evidence/FINDING_column_water_orders_v1.md`](../harness/evidence/FINDING_column_water_orders_v1.md).
- **This fixture precipitates only at f32, which scopes every legacy-vs-conservative
  comparison built on it.** Total `rain` after 300 s is **4.8e-04 / 2.2e-02 /
  3.5e-02 mm at f32** against **2.0e-07 / ~0 / 0.0 at f64** — the condensate sits at
  the scheme's activation thresholds and single precision decides whether
  sedimentation reaches the ground. Three earlier observations collapse into this
  one: column water is conserved at f64 (nothing leaves); **legacy and conservative
  are bit-identical at f64 — 0 of 333 records, against 39 at f32 with max relative
  difference 8.656e-01, max_ulp 24325658** — produced by `g33_probe_read.diff`
  under the `variant` contract, which reports `bitwise_identical: true` at f64
  (an earlier "3.28" used the asymmetric `|a−b|/|a|`); and the moist-enthalpy
  **conservative advantage is 5.89× in
  column 2 at f32 and 1.00× at f64**, so it measures the two variants' response to a
  fixture where the two precisions enter **different precipitation active sets**,
  **not the interface's thermodynamics** — and "a cap event f32 noise creates" is
  itself withdrawn as ahead of the evidence (owner §6.2): which gate diverges first
  is not established. That reading
  is withdrawn; the f32 numbers remain valid *as statements about the f32 reference*,
  which is the operator being certified, but cannot be extrapolated to any case where
  precipitation is not threshold-marginal. **Norm (owner §6.4)**: the ledger now also
  reports `eta = |R|/(|dH|+|H_out|)` — the same residuals read **7.85% / 7.98% /
  4.19%** under `eta` against `3.8e-06 / 4.2e-04 / 1.3e-04` under `/H_start`, four
  orders apart, because `/H_start` divides a process-scale error by the column's
  whole background energy. At f64 `eta` is ~100% in both variants: with `H_out ≈ 0`
  the ledger reduces to `R = dH` and `eta = 1` **algebraically** — it restates
  "nothing left and the potential still moved" rather than adding information. The
  non-closure is **−42.09 / −21.19 / +443.74 J/m²** by column, identical in both
  variants; an earlier "~42 J/m² per column" generalised column 1 and is corrected.
  `eta` is a better norm, **not an acceptance criterion**: the one carrying process
  scale is `eta_phase = |R_H|/(Σ_p∫|L_p q̇_p|dt)`, whose terms are per-cell locals.
  See [`../harness/evidence/FINDING_fixture_precipitates_only_at_f32_v1.md`](../harness/evidence/FINDING_fixture_precipitates_only_at_f32_v1.md). Consequence: §9's obstacle is a
  **sweep-design** problem — but making `mstep` constant is **necessary and not
  sufficient**, and the "a chain over which `mstep` is constant would give column 3 a
  valid domain" that stood here is **withdrawn**. Measured: `mstep` reaches 1 at
  h = 12.5 s (col 2) and h = 6.25 s (col 3), while extending the chain to h = 0.39 s
  shows the successive differences **stop falling and start growing** below
  h = 3.125 s (`th` 1.46e-3 → 2.69e-3 → 6.41e-3; members bit-identical on re-run, so
  **not** nondeterminism — and the cause is now **DECIDED by precision scaling**:
  rebuilding the whole Fortran leg at f64 (`--f64`, with `--probe` as an f32 control
  arm that is bit-identical to the reference build) **removes the turnover
  entirely**. Domain max-norm `th` orders over h = 25 → 0.39 s are
  `+0.601, +1.032, +0.891, −0.874, −1.255, −0.567` at f32 against
  `+0.796, +0.875, +0.978, +1.040, +1.017, +1.007` at f64, and the smallest
  achievable difference falls **13.7× (th) / 114.7× (qv)**. **Grade corrected (owner P0-5)**: what is
  confirmed is that the turnover is **precision-dependent**, not that accumulated
  roundoff is the cause. The earlier argument — "active-set switching is
  state-dependent, not ε-dependent" — is **wrong**: the active set is `1[g(x_ε)>0]`
  and the state itself depends on ε, and the counterexample is in this same branch
  (this fixture precipitates at f32 and not at f64). Grades: turnover not
  nondeterminism **confirmed**; turnover precision-dependent **confirmed**;
  accumulated arithmetic roundoff **strong candidate**; active-set change
  **refuted as excluded** — it is live; cause **HOLD**. Separating
  `E = E_trunc(h) + E_arith(ε) + E_branch(x_ε)` needs arms that move one at a time. Caveats: promotion changes the whole operator, so this
  discriminates against precision-independent explanations rather than isolating
  roundoff absolutely, and the f64 build is an instrument, not the reference —
  it produces no decision evidence. **Scope**: this is the `th`/`qv` domain max-norm.
  It does **not** generalise — column 1's water anomaly at h = 1.5625 s survives f64
  with the same shape scaled ~2370×, so that one is precision-INdependent and remains
  unexplained). Since an order needs three members,
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
  column 3 where the main chain needs **h = 6.25 s**. `ni` column number shows no
  turnover (successive differences fall monotonically 1.76e8 → 9.72e5, relative
  difference ~1e-2 against `th`'s ~5e-6), so inside that window it has **five
  successive orders — `+1.461, +0.863, +1.121, +1.029, +1.052`**. Grade (owner
  §6.3): **first-order-consistent and empirically stable over five estimates, NOT
  branch-certified** — "clean" is withdrawn, because the process gates, number caps,
  cleanup and nucleation/aggregation branches and the active-cell universe were not
  verified constant across these levels. Column *water* still gets none, now for a
  stated reason: it contains qr/qs/qg and so inherits the **main** chain's h ≤ 6.25
  against a noise floor at h ≥ 3.125. This explains what the previous row recorded
  as an unexplained positive result. **The surface number flux is now emitted too**
  (`falln(i,kts,1:2)` + den/delz/dtcld as operands), validated at the same site
  against `bottom_fall_qr`: mean rain-drop mass 5.4–8.6e-10 kg (0.10–0.12 mm),
  consistent across columns. It measures that **every column loses all its rain
  number while the surface accounts for only 1.4–5.8%**. Calling the remaining
  94–99% "microphysical sinks" is **withdrawn** (owner §5.1): what is isolated is
  everything that is *not* surface outflow, which mixes aggregation,
  autoconversion, nucleation, freezing/melting, cleanup, projection, the measure
  mismatch and inter-phase redistribution — and for `ni` the surface flux is 1.38×
  and 3.46× `|ΔN|`, so a pure-sink decomposition has the wrong sign structure there.
  **Still not a closure**: the correct form is `ΔN + F − Σ_p∫S_p dt = R_numerical`
  and every `S_p` is a per-cell local. A **sedimentation-only fixture** would decide
  the transport part alone and has not been run.
  Both emissions sit under their own `KDM6_G33_NUMBER_DUMP`, never defined by
  `fortran_build.sh` — the decision-path stream is **bit-identical** to before, and
  the instrumented run is **bit-identical** to the plain build.
  See [`../harness/evidence/FINDING_two_sedimentation_chains_v1.md`](../harness/evidence/FINDING_two_sedimentation_chains_v1.md).
- **Historical number-budget fixture result, conditional on a dry-air mass basis.**
  The pinned reference moves mass with density weighting and number with thickness
  weighting. If `nrs` denotes #/kg dry air, use `rho_d*dz*nrs`; if it denotes
  #/m³, use `dz*nrs`. Registry declarations and PSD usage disagree, so neither
  this fixture nor its WDM6 inheritance settles the physical unit contract.
  The original endpoint recovery applies only to `mstep == 1` and excludes
  cap-dominated calls. Its density-ratio argument is valid only when the actual
  outgoing and incoming thickness-weighted transfers match. It is not a general
  whole-residual formula. Reported fixture percentages below retain their pinned
  scope, conditional measure, and cap exclusions; they are not operational WRF
  particle-creation measurements.
  **Closure, on emitted data only** (owner priority-3): the segment
  `outer_pre_sed..outer_post_sed` is F:1189-1340 — both sedimentation sub-cycles and
  nothing else — so it isolates transport temporally and **a sources-off fixture is
  not needed**. With every term read from the stream and no recursion anywhere,
  `[X(post)−X(pre)] + F_surface` gives **qr +0.0002% / −0.0000% / +0.0000%** against
  **`ni` +6.26%** and **`nr` +13.68%** of the surface outflow: **mass closes to f32
  roundoff, number does not.** Unlike the recovered-transfer form, nothing in this
  arithmetic forces the mass row to vanish, so it is a real control. Cap-bound calls
  are excluded per species (detected as emitted-vs-recovered disagreement).
  The number stream is now a bracketed protocol — the driver emits
  `G33N CALL_BEGIN/END` per external call, since the kernel's own `loop` resets to 1
  every call — with a strict parser (bracket completeness, call-id contiguity, exact
  per-column record universe, operand positivity/finiteness) and a JSON analysis
  emitted from the same call that prints the table.
  See [`../harness/evidence/FINDING_number_transport_creation_v1.md`](../harness/evidence/FINDING_number_transport_creation_v1.md).
- **The refinement evidence path is fail-closed and produced atomically** (owner
  P0-1/P0-2/P0-3, priority 2). Convergence orders were computed from the FILENAME's
  `N` on the assumption `dtcld = 300/N`; the driver disproves it — `N = 1,2,3` run
  `dtcld = 100, 150, 100 s`, so N-ordering is not step-ordering, `N=2` is *coarser*
  than `N=1`, and `N=1`/`N=3` ran the **same** step. Every `300/N` is gone: pairing,
  labels, the error-series keys and the "finest" member all come from the `dtcld` the
  stream reports, a member reporting none is refused, and a repeated step is refused
  where an order is taken (the series is keyed by step and two members at one step
  collide silently) while still being *readable*, since the N=1/N=3 policy control
  runs one step twice deliberately. The manifest binds each **filename** to its
  stream (`nsplit` and mode), runs the cross-member checks before claiming a bundle
  is reproducible, orders `is_refinement_chain` by actual step, and refuses
  provenance whose digests describe a different build. Provenance now binds **all
  seven compiled sources, `f951`, the link command and the executable** — previously
  only the module and fixture, so a change to `libmassv`/`module_model_constants`/
  `module_mp_radar`/the stub/the driver was invisible (`host/**` is gitignored, so
  `repo_commit` cannot see them) — and records the **pinned** module separately from
  the **compiled** one, which differs under the instrumentation overlay. The parser
  additionally refuses rho-without-delz, an INITIAL state over different cells (not
  merely the same count), ragged level sets and a PREC set that is not exactly
  species 1/2/3 over the state's columns. `g33_refine_experiment.py` now does
  build → run → strict-parse → cross-check → manifest → **atomic publish** in one
  command, so a failure leaves the previous bundle untouched instead of a
  half-replaced one. The analyzer now prints each flip's share of
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
  See [`../harness/evidence/historical/FINDING_moist_enthalpy_ledger_v1.md`](../harness/evidence/historical/FINDING_moist_enthalpy_ledger_v1.md).

Provenance for the closed hardening line: [`RELEASE_ABI_V2_HARDENED.md`](RELEASE_ABI_V2_HARDENED.md),
[`PR1B_OPENMP_DIAGNOSTIC.md`](PR1B_OPENMP_DIAGNOSTIC.md). External deep review that motivated
this table: [`../wiki/sources/kdm6ad-deep-review-2026-07-15.md`](../wiki/sources/kdm6ad-deep-review-2026-07-15.md).
