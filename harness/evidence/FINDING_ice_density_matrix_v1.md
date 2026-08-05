# The ice chain gives the same answer, on a variant that lets it be measured

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-NUMBER-009` | **active** | confirmed | g33_fixture_multisubcycle_v1, CONSERVATIVE variant, h = 25 s, ice columns 2 and 3 (column 1 carries no usable inventory). The conservative variant is what makes the measurement possible and is NOT the reference; legacy's ice chain remains unmeasurable for the post-update cap reason. Constructed probes, and the trajectory term is measured but not apportioned. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner §13-3. Every density result so far has been **main-chain only**, for a
reason that was structural rather than physical: legacy's `ice/qi` mass control
fails at −269% / −384% on the post-update inflow cap, and an uncontrolled row is
not evidence.

The conservative interface computes the inflow **once**, from the source cell's
actual outflow, so there is no post-update recapture. `ice/qi` closes — and the
ice chain becomes measurable under exactly the same arms.

That makes this a **cross-chain, cross-species, cross-variant replication**: a
different sub-cycle (`mstep_i`, not `mstep`), a different species pair
(`qi`/`ni`), and a different algorithm.

**Not an independent replication** (owner §9). It shares the same synthetic
fixture, the same density-intervention driver, the same strict parser, the same
matched-closure analyzer and the same layer-metric definition. An independent
replication would vary those; this varies the chain, the species and the
algorithm, which is a real strengthening and a smaller one than the earlier
wording claimed.

## The matrix, ice chain, conservative

`ice/qi` mass control closes in **all six arms**.

| arm | `ice/ni` col 2 | `ice/ni` col 3 | residual ratio to `as-is` |
|---|---|---|---|
| `as-is` | +6.2789% | +7.0584% | — |
| `uniform` | **+0.0000%** | **+0.0000%** | 0.0000 / 0.0000 |
| `inverted` | −7.0312% | −7.9297% | **−0.9882 / −1.0223** |
| `x2` | +11.9123% | +13.2653% | **+2.0118 / +1.9639** |
| `offset+` | +5.8259% | +6.6314% | +0.9878 / +1.0292 |
| `offset−` | +6.8325% | +7.3390% | +1.0123 / +0.9405 |

Every prediction holds: flat kills it, inverting flips it, doubling the gradient
doubles it, and a ±10% **magnitude** shift barely moves it.

## The decomposition holds there too

| arm | col | metric/base | actual/base | traj/metric |
|---|---|---|---|---|
| `uniform` | 2 / 3 | **0.0000** | 0.0000 | — |
| `inverted` | 2 / 3 | **−1.0000** | −0.9882 / −1.0223 | 1.18% / 2.23% |
| `x2` | 2 / 3 | **+2.0000** | +2.0118 / +1.9639 | 0.59% / 1.80% |
| `offset+` | 2 / 3 | **+1.0000** | 0.9878 / 1.0292 | 1.22% / 2.92% |
| `offset−` | 2 / 3 | **+1.0000** | 1.0123 / 0.9405 | 1.23% / 5.95% |

`metric/base` is exact on ice as it is on main, so the whole departure is again
the trajectory term — here 0.59–5.95%. Unlike `inverted` on main column 3, **no
ice column changes its sub-step schedule**, so every row is comparable.

## What this changes

The scope line "MAIN chain only … so ice rows are excluded" was a limitation of
the *legacy cap*, not of the mechanism. With the cap removed the ice chain
answers the same way, which is what a measure-mismatch — as opposed to a
chain-specific accident — has to do.

## Limits

- **Ice column 1 has no rain-equivalent inventory**, so it produces no usable row
  in any arm. Two columns, not three.
- **Shared apparatus.** Fixture, driver, parser, analyzer and metric definition
  are common to both chains, so a defect in any of them would reproduce here too.
  That is what "not independent" means, concretely.
- **This is the conservative variant.** It is the variant whose cap fix makes the
  measurement possible, and it is not the reference. Legacy's ice chain remains
  unmeasurable for the reason it always was.
- The arms are constructed probes, not physical atmospheres, and the trajectory
  term is measured but not apportioned — both as on the main chain.
- One fixture, h = 25 s.
