# The evidence chain reaches the document and stops there

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status |
|---|---|
| `G33-CHAIN-001` | **active** |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner §9.2. Every claim pins the digest of the **finding** that carries it, and
`test_g33_claims` fails when that digest drifts, so a claim cannot silently come
to cite different prose. Nothing pins the **run**. The numbers inside a finding
can outlive the bundle that produced them with no signal anywhere.

## The three links, measured

`harness/g33_evidence_chain.py` walks them rather than asserting them:

| link | pinned? | checked? | state |
|---|---|---|---|
| claim → finding | yes | yes, `test_g33_claims` | cannot drift |
| claim → run | **no** | — | **0 of 29 claims** |
| bundle → finding | yes | **no** | 5 pins, **3 divergent** |

Only **2 of 29** claims cite a finding that any published bundle names at all.
The other 27 are backed by runs that were never published as bundles — they were
made ad hoc, and the producers only publish for refinement chains.

## The bundle → finding pin is a snapshot, and that is correct

Three of the five bundle pins no longer match the finding they name. The
tempting reading is rot. It is not:

A published bundle is **content-addressed and immutable** — `g33_refine_experiment`
addresses it by its manifest identity digest and reuses an existing one rather
than rebuilding. So the finding digest recorded inside it **can never be updated**.
Any later revision — a correction, or the claim-status stamper writing its own
block — must diverge from it permanently.

That pin therefore means *"the finding as it read when this run was published"*,
which is a legitimate historical record. Treating divergence as failure would
break the build on every correction, and would make the claim-status stamper —
which exists to stop findings drifting — the thing that breaks it.

The real defect is narrower: **nothing surfaced the divergence**, so a reviewer
could not ask the question that matters, which is whether the revision changed
the prose or changed the numbers. The tool now reports it and explicitly does not
fail on it.

## What is pinned now

`artifacts:` on a claim pins the run. `G33-TURNOVER-002` carries the first two:

```
    artifacts:
      - kdm6ad-g33m-refine/full-legacy-dtcld/manifest.json: 86131a0749522295
      - kdm6ad-g33m-refine/fine-legacy-dtcld/manifest.json: 7d7da60204361267
```

A manifest records every member's `output_sha256`, so the tool follows that link
and verifies the members too — **13 raw streams reached transitively from two
pinned digests**. A pin that stopped at the manifest would prove only that a JSON
file had not changed while the outputs it describes could be anything; the test
`test_pinning_the_manifest_reaches_the_RAW_STREAMS_through_it` tampers a stream
whose manifest still matches and requires `--check` to fail.

## Limits

- **27 of 29 claims remain unpinned**, and this does not fix that. Pinning them
  would mean inventing a link that was never established — the runs behind most
  claims were not published. The fix is for the producers to publish, and for new
  claims to pin at the time they are written; the tool now measures the gap so it
  is visible rather than assumed closed.
- **Absent is not failure.** Bundles live outside the repo and are absent in CI,
  so an unavailable artifact reports `unavailable`. This is a local-only check by
  construction — the same posture as the Fortran leg. On a host with no bundles
  it verifies the parse and nothing else.
- **A pin is an identity, not a validation.** It says the bytes are the ones the
  claim was written against. It does not say the run was correct, that the
  analysis was right, or that the finding reads the numbers correctly.
- The claim-status stamper and this tool disagree by design about what a stale
  digest means: for `claim → finding` it is an error to be re-pinned, for
  `bundle → finding` it is history to be reported. Both directions are pinned
  with the same primitive and that difference is deliberate.
