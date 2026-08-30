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
| Weighting the interface transfer by layer air mass (Arm N) collapses the residual to roundoff | CONFIRMED | `FINDING_arm_n_closure_v1` |
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
| The i-seam: `2x2`/`4x1` differ from `np=1` in 77 of 197 fields, from a `delz` difference in owned cells, relative median 6.9e-07 | OPEN | `FINDING_second_decomposition_defect_v1`, `FINDING_np4_seam_is_rounding_v1` |
| Its ten-minute growth on the corrected binary is 77/77/75/106 fields (np=4 arm, `f54ef3c9`) | CONFIRMED | `RECERT_results_v1` (historical) |
| That growth is not distinguishable from a 1-ULP perturbation on the CORRECTED binary (the 1-ULP arm has not been re-run since the two CCN fixes) | UNMEASURED | `RECERT_results_v1` (historical) |
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
