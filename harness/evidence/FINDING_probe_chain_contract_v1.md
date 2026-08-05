# The f64 bundle had every per-member check and none of the between-member ones

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-PROTOCOL-004` | **active** | confirmed | Cross-member within one bundle. Two separately published f64 bundles can still disagree -- that identity lives in a claim's artifacts pins. CHAIN_INVARIANT is enumerated rather than computed, because a chain has no single axis to subtract the way a pairwise comparison does; that is a real difference in strictness from the G33P comparison identity. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner §8.4. An f64 bundle supplies its own `member_reader`, because its members
are G33P streams rather than G33R ones. The manifest builder then left `runs`
empty on that path — and both cross-member checks are guarded on `runs`:

```python
if member_reader is None and len(ns) != len(set(ns)):   # duplicate nsplit
runs = {} if member_reader is not None else {...}
if len(runs) > 1: ra.require_same_universe(runs)         # never reached
```

So each f64 member was strict-parsed on its own — a truncated, NaN or ragged
stream could not get in — and **nothing checked the members against each other**.

## What that admitted

A published f64 refinement chain could mix:

| | consequence |
|---|---|
| two fixtures | a "convergence order" taken across two different atmospheres |
| two algorithms | legacy and conservative averaged into one chain |
| two modes | `carry` and `rezero` members side by side |
| two **tile maps** | `ncmin` makes `(2,1)` and `(1,2)` disagree, so the chain measures **decomposition**, not step |
| two density arms | an `as-is` member beside a `uniform` one |
| two horizons | members integrating different total times |
| a duplicate `nsplit` | one of the two silently discarded |
| different record universes | an incomplete member reports a smaller error — convergence measured on **absence** |

None of these is exotic. The refinement chain is exactly where two runs get
compared, so it is exactly where mixing them is worst.

## `require_probe_chain`

Applies the pairwise `refinement` contract across a whole bundle: `dtcld` is the
axis, `nsplit` and `delt` move with it, and everything else identifying the
experiment must be identical. Plus two the pairwise form does not need:

- **one horizon.** `nsplit` and `delt` both move with `dtcld`, so neither alone
  pins the total integration time — their **product** does.
- **it must actually refine.** Two members at one `dtcld` are a repetition;
  a manifest calling that a refinement chain would be wrong.

The duplicate-`nsplit` check is also no longer guarded on the reader: two members
for one `nsplit` collapse to one entry whichever parser read them, so guarding it
exempted precisely the bundle that had no other cross-member check.

## Verified on a real bundle

A three-member f64 chain (n3, n6, n12) now produces through the atomic producer
and satisfies every invariant. That path was **completely broken** until the
schema-literal fix — it raised `ProbeError` before any of this could run — so
this is also the end-to-end confirmation that P0-1 is closed in the producer and
not only in the driver.

## Limits

- **Cross-member, not cross-bundle.** Two separately published f64 bundles can
  still disagree about anything; the identity that would catch that lives in the
  claim's `artifacts` pins, not here.
- The invariants are `CHAIN_INVARIANT`, a list. It is the same failure mode the
  G33P comparison identity had before it was computed — a field added to the
  header does not join it automatically. The comparison identity is computed
  because it has an axis to subtract; a chain has no single axis to subtract, so
  this one is enumerated and that is a real difference in strictness.
