# The analyzer is recovered, not compared

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-CHAIN-003` | **active** | conditional-confirmed | Bundles published BEFORE this pin existed carry only analyzer_sha256 and keep the report-only treatment, now NAMED `legacy-*` so a weak verdict cannot be read as a strong one; they cannot be retrofitted without re-publishing the artifacts the claims cite. The blob must be reachable in the checking clone -- a shallow clone reports UNRESOLVABLE, which fails by design, so the checker needs the history and not only the worktree. The pin is taken from HEAD at publish time and is only as good as the producer's dirty-tree refusal. The executable digest, the build script, the compiled overlay and a 7-file private reference source set ARE recorded in build_provenance -- verified on a fresh build -- but cannot be RE-DERIVED by the chain, because the driver binary is a build artifact and is not published in the bundle. Bundles published before these fields existed stop at the members, which the report shows rather than hides. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner §16-6. A claim now reaches the commit that produced its numbers:

```
claim
  → finding sha256                    (full, in CLAIMS.yaml)
  → experiment manifest sha256        (full, in CLAIMS.yaml artifacts)
  → raw primary member sha256         (manifest members[])
  → raw density-arm stream sha256     (manifest analyses[], analysis="arm_stream")
  → analysis JSON sha256              (manifest analyses[])
  → analyzer commit + git blob sha    (manifest analyses[])
  → PARSER commit + git blob sha      (manifest member_parsers[])
  → every producer module, likewise   (manifest producer_modules[])
  → executable + build provenance     (manifest build_provenance)
  → private reference source sha set  (manifest module_sha256 / fixture_sha256)
```

## The link that did not hold

The manifest recorded `analyzer` (a path) and `analyzer_sha256` (the file's
content digest at publish time). The checker compared that digest against **the
file in today's working tree**.

That comparison can only ever answer *"is it still the same?"* — never *"what did
this bundle run?"*. So an analyzer that legitimately moved on took the answer
with it, which is exactly why the check **reported** `ANALYZER-CHANGED` and
never failed. A reported non-failure on every bundle older than its analyzer is
not a chain link; it is a note.

Pinning the **git blob SHA at a named commit** makes the question resolvable
instead of comparable:

```
git rev-parse <analyzer_commit>:<analyzer> → the exact bytes, whatever HEAD holds
```

| state | meaning | verdict |
|---|---|---|
| `matches` | the pin resolves and agrees | pass |
| `ANALYZER-BLOB-MISMATCH` | the commit does not hold that blob | **fail** |
| `ANALYZER-UNRESOLVABLE` | commit rewritten, path gone, or a wrong pin | **fail** |
| `analyzer-unpinned` | the entry names no analyzer at all | reported |
| `legacy-analyzer-changed` | content-digest-only bundle, file moved on | reported |
| `legacy-analyzer-absent` | content-digest-only bundle, file gone | reported |

Legacy bundles keep the report-only treatment **and are named as legacy**, so a
weak verdict can no longer be mistaken for a strong one. A bundle that pinned a
commit and blob has no such excuse.

Proved by construction rather than by inspection: the test that a resolvable pin
passes deliberately sets `analyzer_sha256` to `0`×64. It still passes — because
the working-tree digest is no longer what is being asked.

## The parser is not a lesser link

`member_parsers[]` recorded a path and a content digest — checkable against
today's working tree and nothing else, the same defect §16-6 fixed one layer up
(owner P0-2). An analysis is only as good as the stream its parser admitted: a
wrong parser lets a truncated, duplicated or mis-schema'd member through before
any analyzer sees it. Parsers now carry `commit` and `blob_sha`, and so does
every module in `PRODUCER_MODULES` — so the chain does not stop at the links a
reader happens to ask about.

## A manifest that will not parse is corruption, not absence

`members_of()` returned an empty child list when the manifest could not be
read, which reads as an artifact with nothing to check — indistinguishable from
a clean one, even though its own digest matched (owner P0-5). Four states are
distinguished now:

| manifest | state |
|---|---|
| not JSON, or unreadable | `MANIFEST-UNREADABLE` |
| top level is not an object | `MANIFEST-SCHEMA-MISMATCH` |
| no `members` key at all | `MANIFEST-MISSING-MEMBERS` |
| `members: []` | passes — a bundle may legitimately publish none |

All three failures fail `--check`.

## An entry that pinned nothing used to vanish

`if an.get("analyzer") and an.get("analyzer_sha256"):` — an analysis with
neither fell through and produced **no row at all**, so a bundle that pinned
nothing looked exactly like one that checked out. It is now `analyzer-unpinned`
and appears in the report.

## Authoritative pins are the whole digest

All **45** pins in `CLAIMS.yaml` — 43 findings and 2 experiment manifests — are
now full 64-hex sha256. A 16-hex prefix is 64 bits; it is a display convenience,
not an authority (owner §16-6). Truncation survives only where it is genuinely
display: `g33_abc_noninvasiveness`'s PASS line, and the `[:12]` in this
checker's failure messages.

The widening recomputed every digest **from the file it names** and refused on
disagreement — a prefix cannot be extended, only re-derived. `g33_claim_header
--repin` now does this, because the by-hand version was a regex over the
digest's own width and matched nothing the moment the pins widened.

## Limits

- **The pin is now BOUND to the bytes that ran — it was not.** The first
  version of this finding said "the producer refuses a dirty tree, so
  `HEAD:path` is the bytes that ran". **That refusal did not exist.** The
  producer only *recorded* `tree_dirty`; an uncommitted edit to an analyzer
  therefore RAN, the manifest pinned the committed blob, and the checker — which
  resolves that blob — passed (owner P0-1). The chain verified a file nobody had
  executed.

  `require_pinned_producer()` closes it before a bundle is built: for every
  module whose bytes decide what the bundle contains,
  `git hash-object <working file>` must equal `git rev-parse HEAD:<path>`. It
  compares the EXECUTED BYTES rather than overall tree cleanliness, so an
  unrelated dirty file does not block a run while an edited analyzer does. It
  fired on its own uncommitted edit the first time it ran.
- **The blob must be reachable in the checking clone.** A shallow clone, or one
  that has not fetched the pinned commit, reports `ANALYZER-UNRESOLVABLE` — a
  failure. That is deliberate: "I cannot check this" must not read as "checked".
  It does mean the checker requires the history, not just the worktree.
- **Bundles predating the pin cannot be retrofitted.** Their `analyzer_sha256`
  is all that exists, so they stay `legacy-*`. Re-pinning them would require
  re-publishing, which would change the artifacts the claims cite.
- **The executable and the private source set ARE pinned — but cannot be
  re-verified.** An earlier draft of this finding called them a missing link;
  that was wrong. `build_provenance` records `executable_sha256`,
  `build_script_sha256`, `compiled_module_sha256` and a `sources[]` set of 7
  files each with its own digest — including the gitignored
  `host/KIM-meso_v1.0/**` reference sources, which `repo_commit` cannot see.
  Verified on a fresh build, not read off the code.

  What is genuinely open is CHECKING them: the driver binary is a build
  artifact and is not published inside the bundle, so its digest *identifies*
  the executable without letting the chain re-derive it. Closing that means
  either publishing the binary or rebuilding bit-identically from the pinned
  sources — the second is the real test and is not run here.
- **Older bundles predate these fields.** `full-legacy-dtcld` (repo_commit
  29c5119) has no `executable_sha256` and no `analyses[]` at all, so for it the
  chain stops at the members. That is visible in the report rather than
  papered over.
