# The freeze heat term: what the source says, and the measurement that settles it

Design for the next bisection, plus a source-level finding that motivates it. No
measurement here — the claims below are readings of two frozen sources and are
flagged as such.

## Where v13 leaves it

The seed is a 1-ULP `t` at `micro_post_freeze`, loop 2, column 3. `micro_post_melt`
is bit-identical, so D1 melt and the homogeneous freeze before it are excluded.
Four statements write `t` in the remaining span:

```fortran
F:1529  t += xlf/cpm * qci(i,k,1)    homogeneous freeze (T < −40 °C)
F:1618  t += xlf/cpm * pinuc         contact/heterogeneous nucleation
F:1648  t += xlf/cpm * pfrzdtc       Bigg cloud freeze
F:1679  t += xlf/cpm * pfrzdtr       Bigg rain freeze
```

Every companion prognostic those statements write is bit-identical, so the rates
are very likely equal and the difference is in the heat term.

## What the declarations say

Pinned Fortran (`module_mp_kdm6.F`):

| symbol | line | declared |
|---|---|---|
| `xlf` | :783 region | `real` scalar, per cell (`xlf = xls - xl(i,k)`, F:1516) |
| `cpm` | :749 | `real, dimension(its:ite,kts:kte)` |
| `pinuc` | :758 | **`double precision`** scalar |
| `pfrzdtc` | :781–782 | **`double precision`** scalar |
| `pfrzdtr` | :781–782 | **`double precision`** scalar |

So each addition is `f32 + (f32/f32)*DOUBLE`, which promotes to double and rounds
**once** on the store into the `REAL(4)` array.

The C++ mirror (`coordinator.cpp:636–639`):

```cpp
auto fr_coef = xlf_freeze / cpm_safe;
auto t_d2 = (t_d1 + fr_coef * mf.pinuc).to(dtype);      // D2 freeze heat (F:1539)
auto t_d3 = (t_d2 + fr_coef * mf.pfrzdtc).to(dtype);    // D3 freeze heat (F:1569)
out.t   = (t_d3 + fr_coef * mf.pfrzdtr).to(dtype);      // D4 freeze heat (F:1591, f32 rate)
```

with the comment above it: *"the f32 coefficient xlf/cpm promotes against the
DOUBLE D2/D3 rates exactly like gfortran"*.

**The comment classifies D4's rate as `f32`. The pinned Fortran declares
`pfrzdtr` `double precision`, on the same line as `pfrzdtc`.** The comment is
wrong about the reference for that one term.

## Why that is a candidate and not a conclusion

Whether the C++ *value* is f32 cannot be settled by reading. `pfrzdtr` is built as

```cpp
auto pfrzdtr = torch::where(active, torch::minimum(pfrzdtr_raw, in.qr), zero);
```

where `pfrzdtr_raw` multiplies `in.n0r` — DOUBLE per F:679 — so it is probably
f64, and `torch::minimum` / `torch::where` promote, which would make the result
f64 despite `zero` being f32. Torch promotion is a runtime property of the actual
tensor dtypes; a static read cannot decide it.

If the value *is* f32 there, the D4 term rounds twice (at the multiply and at the
add) where Fortran rounds once — which is the right order of magnitude for a
1-ULP `t`.

## The measurement (protocol v14)

`micro_freeze_heat`, the closed operand set of the four additions:

| field | dtype | Fortran | C++ |
|---|---|---|---|
| `t_pre_freeze` | f32 | `t(i,k)` at F:1517 | `s.t` after D1 |
| `xlf` | f32 | scalar at F:1516–1517 | `xlf_freeze` |
| `cpm` | f32 | `cpm(i,k)` | `pre.cpm` |
| `phom` | f32 | `qci(i,k,1)` at F:1529 | homogeneous-freeze amount |
| `pinuc` | **f64** | scalar at F:1618 | `mf.pinuc` |
| `pfrzdtc` | **f64** | scalar at F:1648 | `mf.pfrzdtc` |
| `pfrzdtr` | **f64** | scalar at F:1679 | `mf.pfrzdtr` |

Recording the three rates as **f64 on both sides is the point**: an f32 value
widened to f64 carries zeros in the low mantissa, an f64 value generally does
not, so a precision difference appears as a value difference instead of being
erased by a cast. `real(pfrzdtr)` — the existing forensic capture at F:1662 —
casts to f32 and would hide exactly this.

Replay, per leg, mirroring the source's four sequential f32 stores:

```
c  = f32(xlf / cpm)
t1 = f32(t_pre + c*phom)
t2 = f32(t1    + c*pinuc)
t3 = f32(t2    + c*pfrzdtc)
t4 = f32(t3    + c*pfrzdtr)      t4 == micro_post_freeze.t
```

Outcomes: an operand differs → that rate is the seed; all operands match and the
replay reproduces both legs → the difference is in how the two backends round the
same expression, and the per-term intermediates say which term.

## Implementation notes

The three rates are **per-cell scalars set inside branches**, so they cannot be
read from a top-level emission point. They are captured into dump-only scratch
arrays at the site of use — the pattern `g33_fqb`/`g33_fnb` already uses, and the
pinned source's own `dbg_d4a = real(pfrzdtr)` (F:1662) does the same thing — zeroed
per cell alongside the existing `dbg_d4a…d4d` zeroing at F:1021–1024, so a
skipped branch reads 0, which is what it means numerically.

`if(supcol.lt.0.) xlf = xlf0` at F:1517 is the capture point for `t_pre_freeze`
and `xlf`: it is at the top of the freeze loop, before the homogeneous freeze, and
every cell reaches it. The line occurs twice (F:1366 and F:1517), so the anchor
needs occurrence index 1 (0-based) and a landmark.

On the C++ side the emission has to sit inside `melt_freeze_phase` — `t_d1`,
`t_d2` and `t_d3` are locals there — and `test_g33_overlay_mirror_sites` does not
apply, because this point has no reconciled substep dump. That is a new
correspondence, which is the class of site every placement defect in this protocol
has come from, so it needs its own argument before the numbers are read.
