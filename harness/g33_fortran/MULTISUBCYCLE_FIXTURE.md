# Why the current fixture cannot reach multi-subcycle, and what would

Status: **built and committed.** `harness/g33_fixture_multisubcycle_v1.json` plus
`harness/tests/data/g33_multisubcycle_legacy_sample.g33f` (3 outer loops, mstep
heterogeneous across both columns and loops). This page records the measurement the
design came from, and the switch-margin limit that is still open.

## The substep count is set by one relation

From `module_mp_kdm6.F` (F:1126-1128), per column, maximised over levels:

```
numdt = max( nint( max(work1_qr, workn_qr, work1_qs, work1_qg) * dtcld + 0.5 ), 1 )
mstep = max over k of numdt
```

`work1 = vt / delz` (fall speed over layer thickness). So

For `x >= 0`, `nint(x + 0.5)` is exactly `floor(x + 1)` — ties round away from zero,
so the two agree at every point (verified over `x` in [0, 4] at 1e-3 spacing), and
the C++ path computes `floor(vmax*dtcld + 1.0)` directly. Therefore

```
mstep >= m   <=>   work1 * dtcld >= m - 1
mstep >= 2   <=>   work1 * dtcld >= 1.0        (NOT 1.5)
```

An earlier revision of this page used `>= 1.5` and the timestep/geometry table below
was computed from it; both are corrected here.

## What the current fixture actually contains

Measured from the committed evidence (`g33_legacy_sample.g33f`), not assumed:

| quantity | value |
|---|---|
| layer thickness `delz` | **~8,550 m** |
| peak `work1 = vt/delz` | **1.143e-4 s^-1** |
| implied fall speed `vt` | ~0.98 m/s |
| per-column peak `work1` | 1.143e-4, 1.103e-4, 0.940e-4 (spread only ~1.2x) |

Therefore `mstep >= 2` would need

```
dtcld >= 1.0 / 1.143e-4 = 8,749 s
```

**No timestep change can reach multi-subcycle in this fixture** — dt=300 gives
`loops = ceil(300/120) = 3` and hence `dtcld = 100 s`, two orders of magnitude short.
A dt sweep is not the missing piece; the fixture's geometry is.

## Why raising qr does not work either

`vt ~ qr^0.2`, so lifting `work1` by the required ~130x needs qr about `130^5 ~ 1e10`
times larger — far outside any physical state, and it would collide with the
domain validation the parser already enforces.

## The reachable lever is layer thickness

Holding the fixture's fall speed (~0.98 m/s) and thinning the layers:

| `delz` | `work1` | `mstep >= 2` needs `dtcld >=` | `x` at `dtcld=100 s` | mstep |
|---|---|---|---|---|
| 8,550 m (original) | 1.14e-4 | 8,749 s | 0.011 | 1 |
| 500 m | 1.96e-3 | 511 s | 0.196 | 1 |
| 200 m | 4.9e-3 | 204 s | 0.49 | 1 |
| 100 m | 9.8e-3 | 102 s | 0.98 | 1 |
| **65 m** | **1.51e-2** | **66 s** | **1.51** | **2** |
| **50 m** | **1.96e-2** | **51 s** | **1.96** | **2** |

So a fixture that exercises BOTH the historical multi-outer-loop path (dt=300 ->
loops=3) and multi-substep transport wants `delz` at or below roughly **100 m** —
the 98 m point is where `x` reaches 1.0 at `dtcld = 100 s`. The built fixture uses
150 / 65 / 32 m per column.

## The switch margin cannot be computed from current evidence (OPEN)

A mechanism fixture must not sit near an `mstep` switch: if

```
x = max_k(work) * dtcld        m = floor(x + 1)
delta = min( x - (m-1),  m - x )
```

is small, a sub-ULP fall-speed difference between the backends flips the substep
count, and the comparison is then about scheduling rather than about arithmetic.

Measured on the committed 3-loop evidence, using the operands the dump actually
carries (`work1_qr`, `workn_qr`):

| cell | x | observed mstep | floor(x+1) | delta (lower bound) |
|---|---|---|---|---|
| L1 col1 | 0.610 | 1 | 1 | 0.390 |
| L1 col2 | 1.374 | **5** | 2 | — |
| L1 col3 | 2.410 | **9** | 3 | — |
| L2 col1 | 0.606 | 1 | 1 | 0.394 |
| L2 col2 | 1.329 | 2 | 2 | 0.329 |
| L2 col3 | 5.807 | **10** | 6 | — |
| L3 col1 | 0.285 | 1 | 1 | 0.285 |
| L3 col2 | 0.625 | 1 | 1 | 0.375 |
| L3 col3 | 3.581 | **7** | 4 | — |

In four of the nine cells the observed `mstep` is LARGER than the instrumented
species predict. That is not an inconsistency — `numdt` maximises over
`work1_qr, workn_qr, work1_qs, work1_qg`, and the last two are **not dumped**. So:

- `floor(x+1) <= mstep` is a genuine invariant (more species can only raise `x`),
  and it holds in all nine cells; the harness asserts it.
- the true `delta` is **not computable from the current evidence** in those cells,
  because the operand that sets `mstep` there is missing from the protocol.

Closing it requires adding `work1_qs` / `work1_qg` to `substep_pre`. Until then the
margin claim for this fixture is limited to the five cells where the instrumented
species dominate, where `delta` is 0.29-0.39 — comfortably clear of a switch.

## Heterogeneous mstep needs per-column geometry

At a uniform `delz = 50 m` with `dtcld = 100 s` the three columns give
`work1*dtcld` = 1.95 / 1.88 / 1.61, i.e. `mstep` = 2 / 2 / 2 — homogeneous. The
existing 8x spread in qr only produces a 1.2x spread in `work1`, because
`vt ~ qr^0.2` compresses it (`8^0.2 = 1.5`).

Heterogeneous `mstep` — which is what the active-stream comparator, the gate law and
the Fortran-active-only vs C++-all-lanes topology all exist to handle — therefore
needs **per-column `delz`**, e.g. 200 / 100 / 50 m giving a 4x `work1` spread and
`mstep` of about 1 / 2 / 3.

## Consequences for the fixture build

`arithmetic_multisubcycle_v1` is a NEW field set, not a parameter tweak, so it needs:

1. a second authority JSON alongside `harness/g33_fixture_v1.json`;
2. `g33_fixture_v1.py` parameterised — `MANIFEST`, `CPP_OUT`, `FORTRAN_OUT` are
   module constants today, so the generator renders exactly one fixture;
3. a second generated C++ header plus a case name in `abc_driver.cpp`
   (`make_shared_fixture()` is hard-wired to `g33_fixture_v1`);
4. the same in the Fortran driver;
5. re-checking the domain validation the parser enforces (finite, `rho`/`p`/`delz`
   positive, pressure strictly increasing downward) for the new geometry — thinner
   layers change the hydrostatic column, so `p`, `rho` and `phb` must be rebuilt
   consistently rather than edited field by field.

---

# The sealed-contract problem for the C++ leg (OPEN)

The Fortran leg derives its expected universe FROM the observed mstep, so it needed
no prior declaration. The C++ leg is the opposite by design: its expectation
manifest is sealed BEFORE the run, which is what makes it independent evidence.

For a multi-sub-cycle fixture that creates a genuine ordering problem:

```
the sealed schedule must declare   loops and mstepmax_main[loop]
but the per-loop mstepmax is knowable only BY running
```

`abc._schedule()` now takes `loops` / `mstepmax_main` / `mstepmax_ice` / `dtcld`
instead of hardcoding 1, so the machinery is ready. What remains is WHERE the
declared value comes from.

## Do not take it from the other leg

The Fortran run of this fixture reports `loops = 3`, `mstepmax_main = [9, 10, 7]`.
Sealing the C++ contract with those numbers would COUPLE the two legs: if the two
backends ever computed a different mstep — a CFL / fall-speed difference upstream of
sedimentation, which the comparator classifies as INCONCLUSIVE and is exactly the
sort of thing G3.3-M exists to surface — the C++ contract would have been built from
the Fortran answer and the disagreement would be masked rather than reported.

## Options

1. **Declare it in the fixture authority** (preferred). Add `loops` and
   `mstepmax_*` to `g33_fixture_multisubcycle_v1.json` as reviewed, committed
   metadata, obtained once from a discovery run whose output is NOT evidence. Both
   legs must then satisfy the declaration, and either one disagreeing is a finding.
   Cost: the manifest SHA changes, and the fixture validator must accept the fields.
2. **A C++ discovery mode** that emits only `substep_pre` without a sealed container
   set, used solely to obtain the numbers for option 1. More machinery, same result.
3. Take the numbers from the Fortran leg. **Rejected** for the reason above.

Until this is settled the C++ multi-sub-cycle bundle cannot be produced, so the
four-case gate at dt=300 runs Fortran-only. The one-loop four-leg path is unaffected
and still returns INCONCLUSIVE / exit 2 / attested.
