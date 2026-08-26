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
take the `brs = 0` branch. `g5`'s distinguishing property is therefore
implemented and **not yet exercised by any measurement**.

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
window caps the mass at `qcrmin = 1e-9`, so the effect on `qr/nr` is bounded --
and nobody has bounded it. A column carrying trace graupel near `qcrmin` would.
