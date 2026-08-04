# The conservative variant carries the number defect unchanged — and fixing the cap makes the ice chain measurable

`G33-NUMBER-003` stood as **predicted, unmeasured**: the conservative variant was
expected to keep the number path while fixing the mass measure. It is now
measured, and the same run corroborates the ice-cap diagnosis independently.

## Instrumenting it needed per-algorithm anchors

The overlay refused to build against the conservative module — loudly, on a
missing anchor, rather than instrumenting the wrong statement. That variant
rewrote the sedimentation update: the interior inflow is the source cell's
**actual capped outflow**, converted by `src_metric/dst_metric` for mass, while
number keeps `delz(k+1)/delz(k)`:

```
qrs(i,k,1) = qrs(i,k,1) - dqr(i,k) + dqr(i,k+1)*src_metric/dst_metric   ← ρΔz
nrs(i,k,1) = nrs(i,k,1) - dnr(i,k) + dnr(i,k+1)*delz(i,k+1)/delz(i,k)   ← Δz only
```

The instrumentation sites are therefore keyed by algorithm. Both arms verified
bit-identical to their plain builds at N = 12 and 96.

## Measured, h = 25 s, matched control on every row

| row | legacy | conservative |
|---|---|---|
| `main/qr` ×3 | mass control OK | mass control OK |
| **`main/nr/1`** | **15.0036%** | **15.0036%** |
| **`main/nr/2`** | **13.3377%** | **13.3377%** |
| **`main/nr/3`** | **11.8402%** | **11.8402%** |
| `ice/qi/2,3` | **UNUSABLE** (cap) | **mass control OK** |
| **`ice/ni/2`** | unmeasurable | **6.2789%** |
| **`ice/ni/3`** | unmeasurable | **7.0584%** |

Two things follow.

**1. The number defect is unchanged — bit-for-bit.** `main/nr/1` is
`0.150035513206531` in both variants, not merely close. The conservative
interface fixes the *mass* measure and leaves number on `Δz`, so the created
number is identical. `G33-NUMBER-003` moves from **predicted** to **measured**.

**2. The ice-cap diagnosis is corroborated by a variant that fixes the cap.**
In legacy, `ice/qi` failed its mass control at −384%/−269% and both ice rows were
unusable. The conservative variant computes the inflow once, from the source
cell's actual outflow, so there is no post-update recapture — and its `ice/qi`
control now closes to roundoff, which makes the ice **number** defect measurable
for the first time: **+6.28% / +7.06%**.

That is an independent line of evidence for
`FINDING_ice_chain_missing_term_v1`: the residual attributed to the cap
disappears in the variant that removes the cap.

## Limits

- One fixture, h = 25 s. The `mstep = 10` case was not re-run for conservative.
- The ice number figures are smaller than the main-chain ones (6–7% against
  12–15%); whether that is the density profile the ice chain sees or something
  else is not established.
- Ratios are unaffected by the moist-vs-dry basis offset; the absolute `# m⁻²`
  figures carry it (`FINDING_number_mass_basis_v1`).
- No C4 verdict.
