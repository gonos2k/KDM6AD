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

## The timestep matrix, and the operational call

The measurement above is a 5 s kernel call: the fixture's `dt` word is 60 s and
`nsplit = 12`. The operational configuration calls the kernel at 20 s, so the
number above was not the operational one and the finding did not say so.

Same column, `nsplit` varied:

| call dt | nsplit | mstep <= | legacy dry | Arm N dry | Arm N leaves | flux-weighted |
|---|---|---|---|---|---|---|
| 5 s | 12 | 1 | 1.374e-03 | -2.583e-05 | 1.8796 % | 2.0857 % |
| 10 s | 6 | 2 | 2.755e-03 | -5.201e-05 | 1.8879 % | 2.0951 % |
| **20 s** | **3** | **3** | **5.512e-03** | **-1.046e-04** | **1.8972 %** | **2.1067 %** |
| 30 s | 2 | 4 | 8.244e-03 | -1.568e-04 | 1.9023 % | 2.1157 % |

**At the operational 20 s call the answer is 1.8972 %**, and the ratio is
invariant across the range: 1.880 % to 1.902 %, a 1.2 % relative spread, while
`mstep` goes from 1 to 4.

The residuals themselves scale with the timestep almost exactly -- 2.00x, 4.01x
and 6.00x against dt ratios of 2, 4 and 6 -- which is what a per-step transfer
defect should do, and it is why the RATIO is the timestep-invariant quantity
and the residual is not.

## What this does and does not establish

It establishes that the moisture term is not an artefact of synthetic
stratification: a real column, real moisture profile, real hydrometeors and
real number fields give the size the coefficient work predicted.

It does NOT establish a forecast impact. One column, one time, and the ceiling
on this fixture is STRUCTURAL_ONLY for that reason. A column is an instance; the domain statistics in
`FINDING_number_basis_gap_v1` are what say how typical it is.

## Reproducing

    python3 harness/g33_fixture_v1.py --write --fixture-id=lc05_column_v1
    bash harness/g33_fortran/refine_build.sh --algo=<legacy|nmass> \
         --fixture=g33_fixture_lc05_column_v1 --nflux <outdir>
    <outdir>/g33_refine_driver 12 rezero 1 > arm.txt

then `g33_number_basis.from_stream(text, "nr")`. The manifest is committed, so
the column does not have to be re-extracted from the private forecast output.
