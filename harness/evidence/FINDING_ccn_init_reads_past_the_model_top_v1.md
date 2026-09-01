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

## What it reaches -- less than first written

`phb` has bound 40 and the runtime caught index 41, so `kte = 40` here and the
physical mass levels are `kts .. kte-1` = 1..39. That is also the range this
block's own guard uses. So:

- levels 1..39, the physical mass levels, read `k+1` up to 40 and are **in
  bounds and correct**;
- the out-of-bounds read happens only at `k = 40`, and the value it produces is
  written to `scalar(i,40,j,p_qnn)` -- the **top allocated slot, above the
  physical mass-level range**, not the top model level.

An earlier version of this finding said "the top model level's initial CCN
number". That was wrong: no physical level is affected. Whether anything
downstream reads the `k = kte` slot is not measured, and until it is, the
consequence is a value written from undefined memory into a slot that may never
be consumed.

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

-- was untested at the time. It has since been answered by correcting this read
temporarily and re-running: see below.

## Corrected temporarily, and what that showed

`DO k=kts,kte` was changed to `DO k=kts,kte-1` -- one line, verified by diff --
and the 32 objects rebuilt with `-fcheck=bounds` (binary `63b788a1`). Both
decompositions then ran the whole first minute:

    np=1   exit 0, SUCCESS COMPLETE, 0 bounds violations
    4x1    exit 0, SUCCESS COMPLETE, 0 bounds violations on all four ranks

So this read was the only array-bounds violation on that path, and correcting it
lets the check reach the dynamics, which is what it was run for.

**And the seam is still there**: `np=1` against `4x1` on that binary differs in
0 / 28 / 71 / **75** of 197 fields at 0 / 20 / 40 / 60 s. So the two defects are
independent BY MEASUREMENT rather than by argument -- removing this one does not
remove the seam.

The 75 rather than 77 is expected: `63b788a1` carries the correction and is a
different binary from `f54ef3c9`, so its trajectory is not production's.

The change was reverted afterwards. `start_em.F` is back to `5c6d6faa` and
`main/wrf.exe` to `f54ef3c962a1d6a0`, bit for bit. **The permanent correction,
and the question of what should fill the `k = kte` slot, remain owner
decisions.**

It is also probably not related to the seam, but "it happens once" is not the
reason -- a one-time initialisation error perturbs the state and can seed a later
divergence perfectly well. The reasons that do apply are that the affected slot
is outside the physical mass-level range, and that the seam's first appearance
was traced to `ww` in `rk_step_prep`, which does not read `p_qnn`. Whether the
`k = kte` slot enters any stencil is unmeasured, so this is a strong expectation
and not a demonstration.

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
