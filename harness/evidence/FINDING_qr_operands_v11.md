# The seed at the operand level: three rates, and at the seed cell none of them
# depends on the variant

Protocol v11. Also **withdraws the v10 conclusion** — the v10 Fortran stage was
injected at the wrong ProgB call.

## Retraction first

`micro_post_state_update`'s anchor was written as occurrence `(6, 7)`. The index
is **0-based**, so it resolved to the *seventh* `ProgB_param` call (F:3146),
which runs **after** the saturation adjustment, while the C++ recorded at
`poststateupdate`, before Picons and satadj. The two sides recorded different
instants. Nothing failed: both are real ProgB calls, the overlay built, the run
produced a complete record set, and the gate returned a verdict.

So the v10 claim — that the seed is before the saturation adjustment and that
Picons/satadj are excluded — was **not supported by where the records were
taken**, and is withdrawn. It is re-established below on the corrected run.

This is the third placement defect of this kind in this protocol. The fix is not
the indexing convention: an anchor may now carry a **landmark**, a substring that
must appear within 12 lines after the resolved point, so the spec states which
site it means in the source's own terms and an off-by-one lands somewhere that
does not have it and fails. `micro_call_progb_aux` was audited the same way and
*was* correctly placed (idx 4 resolves to the post-freeze site); it now carries
its landmark too.

## The stage

`micro_qr_operands` records the **closed** operand set of the qr update line, as
`state_update` consumes it:

```fortran
cold (F:2803)  qrs(1) += (praut+pracw+prevp-piacr-pgacr-psacr-pmulrs-pmulrg)*dtcld
warm (F:2922)  qrs(1) += (praut+pracw+prevp+paacw+paacw-pseml-pgeml)*dtcld
```

> **CORRECTION (owner review, §2).** The word "closed" above overstates what
> this stage seals, and the reasoning under it was wrong. It read: the incoming
> `qrs(1)` is already compared because it comes from `outer_post_sed`, so if
> every operand matches and `qr` still differs the difference must be in the
> summation. **`state_update` does not read `outer_post_sed.qr`.** Between that
> snapshot and the update the step runs D1 melt, homogeneous freeze, the
> post-melt re-slope, D2–D4 freeze, the post-freeze re-slope, the rate blocks and
> the mass-conservation scaling; the base is `working.qr`, which no G3.3 stage
> records. (The C++ dumps it as the `prestate` substep forensic, which is not a
> decision stage.)
>
> So the set is closed over the RATE operands and not over the update line. The
> measured first divergence below stands — `prevp` differs, and that is an
> observation, not an inference. What does not stand is the converse: "all
> operands equal ⇒ the difference is in the summation" needs the exact
> pre-update state, and is not available until `micro_pre_state_update` and an
> exact f32 replay of the update are added.

Three C++ names carry a suffix and the same quantity: Fortran adjusts
`psacr`/`pgacr`/`paacw` **in place** after the Hallett-Mossop block
(F:2383/F:2436/F:2368/F:2420), so by the update its array already holds the
post-HM value that C++ calls `psacr_adj`/`pgacr_adj`/`paacw_adj`. Established
from both sources, not from the suffix.

## Result (`b20869c`, fixture `arithmetic_multisubcycle_v1`, manifest `290ddce1…`)

| stage | L1 | L2 | L3 |
|---|---|---|---|
| `outer_post_sed` | 0/144 · 0/144 | 0/144 · 0/144 | 26/144 · 21/144 |
| `micro_call_progb_aux` | 0/228 · 0/228 | 0/228 · 0/228 | 4/228 · 4/228 |
| `micro_qr_operands` | 0/144 · 0/144 | **6/144 · 5/144** | 4/144 · 4/144 |
| `micro_post_state_update` | 0/144 · 0/144 | 18/144 · 12/144 | 37/144 · 37/144 |
| `outer_post_micro` | 0/144 · 0/144 | 24/144 · 20/144 | 35/144 · 35/144 |

(legacy · conservative)

First divergence: `micro_qr_operands`, loop 2, column 3, k 0, **`prevp`** — rain
evaporation.

```
legacy_fortran        0xa9854a33   -5.919258e-14
conservative_fortran  0xa9854a33   -5.919258e-14
legacy_cpp            0xa985531c   -5.92080367e-14
conservative_cpp      0xa985531c   -5.92080367e-14
```

Only **three** of the twelve operands differ anywhere, all in column 3:

`signed_ulp_delta` is `ordered(C) − ordered(F)` under the order-preserving
(Dawson) transform. It is NOT the raw bit difference: for a negative float the
bit ordering runs the other way, so `prevp`'s raw `c_bits − f_bits` is +2281
while its signed ULP delta is **−2281**. An earlier version of this table printed
the raw difference under a bare `Δ` and so reported that one row with the wrong
sign.

| loop | field | k | Fortran | C++ | `signed_ulp_delta` | dir | branch-active here | variant-independent |
|---|---|---|---|---|---|---|---|---|
| 2 | `prevp` | 0 | −5.919258e-14 | −5.920804e-14 | **−2281** | C<F | **yes** (common) | **both sides** |
| 2 | `psacr` | 0 | +5.535328e-16 | +5.535317e-16 | −21 | C<F | **yes** (cold) | **both sides** |
| 2 | `paacw` | 0 | +9.838063e-14 | +9.838044e-14 | −28 | C<F | **no** (warm-only) | both sides |
| 2 | `paacw` | 1 | +4.061015e-12 | | −18 | C<F | **no** (warm-only) | no |
| 2 | `paacw` | 2 | +4.073789e-11 | | −23 | C<F | **no** (warm-only) | no |
| 2 | `paacw` | 3 | +1.849350e-10 | | −8 | C<F | **no** (warm-only) | no |
| 3 | `paacw` | 0 | +3.041082e-15 | +3.041087e-15 | +19 | C>F | **no** (warm-only) | both sides |
| 3 | `paacw` | 1–3 | 1.67e-13 … 1.85e-11 | | +53, +54, +12 | C>F | **no** (warm-only) | no |

**`paacw` is not causal at this cell.** Column 3 runs at 242–244 K, so every level
takes the COLD arm, whose qr line does not read `paacw` at all — it is a
warm-arm operand. Its differences are diagnostics. The operands that are
branch-active AND differ here are `prevp` and `psacr`, and of those `prevp`
dominates by four orders of magnitude (below).

## Three controls

**The branch agrees.** `cold_gate` is bit-identical between the backends at every
cell of every loop, so this is not the `supcol > 0` / `t <= t0c` disagreement the
field was added to detect.

**At the seed cell nothing depends on the variant.** At k = 0 — where the first
divergence is, and where the conservative interface has no inflow from above to
redistribute — all three differing operands have the *same* Fortran value in both
variants and the *same* C++ value in both variants. The Fortran↔C++ difference
there is independent of the conservative interface.

**Where the variant does matter, it shows.** `paacw` at k ≥ 1 is variant-
dependent on both sides — those are the levels the conservative interface acts
on. It is not where the seed is.

## Magnitudes

`prevp` is −5.919258e-14 s⁻¹ in Fortran and −5.920804e-14 s⁻¹ in C++, so

    Δprevp          ≈ −1.546e-17 s⁻¹     (2.6e-4 relative, 2281 ULP)
    Δprevp · dtcld  ≈ −1.546e-15 kg/kg   (dtcld ≈ 100 s)

and the `qr` difference actually observed at that cell is

    0x31974466 → 0x31974463  ≈ −1.332e-15 kg/kg

The sign and magnitude of the `prevp` backend difference match the 3-ULP `qr`
difference. `psacr`'s difference is ~1e-21 s⁻¹ — four orders of magnitude
smaller — so it cannot account for it. That is quantitative evidence that
`prevp` is the **dominant branch-active operand** at this cell.

Two things this does NOT say.

The rate itself is small but **not** zero: `prevp · dtcld ≈ −5.92e-12 kg/kg`.
An earlier wording here said "physically the rate is zero to any meaningful
precision", which overstates it — what is meteorologically negligible is the
Fortran↔C++ *difference*, not the rate.

And a large relative deviation on a near-zero evaporation rate is
**cancellation-consistent**, not a demonstrated cancellation. Evaporation is a
saturation deficit, a difference of nearly equal terms, which would produce
exactly this; but establishing that as the origin needs the rungs of the
computation, and they are not recorded.

## What this does and does not establish

It establishes that the first observed Fortran↔C++ difference is a **scaled**
operand of the qr update line, that exactly three rates differ anywhere in that
set and only two of them are branch-active at the seed cell, that the branch
itself is not implicated, and that at the seed cell the difference is
bit-identically the same with and without the conservative interface.

It does not establish the root cause, and three things stand between:

1. **The exact pre-update state is not sealed** (correction above). Until
   `micro_pre_state_update` and an exact f32 replay of the update line exist,
   "all operands equal ⇒ summation" cannot be asserted.
2. **The recorded `prevp` is the post-budget SCALED rate**, not the raw
   evaporation rate: the C++ path is `warm_phase` → `cold_phase` → D5 →
   `scale_rates_for_conservation` → `micro_qr_operands` → `state_update`. So the
   candidates are the raw formula, the conservation scale factor, or the
   multiply/cast/store that applies it — three different answers, not one.
3. **Which arithmetic step inside the raw `prevp`** produces it, if it is (1).

Going straight to the evaporation formula's internal rungs would skip (1) and
(2). The order is: seal the update base and the branch-active operand set, then
split raw from scaled, then bisect the formula.

The gate returns `INCONCLUSIVE`. Attribution is owner adjudication; the tool
makes no C4 claim.
