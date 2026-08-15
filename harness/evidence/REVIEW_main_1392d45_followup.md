# Review response: `main` at `1392d45`

The owner's review after PR #134 listed fifteen items in a recommended order
(§14). This records what each became. It is a checklist, not a finding: the
numbers it quotes belong to the claims and bundles it points at.

## Closed in this branch

| Order | Item | What it was |
|---|---|---|
| 1 | exact G33R window universe | `max(cols)==B` accepted `{1,3}` and `{0,1,2,3}`; `len(levels)==K` accepted `{-1,0,1,2}` and `{0,1,2,4}` — each a different domain wearing the right summary. The pin now requires exactly `1..B × 0..K-1`, the exactness G33P already had internally |
| 2 | G33R↔G33P bidirectional universe | `_agree` walked G33R's keys and looked each up on G33P, so G33P records with no G33R counterpart were never visited: `{1,3}` against `{1,2,3}` compared two columns and called three agreed. Exact key-set equality now precedes any value comparison |
| 3–4 | one decomposition per stream, in tile-ID order | coverage sorted segments by COLUMN RANGE and compared splits only by their last column, so split 1 could tile `(1..1)(2..3)` beside split 2's `(1..2)(3..3)`, and tile IDs could be spatially permuted — both reproduced, both now refused. `ncmin` is set by a tile's LAST column, so this is scientific content, not bookkeeping. `validated_run_identity` returns `ntile`/`tile_ranges`/`tile_sizes` |
| 5–6 | the same-run contract | a G33N leg declaring legacy/delt=100/rho=1.0 beside a window declaring conservative/delt=300/rho=2.0 passed every check — each protocol validated only inside itself. `_require_same_run` now compares every fact BOTH protocols record: algorithm, delt, dtcld (newly proven single per stream), ntile and the tile vector, and the rho/delz forcing VALUES per cell of every call, as f32 words. A window with no delt or no forcing refuses: a contract that cannot bind is absent, not satisfied |
| 7 | member semantic re-validation in the chain | the digest rows proved "these are the bytes the producer approved", nothing proved they pass TODAY'S contract — the two diverge exactly when a review cycle hardens the parser. `_member_contract_states` re-parses every primary member of every identity-carrying manifest with the current strict parsers and holds it to the full fixture-domain / same-run contract, (B, K) read from the repo fixture source. All 10 live members re-validate `matches` |
| 8 | `ran.levels` bound to the fixture | `want["levels"] = got["levels"]` checked the stream against itself. `_ran` now takes the fixture's K through the one strict reader; the block's shape is unchanged, so the live bundles stay valid |
| 9 | raw-arm runner role | the arm streams are run CONTENT carried by `run_content_id`, and the code that made them lived in an analysis seed cut from the recipe — so the recipe did not cover the code that produced its own content. Resolved by the review's preferred split: `g33_run_matrix` (run role, imported directly) owns the matrix; `g33_metric_trajectory` (analysis) never runs the driver; both chains read ONE collected matrix, making chain-independence structural |
| 10 | subprocess separation as a Phase-B precondition | `DESIGN_identity_phase_b.md` now lists the two-subprocess split as step 0 of the implementation, required before any stored id is called authoritative — not an optional hardening after it |
| 11 | duplicate rows refused | measured first: an exact duplicate pin row validated CLEAN and moved `run_recipe_id`. The validator refuses a repeated path/file in every set-valued block and within an analysis's `inputs`; `inputs` join the canonical sort and `analysis_id` canonicalises before hashing |

### Measured before fixed

Every P0 was reproduced before it was touched:

```
§4   cols {1,3} / {0,1,2,3}, levels {-1,0,1,2} / {0,1,2,4}   all ACCEPTED
§4.3 G33P carrying 2 records G33R never wrote                ACCEPTED
§5   split 1 (1..1)(2..3) beside split 2 (1..2)(3..3)        ACCEPTED
§5   tile 1 covering 2..3 while tile 2 covers 1..1           ACCEPTED
§6   conservative/delt=300/rho=2.0 window beside a
     legacy/delt=100/rho=1.0 G33N leg                        ACCEPTED
§10  duplicated pin row                                      validate() CLEAN,
                                                             recipe id MOVED
```

And after: all 151 published G33N streams re-parse unchanged, all 10
published members of both live bundles pass the full same-run contract, and
the chain reports `matches` for every member-contract row.

## No re-production this cycle — and why that is the right answer

Every change is to the CONTRACT, not to what a run records: the `ran` block's
shape, the member bytes, and the analysis artifacts are all unchanged, and
the published bundles pass every new check as-is (they were produced by the
driver whose behaviour the contract describes). The role graph did gain
`g33_run_matrix`, but a manifest is validated against the graph it RECORDS
and the code it PINS — both from its own production — so the live bundles
remain internally consistent, and the next production records the new graph.
Re-producing bundles that pass the strengthened contract unchanged would
re-point 49 claim pins to prove nothing.

## Deferred, with reasons

**Phase-B ID storage implementation (order 12).** The review's own 판정:
구현 NO-GO until the §4–6 hardening and the role cleanup land. They land in
this branch; the implementation remains the owner's re-production decision,
with the design (now including the subprocess precondition) written down.

**The water forward-error certificate (§11).** The review is right that
`|R_W| < ulp(W_initial)` is a scale diagnostic, not a γₙ certificate, and the
claim's own text stays on the right side of that line: column 1 is bound as a
measured residual ratio (0.2025 initial-inventory ULP) with a predicate,
never as "exact conservation proven". The path-based bound
`γₙ(|W_i|+|W_f|+|P|)` belongs with the closeout, beside the process ledger's
existing γₙ machinery.

**The two-dot-product closure bound (§12).** The single combined count is
conservative in the direction that cannot certify a false gap (it can only
overstate the bound), and the measured gap sits orders below either form. The
split bound `B_actual + B_tel + u(|A|+|T|)` is the right closeout shape;
adopting it re-produces the ledger artifacts, so it is batched with the next
re-production rather than forcing one alone.

**Stage A real MPI (order 13), mediation `G33-NCMIN-005` (order 14), forcing
VJP (order 15).** Science stages, out of scope for a hardening branch, gated
exactly as the review grades them.

## Standing NO-GOs (unchanged)

Identity Phase B/C (designed, with the subprocess precondition recorded; not
implemented); real mixed-coastal MPI; the `G33-NCMIN-005` mediation
experiment; forcing VJP; C4 addendum, C5, release, default DA.
