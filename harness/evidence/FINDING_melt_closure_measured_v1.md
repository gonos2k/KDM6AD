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

## Mass conservation, at the one cell where the melt is partial

`k = 23` is the only level where `qg` and `qr` both change and stay finite. It
carries `qg = 3.199609e-08`, which is **above** `qcrmin = 1e-9` -- so it is
OUTSIDE the defect window, `ProgB_param` computed `rhox` there, and it is a
genuine PARTIAL melt.

    d(qg)     -3.1974e-14
    d(qr)     +2.8422e-14
    d(qr+qg)   0.0000e+00      exactly, 0 ULP of qr

The two increments differ from each other by more than an ULP -- each is
rounded separately -- and the SUM is bit-exactly conserved.

## And all four arms agree there, to the bit

At `k = 23` `legacy`, `g1`, `g3` and `g4` produce identical `qg`, `qr`, `brs`
and `nr`. That is the containment property measured rather than argued: outside
the window `rhox` is positive, every arm reduces to legacy's expression, and
the outputs are the same words.

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
