# Why the current fixture cannot reach multi-subcycle, and what would

Status: **measurement, not yet a fixture.** Grounds the design of
`arithmetic_multisubcycle_v1`.

## The substep count is set by one relation

From `module_mp_kdm6.F` (F:1126-1128), per column, maximised over levels:

```
numdt = max( nint( max(work1_qr, workn_qr, work1_qs, work1_qg) * dtcld + 0.5 ), 1 )
mstep = max over k of numdt
```

`work1 = vt / delz` (fall speed over layer thickness). So

```
mstep >= 2   <=>   work1 * dtcld >= 1.5
```

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
dtcld >= 1.5 / 1.143e-4 = 13,123 s
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

| `delz` | `work1` | `mstep >= 2` needs `dtcld >=` | at dt=300 (`dtcld=100 s`) |
|---|---|---|---|
| 8,550 m (today) | 1.14e-4 | 13,123 s | mstep = 1 |
| 500 m | 2.0e-3 | 767 s | mstep = 1 |
| 200 m | 4.9e-3 | 307 s | mstep = 1 |
| 100 m | 9.8e-3 | 154 s | mstep = 1 |
| **50 m** | **1.95e-2** | **77 s** | **mstep = 2** |

So a fixture that exercises BOTH the historical multi-outer-loop path (dt=300 ->
loops=3) and multi-substep transport wants `delz` of roughly **50-65 m**.

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
