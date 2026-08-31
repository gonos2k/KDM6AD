# The i-cut seam is decomposition-dependent code generation

Rebuild every `dyn_em` object with `-ffp-contract=off -fno-tree-vectorize`,
change nothing else, and `np = 1` and `4x1` compute **the same values at every
instrumented point of the first dynamics step**. On the production flags they
differ at the last owned column of some patches. That is the whole i-seam, and it
closes a question that had been open across four findings.

## The result, with its denominator

Binary `8bd8cdbf`, both arms built from it, one minute, `4x1` against `np=1`.

| | |
|---|---|
| stages compared | 14 -- 0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 31, 32 |
| owned (stage, group, column) records | 2 520 |
| (field, column) comparisons | 16 800 |
| f32 words compared | **141 214 320** |
| **differing** | **0** |

Zero at every stage, every group, every field, including the stage-5 tendencies
that survived the partial rebuild and the eastern-zone columns 231-234.

## Three controls, because an empty table is also what a broken read looks like

**1. The comparison was complete.** `first_difference` refuses a pair whose
coverage differs at all -- the (stage, group) universe against `ANCHORS`, the
owned-key sets against each other, the field list of every record. The probe7
pair passes it, so every record the anchors declare is present on both arms.

**2. The loader read the data.** On the SAME probe7 dumps, `halo-vs-reference`
returns 260 differing rows: the beyond-halo-width columns (rank 0 at 63-66, rank
1 at 53-56 and 121-124, rank 2 at 111-114 and 180-183, rank 3 at 170-173) still
differ in `u_2`, `mu_2`, `mub` and `msfuy`, exactly as on the production build.
Those columns are memory the model never writes and no compiler flag can change
them, so a zero owned-cell table is a result and not a failed load.

**3. The flags were not a no-op.** Same decomposition, different builds:

    probe5/np1 vs probe6/np1   45 differing (stage, field) rows, 120 columns wide
    probe5/np1 vs probe7/np1   97 differing (stage, field) rows, 120 columns wide

The arithmetic changed pervasively, across the full dump window. `ww` vanishing
is not the flags failing to take effect.

Control 3 also shows probe7 differs from production at **stage 0**, in `w_2` and
`mub`, because `start_em` is in the rebuilt set and the base state is computed
there. probe7 is a numerically different model. That does not weaken the result
-- both probe7 arms come from one binary -- but it is why the result is about
decomposition, not about the deployed model's numbers.

## What was rebuilt

Thirty objects, with no compile line in the build lacking the flag:
`adapt_timestep_em`, `couple_or_uncouple_em`, `interp_domain_em`,
`mediation_integrate`, `module_advect_em`, `module_after_all_rk_steps`,
`module_avgflx_em`, `module_big_step_utilities_em`, `module_convtrans_prep`,
`module_damping_em`, `module_diffusion_em`, `module_em`,
`module_first_rk_step_part1`, `module_first_rk_step_part2`, `module_force_scm`,
`module_ieva_em`, `module_init_utilities`, `module_madwrf`, `module_polarfft`,
`module_sfs_driver`, `module_sfs_nba`, `module_small_step_em`,
`module_solvedebug_em`, `module_stoch`, `ndown_em`, `nest_init_utils`,
`shift_domain_em`, `solve_em`, `start_em`, `tc_em`.

`module_advect_em` and `module_small_step_em` are both in, which is what the
partial rebuild lacked and why its stage-5 tendency difference survived.

## Why cutting i differs and cutting j does not

`i` is the INNER loop of these stencils. A decomposition that cuts i changes each
patch's inner trip count, and the trip count selects which vector body and which
remainder run for the same operands; a decomposition that cuts j changes only the
OUTER loop's extent, which does not change how the inner loop is compiled or run.

That is why `1x2`, `1x3` and `1x4` are bit-identical to `np=1` at every rank
count while `2x2` and `4x1` differ in 77 of 197 fields -- an asymmetry that had
no explanation through four findings, and which needs no numerical defect
anywhere. On the production build the shape is visible directly:
`itf = MIN(ite, ide-1)` gives patches 0 and 2 a 59-trip `i` loop and patches 1
and 3 a 58-trip one, and `ww` differed at the last owned column of the 59-trip
patches only.

## The other half of the argument

This run alone does not say the production build's operands were equal; it says
that with the evaluation freedom removed the outputs are equal, on a different
binary. What closes it is the measurement on the PRODUCTION build
(`FINDING_i_seam_first_write_is_rk_step_prep_v1`): every owned cell at the
RK-stage entry agrees, and every halo column `calc_ww_cp` reads at a patch's last
owned mass column -- i = 60, 118, 177 -- is bitwise identical in `u_2`, `mu_2`,
`mub` and `msfuy`.

Identical operands, and no compiler flag can equate operands that differ. So on
the production build the difference was in the evaluation, and this run shows
what happens when that freedom is taken away.

## Scope, and what this does NOT license

- **One case, one time step, the first RK stage, `4x1` only, and only the fields
  the probe dumps.** The ten-minute growth to 77/77/75/106 fields is downstream of
  this and is NOT measured here.
- **"Not a defect" is not "harmless".** A 1-ULP seam at a patch boundary still
  seeds the divergence that grows later, and nothing here bounds that growth.
- **Nothing about the deployed model's numbers changes.** `8bd8cdbf` is not
  `f54ef3c9`, and control 3 shows the two differ from initialization onward.
- **This does not say the code is correct.** It says the difference between
  decompositions comes from code generation rather than from halo exchange,
  stencil reach, or the lateral-boundary update. Whether a stencil reads past the
  width it is given is still unmeasured.
- **`v_2`, `msftx` and `msfvx_inv` are in no group.** The probe's input coverage
  is still incomplete; this result happens not to depend on it, because a flag
  change cannot equate differing data whatever the enumeration.

## Provenance

Binary `8bd8cdbf`, both arms. Runs `mp37_probe7_1min_hist0_20260831_110634_p17386`
(1x1) and `mp37_probe7_1min_hist0_np4_4x1_20260831_110832_p20651` (4x1 requested
and actual), both `experiment_valid` true with `exit_code` 0 and
`model_completed` true, both `SUCCESS COMPLETE WRF`; dump mtimes 11:07:42 and
11:08:55, inside their run windows. Dumps `dyn_dumps_probe7/{np1,np4}`.
Production-flag reference `dyn_dumps_probe5`, partial rebuild `dyn_dumps_probe6`.
Comparator `harness/g33_dyn_probe.py`.

**The tree is as it was found, and the build is deterministic across a flag
round-trip.** After the experiments, the canonical source and the canonical
`FCOPTIM` went back and all 31 `dyn_em` objects were recompiled from scratch;
verified here: `dyn_em/solve_em.F` `d66e9db1bba8f37e` (5002 lines, zero
instrumentation markers), `configure.wrf` line 150
`FCOPTIM = -O2 -ftree-vectorize -funroll-loops`, and `main/wrf.exe`
`f54ef3c962a1d6a0` -- the deployed hash, bit for bit. This is a stronger control
than the original pass's: not merely that removing an overlay restores the
binary, but that a full flag round-trip out and back reproduces it exactly.

Run directories, for citation:

    probe5  np1 mp37_probe5_1min_hist0_20260831_102334_p64676
            4x1 mp37_probe5_1min_hist0_np4_4x1_20260831_102528_p74909    d1b46b8c, production flags
    probe6  np1 mp37_probe6_1min_hist0_20260831_104756_p97861
            4x1 mp37_probe6b_1min_hist0_np4_4x1_20260831_105103_p99140   f15d07a1, 6 objects
    probe7  np1 mp37_probe7_1min_hist0_20260831_110634_p17386
            4x1 mp37_probe7_1min_hist0_np4_4x1_20260831_110832_p20651    8bd8cdbf, 30 objects

`mp37_probe6_1min_hist0_np4_4x1_20260831_104910_p98502` is the attempt that died
(exit 14, `writev`) and is NOT the analysed run.

The probe6 and probe7 experiments and the object list are a second session's work
on the same tree. The reproduction of every number above, the three controls as
run here, and this document are this one's. The two sessions reached the earlier
refutation independently.
