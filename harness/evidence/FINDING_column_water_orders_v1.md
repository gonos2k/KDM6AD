# The column-water orders are precision drift, and the `mstep` attribution rested on them

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status |
|---|---|
| `G33-WATER-CONS-001` | **withdrawn → G33-WATER-CONS-002** |
| `G33-WATER-CONS-002` | **active** |
| `G33-WATER-ORDER-001` | **withdrawn → G33-WATER-ORDER-002** |
| `G33-WATER-ORDER-002` | **active** |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

A correction to this branch's headline result, found by turning the f64 instrument
(built for the roundoff question) on the column budgets.

## Measured

Total ρΔz column water at the end of the run, across the whole chain
h = 100 → 0.39 s, at both precisions:

| | col 1 | col 2 | col 3 |
|---|---|---|---|
| spread across members, **f32** | 5.72e-03 | 7.03e-03 | 9.63e-03 |
| spread across members, **f64** | 1.63e-06 | 2.46e-07 | 8.82e-07 |

At f64 column 3's total is **1.352435e-01 at every member** to seven figures while
the species redistribute underneath it (qc 6.08e-2 → 6.81e-2, qi 1.52e-2 → 1.09e-2).

**Correction (owner §5): spread is not conservation.** The table above measures
STEP-INSENSITIVITY. Every member losing the same amount would give a spread of
zero and a conservation residual of that amount, so "column water is conserved at
f64" did not follow from it. The residual has since been computed properly,
`R_W = (W_final − W_initial) + P_surface`, at h = 25 s:

| arm | col | ΔW | P | **R_W** | R_W/W_i |
|---|---|---|---|---|---|
| f64 | 1 | −2.02e-07 | 2.02e-07 | **−4.4e-17** | −9e-17 |
| f64 | 2 | −1.6e-08 | ~0 | **−1.6e-08** | −6.6e-08 |
| f64 | 3 | 0 | 0 | **0** | 0 |
| f32 | 2 | −5.09e-03 | 2.16e-02 | **+1.66e-02** | **6.8%** |
| f32 | 3 | −1.18e-02 | 3.50e-02 | **+2.32e-02** | **17.1%** |

The conclusion survives on the right evidence — at f64 the budget closes from
1e-16 to 6.6e-8 relative. The f32 rows do **not** close, but `P` there is the WRF
`rain` diagnostic, which is documented to depart from the ρΔz budget by up to 10×
(P0-4b), so those are that defect plus any true non-conservation, not a clean
statement. `conservation_spread` is renamed `cross_member_endpoint_spread` and the
analyzer now prints `R_W` per member.
At f32 the same total wanders through 1.2229e-1, 1.2231e-1, 1.2340e-1, 1.2348e-1,
1.2333e-1, 1.2321e-1.

**The f32 variation is ~10⁴× the f64 variation.** It is removed by precision, so it
is not a property of the discretisation.

## What that costs

The `ρΔz column budgets — successive order per column` table takes
`E_h = |W_h − W_{h/2}|` and reports `log₂(E_h/E_{h/2})` as an order. On a quantity
whose member-to-member variation is precision drift, that exponent describes the
drift. Column 3's `−5.860, +3.884, −1.017, +0.407, +5.222` — the numbers this
branch used to argue that the sedimentation sub-step count `mstep` explains column
3's non-convergence — are of that kind.

**So the `mstep` attribution for column-3 WATER is withdrawn.** Not because `mstep`
was shown irrelevant, but because the measurement it rested on does not measure
what its column header says.

Two further things follow, and they cut in opposite directions:

- **Against `mstep`:** at f64, column 3's `ni` converges at first order across the
  *whole* chain — `+1.199, +0.980, +0.954, +0.967, +0.981, +0.990, +0.995` —
  including h = 100 → 25 where `mstep_i` is 4 → 2 → 1. A varying sub-step count did
  not prevent convergence there. The earlier f32 figures (`+1.461, +0.863`) were
  the same quantity seen through precision noise.
- **For `mstep`:** the source-level fact is untouched. `dtcld/mstep` is what the
  sedimentation operator integrates, so an external-`dtcld` dyadic chain does not
  dyadically refine it. That was never an inference from these orders.

## Grades after this

| claim | grade |
|---|---|
| `dtcld/mstep` is the refinement variable, not `dtcld` | **confirmed** (source) |
| `mstep_i` reaches 1 two levels before `mstep` in column 3 | **confirmed** (measured) |
| `mstep` explains column 3's erratic *water* orders | **withdrawn** |
| a varying `mstep_i` prevents `ni` from converging | **refuted** at f64 |
| `th`/`qv` max-norm fine-step turnover is roundoff | **withdrawn** — precision-dependent is confirmed, the CAUSE is HOLD (`G33-TURNOVER-002`) |

## Why it was not visible before

The column-water anomaly and the roundoff turnover sit at the same end of the chain
and were read as one phenomenon. They are not: the `th` max-norm turnover
**disappears** at f64, while column 1's water anomaly at h = 1.5625 s **survives**
it with the same shape, scaled by ~2370×. One is precision-limited, the other is a
property of the water diagnostic on this fixture. Reading them together produced a
single story that was wrong about half of it.

`g33_refine_analyze` now prints this caveat above the budget table on any f32
stream, so the exponents cannot be quoted as rates again.

## Limits

- The f64 build is an **instrument**, not the reference. It produces no decision
  evidence; the reference operator is f32, which is why the drift exists at all.
- The mechanism of the f32 drift is not identified here — only that it is
  precision-dependent and ~10⁴× the f64 level.
- Column 1's water anomaly at h = 1.5625 s is precision-**independent** and remains
  unexplained. It is one member out of line, not a regime change: the next member
  returns to the first-order trend.
- Synthetic fixture, 300 s. No C4 verdict.
