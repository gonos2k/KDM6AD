# Scalar advection produces the negative graupel volumes; the initial condition already carries the zero ones

Owner review item 20, third priority: find the operator that first breaks
`bg >= 0` and `qg > 0 => bg > 0`, with mass below the f32 representability
threshold kept as its own class.

## The probe

Four counters in `solve_em.F`, over the patch, `np = 1`, ten minutes. Each
counts, at one operator boundary, cells with `bg < 0`; cells with `qg > 0` and
`bg <= 0` where an admissible positive `bg` EXISTS in f32 (`qg >= 100*eta`,
`eta = 1.4012985e-45`); and the same where it does not.

| boundary | emissions | `bg<0` max | `bg<0` mean | steps with `bg<0` | `qg>0,bg<=0` max |
|---|---|---|---|---|---|
| RK entry, before advection | 30 | 6 | 2.2 | 25 | 635 |
| after scalar advection | 450 | **80,586** | 39,560 | 423 | 21,896 |
| before microphysics | 30 | 2,570 | 2,288 | 29 | 4,104 |
| after microphysics | 30 | 6 | 2.2 | 25 | 39 |

## Scalar advection is the producer

At most 6 cells carry a negative volume entering the step. Scalar advection
produces up to **80,586**, and **2,570** are still there when microphysics is
called. Microphysics then takes it back to 6.

The 450 emissions at the second boundary are 15 per step -- the counter sits
inside the scalar loop, so those are mid-loop transients; the settled
post-dynamics number is the third row, 2,570 max and 2,288 mean.

## Microphysics is the consumer, and does not finish

It removes nearly all of it -- 2,570 negatives to 6, and 4,104 invalid zeros to
39 -- but a residue survives every step. That residue is what the output census
sees.

## The chain is closed, and the initial condition is already invalid

Step N's RK entry equals step N-1's after-microphysics exactly, at every step and
in all three counters, so nothing between the two touches the field:

    step   RK entry (neg, invalid, unrepr)   after microphysics
      1        (0,  635,  0)                    (0,   6,  0)
      2        (0,    6,  0)                    (2,  13,  0)
      3        (2,   13,  0)                    (2,  20,  0)
      ...
     30        (1,   38, 31)                    (0,  39, 28)

**635 at step 1 is the initial condition.** Before any operator has run, the
input state already holds 635 cells with `qg > 0` and `bg <= 0` where an
admissible positive `bg` exists. Microphysics clears that to 6 in one step, and
the count then grows monotonically to 39 over thirty steps, with the
unrepresentable class appearing after step ~28 and reaching 31.

## What this settles

- **Settled**: scalar advection produces the negative volumes; microphysics
  consumes almost all of them; a residue of about 0-2 negative and a growing
  count of invalid zeros survives each step; and the initial condition violates
  the invariant before any operator runs.
- **Settled since**: `qib` is INSIDE the positive-definite option and the input
  to advection is non-negative -- see the clamp arm below. The limiter is
  insufficient for this field, not bypassed.
- **Not measured**: any consequence. This counts states, not their effect.

## Reproducing

Four counters at `solve_em.F` before the RK loop, after `scalar_tile_loop_2`,
before `microphysics_driver`, and after it; `np = 1`, 10 minutes, history 1.


## The clamp arm: advection makes them, it does not amplify them

`scalar_adv_opt = 1` in this case's namelist, and `original = 0` in the generated
`module_state_description.F`, so the positive-definite branch is the one taken --
`qib` is inside the limiter, not outside it.

That leaves the limiter's own precondition: a positive-definite scheme guarantees
a non-negative result from a NON-NEGATIVE input, and up to 6 cells enter each
step already negative. To separate the two, a diagnostic arm zeroes every
negative `bg` at RK entry, before advection, and counts as before. This changes
the trajectory on purpose.

| point | `bg<0` max | `bg<0` mean |
|---|---|---|
| RK entry, before clamp | 6 | 2.1 |
| RK entry, **after clamp** | **0** | **0.0** |
| after scalar advection | **80,585** | 39,559.2 |
| before microphysics | 2,570 | 2,288.1 |
| after microphysics | 6 | 2.1 |

Unclamped, the same run gave 80,586 and 39,559.9.

**Handed a strictly non-negative field, advection still returns up to 80,585
negative cells** -- one fewer than with the six seeds present. The seeds account
for at most a single cell in eighty thousand, and every downstream count is
unchanged. So advection PRODUCES the negative volumes; it does not amplify
inherited ones.

## Localised: the last stage does renormalise, and `qg` goes negative too

Labelling the same counter with `rk_step` and the scalar index `is`, and counting
`qg` alongside `qib`. One step, two-minute run, `np = 1` (`P_QIB = 5`):

    point  rk is  qib<0   qg<0
    RK entry            0       0
      2     1   2      0   19849
      2     1   3      0   19849
      2     1   4      0   19849
      2     1   5  29887   19849      <- qib's own update
      2     2   5  57851   42154
      2     3   2  57851    1172
      2     3   5   1535    1172      <- final stage renormalises
    before microphysics  1535    1172

Three things follow, and the third narrows the finding above.

**1. It is `qib`'s own update.** The count moves at `is = 5` and nowhere else, so
this is not spillover from another scalar.

**2. The final stage DOES renormalise, and does not finish.** Stage 3 takes
`qib` from 57,851 negatives to 1,535 -- the positive-definite treatment acts on
the last stage as WRF designs it, and leaves about 1,500 behind. The 80,586 in
the table above is an INTERMEDIATE-stage count; stages 1 and 2 are unbounded
scratch by design.

**3. `qg` goes negative too, in comparable numbers** -- 19,849, then 42,154, then
1,172 surviving into microphysics under `moist_adv_opt = 1`. So this is **not a
paired-moment defect**. Graupel MASS behaves the same way. The hypothesis in the
previous version of this section -- that a moment advected independently of its
mass drifts from it -- is not what the measurement shows, and is withdrawn.

**Still not established**: why the final-stage renormalisation leaves any. The
update carries tendencies besides advection and couples through `mu_old`/`mu_new`;
which of those defeats the bound is not measured here.

**Scope**: this localisation is a two-minute run, so its counts are not the
ten-minute maxima quoted above; the ordering and the `is = 5` attribution are
what it establishes.


## Not the lateral boundary: the residue is spread like the field itself

The surviving negatives could come from the specified and relaxation zones, which
add a non-advective tendency the positive-definite bound does not cover. Bucketing
every cell with `bg < 0` or `qg < 0` before microphysics by its distance `d` to
the nearest lateral boundary (`spec_zone = 1`, `relax_zone = 4`, so the treated
frame is `d <= 4`), six steps, grid 234 x 282 x 39:

| zone | negatives | share | share of cells | enrichment |
|---|---|---|---|---|
| boundary, `d <= 4` | 1,370 | 8.32% | 7.67% | **1.08x** |
| interior, `d >= 5` | 15,100 | 91.68% | 92.33% | **0.99x** |

Normalised by how many cells each zone holds, the two are the same. The frame is
7.67% of the domain and carries 8.32% of the negatives; 85% of them sit at
`d >= 9`, far inside.

**The boundary treatment is not the source.** The residue is distributed like the
graupel field, not like the boundary zone.

The absolute counts alone would have suggested the opposite reading in either
direction -- the interior looks dominant because it is 92% of the grid. The
enrichment ratio is the statement; the raw counts are not.

What remains as a candidate is a non-advective tendency the bound does not cover
anywhere in particular -- diffusion is the obvious one, being no more
positive-definite in the interior than at the edge -- or the mass coupling
itself. Neither is measured here, and separating them needs a probe on the
tendency terms rather than on the field.
