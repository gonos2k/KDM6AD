# Bisecting the microphysics step: the seed is before the saturation adjustment

Protocol v10 result. Narrows the loop-2 divergence from "somewhere in the
microphysics" to the first half of it, and excludes the saturation adjustment
and Picons/Nicons as its origin.

## What v9 left open

The corrected v9 run put the first divergence at `outer_post_micro` loop 2 with
`micro_call_progb_aux` bit-identical. `_STAGE_MAJOR` ran those two stages
adjacently, so the interval between them was the whole of the microphysics
step: the warm and cold rate blocks, the mass-conservation feedback, the
two-branch state update, the ProgB brs re-clamp, Picons/Nicons, the saturation
adjustment and the final re-slope.

## The bisection

`micro_post_state_update` records the twelve carried prognostics at the one
interior point where **both backends already had a reconciled program point**:

- Fortran — after the sixth of the seven `ProgB_param` calls (F:3032), where the
  pinned source's own dump writes `fort_substep_poststateupdate.bin` and
  describes itself as "post-budget + post-ProgB brs-reclamp, PRE-Picons/satadj —
  mirrors C++ cpp_substep_poststateupdate".
- C++ — on `new_state` after the brs sweep and before
  `reclassify_large_ice_to_snow`, the `poststateupdate` substep dump.

Reusing that pair rather than establishing a new correspondence was the point:
both placement defects this protocol has produced came from a site where the
correspondence had to be worked out in the harness.

## Result (`fd162f3`, fixture `arithmetic_multisubcycle_v1`, manifest `290ddce1…`)

Fortran vs C++ differing cells:

| stage | L1 | L2 | L3 |
|---|---|---|---|
| `outer_post_sed` | 0/144 · 0/144 | 0/144 · 0/144 | 26/144 · 21/144 |
| `micro_call_progb_aux` | 0/228 · 0/228 | **0/228 · 0/228** | 4/228 · 4/228 |
| `micro_post_state_update` | 0/144 · 0/144 | **18/144 · 12/144** | 37/144 · 37/144 |
| `outer_post_micro` | 0/144 · 0/144 | 24/144 · 20/144 | 35/144 · 35/144 |

(legacy · conservative)

The first divergence moved upstream from `outer_post_micro` to
`micro_post_state_update`, at the **same cell** — loop 2, column 3, k 0, `qr`:

```
legacy_fortran        0x31974466        conservative_fortran  0x31974466
legacy_cpp            0x31974463        conservative_cpp      0x31974463
```

Both pairs carry the identical −3 ULP delta, as they did at `outer_post_micro`.

## What is excluded

`micro_call_progb_aux` is bit-identical at loop 2, and the difference is already
present at `micro_post_state_update`. So the seed lies in:

- the warm and cold rate blocks,
- the mass-conservation feedback (F:2628),
- the two-branch state update (F:2796 / F:2918),
- or the ProgB brs re-clamp (F:3032).

And **not** in Picons/Nicons, the saturation adjustment, or the final re-slope —
those run after this snapshot.

## What the second half does do

Comparing the two snapshots at loop 2 shows the region II arithmetic amplifying
rather than seeding. At `micro_post_state_update`, k = 0 differs in `qr` (−3),
`qs` (−6) and `t` (+2), and `qv` differs only at k = 3 by 1 ULP. By
`outer_post_micro` the same column carries `qc` −84 and `qv` +169 at k = 0. The
saturation adjustment turns a few-ULP temperature and rain difference into a
large vapour one, which is what a saturation solve does to a perturbed `t`. It
is downstream of a difference that already exists.

## Two controls

**The variant does not add divergent cells.** At `micro_post_state_update` loop
2 the conservative pair diverges in 12 cells and the legacy pair in 18; the 12
are a **strict subset** — 6 cells are legacy-only and none are
conservative-only.

**At the model top the delta is variant-independent.** At k = 0, where the
conservative interface has no inflow from above to redistribute, every differing
field carries the same delta in both variants:

| field | k | legacy Δ | conservative Δ |
|---|---|---|---|
| `qr` | 0 | −3 | −3 |
| `qs` | 0 | −6 | −6 |
| `t` | 0 | +2 | +2 |

Below the top they part — of 12 shared cells, 3 agree on the delta and 9 do not
— which is where that interface acts.

## What this does and does not establish

It establishes that the Fortran↔C++ difference is present before the saturation
adjustment runs, that it is bit-identically the same at the first divergent cell
with and without the conservative interface, and that the conservative variant
diverges in a subset of the cells the legacy variant does.

It does not establish which operation in the first half produces it. The rate
blocks are still uninstrumented: localising further needs records of the rate
arrays feeding the two update branches, which is a larger vocabulary and a
mapping between the backends that does not yet exist — the place where the two
defects so far have come from.

The gate returns `INCONCLUSIVE`. Attribution is owner adjudication; the tool
makes no C4 claim.
