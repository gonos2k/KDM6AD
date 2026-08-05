# The f64 bundle had every per-member check and none of the between-member ones

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-PROTOCOL-004` | **active** | confirmed | Cross-member within one bundle. Two separately published f64 bundles can still disagree -- that identity lives in a claim's artifacts pins. CHAIN_INVARIANT is COMPUTED as IDENTITY minus {dtcld, nsplit, delt}, so a field already in IDENTITY is a chain invariant by default. It does NOT make the contract fail-closed against a new header field: IDENTITY is hand-written, so a field added to the G33P header and not to IDENTITY is invisible to this check and to the pairwise one alike. What the change removes is the per-chain omission, not the per-field one. It was first enumerated, on the argument that a chain has no axis to subtract; that argument was wrong -- dtcld IS the axis and nsplit/delt covary with it, exactly as the pairwise contract declares. |

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
  pins the total integration time — their **product** does. The pairwise identity
  cannot supply this for `refinement`, because both factors are declared to
  covary there; that is why the check lives here rather than being inherited.
  (`FINDING_comparison_identity_v1.md` originally claimed the pairwise contract
  fixed the horizon. It does for `precision_pair` and `variant`, where both
  factors are invariants, and NOT for `refinement` — corrected there.)

  **Neither of these two is novel**, and nor is most of the rest. Audited
  against the G33R path:

  | check | G33R already had it |
  |---|---|
  | record universe | `require_same_universe` |
  | algorithm | `require_same_universe` |
  | mode | `require_comparable` |
  | horizon `delt × nsplit` | `require_comparable` |
  | step distinctness / `> 1 distinct dtcld` | **no** — `require_orderable` exists but is **not reachable from `build()`**; it runs only in the report path, inside a `try/except` that deliberately tolerates a repeated step |
  | `schema`, `precision`, `source_precision`, `fixture`, `loops`, `ntile`, `tiles`, `rho_profile` | **no — G33P-only fields** |

  So four of the checks are a **parity port** and two are not. The G33P path had
  *no* cross-member checks at all, so the gap closed was real and total.

  **Two corrections, in opposite directions, both mine.** The first version of
  this finding called the function a new contract, which oversold it. The
  correction then called it "mostly a parity port", which undersold it by
  claiming step distinctness already existed on the bundle path — it does not.
  `require_orderable` is called once, in the report path, and wrapped so that a
  repeated step is *accepted*: "the N=1/N=3 policy control deliberately runs one
  step twice."

- **`require_probe_chain` is therefore STRICTER than G33R on one axis**, not at
  parity. A G33P analogue of the N=1/N=3 policy control — two members at one
  `dtcld`, run deliberately — would be **refused** here while its G33R equivalent
  is accepted with the order tables suppressed. That asymmetry is unintended and
  is recorded rather than argued away; whether the chain contract should refuse
  or degrade is an open question.
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
- **`CHAIN_INVARIANT` is now COMPUTED**, `IDENTITY − {dtcld, nsplit, delt}`, so a
  field already in `IDENTITY` is a chain invariant by default. This finding
  originally recorded it as an enumerated list and argued that a chain "has no
  single axis to subtract the way a pairwise comparison does". That argument was
  wrong: a refinement chain does have an axis — `dtcld` — and `nsplit` and `delt`
  are the same knob written differently, which is exactly the covariance the
  pairwise contract already declares.
- **This is not fail-closed against a NEW header field.** `IDENTITY` is itself a
  hand-written tuple, so a field added to the G33P header and not to `IDENTITY`
  is invisible to this check *and* to the pairwise comparison alike. Computing
  the set removes the **per-chain** omission — forgetting to list a field that
  `IDENTITY` already knows — and not the **per-field** one.
  `FINDING_comparison_identity_v1.md` already stated exactly this limit for the
  pairwise identity; the first version of this finding claimed the stronger
  property for the same mechanism, which was an overstatement.
