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

## The switch margin — measured, all cells (CLOSED)

A mechanism fixture must not sit near an `mstep` switch: if

```
x = max_k(work) * dtcld        m = floor(x + 1)
delta = min( x - (m-1),  m - x )
```

is small, a sub-ULP fall-speed difference between the backends flips the substep
count and the comparison becomes one about scheduling rather than arithmetic.

`delta` was previously uncomputable in four of nine cells: `numdt` maximises over
`work1_qr, workn_qr, work1_qs, work1_qg`, and the sealed evidence carries only the
first two, so in those cells the operand that SET `mstep` was absent entirely. The
schedule probe carries all four, which closes it.

Measured with `run_cpp_probe.py --fixture-id arithmetic_multisubcycle_v1`
(identical for both algorithms):

| cell | mstep | delta | | cell | mstep | delta |
|---|---|---|---|---|---|---|
| L1 col1 | 1 | 0.3904 | | L2 col3 | 10 | 0.2613 |
| L1 col2 | 5 | 0.2066 | | L3 col1 | 1 | 0.2847 |
| L1 col3 | 9 | 0.2606 | | L3 col2 | 1 | 0.3755 |
| L2 col1 | 1 | 0.3942 | | L3 col3 | 7 | 0.4388 |
| L2 col2 | 2 | 0.3290 | | | | |

The minimum is **0.2066** — every cell is a comfortable distance from a switch, so
the fixture is usable as a mechanism fixture. `floor(x+1) <= mstep` remains a
standing invariant on the sealed evidence (more species can only raise `x`), and the
harness asserts it there.

Independently, the Fortran leg observed the same `mstep` vectors column by column
(`[1,5,9] [1,2,10] [1,1,7]`). That agreement is an OBSERVATION, not an input: the
C++ contract is sealed from C++ operands alone, so a future backend disagreement
would surface at the comparator rather than being absorbed into the contract.

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

# The sealed-contract problem for the C++ leg — RESOLVED

The Fortran leg derives its expected universe FROM the observed mstep, so it needed
no prior declaration. The C++ leg is the opposite by design: its expectation manifest
is sealed BEFORE the run, which is what makes it independent evidence. For a
multi-sub-cycle fixture that is circular:

```
the sealed schedule must declare   loops and mstepmax_main[loop]
but the per-loop mstepmax is knowable only BY running
```

## What was rejected, and why

**Take the numbers from the Fortran leg.** Rejected. If the backends ever computed a
different mstep — an upstream CFL / fall-speed difference, precisely what G3.3-M
exists to surface — the C++ contract would have been built from the Fortran answer
and the disagreement masked rather than reported.

**Let the sealed run discover its own containers.** Impossible: the sink refuses any
container id with no pre-sealed op-seq entry and descriptor.

**Over-declare the sealed contract to the mstep ceiling and write fewer containers.**
Disproved by experiment. `op_seq_id` is a process-global counter and each descriptor
line pins it, so loop 2's descriptor expects ids after loop 1's DECLARED substeps
while the run has advanced only by its ACTUAL ones. On the real driver:

```
expected: 21806|surface|-|-1|-|-|bottom_fall_qr|f32|3
actual:    1968|surface|-|-1|-|-|bottom_fall_qr|f32|3
```

The shortfall is survivable only at the very end of the stream, which is exactly not
the multi-loop case.

## What resolves it: a separate probe channel

`sched_emit` (overlay, gated by `KDM6_G33_SCHED_PROBE`) writes a `KDM6SCHED` stdout
stream and touches no container, descriptor or op-seq machinery. It carries all four
fall speeds `numdt` maximises over — `work1_qs` / `work1_qg` included, which the
sealed evidence omits.

```
pass 1  run_cpp_probe.py   ->  probe.sched, schedule.json, switch_margin.json
        Python RE-DERIVES the mstep vector from the raw fall speeds and requires
        the run's own mstep_native to match. The producer is not trusted.
pass 2  seal that schedule, run for real, and require assert_reproduced():
        the evidence run's mstep vectors must equal the probe's exactly.
```

The probe is not evidence and cannot become it: no run identity, no binary binding,
no descriptors, a case id marked with the probe marker, and `assert_not_evidence()`
at the decision boundary.

Measured for `arithmetic_multisubcycle_v1`, identical for both algorithms:
`loops = 3`, `mstepmax_main = [9, 10, 7]`, `mstepmax_ice = [1, 1, 1]`. The ABC stream
is byte-identical with the probe on and off, and `--check-noninvasive` keeps that a
gate rather than a one-off observation.
