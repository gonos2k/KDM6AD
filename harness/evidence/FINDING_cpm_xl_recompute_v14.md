# The port recomputes `cpm` and `xl`; the reference deliberately does not

Protocol v14. The 1-ULP `t` traces to a **semantic divergence in production code**,
not to rounding: the C++ recomputes the latent-heat and heat-capacity
coefficients every outer loop from the evolved state, while the pinned Fortran
computes them once per kernel call and says in its own comment that this is
intentional.

## The reference

```fortran
!  latent heat for phase changes and heat capacity. neglect the
!  changes during microphysical process calculation
!  emanuel(1994)
   do k = kts,kte_in
     do i = its,ite
       cpm(i,k) = cpmcal(q(i,k))      ! F:893
       xl(i,k) = xlcal(t(i,k))        ! F:894
     enddo
   enddo
```

F:893–894 sit **before** `do loop = 1,loops` (F:934), and no outer loop encloses
them. `cpm` and `xl` are therefore fixed for the whole kernel call — the comment
states the approximation explicitly.

## The port

`preamble()` computes them from the state it is given:

```cpp
auto cpm = thermo::compute_cpm(state.qv, params.thermo);   // coordinator.cpp:416
auto xl  = thermo::compute_xl(state.t,  params.thermo);    // coordinator.cpp:417
```

and `runtime.cpp:625` calls `preamble(cur_pyc, …)` **inside** the sub-cycle loop,
with the current state. So they are recomputed every outer loop.

## The measurement (`micro_freeze_heat`, loop 2)

`cpm` as each backend actually used it:

| | distinct values across the 12 cells |
|---|---|
| Fortran | **3** — one per column, constant in k |
| C++ | **12** — one per cell |

The three Fortran values (1005.34186, 1005.35870, 1005.37555) order exactly with
the **kernel-entry** `qv` (1.000e-3, 1.020e-3, 1.040e-3, each k-constant per
column on this fixture). The twelve C++ values track the loop-2 `qv`, which has
evolved away from entry — most in column 3, where `qv` has fallen to 3.2–4.2e-4.

At the seed cell (loop 2, column 3, k 0):

| field | Fortran | C++ | |
|---|---|---|---|
| `t_pre_freeze` | 0x43739698 | 0x43739698 | identical |
| `pinuc` (f64) | 1.64092947e-09 | 1.64092947e-09 | **identical** |
| `pfrzdtc` (f64) | 1.84655769e-06 | 1.84655769e-06 | **identical** |
| `pfrzdtr` (f64) | 3.32974268e-08 | 3.32974268e-08 | **identical** |
| `xlf` | 276997.0 | 280719.0 | **+1.3%** |
| `cpm` | 1005.37555 | 1004.85382 | **−0.05%** |

**All three freeze rates are bit-identical at f64.** The difference is entirely in
the coefficient `c = xlf/cpm`: 275.52 against 279.36, **1.4%**.

That accounts for the observed `t` difference quantitatively:

    Δc · pfrzdtc ≈ 3.84 × 1.847e-6 ≈ 7.1e-6
    ULP(t) at 243.6 K            = 1.526e-5
    ⇒ ≈ 0.46 ULP  →  1 ULP in the stored t

## Why this is not a harness artifact

The per-leg freeze replay

    c  = f32(xlf/cpm);  t2 = f32(t_pre + c·pinuc);  t3 = f32(t2 + c·pfrzdtc)
    t4 = f32(t3 + c·pfrzdtr)   ==   micro_post_freeze.t

reproduces **0/12 misses on all four legs, all three loops**. So the `cpm` and
`xlf` recorded here are exactly the values each backend multiplied — the capture
is not reading a different quantity from the one in use. This is the check the
emission point needed, since it has no reconciled substep dump.

## Scope and caveats

- **Variant-independent.** Both Fortran legs agree and both C++ legs agree, so
  this is a legacy-shared port-fidelity difference and has nothing to do with the
  conservative interface.
- **The 1-ULP is fixture-specific; the 1.4% is not.** The coefficient error is
  proportional to how far the state has evolved from entry. Here it lands on a
  cell whose freeze rates are ~1e-6, so it shows as 1 ULP. With larger rates the
  same coefficient error scales directly into the temperature tendency. Whether
  that is meteorologically material is a question for a real case, not this
  synthetic fixture.
- **Which behaviour is correct is not the harness's call.** The reference states
  its approximation deliberately (Emanuel 1994); the port's recomputation is
  arguably more accurate physics and is certainly different. Changing either is
  owner adjudication and both are frozen.

## A comparator gap this exposed

The gate's first divergence is reported at loop 1, column 1, `xlf` — a **warm**
cell (289 K) where Fortran applies the `xlf = xlf0` override at F:1517 and the
C++ does not. All three freeze rates are zero there, so that coefficient is
multiplied by zero and is not causal. The comparator has no branch-activity
filter for this stage, so it named a value the arithmetic did not use — the same
class of defect owner review §3 raised for `micro_qr_operands`.

Measured: of the differing cells, loop 1 has **0** with a nonzero freeze rate,
loops 2 and 3 have **4 each**, all in column 3. The causally meaningful first
divergence is loop 2, column 3.

## Also retracted here

The v14 design was motivated by a precision hypothesis — the C++ comment calls
D4's rate an "f32 rate" where the reference declares all three
`double precision`. That is a real documentation defect, but it **cannot** be the
mechanism: `t += c·rate` rounds to f32 on every store, so the width of `c·rate`
can only change the result when `step ≳ t`, i.e. `rate ≳ 0.73 kg/kg` against the
~1e-8 rates here. A search over 400 000 values found zero discriminating cases;
at 1.5 kg/kg they do differ, confirming the comparison works.
`test_the_rate_precision_CANNOT_move_t_at_physical_magnitudes` pins it.

The gate returns `INCONCLUSIVE`. Attribution is owner adjudication.
