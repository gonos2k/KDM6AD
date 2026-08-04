# The ice chain's missing term is the post-update-reservoir inflow cap — and it lifts the main-chain result to an exact match

The matched closure's `qi` mass control failed at −384%/−269%, which said the ice
accounting was missing a term. This identifies it, and the instrumentation added
to find it turned the main-chain number result from a residual into an exact
agreement with the predicted mechanism.

## The missing term

`dq(i,k+1)` is written **twice, with different caps**:

```
iteration k+1:  dqi(i,k+1) = min(falk(i,k+1,4)*dtcld/dend(i,k+1), qci(i,k+1,2))
                                                    ← capped against PRE-update content
                qci(i,k+1,2) = max(qci(i,k+1,2) - dqi(i,k+1) + dqi(i,k+2), 0.)

iteration k:    dqi(i,k+1) = min(falk(i,k+1,4)*delz(i,k+1)/delz(i,k)*dtcld/dend(i,k),
                                 qci(i,k+1,2))      ← capped against POST-update content
                qci(i,k,2)   = max(qci(i,k,2) - dqi(i,k) + dqi(i,k+1), 0.)
```

The first is what **left** cell k+1; the second is what **arrives** at cell k.
When the second cap binds, the difference is destroyed. This is the
reference-faithful interface defect already recorded as P0-4b
(`post-update-reservoir inflow cap`), here located per interface.

## Measured

New emissions, both macro-gated and verified bit-identical to the committed
members: `G33F CAPIN` gives each cell's own outflow beside the inflow it grants
below, and `G33F TOPOUT` gives the top cell's removal — the top cell is updated
outside the interior loop, so its departure had no record and the topmost
interface was invisible.

Pairing departure against arrival under the ρΔz measure, h = 25 s:

| chain | col | mass residual | interface term | explained |
|---|---|---|---|---|
| ice | 2 | −2.942160e-03 | −2.942160e-03 | **100.00%** |
| ice | 3 | −5.685992e-03 | −5.685992e-03 | **100.00%** |

**The cap accounts for the entire ice mass residual.** It binds at **39 of 255**
interfaces, all of them in the ice chain; the main chain's mass residual stays at
1e-10–1e-12, i.e. nothing binds there.

## What this does to the number result

With the interface term included, every row closes — mass and number, both
chains. So the number "residual" was never unaccounted: it lives **at the
interfaces**, which is where the ρΔz-vs-Δz mismatch acts. Separating that
prediction from the cap:

| chain | col | number created at interfaces | ρΔz-vs-Δz prediction | ratio |
|---|---|---|---|---|
| **main** | 1 | 8.43890e+04 | 8.43890e+04 | **1.0000** |
| **main** | 2 | 4.05894e+04 | 4.05894e+04 | **1.0000** |
| **main** | 3 | 1.37209e+04 | 1.37209e+04 | **1.0000** |
| ice | 2 | −2.94e+06 | 1.03e+05 | −28.58 |
| ice | 3 | −5.24e+08 | 1.81e+07 | −28.90 |

**On the main chain the number created at interfaces equals
`Σ (den_below − den_above)·delz_above·dn` to four decimals**, computed from
independently emitted per-interface transfers, with the mass control on the *same*
interfaces closing to roundoff. That is a quantitative confirmation of the
mechanism, not a residual consistent with it.

The **ice** rows are cap-dominated (the cap binds at 39 interfaces) and their
number term is not a clean measure-mismatch measurement — ratio −28.6/−28.9, sign
flipped because the arrival is far below the uncapped value. The ice chain
measures the cap; the main chain measures the measure.

## Limits

- One fixture, legacy only, h = 25 s. The conservative variant is not run.
- The prediction and the measurement share the emitted `dn`, so this shows the
  interface arithmetic is what the source says it is and quantifies its effect;
  it is not an independent re-derivation of `dn`.
- The absolute `# m⁻²` figures carry the moist-vs-dry basis offset
  (`FINDING_number_mass_basis_v1`, 0.10% here). Ratios are unaffected.
- Whether the cap or the measure dominates in a real case is unmeasured; here it
  is chain-dependent.
