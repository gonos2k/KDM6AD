# A comparison that fixed five things and let seven vary

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-COMPARE-001` | **active** | confirmed | The G33P stream contract and comparator. Fixture SHA and executable identity are still NOT in the stream -- they live in the bundle's build_provenance -- so identity is enforced at two levels and a comparison of loose streams outside a bundle cannot check them. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner §8. `compare()` refuses two streams that are not the same experiment, which
made it look like the comparison identity was settled. It was not: the identity
was a **hand-written list**, and the list was short.

## §8.1 — what was allowed to differ

| kind | was pinned | was free to vary |
|---|---|---|
| `precision_pair` | fixture, algorithm, mode, nsplit, dtcld | `source_precision`, `loops`, `ntile`, `delt`, **the tile vector** |
| `variant` | fixture, precision, mode, nsplit, dtcld | same five |
| `refinement` | fixture, algorithm, mode, precision | same five |

`ntile` free is the one that bites. `ncmin` is a scalar overwritten inside the
column loop (`FINDING_ncmin_scalar_vs_percell.md`), so the same atmosphere split
differently can give different answers — and a `variant` comparison across two
decompositions would attribute a **decomposition** effect to the **algorithm**.

The fix is not a longer list. The invariant set is now **computed**:

    invariants(kind) = IDENTITY − {the axis under test} − {what covaries with it}

so a field added to the header becomes an invariant **by default**. The failure
mode of a list is that the next schema change fails *open*; this one fails closed.

`refinement` names `nsplit` and `delt` as covarying with `dtcld`, because they are
the same knob written three ways — pinning them would make the comparison
impossible rather than strict.

### The tile vector

`ntile` cannot distinguish `(2,1)` from `(1,2)`, which is exactly the pair that
`ncmin` makes disagree. So G33P schema 3 carries the **vector**, not its length:

```
G33P BEGIN 3 precision f32 source_precision f32 fixture … mode rezero tiles 2,1 …
```

## §8.2 — the ULP statistic depended on argument order

`precision = a[("meta", "precision")]` took the lattice from whichever stream was
passed **first**, so `diff(f32, f64)` and `diff(f64, f32)` counted representable
steps on different lattices and reported different numbers for the same pair.

Across precisions there is no single "max ULP". The lattice is now **named in the
field itself** — `max_ulp_f32` beside `ulp_lattice: "f32"` — and for a
cross-precision pair it is f32, which is the question a `precision_pair` is
actually asking: *does promoting the arithmetic change the answer at the
reference's own resolution?* The `precision` field is **absent** on such a diff
rather than carrying whichever stream came first.

Verified order-independent: `diff(f32,f64)` and `diff(f64,f32)` both report
`max_ulp_f32 = 1024419564`.

## §8.3 — "bitwise identical" did not mean the bits

`x == y` is `True` for `+0.0` and `−0.0`, and `_bits` deliberately maps both to
the same point (so that "zero representable steps apart" is true across zero). Both
are right for their purpose, and together they certified a pair whose **stored
patterns differ** as `bitwise_identical`.

*Bitwise* is a certification word. One field became two:

| field | question |
|---|---|
| `numerically_identical` | are the numbers the same |
| `raw_bit_identical` | are the stored patterns the same |

## Nothing about the published results changed

The comparator reproduces every figure it produced before: legacy vs conservative
**0 of 333** at f64 (now also `raw_bit_identical: true`), **39 of 333** at f32
with `max_rel = 0.8656` and `max_ulp_f32 = 24325658`. This tightens what may be
compared and what a field is allowed to claim; it does not move a number.

## Limits

- **Fixture SHA and executable identity are still not in the stream.** The owner
  lists them, and they are genuinely not the driver's to know — the *bundle*
  records them in `build_provenance`. So identity is enforced at two levels, and
  a comparison of two loose streams outside a bundle cannot check them. Named
  here rather than quietly dropped.
- **Total horizon is not separately pinned.** `nsplit`, `delt` and `dtcld` are
  pinned or covarying, which fixes it on this driver because the horizon is
  `DT_BITS`, a fixture constant. A driver that took the horizon as an argument
  would need it in the header.
- The computed invariant set is only as good as `IDENTITY`. A header field that
  is never added to that tuple is still invisible — the mechanism removes the
  per-comparison omission, not the per-field one.
