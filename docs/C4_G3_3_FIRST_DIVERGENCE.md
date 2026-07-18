# C4 Gate B G3.3 — first-divergence attribution (analysis)

**Branch**: `analysis/c4-g3.3-first-divergence` · diagnostic-only, no production change.
**Status**: **G3.3 OPEN.** Strong but NOT conclusive evidence for **Case 2
(inherited cross-tree mechanism, variant amplifies state magnitude)**; the
op-level per-sub-cycle **G3.3-M** trace (see closure section) is the REQUIRED
closure and is not yet done. On evidence, the aggregate relative-error argument
is suggestive only.

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

## Evidence 2 — near-identical RELATIVE cross-tree drift in the dominant field

**Correction (prior wording was imprecise).** A **ULP count** is already a
magnitude-normalized distance — the number of representable floats between two
values — so for the SAME relative error it stays broadly comparable across
magnitudes, varying only ~2× with exponent-boundary and significand position, NOT
proportionally with the value. So "ULP distance scales with magnitude" is wrong
for ULP *count*; a large ULP-count gap is therefore **not automatically** a mere
magnitude artifact and must be checked against the relative error directly.
Doing so, the relative cross-tree error `|fort − cpp| / |fort|` at the max cell is:

| case | field | cons rel | legacy rel | ratio |
|---|---|---|---|---|
| closure3-C3.3 | qr | 6.697e-03 | 6.537e-03 | **1.02** |
| closure3-C3.3 | nr | 1.955e-04 | 1.113e-04 | 1.76 |
| closure3-C3.3 | qv | 4.052e-04 | 1.582e-04 | 2.56 |
| species-iso | qr | 1.378e-04 | 1.282e-04 | **1.07** |
| species-iso | nr | 1.033e-05 | 9.839e-06 | 1.05 |
| species-iso | qv | 5.636e-07 | 5.634e-07 | **1.00** |

- For the **dominant field `qr`** the relative drift is **near-identical**
  between the two pairs (ratio 1.02 / 1.07). The 77,852-vs-77,312 ULP-count gap
  corresponds to this near-identical relative drift evaluated at a slightly
  different `qr` magnitude — consistent with the SAME inherited effect. This is
  **suggestive, not proof**: an equal aggregate relative drift does not by itself
  establish a shared first-diverging operation (that is the op-level step below).
- This holds **per cell, not just at the max** — every shared `qr` cell has a
  cons/legacy relative-error ratio ≈ 1 (and one cell where the conservative is
  LOWER):

  | case | cell (j,k) | cons rel | legacy rel | ratio |
  |---|---|---|---|---|
  | closure3-C3.3 | (2,1) | 1.095e-03 | 1.916e-03 | 0.57 |
  | closure3-C3.3 | (2,2) | 2.982e-03 | 2.860e-03 | 1.04 |
  | closure3-C3.3 | (2,3) | 6.697e-03 | 6.537e-03 | 1.02 |
  | species-iso | (1,1) | 1.378e-04 | 1.282e-04 | 1.07 |
  | species-iso | (1,2) | 6.246e-05 | 6.273e-05 | 1.00 |
  | species-iso | (1,3) | 1.791e-05 | 1.747e-05 | 1.03 |
  | species-iso | (1,4) | 2.802e-06 | 2.802e-06 | 1.00 |

  The `qr` field — the one that breaches the ULP envelope — carries near-identical
  relative cross-tree drift in both pairs, cell for cell. This is strong evidence
  the breach reflects an inherited drift at amplified magnitude rather than a new
  divergence — but it remains evidence, not the op-level proof.
- The larger `nr`/`qv` ratios (closure3 **1.76× / 2.56×**) are **NOT automatically
  explained by `qr` magnitude alone**. They are consistent with the conservative
  feeding more rain mass into the number/vapour couplings (rain evaporation → qv,
  rain-number carry → nr), but a raised relative error in a coupled field could
  equally conceal a distinct defect. Ruling that out is precisely the job of the
  op-level trace — it is NOT settled by the aggregate relative-error argument.

## Established mechanism

The multi-subcycle Fortran↔C++ op-order drift is pre-documented and **inherited,
not variant-specific**: C3.4 records the `FS64_MULTI` oracle↔C++ op-order drift
(gated 1e-5), and the Gate B **legacy control pair (mp37 `kdm6` vs C++
`physics_variant=0`) fails raw-bit at dt=300 in the same cells** — i.e. the drift
exists with the conservative code entirely inactive.

## Interim conclusion

Cell-set identity + near-identical `qr` relative drift + rain-family locality +
the inherited legacy-control drift point to **Case 2** (not yet proven at op
level): the conservative variant most likely does not introduce a new cross-tree
divergence; it amplifies the state magnitude
(legitimately, by not deleting rain mass at interfaces) feeding an inherited
multi-subcycle relative-precision drift.

**Remaining step (REQUIRED, not optional)**: the **G3.3-M** per-sub-cycle
instrumented dump of the Gate B driver (branch `analysis/c4-g3.3-op-provenance`)
for both pairs, at the `qr` max cell (closure3 j=2,k=3) **and** the `nr`/`qv`
cells that carry the 1.76×/2.56× ratios, pinning the first-diverging sub-cycle
index + sed op + pre/post raw bits + branch/clamp/mstep signature — to confirm
the first divergence is the SAME op on the SAME branch with only input magnitude
differing (and specifically that the elevated `nr`/`qv` ratios are not a distinct
op). See the closure section for the pass/fail criterion.

## Closure metric — G3.3-M mechanism-provenance gate (supersedes the withdrawn G3.3′)

An earlier draft proposed a fixture-wide global relative-error envelope
("G3.3′"). **It is withdrawn** — it is not a sound gate:

- it bundles fields of different units (`th` [K], `qv`/`qr` [kg/kg], `nr` [#/kg])
  under one maximum relative error;
- it applies the mixing-ratio floor `qcrmin` to temperature and number
  denominators, where that floor has no physical meaning;
- a large legacy relative error would raise the single bound enough to **mask** a
  genuine new conservative defect in a different field.

The correct closure is **mechanism provenance, not an error envelope**. On branch
`analysis/c4-g3.3-op-provenance`, a per-sub-cycle instrumented dump must record,
**identically for both pairs** (legacy `kdm6`↔`variant=0` and conservative
`237`↔`337`):

> **G3.3-M:** the first divergent outer sub-cycle · the first divergent
> process / exact operation · the pre-op input raw bits · the post-op output raw
> bits · the branch/clamp/mstep signature · the downstream `qr/nr/qv/th/precip`
> propagation. G3.3 closes **PASS-by-mechanism iff both pairs begin diverging at
> the SAME operation on the SAME branch with NO conservative-only switch**, and
> the conservative differs ONLY in the input magnitude entering that shared op.
> Any conservative-only operation or branch at the first divergence is a **FAIL**.

This is decided a-priori (the criterion is structural, not a tuned threshold) and
does not depend on the imprecise ULP-vs-magnitude argument. Until that trace
exists G3.3 stays **OPEN**; the absolute-ULP envelope remains the gate in the
interim. Single-subcycle raw-bit (G1) and water closure (G2) are unchanged and
remain strict.
