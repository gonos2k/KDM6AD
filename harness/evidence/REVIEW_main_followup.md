# Review response: `main` at `4274da2`

The owner's review of `main` after PR #130 listed fourteen items in priority
order. This records what each one became. It is a checklist, not a finding:
nothing here is a measurement, and the numbers it quotes belong to the claims
and bundles it points at.

## Closed in this branch

| # | Item | What it was |
|---|---|---|
| 1 | out-of-bracket records fail-closed | the unknown-family refusals sat AFTER `if cur is None: continue`, so they only ever saw records inside a call |
| 2 | checked-only payload domain | grammar and width were checked and the bytes never decoded, so a NaN f64 and a `u8` of `FF` both parsed |
| 3 | the f64 window denominator | `window_inventories` read G33R only; an f64 build emits G33P, so it returned `{}` and `defect_magnitude` published nulls |
| 4 | the mass-weighted closure | recorded unweighted only, while the claim's headline is the weighted pair |
| 5 | the arm's run identity | four argv strings of which the schema compared two, and none against the stream |
| 6 | the storage class | decided by matching `real(...,4)`, which cannot see `real(expr, kind=4)` |
| 7 | the IEEE format | the header declared a width where the reader assumed a format |
| 8 | the identity role graph | ids were a function of the manifest AND of whichever checkout computed them |
| 9 | the authority YAML | the drift guard covered one field of eleven |
| 10 | packaging and anchors | payloads checked with a symlink-following test; any local ref satisfied reachability |
| 11 | `causal_attribution_valid` | not merely misnamed: a duplicate of `prediction_holds` |

### Measured, not argued

Each P0 was reproduced before it was fixed, on a real f64 build of the pinned
legacy module (`refine_build.sh --f64 --nflux`, owner's host — the reference
Fortran is gitignored and absent from CI).

```
1  four out-of-bracket mutations -> four silent acceptances, 12 calls either way
   archive scan: 55 streams, 6,265,378 records in the namespace, 0 out of bracket
2  G33FOP ... f64 7FF8000000000000 (NaN)  -> accepted
   G33FOP ... u8 FF                       -> accepted
3  published f64 bundle: 46 null fields per member x 9 members = 414
   after: 12 window keys at f64, the same set as f32
7  gfortran reports (2, 24, 128) at f32 and (2, 53, 1024) at f64
10 169 payload files across the archive, 0 symlinks; all pinned commits on a remote
11 prediction_holds == causal_attribution_valid in every published partition
```

Items 9 and 11 were each expected to be a rename or a cross-check and turned
out to be live defects. Comparing the whole registry against PyYAML found
`grade` and `scope` were never read at all, and that `evidence` took only the
key line — so `G33-TURNOVER-002` cites two findings and the chain followed one,
while the stamper, reading the same file, followed both.

## Bundles re-produced

Two, because the analyzers moved under them:

* `kdm6ad-g33m-migrate/ncmin-001` → `dada2bac…`. 27 of 29 pinned figures
  reproduce EXACTLY; the two that do not are precisely the renamed field.
* `kdm6ad-g33m-f64/water-001` → `1387ae06…`. Nine members, h = 100 s down to
  0.39 s. The bundle produced before the window fix is defective (414 nulls)
  and was moved out of the evidence namespace rather than deleted.

## Claims

`G33-ENTHALPY-001` and `G33-WATER-CONS-002` are **pinned**, on the f64 sweep
their blockers asked for. Every figure reproduces exactly, including the three
enthalpy residuals the old blocker said the nearest f32 field disagreed with —
the disagreement was the precision, not the claim.

`G33-WATER-CONS-002` column 1 binds a **bound**, not a value: `W_initial` there
is 0.4930884 kg/m2 whose ULP is 5.55e-17, so the published −4.4e-17 was 0.79
ULP and today's +1.1e-17 is 0.20 ULP. Both say the sum closes below the
representability of its own terms, and the sign and last digits of a sub-ULP
residual are summation order rather than a measurement.

`G33-WATER-ORDER-002` is **reclassified**, from `needs-f64` to
`needs-derived-field`. Running the sweep is what showed the blocker named the
wrong obstacle: the sweep now exists and is pinned by its siblings, and the
figure is a spread ACROSS members while every analysis in the bundle is per
member. The remedy is a bundle-level water-endpoint analysis, which re-produces
the archive — an owner decision, not a run.

## What a stop-time review found after all eleven were "closed"

Three fail-open paths, all in the identity work of item 8, and the first is the
defect this repository has a name for.

**The block was added to the producer and required by nothing.**
`rm.validate` never asked for `identity`, so a v3 manifest could omit it and
validate clean — and `_graph()` then fell back to the reading checkout's role
graph and computed ids anyway. The block exists to remove exactly that
coupling; omitting it restored it in silence. Required from v3 now, and the
derivation RAISES rather than falling back.

**The reach map was built from the wrong vocabulary.** It came from the
producer's two dispatch registries, and `metric_trajectory` is in neither — it
is written by `_driver_analyses` directly, and it is in every instrumented
as-is bundle. So its `analysis_id` fell back to the reader's imports while
every other analysis in the same bundle was recorded. The test that should have
caught this asserted the same two registries, so it agreed with the gap.

**Nothing asked.** `identity_is_self_contained` existed and no gate called it,
so a bundle whose ids follow whichever checkout reads them looked exactly like
one whose ids do not — and that difference IS the Phase B prerequisite. The
chain now carries an `identity` row per bundle.

The schema check refused the ncmin bundle produced an hour before it, on
exactly the `metric_trajectory` gap. It was re-produced. Chain after: 1488
`matches`, 15 `identity-predates-block` (the pre-v3 published bundles, reported
and blocking only a closeout), 6 `modules-unpinned` (pre-existing).

## Not closed, and why

**12. Stage A real MPI one-call gate — not started.** Every ncmin figure comes
from a three-column synthetic fixture called as one tile by a sequential
driver. The gate needs real ranks, haloes and a real coastal `xland`: a host
campaign, not a harness change.

**13. `G33-NCMIN-005` mediation experiment — not started.** It needs one arm
per link of the chain, each holding that link at the local-oracle value. The
claim records the experiment; nothing here runs it.

**14. Forcing VJP — not implemented.** It is the adjoint form of the same
question and is downstream of a corrected forward contract.

`C4 addendum`, `C5`, release and default-DA promotion stay NO-GO for the
reasons already recorded against them.

## Two judgements worth naming

The review's §9 asks for `storage_class` as a fourth tuple element on every
binding. It is declared for the two that need it and inferred for the rest —
but the inference is now the ABSENCE of a kind-conversion construct rather than
the presence of a pattern, and an expression carrying one that is not declared
is refused. That makes the 200-odd ordinary bindings need no ceremony while the
next `real(expr, kind=4)` fails loudly instead of silently.

The review's §13 asks for `yaml.safe_load` as the single authority reader. Not
taken: it would stop the evidence chain working where the harness deliberately
has no third-party dependency, and it would leave one parser and no
cross-check. What replaces the risk is the pair of properties that matter — the
two readers must agree on every field of every claim, and the hand reader must
REFUSE the YAML it does not implement. Both are now tested, and both found
defects the single-parser version would have kept.
