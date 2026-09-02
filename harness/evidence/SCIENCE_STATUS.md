# Science status

One file. Four words: CONFIRMED, OPEN, REFUTED, UNMEASURED -- one statement
per row, one word per statement, and no release or adoption decisions here. A
line moves only when a measurement moves it. History is in `evidence/historical/`; the findings
still cited here are in `evidence/`.

Standard commands:

    python3 -m pytest harness/tests            # what CI runs
    python3 -m pytest harness/tests --local    # + the Fortran / bundle / real-column leg

Deployed WRF binary for MPI runs: `6797945d` (kernel `9354141b`, corrected
`share/module_bc.F`, and `start_em.F` corrected at the CCN loop bound,
2026-09-02). It produces output BITWISE IDENTICAL to the previous `f54ef3c9`
on both `np=1` and `4x1`, 197 fields, every frame to 60 s, so every result
recorded against `f54ef3c9` carries over unchanged; `f54ef3c9` is the
historical campaign reference. The campaign binary `a40bd80f` is kept beside
them.

## Number transport

| statement | status | where |
|---|---|---|
| Number sedimentation transfers a mixing ratio by thickness ratio only; the rho*dz column measure is not conserved | CONFIRMED | `FINDING_number_transport_creation_v1` |
| The conservative variant carries the same number defect, identical to the last digit (main/nr 15.00/13.34/11.84 %) | CONFIRMED | `FINDING_conservative_number_defect_v1` |
| Arm N weights the interface transfer by MOIST layer air mass and closes the moist/operator number ledger on the tested first-call matrix | CONFIRMED | `FINDING_arm_n_closure_v1` |
| Under vertical moisture gradients Arm N leaves a dry-air physical remainder; over 23 real columns the actual-`XFER` median is 2.0664 % of the legacy defect | CONFIRMED | `FINDING_real_column_batch_v1`, `FINDING_moisture_gradient_basis_v1` |
| Arm `N_d` closes the first-call dry-air physical number ledger on the moisture-gradient fixture | CONFIRMED | `FINDING_arm_nd_closure_v1` |
| `nmass_dry_window` closes the fixed-forcing 12-call dry ledger on the one column that keeps transporting after call 1 | CONFIRMED | `FINDING_arm_nd_window_v1` |
| The defect's sign and size follow the layer-air-mass gradient | CONFIRMED | `FINDING_density_falsification_v1`, `FINDING_ice_density_matrix_v1` |
| `nr` is per kg of dry air; the physical column measure is sum rho_d*dz*nr | CONFIRMED | `FINDING_number_mass_basis_v1` |
| Conservative `nr`/`ni` sedimentation creates number on density increase | CONFIRMED | `FINDING_number_transport_creation_v1`; the fix is frozen pending an owner freeze-lift, which is a release decision, not a status |

## Graupel melting

| statement | status | where |
|---|---|---|
| `rhox` is computed only under `qg > qcrmin .or. brs > brs_min` (F:3669) while melt asks `qg > 0.` (F:1400); `brs += pgmlt/rhox` divides by zero | CONFIRMED | source, `FINDING_melt_closure_measured_v1` |
| Float64 residual of the three melts, per level | CONFIRMED | `FINDING_melt_closure_measured_v1` |
| Whether trace graupel (1e-20..1e-43 kg/kg) should melt at all -- g1 skips, g3/g4/g5 zero it | OPEN | owner decision; `FINDING_melt_arm_g5_and_number_policy_v1` |
| On a partial melt inside the window `g4` and `g5` differ substantively, not at rounding: over 200,000 f32 draws log-uniform in the window, `g4` floors to zero -- leaving `qg > 0` with `bg = 0` -- in 64.3%, and where it stays positive the apparent density drifts a median 32%, while `g5` holds that density to 2.5e-08 relative and never reaches zero while mass remains | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| Whether any model column reaches that branch -- the fixture's window melts are all complete, and the sampling above is uniform in log over the window, not the model's distribution | UNMEASURED | `FINDING_melt_arm_g5_and_number_policy_v1` |

## CCN initialisation

| statement | status | where |
|---|---|---|
| Two sites: kernel memory-bounds sweep (`module_mp_kdm6.F:311`) seeds the divergence; `flow_dep_bdy_qnn` (transposed `dz8w`, wrong `xland` extent, slab `z_sum`) crashes | CONFIRMED | `FINDING_segv_localised_to_flow_dep_bdy_qnn_v1` |
| With both fixed, `np=1` vs `1x2`/`1x3`/`1x4` is 197 of 197 fields byte-equal at 20 s; `1x4` 0 of 197 at 1 min | CONFIRMED | `RECERT_results_v1` (historical), runs on `f54ef3c9` |
| The kernel block still overwrites valid external `QNCCN` (no `ccn_max_val` guard; `start_em.F` has one) | CONFIRMED | `FINDING_ccn_destroys_valid_input_v1` |
| One-time-initialisation reference (Arm C) against the corrected block | UNMEASURED | needs a variant binary; owner-host only |
| `start_em.F:1786` reads `phb(i,kte+1,j)` at the last iteration of a loop bounded by `kte`, one past the declared top. CORRECTED 2026-09-02 to `DO k=kts,kte-1`, no padding assignment; `start_em.F` `5090ca10`, `wrf.exe` `6797945d` | CONFIRMED | `FINDING_ccn_init_reads_past_the_model_top_v1` |
| The physical mass levels 1..`kte-1` are computed from in-bounds reads and are unaffected; the out-of-bounds value lands in the top ALLOCATED slot `k = kte` | CONFIRMED | `FINDING_ccn_init_reads_past_the_model_top_v1` |
| Every `p_qnn`-specific reader found in the forward path stops at `kde-1` -- `flow_dep_bdy_qnn` loops to `ktf = kde-1` and `microphysics_driver` is called with `KTE = min(k_end, kde-1)` -- so no padding policy is needed for the correction. `qnn` is a member of the generic `scalar` container, so a literal `p_qnn` search is not an exhaustive consumer proof; the generic scalar-update paths inspected also stop at `kde-1` | CONFIRMED | `FINDING_ccn_init_reads_past_the_model_top_v1` |
| A decomposition difference persists in a build that corrects the CCN loop AND enables bounds checking, so the CCN defect is not necessary for one | CONFIRMED | `FINDING_ccn_init_reads_past_the_model_top_v1` |
| The CCN defect contributes nothing to the production seam: corrected alone on production flags, `np=1` against `4x1` is 0/28/71/77, production's exactly | CONFIRMED | `FINDING_ccn_init_reads_past_the_model_top_v1` |

## MPI decomposition

Detail lives in the findings; this table carries what is true now.

| statement | status | where |
|---|---|---|
| On the production flags an i cut (`2x2`, `4x1`) differs from `np=1` in 77 of 197 fields at one minute, while a pure j cut (`1x2`, `1x3`, `1x4`) is raw-word identical at every rank count | CONFIRMED | `FINDING_second_decomposition_defect_v1`, `FINDING_seam_is_i_specific_v1` |
| The i-cut difference is banded on the i patch boundaries, one band per boundary, and its envelope edge advances at 1.1-1.6 km/s -- numerical domain of dependence, not a signal in the fluid | CONFIRMED | `FINDING_i_seam_is_banded_at_the_patch_boundary_v1` |
| Cutting i also perturbs the EASTERN lateral-boundary zone and not the western one; `relax_bdy_dry` is not its first producer, and the band going clean under the alternative build is NOT evidence about the dynamics, because that build also recompiled `module_bc_em` | CONFIRMED | `FINDING_i_seam_is_banded_at_the_patch_boundary_v1`, `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| `HALO_EM_A` width-1 transfers match the owner bit for bit: 12 exchanged fields x 3 INTERIOR i boundaries x both directions. The probe classifies ownership as `ips <= i <= MIN(ipe, ide-1)` for every field regardless of stagger, which is the right partition at an interior boundary for x- and y-staggered fields too -- WRF gives them the same `ips..ipe` patch and only one extra face at the DOMAIN edge, which this bound drops and this claim does not cover | CONFIRMED | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| The stale-`u`/`mu`-halo account of the stage-2 `ww` difference -- the halo columns `calc_ww_cp` reads at each patch's last owned mass column (i = 60, 118, 177) are bitwise identical to `np=1` in `u_2`, `mu_2`, `mub` and `msfuy` | REFUTED | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| Three alternative builds -- both flags, `-fno-tree-vectorize` alone, `-ffp-contract=off` alone -- each remove the ENTIRE one-minute difference: 0 of 197 fields at 0/20/40/60 s, against 0/28/71/77 for production on the same case, frames and comparator | CONFIRMED | `FINDING_i_seam_is_code_generation_v1` |
| The bounds-checked build's difference carries the same structural SIGNATURE as production -- identical differing-field sets at 20 and 40 s, Jaccard 0.949 at 60 s, same `PH` band geometry -- while its cell masks, signs and magnitudes are uncompared | CONFIRMED | `FINDING_ccn_init_reads_past_the_model_top_v1` |
| The response is conjunctive: the seam appears only when vectorisation and contraction are BOTH permitted, and forbidding either is sufficient to remove it. In the standard +-1 factorial both main effects and the interaction are equal and non-zero, so "an interaction and not a main effect" -- an earlier wording -- is coding-dependent and withdrawn | CONFIRMED | `FINDING_i_seam_is_code_generation_v1` |
| The `-fno-tree-vectorize` arm starts from the production initial state BIT FOR BIT (0 of 197 fields at frame 0, compared as raw uint32 words with no signed-zero cells; the 197 time-varying output fields only, not static, integer or halo state) and still removes the seam, while itself changing the arithmetic (78 of 197 fields by one minute), so the removal is not an artefact of a moved initial state | CONFIRMED | `FINDING_i_seam_is_code_generation_v1` |
| Three tested object sets are each insufficient to remove the seam: `{small_step_em, solve_em, madwrf}` 74, the nine-object `big_step_utilities` closure 75, those nine plus `advect_em` 74, against production's 77 | CONFIRMED | `FINDING_i_seam_is_code_generation_v1` |
| Their union, about 12 objects, removes it: 0 of 197 at every frame. Each arm leaves the initial state unchanged (0 of 197 at frame 0) and is demonstrably active | CONFIRMED | `FINDING_i_seam_is_code_generation_v1` |
| The minimal sufficient object set, and whether the first arithmetic source is a single place -- the 32 were not tried one at a time and no arm was one object | UNMEASURED | `FINDING_i_seam_is_code_generation_v1` |
| The deployed build does not reproduce bitwise across i decompositions | CONFIRMED | `FINDING_i_seam_is_code_generation_v1` |
| Under the alternative build the sampled non-owned records differ from the single-patch reference while the sampled owned outputs are raw-word identical; whether those values are read, overwritten before an anchor, or observable under the PRODUCTION flags is a separate question, and a null under one build does not transfer to another | UNMEASURED | `FINDING_i_seam_is_code_generation_v1` |
| Every interior i patch boundary carries a band: one for `2x1`, two for `3x1`, four for `5x1`, plus the eastern zone in each, on the production binary | CONFIRMED | `FINDING_i_seam_is_code_generation_v1` |
| The `i` loop that computes `divv` and reads `i+1` across the patch boundary is compiled as a vectorisation-factor-4 main loop followed by an `epilog loop required` at factor 2, with the epilogue peel set to vf/2 because the trip count is unknown at compile time -- read from `-fdump-tree-vect-details`, which names it, rather than from `-fopt-info`, which does not | CONFIRMED | `FINDING_i_seam_is_code_generation_v1` |
| The mechanism: whether the difference is MADE in that remainder (the structure is now measured, the attribution is not), whether the `i`-loop trip count predicts which boundary the difference is written at FIRST -- `nproc_x` = 2, 3, 5 do not decide it, since none yields a 58 or 59 and almost every patch in them shares one trip count, and forecast output cannot test it because the 58-trip boundary at `4x1` carries a band even though it carries no stage-2 `ww` difference, and whether the sensitivity is ordinary rounding or exposes a source or extent defect -- the vectorisation report has been read; with the CCN read corrected, a bounds-checked build ran both decompositions for the whole minute with ZERO violations on every rank and the seam was still present (0/28/71/75 of 197), so no executed subscript violation that the enabled gfortran checks can see is required for the difference; that weakens an array-index cause without refuting it, since those checks miss uninitialised in-bounds reads, aliasing, assumed-size dimensions, non-Fortran code and untaken branches; no disassembly has been read | OPEN | `FINDING_i_seam_is_code_generation_v1` |
| Whether every `calc_ww_cp` operand agrees across decompositions: `v_2`, `msftx` and `msfvx_inv` are dumped by no group, so only the x-side operands are measured | UNMEASURED | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| The i-cut difference grows to 77/77/75/106 fields over ten minutes on the corrected binary; whether that growth is distinguishable from a 1-ULP perturbation on `f54ef3c9` is not measured, and the three 1-ULP runs on disk used other binaries or record none | CONFIRMED | `RECERT_results_v1` (historical) |
| The forecast-skill effect of the seam | UNMEASURED | `FINDING_i_seam_is_code_generation_v1` |
| Same-decomposition runs repeat bit-identically | CONFIRMED | `FINDING_mpi_repeatability_v1` |
| `ncmin` is a scalar overwritten in the column loop; tile decomposition changes prognostic components, and Arm L (`ncmin` per cell) removes none of the decomposition difference | CONFIRMED | `FINDING_ncmin_scalar_vs_percell`, `FINDING_arm_l_mpi_null_v1` |

## Ice number

| statement | status | where |
|---|---|---|
| Column 3's ni number is first-order-consistent over five estimates (consistency of the estimates, not a branch certificate) | CONFIRMED | `FINDING_two_sedimentation_chains_v1` |
| The ice-chain missing term is the post-update-reservoir inflow cap | CONFIRMED | `FINDING_ice_chain_missing_term_v1` |
| A conversion-free ice fixture | UNMEASURED | no fixture exists |

## Fixture and protocol facts still relied on

| statement | status | where |
|---|---|---|
| The refinement variable is dtcld/mstep; orders are taken against the reported dtcld | CONFIRMED | `FINDING_two_sedimentation_chains_v1`, `FINDING_refinement_provenance_v1` |
| legacy and conservative are bit-identical at f64 and differ in 39 records at f32; the fixture precipitates only at f32 | CONFIRMED | `FINDING_fixture_precipitates_only_at_f32_v1` |
| The f32 fine-step turnover is precision-dependent | OPEN | `FINDING_refinement_noise_floor_v1` |
| Both column measures (rho_m*dz operator, rho_d*dz physical) reported on every closure row | CONFIRMED | `FINDING_dual_ledger_v1`, `FINDING_water_enthalpy_dual_basis_v1` |
| The dt=300 wrapper boundary decides the four-case verdict | OPEN | `g33m_dt300_wrapper_boundary_result.json` (the run was inconclusive) |
| `QNCLOUD` negative cells (~1e-9..1e-2) | UNMEASURED | source undiagnosed |

## Not carried forward

The claim registry (`CLAIMS.yaml`, 48 claims, 27 pinned findings), the evidence
chain walker, the pin verifier and the owner-adjudication layer are in
`historical/`. Their withdrawn and superseded entries are recorded there; their
active entries are the rows above.
