# The `np = 4` difference grows no faster than a one-ULP perturbation does

`FINDING_np4_seam_is_rounding_v1` measured that the decomposition difference
starts rounding-scale -- medians of a few ULP at the patch seam -- and that its
maxima are not, `W` reaching 1.03e+01 within one step. It could not say whether
the ten-minute growth that follows is ordinary chaotic amplification or
something the decomposition does that a rounding seed would not.

The review's control answers it: perturb `np = 1` by a seed of the same size and
shape and compare the growth.

## The perturbation

One ULP -- `nextafter` toward `+inf`, exactly one representable f32 step --
applied to `THM` in the columns `i = 109..125`, the band where the `np = 4`
difference first appears. 186 966 cells, ULP distance exactly 1 everywhere.
`np = 1` throughout, so no decomposition is involved.

## The comparison

Differing fields against the unperturbed `np = 1` baseline, of 197:

| minute | `np = 4` decomposition | 1 ULP `THM` perturbation |
|---|---|---|
| 1 | 77 | **104** |
| 2 | 78 | 103 |
| 5 | 75 | 102 |
| 10 | **106** | **106** |

and the size at ten minutes, p99 of the relative difference over cells that
differ:

| field | `np = 4` | 1 ULP | ratio |
|---|---|---|---|
| `T` | 5.8329e-03 | 4.9545e-03 | 1.18 |
| `W` | 6.4853e-01 | 5.4665e-01 | 1.19 |
| `QVAPOR` | 6.8024e-04 | 5.3899e-04 | 1.26 |
| `REFL_10CM` | 1.7025e+00 | 5.8004e-01 | **2.93** |

**A one-ULP change in one field reaches MORE fields than the decomposition does
at every time before ten minutes, and the same number at ten.**

That sentence first read "the single smallest perturbation this arithmetic can
express", which is true PER CELL and misleading in aggregate: it is one ULP
each in 186 966 cells, **7.26 % of the domain**. Minimal in amplitude, large in
extent. And compared at one minute, neither seed dominates the other:

| field | `np = 4` cells | 1 ULP cells | `np = 4` p99 | 1 ULP p99 |
|---|---|---|---|---|
| `THM` | 220 237 | 191 431 | 2.157e-04 | 1.892e-04 |
| `T` | 225 067 | 194 241 | 1.874e-03 | 1.398e-03 |
| `W` | 1 255 445 | 534 212 | 4.936e-02 | **1.307e-01** |
| `U` | 1 006 583 | 469 744 | 6.994e-04 | **2.056e-03** |
| `QVAPOR` | 585 597 | 352 525 | 4.608e-05 | **2.803e-04** |

The perturbation touches FEWER cells and reaches HIGHER peaks in the dynamical
fields; the decomposition is the reverse. They are the same order and neither is
uniformly the larger, which is what the comparison can support -- not that a
smaller kick did more.

So the decomposition's ten-minute footprint is not evidence of a defect: it is
what this case does with a rounding-scale seed. A difference that grows to 106
of 197 fields sounds like a lot until a one-ULP change does the same.

## What it does NOT say

**That there is no defect.** This bounds the SIZE argument only. The CCN halo
read and the per-tile overwrite are defects on their own evidence
(`FINDING_qnccn_first_write_v1`, `FINDING_ccn_overwrites_microphysics_v1`), and
they are not made harmless by this. What is withdrawn is any inference from
"the difference is large at ten minutes" to "something is wrong in the
dynamics".

**That the two are the same difference.** `REFL_10CM` is 2.9x larger under the
decomposition, and reflectivity is the most nonlinear diagnostic here. The
perturbation moved one prognostic; the decomposition moves all of them. A
matched-magnitude ensemble, not one member, would be needed to compare
distributions rather than realisations.

**Anything about which processor grid.** `1x4`, `2x2` and `4x1` at the same rank
count would separate seam direction, and `run_ss_case` does not expose the
decomposition, so it is not run here.

## The first attempt was invalid, and the control caught it

The perturbation was first applied to `T`, which produced **zero** difference in
every field at every frame -- a null result that would have read as "the model
is insensitive". It is not: `T` is DIAGNOSED from `THM` and the moisture, so the
first step overwrote it. Frame 0 showed the perturbation present in the initial
state and absent by minute one, which is what identified the mistake.

A null from a perturbation experiment tests where the perturbation was put
before it tests the model. The control that catches it is the initial frame.

One case, one build, one host, one realisation.
