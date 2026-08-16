# Review response: `main` at `9049e04`

The owner's review after PR #137 listed seventeen items in a recommended
order (§13). This records what each became. It is a checklist, not a
finding: the numbers it quotes belong to the claims and bundles it points
at.

The review's central sentence is what this branch answers:

> a pinned fixture horizon plus a current-checkout `dtcldcr` is not
> historically self-contained geometry.

## Closed in this branch

| Order | Item | What it was |
|---|---|---|
| 1, 3 | the sub-cycle limit stops being ambient | `dtcldcr` was a module global read from the working tree's private kernel source, with a silent `120.0` fallback when the tree lacked it — so the same historical bundle could get different verdicts on two hosts. Reproduced: a member stepping 300 s at nsplit=1 is CLEAN at limit 120 and refused at 60, no bundle byte different. `expected_geometry()` takes the limit as a parameter and has no default to fall back to |
| 2 | `kernel_geometry` in the manifest | value, storage width, raw word, and the digest of the source it was read from. The producer REFUSES when that source is absent or ambiguous — a silent 120.0 is a number nobody measured, and the whole geometry contract rests on it — and the validator requires the word and the value to name one limit |
| 4, 5, 6 | `g33_expected_run_v1`, closed | every field was "compare if present": dropping algorithm, precision or rho_profile removed its own check, `levels` was never read, `window_seconds` was never held to the pinned `DT_BITS` (300.000001 named a horizon no fixture holds while deriving identical geometry), and mode/nsplits were absent so a mixed carry/rezero bundle passed. Seven gaps measured. The key set is exact, the raw `DT_BITS` word is the canonical horizon with the decimal required to be its **exact decode**, and mode/nsplits/fixture_sha256/source_precision joined the block |
| 7 | the four records of one invocation agree | `runtime_argv` ↔ `expected_run` ↔ member rows are tied at the document level (mode, rho_profile, the nsplit set); the chain adds the raw headers |
| 8 | the recipe id carries the request | `expected_run` and `kernel_geometry` are what was ASKED FOR, yet only the subtractive content id picked them up — measured: changing the declared horizon moved the content id alone. Both now enter `run_recipe_id`, which is an id-semantics change: `g33_layered_identity_v3` |
| 9 | multi-run binds the algorithm before publishing | the legs took fixture/horizon/tiles/nsplit/mode/rho but not the algorithm, so a `conservative` stream inside a legacy bundle was publishable and refused only later by the chain. And `qr_process_ledger` called `run()` directly, so the two streams its whole comparison rests on carried **no** member contract at all — both now go through one `gated_text` seam |
| 10 | fixture parsing is structured | `FixtureContractError(ValueError)` instead of `SystemExit`, so a malformed pinned fixture yields `FIXTURE-UNRESOLVED` rather than terminating the checker that found it; the producer translates at its own boundary |
| 11 | the loop count is the kernel's arithmetic | the quotient is formed at the member's width before `nint` sees it; dividing in Python's binary64 is a different function near a half-integer boundary |
| 12 | the run cache keys on the executable's bytes | keyed on the driver path, a rebuilt binary at the same path could be served a previous build's stdout inside one process |

### Measured before fixed

```
§4  same bundle, ambient limit 120 vs 60          CLEAN vs refused
§5  drop algorithm / precision / rho_profile      each check vanished
§5  levels 999 beside a K=4 fixture               CLEAN
§5  window_seconds 300.000001                     CLEAN
§5  members mixing carry and rezero               CLEAN
§6  declared horizon changed                      content id moved, recipe id did not
§7  ledger streams                                published under no contract
§10 malformed pinned fixture                      SystemExit out of the checker
```

## Schema v5, identity v3, and the controlled re-production

`kernel_geometry` and the closed `expected_run` are new required fields and
the recipe id changed semantics, so both arrive as versions rather than as
demands on history: `refinement_experiment_v5` and
`g33_layered_identity_v3`, with older bundles held to the contracts and id
rules they were published under. Both live bundles were re-produced;
**49 of 49 pinned figures verified byte-identical before the pins moved**.

```
ncmin-001   ff0be031… -> b97f36f9…      water-001   be3413b9… -> 0a7ca415…
```

The Codex stop-time review caught two things in this cycle's own work, both
reproduced and both fixed before the pins moved: `kernel_geometry` pinned
the LEGACY kernel source for every bundle, so a conservative one would have
recorded the digest of a module it never compiled (the build compiles
`module_mp_kdm6_cons.F` for that arm, `refine_build.sh:54-55`); and adding
the `algorithm` key to that block made it stricter while leaving the tag at
`kdm6_subcycle_v1` — a tag meaning two things, which is the one discipline
this campaign has kept unbroken. The tag is `kdm6_subcycle_v2`, v1 is held
to what v1 promised, and the bundles were re-produced under it.

## Deferred, with reasons

**Raw/analysis subprocess split (order 13) and Identity Phase B/C (order
14).** Unchanged and still NO-GO. This cycle removes the four reasons the
review gave for keeping it there — historical `dtcldcr` self-containment,
the closed expected-run schema, the recipe-ID binding, and multi-run
publish-time algorithm binding — so what remains before stored ids is the
subprocess isolation itself and the owner's re-production decision.

**Stage A real MPI (order 15), mediation `G33-NCMIN-005` (order 16), forcing
VJP (order 17).** Science stages, gated exactly as the review grades them.

## Standing NO-GOs (unchanged)

Identity Phase B/C; real mixed-coastal MPI; the `G33-NCMIN-005` mediation
experiment; forcing VJP; C4 addendum, C5, release, default DA.
