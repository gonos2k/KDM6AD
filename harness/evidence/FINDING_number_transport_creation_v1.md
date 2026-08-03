# Sedimentation creates column number: measured, and the alternative hypothesis excluded

The `nr` number-moment release blocker, quantified on the pinned legacy reference.

## The arithmetic, from the source

Mass carries the density ratio; number does not (F:1214-1224):

```
falk (i,k,1) = dend(i,k)*qrs(i,k,1)*work1(i,k,1)/mstep      <- built with dend
dqr  (i,k+1) = min(falk (i,k+1,1)*delz(i,k+1)/delz(i,k)*dtcld/dend(i,k), ...)
                                                            ^^^^^^^^^^^ and divided by dend

falkn(i,k,1) =           nrs(i,k,1)*workn(i,k,1)/mstep      <- no density
dnr  (i,k+1) = min(falkn(i,k+1,1)*delz(i,k+1)/delz(i,k)*dtcld,          ...)
                                                            <- and none here either
```

`nrs(i,k,1) = nr(i,k,j)` (F:388) makes `nrs` the prognostic number **mixing**
ratio, so the physical column measure is `Σ den·delz·nr`. Weighted, `den(lower)·
delz(upper)·a` arrives where `den(upper)·delz(upper)·a` left. Density increases
downward, so **every interface creates number**.

## Two things that look like proof and are not

Both were caught by working them out, not by the numbers looking wrong.

1. Decomposing the residual as `Σ [den(lower)−den(upper)]·delz(upper)·a` and
   recovering it exactly is an **algebraic identity** of the recursion used to
   get `a` — it telescopes for any `a` whatsoever. It reported `1.00000` in every
   row and meant nothing.
2. Running the **mass** channel through the same recovery as a "control" is
   forced the same way: with `w = den(upper)delz(upper)/(den(lower)delz(lower))`
   every telescoped term is identically zero, so mass returns ~0 for any data.
   It returned 4e-19 on fluxes of 1e-3 — an arithmetic check, not a control.

## What is evidence: a hypothesis test against data the recursion never sees

With `mstep == 1` there is a single substep, so the per-interface transfers follow
from the state change alone, top down:

    a_0 = x_0 − x'_0                        (top cell has no inflow)
    a_t = x_t − x'_t + a_{t−1}·w_t

Recover `a` under each candidate inflow weight and compare the recovered
bottom-cell transfer against the **independently emitted `falln` accumulator**,
which the recursion does not consume. A wrong `w` does not reproduce it.

| | (A) `dz` only — F:1222 | (B) with density |
|---|---|---|
| `nr` col 1 | **1.00001** | 0.84997 |
| `nr` col 2 | **1.00000** | 0.92532 |
| `nr` col 3 | **1.00000** | 0.87436 |
| `ni` col 3 | 1.00614 | 0.94313 |

The source says (A); the run agrees to five decimals and **excludes (B) by
7–15%**. `recovered/falln = 1.0000` is simultaneously the test that the caps did
not bind, so those rows are exact.

## The closure, on emitted data only — and here the mass control is real

The recovered-transfer route above needs the `mstep == 1` restriction and a
hypothesis test. There is a stronger form. The segment
`outer_pre_sed .. outer_post_sed` is F:1189-1340 — **both sedimentation
sub-cycles and nothing else** — so it isolates transport *temporally*, without
needing a fixture with the microphysical sources switched off. Conservation under
the ρΔz measure then means

    [X(post_sed) − X(pre_sed)] + F_surface = 0

with **every term read from the stream** — the column integrals from the stage
records, `F` from the emitted `bottom_fall_qr` / `bottom_falln_*` accumulators.
No recursion appears anywhere, so nothing forces the mass row to vanish:

| species | col | calls | surface out | residual | residual/out |
|---|---|---|---|---|---|
| **qr** | 1 | 1 | 5.985e-05 | 1.405e-10 | **+0.0002%** |
| **qr** | 2 | 3 | 8.538e-05 | −4.263e-12 | **−0.0000%** |
| **qr** | 3 | 1 | 7.543e-06 | 3.070e-12 | **+0.0000%** |
| `ni` | 3 | 95 | 3.345e+08 | 2.094e+07 | **+6.26%** |
| `nr` | 2 | 1 | 3.769e+04 | 5.155e+03 | **+13.68%** |

**Mass closes to f32 roundoff; number does not, by 6–14%.** Same segment, same
cells, same kind of emitted accumulator — the transfer arithmetic is the only
difference. Calls where a `min`/`max` cap bound are excluded per species, detected
as a disagreement between the emitted accumulator and the recovered transfer;
such a call measures the cap, not the transport.

## How much number is created

ρΔz column number across the sedimentation segment, `mstep == 1`, h = 3.125 s:

| species | col | calls | created (# m⁻²) | per call | of final column |
|---|---|---|---|---|---|
| `ni` | 3 | 96 | 2.113e+07 | **0.248%** | **19.6%** |
| `ni` | 2 | 1 | 1.596e+05 | 4.30% | 10.2% |
| `nr` | 2 | 3 | 8.244e+03 | 0.034% | 0.44% |
| `nr` | 1 | 1 | 1.055e+04 | 0.027% | 0.03% |

**In the ice-heavy column, transport alone inflates column ice number by ~0.25%
per call, compounding to ~20% of what the column ends with** over 300 s.

**Step-robust.** Total created for `ni` col 3 is 1.978e+07 at h = 6.25 s against
2.113e+07 at h = 3.125 s — within 7%. Creation scales with the number *transported*,
which the physics sets, not with how many calls it is split into. So the ~20% is
not an artifact of measuring at a fine step.

`nr` col 3 reads 4475% "of final" because that column ends with 94 particles m⁻²;
the ratio is meaningless there and the per-call figure (0.12%) is the usable one.

## Limits

- **`mstep == 1` only.** With more substeps the composition is not invertible from
  endpoints, so operational steps (where `mstep` is 5–10) are not measured. The
  step-robustness above is evidence against a strong step dependence, not a
  measurement at operational steps.
- **Legacy reference.** The conservative variant was not run through this. It
  fixes the *mass* measure and leaves number on the legacy one
  (`sedimentation_conservative.cpp:91-92` against `:109`), so the defect should be
  unchanged — predicted, not measured.
- **Cap-dominated rows are excluded, not explained.** `ni` col 2's single call
  reads `recovered/falln = 3.60`: the caps bound hard and the single-variable
  recursion does not describe that call. The kernel recomputes the inflow cap
  against the *already updated* cell above (F:1306-1307), so out(above) ≠
  in(below)/w when it binds.
- Synthetic fixture, 4 levels, 300 s. This is the mechanism and its size on this
  fixture, not an operational impact estimate. No C4 verdict.
