# The update base differs first, in one field, by one ULP

Protocol v12. The first divergence moves upstream again — from `prevp` to the
**base state `state_update` reads** — and the qr update line is now genuinely
closed, which it was not at v11.

## What v11 got wrong, and why

The v11 finding called `micro_qr_operands` a closed operand set on the grounds
that the incoming `qrs(1)` came from `outer_post_sed`. It does not:
D1 melt, homogeneous freeze, the post-melt re-slope, D2–D4 freeze, the
post-freeze re-slope, the rate blocks and the conservation scaling all run
between that snapshot and the update, and the base is `working.qr`, which no
G3.3 stage recorded. So `prevp` was the first divergence *among the stages that
existed*, and the base was not one of them.

`micro_pre_state_update` records it: the C++ on the same line as the `prestate`
substep dump, which already calls itself "the EXACT state_update base"; the
Fortran before the F:2638 branch, where the state is unmodified through either
arm's update.

## The replay, and why it comes first

`g33_update_replay` reproduces

    qr_post == max(fl32(qr_pre + fl32(S * dtcld)), 0)

per leg, in the source's left-to-right f32 association (`paacw` added **twice**
in the warm arm, not doubled — the two forms differ in f32).

**144 cells, four legs, three outer loops: 0 misses.**

That is a statement about the evidence, not about the physics. Three placement
defects in this protocol have had the same shape — two backends recording
instants that are not the same instant, with nothing failing because both are
real program points. A replay that reproduces `micro_post_state_update.qr` from
`micro_pre_state_update.qr` and the operands can only succeed if those three
stages sit at mutually consistent points *within that backend*. It passing on
all four legs is what licenses reading the cross-backend comparison below.

It also settles a question the source could not: the C++ `state_update` adds
`dqr_amount = -mf.pfrzdtr` internally while `coordinator.cpp:606` already applies
`- mf.pfrzdtr` to `out.qr`, so whether `working.qr` at the dump was the right
base was not decidable by reading. The replay says it is.

## Result (`6ca5945`, fixture `arithmetic_multisubcycle_v1`, manifest `290ddce1…`)

| stage | L1 | L2 | L3 |
|---|---|---|---|
| `outer_post_sed` | 0/144 · 0/144 | 0/144 · 0/144 | 26/144 · 21/144 |
| `micro_call_progb_aux` | 0/228 · 0/228 | 0/228 · 0/228 | 4/228 · 4/228 |
| `micro_pre_state_update` | 0/144 · 0/144 | **4/144 · 3/144** | 37/144 · 37/144 |
| `micro_qr_operands` | 0/144 · 0/144 | 6/144 · 5/144 | 4/144 · 4/144 |
| `micro_post_state_update` | 0/144 · 0/144 | 18/144 · 12/144 | 37/144 · 37/144 |
| `outer_post_micro` | 0/144 · 0/144 | 24/144 · 20/144 | 35/144 · 35/144 |

(legacy · conservative)

At loop 2 the base state differs in **exactly one field**: `t`, at all four
levels of column 3 (legacy; three levels for conservative). All eleven other
prognostics — `qr`, `nr`, `qv`, `qc`, `qi`, `qs`, `qg`, `nc`, `ni`, `nccn`,
`brs` — are bit-identical.

First divergence: `micro_pre_state_update`, loop 2, column 3, k 0, **`t`**.

```
legacy_fortran        0x437396ba   243.588775635
conservative_fortran  0x437396ba   243.588775635
legacy_cpp            0x437396bb   243.588790894
conservative_cpp      0x437396bb   243.588790894

signed_ulp_delta = +1   (ordered(C) − ordered(F)),  direction C>F
```

**One ULP**, and both variants agree on each side.

## What this localises

`t` matches at `outer_post_sed` (loop 2, all 144 cells) and differs at the update
base. What runs between is D1 melt, homogeneous freeze, the post-melt re-slope,
D2–D4 freeze and the post-freeze re-slope — `t` is written by the melt and by the
D4 freeze heat. The seed is in that chain, upstream of the rate blocks entirely.

`micro_call_progb_aux` matching does **not** narrow this: that stage records the
19 ProgB auxiliary fields, not the state, so it says nothing about `t`.

## What is NOT established — including a claim from the previous finding

The v11 finding suggested the `prevp` difference was "the signature of
cancellation" in a near-saturated cell. A first-order estimate does not support
that, and is recorded here rather than dropped:

    1 ULP at t = 243.5888 K                    = 1.526e-05 K
    qs (Clausius–Clapeyron over ice, p=78 kPa) ≈ 3.185e-04
    rh = qv/qs                                 ≈ 1.32        → rh − 1 ≈ +0.32
    d(rh)/dT · 1 ULP                           ≈ −2.08e-06
    ⇒ relative change of (rh − 1)              ≈ 6.5e-06
    observed relative change of prevp (2281 ULP) ≈ 2.7e-04

so the `(rh − 1)` path accounts for roughly **2%** of the observed `prevp`
difference, and `rh` is not near 1 on this estimate — there is no catastrophic
cancellation in that term here.

Two caveats keep this from being a refutation. The estimate uses
Clausius–Clapeyron over ice, not the model's own `fpvs`, and `rh(i,k,1)` may be
the water-saturation slot. And `(rh − 1)` is only one of the `t`-dependent
factors in `prevp`: `work1` and `work2` (the thermodynamic denominator and the
ventilation factor) also depend on `t`, and neither is recorded.

What the estimate does establish is that **no mechanism should be asserted yet**.
The only differing state input at the update base is `t`, so every channel from
the state to `prevp` runs through it; which `t`-dependent factor carries the
amplification is a measurement that has not been made.

## Controls

- **Variant-independent at the seed.** Both Fortran legs give `0x437396ba` and
  both C++ legs `0x437396bb`; the difference does not depend on the conservative
  interface.
- **The branch agrees.** Both sides are cold at that cell (243.59 K against
  t0c = 273.15), recomputed from the recorded `t` rather than taken from a
  producer-emitted flag.
- **Everything else in the base matches.** One field of twelve, four cells of
  144.

## Standing gaps (owner review, not closed here)

- **§4 raw vs scaled `prevp`.** The recorded `prevp` is post-`scale_rates_for_conservation`.
  Splitting raw / scale factor / scaled is still needed, and is now arguably
  lower priority than the melt–freeze chain that produces the 1-ULP `t`.
- **§3 t == t0c.** Fortran branches on `t <= t0c`, the C++ on `supcol > 0`
  (i.e. `t < t0c`); they disagree at exactly the boundary. Encoded as a passing
  assertion in `test_g33_update_replay`, needs a threshold fixture and an owner
  decision — not a silent fix.
- **§8** single-file provenance, **§9** historical Gate-D witness, and the
  column-number / moist-energy gates.

The gate returns `INCONCLUSIVE`. Attribution is owner adjudication.
