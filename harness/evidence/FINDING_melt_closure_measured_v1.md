# The melt's closure, measured on a real failing column

Column `(281,16)` from the provenance-complete ten-minute forecast, driven
through `legacy`, `g1`, `g3` and `g4` at the operational 20 s call, reading the
STAGE stream rather than a summary.

## Where the defect actually lands

`brs = -inf`, at **five levels, k = 26..30**. It appears in the stream at
`micro_call_progb_aux` as `bg` and again at `micro_post_freeze`,
`micro_post_melt` and `micro_pre_state_update` as `brs`.

**Those are not four separate creations.** The stream carries all three
substeps of `nsplit = 3` and this reading collapses them, so a value created by
the melt in substep 1 reappears at every stage of substeps 2 and 3, including
ones that precede the melt within a substep. The defect is created once, by the
divide, and then carried.

Under `g3` and `g4` those same five levels read

    qg  = 0.000000e+00
    brs = 0.000000e+00

which is the acceptance criterion's second branch -- `qg+ = b+ = 0` -- exactly,
not to a tolerance. The volume leaves with the mass.

## Mass conservation, and what the metric can actually resolve

This section has been wrong twice, in opposite directions, and the corrections
are the useful part.

**First reading: one event, residual exactly zero.** Keying the stream by
`(stage, field, k)` and taking the last write reads substep 3 and calls it the
whole story.

**Second reading: six events, one residual of 1 ULP.** Parsing by occurrence
order -- the n-th write of a key is the n-th substep -- finds changes at
`k = 18, 19, 20` (substep 0) and `k = 23` (all three). That is the right parse
and still the wrong conclusion, because three of those six are below the
metric's resolution.

**What the bracket spans, checked rather than assumed.** `micro_post_freeze`
sits at the `ProgB_param` call and `micro_post_melt` at `endif !supcol`
(F:1434), so the bracket contains **three** melts: `psmlt` (F:1372), `pgmlt`
(F:1397) and `pimlt` (F:1422). Attributing the change to the graupel melt is
only valid if the other two did not fire. Measured: `d(qs) = d(qi) = d(qc) = 0`
at every one of the six, so they did not.

**Third reading, and the resolution limit that made the second one wrong:**

| level | substep | `qg` before → after | `qr` before → after | `d(qr+qg)` | resolvable |
|---:|---:|---|---|---:|---|
| 18 | 0 | 2.74609e-11 → **unchanged** | 9.11892e-35 → 9.12301e-35 | `0` | **no** |
| 19 | 0 | 1.75051e-09 → **unchanged** | 2.60876e-36 → 2.60877e-36 | `0` | **no** |
| 20 | 0 | 2.21153e-09 → **unchanged** | 8.90211e-19 → 8.90211e-19 | `0` | **no** |
| 23 | 0 | 3.50032e-08 → 3.50031e-08 | 8.40206e-08 → 8.40206e-08 | `+0.0e+00` | yes |
| 23 | 1 | 3.40400e-08 → 3.40400e-08 | 6.94456e-08 → 6.94456e-08 | `-3.5527e-15` | yes |
| 23 | 2 | 3.19961e-08 → 3.19961e-08 | 5.78051e-08 → 5.78051e-08 | `+0.0e+00` | yes |

At `k = 18, 19, 20` the melt moves roughly `1e-38`. On the `qr` side that is a
large RELATIVE change, because `qr` there is `1e-35` or smaller. On the `qg`
side it is absorbed -- `qg + pgmlt == qg` in f32 -- so `qg` is bit-identical.
And `d(qr + qg)` is formed against a `qg` of `1e-11`, which **cannot see a
`1e-38` change at all**. Reporting "conserved" there reports the metric's
resolution, not the physics.

**So the claim is: at the one level where the melt moves an amount the sum can
resolve, mass conserves to zero or one ULP.** `3.5527e-15` is exactly one ULP
of `qr` at that magnitude (`spacing(5.78e-08) = 3.5527e-15`, ratio 1.00).

`d(qr + qg)` is the wrong metric wherever the two species differ by many orders.
A relative or per-species check is what those levels need.

## And the arms agree at every one of them, to the bit

`legacy`, `g3` and `g4` produce identical values at **all six changes, across
four levels and three substeps** -- including the three the conservation metric
cannot resolve, since bit-identity does not depend on a metric. That is the containment property measured on a wider population than was
claimed: outside the window `rhox` is positive, every arm reduces to legacy's
expression, and the outputs are the same words.

Combined with the defect levels above, the arms differ from legacy **only where
`rhox` was never computed**, which is what they were built to do.

## What this does NOT close

**Enthalpy.** `cpm` and `xlf` are carried at different stages than the
prognostics in this stream, so `cpm dT - Lf pgmlt` could not be formed from the
records without assuming which substep each belongs to. It needs either a stage
that carries all four together or a per-substep parse that does not collapse.

**Number.** `nr` is unchanged at `k = 23` to the recorded precision, and at the
defect levels the rain-number update is gated off by `qg > qcrmin`
(`FINDING_melt_number_and_replay_scope_v1` §1) -- so the number question is not
answered by this column, it is *displayed* by it: mass moves to rain at five
levels where number does not.

**Whether the partial branch differs between g3 and g4.** It is not reached
inside the window here: the five defect levels all melt completely, and the one
partial melt is outside the window where both arms are legacy.
