# The 1-ULP `t` is acquired in the freeze block, in the heat term

Protocol v13. Splits the melt–freeze chain and localises the seed from "somewhere
between the sedimentation result and the update base" to three statements.

## Correction, before the result

The first v13 run reported the first divergence at `micro_post_freeze` **loop 1**,
`brs`, at every level of column 3 — 8.8% apart — and it healed completely by the
next stage. A difference that large which then vanishes is not a divergence: it is
two backends recording different things.

The C++ emission sat 25 lines ahead of the reconciled `postfreeze` dump, before
`working.brs = pre2.progb.bg`. The Fortran records at F:1714, after `ProgB_param`
at F:1707 has already rewritten `brs` in place. The block's own comment said it
reused the reconciled pair; the code sat somewhere else. Moved onto the dump; the
loop-1 artifact is gone (0 cells).

`test_g33_overlay_mirror_sites` closes that gap. Orientation is checked, the
Fortran anchor's landmark is checked, and now each state stage declares the
substep-dump tag it mirrors and must FOLLOW it within 20 lines with nothing
executable in between — which is exactly what the assignment to `brs` was.

## Result (`1b09d24`, fixture `arithmetic_multisubcycle_v1`, manifest `290ddce1…`)

| stage | L1 | L2 | L3 |
|---|---|---|---|
| `outer_post_sed` | 0/144 · 0/144 | 0/144 · 0/144 | 26/144 · 21/144 |
| `micro_post_melt` | 0/144 · 0/144 | **0/144 · 0/144** | 26/144 · 21/144 |
| `micro_post_freeze` | 0/144 · 0/144 | **4/144 · 3/144** | 37/144 · 37/144 |
| `micro_pre_state_update` | 0/144 · 0/144 | 4/144 · 3/144 | 37/144 · 37/144 |
| `micro_qr_operands` | 0/144 · 0/144 | 6/144 · 5/144 | 4/144 · 4/144 |
| `micro_post_state_update` | 0/144 · 0/144 | 18/144 · 12/144 | 37/144 · 37/144 |
| `outer_post_micro` | 0/144 · 0/144 | 24/144 · 20/144 | 35/144 · 35/144 |

**D1 melt and the homogeneous freeze are excluded**: `micro_post_melt` is
bit-identical at loop 2. The seed appears at `micro_post_freeze`, in one field —
`t` — at four levels of column 3.

```
legacy_fortran / conservative_fortran   0x437396ba   243.588775635
legacy_cpp     / conservative_cpp       0x437396bb   243.588790894
signed_ulp_delta = +1   (C>F)
```

Identical to the value at `micro_pre_state_update`, so `t` acquires the
difference here and carries it unchanged to the update base.

## What writes `t` in that span, and why the rates are not implicated

Four statements, and the cell at 243.59 K (−29.6 °C) is outside the first:

```fortran
:1529  t += xlf/cpm * qci(1)     homogeneous freeze, T < −40 °C — not this cell
:1618  t += xlf/cpm * pinuc      companions: qci(1), qci(2)
:1648  t += xlf/cpm * pfrzdtc    companions: qci(1), qci(2), nci(1), nci(2)
:1679  t += xlf/cpm * pfrzdtr    companions: qrs(3), brs, qrs(1), nrs(1)
```

At `micro_post_freeze` loop 2 **only `t` differs**. Every companion prognostic
those same three statements write — `qc`, `qi`, `nc`, `ni`, `qg`, `brs`, `qr`,
`nr` — is bit-identical. Each rate is added to its companion with the same value
it contributes to `t`, so a rate that differed would have to differ by less than
the companion's rounding while still moving `t`. That is possible but narrow, and
the simpler reading is that the rates agree and the difference is in the heat
term `xlf/cpm * rate` — the division, the multiply, their order, or the
accumulation across three sequential f32 stores.

The C++ mirror computes `out.t = (t_d3 + fr_coef * mf.pfrzdtr).to(dtype)`, with
`fr_coef` a precomputed factor, against Fortran's per-statement `xlf/cpm(i,k)*…`.
Whether those are the same arithmetic is the next measurement, not a conclusion.

## Controls

- **Variant-independent AT THE SEED CELL.** At k 0 both Fortran legs give
  `0x437396ba` and both C++ legs `0x437396bb`. This does NOT extend up the
  column: at k 1–3 the two variants hold different temperatures (e.g. k 1,
  243.183975 legacy against 243.185989 conservative), which is why conservative
  shows 3 differing cells and legacy 4 — at conservative k 1 the two backends
  happen to agree. The claim is about the seed cell, not the column.
- **Replay exact, with its scope stated.** 144 cells, 0 misses — but "144 cells,
  0 misses" reads as 144 checks and is not, and the earlier phrasing let it. Where
  every branch-active rate is zero the replay reduces to `qr_post == qr_pre` and
  confirms nothing about the arithmetic; where the `max(…,0)` clamp binds, the sum
  is discarded. `g33_update_replay.coverage()` reports it so this is not worked out
  by hand again — and it corrected a hand count that had looked only at loop 3:

  | cells | moved | zero-sum (vacuous) | clamped | **load-bearing** |
  |---|---|---|---|---|
  | 144 | 72 | 72 | 6 | **66** |

  So 66 of 144, not 144. What the 66 do cover is real: the branch is exercised
  both ways (48 of 144 cells take the warm arm), and the branch recomputed from
  `t` agrees with the producer's `cold_gate` in **144 of 144** — so the placement
  guarantee the replay exists to give holds across the whole set, while the
  arithmetic claim rests on the 66.
- **One field of twelve**, four cells of 144.

## Next

Record `xlf`, `cpm`, the three rates (`pinuc`, `pfrzdtc`, `pfrzdtr`) and the
intermediate `t` after each of the three additions. That set is closed for the
heat term the same way `micro_qr_operands` is closed for the qr line — with the
base now sealed, which is what v12 established it needs.

The gate returns `INCONCLUSIVE`. Attribution is owner adjudication.
