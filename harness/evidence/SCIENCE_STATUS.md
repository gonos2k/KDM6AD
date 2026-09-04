# Science status

One file. Four words: CONFIRMED, OPEN, REFUTED, UNMEASURED -- one statement
per row, one word per statement, and no release or adoption decisions here. A
line moves when a measurement, source check or counterexample changes its support.
History is in `evidence/historical/`; the findings still cited here are in `evidence/`.

Standard commands:

    python3 -m pytest harness/tests            # what CI runs
    python3 -m pytest harness/tests --local    # + the Fortran / bundle / real-column leg

Deployed WRF binary for MPI runs: `6797945d` (kernel `9354141b`, corrected
`share/module_bc.F`, and `start_em.F` corrected at the CCN loop bound,
2026-09-02). It is raw-word identical to the previous `f54ef3c9` for the
sampled `np=1` and `4x1` 197-field outputs through 60 s, so the ONE-MINUTE
results derived from those outputs carry over. Everything else -- other
decompositions, the ten-minute runs, other cases, the stage dumps, the 1-ULP arm
-- stays attributed to the binary it was measured under, because it was not
re-measured. `f54ef3c9` is the historical campaign reference and the campaign
binary `a40bd80f` is kept beside them.

## Number transport

Number-unit contract (review of main `2638fb2`, 2026-09-05): the host Registry
and dynamics suggest `n_d [# kg_d^-1]`, while the kernel slope relation requires
`N [# m^-3]`; no density conversion connects them. Which side to correct is
**OPEN**. Conditional identities are `N=rho_d*n_d`, physical column number
`sum rho_d*dz*n_d` for the host interpretation and `sum dz*N` for the kernel
interpretation. Neither inheritance from WDM6 nor closure of one diagnostic
ledger decides this contract. The existing analysis names `operator` and
`physical` select moist and dry density weights respectively; for number,
`physical` is conditional on the per-dry-kg interpretation. Historical measured
ledger values below retain their stated weights and fixture scopes.

| statement | status | where |
|---|---|---|
| Legacy number sedimentation uses thickness ratios and separate departure/arrival caps; the tested rho*dz ledger does not close. Its physical meaning depends on the unresolved number-unit contract | CONFIRMED | `FINDING_number_transport_creation_v1` |
| The conservative variant carries the same number defect, identical to the last digit (main/nr 15.00/13.34/11.84 %) | CONFIRMED | `FINDING_conservative_number_defect_v1` |
| Arm N weights the interface transfer by MOIST layer air mass and closes the moist/operator number ledger on the tested first-call matrix | CONFIRMED | `FINDING_arm_n_closure_v1` |
| Under vertical moisture gradients Arm N leaves a dry-density-weighted remainder; over 23 real columns the actual-`XFER` median is 2.0664 % of the legacy residual on that measure | CONFIRMED | `FINDING_real_column_batch_v1`, `FINDING_moisture_gradient_basis_v1` |
| Arm `N_d` closes the first-call dry-density-weighted number ledger on the moisture-gradient fixture | CONFIRMED | `FINDING_arm_nd_closure_v1` |
| `nmass_dry_window` closes the fixed-forcing 12-call dry ledger on the one column that keeps transporting after call 1 | CONFIRMED | `FINDING_arm_nd_window_v1` |
| The defect's sign and size follow the layer-air-mass gradient | CONFIRMED | `FINDING_density_falsification_v1`, `FINDING_ice_density_matrix_v1` |
| Registry declares number per kg and the host interprets mixing ratios per dry-air kg; the kernel slope equation instead requires m^-3, with no boundary conversion | CONFIRMED | `FINDING_number_mass_basis_v1` |
| The tested conservative `nr`/`ni` fixture has a positive density-weighted residual under a downward density increase; this is not a claim about every capped transfer or a resolved physical unit | CONFIRMED | `FINDING_number_transport_creation_v1`; the fix is frozen pending an owner freeze-lift, which is a release decision, not a status |

## Graupel melting

| statement | status | where |
|---|---|---|
| `rhox` is computed only under `qg > qcrmin .or. brs > brs_min` (F:3669) while melt asks `qg > 0.` (F:1400); `brs += pgmlt/rhox` divides by zero | CONFIRMED | source, `FINDING_melt_closure_measured_v1` |
| Float64 residual of the three melts, per level | CONFIRMED | `FINDING_melt_closure_measured_v1` |
| Whether trace graupel (1e-20..1e-43 kg/kg) should melt at all -- g1 skips, g3/g4/g5 zero it | OPEN | owner decision; `FINDING_melt_arm_g5_and_number_policy_v1` |
| Which states the scheme should treat as ACTIVE (`qg > 0`, `bg > 0`, `100 <= qg/bg <= 900`), which as TRACE needing a deterministic cleanup or an explicit skip, and which as INVALID needing the producer fixed. None of the four melt arms answers this: `g4` clamps the density then floors, `g5` preserves a ratio that can sit orders outside the band, `g3` leaves partial/`rhox=0` undefined, `g1` leaves the invalid state alone. Zero of the nine partial occurrences fell in the band where any two arms agree | OPEN | owner decision; `FINDING_melt_arm_g5_and_number_policy_v1` |
| `g4` and `g5` are the same equation when `bg0 >= tiny(f32)` AND `100 <= qg0/bg0 <= 900`: both give `(1-a)*bg0`, bit-equal in 6,646 of 14,344 in-band f32 draws with the rest at rounding (relative median 1.006e-07, max 2.936e-04). The `bg0 >= tiny` half was missing and the claim without it was wrong -- inside the window `g4` divides by `clip(qg0/max(bg0,tiny),100,900)`, so below `tiny` the arms separate even in band | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| For positive bg0 and a partial melt, the real-arithmetic g4 floor condition is `a*rho0 >= rho_c`, where `rho_c=clip(qg0/max(bg0,tiny(f32)),100,900)`. Only with `bg0 >= tiny` does it require `rho0 > 900`; below tiny, qg0=5e-37, bg0=1e-39, a=0.3 floors at raw rho0 about 500. Rounded f32 boundary candidates must be checked directly | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| `g5` preserves the raw ratio `qg0/bg0` in real arithmetic for positive operands; f32 products can round or underflow. Ratio preservation is not admissibility: the branch is entered where `rhox` was never computed, so the ratio can sit orders of magnitude outside `[100, 900]` and `g5` carries it through intact | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| That `g5` never produces a zero volume while mass remains -- with `bg0` exactly zero, or at the smallest f32 subnormal, `bg0*(qg+/qg0)` is 0.0 with `qg+ > 0`; `g5` does not RETURN that state, it `error stop`s, which suits a diagnostic arm and is not production-safe | REFUTED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| The melt window's STATE predicate is common in the real trajectory, not rare: over `mp37_traj_10min_hist1_20260822_212132`, 11 frames, 12,919 of 243,117 graupel-bearing cell-frames satisfy `qg <= qcrmin` and `bg <= brs_min` (5.3%), present in every frame after the first at about 1,300 a frame. Counted from `QGRAUP` and `QIB`, the field the driver passes as the kernel's `bg` | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| Within that window 1,831 cell-frames have raw density above 900 and 2,901 lie in `[100, 900]`. Classified by raw `rho0` ALONE; `bg0` was not tested against `tiny` and the melt fraction was not recorded, so neither group's arm behaviour follows from this count | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| The model's own state already carries the inconsistency the melt arms argue about: 551 in-window cell-frames have `qg > 0` with `bg` exactly 0, and 16 have `bg < 0` | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| Negative volume counts rise across the scalar-update interval: at most 6 at RK entry, up to 80,586 at intermediate boundaries and 2,570 before microphysics, falling to at most 6 after it. This interval contains advection, other tendencies and mass coupling; np=1, ten minutes | CONFIRMED | `FINDING_invalid_qib_producer_v1` |
| Step N RK-entry counts match step N-1 after-microphysics counts in three categories; values and locations were not compared. The first RK entry already has 635 qg>0,bg<=0 cells with an admissible positive volume available | CONFIRMED | `FINDING_invalid_qib_producer_v1` |
| A diagnostic clamp produces zero negative bg cells at RK entry, yet the scalar-update interval reaches 80,585 negatives (80,586 without it). Inherited RK-entry negatives are not necessary; the test does not isolate advection or prove limiter failure | CONFIRMED | `FINDING_invalid_qib_producer_v1` |
| The final RK stage DOES renormalise `qib` -- stage 3 takes it from 57,851 negatives to 1,535 -- so stages 1 and 2 are unbounded scratch by design and the 80,586 figure is an intermediate count. The count moves at `is = P_QIB = 5` and nowhere else. Two-minute run, `np=1` | CONFIRMED | `FINDING_invalid_qib_producer_v1` |
| Graupel mass also becomes negative (19,849, 42,154 and 1,172 before microphysics), so negativity is not volume-only. These counters do not test paired-moment ratio consistency | CONFIRMED | `FINDING_invalid_qib_producer_v1` |
| Under whole-grid normalisation the boundary frame has weak enrichment: 7.67% of cells and 8.32% of negatives (1.08x; interior 0.99x), with 85% at d>=9. Boundary contribution is not excluded; graupel-bearing exposure was not used as the denominator | CONFIRMED | `FINDING_invalid_qib_producer_v1` |
| Which term first produces a surviving negative value within the scalar-update interval: advection, other tendencies or mu_old/mu_new coupling. A first-negative-cell operand/tendency record is still needed | UNMEASURED | `FINDING_invalid_qib_producer_v1` |
| Of 551 zero-volume cell-frames, 280 have qg<100*eta and no admissible positive f32 volume; 90 have 100*eta<=qg<900*eta and admit bg=eta, potentially other multiples; 181 have qg>=900*eta. The 280/271 existence split holds, but uniqueness for the 90 is withdrawn (qg=500*eta admits eta through 5*eta) | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| Cell-operator occurrences counted inside the kernel over the same ten minutes: 644,771 with `pgmlt < 0`, 193,827 of them in the window (30.1%), of which 9 are PARTIAL -- the branch that separates `g4` from `g5` is reachable but thin. These are per cell, per microphysics call, per substep, per level; unique cells and episodes were not resolved | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| ALL 193,827 window occurrences move graupel mass to rain and add NO rain number: `ProgB_param` leaves `rhox` uncomputed exactly when `qg <= qcrmin .and. bg <= brs_min` (`:3693`), and the melt's number update is gated on `qg > qcrmin` (`:1412`), so the two predicates are complementary by construction. Per occurrence `d(qr/nr)/(qr/nr) = -pgmlt/qr` | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| The window carries 30.1% of the melt COUNT and 5.24e-07 of the melted MASS: `sum rho*dz*(-pgmlt)` is 1.77818e+02 kg m-2 over all occurrences and 9.31222e-05 over the window. Latent enthalpy is `xlf` times that mass, `xlf` a parameter, so the enthalpy fraction is the same 5.24e-07. The g1-vs-g3/g4/g5 policy difference therefore moves five parts in ten million of the melted mass | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| The number moment is where the window is NOT negligible: `d(qr/nr)/(qr/nr) = -pgmlt/qr` has p50 2.1983e-09 but p99.9 1.7269e-01 and max 1.0882e+08, with 958 occurrences above 1%, 274 above 10% and 71 above 100% -- more than doubling the rain mass without adding a drop. 2,904 window occurrences have `nr <= 0`, so `qr/nr` is undefined, and 21 have `qr <= 0`, creating rain mass where there was none | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| There is no graupel number moment to balance: `nrs(i,k,3) = 0.` on entry (`:392`), floored only afterwards (`:859`), and melting draws rain number from the graupel size distribution `n0go`, never from a carried number | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| Those counts do not depend on thread semantics: `configure.wrf` has `OMP = # -fopenmp` and `OMPCPP = # -D_OPENMP` both commented out, and the runs are `np=1`, so the increments were single-threaded | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| The instrumented binary produced the same trajectory as the deployed one: the raw-row run against the deployed 10-minute run differs in 0 of 197 fields across all seven frames | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| The `frame_reader` QNCCN fallback synthesised a profile whenever the stored field was all zero. Since Arm C the two initialisers are known to differ by geometry, so a synthesised field is neither one's unless the frame is t=0. Now an explicit `nccn_policy` argument, defaulting to `as_stored` | CONFIRMED | `oracle/kdm6/io/frame_reader.py` |
| Of those 9 partial window occurrences, 8 have raw density above 900, 1 below 100, and none in `[100, 900]` | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| `g4`'s candidate is exactly zero in 8 of the 9 partial occurrences and `g5`'s is positive in 9 of 9, measured from the arms' own f32 arithmetic emitted at the melt clamp, with three counters returning the census's 644,771 / 193,827 / 9 as a positive control. The floor predicate holds exactly: the eight have `a*rho0` far above 900, and the one that does not floor has `a*rho0 = 79.2` against `rho_c = 100`. All nine have `bg0 >= tiny(f32)`, so the `max(bg0,tiny)` bound never bit in this run | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| The nine are not nine independent cells: 5 distinct `i`, all at `k = 16`, `i = 167` five times. Unique `(i,j,k)` and episode length stay uncounted -- the `j` printed is a local in `kdm62D`, not the slice index | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| The partial-to-window occurrence fraction IN THIS RUN is 9/193,827 | CONFIRMED | `FINDING_melt_arm_g5_and_number_policy_v1` |
| The population rate that fraction implies for other cases, seasons or longer integrations -- one case, `np=1`, ten minutes, nine occurrences | UNMEASURED | `FINDING_melt_arm_g5_and_number_policy_v1` |

## CCN initialisation

| statement | status | where |
|---|---|---|
| Two sites: kernel memory-bounds sweep (`module_mp_kdm6.F:311`) seeds the divergence; `flow_dep_bdy_qnn` (transposed `dz8w`, wrong `xland` extent, slab `z_sum`) crashes | CONFIRMED | `FINDING_segv_localised_to_flow_dep_bdy_qnn_v1` |
| With both fixed, `np=1` vs `1x2`/`1x3`/`1x4` is 197 of 197 fields byte-equal at 20 s; `1x4` 0 of 197 at 1 min | CONFIRMED | `RECERT_results_v1` (historical), runs on `f54ef3c9` |
| The kernel block still overwrites valid external `QNCCN`: `module_mp_kdm6.F:309` is `if (itimestep .eq. 1)` with no `ccn_max_val` guard, which `start_em.F` has. The 85.41%-overwritten control was measured on `a06c954b`; the tile-bounds fix has landed since and the GUARD has not, so the defect carries to `6797945d` as a source fact | CONFIRMED | `FINDING_ccn_destroys_valid_input_v1` |
| Which paths fire the CCN overwrite is decided by ONE guard, `start_em.F:242`: `IF ( .not. ( config_flags%restart .or. grid%moved ) ) grid%itimestep=0`. Ordinary restart and a moved nest are excluded and do not fire; cold start, a newly spawned nest, and cycling are not excluded and do fire; and `share/dfi.F:287` zeroes it again unconditionally at the end of DFI. Read from the two guards; no restart, nest, DFI or cycling run was made | CONFIRMED | `FINDING_ccn_destroys_valid_input_v1` |
| A newly spawned NEST fires it over its parent's EVOLVED `QNCCN`: `qnn` carries `d`/`bdy_interp` so `med_interp_domain` interpolates it down, `start_domain` runs `start_em` whose guard then correctly stands down, and `start_em.F:243` zeroes the nest's own `itimestep` because a new nest is neither `restart` nor `moved`. No nested run was made | CONFIRMED | `FINDING_ccn_destroys_valid_input_v1` |
| That the exposure is a COLD START -- DFI, cycling and a newly spawned nest reach it too, and the DFI path does so unconditionally | REFUTED | `FINDING_ccn_destroys_valid_input_v1` |
| How LARGE the Arm C difference is at 60 s, `np=1`: concentrated in the number concentrations -- `QNRAIN` rel p99 9.17e-01, `QNCLOUD` 1.67e-01, `QCLOUD` 3.30e-02 -- while `T` and `QVAPOR` are bit-identical over more than half the domain and reach 1.10e-04 and 7.67e-06 at p99, `REFL_10CM` is unchanged below p99, and domain-total `RAINNC` differs by +0.037% (18.76216 vs 18.75524 mm). Wide, and large only where the defect writes | CONFIRMED | `FINDING_ccn_destroys_valid_input_v1` |
| What that does to FORECAST SKILL -- 60 seconds is not hours, and none of these are skill measures | UNMEASURED | `FINDING_ccn_destroys_valid_input_v1` |
| Guarding the kernel block on an empty field is the same edit as deleting it: bitwise identical to Arm C over 197 fields, frames 0-3, because `start_em` is a fallback that always leaves `QNCCN` populated, so the block one step later never meets an empty field | CONFIRMED | `FINDING_ccn_destroys_valid_input_v1` |
| The kernel slope relation requires number in m^-3 while Registry declares kg^-1 and no boundary conversion is present. Thickness-only transport has sum N*dz as its matched-transfer measure, but independent caps can violate matching. These assumptions are inherited from WDM6; source comparison does not decide which side is correct | CONFIRMED | `FINDING_number_basis_is_inherited_from_wdm6_v1` |
| The ten-minute np=1 run recorded an UNCLIPPED density-contrast term divided by UNCLIPPED departure: rain 4.6188%, ice 8.5710%, with 163,801,204 recorded interface occurrences each. These are moist-density-weighted proxy ratios, not actual number-creation fractions | CONFIRMED | `FINDING_number_creation_in_the_real_model_v1` |
| That clip frequencies (rain 0.0018%, ice 2.91%) make the rain proxy effectively exact or the ice ratio an upper bound; independently capped arrivals and departures can reverse the residual sign and change ratio weights either way | REFUTED | `FINDING_number_creation_in_the_real_model_v1` |
| The actual ten-minute number residual from paired applied dn_out/dn_in with explicit density, including separate density-contrast and transfer-mismatch terms | UNMEASURED | `FINDING_number_creation_in_the_real_model_v1`; existing `g33_cap_interface.py` handles fixed-forcing streams |
| Arm C -- the kernel one-time CCN block removed -- differs from the deployed binary in 0/11/74/76 of 197 fields at 0/20/40/60 s, `np=1` | CONFIRMED | `FINDING_ccn_destroys_valid_input_v1` |
| The two initialisers write DIFFERENT profiles, not two spellings of one: `QNCCN` is identical at `t=0` and differs in 54.3% of cells domain-wide by 20 s (median 8.4e+04, max 3.4e+08). They apply the same formula to different thicknesses -- `start_em` to `dz8w` from `phb+ph_2` at initialisation, the kernel to `delz` as passed after one dynamics step | CONFIRMED | `FINDING_ccn_destroys_valid_input_v1` |
| That the overwrite is harmless when the input is zero -- an earlier reading held that A, B and C then differ over tiling and halo rather than over the field's origin | REFUTED | `FINDING_ccn_destroys_valid_input_v1` |
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
| A conversion-free ice fixture. No fixture exists and building one is a modelling choice, not an extraction: it must hold ice with sedimentation active and conversion terms off, which no current column does | UNMEASURED | `FINDING_ice_chain_missing_term_v1` |

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
