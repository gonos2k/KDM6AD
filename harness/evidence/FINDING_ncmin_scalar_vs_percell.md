# Finding: `ncmin` is a scalar in Fortran and per-cell in C++

Status: **CONFIRMED by measurement.** A column permutation changes **46 of 144**
final-state cells, so the pinned Fortran operator is not column-local. Reported, not
acted on — production physics is frozen and which implementation is correct is owner
adjudication.

## The measurement

Microphysics is column-local, so the operator is block-separable and therefore
equivariant under any column permutation `P`:

    M(P X) = P M(X)

`harness/tests/test_g33_column_separability.py` runs the same atmosphere twice with its
columns in two orders, un-permutes the second, and compares the final state bit for bit.
On `boundary_mapping_v1`, legacy, kernel boundary:

    46 of 144 final-state cells differ
    e.g. bg(1,2) bg(2,2) bg(3,2) nc(1,1) nc(1,2) nc(2,2)

144 = 12 carried fields x 3 columns x 4 levels. The permutation moves the SEA column to
`ite`, which is what changes the scalar's selection; the fixture's `nc` is 4.0e7..5.04e7,
between `ncmin_sea` 2.5e7 and `ncmin_land` 1e8, so `nci <= ncmin` genuinely flips.

The test is a `strict` xfail: it documents a property the code does not have, and if it
ever starts passing the behaviour changed and the test must be promoted to a requirement.

### It passed vacuously the first time

My first permutation was `(1, 0, 2)`, which swaps two columns but leaves the LAND column
at `ite` — so the scalar `ncmin` never moved and the test could not have failed however
wrong the code was. Worse, the precondition I wrote asserted
`sea[PERM[-1]] == sea[-1]` — that the surface type at `ite` is UNCHANGED, the opposite of
what the test needs. Both are fixed, and the precondition now also requires `nc` to
straddle the two thresholds so the gate can actually flip.

## What it means beyond parity

Column ordering is not a physical property of an atmosphere. A result that depends on it
depends on tile decomposition and on MPI partitioning, which means the same case can give
different answers at different rank counts — and coastal tiles, where land and water
columns share a tile, are exactly where mixed surface types occur.

The `dt=300` fixture is all-land with equal `ncmin`, so this mechanism is inert there and
is NOT the cause of that run's -3 ULP `qr` difference.

Found while looking for an injection anchor for `kernel_after_prologue`. It is exactly
the class of defect the degenerate-fixture finding (owner P0-6) predicted, and it is
invisible to every fixture that existed before `boundary_mapping_v1`.

## The two implementations

**Fortran**, `host/KIM-meso_v1.0/phys/module_mp_kdm6.F` (the SHA-pinned reference):

```fortran
   real                                :: ncmin          ! :812  — a SCALAR
...
! 20250205 ncmin setting
! yhlee start
   do i = its,ite                                        ! :876
     if(slmsk(i).eq.2) then ! land
        ncmin = ncmin_sea
     else
       ncmin = ncmin_land
     endif
   enddo                                                 ! :883
! yhlee end
```

The loop runs over every column and assigns a scalar, so when it ends `ncmin` holds
**only the last column's value** (`i = ite`). It is never re-assigned afterwards, and it
is read at 18 sites, all inside per-`(k,i)` loops — `:1124`, `:1534`, `:1565`, `:1610`,
`:1636`, `:1753` and others, each of the form

```fortran
          if(qci(i,k,1).le.qmin .or. nci(i,k,1).le.ncmin ) then
```

so every column is gated on column `ite`'s threshold.

**C++**, `harness/g33_overlay/runtime.cpp.overlay` (mirroring `runtime.cpp`):

```cpp
auto sea_mask_flat = xl_flat >= 1.5;
auto ncmin_flat = torch::where(sea_mask_flat,
                               torch::full_like(xl_flat, ncmin_sea),
                               torch::full_like(xl_flat, ncmin_land));
auto ncmin_tensor = ncmin_flat.unsqueeze(1).expand_as(cs.qc).contiguous();
ncmin_tensor = torch::clamp(ncmin_tensor, /*min=*/constants::NCMIN);
```

Per **cell**, from each column's own `xland`.

## When they disagree

The two agree only if every column has the same surface type, or if
`ncmin_land == ncmin_sea`. Otherwise the Fortran applies column `ite`'s threshold
everywhere and the C++ applies each column's own.

Both pre-existing fixtures satisfy BOTH escape conditions:

| fixture | `xland` | `ncmin_land` | `ncmin_sea` |
|---|---|---|---|
| `arithmetic_synthetic_v1` | all 1.0 | 10.0 | 10.0 |
| `arithmetic_multisubcycle_v1` | all 1.0 | 10.0 | 10.0 |
| `boundary_mapping_v1` | **[1, 2, 1]** | **1.0e8** | **2.5e7** |

So the difference is doubly invisible to the fixtures the gate has been running on, and
`boundary_mapping_v1` breaks both conditions deliberately.

## Why it matters for G3.3-M

It is a Fortran↔C++ semantic difference **at the kernel boundary** and **not
conservative-only** — the code is identical in `module_mp_kdm6.F` and
`module_mp_kdm6_cons.F`. That makes it a candidate explanation for a difference that
appears in the legacy and conservative pairs alike, which is the shape of the observed
`dt=300` divergence.

It is a candidate, not the cause. The `dt=300` fixture has `xland = [1,1,1]` and equal
`ncmin`, so this mechanism is inert there and cannot be what produced that run's −3 ULP
`qr` difference.

## Not a bug, one line up

The comment on `:877` reads `! land` while the branch assigns `ncmin_sea`. The comment is
wrong and the assignment is right: `slmsk` is `xland`, WRF uses 1 = land / 2 = water, and
the sibling block at `:900` labels the same test `! water`:

```fortran
   do i = its,ite
     if(slmsk(i).eq.2) then      ! water
       qcr(i,:) = qc0
     else
       qcr(i,:) = qc1
     endif
   enddo
```

That block is also the internal evidence for the scalar reading being unintended: the
same author, in the same prologue, made `qcr` a per-column ARRAY (`qcr(i,:)`) and left
`ncmin` a scalar.

## What would settle it

A four-leg run at `boundary_mapping_v1`. If the mechanism is real, the Fortran and C++
legs differ on the columns whose surface type is not column `ite`'s, in the fields gated
by `ncmin` — and legacy and conservative differ identically, since neither variant
touches this code.

## What must NOT happen

No production change. `host/**` is frozen, this is a physics-behaviour question, and
which of the two implementations is correct is not the harness's call.
