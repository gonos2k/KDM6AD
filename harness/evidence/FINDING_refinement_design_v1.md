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

`th` and `number` sit near p = 1 by the valid estimator. `mass` and `precip` do
not, and the precipitation successive differences are not even monotone.

## What may and may not be said about convergence

Established: **selected max norms of a synthetic fixture decreased monotonically
along a 100 → 50 → 25 → 12.5 s chain, and `th` and `number` show p ≈ 1 by
successive differences.**

Not established: that the reference operator converges at first order. A classical
order is meaningful within one smooth branch, and this kernel has `floor(mstep)`,
min/max caps, hydrometeor thresholds, phase branches, complete-evaporation and
number clamps. If the branch topology changes with `h` the exponent is not an
order at all. None of the following is currently recorded per member, and until it
is, the numbers above are a trend and not a rate:

```
outer-loop count            cold/warm branch mask
sedimentation mstep vector  complete-evaporation mask
cap-active mask             entry-clamp mask
ncmin gate                  surface precipitation onset
```

## Precipitation is not explained by "it is a flux"

`precip` is essentially flat from 100 s to 50 s and its successive differences are
non-monotone. A smooth flux integrated with a consistent quadrature would normally
inherit something close to the state's order, so the first version's "it is an
accumulated flux, so it need not" is not an explanation. Live candidates:

- precipitation **onset time** moving between steps,
- bottom-outflow cap or threshold firing at different steps,
- `mstep` topology changing,
- the column dominating the max norm changing with resolution,
- the cumulative diagnostic being sensitive to call segmentation,
- the chain not having reached an asymptotic regime by 12.5 s.

Distinguishing them needs per-species per-column cumulative precipitation, the
increment at each call, the first nonzero time, and members at 6.25 s and 3.125 s.
Not done.

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
