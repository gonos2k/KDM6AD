# CCN initialisation reads one level past the top of `phb` and `ph_2`

Found by turning on runtime bounds checking, which this build has never had.

    At line 1969 of file start_em.f90
    Fortran runtime error: Index '41' of dimension 2 of array 'grid%phb'
    above upper bound of 40

## The defect

`dyn_em/start_em.F:1786`, inside the block that initialises the CCN number
`scalar(:,:,:,p_qnn)`:

    DO k=kts,kte
       dz8w(i,k,j) = (grid%phb(i,k+1,j)+grid%ph_2(i,k+1,j))/g &
                   - (grid%phb(i,k,j)  +grid%ph_2(i,k,j)  )/g
       z_sum = z_sum + dz8w(i,k,j)
       ... scalar(i,k,j,p_qnn) = f(z_sum)

The loop runs to `kte` while the body reads `k+1`, so at the last iteration it
reads one level above the top of `phb` and `ph_2`.

**It is the only one of the four such reads in the file that does this.** The
same `phb(i,k+1,j)` pattern appears three more times, each with a loop that stops
one short:

    .F:735   DO k=kts,kte-1     safe
    .F:815   DO k=kts,kte-1     safe
    .F:1786  DO k=kts,kte       <-- reads k+1 past the top
    .F:2131  DO k=1,   kte-1    safe

The block's own guard, twelve lines above at `.F:1774`, is written
`MAXVAL(scalar(its:MIN(ite,ide-1), kts:kte-1, ...))` -- `kte-1`. The upper bound
was known in the same block and missed in the fill loop.

## What it reaches

`dz8w(i,kte,j)` is computed from memory past the declared top. `z_sum`
accumulates upward and each level's CCN is set from the running sum before the
next increment, so the levels below `kte` use only in-bounds thicknesses. The
value that carries the out-of-bounds read is **the top model level's initial CCN
number**, on every column the block fills.

Whether that value matters to the forecast is NOT measured here. What is measured
is that it is computed from memory the array does not own.

## Why nobody had seen it

The deployed build compiles with `-w`, which suppresses every warning, and
without `-fcheck`. Turning warnings back on for this file yields 208, all
`-Wunused-dummy-argument` or `-Wunused-variable` and none about initialisation --
so the compiler was not going to say it either. It takes a runtime bounds check,
and this campaign had never run one.

## Scope, and what this experiment did NOT settle

The bounds-checked binary (`649b437f`, the 32 `dyn_em` objects with
`-fcheck=bounds`, 36 flagged compile lines) **aborted here, in initialisation,
before the first dynamics step**. So the dynamics were never bounds-checked, and
the question this experiment was run to answer --

> whether the i-cut seam is ordinary rounding sensitivity or exposes a source or
> extent defect

-- is **untested**. This finding is what the run hit on the way there. It is in a
different subsystem, it happens once, and it cannot be the seam, which is created
inside the RK loop at every step.

Reaching the dynamics under bounds checking needs this read corrected first, and
`start_em.F` is campaign source: not corrected here, and the correction is an
owner decision.

## Provenance

Binary `649b437f21d40191`, run `mp37_bnd_1min_hist0_20260831_200552_p89850`, exit
code 2, `experiment_valid` **false** with `invalid_reasons`
`["model_did_not_complete"]` -- the runner change that records a crashed run as
invalid, made earlier in this campaign, is what filed it correctly rather than as
a clean run with no output.

Source read from `dyn_em/start_em.F` in the campaign tree; line 1786 in the `.F`
corresponds to 1969 in the preprocessed `.f90` the runtime names. The tree was
restored afterwards and gated: `main/wrf.exe` `f54ef3c962a1d6a0`, bit for bit,
with zero `-fcheck` lines in the restore log.
