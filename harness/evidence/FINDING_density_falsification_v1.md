# The Δz-only number metric, across a layer-air-mass gradient, creates column number

**The density gradient is not the defect.** A density gradient is ordinary
atmospheric stratification; it is what the air does. The defect is the **missing
layer-air-mass ratio in the number inflow**, and what this experiment established
is the **interaction term** between the two (owner §4).

Writing `m_k` for the layer air mass per unit area that the number mixing ratio is
referenced to, a conserving update would be

    n_l ← n_l + d_u · m_u / m_l

while the kernel does

    n_l ← n_l + d_u · Δz_u / Δz_l

so with `m_k = ρ_k Δz_k` the residual is `(ρ_l − ρ_u) Δz_u d_u`. The causal chain
is therefore

    ordinary density gradient  ×  missing density ratio in the number transfer
        →  column number created (or destroyed)

Fixing the second factor is the correction; the first is not a fault to fix.

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-NUMBER-008` | **active** | confirmed | OPERATOR-LEVEL: this is causality under the current den*dz ledger, where den is MOIST density, and must NOT be promoted to physical dry-air column-number causality -- the physical measure is sum m_d,k n_k (owner §10, G33-BASIS-002/003). MAIN chain only on g33_fixture_multisubcycle_v1, legacy, h = 25 s. The ice chain's mass control fails in every arm (post-update inflow cap, G33-ICE-CAP-001), so ice rows are excluded. The perturbed profiles are constructed probes, not physical atmospheres; this establishes the cause, not the magnitude in a forecast. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner priority-5. `G33-NUMBER-001` says number is created because the inflow
weight carries `delz(k+1)/delz(k)` where the ρΔz measure needs
`den(k+1)delz(k+1)/(den(k)delz(k))`, leaving

    R_N = (den(lower) − den(upper)) · delz(upper) · dn

per interface. Until now that was supported by a source reading and a hypothesis
test on **one** density profile — the fixture's own. A mechanism confirmed on a
single profile is indistinguishable from any other quantity that happens to
correlate with it.

The formula's density dependence is the part that can be **wrong**, so it is the
part to attack: it forbids specific outcomes under specific perturbations.

## The three forbidden outcomes

The density profile is *forcing*, and the driver builds the forcing, so the
controlled variable can be varied with the kernel and the fixture both untouched.
A fourth positional argument rewrites `den(i,:)` about the column's own mean
after it is filled (`g33_refine_driver.f90`), leaving `delz`, the state and every
other input alone:

| arm | profile | prediction | falsified if |
|---|---|---|---|
| `uniform` | `den ≡ mean` | R_N = 0 | number is still created |
| `inverted` | `2·mean − den` | R_N → **−**R_N | sign does not flip |
| `x2` | `mean + 2(den − mean)` | R_N → **2**·R_N | magnitude does not scale |

## What happened

Raw residual, main chain, legacy, h = 25 s (`mstep` 1 / 1–2 / 1–3 by column):

| arm | col 1 | col 2 | col 3 |
|---|---|---|---|
| `as-is` | 8.438942e+04 | 4.058947e+04 | 1.372095e+04 |
| `uniform` | 1.164551e−01 | 0.000000e+00 | 5.222656e−02 |
| `inverted` | −8.351415e+04 | −4.026098e+04 | −1.376539e+04 |
| `x2` | 1.697653e+05 | 8.154752e+04 | 2.800075e+04 |

As a ratio to the unperturbed residual — the prediction, and the measurement
beside it:

| arm | predicted | col 1 | col 2 | col 3 |
|---|---|---|---|---|
| `uniform` | 0 | 0.0000 | 0.0000 | 0.0000 |
| `inverted` | −1 | **−0.9896** | **−0.9919** | **−1.0032** |
| `x2` | +2 | **+2.0117** | **+2.0091** | **+2.0407** |

Flattening the density profile removes **99.9999%** of the number creation
(1.4e−6, 0, 3.8e−6 of the original), and what remains is below the same γₙ bound
the mass control is held to — 0.116 against 3.09, 0 against 1.68, 0.052 against
0.641. It is accumulation roundoff, not a residual signal.

### The control that makes `uniform` mean something

An arm that stopped the sedimentation would also show zero creation. Surface
number outflow across the four arms:

| | col 1 | col 2 | col 3 |
|---|---|---|---|
| `as-is` | 5.62463e+05 | 3.04321e+05 | 1.15884e+05 |
| `uniform` | 5.39214e+05 | 2.92989e+05 | 1.11985e+05 |

Number is still being transported to the surface at 96% of the original rate
while the creation term falls by six orders of magnitude. **The process is still
running; only the residual is gone.**

### The mass control holds in every arm

Perturbing the forcing could have broken the accounting rather than the
mechanism, which would make all four arms unreadable. It did not: `main/qr`
closes at 2e−7 relative or better in all four (−1.51e−10, −2.71e−10, −1.76e−10,
−8.68e−11 against outflows of ~4.6e−4). Every number row above is admissible
under `g33_matched_closure.usable()`.

### The sub-step schedule does not move

`mstep` is 1 / 1–2 / 1–3 by column and `mstep_i` is 1, **identically in all four
arms**. The perturbation changed the density values without changing the
operator's discrete schedule, so the arms are compared over the same number of
accumulations — the same γₙ basis, and the same number of interfaces at which the
residual can be generated.

## Why not exactly −1 and +2

**The three arms are not equally strong, and the strongest is `uniform`.** Under a
flat profile every `(den_below − den_above)` is zero, so R_N = 0 is forced
*whatever the trajectory does* — the prediction survives the fact that changing
density also changes the fall speeds, the state and every subsequent step.
`inverted` and `x2` have no such immunity: they predict a specific magnitude, and
that magnitude assumes `dn` is roughly carried over from the unperturbed run.

Density enters the fall speed as well as the transfer weight, so `dn` is not held
fixed. **Attributing the 1–4% departure to fall speed alone is withdrawn**
(owner §7): density also changes the pre-sedimentation state of the next external
call, the cap state, and every density-dependent rate, so "second-order effect of
density on the fall speed" names one candidate among several without separating
them.

What the departure IS, exactly, is the sum of a metric term and a trajectory
response,

    R(ρ′) = Σ_j Δρ′_j Δz_j d_j(ρ)          metric-only counterfactual
          + Σ_j Δρ′_j Δz_j [d_j(ρ′) − d_j(ρ)]   trajectory response

and until those are computed separately the split is unmeasured. What the two
weaker arms still establish is that a competing explanation would have to
reproduce −0.99 and +2.01 across three columns by some other route.

## Limits

- **Main chain only.** The ice chain's mass control fails in all four arms
  (−269% to −384%), for the reason `FINDING_ice_chain_missing_term_v1.md` gives —
  the post-update inflow cap — so `ice/ni` is excluded structurally here, exactly
  as it is elsewhere. This experiment says nothing new about ice.
- **The perturbed arms break the equation of state.** `den` is rewritten while
  `p`, `tk` and `qv` are left alone, so the `uniform`, `inverted` and `x2` columns
  are not hydrostatically or thermodynamically consistent atmospheres. That is
  acceptable *here* because the quantity under test is the transport arithmetic,
  which takes `den` as an input and never re-derives it — and the mass control
  closing to 2e−7 in every arm shows the accounting did not notice. It would not
  be acceptable for any claim about how the model behaves on real air.
- **One fixture, one algorithm, one step.** `g33_fixture_multisubcycle_v1`,
  legacy, h = 25 s. The perturbed profiles are constructed, not physical: an
  inverted or contrast-doubled column is a probe of the operator, not an
  atmosphere anyone would forecast.
- **This does not measure how much number is created in a real forecast.** It
  establishes *why* it is created. The magnitude question is `G33-NUMBER-002`
  and `G33-NUMBER-003`, and is unchanged by this.
- The default path is byte-unchanged: with no fourth argument, the driver
  reproduces the committed `n12.rezero` stream bit-identically.

## Reproducing

```
harness/g33_fortran/refine_build.sh <out> \
    --fixture=g33_fixture_multisubcycle_v1 --algo=legacy --nflux
<out>/g33_refine_driver 12 rezero 3 {as-is|uniform|inverted|x2}
```
then `g33_matched_closure.analysis()` on the stream.
