# The i-cut seam is decomposition-dependent code generation

Rebuild the 32 `dyn_em` objects identified from the anchored compile lines
with `-fno-tree-vectorize -ffp-contract=off` appended, change nothing else, and `np = 1` and `4x1` compute **the same values at every
instrumented point of the first dynamics step**. On the production flags they
differ at the last owned column of some patches.

That was first shown only for the instrumented first RK stage, and this document
said so. It has since been measured over the headline quantity as well: all 197
fields at one minute, on three alternative builds, all zero, against 77 for
production. The section below carries that.

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

## The one-minute seam, and which flag removes it

The measurements above were confined to the instrumented first RK stage, because
the runs that produced them wrote no forecast output. That limitation is now
gone. Four builds were made, differing only in `FCOPTIM`, each rebuilding the
same 32 `dyn_em` objects, and each run at `np=1` and `4x1` for one minute with
history every 20 s. The comparator's field universe is **197** in every file.

    build                       vectorise   contract    0s  20s  40s  60s
    production      f54ef3c9    permitted  permitted    0   28   71   77
    both off        309e2a8e    forbidden  forbidden    0    0    0    0
    vectorise off   b6eb2159    forbidden  permitted    0    0    0    0
    contract off    5f77fefe    permitted  forbidden    0    0    0    0

`-ffp-contract=off` forbids CONTRACTION. Whether the loop actually emitted FMA
instructions under the production flags is a separate question and is not
measured; "fma on/off" appeared in an earlier version of this table and is
withdrawn.

Counted as RAW WORDS rather than as values the table is unchanged -- 0/28/71/77
and 0/0/0/0 over the same 197 fields -- so "identical" here is bit for bit in the
compared output, not merely equal as floating-point values.

The production row reproduces the campaign's headline number -- 77 of 197 fields
at one minute -- with the same comparator, case, frames and field universe. So
the zeros are not the instrument failing to see this seam.

**The response is conjunctive.** The seam appears only when both transformations
are permitted, and forbidding either is sufficient to remove it.

An earlier version of this section called that "an interaction, not a main effect
of either". That is wrong, and wrong in a way that depends on how the factors are
coded. In the standard +-1 factorial with `Y(++)=77` and the other three cells 0,

    Y = 19.25 + 19.25 x_V + 19.25 x_C + 19.25 x_V x_C

so both main effects and the interaction are equal and non-zero. Only in 0/1
treatment coding against the off/off cell does the product term stand alone.
"Conjunctive and non-additive" says what was measured without depending on the
coding, and is what this document now claims.

### The vectorisation arm leaves the initial state untouched

The full 32-object rebuild includes `start_em` and `module_initialize_real`, so
"the two builds do not start from the same operands" was a live objection to
every zero above. It is now measured, per arm, against the production run:

    arm np=1 frame 0 vs production np=1 frame 0, 197 fields
      both flags off    7 fields differ   MUB, P, PB, PHB, P_HYD, QNCCN, W
      contract off      7 fields differ
      vectorise off     0 fields differ   <-- bitwise identical start

So `-fno-tree-vectorize` alone starts from the production initial state and still
removes the whole one-minute seam.

"Bit for bit" is measured, not assumed: comparing those frame-0 fields as raw
uint32 words rather than as floating-point values gives 0 of 197 differing, with
zero cells where one arm holds `+0.0` and the other `-0.0`. The comparator's own
equality is `np.array_equal`, which is value equality and would not have
distinguished those, so the raw-word pass was run separately.

Its SCOPE is the 197 time-varying f32 output fields. Static fields, integer and
logical state, halo and boundary arrays and internal temporaries are not in the
forecast file and are not compared, so this is not a claim that the two builds'
entire initial states are identical.

### And that flag does change the arithmetic

A flag that changed nothing would also give zero. The control, same build against
production at `np=1`, where the start is identical so any difference is the flag:

    vectorise off np=1 vs production np=1    0    28    76    78

Seventy-eight of 197 fields differ by one minute. That is a count of FIELD NAMES,
not a magnitude, so it says the flag is not a no-op and nothing about whether the
answer got smaller or smoother; an earlier version of this paragraph said it did
and that is withdrawn.

What is measured is that under the alternative build the two decompositions agree
in the 197 compared fields at every sampled frame through 60 s. Intermediate RK
stages and acoustic sub-steps are not sampled here, so "they follow the same
path" -- also an earlier wording -- overstates it: paths that differ in between
and rejoin at the frame boundary are not excluded by this measurement.

### What this settles and what it does not

It settles the scope objection that this document carried: the removal is not
confined to the instrumented first RK stage. Over all 197 fields at one minute,
on this case and `4x1`, the seam is gone under any of the three alternative
builds.

It does not settle the mechanism. Vectorisation and contraction are each
sufficient to remove the difference, which is consistent with a vector body and
its scalar remainder being fused differently for the same operands, and also
consistent with other readings. No vectorisation report or disassembly has been
read, and the ten-minute growth, other decompositions, other cases and forecast
skill remain unmeasured.

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

Those arms have since been run, and each flag ALONE removes the difference; see
the flag matrix above. So the difference requires both transformations enabled,
which is an interaction rather than a main effect. It still does not establish
that "a trip count selects the vector body and remainder": that reading is
consistent with the interaction and so are others, and a vectorisation report and the
vectoriser's own dump have now been read (below); disassembly has not.

## The initial state moved too

The rebuilt objects include `start_em` AND `module_initialize_real`, which
between them compute the base and initial state, and control 3
shows this build differs from production at stage 0 in `w_2` and `mub`. So the
two builds do not start from the same operands, and

> zero difference under the alternative build

does not by itself prove that production's own operands were equal and only its
evaluation differed. What supplies that is the separate probe5 measurement below.
That objection is now answered by measurement rather than by a narrower rebuild:
the `-fno-tree-vectorize` arm starts from the production initial state BIT FOR
BIT (0 of 197 fields differ at frame 0) and still removes the whole one-minute
seam. The two arms carrying `-ffp-contract=off` do move the start, by 7 fields.
So the objection stands for those two and is retired for the arm that matters,
since that arm is sufficient on its own.

## The eastern band cannot be read as being about the dynamics

The partial build did NOT recompile `module_bc_em`; the full build did. Across
that pair the eastern-zone columns 231-234 were still present at stage 5 under
the partial build and absent under the full one -- but the boundary-condition
code moved between the two builds along with twenty-two other objects. So the
band going clean is a correlation across a pair of builds, not evidence about
`module_bc_em` and not evidence that the band is a dynamics effect. Any earlier
reading of it as the latter is withdrawn.

## The intervention is global, so the site is not attributed

`-fno-tree-vectorize` turns tree vectorisation off in all 32 objects, not in
`calc_ww_cp`. So what is established is that the whole-build intervention removes
the seam, NOT that this loop is the only place that would. `module_advect_em`,
`module_small_step_em`, `module_bc_em`, `start_em` and the rest are in the same
build.

The arm that would attribute it keeps production flags everywhere and applies
`-fno-tree-vectorize` to one object at a time -- `module_big_step_utilities_em`
first, then `module_advect_em` and `module_bc_em` if anything survives. It also
holds the initial state fixed, since `start_em` and `module_initialize_real` stay
on production flags. It has not been run.

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

## Stale non-owned records beside an owned null, and what that does not prove

`FINDING_i_seam_first_write_is_rk_step_prep_v1` left open whether any stencil
reads the exchanged fields past the width they are refreshed to. The probe7 pair
answers it, because it holds a stale halo and a clean result side by side.

Comparing each rank's records against `np=1` at the same global column:

    stage   non-owned f32 words differing   owned f32 words differing
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

That count is f32 WORD comparisons summed over stage, field, rank, j and k --
not fifteen million distinct halo cells. The same spatial column is counted once
per field and per stage.

What it says is narrow and it is what is measured: at every stage that records
both, the sampled non-owned records differ from the single-patch reference while
the sampled owned outputs are raw-word identical.

> **Under this build, at the stages that record both, the non-owned records
> differ from the single-patch reference and the owned outputs do not.**

**Two inferences drawn from that earlier are withdrawn.**

*"Had a stencil read one of those columns, the owned result would have moved with
it."* Floating-point evaluation is not injective. Two different inputs can round
to the same f32 output -- the difference can fall below a rounding threshold, be
multiplied by a small or zero coefficient, cancel against another term, leave the
branch taken unchanged, be overwritten before the next anchor, or propagate only
into fields the probe does not dump. A net null at the anchors is not proof that
nothing was read.

*"A data difference survives a change of optimisation flags."* This is false in
general, and it contradicts the rest of this document. Changing vectorisation or
contraction changes the map from operands to stored result, so two operands that
give different f32 values under one build can give the same value under another.
That is the very effect measured here. So the null observed under this build does
NOT transfer to the production build, and whether those non-owned values become
observable under production flags is UNMEASURED.

What the null also does not cover: fields the probe does not dump, later RK
stages, later time steps, and the microphysics.

## The compiler was asked what it did

Every mechanism statement in this document so far was inference from timing and
flags. `-fopt-info-vec` answers it directly, and costs no run: the same compile
line the restore build used, on the same preprocessed source, with the object
written to a scratch path so the tree is untouched.

In `dyn_em/module_big_step_utilities_em.f90`, `calc_ww_cp` spans 633-775 and the
`divv` assignment sits at 740, inside

    737   DO k=kts,ktf
    738   DO i=its,itf
    740     divv(i,k) = msftx(i,j)*dnw(k)*( rdx*(... muu(i+1,j) ... u(i+1,k,j) ...

Under the production flags the report for that loop is

    module_big_step_utilities_em.f90:738:13: optimized: loop vectorized using 16 byte vectors
    module_big_step_utilities_em.f90:738:13: optimized: loop vectorized using 8 byte vectors

Two widths for one loop. `-fopt-info` alone does NOT say which is the main loop
and which the epilogue -- it never uses the word -- so the vectoriser's own dump
was read instead (`-fdump-tree-vect-details`, GCC 15.2.0). For the same loop, in
order:

    vectorization factor = 4
    ... Vectorizing an unaligned access.  (x14)
    epilog loop required
    vectorization factor = 2

and, on the same loop, `cost model: epilogue peel iters set to vf/2 because loop
iterations are unknown`. So the four-lane body and the two-lane epilogue are
named by the compiler, in that order, and the reason the epilogue cannot be
specialised is that the trip count is a run-time value -- which is exactly what
changes with the patch width.

Adding `-fno-tree-vectorize` to the identical line takes the whole file from 347
vectorisation reports to **zero**, and `calc_ww_cp` from 10 to zero.

WHAT THIS DOES AND DOES NOT ADD. It establishes the STRUCTURE the trip-count
reading assumed -- body plus narrower remainder -- rather than leaving it
assumed. It does not establish that the remainder is where the difference is
made: that needs the generated code, or a numeric test that isolates the
remainder lanes, and neither has been done. The second possibility this document keeps open -- that vectorisation is
suppressing an out-of-bounds load or an uninitialised value rather than only
reordering arithmetic -- was ATTEMPTED and is still open. A bounds-checked build
of the same 32 objects (`649b437f`) aborted in INITIALISATION, before the first
dynamics step, on a real out-of-bounds read in the CCN block
(`FINDING_ccn_init_reads_past_the_model_top_v1`). So the dynamics were never
reached under bounds checking and the question is untested, not answered.

Two weaker checks did run and found nothing: re-enabling the warnings the build
suppresses with `-w` yields 208 for this file, all `-Wunused-dummy-argument` or
`-Wunused-variable` and none about initialisation; and the three reads that cross
the patch boundary are in bounds by declaration --

    muu(i+1,j)   declared its:ite+1     read to MIN(ite,ide-1)+1 <= ite+1
    u(i+1,k,j)   declared ims:ime       read to ite+1, halo measured >= 7
    muv(i,j+1)   declared jts:jte+1     read to jte+1

-- so the specific stencil is not where an extent defect would be. That is not
the same as the dynamics being clean.

For the record, since it is arithmetic and not a claim: at four f32 lanes, 59
trips leave a remainder of 3 and 58 leave 2, and a two-lane epilogue covers 2
exactly while 3 needs the epilogue plus one scalar iteration.

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

### The attempt to test it, and why it did not

`nproc_x` = 2, 3 and 5 were run on `f54ef3c9`, no rebuild. Their patches carry

    2x1   117, 117                 boundary 117
    3x1    78,  78,  78            boundaries 78, 156
    5x1    47,  47,  47,  47, 46   boundaries 47, 94, 141, 188

**Neither point is decided by these runs.** Point 2 needs a 58 or a 59 and none
occurs. Point 1 is satisfied, but vacuously: almost every patch in these
decompositions shares one trip count, so "equal trip counts behave alike" cannot
fail when every boundary behaves the same way -- which it does. The footprint at
20 s shows one band per interior boundary and nothing else: one band for `2x1`,
two for `3x1`, four for `5x1`, plus the eastern zone in each.

That per-boundary scaling is a real measurement and it is new. The prediction is
not.

**It also corrects how the prediction was stated here.** The 59-versus-58
observation was about `ww` AT STAGE 2 -- the first write -- and at `4x1` the
58-trip boundary at 117 carries no stage-2 `ww` difference. But it does carry a
forecast band: `FINDING_i_seam_is_banded_at_the_patch_boundary_v1` records three
`PH` and `T` bands at `4x1`, at 59, 117 and 176. So trip count is at most about
WHICH BOUNDARY THE DIFFERENCE IS WRITTEN AT FIRST, not about which boundaries end
up differing. The prediction therefore cannot be tested on forecast output at
all; it needs the stage probe at a decomposition whose trip counts are mixed.

## Scope, and what this does NOT license

- **One case and `4x1` only.** The first-stage result covers the probe's field
  set; the one-minute result covers all 197 forecast fields. The TEN-minute
  growth to 77/77/75/106 fields is still downstream of both and NOT measured.
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

## Provenance for the flag matrix

Four builds, differing only in `FCOPTIM`, each rebuilding the same 32 `dyn_em`
objects (36 anchored compile lines, none lacking `-funroll-loops`), each run at
`np=1` and `4x1`, `--minutes 1 --history 0 --history-s 20` -- eight runs, six new
and the two production references -- all with `experiment_valid` true with `exit_code` 0 and `model_completed` true:

    f54ef3c9  production                 mp37_lin3_1min_hist0{,_np4_4x1}_20260830_2114*
    309e2a8e  + both flags               mp37_p1nc_1min_hist0{,_np4_4x1}_20260831_1815*
    b6eb2159  + -fno-tree-vectorize      mp37_p2cv_1min_hist0{,_np4_4x1}_20260831_1833*
    5f77fefe  + -ffp-contract=off        mp37_p2cf_1min_hist0{,_np4_4x1}_20260831_1850*

The tree was restored afterwards and gated: `configure.wrf` back to
`-O2 -ftree-vectorize -funroll-loops`, `dyn_em/solve_em.F` `d66e9db1`, and
`main/wrf.exe` `f54ef3c962a1d6a0` -- the deployed binary, bit for bit, from a
32-object recompile, with zero `-ffp-contract=off` lines in the restore log.

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
`FCOPTIM` went back and all 32 `dyn_em` objects were recompiled from scratch
(recounted; "31" was the same extraction bug that produced "30");
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
