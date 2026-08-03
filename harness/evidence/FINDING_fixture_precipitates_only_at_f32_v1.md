# This fixture precipitates only at f32, and that scopes every comparison built on it

Owner §6.4 sent me to the enthalpy ledger's normalisation. Applying the f64
instrument on the way found something larger.

## Measured

Total `rain` per column after 300 s, h = 25 s, legacy:

| | col 1 | col 2 | col 3 |
|---|---|---|---|
| **f32** (reference) | 4.7913e-04 | 2.1646e-02 | 3.5010e-02 |
| **f64** (promoted) | 2.0216e-07 | ~5.3e-316 | 0.0 |

**At f64 the fixture essentially does not precipitate.** The condensate sits near
the scheme's activation thresholds, so single precision decides whether
sedimentation reaches the ground at all.

## What that explains

Three separate observations collapse into this one:

1. **Column water is conserved at f64** — spread 1.6e-06 / 2.5e-07 / 8.8e-07
   against ~1e-02 at f32. With no outflow there is nothing for the column budget
   to lose, which is why orders taken on it are conservation residual
   (`FINDING_column_water_orders_v1`).
2. **Legacy and conservative are bit-identical at f64** — **0 of 333** G33P
   records differ, against 39 at f32 (max relative difference **3.28**, in
   `qi` at col 3 k3). The variant's single physics change is the sedimentation
   interface transfer, and its header states the interior inflow is the source
   cell's *actual entry-capped* outflow. With no cap binding, that equals the
   legacy form exactly.
3. **The conservative enthalpy advantage is a threshold effect.** Ledger residual
   at h = 25 s:

   | | col 1 | col 2 | col 3 |
   |---|---|---|---|
   | legacy f32 | −48.336 | −70.266 | +539.78 |
   | conservative f32 | −48.336 | **−11.932** | +533.09 |
   | legacy f64 | −42.092 | −21.188 | +443.74 |
   | conservative f64 | −42.092 | −21.188 | +443.74 |

   | advantage `\|R_legacy\|/\|R_cons\|` | col 1 | col 2 | col 3 |
   |---|---|---|---|
   | f32 | 1.00× | **5.89×** | 1.01× |
   | f64 | 1.00× | **1.00×** | 1.00× |

## What is withdrawn, and what is not

The conservative interface's measured advantage on this fixture is **confined to
column 2 and to f32**, and it is 1.00× once precision removes the threshold
crossing. Earlier text presented the column-2 figure as a property of the
interface; **that reading is withdrawn.** It is a measurement of how the two
variants respond to a cap event that f32 noise creates.

Not withdrawn, and worth being clear about: **the reference operator IS f32.** A
statement about f32 behaviour is a statement about the thing being certified. What
cannot be done is to read these numbers as the interface's thermodynamics, or to
extrapolate them to a case where precipitation is not threshold-marginal — which
is every operational case.

## The normalisation (owner §6.4)

`|R|/|H_start|` divides a process-scale error by the column's entire background
sensible energy plus an enthalpy-reference offset. The ledger now also reports

    eta = |R| / (|dH| + |H_out|)

On the committed chain the same residuals read 7.85% / 7.98% / 4.19% at h = 100 s
under `eta` against 3.8e-06 / 4.2e-04 / 1.3e-04 under `/H_start` — four orders of
magnitude apart, and `eta` is the one measured against what actually moved.

At f64, `eta` is ~100% in every column: with `H_out ≈ 0` the ledger reduces to
`R = dH`, so the column's enthalpy changes with nothing leaving it. That is a
non-closure of ~42 J/m² per column over 300 s, and it is present in **both**
variants identically.

## Limits

- The f64 build is an **instrument**. It is not the reference, produces no
  decision evidence, and its own non-precipitating behaviour is not "correct" —
  it is a different point on the same threshold.
- Why f32 crosses the threshold and f64 does not is not identified here.
- One fixture, 3 columns × 4 levels, 300 s, one host. A fixture whose
  precipitation is not threshold-marginal would answer the interface question
  properly; this one cannot.
- `eta` is a better norm, not a validated closure criterion. Nothing here says
  what value of `eta` should be acceptable.
