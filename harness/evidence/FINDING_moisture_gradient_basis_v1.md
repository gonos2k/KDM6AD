# The two number ledgers separated on a fixture built to separate them

`FINDING_number_basis_gap_v1` established that Arm N closes the OPERATOR's
number ledger, which is moist, while the physical column number is taken in dry
mass -- and that NO published fixture could show the difference, because every
stream in the archive carries `qv` UNIFORM in the column. Under a uniform
profile the two ledgers differ by a constant factor per column and it cancels
out of every ratio.

This is the fixture that separates them, and the measurement on it.

## The schema forbade the experiment

The fixture manifest fixed `anchor_fields` at `{vertical: p, column: qv}`, and
the column anchor must be constant along K -- it is a transposition detector.
So a vertical moisture gradient was UNREPRESENTABLE in the fixture format, and
the reason the basis question had no matched control was a schema rule, not a
scientific obstacle.

The column anchor is DECLARED now. Whichever field is named must still be
unique across B and constant down each column, so nothing escapes the
transposition guard; `nccn` has those properties and carries the anchor here.
Every existing fixture declares `qv` and validates exactly as before.

## The fixture

`g33_fixture_moisture_gradient_v1` differs from
`g33_fixture_boundary_mapping_v1` in `qv` ALONE. Every other field, forcing and
parameter is identical, so it is that fixture's matched control for the basis
question and nothing else moves.

| column | qv, top to bottom | in-column spread |
|---|---|---|
| 1 | 5.0e-04, 2.0e-03, 6.0e-03, 1.4e-02 | 0.964 |
| 2 | 7.0e-04, 2.6e-03, 7.5e-03, 1.7e-02 | 0.959 |
| 3 | 4.0e-04, 1.5e-03, 4.5e-03, 1.1e-02 | 0.964 |

Against exactly 0.0 in every published stream that carries `qv`.

## The measurement

First call, `nsplit = 12`, `rezero`, `nr`. Residual over starting inventory:

| arm | column | moist ledger | dry ledger |
|---|---|---|---|
| `legacy` | 1 | 3.849e-03 | 3.788e-03 |
| `legacy` | 2 | 3.690e-03 | 3.618e-03 |
| `legacy` | 3 | 3.538e-03 | 3.492e-03 |
| **`nmass`** | 1 | **3.256e-17** | **-6.588e-05** |
| **`nmass`** | 2 | **-2.654e-17** | **-7.709e-05** |
| **`nmass`** | 3 | **5.070e-17** | **-4.989e-05** |

**Arm N closes the operator's ledger to roundoff and leaves a residual against
the physical one.** That is the first direct demonstration of it: on every
previous fixture the two columns of this table were the same number times a
constant.

Size: the dry residual Arm N leaves is 1.7 % of what legacy left against the
same measure. Consistent with the real-atmosphere coefficient in
`FINDING_number_basis_gap_v1` -- median 0.33 %, p90 4.62 % over 2 507 544 LC05
interfaces -- this fixture's gradient being steeper than the median real column.

## It is an identity, not an observation

With `A` the density the arm weights the interface transfer by and `B` the
ledger's,

    R = sum_j a_j * dz_j * ( B_{j+1} * A_j / A_{j+1} - B_j )

Evaluated from the same recovered transfers, `predicted / measured` is
**1.00000000 on all six rows** where the residual is above roundoff. Where
`A == B` every term vanishes ALGEBRAICALLY, and on this fixture it also
vanishes exactly: Arm N's moist prediction is `0.000000e+00` in all three
columns, against a measured residual of 1e-10 on a starting inventory of 3e+06.
Exactness is a property of these particular f32 values dividing cleanly, not of
the arithmetic -- `B_{j+1} A_j / A_{j+1} - B_j` is a division and a multiply
that round, and a synthetic profile lands at 1e-14 instead. The claim is the
algebraic one; the bit-exact zero is a bonus this fixture happens to give.

Its DRY prediction is not zero in any sense: -1.751e+02, -2.195e+02, -1.529e+02.

So the remaining defect follows from the source equation rather than from the
size of a number somebody observed, and the arm that would remove it is
determined: weight by `rho/(1+qv)` instead of `rho`, which makes every term of
the dry prediction vanish the same algebraic way the moist one does now.

## The same result from the ACTUAL transfer records

The table above recovers the transfers from the endpoints, so a residual built
on them and a prediction built on them share their input: the ratio of
1.00000000 is an algebraic check, not an independent measurement. The kernel
emits its own surface transfer in the `XFER` records, which shares nothing with
the recovery. Residual over starting inventory, first call, `nr`:

| arm | column | moist, from XFER | dry, from XFER | dry XFER / dry recovered |
|---|---|---|---|---|
| `legacy` | 1 | 3.849e-03 | 3.788e-03 | 1.000004 |
| `legacy` | 2 | 3.690e-03 | 3.618e-03 | 0.999989 |
| `legacy` | 3 | 3.538e-03 | 3.492e-03 | 0.999989 |
| `nmass` | 1 | **5.775e-08** | -6.583e-05 | 0.999128 |
| `nmass` | 2 | **-4.660e-08** | -7.714e-05 | 1.000601 |
| `nmass` | 3 | **6.498e-10** | -4.989e-05 | 0.999987 |

The dry residuals agree with the recovered ones to better than 0.1 %. **The
moisture term is an independent measurement.**

And the moist row corrects a number in this finding. `A == B` makes the
RECOVERED moist residual algebraically zero, so its 1e-17 is forced by the
arithmetic and is not a measurement of anything. The honest figure is the XFER
path's 5.8e-08 relative -- still below the f32 epsilon of 1.19e-07, so "Arm N
closes the operator's ledger to roundoff" stands, but at roundoff and not at
1e-17.

## What this does NOT do

It does not run that arm. Arm N_d is a change to the frozen kernel and the
existing freeze-lift says in its own text that the dry-density question is a
separate one it does not touch. `REQUEST_freeze_lift_arm_nd.md` asks for it,
against these numbers.

It is also not a forecast impact, a precipitation change, or a claim about a
real atmosphere: one synthetic fixture, chosen gradient, f32, first call,
`mstep = 1`.

## Reproducing

    python3 harness/g33_fixture_v1.py --write --fixture-id=moisture_gradient_v1
    bash harness/g33_fortran/refine_build.sh --algo=<legacy|nmass> \
         --fixture=g33_fixture_moisture_gradient_v1 --nflux <outdir>
    <outdir>/g33_refine_driver 12 rezero 3 > arm.txt

then `g33_number_basis.from_stream(text, "nr")`.
