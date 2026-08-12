# Finding: `ncmin` is a scalar in Fortran and per-cell in C++

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-NCMIN-001` | **active** | confirmed | g33_fixture_boundary_mapping_v1, one call, legacy and conservative. The real mixed-coastal case is still UNMEASURED, so the operational magnitude is not established -- only that the mechanism is O(1) where it bites. The (1,2) partition differs in ZERO cells because both tiles end on land: an even-split-only gate would pass while the operator was arbitrarily non-local, which is why the partition set is exhaustive. "31/144" counts prognostic state COMPONENTS (12 fields x 3 columns x 4 levels); the grid has 12 cells, so calling them cells overstated the spatial extent twelvefold (owner §11.1). The derived quantities that would decide operational significance -- q/N, characteristic diameter, reflectivity, surface precipitation -- are NOT measured, and neither is a real MPI rank decomposition with haloes and per-rank surface patterns: this is a sequential multi-call tile experiment that PREDICTS rank sensitivity rather than demonstrating it. |
| `G33-NCMIN-004` | **active** | hold | Direct terms only, not the causal chain: pracw consumes rain that praut produces, so a suppressed autoconversion may still be upstream of the accretion collapse. What the measurement establishes, subject to the HOLD above, is that autoconversion is not where the change APPEARS. g33_fixture_boundary_mapping_v1, one call, nsplit=1. No mass weighting, no dt, and no closure against micro_pre/post_state_update. |

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

**CORRECTION — relative O(1) is not meteorological O(1) (owner §11.3).** The
line above previously read "cloud ice in an affected column is decided to O(1)
by where the tile boundary falls". That is true of the *ratio* and misleading as
physics: `qi`'s 0.9966 sits on a baseline of **6.56e-08 kg/kg**, an absolute
difference of **1.93e-05**. A near-100% disagreement about a near-zero value.

Integrated over the column under the ρΔz measure — the only form in which this
is a physical statement — the picture is different and, for precipitation,
stronger:

| column | quantity | baseline | partitioned | relative |
|---|---|---|---|---|
| 2 | **rain** | 1.6376e-01 | 2.0655e-01 | **26.1%** |
| 1 | **rain** | 1.6710e-01 | 2.0164e-01 | **20.7%** |
| 1 | cloud ice | 9.3998e-02 | 1.0225e-01 | 8.8% |
| 1 | **total condensate** | 1.0556e+00 | 1.0900e+00 | **3.3%** |
| 2 | **total condensate** | 1.5938e+00 | 1.6366e+00 | **2.7%** |

So the defensible headline is **column rain mass differs by 21–26%** with the
tile boundary, and total condensate by 2.7–3.3% — not that cloud ice changes by
100%. The per-component ratios stay in the table above because they show the
mechanism bites hard where it bites; they are not the physical magnitude.

**Both bases, because one of them was called "the only physical form" and was
not (owner §7.1).** The table above is the OPERATOR integral, `ρ_m·Δz` — what the
kernel budgets. The mixing ratios are per dry-air kg, so the physical column mass
is `ρ_d·Δz`. Computed:

| row | operator abs | physical abs | ratio | relative |
|---|---|---|---|---|
| 2/rain | 4.279502e-02 | 4.272239e-02 | 1.00170 | **26.13%** |
| 1/rain | 3.453653e-02 | 3.450203e-02 | 1.00100 | **20.67%** |
| 1/total condensate | 3.435973e-02 | 3.432540e-02 | 1.00100 | 3.25% |

The **relative** figures are identical under both bases, and necessarily so: both
runs share the same window-initial `qv`, so the `1+qv` weight cancels in the
ratio. The absolute masses differ by that factor, 0.10–0.17% here. So the
21–26% headline does **not** depend on the basis — but it is now measured under
both rather than asserted under one.

**The prediction needs the gate to be ACTIVE (owner §7.2).** "A differing
tile-end surface type makes every column in that tile differ" holds only where
the two candidate thresholds can actually behave differently. `ncmin` is used
both as a gate (`nci .le./.gt./.ge. ncmin`, many sites) and as a floor
(`max(ncmin, nci)`, F:2736/2750/2888), and the two candidates agree exactly where
the number exceeds **both**. On this fixture `nc` runs 4.00e+07…5.04e+07 against
thresholds 2.5e+07 and 1.0e+08, so the gate is active in **every** cell — which
is *why* the column prediction is exact here, not a general property. The
predicate is computed now, so a fixture whose `nc` sat outside that band would
not be over-predicted.

**`causal_attribution_valid` is separate from `measurement_valid`.** A partition
whose observed columns miss the prediction used to be recorded as an ordinary
row; the two verdicts are distinguished now, so a causal claim cannot rest on a
run where the attribution failed.

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

## The oracle already exists, and the whole-domain run fails it

A corrected per-column `ncmin` would have to reproduce

    M_local(X) = ⊕ᵢ Mᵢ(Xᵢ; xlandᵢ)

and that answer is computable **with the unmodified kernel**: run each column as
its own tile. In a one-column tile `ncmin` survives the loop holding that
column's own threshold, so `(1,1,1)` **is** the direct sum. The oracle is a
decomposition, not a variant — no freeze-lift, no diagnostic overlay.

That reframes what the earlier tables measured. Comparing partitions with each
other says only that they disagree. Comparing them with the local answer says
how far each is from column-locality. The whole-domain run is the closest thing
here to an operational configuration — **but it is a three-column synthetic
fixture called as one tile by a sequential driver, not a production run**
(owner §9.3). Real MPI adds rank-local `its/ite`, haloes, physics-tile sizing,
the actual coastal layout and multi-step feedback, none of which are here:

| decomposition | components differing | column | worst column-integrated |
|---|---|---|---|
| `1,1,1` | 0 / 144 | — | the oracle |
| **`3` (whole domain, one tile)** | **16 / 144** | **2 (sea)** | **rain −20.72%** |
| `1,2` | 16 / 144 | 2 (sea) | rain −20.72% |
| `2,1` | 15 / 144 | 1 (land) | rain **+**20.67% |

**Sign corrected (owner §9.4).** This table previously read `+20.72%` and the
sentence below it said the run "carries ~21% too much column rain". **The sign
was backwards.** The whole-domain run gates the sea column on `ncmin_land`
(1.0e+08) instead of its own `ncmin_sea` (2.5e+07); a *higher* droplet-number
floor suppresses autoconversion, so it produces **~21% LESS** rain than the
per-column answer, not more. `(2,1)` goes the other way for column 1, which ends
up on the *lower* sea threshold and rains more. The direction is now in the
artifact as `signed_rel` and asserted, rather than being an `abs()` that reads
the same either way.

**Both bases agree here — but not by an identity (owner §9.2).** The finding
said the `1+qv` weight "cancels in a ratio between two runs that share the
window-initial humidity". That is false in general: `a_k = 1/(1+q_{v,k}(t₀))`
sits *inside* the column sum,

    r_d = |Σₖ aₖ wₖ Δqₖ| / |Σₖ aₖ wₖ qₖ|

so a *common* factor cancels and a *level-dependent* one does not. On
`boundary_mapping_v1` the vertical spread of `aₖ` is **exactly zero** in every
column — `qv(t₀)` is vertically constant there — which is why the two bases
agree to the last digit. `humidity_weight_spread()` measures it, so the
agreement is a fixture property rather than an assumed law.

**What licenses attributing this to `ncmin` alone** is the `(1,2)` row of the
earlier table: it differs from the whole domain in **zero** components although
the decomposition changed. Nothing but the `ncmin` gate responds to tiling here.

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
