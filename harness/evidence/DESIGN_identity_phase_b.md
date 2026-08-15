# Design: storing the layered ids (Identity Phase B)

Status: **design only — no implementation**. Phase B remains NO-GO until the
owner takes the re-production decision; this records the shape that decision
would build, so the prerequisites closed this cycle do not have to be
re-derived then. (Owner review of `main@db39209`, §7.)

## The self-reference trap (§7.1)

The ids are subtractive digests over the manifest. Writing them back as
top-level fields makes them their own hash input:

```text
I = H(M ∪ {I})        — unsatisfiable except by luck
```

The same applies one level down: an `analysis_id` written into its own
`analyses[]` entry is hashed by `analysis_id()`.

**Decision**: stored ids live inside the `identity` block, which the content
id already reduces to its schema tag — so the storage location is excluded
from every hash input *by the rule that exists*, not by a new exclusion:

```json
"identity": {
  "schema": "g33_layered_identity_v3",
  "role_graph": { ... },
  "analysis_seeds": { ... },
  "analysis_reach": { ... },
  "derived_ids": {
    "run_recipe_id": "…",
    "run_content_id": "…",
    "analyses": { "dual_ledger": "…" }
  }
}
```

Verification order, in the schema validator (fail-closed, like every gate):

```text
1. compute each id from the manifest (derived_ids plays no part — the
   identity block reduces to its tag before hashing)
2. compare against identity.derived_ids
3. any mismatch → the manifest is refused
```

The recompute-equality check is the whole point of storing them: a stored id
nobody recomputes is a decoration.

## Container schema vs run-identity schema (§7.2)

`run_recipe_id` currently hashes `schema: refinement_experiment_v3`. A
container-format bump — a new metadata field, an analysis sidecar — would move
every run id with no run byte changed: the same coupling as the commit
anchors, one field over.

**Decision**: the ids hash their own schema tags, not the container's:

```text
manifest container   refinement_experiment_vN   (excluded from ids)
run recipe           g33_run_recipe_v1          (hashed by run_recipe_id)
run content          g33_run_content_v1         (hashed by run_content_id)
analysis identity    g33_analysis_v1            (hashed by analysis_id)
```

These tags version the *canonicalization rules*, which is what
`g33_layered_identity_v2` already does for the block; splitting them per-id
lets one id's rules change without re-versioning the others. This is an id
SEMANTICS change → `g33_layered_identity_v3`, and both bundles re-produce
under it (the standing pattern: never migrate a live tag quietly).

## Execution isolation (§8)

Closed this cycle to its minimal-change form: analyzers import at dispatch
time, after every raw member is on disk and strict-parsed, and a lazy
`_an("…")` dispatch counts as a dependency edge in both AST derivations so the
recorded graph did not move. The full form for Phase B, if the owner wants the
structural guarantee rather than the ordering one:

```text
phase 1 (subprocess): build → run → strict-parse → freeze raw bundle
phase 2 (subprocess): read frozen bundle read-only → write derived artifacts
```

The ordering guarantee already prevents import-time side effects from
preceding the run; the subprocess split would additionally prevent *run-time*
analyzer state from leaking backward, which cannot happen today only because
the producer's control flow says so.

## Already closed this cycle (the other §7 prerequisites)

* set-valued list canonicalization in the id inputs (pins by path, members by
  `(nsplit, mode, file)`, build artifacts by file) — order-bearing lists
  (`runtime_argv`) deliberately left order-sensitive;
* the analysis coupling through the identity block (identity v2);
* the publish-time resolved-graph gate;
* the full-path pin table.

## What Phase B then is

1. bump to `g33_layered_identity_v3` with per-id schema tags;
2. producer writes `derived_ids`; validator recomputes and compares;
3. re-produce the two live bundles;
4. Phase C: claims bind `analysis_id` instead of bundle-directory digests, so
   a re-production that changes no analysis stops re-pointing every claim.

Steps 1–3 are mechanical once approved. The cost that makes this an owner
decision is unchanged: every stored id is a promise that the canonicalization
rules never change silently again.
