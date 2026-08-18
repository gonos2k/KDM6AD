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

## Standing NO-GOs (unchanged)

Identity Phase B/C; real mixed-coastal MPI; the `G33-NCMIN-005` mediation
experiment; forcing VJP; C4 addendum, C5, release, default DA.
