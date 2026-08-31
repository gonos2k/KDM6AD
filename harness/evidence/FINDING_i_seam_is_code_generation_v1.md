# The i-cut seam is decomposition-dependent code generation

Rebuild the 30 `dyn_em` objects listed below with `-O2 -fno-tree-vectorize
-ffp-contract=off`, change nothing else, and `np = 1` and `4x1` compute **the same values at every
instrumented point of the first dynamics step**. On the production flags they
differ at the last owned column of some patches.

That is the i-seam AS THIS PROBE MEASURES IT -- one time step, the first RK
stage, the instrumented field set. The headline i-seam is 77 of 197 fields at ONE
MINUTE, and this run wrote no forecast output, so whether the alternative build
removes that too is unmeasured. The wording "the whole i-seam" appeared in an
earlier version of this document and is withdrawn.

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

**Thirty-two, not thirty**, and the discrepancy had one cause. The list
published with the experiment was extracted with a pattern requiring a BARE
filename after `-o`, so every object compiled with a path prefix vanished from
it. Counted from the 36 compile lines of `compile_ffpoff_all.log` with
`-o\s+(\S+\.o)`, the build touched 32 `dyn_em` sources; the two the published
list omits are

    module_bc_em              -o ../dyn_em/module_bc_em.o
    module_initialize_real    -o ../dyn_em/module_initialize_real.o

Neither is neutral here. `module_initialize_real` sits with `start_em` in the
group that moved the initial state, and `module_bc_em` is the boundary-condition
code, which the eastern-band question turns on.

The same bug undercounted the other two builds. Recounted: the partial build took
9 objects (published as 6), this one 32 (published as 30), and the restore
rebuild 32 (published as 31). The restore set is IDENTICAL to this one, so the
restore recompiled exactly what the experiment had changed, and
`compile_restore.log` carries zero lines with `-ffp-contract=off`. Nothing is
left unreconciled.

The 30 published with the experiment were, and the two above complete them:
`adapt_timestep_em`, `couple_or_uncouple_em`, `interp_domain_em`,
`mediation_integrate`, `module_advect_em`, `module_after_all_rk_steps`,
`module_avgflx_em`, `module_big_step_utilities_em`, `module_convtrans_prep`,
`module_damping_em`, `module_diffusion_em`, `module_em`,
`module_first_rk_step_part1`, `module_first_rk_step_part2`, `module_force_scm`,
`module_ieva_em`, `module_init_utilities`, `module_madwrf`, `module_polarfft`,
`module_sfs_driver`, `module_sfs_nba`, `module_small_step_em`,
`module_solvedebug_em`, `module_stoch`, `ndown_em`, `nest_init_utils`,
`shift_domain_em`, `solve_em`, `start_em`, `tc_em`.

`module_advect_em` and `module_small_step_em` are both in, and the partial
rebuild lacked them. That is a correlation over two builds, not an attribution:
this build added twenty other objects and `start_em` at the same time, so which
one removes the stage-5 tendency difference is UNMEASURED. An arm that adds
`module_advect_em` alone would say.

## Two compiler effects changed together

The flags were APPENDED, not replaced. Every one of the 36 compile lines in
`compile_ffpoff_all.log` -- lines matching `^time (mpif90|mpicc) ` -- reads

    -O2 -ftree-vectorize -funroll-loops -fno-tree-vectorize -ffp-contract=off

so `-funroll-loops` is present in the alternative build exactly as in production,
and `-ftree-vectorize` is present but overridden by the later
`-fno-tree-vectorize`. TWO things moved: vectorisation off and contraction
forbidden. Unrolling was constant across both arms.

An earlier version of this section said unrolling was dropped. It was not, and
the difference matters: the decomposition needs TWO arms off production
(`-fno-tree-vectorize` alone, `-ffp-contract=off` alone), and an unrolling arm
would test something neither build varied.

Until those run, "a trip count selects the vector body and remainder" below is
the reading the evidence points at, not the reading it establishes.

## The initial state moved too

The rebuilt objects include `start_em` AND `module_initialize_real`, which
between them compute the base and initial state, and control 3
shows this build differs from production at stage 0 in `w_2` and `mub`. So the
two builds do not start from the same operands, and

> zero difference under the alternative build

does not by itself prove that production's own operands were equal and only its
evaluation differed. What supplies that is the separate probe5 measurement below.
The clean form of this experiment leaves the initial state bitwise unchanged --
rebuild only the objects on the `ww` path, with `start_em` on production flags --
and it has not been run.

## The eastern band cannot be read as being about the dynamics

The partial build did NOT recompile `module_bc_em`; the full build did. Across
that pair the eastern-zone columns 231-234 were still present at stage 5 under
the partial build and absent under the full one -- but the boundary-condition
code moved between the two builds along with twenty-two other objects. So the
band going clean is a correlation across a pair of builds, not evidence about
`module_bc_em` and not evidence that the band is a dynamics effect. Any earlier
reading of it as the latter is withdrawn.

## Why cutting i differs and cutting j does not

`i` is the INNER loop of these stencils. A decomposition that cuts i changes each
patch's inner trip count, and the trip count selects which vector body and which
remainder run for the same operands; a decomposition that cuts j changes only the
OUTER loop's extent, which does not change how the inner loop is compiled or run.

That is why `1x2`, `1x3` and `1x4` are bit-identical to `np=1` at every rank
count while `2x2` and `4x1` differ in 77 of 197 fields -- an asymmetry that had
no explanation through four findings.

**This does not establish that no defect exists.** Turning vectorisation off also
suppresses a second class of cause: an out-of-bounds vector load, an
uninitialised temporary, a wrong extent, an aliasing violation. Distinguishing
that class from ordinary reordering needs counterfactuals none of which has been
run here -- bounds checking, an uninitialised-value trap, signalling-NaN
initialisation, the vectorisation report, a disassembly comparison. So the
accurate statement is that no stale-halo or lateral-boundary source was found for
the measured first-stage seam and the remaining evidence points at
compiler- and loop-shape-sensitive evaluation; whether that is ordinary rounding
sensitivity or exposes a source or extent defect is OPEN. On the production build the shape is visible directly:
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

**That argument covers `ww` and nothing else.** probe5 measured the operands
`calc_ww_cp` reads, on the production build. For the stage-5 tendencies there is
NO production-build operand measurement at all, so for those the only evidence is
"zero under a different build", which is the weaker half. The same-state
minimal-object arm is not a refinement there; it is the missing measurement.

## No stencil propagates a stale halo into an owned cell

`FINDING_i_seam_first_write_is_rk_step_prep_v1` left open whether any stencil
reads the exchanged fields past the width they are refreshed to. The probe7 pair
answers it, because it holds a stale halo and a clean result side by side.

Comparing each rank's records against `np=1` at the same global column:

    stage   halo cells differing      owned cells differing
        0            284,256                        0
        1            284,256                        0
        2          2,971,331                        0
        6          3,054,680                        0
        7          3,092,161                        0
       31          2,971,331                        0
       32          2,658,752                        0
    TOTAL         15,316,767                        0

Stages 4, 5 and 8-12 are absent from the left column because they dump only
owned-clipped groups (1 and 3); they hold no halo records at all, and their zero
is an absence of observation, not an observation of currency. Their owned zero is
real.

So fifteen million halo cells hold values that differ from what the single-patch
run has at the same global column -- and not one owned cell differs, at any
stage. Had a stencil read one of those columns and used it, the owned result
would have moved with it.

> **Within the first RK stage of the first time step, for the fields dumped, no
> stencil propagates a stale halo value into an owned cell.**

This carries to the production build. A stale read is a DATA difference, and a
data difference survives a change of optimisation flags -- that is the same
argument that refuted the halo account of `ww`. So the null is not an artefact of
building without contraction.

What it does not cover: fields the probe does not dump, later RK stages, later
time steps, the microphysics, and any read whose effect is overwritten before the
next anchor. The claim is about owned cells observed at the anchors.

## A prediction, registered before the run that would test it

Which boundaries differ is still unexplained. The trip-count reading says the
answer depends on the loop extent and nothing else, and that is falsifiable
without any rebuild -- `f54ef3c9` is back, so a different `nproc_x` is one pair of
runs. Writing the prediction down first is what makes that run worth doing.

For each patch, let `trips = MIN(ipe, ide-1) - ips + 1` (the patch bounds are in
the dump filenames). The hypothesis predicts:

1. **Two patches with the same trip count behave the same.** Both differ at their
   last owned mass column, or neither does. A run where they disagree kills it.
2. **58 trips does not differ; 59 trips does.** Measured at `4x1`, where patches 0
   and 2 have 59 and patches 1 and 3 have 58. Any 58-trip patch that differs, or
   any 59-trip patch that does not, kills it.
3. **A trip count not yet seen has no prediction here**, but must be consistent
   across every patch that shares it.

What it does NOT predict is which side of 58/59 a new trip count falls on: that
depends on the vector width and how the remainder is emitted, which has not been
read out of the object code. Point 1 is the load-bearing one, because it is the
claim that position and data are irrelevant.

## Scope, and what this does NOT license

- **One case, one time step, the first RK stage, `4x1` only, and only the fields
  the probe dumps.** The ten-minute growth to 77/77/75/106 fields is downstream of
  this and is NOT measured here.
- **"Not a defect" is not "harmless".** A 1-ULP seam at a patch boundary still
  seeds the divergence that grows later, and nothing here bounds that growth.
- **This is a property of the deployed implementation, not only of a build.** A
  numerical model is source plus compiler plus flags plus processor plus
  decomposition. `f54ef3c9` does not reproduce bitwise across i decompositions,
  and that is a REPRODUCIBILITY failure of the deployed model wherever bitwise
  decomposition invariance is required. "Not a defect" was too strong; what is
  established is that it is not a physical-state or stale-halo defect.
- **The alternative build's own numbers say nothing about `f54ef3c9`.**
  `8bd8cdbf` is not `f54ef3c9`, and control 3 shows the two differ from
  initialisation onward.
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
            4x1 mp37_probe6b_1min_hist0_np4_4x1_20260831_105103_p99140   f15d07a1, 9 objects
    probe7  np1 mp37_probe7_1min_hist0_20260831_110634_p17386
            4x1 mp37_probe7_1min_hist0_np4_4x1_20260831_110832_p20651    8bd8cdbf, 32 objects

`mp37_probe6_1min_hist0_np4_4x1_20260831_104910_p98502` is the attempt that died
(exit 14, `writev`) and is NOT the analysed run.

The probe6 and probe7 experiments and the object list are a second session's work
on the same tree. The reproduction of every number above, the three controls as
run here, and this document are this one's. The two sessions reached the earlier
refutation independently.
