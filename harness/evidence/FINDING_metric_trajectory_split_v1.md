# The departure from −1 and +2 is the trajectory term, and it is 0.45–2.04%

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-TRAJECTORY-001` | **active** | confirmed | g33_fixture_multisubcycle_v1, legacy, main chain, h = 25 s. The trajectory term is not further decomposed -- it is everything the perturbation did to the run, and its size is measured, not apportioned. The metric counterfactual is defined only where the sub-step schedule holds. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner §7. The density arms land at −0.99 and +2.01 rather than exactly −1 and +2.
That was once attributed to "density also changes the fall speed", and the
attribution was **withdrawn**: density also changes the next call's
pre-sedimentation state, the cap state, and every density-dependent rate, so
naming fall speed picked one candidate out of several without separating them.

The departure is now **decomposed** instead:

    R(ρ′) = Σⱼ Δρ′ⱼ Δzⱼ dⱼ(ρ)                 metric-only counterfactual
          + Σⱼ Δρ′ⱼ Δzⱼ [dⱼ(ρ′) − dⱼ(ρ)]      trajectory response

The first term takes the **arm's** density gap with the **baseline's** transfers,
so it is the pure measure scaling. The second is everything the perturbation did
to the run itself. Their sum is the measured residual identically — this is an
identity, not a fit.

## Measured

| arm | col | metric/base | actual/base | trajectory | traj/metric |
|---|---|---|---|---|---|
| `uniform` | 1–3 | **0.0000** | 0.0000 | 0.0 | — |
| `offset+` | 1 | **1.0000** | 0.9775 | −1.898e+03 | **2.25%** |
| `offset+` | 2 | **1.0000** | 0.9780 | −8.943e+02 | **2.20%** |
| `offset−` | 1 | **1.0000** | 1.0255 | 2.154e+03 | **2.55%** |
| `offset−` | 2 | **1.0000** | 1.0250 | 1.014e+03 | **2.50%** |
| `offset−` | 3 | **1.0000** | 1.0668 | 9.170e+02 | **6.68%** |
| `inverted` | 1 | **−1.0000** | −0.9896 | 8.747e+02 | **1.04%** |
| `inverted` | 2 | **−1.0000** | −0.9919 | 3.285e+02 | **0.81%** |
| `inverted` | 3 | — | — | — | not comparable |
| `x2` | 1 | **+2.0000** | +2.0117 | 9.870e+02 | **0.58%** |
| `x2` | 2 | **+2.0000** | +2.0091 | 3.688e+02 | **0.45%** |
| `x2` | 3 | **+2.0000** | +2.0407 | 5.589e+02 | **2.04%** |

`metric/base` is **exactly** 0 / −1 / +2 — by construction, since those profiles
scale every density gap by exactly that factor. So the entire departure is the
trajectory term, and it is **0.45–2.04% of the metric term**. Measured, not
attributed.

`uniform` kills **both** terms: with every density gap zero the metric term
vanishes for any transfers whatever, and the trajectory term has nothing to
multiply. That is the formal reason it is the strongest arm.

## The offset arm separates gradient from magnitude directly

Scaling the contrast changes the gradient *and* the absolute density together.
Adding a **constant** to every level changes only the magnitude — and a constant
cancels out of `(ρ_below − ρ_above)` identically. So `offset±` (±10% of the
column mean) is the sharpest available test of *which* of the two matters:

| arm | what moved | metric/base | actual/base |
|---|---|---|---|
| `x2` | the **gradient** | **2.0000** | 2.0117 / 2.0091 / 2.0407 |
| `offset+` | the **magnitude**, +10% | **1.0000** | 0.9775 / 0.9780 |
| `offset−` | the **magnitude**, −10% | **1.0000** | 1.0255 / 1.0250 / 1.0668 |

**The metric term is exactly 1.0 under a 10% density shift and exactly 2.0 under
a doubled gradient.** Eleven of the twelve metric ratios are bit-exact; the
twelfth (`offset+` column 2) is 5.8e−7, which is f32 roundoff on the offset
addition itself. So the residual follows the **gradient**, and the 2.25–6.68% it
moves under an offset is trajectory response by construction — the measure did
not change at all.

That is the cleanest statement of the mechanism available from this fixture:
a density *gradient* is what the defective metric interacts with; the density
*magnitude* is not.

## A control of mine was defective, and it hid a real effect

The finding previously claimed `mstep`/`mstep_i` were identical in all four arms,
as a control. The test behind it built

```python
{k: v for c in nt.calls(text) for k, v in c["mstep"].items()}
```

whose keys are `(loop, chain, col)` — **identical across calls** — so later calls
overwrote earlier ones and the comparison saw only the last call. Keyed per call:

> **`inverted`, call 1, column 3, main chain: `mstep` 3 → 2.**

Density sets the fall speed and `mstep` is derived from it, so a large enough
density change moves the schedule. The claim "identically in all four arms" is
**corrected**: it holds for `uniform` and `x2`, and not for `inverted`.

Two consequences, both handled rather than tolerated:

- Column 3 of `inverted` has 69 interfaces against the baseline's 72, so there is
  no one-to-one correspondence and the metric counterfactual is undefined. It is
  reported `comparable: false`. `offset+` column 3 does the same — column 3 is
  the schedule-sensitive one. Zipping the two lists would have paired unrelated
  interfaces and produced a confident wrong number.
- The test now **asserts the difference** — one schedule change, at that exact
  location. If a future change made every arm schedule-identical the finding's
  scope would need widening; if it made more arms differ, the decomposition's
  matched-interface assumption would break silently.

## Limits

- **The trajectory term is not further decomposed.** It is everything the
  perturbation did to the run: fall speeds, the cap state, the state each later
  call starts from. This measures its size; it does not apportion it.
- **The metric counterfactual is only defined where the schedule holds.** That is
  a property of these arms on this fixture, not a general guarantee.
- One fixture, legacy, main chain, h = 25 s. The ice chain's mass control fails
  for the post-update cap, as everywhere.
