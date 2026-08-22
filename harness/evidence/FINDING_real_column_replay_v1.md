# The kernel run on a real atmospheric column, and what Arm N leaves there

Every measurement in this campaign has been on a synthetic fixture. The
coefficient work in `FINDING_number_basis_gap_v1` read a real state but never
ran the kernel on one, because the fixture manifest requires the vertical anchor
`p` to be the same profile in every column, and real columns on
terrain-following levels are not.

With ONE column that requirement is satisfied trivially: a single column cannot
be transposed with another. `g33_fixture_lc05_column_v1` is a real column of the
operational 5 km case -- `(j, i) = (87, 117)`, over sea, 39 levels, `qv` from
1.85e-02 at the surface to 3.19e-06 at the top -- taken from the 20 s `mp37`
forecast frame, which carries `QNRAIN` in ten of its levels.

Two schema rules had to be widened for it, both hard-coded values that forbade
the experiment rather than protecting anything at `B = 1`:

- `science_role` was fixed at `arithmetic_synthetic`, so a real column could
  only be registered by declaring something false about itself. It is a
  declared closed set now, and the decision ceiling is unchanged --
  STRUCTURAL_ONLY, because one column at one time is an instance, not a sample.
- The column anchor must be unique across columns and constant down each one.
  Both are the mechanics of a transposition guard, and at `B = 1` the first is
  vacuous while the second forbids any real profile: nothing is constant in the
  vertical in a real column. The waiver is exactly and only `B = 1`.

## The measurement

First call, `nsplit = 12`, `rezero`, `nr`, residual over starting inventory:

| arm | moist ledger | dry ledger | moist, from XFER | dry, from XFER |
|---|---|---|---|---|
| `legacy` | 1.402e-03 | 1.374e-03 | 1.402e-03 | 1.374e-03 |
| **`nmass`** | **-3.271e-16** | **-2.584e-05** | **1.026e-08** | **-2.583e-05** |

**Arm N leaves 1.88 % of the legacy dry defect on a real atmospheric column.**

The coefficient analysis over the whole LC05 domain predicted 1.92 % as a
median and 1.98 % flux-weighted. A closed-form estimate from the state file and
a kernel run on a column of it agree to within a tenth of a percentage point.

The moist row carries the same distinction the gradient fixture showed: the
recovered residual is algebraically forced to zero and reads 3.3e-16, while the
independent XFER path gives 1.0e-08 -- the honest figure, and still two orders
below the f32 epsilon of 1.19e-07.

## What this does and does not establish

It establishes that the moisture term is not an artefact of synthetic
stratification: a real column, real moisture profile, real hydrometeors and
real number fields give the size the coefficient work predicted.

It does NOT establish a forecast impact. One column, one time, one call,
`mstep = 1`, and the ceiling on this fixture is STRUCTURAL_ONLY for that
reason. A column is an instance; the domain statistics in
`FINDING_number_basis_gap_v1` are what say how typical it is.

## Reproducing

    python3 harness/g33_fixture_v1.py --write --fixture-id=lc05_column_v1
    bash harness/g33_fortran/refine_build.sh --algo=<legacy|nmass> \
         --fixture=g33_fixture_lc05_column_v1 --nflux <outdir>
    <outdir>/g33_refine_driver 12 rezero 1 > arm.txt

then `g33_number_basis.from_stream(text, "nr")`. The manifest is committed, so
the column does not have to be re-extracted from the private forecast output.
