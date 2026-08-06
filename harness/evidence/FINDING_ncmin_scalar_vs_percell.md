# Finding: `ncmin` is a scalar in Fortran and per-cell in C++

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-NCMIN-001` | **active** | confirmed | g33_fixture_boundary_mapping_v1, one call, legacy and conservative. The real mixed-coastal case is still UNMEASURED, so the operational magnitude is not established -- only that the mechanism is O(1) where it bites. The (1,2) partition differs in ZERO cells because both tiles end on land: an even-split-only gate would pass while the operator was arbitrarily non-local, which is why the partition set is exhaustive. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

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


---

# Tile decomposition, measured (owner review §6 acceptance gates 2 and 3)

Column permutation is §6's first gate and already measured. The second is now
measured too: splitting the SAME columns across separate `kdm62D` calls, the way a
tile or MPI decomposition does. `its:ite` is a call argument, so this is
driver-side only and needs no production change — and it reaches the mechanism from
a completely different direction than permuting the input.

**Exhaustive over the contiguous partitions of the domain**, not just even splits.
`boundary_mapping_v1` (xland 1, 2, 1 — the middle column is sea; ncmin_land = 1e8,
ncmin_sea = 2.5e7), legacy:

| partition | tile ends | cells differing | columns |
|---|---|---|---|
| (3,) | 3: land | — | baseline |
| (1, 2) | 1: land, 3: land | **0 / 144** | — |
| (1, 1, 1) | 1: land, **2: SEA**, 3: land | **16 / 144** | 2 |
| (2, 1) | **2: SEA**, 3: land | **31 / 144** | 1, 2 |

Up to **21% of the final state** is decided by where the tile boundary falls, and
all twelve prognostics move in the affected columns.

**How large, not only how many.** The line above used to end "— a whole-state
difference, not a rounding one". That was an assertion attached to a *count*, and
a count cannot separate a roundoff-scale difference from a dominating one — the
same conflation owner §10 named for the cap-bound interfaces. `g33_ncmin_locality`
measures it:

| partition | field | max relative | max ulps | vs f32 eps |
|---|---|---|---|---|
| (2, 1) | **qi** | **9.9661e-01** | 68 525 882 | **8.4 × 10⁶** |
| (2, 1) | ni | 8.8394e-01 | 26 265 291 | 7.4 × 10⁶ |
| (2, 1) | qr | 2.0719e-01 | 2 237 951 | 1.7 × 10⁶ |
| (2, 1) | qv | 3.6666e-02 | 468 889 | 3.1 × 10⁵ |
| (1,1,1) | qi | 9.8346e-01 | 49 659 291 | 8.2 × 10⁶ |

Cloud ice in an affected column is decided **to O(1)** by where the tile boundary
falls — the smallest of the twelve fields (`qg`, 1.7e-05) is still 142× f32 eps.
So the phrase was right, and far weaker than the fact.

**What the analyzer refuses, and what it cannot see.** Three successive
fail-open holes were found in this tool's completeness gate — it parsed the
stream itself instead of using the strict parser; it then compared each
partition only against the baseline, which a commonly-dropped column satisfies
exactly; and it checked columns as a set but levels as a count, admitting a
shifted axis. Each fix moved the weakest point rather than closing the class, so
the axes are enumerated here rather than discovered one at a time:

| what | how it is caught |
|---|---|
| truncated / empty / duplicated / non-finite stream | the strict `G33R` parser |
| a column or level missing from **every** run | `B`, `K` read from the fixture source |
| a level axis shifted off `0..K-1` | set equality, not a count |
| record count ≠ `12 × B × K` | explicit |
| a driver that validates the tile spec and then **ignores** it | `G33N CALL_BEGIN`, written from inside the tile loop, must carry the bounds actually handed to `kdm62D` |
| a **reversed** level axis, a **transposed** column mapping | **not caught** — these are the same set. Ordering is not a universe property. Neither passes silently: applied to one run and not the other they make most cells differ, surfacing as an implausibly large result rather than a clean one. |

The tile-liveness row went through the same cycle in miniature and is worth
recording. Its first version ran an *invalid* spec and required a refusal —
which proves only that the argument is parsed and **validated**. Validation
lives in the argument parser and use lives in the tile loop, so a driver that
validated the spec and then called the kernel over the whole domain passed that
check. It now reads `G33N CALL_BEGIN`, which the driver writes from inside the
tile loop carrying the very bounds it hands to `kdm62D`. That requires an
`--nflux` build; a build without one is **refused**, not skipped, and the
overlay is measured non-invasive on this fixture (STATE records byte-identical
across all four partitions) rather than assumed from the A/B/C proof.

The common failure mode in all of them is the same and is worth naming: a broken
measurement reports **zero differences**, which reads as "the operator is
column-local" — the strongest possible pass, and the exact claim this tool
exists to refute.

**The conservative interface does not fix it.** The document argued this from
source; it is now measured — both variants differ in exactly the same 0 / 16 / 31
cells, in the same columns. The P0-4b work does not touch this, so it stays open
on its own terms.

The pattern is predicted exactly by the scalar mechanism. `ncmin` survives the
column loop holding the LAST column's threshold, so what matters is the surface
type at each tile's `ite`:

* **(3,)** ends on land, so every column is gated on `ncmin_land`.
* **(1,2)** — both tiles end on land, identical gating, 0 cells differ. That
  agreement is **not** evidence of correctness, and an even-split test that only
  reached this partition would pass while the operator was arbitrarily non-local.
* **(1,1,1)** puts the sea column at its own tile end, so that column alone is
  gated on `ncmin_sea`.
* **(2,1)** ends its first tile on the sea column, so **both** columns 1 and 2 are
  gated on `ncmin_sea` — the worst case, and the one an even split misses entirely.

**This is the MPI rank-count gate as well.** A rank boundary is a tile boundary;
the mechanism cannot distinguish them, and the partition set above is exhaustive
for this domain. What a real MPI driver would add is halo and reduction behaviour,
which is not what `ncmin` depends on.

An earlier run of this on `arithmetic_multisubcycle_v1` gave 0/144 at every
partition. That fixture is all-land (xland 1, 1, 1), so `ncmin` is identical for
every column and the mechanism cannot fire — the result was vacuous and is not
evidence. The gate now asserts both that some partition can expose the mechanism
and that some multi-tile partition is expected to agree trivially, so neither a
vacuous fixture nor a lucky partition can be read as a pass.

Remaining from §6's four gates: a **mixed coastal real case**, which needs a real
fixture rather than a synthetic one.

## Independently strengthened under adversarial review

An independent check tried to break the `ncmin` attribution by constructing two
**new** surface layouts specifically designed to make the last-column rule fail. It
held. Keying every column-run by `(column index, its own xland, the ncmin selected
by its tile's LAST column)`, **all 60 column-runs across 5 fixtures × 4 partitions
are bitwise identical within each key** — a bit-level confirmation rather than the
column-level one above, and stronger than the original measurement.

The `(1,2)` partition agreeing (0/144) remains the control against a slicing or
loop-bound artifact: if the difference came from how the array is sliced rather than
from which threshold is selected, `(1,2)` would differ too.
