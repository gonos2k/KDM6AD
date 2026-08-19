# Review response: `main` at `7757abd`

The owner's additional review after PR #140 listed four new P0s, a
publication P0, an identity stop-gate, and four P1s. This records what each
became. It is a checklist, not a finding: the numbers it quotes belong to
the claims and bundles it points at.

The review's central sentence is what this branch answers:

> content-addressed 이름 ⇏ 기존 entry의 실제 내용 검증

## Closed

| Item | What it was |
|---|---|
| §3 P0-1 | the store verified writes and TRUSTED reads. An entry already at an address went to the compiler unexamined -- reproduced, it returned B under A's address. Symlink, non-regular file and digest mismatch all refuse now, before and after the compile |
| §4 P0-2 | `RunContract`, `expected_run` and the pinned `fixture_sha256` re-read the working tree while `sources[]` carried the compiled digest. `SourceSnapshot` joins the staged map and the source log; every fixture parameter comes from the bytes the compiler read, and tracked sources are held to their HEAD blob |
| §5 P0-3 | the four witnesses are compared, and `build_provenance` becomes an EXACT contract at v7 with a role table. Five forgeries measured CLEAN before it: six of seven source rows dropped, one path under two digests, a row nothing compiled, `compiler_f951_sha256` removed, an unknown key |
| §6 P0-PUBLISH | the producer's reuse check and the evidence chain held DIFFERENT rules -- reproduced on a real bundle, producer ACCEPTED and chain NOT-SELF-CONTAINED. One rule now, `rm.payload_state`, called by both |
| §7 P0-B/C | identity carried the checkout root and `TMPDIR`. Measured: the recipe id moved for a changed root, the content id for a changed TMPDIR. Paths are repo-relative and the normaliser tags `<TMP>`/`<REPO>` while keeping the digest-bearing basename |
| §8 (analyzer half) | an analyzer edited after the preflight, imported, and restored ran bytes neither check saw -- reproduced, `d86879e0` executed and `6bc1b9c8` was pinned. The digest is taken when the module executes, and `executed_analyzers` records it |
| §9 P1 | the ledger compared cell universes AFTER indexing across them: `KeyError: ('c', 2)` instead of its own refusal. The state stream was a second universe, never compared |
| §10 P1 | `\|R\| < ulp(W_0)` is a size indicator, not a closure certificate. The artifact carries a forward-error screening bound; the predicate is `is_sub_ulp_of_initial_inventory` and the closure verdict is `passes_roundoff_screening`. `basis_factor` is `null` with a reason when either residual is unresolved |
| §11 P1 | `--algo` chose what the build compiled while `--module` chose what the manifest pinned, defaulting to legacy. The module follows the algorithm; departing takes `--module-override` and is recorded |
| §12 P1 | a `paths:` filter stopped the workflow, so the ruleset's required contexts were never created and #140 needed an administrator merge. The decision moved into a `detect` job; the jobs are skipped rather than absent |

## Still open, deliberately

**§8's other half.** The review's preferred structure is a detached
snapshot that everything executes from. This branch closes the analyzer and
compiled-source windows without it, which is why that seam took eleven
corrections in this cycle -- each closed one state the previous
reproduction had not visited. The snapshot removes the class rather than
the instances, and analyzer subprocess isolation belongs with it.

**Full attestation coverage.** Requiring every analysis's seed module to be
attested is the obvious next clause. The re-production answers why it is
not enforced: the producer attests EIGHT modules while `analysis_seeds`
names TEN. The gap is the multi-run analyses, which do not reach their
module through the `_an` seam. Routing them through it is the prerequisite,
and it sits with the snapshot work.

## The controlled re-production

Every schema-affecting change landed in one re-production (§13 step 6).

```
ncmin-001   4394c51e… -> c931c28b…      37 pins
water-001   f5ded55d… -> 3859a797…      16 pins
```

Both are `refinement_experiment_v7` carrying a `g33_build_provenance_v1`
block, a role per source row, a repo-relative `fixture_path`, and
`executed_analyzers`. Every member's `output_sha256` is byte-identical
across the change, and **49 of 49 pinned figures reproduce, 0 moved** --
verified before a single pin was touched. §10 changed the water artifact's
shape, not its numbers.

## What the Codex stop-time review found in this cycle's own work

Eleven findings, every one reproduced before it was fixed, and most of them
in code written earlier in the same cycle. Three patterns are worth keeping:

* **A gate that cannot see must not answer "no".** Absent logs, a `HEAD^`
  base that missed a multi-commit push, a widened derivation refusing
  records that predate it -- each turned "could not check" into "checked
  and fine".
* **The attestation must be beyond the reach of what it attests.** A module
  attribute and a `sys.modules` registry were both forged in one line. No
  in-process location works; git HEAD is the only reference the running
  code cannot rewrite.
* **A production invariant is not a test-process invariant.** Refusing at
  import was right for a fresh producer process and killed pytest
  collection outright. The gate belongs where the claim is published.

## Post-rebase: what a public checkout said that this host could not

PR #141 was squash-merged mid-cycle, so the remaining work was rebased onto
the merged `main`. That changed the commit the bundles pin, and a bundle
pinning an unreachable commit is not evidence -- so the experiment was
re-produced against the rebased HEAD, member digests byte-identical, ten and
eight analyzer attestations with nothing unattested, and **49 of 49 pinned
figures reproduced before the pins moved**.

CI then failed fifteen tests that pass here. Two independent causes, and the
reproduction is the finding:

* **`host/**` is gitignored, so a throwaway `git worktree` IS a public
  checkout.** That is where the second defect became visible. The test's
  module stand-in falls back to the fixture when the private kernel is
  absent, so one path carried both `module` and `fixture` while `verify()`
  re-derives every role from the path and called them both `fixture`. The
  fake asserted what the verifier derives. It now derives them the same way,
  so the two cannot disagree by construction.

* **One rule, written out twice, drifts.** The attestation seam records an
  analyzer it could not attest whether or not this bundle dispatches to it;
  the manifest refuses declarations outside the dispatch set. Both were
  right; together they made a suite that imported `g33_number_transport`
  first publish a bundle its own validator rejected -- thirteen tests, and
  none when that module was not collected first. `dispatched_seeds()` is now
  the single authority both call.

A fourth pattern to keep beside the three above:

* **A skip is honest; a silent fallback is not.** Every other test that
  needs the private kernel is `skipif`-ed. The one that quietly substituted
  a different file instead changed the shape of what it was testing, and the
  difference only surfaced on a machine that had never seen `host/**`.

### The fix that hid what it fixed

Codex, on that commit: *the public-checkout fix disguises a missing private
kernel as compiled input.* It did. Naming `host/.../module_mp_kdm6.F` in the
fake's `sources` traded a VISIBLE CI failure for a SILENT contradiction --
on a public checkout that file is absent, its digest was a hash of its own
path, and the manifest pinned the fixture as its module while the provenance
claimed to have compiled the kernel. Measured: the two records named
different files, and validation was CLEAN.

That the fabrication survived is the finding. `build_provenance` states the
fixture and the compiled module TWICE -- at the top, and again in `sources`
as what the compiler read -- and nothing joined the two. All four mutations
validated CLEAN against a real published bundle. The same shape as
`dispatched_seeds`, one file later: **one fact written in two places drifts,
and the drift is where a forgery lives.**

The join for the module is `compiled_module_sha256`, not `module_path`. A
build reads the kernel and compiles a GENERATED overlay, so those two are
different files by design -- binding them refused all five published v7
bundles. That measurement came before enforcement and corrected the rule,
which is the discipline working rather than the discipline being followed:
37 bundles, 0 refused after the correction, and forgery of the overlay
digest, the fixture digest and the fixture path all refused on a real bundle.

The fake now names the overlay it actually wrote -- which is what a real
build compiles, since gfortran never opens the kernel -- so nothing has to
be invented on any checkout.

### The same root, a third time

A full run then failed two tests that no partial run reproduces. The
attestation record is a module-level dict living for the whole session, so
whichever test first touches an analyzer fixes its attestability for every
later one. With all eight seeds already imported, the producer attested
none, omitted `executed_analyzers`, and the validator refused the omission
even though `unattested_analyzers` named every seed the bundle dispatched
to. Refusing an honest confession is, again, a production invariant applied
to a process that is not the production one. Absence is legal now exactly
when the declaration covers the dispatched seeds -- partial declarations and
silence are still refused, and the field still bars decision eligibility.

Public-checkout worktree at the fix: 1850 passed, 240 skipped, 0 failed.

### The check I kept skipping

Twice in this cycle I tightened a validator, ran the module that TESTS the
validator, and committed -- while the modules that PRODUCE records for it
went unrun. Both times Codex found it, and both times the reproduction took
under two minutes. A rule and its fixtures are one change; running half of
it is not a partial check, it is no check.

A fifth pattern, then, beside the four above:

* **Strengthening a rule is a change to everything that satisfies it.** The
  blast radius of a validator edit is every producer of the thing validated,
  and it is knowable before committing -- `grep` for the field.

### Where the shape hardening stops, and why

Owner, mid-cycle: **this system is not built for deployment; scientific
demonstration is the centre.** That settles a question this cycle had
started to lose. The last several rounds chased malformed-input crashes
through every public reader, and each round found more, because the axis has
no bottom: any location in the document can hold the wrong shape and every
location is read somewhere.

What is scientifically load-bearing is narrower and sharper:

* **`validate()` must never crash.** It decides whether a bundle is
  admissible evidence, and a validator that raises is indistinguishable from
  a bundle nothing examined. The caller sees a crash either way, and the
  difference between "refused" and "never looked at" is the difference
  between evidence and no evidence. Measured: 2260 gate calls over every
  location in a real manifest to depth two, five crash sites, now none.

* **The other readers compute addresses for documents the gate has already
  accepted.** Their contract is at the boundary now -- a document
  `validate()` refuses turns a structural error into a refusal, while a
  document it ACCEPTS lets the exception through untouched, so a genuine
  defect still surfaces as itself rather than being swallowed. One rule, not
  a guard per site.

The exhaustive cross-product sweep is retired. It was finding shapes no
producer in this system emits, at the cost of the work the bundles exist
for. The gate test stays because the gate's answer is part of the evidence.

### Open, and why it is not closed here

Sweeping every nested block for the same defect found two more that accept
keys nobody declared: `kernel_geometry` and `identity`. Measured -- a
smuggled key validates CLEAN in both.

It is a lesser hole than the ones closed above: an undeclared key is inert,
where a nulled or emptied one erased a value something reads. And closing
it is a **schema bump**, because a stricter key set is a new tag and never a
new demand on history -- the one discipline this campaign has kept unbroken.
Both blocks carry their own versioned tags, so `identity` and
`kernel_geometry` would each move, every published bundle would answer for
the tag it was published under, and the current experiment would have to be
re-produced and its 49 figures re-verified before the pins could move again.

That is the next item, not a thing to slip into this one. Recorded with the
measurement so it is a decision rather than an oversight.

## Standing NO-GOs (unchanged)

Identity Phase B/C; real mixed-coastal MPI; the `G33-NCMIN-005` mediation
experiment; forcing VJP; C4 addendum, C5, release, default DA.
