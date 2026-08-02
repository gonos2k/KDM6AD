# The §9 sweep does not refine, and the discarded members are a partial control

Owner review §9 asks for 300 s reached as 1×300, 2×150, 3×100, 6×50, 12×25, at the
`kdm62D` boundary, to see which thermodynamic-coefficient policy converges. Running
it produces a sequence whose error to the finest member goes **up** before it goes
down, which reads as an operator that does not converge.

It is not. The sweep does not refine.

Revised throughout after owner review of the first version. What changed is listed
under *Corrections* at the end; the two claims that did not survive are the
convergence orders and the "coefficient-only" description of the N=1/N=3 contrast.

## The kernel sets its own step

```fortran
F:930   loops = max(nint(delt/dtcldcr),1)        dtcldcr = 120 s   (F:56)
F:931   dtcld = delt/loops
F:932   if(delt.le.dtcldcr) dtcld = delt
```

so the integration step is `dtcld`, not `delt`:

| N | delt | loops | **dtcld** | |
|---|---|---|---|---|
| 1 | 300 | 3 | **100** | |
| 2 | 150 | 1 | **150** | coarser than N=1 |
| 3 | 100 | 1 | **100** | duplicate of N=1 |
| 6 | 50 | 1 | 50 | |
| 12 | 25 | 1 | 25 | |

`nint(150/120) = nint(1.25) = 1`, and because `delt > dtcldcr` the guard at F:932
does not apply, so N=2 integrates in one 150 s step — the coarsest member of a
sweep meant to be the second-finest.

**`dtcldcr` is a target interval, not an upper bound.** Because the divisor is
rounded with `nint` rather than a ceiling, `dtcld` exceeds 120 s for any `delt` in
(120, 180): it reaches 175 s at `delt = 175`, about 1.46× nominal. Whether that is
intended is a separate question and a production-physics one — if 120 s is a real
stability limit then `nint` should be `ceiling`, and that is an owner science item,
not something to change under a refinement experiment. This document takes no
position beyond removing the "limit"/"criterion" language the first version used.

**Corrected chain: N ∈ {3, 6, 12, 24}** → dtcld = 100, 50, 25, 12.5. A clean
halving.

## Order is estimated only from successive differences

The finest member is not the exact solution, and treating it as one biases the
exponent upward. With `X_h = X* + C h^p`,

```
E_h = |X_h - X_hf| = |C| |h^p - hf^p|        so   E_h / E_{h/2} != 2^p
```

For a truly **first-order** operator with `hf = 12.5 s` the ratio reads **+1.222**
then **+1.585**. The first version of this document computed orders from that
series, got +1.221/+1.413 for `th` and +1.205/+1.614 for `number`, and read them as
"near or above first order". They are what exactly first order looks like through
the wrong estimator. **Those numbers are withdrawn.** The analyzer no longer
computes an order from the error-to-finest series at all.

## The corrected chain, read correctly

`legacy`, fixture `arithmetic_multisubcycle_v1`, max absolute difference over cells.

**Successive differences** `E_h = |X_h - X_{h/2}|` — the only valid order estimate:

| | h=100 | h=50 | h=25 | p(100→50) | p(50→25) |
|---|---|---|---|---|---|
| `th` | 2.985e-02 | 1.495e-02 | 8.423e-03 | **+0.997** | **+0.828** |
| mass | 2.819e-05 | 1.901e-05 | 3.921e-06 | +0.568 | +2.278 |
| number | 3.806e+06 | 1.879e+06 | 9.121e+05 | **+1.018** | **+1.043** |
| precip | 4.409e-03 | 2.088e-02 | 1.637e-02 | −2.244 | +0.351 |

**Error to the finest (N=24)** — magnitude and monotonicity only, no order:
monotone decreasing in all four groups.

On this four-member chain `th` and the `number` group sit near p = 1 by the valid
estimator. Both readings are qualified by the six-member chain below: the `number`
group figure is `nccn` alone, and precipitation's apparent failure was the chain
stopping too early.

## Extended to 3.125 s: precipitation converges, most fields do not hold an order

Chain extended to N ∈ {3,6,12,24,48,96} → dtcld 100, 50, 25, 12.5, 6.25, 3.125 s.

**Precipitation was pre-asymptotic, and that is all it was.** Successive orders run
−2.244, +0.351, then **+1.399, +1.256** once h ≤ 25 s. Of the six candidates listed
below for its near-zero order, the simplest — "the chain had not reached an
asymptotic regime" — is confirmed by extending it, and the other five need not be
invoked. The earlier +0.028 was measured on a chain that stopped too early.

**Per field, most fields do not hold a stable exponent** (successive differences):

| field | 100→50 | 50→25 | 25→12.5 | 12.5→6.25 |
|---|---|---|---|---|
| `nccn` | +1.018 | +1.043 | +1.023 | **+1.008** |
| `ni` | +1.196 | +0.801 | +0.981 | +1.025 |
| `qv` | +1.000 | +0.894 | +0.602 | +1.039 |
| `th` | +0.997 | +0.828 | +0.601 | +1.032 |
| `qc` | +0.568 | +2.278 | +0.825 | **+0.018** |
| `qi` | +1.867 | +1.847 | +1.738 | **−0.405** |
| `qs` | +1.598 | +2.201 | **−0.293** | +0.019 |
| `nc` | +1.581 | +0.650 | +1.125 | **−1.021** |
| `bg` | +3.915 | +2.962 | +1.551 | **−6.179** |

Only `nccn` is clean across all four halvings. `ni` is close. Everything else either
dips, stalls or goes negative — and a negative order is not a slow rate, it is the
absence of one.

**This corrects a reading of my own.** The grouped `number` series gave +1.018,
+1.043, +1.023, +0.978 and I reported the group as near first order. Those are
`nccn`'s numbers: the group max is set by `nccn` at every level except the last.
`nc` in the same group runs +1.581, +0.650, +1.125, **−1.021**. The group was
reporting one well-behaved field and hiding one that is not.

**The cell setting each group max migrates**, which is owner review §7 measured
rather than argued:

```
th      th/c1k0 -> th/c1k0 -> th/c2k0 -> th/c2k0 -> th/c2k0
mass    qc/c3k3 -> qc/c3k3 -> qc/c3k3 -> qc/c3k2 -> qc/c3k1
number  nccn/c1k2 -> nccn/c1k1 -> nccn/c1k1 -> nccn/c1k1 -> nc/c3k0
```

So a grouped order is partly a record of the max moving. The analyzer now prints
per-field orders and the migration trail alongside the groups.

The fields that lose their order at the fine end — `qc`, `qi`, `qs`, `bg` — are ice
and cloud water in the cold column, which is where discrete thresholds live. That
is consistent with the branch-topology caution below and is not further diagnosed:
no per-member topology record exists.

## The physical column budgets say something different again

Owner review §7: the grouped norms above are max norms over **mixing ratios**, with
no ρΔz weighting and a max cell that migrates. The quantities conservation is
actually about are the column integrals, and both drivers now emit `rho`/`delz` so
they can be formed against the state in the same k convention rather than
re-derived from the fixture by a second path that could drift.

    W_col   = Σ_k ρ_k Δz_k (q_v+q_c+q_r+q_i+q_s+q_g)
    N_x,col = Σ_k ρ_k Δz_k n_x

Successive order, per column:

| quantity | col | 100→50 | 50→25 | 25→12.5 | 12.5→6.25 |
|---|---|---|---|---|---|
| **water** | 1 | +1.969 | +1.002 | +1.000 | **+1.002** |
| **water** | 2 | +1.376 | +0.582 | +2.420 | +0.066 |
| **water** | 3 | −5.860 | +3.884 | −1.017 | +0.407 |
| `nccn` | 1 | +0.638 | +0.956 | +0.981 | **+0.990** |
| `nccn` | 2 | +0.539 | +0.843 | +0.943 | **+0.956** |
| `ni` | 3 | +1.173 | +0.799 | +1.461 | +0.863 |
| `nc` | 3 | +2.345 | +4.989 | +0.802 | **−5.184** |

Reported per column rather than summed, so a budget error in one column is not
diluted by the rest.

**Column water converges cleanly at first order in column 1 and not at all in
column 3.** Column 2 is in between and does not settle. `nccn` approaches first
order from below in both columns that carry it. `nc` in column 3 has no order.

`nr` does not appear: its column budget is bit-identical across every member, which
is the same fact the call-boundary control found from the other side — the
sedimentation interface never touches `nr` on this fixture.

**Column 3 is where everything is ill-behaved** — the mixing-ratio orders for `qc`,
`qi`, `qs` and `bg`, the column water budget, and `nc`. It is the cold column
(242–244 K), it is where the G3.3 seed cell is, and it is where the conservative
call-boundary sensitivity lives. Three separate experiments land on the same three
cells. The common feature is that this is where the phase branches and hydrometeor
thresholds are active, which is precisely the condition under which a classical
order stops being meaningful — and the topology record that would confirm it is
still not built.

## The branch topology DOES move, and it is measured

Owner review §5 warned that a classical order is meaningful only within one smooth
branch. That was carried as a caution. It is now a measurement, and it needed no
kernel instrumentation: the final branch state is recoverable from the emitted
fields, given `pii` — the cold/warm mask from `t = th·pii` against `t0c`, and which
species are present above `qmin`.

Against the coarsest member, every finer member differs — and always the same way:

```
N=  6 (h=50s)   : 3 flips  qg@c3k1, qg@c3k2, qg@c3k3
N= 12 (h=25s)   : 3 flips  qg@c3k1, qg@c3k2, qg@c3k3
N= 24 (h=12.5s) : 3 flips  qg@c3k1, qg@c3k2, qg@c3k3
N= 48 (h=6.25s) : 3 flips  qg@c3k1, qg@c3k2, qg@c3k3
N= 96 (h=3.125s): 2 flips  qg@c3k1, qg@c3k2
```

Graupel in the cold column:

| h (s) | k1 | k2 | k3 |
|---|---|---|---|
| 100 | 2.860e-09 ✓ | 4.229e-09 ✓ | 8.460e-09 ✓ |
| 50 | 0 | 0 | 0 |
| 25 | 0 | 0 | 0 |
| 12.5 | 0 | 0 | 0 |
| 6.25 | 0 | 0 | 0 |
| 3.125 | 0 | 0 | 1.615e-09 ✓ |

**Exactly zero**, not small — a threshold fired and removed the species. So graupel
presence in column 3 switches on at 100 s, off for four members, and on again at
3.125 s. The chain is **not integrating the same set of processes at different
resolutions**.

Three consequences, and they close the column-3 story:

1. **Any order computed across members that straddle this flip is not a rate.**
   That covers every column-3 exponent in this document.
2. It explains why the column-3 water budget has no order: the species set changes.
3. It explains why `qg` shows `n/a` in the per-field table — the norm hits exact
   zeros, which the analyzer already declines to convert into an exponent.

The cold/warm mask itself never flips, and no other species does. The instability is
graupel presence alone, and it is in the same three cells as everything else.

What this does NOT recover is the per-sub-cycle topology — the `mstep` vector, the
cap-active masks, the intermediate branch history. Those are inside the kernel. The
final-state record is one-sided: a difference proves the topology moved, but
agreement would not prove it stayed put, since an intermediate flip can heal before
the end.

## What may and may not be said about convergence

Established: **selected max norms of a synthetic fixture decreased monotonically
along a 100 → 50 → 25 → 12.5 → 6.25 → 3.125 s chain; `nccn` holds p ≈ 1 across every
halving and `ni` is close; precipitation reaches p ≈ 1.3 once h ≤ 25 s.**

Not established: that the reference operator converges at first order. A classical
order is meaningful within one smooth branch, and this kernel has `floor(mstep)`,
min/max caps, hydrometeor thresholds, phase branches, complete-evaporation and
number clamps. If the branch topology changes with `h` the exponent is not an
order at all. None of the following is currently recorded per member, and until it
is, the numbers above are a trend and not a rate:

```
outer-loop count            RECORDED (loops, in the stream)
cold/warm branch mask       RECORDED (final state; stable across the chain)
species presence mask       RECORDED (final state; qg FLIPS -- see above)
sedimentation mstep vector  not recorded, inside the kernel
cap-active mask             not recorded, inside the kernel
complete-evaporation mask   not recorded, inside the kernel
entry-clamp mask            not recorded, inside the kernel
ncmin gate                  not recorded, inside the kernel
surface precipitation onset not recorded, needs per-call increments
```

The two that are recorded are enough to settle the question for column 3: the
topology **does** move there, so its exponents are not rates.

## Precipitation: RESOLVED by extending the chain

The first version reported `precip` flat from 100 s to 50 s and dismissed it as
"an accumulated flux". The second withdrew that dismissal and listed six candidates.
The six-member chain settles it: precipitation reaches **p = +1.399 then +1.256**
once h ≤ 25 s, so it was simply **pre-asymptotic**, the last of the six. Kept here
because the candidate list is what a reader would otherwise have to re-derive:

- precipitation **onset time** moving between steps,
- bottom-outflow cap or threshold firing at different steps,
- `mstep` topology changing,
- the column dominating the max norm changing with resolution,
- the cumulative diagnostic being sensitive to call segmentation,
- **the chain not having reached an asymptotic regime by 12.5 s** — this one.

The 6.25 s and 3.125 s members were the test and they were run. Note that the
segmentation candidate is separately TRUE — the call-boundary control finds
precipitation differing in every arm, including one whose state is bitwise
identical — but it is not what produced the low order here.

## The discarded members are a PARTIAL control

N=1 and N=3 both integrate 300 s in three 100 s steps. F:893–894 computes `cpm`/`xl`
once for N=1, held across three subcycles, and three times for N=3.

| | cells differing | max abs difference |
|---|---|---|
| `th` | 4 / 12 | **2.899e-04 K** |
| mass | 19 / 72 | 1.336e-08 |
| number | 8 / 48 | 5.120e+02 |
| precip | 2 / 9 | 3.522e-03 |

Three confounds are excluded by inspection:

- `qcr` (F:896–902), `den_tmp`/`delz_tmp` (F:909–910) are pure functions of inputs
  the kernel does not modify.
- `rainncv`/`snowncv`/`graupelncv` are zeroed at entry (F:917–919), which is why
  this reads the **cumulative** `rain`/`snow`/`graupel` (F:1467, 1473, 1482).
- `tstepsnow`/`tstepgraup` are zeroed at entry but feed only `sr`, which is not read.

**Two are not excluded, so this is not yet a coefficient-only contrast.**

1. **Entry normalisation runs three times instead of once.** Whatever clamping
   `kdm62D` applies at entry — negative-water padding, `ni` bounds, `nccn` banding —
   N=3 applies at 100 s and 200 s as well. Unless the intermediate state is measured
   to be strictly interior to every clamp, part of the difference is re-clamping.
2. **Call-local state may reset.** The four external auxiliaries are controlled
   below, but that is not evidence they are the complete set of state that persists
   between a call's outer loops and is reinitialised on re-entry.

Formally, the contrast is clean only if, for hidden state `Z`,
`Φ₁₀₀³(X₀,Z₀)` equals `Φ₁₀₀(Φ₁₀₀(Φ₁₀₀(X₀,Z₀)))` up to the coefficient policy. `X`
is carried; the universe of `Z` is not sealed.

So the supported statement is:

> **A sensitivity to Fortran call segmentation was observed over a synthetic 300 s
> microphysics-only integration. Coefficient refresh frequency is a demonstrated
> and plausibly dominant component of it. It is not proven to be the whole of it.**

### The control that would close it

The C++ port already refreshes `cpm`/`xl` every subcycle, so at N=1 (one call,
three internal refreshes) and N=3 (three calls, one each) the **refresh count is
identical**. Therefore `X^{C++}_{N=1}` vs `X^{C++}_{N=3}` isolates call-boundary
artifacts with the coefficient policy held constant. Bitwise equality would make
the Fortran N=1/N=3 difference attributable to the policy; a difference would show
that external segmentation is its own operator change. This needs only a harness
driver, no production change. **Not yet run.**

## Scale, stated precisely

The single-store difference at the G3.3 seed cell is 1 ULP = 1.526e-05 K. The
2.899e-04 K above is the **domain max over 12 `th` cells**, not necessarily the same
cell. The ratio ~19 therefore compares two different locations and should not be
quoted as an amplification factor at a point. Same-seed-cell delta, domain max and
a domain percentile should be recorded separately; only the domain max exists now.

This is a **300 s microphysics-only direct-kernel integration**, not a forecast: no
dynamics coupling, no full cloud-system lifetime. The first version called it
"forecast-length", which it is not.

## Control that does hold: the auxiliaries carry no intent in, across calls too

Re-zeroing `rhoxk`, `cmgk`, `n0so2d`, `n0go2d` before every call versus letting the
kernel's writes survive gives **bit-identical output at every N**, so the sentinel
matrix's finding extends from within one call to a multi-call sequence. This does
not establish that these four are the only call-local state — see confound 2.

## Reproducibility

Each sweep now emits `delt`, `loops` and `dtcld` as the kernel computed them, so
the design rule is checkable from the stream rather than re-derived. An experiment
manifest (`refinement_experiment_v1`) records repo commit, tree cleanliness, module
and fixture digests, compiler, per-member output digests and the analyzer digest.
Its `artifact_type` is `refinement_experiment` and `decision_eligible` is a constant
`False` with no argument that sets it.

## Corrections to the first version

1. Convergence orders computed from the error-to-finest series — **withdrawn**;
   they measured the estimator's bias.
2. "Reference operator converges at first order or better" — **downgraded** to
   monotone decrease of selected max norms, plus p ≈ 1 for `th`/`number` by
   successive differences.
3. "Past the code's own 120 s limit" — **wrong**; `nint` makes 120 s a target, and
   `dtcld` reaches ~175 s at `delt = 175`.
4. "Coefficient-only controlled contrast" — **downgraded**; entry re-clamping and
   call-local state resets are not excluded.
5. "Forecast-length interval" — **wrong**; 300 s, microphysics only.
6. The 19× ratio — now labelled as domain-max against seed-cell, not a point
   amplification.
7. Precipitation dismissed as "an accumulated flux" — **withdrawn** as an
   explanation; candidates listed instead.

## Still not established

- The C++ leg has not been run, in either the refinement chain or the N=1/N=3
  control.
- Neither counterfactual operator exists. Reference-faithful C++ (kernel-call-fixed
  coefficients) and thermodynamically-consistent (`dL_f/dT = c_l − c_i`, §3.1) both
  need changes inside frozen C++ — a scoped freeze-lift, not self-authorized.
- Convergence order is not a physics verdict. §3.1 stands: the code's
  `dxlf/dT = c_l − c_pv = 2343.6` against a consistent `c_l − c_i = 2084` is a 12.5%
  discrepancy, so a policy can evaluate the coded formula more faithfully while
  tracking thermodynamics less well. The §8 ledgers are the other half.
- `mass` and `number` here are max norms over mixing ratios, **not** physical
  column budgets. No `ρΔz` weighting, and the field setting the max may change with
  resolution. Column water `Σ ρ_k Δz_k (q_v+q_c+q_r+q_i+q_s+q_g)` and column number
  `Σ ρ_k Δz_k n_r` are the physical norms and are not computed.
- The fixture is arithmetic-synthetic; these magnitudes are properties of it.

Attribution and policy selection remain owner adjudication.
