# RETRACTED: the `-inf` was real, and my refutation of it was not

This finding claimed that a `-inf` emitted during the timestep-matrix batch came
from two processes sharing the compile-time fixture, and that it "does not
reproduce". **Both claims were wrong.** The retraction is kept here rather than
deleted, because the way it was wrong is the point.

## What the finding said

The batch died on its fourth column with

    StreamError: STAGE f32 payload is -inf:
      'G33F STAGE 1 - micro_post_melt 0 brs 1 26 f32 FF800000'

and I attributed it to a concurrent test suite regenerating the fixture between
the tool's write and its build, producing a kernel whose `.f90` and `.h` held
different columns.

## Why that was wrong

**The rerun was serial, and it died in the same place.** No other writer, same
column, same record.

**And my reproduction had skipped a step.** The batch does three things per
column: write the manifest, run `g33_fixture_v1.py --write` to REGENERATE the
`.f90` and `.h` from it, then build. My reproduction wrote the manifest and
built. The generated sources are compile-time constants, so the build took
whatever column was generated LAST -- not the one I had just written. The "0
non-finite at every step" was measured on a different column.

A reproduction that does not reproduce is evidence only if it is faithful. Mine
was not, and it produced exactly the answer that let me stop looking.

## What is actually true

With the generation step included, column `(j, i) = (71, 147)`, `legacy`:

    nsplit 12  ( 5 s call)    0 non-finite
    nsplit  6  (10 s call)    0 non-finite
    nsplit  3  (20 s call)    0 non-finite
    nsplit  2  (30 s call)    8 non-finite   brs at level 26 = -inf

See `FINDING_thirty_second_step_overflows_v1.md`.

## What survives

The lock added alongside this finding is still worth having: the fixture IS a
shared compile-time constant, five test modules build through the same files,
and nothing was enforcing single-writer access. That hazard is real and was
never demonstrated to have fired. The lock guards it; it did not cause this.

The instrument note also survives, and gained a second instance. My first
reproduction searched each line for the substring `inf` and reported thousands
of hits, all of them the token `NR_INFLOW` -- the same defect corrected in the
analyzer the same day, where `"nmass" in algorithm` swallowed `nmass_dry`. Two
substring bugs and one unfaithful reproduction, in one investigation.
