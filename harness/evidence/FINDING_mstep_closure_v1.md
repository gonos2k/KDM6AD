# The number defect above one sub-step, and the mass control that could not see

Every claim in this campaign about the number residual carries the scope line
"mstep > 1 not re-run". That understated it. The residual was not merely un-run
above one sub-step: no reader in the harness could measure it there.

## Why the archive had nothing above mstep == 1

`column()` recovers the per-interface transfers by inverting the update, which
needs exactly one sub-step, and it says so. The TRANSPORT-ONLY closure is the
path that does not -- it reads the emitted surface accumulator and the pre/post
column inventory, and its docstring says "no recursion".

Its GUARD went through `column()` anyway. Asking whether the surface cap bound
was implemented as "does the recovered transfer match the emitted flux", so
every mstep > 1 call returned `None` and was dropped. Measured on
`g33_fixture_multisubcycle_v1`: at nsplit 3, `closure()` succeeds on all 13 of
the 27 (call, column, species) rows with mstep > 1, and `column()` is blind to
every one of them.

The guard now asks the same question of `G33F CAPIN`, whose bottom-cell own
outflow IS what left, summed over sub-steps and needing no inversion. Validated
against the old test where both can see: agreement on 218 of 220 rows, and the
two exceptions are at 2.7e-11 relative and at an absolute scale of 1e-10 --
a tolerance comparing near-nothing, not a disagreement about capping.

**At mstep == 1 the old test still runs, unchanged**, so every figure published
under it reproduces bit for bit. The new one applies only where the old one
could not see.

An INTERIOR cap is a different question and is now LABELLED rather than
excluded. Conflating the two was tried first and was wrong: it drops every row
with an interior cap for a reason the arithmetic never had. Where an interior
cap binds the residual is still what the operator did -- the capped transfer is
the one that ran -- it is simply no longer transport alone.

## The matrix

Transport-only closure, residual over surface flux, single tile, `rezero`:

| arm | NCL | nsplit 3, mstep<=10 | | | nsplit 24, mstep<=2 | | |
|---|---|---|---|---|---|---|---|
| | | qr | nr | ni | qr | nr | ni |
| `legacy` | 000 | -27.645% | 13.224% | -- | 0.000% | 13.296% | 6.772% |
| `nmass` | 100 | -27.608% | -0.000% | -- | 0.000% | 0.000% | 0.000% |
| `lncmin` | 001 | -27.645% | 13.224% | -- | 0.000% | 13.296% | 6.772% |
| `nmasslncmin` | 101 | -27.608% | -0.000% | -- | 0.000% | 0.000% | 0.000% |
| `conservative` | 010 | -0.000% | 13.224% | 8.431% | 0.000% | 13.296% | 5.359% |
| `cons_nmass` | 110 | -0.000% | -0.000% | -0.000% | 0.000% | 0.000% | -0.000% |
| `cons_lncmin` | 011 | -0.000% | 13.224% | 8.431% | 0.000% | 13.296% | 5.359% |
| `cons_nmasslncmin` | 111 | -0.000% | -0.000% | -0.000% | 0.000% | 0.000% | -0.000% |

Three things it says.

**Arm N's closure is not an mstep == 1 artefact.** At mstep up to 10 the number
residual still goes to zero, against a legacy defect of 13.2%.

**The N x C masking survives too.** At nsplit 24 the ice-number residual runs
6.772 (legacy) -> 5.359 (C alone) -> 0.000 (N present), the same shape the
factorial coefficients named: C moves it only while N is absent.

**C does its own job on MASS at high mstep**, which one sub-step could not show:
the legacy mass closure is -27.6% at mstep 10 and the conservative arms are at
roundoff.

## The mass control could not detect what it was controlling

`FINDING_arm_n_closure_v1` reports, under "The mass control is untouched":

    qr   1.412673e-16  ==  1.412673e-16
    qi   5.551115e-17  ==  5.551115e-17
    Bit for bit. A number fix that moved water would be a different change.

Those two quantities are ~0 BY CONSTRUCTION of their weight in EVERY arm --
`g33_number_transport.report` says so in its own header. A control that reads
zero whatever happens cannot detect a change, so this one never tested the
sentence it was offered for.

Read out of the same published bundles the claim rests on --
`kdm6ad-g33m-armn/legacy-001` against `nmass-001`, member `n12.rezero.txt`,
G33R final state, 12 cells per field:

| field | cells differing | max relative | max absolute |
|---|---|---|---|
| `qv` | 3 | 1.429e-05 | 1.490e-08 |
| `nccn` | 6 | 6.175e-06 | 6.784e+03 |
| `th` | 3 | 2.291e-07 | 6.104e-05 |
| `ni` | 1 | 2.051e-07 | 1.250e-01 |
| `qi` | 1 | 1.919e-07 | 3.411e-13 |
| `qc` | 1 | 1.872e-07 | 1.164e-10 |
| unchanged | | `nr` `qg` `qr` `qs` | |

f32 epsilon is 1.19e-07, so `qv` moves by roughly 120 ulp. **Arm N moves
water.** It is expected that it does: number sets fall speed, fall speed sets
mass sedimentation, and sedimentation sets the latent heating that moves `qv`
and `th`. A number fix that left water alone would be the surprise.

## What changes and what does not

`G33-NUMBER-010`'s result stands -- the number residual collapses, the
mechanism chain is closed, and none of that rested on the mass control. What is
withdrawn is one supporting sentence: "A number fix that moved water would be a
different change" is contradicted by the claim's own bundles, and the two
figures offered as its control cannot bear on it either way.

The scope line every number claim carries should now read that mstep > 1 HAS
been measured on this fixture and the defect persists, rather than that it was
not re-run.

## Not claimed

One fixture, f32, single tile, `rezero`. Not a forecast impact and not a
precipitation change: `qv` moving by 1.4e-05 relative over one call is a
statement about the operator, not about weather.

## Reproducing

    bash harness/g33_fortran/refine_build.sh --algo=<arm> \
         --fixture=g33_fixture_multisubcycle_v1 --nflux <outdir>
    <outdir>/g33_refine_driver <nsplit> rezero 3 > arm_n<nsplit>.txt

then `g33_number_transport.closure_report(text)`; `multistep=False` restores the
mstep == 1 restriction the old guard imposed by accident.
