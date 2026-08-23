# The `-inf` was two processes sharing one compile-time fixture

The timestep-matrix batch died on its fourth column with the stream parser
refusing a record:

    StreamError: STAGE f32 payload is -inf:
      'G33F STAGE 1 - micro_post_melt 0 brs 1 26 f32 FF800000'

A kernel emitting `-inf` for a bulk density is a finding if it is real. It is
not real.

## It does not reproduce

Column `(j, i) = (71, 147)`, `legacy`, the same four call steps, run alone --
decoding every `f32`/`f64` payload rather than testing the line for a substring:

    nsplit 12  ( 5 s)   0 non-finite
    nsplit  6  (10 s)   0 non-finite
    nsplit  3  (20 s)   0 non-finite
    nsplit  2  (30 s)   0 non-finite

## What actually happened

The fixture is a COMPILE-TIME constant. `g33_real_column_batch` therefore
rewrites `harness/g33_fixture_lc05_column_v1.json` for every column and
regenerates the `.f90` and `.h` beside it -- one fixed path in the working
tree, not a private copy. Five test modules build fixtures through the same
files.

The full test suite was running concurrently. Between this tool's write and its
build, the artefacts were regenerated, and the build took a `.f90` and a `.h`
holding **different columns**. That kernel compiled, ran, and produced `-inf`
from a state that never existed.

## Two things this costs, and one it does not

It cost the timestep matrix, which is re-run serially.

It cost nothing else measured today: every other result came from a build that
held the lock on its own inputs by being the only writer at the time. The
23-column batch, the gradient-fixture arms and the MPI runs do not share this
path with anything that ran beside them -- but nothing was ENFORCING that,
which is the actual defect.

It did NOT cost the earlier full-suite failure of
`test_the_ONE_validator_reads_the_probe_arm_too`, which has the same shape --
a suite run reading files while they were edited -- and the same cause: work
running concurrently with something that owns global mutable state.

## The fix

An advisory lock. The tool refuses to start if `.g33-fixture-lock` exists,
writes its pid and scope into it, and removes it where it restores the manifest.
It already refused to start on a manifest dirty against HEAD; that catches a
crashed predecessor and not a live peer.

That is a guard and not a cure. The cure is a fixture that is not a shared
compile-time constant, which is a build-system change and is not made here.

## The instrument that reported it was also wrong

The first attempt to reproduce this searched each line for the substring `inf`
and reported thousands of hits at every step -- all of them the token
`NR_INFLOW`. That is the same defect corrected in the analyzer the same day,
where `"nmass" in algorithm` swallowed `nmass_dry`
(`FINDING_arm_nd_closure_v1`, owner review §9). A substring test on a name
cannot fail; it can only be wrong quietly. The measurement above decodes the
payload.
