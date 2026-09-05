# Full-residual weight and transport effects; historical density-term results

Scope: historical `g33_fixture_multisubcycle_v1`, legacy, main chain, h = 25 s.
Interpretation corrected 2026-09-05 after PR #205. The archived
`G33-TRAJECTORY-001` claim is historical; `SCIENCE_STATUS.md` is the current
status authority. The table below retains the historical density-only values;
current output identifies the full-residual calculation described next. The
counterfactual requires matching interface identities and unchanged layer geometry.

## Current computation: both applied transfers are fixed

The follow-up review of `b771d0d` requires decomposition of the **full** residual,
not just clearer labeling of the density term. The analyzer now uses one function

    R(w,F) = sum_e (w_lo*dn_in - w_up*dn_out),  w=rho*dz

and computes `baseline=R(w,F)`, `metric=R(w',F)` and `actual=R(w',F')`.
`weight_effect=metric-baseline` and `trajectory=actual-metric` add to
`residual_change=actual-baseline`. Both the baseline arrival and departure stay
fixed in the counterfactual. Interface identities and layer geometry must match.

With unit thickness, departure .75 and arrival .25, a density offset from (1,2)
to (2,3) changes the full residual from -.25 to -.75: **weight effect -.50,
transport response 0**. In general the offset effect is `c*sum(B-A)`; it cancels
only when that summed transfer mismatch is zero. A changed arrival at fixed
departure is also a transport response and is now included.

Output declares `quantity=full_interface_residual`. Older JSON without that
marker decomposed the density contribution; its `metric`, `actual`, `trajectory`
and ratios have a different meaning. Recompute from the captured streams when
comparing full residuals. `density_contribution` and `number_cap_term` remain
separate accounting diagnostics, whose sum equals `actual` up to rounding.

## Historical density-term interpretation and measurements

Owner §7. The density arms land at −0.99 and +2.01 rather than exactly −1 and +2.
That was once attributed to a second-order
`effect of density on the fall speed`.
The withdrawn wording is quoted verbatim so a reader can recognise it, and so a
test can refuse to let it reappear in an active claim. The attribution was
**withdrawn**: density also changes the next call's
pre-sedimentation state, the cap state, and every density-dependent rate, so
naming fall speed picked one candidate out of several without separating them.

The same applies to the wording `gamma_n roundoff bound`, used of the γₙ
threshold. It is not a bound and not a **roundoff certificate**: the operation
count is a floor and the capped, branching kernel is not a straight-line
summation. The control's own `tolerance_basis` field says exactly this, and the
withdrawn phrasing is quoted here for the same reason as the one above.

The departure is now **decomposed** instead:

    D(ρ′) = Σⱼ Δρ′ⱼ Δzⱼ dⱼ(ρ)                 metric-only counterfactual
          + Σⱼ Δρ′ⱼ Δzⱼ [dⱼ(ρ′) − dⱼ(ρ)]      trajectory response

The first term takes the **arm's** density gap with the **baseline's** transfers,
so it is the pure measure scaling. The second is the response of this density
contribution to changed departures. Their sum is the density term `D`, not
generally the full residual. With actually applied departures and arrivals,

    R_full = D + Σⱼ ρ_lo,j (Δz_lo,j dn_in,j − Δz_up,j dn_out,j)

The extra term includes any transfer mismatch, including caps, metric
conversion and rounding. Both terms use the moist-density operator measure;
their physical number interpretation remains conditional on the unresolved
host/kernel number-unit contract. `actual/base` below is the historical JSON
name for the density-term ratio, not the full-residual ratio.

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

Ideal profiles give `metric/base` = 0 / −1 / +2 in exact arithmetic. The table
rounds ratios to four decimals; f32 profile arithmetic can perturb ideal scaling.
For the comparable inverted/x2 rows, the recorded trajectory term is
**0.45–2.04% of the metric term**. This measures changed departures' contribution
to `D`, without attributing it to a specific process.

`uniform` kills **both** terms: with every density gap zero the metric term
vanishes for any transfers whatever, and the trajectory term has nothing to
multiply. An arrival/departure mismatch can still leave `R_full` nonzero.

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

The ideal metric ratio is 1.0 under a uniform density shift and 2.0 under a
doubled gradient. The original calculation reported a 5.8e−7 deviation for
`offset+` column 2 from f32 profile arithmetic. The recorded 2.20–6.68% offset
trajectory responses describe changes in `D`; this does not establish that the
full residual depends on the gradient alone.

The precise statement has two halves, and collapsing them overstates the result
(owner §8):

| quantity | depends on |
|---|---|
| **direct metric counterfactual at fixed departures** | the density difference — a uniform offset cancels in exact arithmetic |
| **density contribution D** | density differences and changed departures |
| **full interface residual** | D plus the separately evaluated arrival/departure mismatch |

"The density magnitude is not what matters" is **too strong**. Absolute density
sets fall speeds, the sub-cycle count, the state each later call starts from and
the cap state. It therefore affects `D` through the trajectory. It also weights
the transfer-mismatch term directly whenever arrivals and departures differ.
The table does not quantify that additional response.

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

- Column 3 of `inverted` has a different interface **universe** from the
  baseline's — 69 keys against 72 — so there is no one-to-one correspondence and
  the metric counterfactual is undefined. It is reported `comparable: false`.
  `offset+` column 3 does the same; column 3 is the schedule-sensitive one.

  The differing count is a *symptom*, not the test. Interfaces are matched by
  **identity** — `(call, loop, sub-step, upper level, lower level)` — and
  decomposition requires the two key sets to be equal. Matching on count alone
  was the original form and it was unsound: a baseline with `mstep` 2-then-1 and
  an arm with 1-then-2 have the same total and describe different interfaces, so
  a positional pairing would have compared element 2 of one call against element
  1 of another and produced a confident wrong number.
- The test now **asserts the difference** — one schedule change, at that exact
  location. If a future change made every arm schedule-identical the finding's
  scope would need widening; if it made more arms differ, the decomposition's
  matched-interface assumption would break silently.

## Limits

- **The trajectory term is not further decomposed.** It measures how changed
  departures affect `D`, without apportioning the effects of fall speeds, caps
  or prior states. It does not summarize every change in the model.
- **The metric counterfactual requires matching interface identities and layer
  geometry.** This is a condition checked for each comparison.
- **Zero net mismatch does not prove zero mismatch at every interface.** The
  analyzer now reports `sum_abs_number_transfer_mismatch` alongside the net
  `number_cap_term`; `measure_only` tests net agreement only.
- One fixture, legacy, main chain, h = 25 s. The ice chain's mass control fails
  for the post-update cap, as everywhere.
