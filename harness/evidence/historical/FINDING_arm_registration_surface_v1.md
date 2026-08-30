# Adding one arm takes eight registrations, and I twice said the set was closed

`melt_g4` is the third time this campaign has added an arm, and the second time
I claimed to have found every place that needs to know about it. Both claims
were wrong, and the way they were wrong is the useful part.

## The eight

    g33_refine_driver.f90        ALGOTAG under a KDM6_ARM_* macro
    refine_build.sh              the --algo case list
    g33_fortran_bindings.py      FIELD_EXPR
                                 XFER_SITES  \
                                 CAP_SITES    > all three via _DERIVED
                                 TOP_SITES   /
                                 VARIANTS     (the overlay generator's --algo
                                               choices are sorted(VARIANTS))
    g33_expectation.py           _STRUCTURALLY_LEGACY
    g33_number_transport.py      NUMBER_TRANSFER_METRIC
    g33_refine_manifest.py       _ALGOS

## How each omission announced itself

Not one of them failed at the edit. `_ALGOS` failed in CI. `_STRUCTURALLY_LEGACY`
failed silently -- nothing at all. A partial `FIELD_EXPR` passed every table
check and died much later inside schema validation on a `QR_OUTFLOW` key that
had nothing to do with the edit. `VARIANTS` failed as an argparse "invalid
choice" from a build script. `CAP_SITES` failed as a `KeyError` inside the
overlay generator.

So the failure is late, and it names something other than the thing that is
wrong. That is what makes the count matter rather than the list.

## Why the earlier sweep said six and then said closed

It searched for files containing three or more arm-name LITERALS. `CAP_SITES`
and `TOP_SITES` have none -- they are populated by a loop over `_DERIVED`.
`VARIANTS` gets its melt entries from three assignment statements the sweep
counted as one file, not five tables. A sweep keyed on how a table LOOKS cannot
find a table that is built rather than written.

## What is done, and what is not

**Done.** The guard no longer enumerates. It DISCOVERS every module-level dict
in the bindings keyed on arm names, asserts the checked list covers it, and pins
all five against the driver's own `ALGOTAG` set in both directions. A table
added later fails a test that names it, instead of a build that does not.
`_DERIVED` is the one known partial table -- it maps derived arms to their base,
so it deliberately omits `legacy` and `conservative` -- and the guard says so
by name rather than by tolerance.

**Not done, deliberately.** The single `ARM_SPECS` descriptor that would
GENERATE the five tables from one declaration. It is the right shape and it is
what removes the class rather than reporting it. It is also 70 entries across a
1082-line module with 39 tests over it, at the end of a review-response batch,
which is the wrong moment: the risk of that edit is not the risk this finding
is about. It should be its own change with its own gate.

The guard is what makes deferring it safe. Without it, deferring means the next
arm finds the ninth registration point the way I found the eighth.
