# Negative graupel volumes appear during the scalar-update interval

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
| after scalar-update interval | 450 | **80,586** | 39,560 | 423 | 21,896 |
| before microphysics | 30 | 2,570 | 2,288 | 29 | 4,104 |
| after microphysics | 30 | 6 | 2.2 | 25 | 39 |

## Localisation to the scalar-update interval

At most 6 cells carry a negative volume entering the step. The counter after
the scalar-update interval reaches **80,586**, and **2,570** remain when
microphysics is called. After microphysics the maximum is 6. This interval
contains advection, other tendencies and mass coupling; the counts do not
isolate which term creates the final negative values.

The 450 emissions at the second boundary are 15 per step -- the counter sits
inside the scalar loop, so those are mid-loop transients; the settled
post-dynamics number is the third row, 2,570 max and 2,288 mean.

## Microphysics is the consumer, and does not finish

The before/after-microphysics maxima are 2,570 versus 6 negative volumes and
4,104 versus 39 states with `qg > 0, bg <= 0`. These are separate maxima across
the run, not a paired transition for one cell or step. Negative volumes remain
at 25 of 30 after-microphysics boundaries; invalid paired states also remain.

## Boundary counts agree; the first RK entry already contains invalid states

Step N's RK-entry COUNTS equal step N-1's after-microphysics counts in all
three recorded categories. This does not establish equality of values or
locations. A raw-bit field comparison or checksum was not recorded:

    step   RK entry (neg, invalid, unrepr)   after microphysics
      1        (0,  635,  0)                    (0,   6,  0)
      2        (0,    6,  0)                    (2,  13,  0)
      3        (2,   13,  0)                    (2,  20,  0)
      ...
     30        (1,   38, 31)                    (0,  39, 28)

**635 is the count at the first RK entry.** At that boundary the state
already holds 635 cells with `qg > 0` and `bg <= 0` where an
admissible positive `bg` exists. Microphysics clears that to 6 in one step, and
the count then grows monotonically to 39 over thirty steps, with the
unrepresentable class appearing after step ~28 and reaching 31.

## What this settles

- **Observed**: negative counts increase across the scalar-update interval
  and fall across microphysics. The recorded small negative residue and invalid
  nonpositive-volume counts remain after microphysics; the first RK entry already
  violates the paired-state invariant.
- **Observed**: `qib` uses the positive-definite option, and the clamp arm
  provides nonnegative RK-entry input. This does not isolate the pure advection
  operator or show a violation of the limiter's own preconditions.
- **Not measured**: any consequence. This counts states, not their effect.

## Reproducing

Four counters at `solve_em.F` before the RK loop, after `scalar_tile_loop_2`,
before `microphysics_driver`, and after it; `np = 1`, 10 minutes, history 1.


## The clamp arm: inherited negative RK-entry values are not necessary

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
| after scalar-update interval | **80,585** | 39,559.2 |
| before microphysics | 2,570 | 2,288.1 |
| after microphysics | 6 | 2.1 |

Unclamped, the same run gave 80,586 and 39,559.9.

**With nonnegative RK-entry input, the scalar-update interval still reaches
80,585 negative cells**, compared with 80,586 without the clamp. The displayed
downstream counts are also nearly unchanged. Thus inherited RK-entry negatives
are not necessary for this pattern. A difference of one in aggregate maxima
does not bound the seeds' effect on individual cells, amplitudes or locations,
and the experiment does not isolate advection from the other update terms.

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
1,172 surviving into microphysics under `moist_adv_opt = 1`. Negativity is
therefore not confined to the volume field. The counters do not test the
mass/volume ratio or their co-location; mutual consistency of the two moments
remains a separate question. The prior claim that this refutes a paired-moment
defect is withdrawn.

**Still not established**: why the final-stage renormalisation leaves any. The
update carries tendencies besides advection and couples through `mu_old`/`mu_new`;
which of those defeats the bound is not measured here.

**Scope**: this localisation is a two-minute run, so its counts are not the
ten-minute maxima quoted above; the ordering and the `is = 5` attribution are
what it establishes.


## Weak boundary enrichment under whole-grid normalisation

The surviving negatives could come from the specified and relaxation zones, which
add a non-advective tendency the positive-definite bound does not cover. Bucketing
every cell with `bg < 0` or `qg < 0` before microphysics by its distance `d` to
the nearest lateral boundary (`spec_zone = 1`, `relax_zone = 4`, so the treated
frame is `d <= 4`), six steps, grid 234 x 282 x 39:

| zone | negatives | share | share of cells | enrichment |
|---|---|---|---|---|
| boundary, `d <= 4` | 1,370 | 8.32% | 7.67% | **1.08x** |
| interior, `d >= 5` | 15,100 | 91.68% | 92.33% | **0.99x** |

Normalised by all cells in each zone, enrichment is close to one. The frame is
7.67% of the domain and carries 8.32% of the negatives; 85% of them sit at
`d >= 9`, far inside.

**The counts show no strong concentration in the treated boundary frame.**
They do not rule out a contribution from boundary treatment. The denominator
is all grid cells, not the graupel-bearing cells exposed to negativity; no
claim about distribution relative to the graupel field follows from this table.

The absolute counts alone would have suggested the opposite reading in either
direction -- the interior looks dominant because it is 92% of the grid. The
enrichment ratio is the statement; the raw counts are not.

The causal candidates still include advection, non-advective tendencies
(including boundary and diffusion terms), and the `mu_old`/`mu_new` coupling.
The next discriminating record is the first cell that becomes negative: its
index and RK/scalar stage, state before/after, applied tendency components,
`mu_old`/`mu_new`, and the limiter-related values used by that update. This
would support a term-by-term reconstruction; more whole-domain counts alone
would not. That operand record has not been measured here.
