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

**Not established**: which part of the positive-definite path fails for `qib`.
That the limiter is reached and is insufficient is measured; where inside it the
guarantee breaks is not. A paired moment advected independently of its mass has
no reason to stay consistent with it, but that is a hypothesis here, not a
result.
