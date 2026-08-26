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

## Mass conservation, over every melt event -- corrected

**The first reading of this section was wrong, and the collapse is why.** It
reported ONE partial melt at `k = 23` with a residual of exactly zero. Keying by
`(stage, field, k)` and taking the last write meant reading substep 3 and
calling it the whole story.

Parsing by OCCURRENCE ORDER instead -- the n-th write of a key is the n-th
substep -- there are **six melt events across four levels**:

| level | substep | `d(qr + qg)` | |
|---:|---:|---:|---|
| 18 | 0 | `+0.0000e+00` | partial |
| 19 | 0 | `+0.0000e+00` | partial |
| 20 | 0 | `+0.0000e+00` | partial |
| 23 | 0 | `+0.0000e+00` | partial |
| 23 | **1** | **`-3.5527e-15`** | partial |
| 23 | 2 | `+0.0000e+00` | partial |

Every one is a PARTIAL melt -- `qg` never reaches zero at these levels, which
are all above `qcrmin` and therefore outside the defect window.

`3.5527e-15` is **exactly one ULP** of `qr` at that magnitude
(`spacing(5.78e-08) = 3.5527e-15`). So the honest statement is **mass conserves
to zero or one ULP**, not "exactly, 0 ULP" -- which was true of the one event
the collapsed reading happened to show.

## And the arms agree at every one of them, to the bit

`legacy`, `g3` and `g4` produce identical values at **all six events, across
four levels and three substeps** -- not at the single cell the first reading
found. That is the containment property measured on a wider population than was
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
