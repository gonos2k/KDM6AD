# Five arms, and what each one actually leaves behind

Column `(281,16)` from the provenance-complete forecast, at the operational
20 s call. `micro_post_melt`, substep 0, the five levels where legacy makes
`brs = -inf`.

| | `qg` | `brs` |
|---|---|---|
| `legacy` | 0 | **`-inf`** |
| `g1` | **trace kept** (3.05e-20 … 4.99e-43) | 0 |
| `g3` | 0 | 0 |
| `g4` | 0 | 0 |
| `g5` | 0 | 0 |

Three separate policies, and the table is the whole difference:

- **legacy** removes the mass and divides by a density it never computed.
- **`g1`** skips the melt block, so the trace graupel stays and nothing moves.
- **`g3`/`g4`/`g5`** remove the mass and take the volume with it.

## `g5`: the window-only proportional transaction

`g4` clamps the density inside the window and then floors the result at zero.
That prevents a negative volume but permits `qg > 0` with `bg = 0`, which no
finite density satisfies. `g5` avoids both by scaling the volume by the MASS
FRACTION instead of subtracting a clamped quotient:

    outside the window   brs = brs + pgmlt/rhox        legacy, to the bit
    inside, complete     brs = 0
    inside, partial      brs = bg0 * (qg+ / qg0)

which preserves the pre-melt apparent density exactly (`qg+/bg+ = qg0/bg0`),
reaches zero on its own when the melt is complete, and **never subtracts**, so a
negative volume is unreachable and no floor is needed. Checked over 50 000 f32
draws spanning the window: **0 negatives, 0 density drift above 1e-5 relative**.

**And `g4` and `g5` are indistinguishable here** -- 0 differences across every
level, substep and prognostic. They can only differ on a PARTIAL melt inside the
window, and this column has none: every melt in the window is complete, so both
take the `brs = 0` branch.

### What they do when that branch IS reached

The branch was not reachable on the fixture, so it was classified from the
formulas, with a sample only as a check. Write the melt fraction
`a = -pgmlt/qg0` in `(0,1)` and the raw ratio `rho0 = qg0/bg0`, and let
`rho_c = clip(rho0, 100, 900)`. Then

    g4 : bg+ = max(0, bg0 - a*qg0/rho_c)
    g5 : bg+ = bg0 * (qg+/qg0) = (1-a)*bg0        in exact arithmetic

and three statements follow, none of them statistical:

**1. Inside the model's density band the two are the same equation.** If
`100 <= rho0 <= 900` then `rho_c = rho0`, so `a*qg0/rho_c = a*bg0` and both give
`(1-a)*bg0`. Checked on 14,344 in-band f32 draws: bit-equal in 6,646, and where
f32 separates them the difference is rounding -- relative median 1.006e-07, max
2.936e-04 -- with **no in-band draw floored to zero**.

**2. `g4` floors exactly when `a*rho0 >= rho_c`.** Which for a partial melt needs
`rho0 > 900`, since `rho_c = clip(rho0)` and `a < 1`. Checked: the predicate and
`g4 == 0` agree on **100.000%** of 200,000 draws, and every floored draw has
`rho0 > 900`.

**3. `g5` preserves `rho0`, whatever `rho0` is.** That is algebraic consistency,
not admissibility: this branch is entered precisely where `rhox` was never
computed, so `rho0` is the apparent ratio of a sub-threshold residual and can sit
orders of magnitude outside `[100, 900]`. With `qg0 = 1e-9` and `bg0 = 1e-16`,
`rho0 = 1e7 kg m^-3`; `g5` carries that ratio through the melt intact.

A percentage was reported here earlier -- 64.3% of the sample floored -- and it is
demoted to what it is: the share of ONE log-uniform sampling measure that
satisfies `a*rho0 >= rho_c`. It is not a rate at which the model does anything.

### And `g5` does not avoid the zero-volume state; it refuses it

An earlier version of this section said `g5` "never reaches zero while mass
remains". That is wrong, and it was wrong because the sampling could not reach
the boundary: `bg0` drawn log-uniform is never exactly zero. The implementation
computes the value and then tests it:

    brs = melt_bg0*(qrs(i,k,3)/melt_qg0)
    if (brs .le. 0.) then ... error stop

and both reachable ways to get there produce it. With `bg0 = 0` exactly, and with
`bg0` at the smallest f32 subnormal `1.4e-45` and a half melt, the product is
`0.0` while `qg+ = 5e-13 > 0` -- the inconsistent state. `g5` does not RETURN it;
it stops the model. That is right for a diagnostic arm and is not
production-safe behaviour.

The sampling is uniform in log over the window, which is not the model's
distribution, and it excludes the boundary. **Whether any model column reaches
this branch at all is still unmeasured**, and the fixture has none.

## The number policy is the real arm choice

`g1` keeps the mass-number pair intact by never entering the block. `g3`, `g4`
and `g5` all move graupel mass to rain while `F:1412` keeps the rain-number
update gated off, because they replace statements INSIDE the block rather than
its opening condition.

So the choice is not "which arm removes the non-finite" -- all four do -- but
**whether trace graupel should melt at all when its density was never
computed.** `g1` says no. `g3`/`g4`/`g5` say yes and accept a mass-only
transfer. That is an owner policy question, and the harness can now measure
either side.

## What is still unmeasured

The magnitude. At this column the mass involved is `1e-20` and below against a
`qr` of `1e-05`, so `qr` and `nr` are bit-identical across all five arms. The
window caps the mass at `qcrmin = 1e-9`, so the transferred rain MASS is bounded.

**That bounds the mass and nothing else.** In the defect window the rain-number
update is gated off while the mass moves, so `qr -> qr + dq` with `nr` unchanged
and `0 < dq <= 1e-9`. The mean particle mass then shifts by `dq/nr` absolutely
and `dq/qr` relatively, and neither has a bound without a positive lower bound on
`nr` and on `qr` -- which nothing here provides. A representative diameter
`Dr ~ (qr/nr)^(1/3)` scales as `(1 + dq/qr)^(1/3)`, unbounded as `qr -> 0`, and
at `qr = nr = 0` with `dq > 0` the moment state is not defined at all.

An earlier version of this paragraph said the effect on `qr/nr` is bounded by
`qcrmin`. Only the absolute increment is. The relative and moment effects are not
bounded, and a column carrying trace graupel near `qcrmin` with small `qr` is
where that would show.
