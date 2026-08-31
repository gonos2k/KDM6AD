# Science status

One file. Four words: CONFIRMED, OPEN, REFUTED, UNMEASURED -- one statement
per row, one word per statement, and no release or adoption decisions here. A
line moves only when a measurement moves it. History is in `evidence/historical/`; the findings
still cited here are in `evidence/`.

Standard commands:

    python3 -m pytest harness/tests            # what CI runs
    python3 -m pytest harness/tests --local    # + the Fortran / bundle / real-column leg

Deployed WRF binary for MPI runs: `f54ef3c9` (kernel `9354141b`, corrected
`share/module_bc.F`). The campaign binary `a40bd80f` is kept beside it.

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
| g5's partial-melt branch (window-only proportional volume) | UNMEASURED | never reached on the fixture |

## CCN initialisation

| statement | status | where |
|---|---|---|
| Two sites: kernel memory-bounds sweep (`module_mp_kdm6.F:311`) seeds the divergence; `flow_dep_bdy_qnn` (transposed `dz8w`, wrong `xland` extent, slab `z_sum`) crashes | CONFIRMED | `FINDING_segv_localised_to_flow_dep_bdy_qnn_v1` |
| With both fixed, `np=1` vs `1x2`/`1x3`/`1x4` is 197 of 197 fields byte-equal at 20 s; `1x4` 0 of 197 at 1 min | CONFIRMED | `RECERT_results_v1` (historical), runs on `f54ef3c9` |
| The kernel block still overwrites valid external `QNCCN` (no `ccn_max_val` guard; `start_em.F` has one) | CONFIRMED | `FINDING_ccn_destroys_valid_input_v1` |
| One-time-initialisation reference (Arm C) against the corrected block | UNMEASURED | needs a variant binary; owner-host only |

## MPI decomposition

| statement | status | where |
|---|---|---|
| A decomposition that cuts i (`2x2`, `4x1`) differs from `np=1` in 77 of 197 fields at one minute | CONFIRMED | `FINDING_second_decomposition_defect_v1`, `FINDING_seam_is_i_specific_v1` |
| A decomposition that cuts only j (`1x2`, `1x3`, `1x4`) is bit-identical to `np=1` -- raw-word comparison, 0 of 197 fields differing in any bit -- so the difference is specific to splitting i. Its MECHANISM is now measured: `i` is the inner loop and `j` the outer, so only an i cut changes inner trip counts | CONFIRMED | `FINDING_seam_is_i_specific_v1`, `FINDING_i_seam_is_code_generation_v1` |
| The difference is derived from `PH` with `PHB` bit-identical, rounding-scale in the median (6.9e-07) and not in the tail | CONFIRMED | `FINDING_np4_seam_is_rounding_v1` |
| The i-cut difference is banded on the i patch boundaries -- one band per boundary, peaking within 2 columns of it for `PH` and `T` -- so it is local and not a changed global reduction | CONFIRMED | `FINDING_i_seam_is_banded_at_the_patch_boundary_v1` |
| Cutting i also perturbs the EASTERN lateral-boundary zone (`spec_bdy_width=5`) and not the western one, in a band that sits under no patch boundary and is kept a separate source family from the interior bands | CONFIRMED | `FINDING_i_seam_is_banded_at_the_patch_boundary_v1` |
| After one 20 s step the exact-difference support spans 14-20 i columns around each interior i patch boundary; from step 1 to 3 that envelope widens by 9-13 columns per step while the RELATIVE HALF-PEAK core (columns whose per-column max abs diff is at least half that step's peak) stays within 1-6 columns and does not widen. This is a half-peak SUPPORT, not an energy concentration: a boundary peak that grows faster than its surroundings narrows it too. Whether the difference ENERGY stays localized is UNMEASURED (needs the L2 widths) | CONFIRMED | `FINDING_i_seam_is_banded_at_the_patch_boundary_v1` |
| The envelope's edge advances at 1.1-1.6 km/s, 3.5-4.5x the sound speed, so it is numerical domain of dependence and not a signal in the fluid | CONFIRMED | `FINDING_i_seam_is_banded_at_the_patch_boundary_v1` |
| The first owned-cell difference inside the step is `ww` after `rk_step_prep` | **RETRACTED** -- true of the production BUILD, not of the model. Rebuilt with `-ffp-contract=off -fno-tree-vectorize` and nothing else changed, `ww` is identical at every stage | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| Rebuilt with `-ffp-contract=off -fno-tree-vectorize` (both arms from binary `f15d07a1`), the `ww` difference is ABSENT at stages 2, 31, 32 and `ph_tend` is ABSENT at stage 5; stages 0, 1, 2, 31, 32, 4 clean and the first difference moves to stage 5, `rk_tendency` | CONFIRMED | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| The `ww` difference was therefore produced by HOW the expression was evaluated, not by what it read: the operands were measured identical on the production build and no compiler flag can equate differing operands | CONFIRMED (two-sided: probe5 inputs, probe6 outputs) | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| "Why `ww` differs at 59 and 176 but not 117" has no answer in the physics -- it was never a property of the boundary | RESOLVED (dissolved by the above) | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| `HALO_EM_A` delivers correctly for the width it declares: after the exchange, ALL 12 exchanged fields at ALL 3 interior i boundaries in BOTH directions -- 72 comparisons -- match the owner bit for bit; columns beyond width 1 are stale by design. This says the exchange is correct, NOT that it sits in the right place | CONFIRMED | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| `relax_bdy_dry` is not the FIRST producer of the eastern-zone difference: the columns are already in the `rk_tendency` outputs one stage earlier. Whether the band is independent of boundary handling ALTOGETHER (`set_phys_bc`, boundary-aware stencils in `rk_tendency`, the specified-boundary input) is UNMEASURED | CONFIRMED-WITH-SCOPE | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| The source shows `calc_ww_cp` builds its OWN local `muu` from `mu` -- NOT the `grid%muu` that `HALO_EM_A` moves -- and reads `u(i+1)`/`mu(i+1)` past the last owned mass column, while nothing exchanges `u`, `v` or `mu` between the RK-stage entry (L573) and the call (L652) | CONFIRMED (source reading, not a run) | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| The source shows the same divergence reads `muv(i,j+1)`/`v(i,j+1)` as the exact mirror of its `i+1` term, so an unexchanged-halo read is symmetric in i and j and CANNOT alone explain the j-cut null | CONFIRMED (source reading, not a run) | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| The halo columns `calc_ww_cp` reads at each patch's last owned mass column (i = 60, 118, 177) are BITWISE IDENTICAL to `np=1` in `u_2`, `mu_2`, `mub` and `msfuy`, at all three boundaries, at stages 0 and 1. The model carries those fields correct to halo width 3; the columns that differ lie beyond it and differ in the TIME-INVARIANT `mub`/`msfuy` too, so they are memory never written rather than stale dynamics | CONFIRMED | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| The unexchanged-`u`/`mu`-halo account of the `ww` difference is therefore REFUTED: the inputs the stencil reads are current and the output is not | REFUTED | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| `ww` differs at the last owned mass column of the patches whose `i` loop runs 59 trips (0 and 2) and not at those running 58 (1 and 3), 4 of 4 | CONFIRMED AS A CLASS, not as a predictor: the no-contraction rebuild shows the difference is evaluation, and a trip count selects the vector body and remainder; WHICH boundaries differ has not been tested at another `nproc_x`. A prediction is now REGISTERED before that run (patches with equal trip counts must behave alike; 58 must not differ, 59 must), needing no rebuild since `f54ef3c9` is restored | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| With ALL 30 `dyn_em` objects built `-ffp-contract=off -fno-tree-vectorize` and nothing else changed, `np=1` and `4x1` agree on EVERY instrumented point of the first dynamics step: 0 differing of 141,214,320 f32 words over 14 stages and 16,800 (field, column) comparisons | CONFIRMED | `FINDING_i_seam_is_code_generation_v1` |
| The i-cut seam is therefore decomposition-dependent CODE GENERATION -- not halo exchange, not stencil reach, not the lateral-boundary update. `i` is the INNER loop, so cutting i changes trip counts and selects a different vector body and remainder for identical operands; cutting j changes only the OUTER loop's extent | CONFIRMED (this case, one time step, first RK stage, `4x1`, the dumped field set) | `FINDING_i_seam_is_code_generation_v1` |
| That the zero is a result and not a failed read | CONFIRMED by three controls: the coverage fail-close passes; `halo-vs-reference` returns 260 differing rows on the SAME dumps; and the same decomposition across builds differs in 45 (probe5 vs probe6) and 97 (probe5 vs probe7) rows, 120 columns wide | `FINDING_i_seam_is_code_generation_v1` |
| That "not a defect" means "harmless" | NO -- a 1-ULP seam still seeds the later divergence, and the ten-minute growth to 77/77/75/106 fields is downstream and NOT measured here | `FINDING_i_seam_is_code_generation_v1` |
| That anything about the DEPLOYED model's numbers changes | NO -- `8bd8cdbf` is not `f54ef3c9`, and it differs from production at stage 0 because `start_em` is in the rebuilt set | `FINDING_i_seam_is_code_generation_v1` |
| The stage-5 `rk_tendency` difference survives the PARTIAL no-contraction build only because `module_advect_em.F` was outside its rebuilt object set; with that object included it is gone too | RESOLVED | `FINDING_i_seam_is_code_generation_v1` |
| Whether the y half of the same expression agrees: `v_2` is dumped by NO group, and neither are `msftx` and `msfvx_inv` | UNMEASURED | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| Whether any stencil reads the exchanged fields beyond halo width 1 without a wider exchange first | UNMEASURED | `FINDING_i_seam_first_write_is_rk_step_prep_v1` |
| The i-cut difference grows to 77/77/75/106 fields over ten minutes on the corrected binary (np=4 arm, `f54ef3c9`) | CONFIRMED | `RECERT_results_v1` (historical) |
| That ten-minute growth is not distinguishable from a 1-ULP perturbation on the CORRECTED binary (the 1-ULP arm has not been re-run since the two CCN fixes) | UNMEASURED | `RECERT_results_v1` (historical) |
| Same-decomposition runs repeat bit-identically | CONFIRMED | `FINDING_mpi_repeatability_v1` |
| `ncmin` is a scalar overwritten in the column loop; tile decomposition changes prognostic components | CONFIRMED | `FINDING_ncmin_scalar_vs_percell` |
| Arm L (`ncmin` per cell) removes none of the decomposition difference -- a null about `ncmin`, not about the seam | CONFIRMED | `FINDING_arm_l_mpi_null_v1` |

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
