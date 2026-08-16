# Review response: `main` at `8f73f05`

The owner's review after PR #136 listed fifteen items in a recommended order
(§14). This records what each became. It is a checklist, not a finding: the
numbers it quotes belong to the claims and bundles it points at.

The review's central sentence is the one this branch answers:

> two protocols agreeing on a fact does not make that fact the requested
> experiment's.

## Closed in this branch

| Order | Item | What it was |
|---|---|---|
| 1–2 | the fixture's HORIZON, and one owner for the geometry rule | `DT_BITS` is a fixture parameter like B and K — the driver derives every member's step from it — and nothing checked it: a member stepping 20 s at nsplit=1 satisfied every existing check while integrating 20 s of a 300 s fixture (reproduced). The producer reads it from the fixture source, the chain from the fixture BLOB the bundle pins, through one reader. `expected_geometry()` is now the single place the kernel's arithmetic lives: `delt = f32(DT_BITS)/nsplit`, `loops = max(nint(delt/dtcldcr),1)`, `dtcld = delt/loops` (or `delt` at or below `dtcldcr`), at the build's width, with `dtcldcr` read from the frozen source |
| 3 | the REQUESTED decomposition | the parser proved the tile vector coherent, never that it was the one asked for — and `ncmin` is a scalar set by a tile's LAST column, so an unrequested tiling is a different operator. In the density experiment that is a confounder, not bookkeeping. Primary members and density arms request `(B,)`; the ncmin decompositions request their own. The arm's `ran` block records `ntile`/`tile_sizes`/`tile_ranges`, the schema requires them, and the chain compares the decomposition as a VALUE — `(1,2)` and `(2,1)` are two operators with one `ntile` |
| 4 | the bundle declares its experiment | the algorithm lived only in member rows, so the document said what each member ran and never what the bundle was FOR. Manifest gains top-level `algorithm` and an `expected_run` block; the validator cross-checks them against the pinned fixture and every member row, and RECOMPUTES each member's delt/loops/dtcld from the horizon rather than copying what the stream said |
| 5 | the closeout reads the request it recorded | multi-run inputs were re-validated from a filename regex that read nsplit/mode/rho and skipped `tiles-2-1`, so a manifest recording tiles 2,1 beside a stream running tiles 3 passed while the derived JSON was labelled (2,1). The chain now reads the typed `runtime_argv` — the command line the producer issued, which IS the request — and an entry without one is refused, not skipped |
| 6 | the current profile covers non-instrumented members | the producer applies it either way; the chain gated it on `instrumented`, so plain bundles were never re-validated for exact B/K, INITIAL, forcing, time geometry or horizon |
| 7 | the surface stage has a VOCABULARY | requiring the same field set in every column let a stream whose only surface field was something no analysis reads pass, while a surface closure got `None` and dropped its row. The exact set is stated with the protocol — measured across all 26751 published surface cells — and a test compares it against the emitter's own `SURFACE_FIELDS` rather than importing them |
| 8 | the withdrawn product inverse is gone | the profile still carried `loops*dtcld == delt` at fixed-six, the exact inverse the transport parser had abandoned for refusing VALID streams (f32 `delt=400, L=3` → 399.999984). Both callers read `expected_geometry` in the quotient direction now |
| 9 | one validator, every arm | it picked the G33P reader for f64 alone, so a probe stream was read as G33R and then held to a contract demanding G33P metadata it had never parsed — a direct call would refuse a valid member, and the primary path worked only because `members()` kept its own G33R/G33P/`_agree` sequence. That sequence moved inside; the callers now call the validator and nothing else |
| 10 | adversarial sweep | every counterexample class the review names refuses on live bytes (below), and all 21 published members and raw streams of both bundles report `matches` |

### Measured before fixed

```
§4  a member stepping 20 s where the fixture defines 300 s   ACCEPTED
§5  a (1,2) stream against a caller requesting (3,)          ACCEPTED
§6  a multi-run request read from the filename               tiles never read
§7  a surface row carrying no analysable quantity            ACCEPTED
§8  f32 delt=400, L=3 through the product inverse            FALSE REFUSAL
§9  validate_member_stream(arm="probe")                      refuses a valid member
§10 non-instrumented members in the chain                    profile never re-applied
```

And after, on the re-produced bundles:

```
wrong horizon (60 -> 300 s)          refused
wrong decomposition request          refused
wrong algorithm request              refused
member delt not the fixture's        refused (document level)
expected_run horizon lie             refused (every member row)
expected_run tiles != columns        refused
top-level algorithm absent           refused
arm ran without its decomposition    refused
```

## Schema v4, and the controlled re-production

The contract needed new required fields, so it arrives as
`refinement_experiment_v4` rather than as a demand on history: requiring
`algorithm`, `expected_run` and `ran.tile_sizes` unconditionally failed every
historical bundle — including the v2 ones whose instrumented builds are not
re-producible on demand — which is a blocker with no resolution rather than a
check. The validator applies the new rules at or above v4; the chain compares
an arm's decomposition only for schemas that promise one; all six published
bundles validate under the contract they were published against.

The two live bundles were re-produced under v4, as the review's closing note
requires. Every figure the registry pins was verified against the new
artifacts **before** the pins moved: 49 of 49 byte-identical, 0 moved.

```
ncmin-001   937df8b3… -> ff0be031…   (manifest 5eb82f01… -> b6453e2b…)
water-001   e9371952… -> be3413b9…   (manifest 72286e09… -> 87040bce…)
```

## Deferred, with reasons

**Raw/analysis subprocess split (order 11) and Identity Phase B/C (order
12).** Unchanged: the split is step 0 of Phase B in
`DESIGN_identity_phase_b.md`, and Phase B remains the owner's re-production
decision. This cycle removes the reason the review gave for keeping it NO-GO
— the expected-run contract it warned would force another schema bump is now
in v4, before any id is stored.

**Stage A real MPI (order 13), mediation `G33-NCMIN-005` (order 14), forcing
VJP (order 15).** Science stages, gated exactly as the review grades them.
The review's §13 runtime record for Stage A — per-column rank/tile/xland and
the selected scalar `ncmin` — is the right shape and belongs with that
experiment's instrumentation, not ahead of it.

## Standing NO-GOs (unchanged)

Identity Phase B/C; real mixed-coastal MPI; the `G33-NCMIN-005` mediation
experiment; forcing VJP; C4 addendum, C5, release, default DA.
