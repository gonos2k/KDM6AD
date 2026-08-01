# The §9 sweep does not refine, and the discarded members are the controlled experiment

Owner review §9 asks for 300 s reached as 1×300, 2×150, 3×100, 6×50, 12×25, at the
`kdm62D` boundary, to see which thermodynamic-coefficient policy converges. Running
it produces a sequence whose error to the finest member goes **up** before it goes
down, which reads as an operator that does not converge.

It is not. The sweep does not refine.

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
| 2 | 150 | 1 | **150** | coarser than N=1, and past the kernel's own 120 s criterion |
| 3 | 100 | 1 | **100** | duplicate of N=1 |
| 6 | 50 | 1 | 50 | |
| 12 | 25 | 1 | 25 | |

`nint(150/120) = nint(1.25) = 1`, and because `delt > dtcldcr` the guard at F:932
does not apply, so N=2 integrates in one 150 s step — the coarsest member of a
sweep meant to be the second-finest.

Measured on it, the error to the finest is non-monotone (`th`: 4.48e-02 at N=1,
**7.46e-02** at N=2, 4.48e-02 at N=3, 1.50e-02 at N=6). N=1 and N=3 give the same
number to six figures because at the internal level they are nearly the same
integration.

**Corrected chain: N ∈ {3, 6, 12, 24}** → dtcld = 100, 50, 25, 12.5. A clean
halving.

## The reference operator converges on the corrected chain

`legacy`, fixture `arithmetic_multisubcycle_v1`, max-norm over cells:

| | h=100 | h=50 | h=25 | p(100→50) | p(50→25) |
|---|---|---|---|---|---|
| `th` | 5.228e-02 | 2.243e-02 | 8.423e-03 | +1.221 | +1.413 |
| mass | 5.112e-05 | 2.294e-05 | 3.921e-06 | +1.156 | +2.548 |
| number | 6.436e+06 | 2.791e+06 | 9.121e+05 | +1.205 | +1.614 |
| precip | 3.175e-02 | 3.114e-02 | 1.637e-02 | **+0.028** | +0.928 |

(error to the finest member, N=24)

Monotone in every group. Temperature, mass and number sit near or above first
order. **Precipitation does not**: it is essentially flat from 100 s to 50 s
(p = +0.028) and its successive differences are non-monotone (p = −2.244). Surface
precipitation is an accumulated flux through the bottom interface rather than a
state variable, so it is not obliged to inherit the state's rate — but it is the
quantity a forecast is scored on, and on this fixture it is the slowest to settle.
Not diagnosed here.

Max-norm, not RMS: the fixture is arithmetic-synthetic and most cells are quiet, so
an RMS over 144 cells would mostly measure how many cells are quiet.

## The discarded members are a controlled contrast of the coefficient policy

N=1 and N=3 both integrate 300 s in three 100 s steps. They differ in one thing:
N=1 makes one kernel call, so F:893–894 computes `cpm`/`xl` **once** and holds them
across three subcycles; N=3 makes three calls, so they are computed **three times**.

Everything else the kernel recomputes at entry was checked and cannot contribute:

- `qcr` (F:896–902), `den_tmp`/`delz_tmp` (F:909–910) are pure functions of inputs
  the kernel does not modify, so they are identical on every call.
- `rainncv`/`snowncv`/`graupelncv` are zeroed at entry (F:917–919) — which is why
  this experiment reads the **cumulative** `rain`/`snow`/`graupel` (F:1467, 1473,
  1482), which are not. An earlier version of the driver read `ncv` and so compared
  300 s of precipitation at N=1 against 100 s of it at N=3, reporting a difference
  in call structure as a difference in the operator.
- `tstepsnow`/`tstepgraup` are zeroed at entry but feed only `sr` (F:1486–1488),
  which is not read.

With those excluded, the coefficient refresh count is the only mechanism left:

| | cells differing | max abs difference |
|---|---|---|
| `th` | 4 / 12 | **2.899e-04 K** |
| mass | 19 / 72 | 1.336e-08 |
| number | 8 / 48 | 5.120e+02 |
| precip | 2 / 9 | 3.522e-03 |

For scale, the single-store difference at the G3.3 seed cell is 1 ULP =
1.526e-05 K. Over 300 s the refresh policy moves temperature by **2.899e-04 K**,
about 19× that — on the reference operator alone, with no modified build.

This does not say which policy is better. Both arms here are the reference's own
"hold within a call" rule; what varies is how often a call boundary occurs. It
measures the **sensitivity of the answer to refresh frequency**, which is the
quantity the policy question is about, and it establishes that the effect does not
stay at the 1-ULP scale once the operator is run over a forecast-length interval.

## Control: the auxiliaries carry no intent in, across calls too

The four `kdm62D` auxiliaries (`rhoxk`, `cmgk`, `n0so2d`, `n0go2d`) were shown by
the sentinel matrix to carry no intent in. That was established within one call.
Re-zeroing them before every call versus letting whatever the kernel wrote survive
gives **bit-identical output at every N in the sweep** (1, 2, 3, 6, 12), so the
finding extends to a multi-call sequence. The refinement result depends on this: if
they carried state, the sweep members would differ by how many times that state was
reset.

## What is NOT established

- **The C++ leg has not been run.** The comparison §9 is for — reference frozen
  against port dynamic — needs it, and needs the same dtcld-based sweep design.
- **Neither counterfactual operator exists.** The reference-faithful C++ variant
  (kernel-call-fixed coefficients) and the thermodynamically-consistent variant
  (`dL_f/dT = c_l − c_i`, §3.1) both require changes inside frozen C++. That needs a
  scoped freeze-lift and is not self-authorized.
- **Convergence order is not a physics verdict.** §3.1's point stands: the code's
  `dxlf/dT = c_l − c_pv = 2343.6` against a consistent `c_l − c_i = 2084` is a 12.5%
  discrepancy, so a policy can evaluate the coded formula more faithfully while
  tracking the thermodynamics less well. The moist-energy ledger of §8 is the other
  half and has not been built.
- **This fixture is arithmetic-synthetic.** The magnitudes above are properties of
  it, not of a forecast.

Attribution and policy selection remain owner adjudication.
