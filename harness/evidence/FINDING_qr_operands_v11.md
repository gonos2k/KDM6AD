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

Closed is the point: the incoming `qrs(1)` is already compared (it comes from
`outer_post_sed`) and `dtcld` is a sealed scalar, so if every operand matches and
`qr` still differs, the difference is in the summation and not in an operand.

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

| loop | field | k | Fortran | C++ | Δ | variant-independent |
|---|---|---|---|---|---|---|
| 2 | `prevp` | 0 | −5.919258e-14 | −5.920804e-14 | +2281 | **both sides** |
| 2 | `psacr` | 0 | +5.535328e-16 | +5.535317e-16 | −21 | **both sides** |
| 2 | `paacw` | 0 | +9.838063e-14 | +9.838044e-14 | −28 | **both sides** |
| 2 | `paacw` | 1–3 | 4.06e-12 … 1.85e-10 | | −18, −23, −8 | no |
| 3 | `paacw` | 0 | +3.041082e-15 | +3.041087e-15 | +19 | **both sides** |
| 3 | `paacw` | 1–3 | 1.67e-13 … 1.85e-11 | | +53, +54, +12 | no |

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

These rates are ~1e-14 to 1e-16. `prevp`'s 2281 ULP is 2.6e-4 *relative* on a
rate of −5.9e-14, i.e. about 1.5e-17 absolute; over `dtcld` that is ~1e-15,
which tips `qr` (3.8e-8 at that cell) by the 3 ULP seen downstream. The large
relative deviation on a near-zero evaporation rate is the signature of
cancellation — evaporation is a saturation deficit, a difference of nearly equal
terms — so a small absolute difference upstream becomes a large relative one
here. Physically the rate is zero to any meaningful precision.

## What this does and does not establish

It establishes that the first observed Fortran↔C++ difference is an operand of
the qr update line, that exactly three rates differ anywhere in that set, that
the branch is not implicated, and that at the seed cell the difference is
bit-identically the same with and without the conservative interface.

It does not establish which arithmetic step inside `prevp` produces it. That
needs the rungs of the evaporation computation itself, which is the next
bisection and a new operand vocabulary.

The gate returns `INCONCLUSIVE`. Attribution is owner adjudication; the tool
makes no C4 claim.
