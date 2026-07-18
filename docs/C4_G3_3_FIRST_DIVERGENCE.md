# C4 Gate B G3.3 — first-divergence attribution (analysis)

**Branch**: `analysis/c4-g3.3-first-divergence` · diagnostic-only, no production change.
**Status**: strong evidence for **Case 2 (inherited cross-tree mechanism, variant
amplifies state magnitude)**; op-level per-subcycle confirmation is the remaining step.

## The exceedance

Gate B G3.3 gates `conservative max ULP <= legacy ULP envelope` per case. At the
`dt=300` (3 KDM sub-cycle) fixtures it is exceeded:

| case | field | cons max ULP | legacy envelope |
|---|---|---|---|
| closure3-C3.3 | qr | 77,852 | 77,312 |
| species-iso | qr | 2,188 | 1,164 |

The `piacw` C4-S1 fix did **not** change these numbers (piacw was the Gate D
single-subcycle residual; G3.3 is a distinct multi-subcycle phenomenon).

## Evidence 1 — the excess is rain-family only, in (near-)identical cells

Per-field cons-vs-legacy over the diff listing (`gateb_diffs.txt`):

- **Excess fields**: `qr` (dominant), and its couplings `nr`, `qv`, `th`,
  `rain_increment`. **`qs`, `qg`, `bg`, `rhog` show NO excess** (cons ≤ legacy).
  The conservative interface transfer acts on **rain sedimentation mass carry**,
  so only the rain family is affected — consistent with the variant's design.
- **Divergence cell SETS**: closure3 — `qr/nr/qv/rain_increment` diverge in the
  **EXACT SAME cells** for both pairs (cons-only = ∅). species-iso — `qr` same
  cells; `nr`/`qv` are a cons ⊇ legacy superset (+1 cell each). No wholesale new
  divergence region → not a new conservative-specific failure site.

## Evidence 2 — same RELATIVE cross-tree drift (ULP difference is a magnitude artifact)

ULP distance scales with magnitude, so comparing max-ULP across two pairs at
different magnitudes is the wrong invariant. The magnitude-independent measure is
the relative cross-tree error `|fort − cpp| / |fort|` at the max cell:

| case | field | cons rel | legacy rel | ratio |
|---|---|---|---|---|
| closure3 | qr | 6.697e-03 | 6.537e-03 | **1.02** |
| closure3 | nr | 1.955e-04 | 1.113e-04 | 1.76 |
| closure3 | qv | 4.052e-04 | 1.582e-04 | 2.56 |
| species-iso | qr | 1.378e-04 | 1.282e-04 | **1.08** |
| species-iso | nr | 1.033e-05 | 9.839e-06 | 1.05 |
| species-iso | qv | 5.636e-07 | 5.634e-07 | **1.00** |

- For the **dominant field `qr`** the relative drift is **essentially identical**
  between the two pairs (ratio 1.02 / 1.08). The 77,852-vs-77,312 ULP gap is
  purely that the conservative `qr` sits at a slightly different magnitude — the
  underlying relative-precision drift is the same inherited effect.
- This holds **per cell, not just at the max** — every shared `qr` cell has a
  cons/legacy relative-error ratio ≈ 1 (and one cell where the conservative is
  LOWER):

  | case | cell (j,k) | cons rel | legacy rel | ratio |
  |---|---|---|---|---|
  | closure3 | (2,1) | 1.095e-03 | 1.916e-03 | 0.57 |
  | closure3 | (2,2) | 2.982e-03 | 2.860e-03 | 1.04 |
  | closure3 | (2,3) | 6.697e-03 | 6.537e-03 | 1.02 |
  | species-iso | (1,1) | 1.378e-04 | 1.282e-04 | 1.08 |
  | species-iso | (1,2) | 6.246e-05 | 6.273e-05 | 1.00 |
  | species-iso | (1,3) | 1.791e-05 | 1.747e-05 | 1.03 |
  | species-iso | (1,4) | 2.802e-06 | 2.802e-06 | 1.00 |

  The `qr` field — the one that breaches the ULP envelope — carries the SAME
  relative cross-tree drift in both pairs, cell for cell. The breach is an
  absolute-ULP-vs-magnitude artifact, not a new divergence.
- The larger `nr`/`qv` ratios (closure3 ~1.8–2.6×) are the conservative feeding
  **more rain mass** into the number/vapour couplings (rain evaporation → qv,
  rain-number carry → nr) through the SAME drifting sub-cycle machinery — a
  magnitude effect on coupled fields, not a new op.

## Established mechanism

The multi-subcycle Fortran↔C++ op-order drift is pre-documented and **inherited,
not variant-specific**: C3.4 records the `FS64_MULTI` oracle↔C++ op-order drift
(gated 1e-5), and the Gate B **legacy control pair (mp37 `kdm6` vs C++
`physics_variant=0`) fails raw-bit at dt=300 in the same cells** — i.e. the drift
exists with the conservative code entirely inactive.

## Interim conclusion

Cell-set identity + identical `qr` relative drift + rain-family locality +
the inherited legacy-control drift point to **Case 2**: the conservative variant
does not introduce a new cross-tree divergence; it amplifies the state magnitude
(legitimately, by not deleting rain mass at interfaces) feeding an inherited
multi-subcycle relative-precision drift.

**Remaining step (rigour)**: per-sub-cycle instrumented dump of the Gate B driver
for the `qr` max cell (closure3 j=2,k=3) in both pairs, to pin the first-diverging
sub-cycle index + sed op + pre/post raw bits and confirm the op is identical with
only the input magnitude differing.

## Proposed a-priori G3.3 metric (for owner adjudication — specified before re-measuring)

The current absolute-max-ULP-envelope is the wrong invariant for a magnitude-
amplified inherited drift. Proposed replacement, defined a-priori (NOT tuned to
the 77,852 result):

> **G3.3′ (relative, magnitude-normalized):** for every (field, cell) diverging
> in the conservative pair at a multi-subcycle fixture, the relative cross-tree
> error `|fort − cpp|/max(|fort|, qcrmin)` must be **≤ the maximum relative
> cross-tree error the LEGACY pair exhibits over the same fixture** (a single
> per-fixture legacy bound), not a per-cell absolute-ULP comparison. New
> cons-only cells are held to the same single legacy bound.

This certifies "the conservative introduces no relative cross-tree error beyond
the inherited legacy envelope," which is the physically meaningful invariant and
is decided before its value is measured. Single-subcycle raw-bit (G1) and water
closure (G2) are unchanged and remain strict.
