# Column 3 does have a valid convergence domain — in the ice chain, which refines two levels earlier

Owner §5, and a correction to this branch's own reasoning twice over.

The kernel runs **two independent sedimentation sub-cycles with separate
sub-step counts** (`module_mp_kdm6.F:1179-1180`):

```
numdt(i)   = max(nint(max(work1(qr), workn(nr), work1(qs), work1(qg))*dtcld+.5),1)   -> mstep
numdt_i(i) = max(nint(max(work1(qi), workn(ni))              *dtcld+.5),1)           -> mstep_i
```

So **`mstep` governs qr, nr, qs, qg** (F:1189-1276) and **`mstep_i` governs
qi, ni** (F:1281-1340). Everything this branch measured as "`mstep`" was the
first of the two.

## They bottom out two levels apart

`mstep_i` was a kernel local nothing emitted. Reached through a new anchored
overlay site (below); measured against the rain chain:

| h (s) | `mstep_i` c1/c2/c3 | `mstep` c1/c2/c3 |
|---|---|---|
| 100 | 1 / 2 / 4 | 1 / 5 / 10 |
| 50 | 1 / 1 / 2 | 1 / 3 / 5 |
| **25** | 1 / 1 / **1** | 1 / 2 / 3 |
| 12.5 | 1 / 1 / 1 | 1 / 1 / 2 |
| **6.25** | 1 / 1 / 1 | 1 / 1 / **1** |

In column 3 the ice chain reaches `mstep_i ≡ 1` at **h = 25 s**; the main chain
needs **h = 6.25 s**.

## Which is why the ice number converges and column water does not

`FINDING_refinement_noise_floor_v1` recorded column 3's converging ice number as
a "positive result" with no explanation. This is the explanation, and it makes
the domain **per-chain, not per-column**.

`ni` column number in column 3 — successive differences fall monotonically
across the whole chain (1.76e8, 7.79e7, 4.48e7, 1.63e7, 8.94e6, 4.11e6, 2.02e6,
9.72e5), so **`ni` never reaches the noise floor** that stops `th` and `mass` at
h = 3.125 s. Its relative signal stays near 1e-2, far above f32 roundoff, where
`th`'s falls to ~5e-6.

Inside the `mstep_i ≡ 1` window that leaves **five clean successive orders**:

| order | 25→12.5 | 12.5→6.25 | 6.25→3.125 | 3.125→1.56 | 1.56→0.78 |
|---|---|---|---|---|---|
| `ni` col 3 | +1.461 | +0.863 | +1.121 | +1.029 | +1.052 |

First order, tightening to `+1.029 / +1.052` at the fine end. **This is the first
valid convergence domain established for column 3.**

Column *water* gets none, and now for a stated reason rather than an unexplained
one: it contains qr, qs and qg, so it inherits the **main** chain's requirement
(h ≤ 6.25) and meets the noise floor (h ≥ 3.125) two levels too late.

## The surface number flux is now emitted

`falln` is a kernel local (F:719), so no driver can see it — the earlier claim
that emitting it was "a driver change" was wrong and is corrected in
`FINDING_number_budget_v1`. It is reached at the surface accumulation anchor:

```
bottom_falln_nr = falln(i,kts,1)      nflux_den   = den(i,kts)
bottom_falln_ni = falln(i,kts,2)      nflux_delz  = delz(i,kts)
                                      nflux_dtcld = dtcld
```

Operands, not a product. `nrs(i,k,1) = nr(i,k,j)` (F:388) makes `nrs` the
prognostic number **mixing** ratio, so `falln` is [# kg⁻¹ s⁻¹] and the per-area
flux is `falln·den·delz·dtcld` [# m⁻²] — reasoning that belongs in the analysis,
not buried in a Fortran expression.

**Validated at the same site.** `bottom_fall_qr` is emitted at the same instant,
so `fall/(falln·den)` is the mean rain-drop mass with no channel mixing:

| column | 1 | 2 | 3 |
|---|---|---|---|
| mean drop mass (kg) | 8.51e-10 | 8.56e-10 | 5.39e-10 |
| implied diameter (mm) | 0.118 | 0.118 | 0.101 |

Drizzle-sized and consistent across columns, matching a fixture that precipitates
0.0005–0.035 mm in 300 s.

### What it measures

At h = 25 s, surface flux against the column number change:

| species | col | ΔN (# m⁻²) | surface flux | flux/\|ΔN\| |
|---|---|---|---|---|
| nr | 1 | −3.88e7 | 5.62e5 | **0.014** |
| nr | 2 | −9.27e6 | 3.04e5 | **0.033** |
| nr | 3 | −1.99e6 | 1.16e5 | **0.058** |
| ni | 2 | −3.71e6 | 5.12e6 | 1.380 |
| ni | 3 | +9.42e7 | 3.26e8 | 3.460 |

**Every column loses all of its rain number, and the surface accounts for 1.4–5.8%
of it.** 94–99% goes to microphysical sinks. That is directly relevant to the
`nr` number-moment release blocker: a transport-side number defect on this
fixture would sit under a sink term one to two orders of magnitude larger.

## How the site stays out of the decision path

The four-case protocol's record universe is a v14 contract with the C++ mirror,
and its Fortran parser **raises on any unrecognised `G33F` line**. Two wrong fixes
were checked and rejected:

- `G33F MSTEP <loop> ice <col>` **parses** — which is the trap. `run.mstep` is
  keyed `(loop, chain, col)`, and `g33_fortran_semantics.verify_semantics`
  iterates every `(loop, chain)` scope while looking up `substep_pre` with **no
  chain**, so an ice scope compares ice counts against the main chain's records
  and raises.
- A new record name under the existing macro fails the unknown-line check.

So both emissions sit under their own `KDM6_G33_NUMBER_DUMP`, enabled by
`refine_build.sh --nflux` and **never defined by `fortran_build.sh`**. Verified:

| check | result |
|---|---|
| decision-path (`--dump`) stream vs before this change | **bit-identical** |
| instrumented run vs plain build, G33R records, N = 3/12/48 | **bit-identical** |

`test_g33_number_flux_site.py` holds the separation, including a test asserting
the decision parser *would* reject these records — the reason, kept mechanical.

## Limits

- **Still not a number closure.** `ΔN + F_surface = R_N` defines `R_N`; it does
  not check it. The microphysical number tendencies are per-cell locals inside
  the rate blocks and are not emitted. The 1.4–5.8% above says the sink is large,
  not what it is — `threshold cleanup`, which zeroes sub-threshold mass **and
  paired number**, is the obvious candidate and is untested here.
- The ice-chain domain is established for **`ni` column number on this fixture**.
  `qi` was not checked the same way, and neither channel was checked under the
  conservative interface.
- Synthetic fixture, legacy algorithm, 300 s. No C4 verdict.
