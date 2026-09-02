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
0 / 28 / 71 / **75** of 197 fields at 0 / 20 / 40 / 60 s.

That shows this defect is not NECESSARY for a decomposition difference. It does
NOT show the two are independent: this build changed two things at once, the CCN
loop and the bounds instrumentation, and the cell that separates them -- CCN
corrected with production flags -- is a separate arm. An earlier version said
"independent by measurement"; that is withdrawn.

**It carries the same structural signature**, checked as SETS rather than
counts, since equal cardinality is not equal membership. Signature, not identity:
cell masks, signs and magnitudes were not compared.

    t      production   checked   common   prod-only   checked-only   Jaccard
    20 s       28         28        28         0            0          1.000
    40 s       71         71        71         0            0          1.000
    60 s       77         75        74         3            1          0.949

Identical field sets at 20 and 40 s. The four differing at 60 s are `ACSNOM`,
`SNOW`, `SNOWH` and `VIS_SFC_CAPPED` -- accumulation and capped-diagnostic fields
that cross a threshold on or off. The `PH` footprint at 20 s sits in the same
three interior bands plus the eastern zone in both, weaker in the checked build.
The 75 rather than 77 is expected: `63b788a1` is not `f54ef3c9`.

The change was reverted afterwards. `start_em.F` is back to `5c6d6faa` and
`main/wrf.exe` to `f54ef3c962a1d6a0`, bit for bit.

## Corrected alone, with production flags: no effect at all

The bounds-checked arm changed two things at once, so it could not separate them.
This one changes only the loop bound, on the production flags (`6797945d`):

    np=1 against production np=1     0 / 0 / 0 / 0  of 197 fields
    np=1 against 4x1                 0 / 28 / 71 / 77

**The correction changes nothing in either decomposition's output, bit for bit**
(raw `uint32`, 197 fields, every frame):

    corrected np=1 vs production np=1     0 0 0 0
    corrected 4x1  vs production 4x1      0 0 0 0

Both endpoints being bitwise equal, the difference tensors are identical by
construction, and the differing-field sets confirm it: Jaccard 1.000 at 20, 40
AND 60 s. **So this defect contributes nothing to the production seam**, from a
single-intervention arm compared on both decompositions.

The `np=1`-only version of this comparison was published first and was not
enough: equal counts are not equal sets, and `X_fix1 = X_prod1` does not imply
`X_fix4 = X_prod4`, since the value an out-of-bounds read returns can depend on
rank count and memory layout. The `4x1` cell was the one that mattered.

On the slot itself: what is measured is that **no effect of the correction is
observable in the 197 sampled output fields through 60 s**, on either
decomposition. That is not the same as "the slot is never read" -- it could be
read and multiplied by zero, or cancel, or fall below a rounding threshold, or
reach only state the forecast file does not carry. Proving it is never read needs
source tracing or a sentinel, neither of which was done.

It also places the earlier 75: that came from the bounds instrumentation, not
from the correction.

## The slot has no consumer, so no padding policy is needed

Both readers of `qnn` stop one short of it, in source:

    share/module_bc.F   flow_dep_bdy_qnn   ktf = kde-1, DO k = kts, ktf
    dyn_em/solve_em.F   microphysics_driver called with KTE = min(k_end, kde-1)

`k_end` is `kpe`, so the driver receives `kde-1` and the microphysics never sees
`k = kte`. `p_qnn` appears nowhere else in `dyn_em`, `phys` or `share`.

So the two sides agree: the measurement found no observable effect, and every
reader found in the forward path stops one short of the slot.

**That is a reader audit, not an exhaustive proof.** `qnn` is a member of the
generic `scalar` container, so code can reach it as `scalar(:,:,:,is)` without
naming `p_qnn`; the generic scalar-update paths inspected also stop at `kde-1`,
but a literal search for the symbol is not by itself a proof that nothing reads
the slot. The correction is therefore just

    DO k = kts, kte-1

with no padding assignment to decide -- the question of what should fill
`scalar(:,kte,:,p_qnn)` does not arise, because nothing reads it.

## Corrected, permanently

Applied on the owner's decision, 2026-09-02:

    dyn_em/start_em.F   5c6d6faa -> 5090ca10   DO k=kts,kte  ->  DO k=kts,kte-1
    main/wrf.exe        f54ef3c9 -> 6797945d

No padding assignment was added, because no reader needs one.

The rebuild reproduced `6797945de1ada48f`, the same hash the temporary fix-only
build produced earlier from the same source and flags -- so the build is
deterministic across the experiment and the permanent change.

Nothing recorded against `f54ef3c9` moves: that binary and this one produce
bitwise identical output on both `np=1` and `4x1`, 197 fields, every frame to
60 s, which is the measurement above. `f54ef3c9` is now the historical campaign
reference and `6797945d` is the deployed one.

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
