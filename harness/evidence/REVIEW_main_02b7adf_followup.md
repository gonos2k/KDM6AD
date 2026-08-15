# Review response: `main` at `02b7adf`

The owner's review after PR #131/#132 listed seventeen items in a recommended
order. This records what each became. It is a checklist, not a finding: the
numbers it quotes belong to the claims and bundles it points at.

## Closed in this branch

| Order | Item | What it was |
|---|---|---|
| 1–3 | `run_content_id` decoupled from the identity block; **identity v2**; producer-path regression | an analysis-only change that regenerated the block moved the run's content id — measured on the real f64 manifest, both mutations |
| 4 | `graph_violations` as a publish-time hard gate | the resolved check ran only after publication, in the chain |
| 5 | canonical full-path pin table | two files pinned in two blocks each, stem-keyed last-wins, divergent duplicates passing `validate()` clean |
| 6 | one strict identity reader | the chain's regex reader reported `matches` on streams `nt.calls` refuses — measured |
| 7 | coverage anchored at column 1, congruent across splits | a split covering 2..3 (column 1 missing) parsed clean |
| 8 | water ULP predicate | the binding admitted **2.16 ULP** against a "below one ULP" sentence; the artifact now computes the ratio and the verdict, and the `TOLERATED` registry is empty again |
| 9 | water measurement/acceptance/basis split | column 2's residual is measured (5.8e8 ULP of its inventory) and no longer called "closed"; every figure states the operator basis |
| 10* | cross-variant coverage | see below — bindings and blockers corrected; the comparator itself deferred |
| 11* | textual coverage | the three concrete gaps closed with bindings and a declared `unbound:`; the facts schema deferred |
| 13† | weighted closure | γₙ forward-error bound published in the artifact; weight-field equality checked raw |
| 14 | both bundles re-produced under v2 | 48 pinned figures reproduce, 0 moved |

\* partially — the architecture halves are in "Deferred" below.
† review §14; the order-13 storage item is in "Deferred".

Also §11 (BASIS-002): the unit fact — the physical column number is
ρ_d·Δz·n_r, forced by `nr` being per kg of dry air — is now its own source
claim (`G33-BASIS-006`, confirmed), and BASIS-002 holds open exactly what is
genuinely a decision: legacy compatibility and default promotion.

### Measured before fixed

Every P0 was reproduced before it was touched:

```
§3  reach entry grown by one module        -> run_content_id MOVED
§4  producer calls graph_violations        -> False
§5  divergent duplicate pin                -> validate() == []
§6  stream nt.calls REFUSES                -> _arm_ran_state == "matches"
§7  split covering 2..3, col 1 missing     -> ACCEPTED
§8  tolerance 1.2e-16 on W_initial          = 2.16 ULP vs "< 1 ULP"
```

And two gates built earlier in this campaign each caught a defect *introduced
while writing this branch*: the whole-registry reader-agreement test refused an
unfolded two-line scope, and the publish gate's `validate` contract caught the
pin resolver's refusal escaping as an exception.

## Cross-variant and f32 coverage (§12)

* `G33-ICE-CAP-001`: the six published figures (39/108, 8.63e-3, 23/147,
  2.70e-11) were in the pinned artifact all along under `by_chain.*` — bound,
  exact.
* `G33-WATER-CONS-002`: the f32 halves (6.8% / 17.1%) bind from the f32
  instrumented bundle (`mstepi-001`), pinned as a second artifact.
* `G33-ENTHALPY-001`: "identical in legacy and conservative" is now a declared
  `unbound:` entry — the equality spans two runs and the archive's analysis
  vocabulary is per-bundle.
* `G33-VARIANT-F64-001`: blocker reclassified `no-figure` →
  `needs-run-variant`; the old kind contradicted the claim's own text.

## Deferred, with reasons

**The structured `facts` claim schema (§13).** The concrete gaps the review
found are closed above through the existing mechanisms — bindings where the
artifact carries the figure, `unbound:` where it cannot. The schema itself
replaces the registry's whole claim format and re-touches every entry; that is
an owner decision about the registry's shape, not a fix this branch can carry
incidentally. The failure mode it addresses — an author omitting `unbound:` —
is real and remains; the review response says so rather than hiding it.

**The single `AnalysisSpec` registry (§16).** Agreed in direction — the
repeated "in one registry, not the other" defects are the evidence. Deferred
because collapsing seven registries and the AST-based `_analyzer_pin`
derivation into one dataclass touches the producer, the manifest vocabulary,
the identity derivation and their tests at once, and this branch already
changes the identity semantics; two semantic migrations in one PR is how
neither gets reviewed properly.

**`git ls-remote` anchor proof (§17.1).** The current trusted-ref check can be
satisfied by a stale remote-tracking ref or an unpushed local tag; real. But a
network call inside the evidence chain makes `--check` nondeterministic and
unusable offline. The honest shape is a separate closeout-only step that
records `remote URL + ref + observed SHA` in the closeout record; left for the
closeout design.

**IEEE bit sentinels (§17.2).** The PROTOCOL header carries
radix/digits/maxexponent, which pins the value model; the byte layout is still
assumed. Adding `1.0f32 → 3F800000` sentinels is cheap but changes the header
shape again, invalidating the streams produced this cycle; batched for the next
protocol bump.

**Explicit storage-class constructors (§15).** The declared-override table with
fail-closed conversion detection covers every binding in the table today; the
gap is `real(kind=real32) :: tmp` referenced as bare `tmp`, which carries no
conversion token. No such binding exists, and adding one now requires a
declaration or it is refused — the risk is bounded to a reviewer approving a
wrong declaration. The constructor form remains the right long-term shape.

## One deliberate deviation

**`run_content_id` stays subtractive** (§3 proposes an allow-list projection).
The essential content of the review's fix is applied — the identity block
reduces to its schema tag, and the run-role information reaches the id through
`_by_role`'s filtered pins. The shape deviates because an enumerated projection
silently *drops* any new manifest field from the id until someone remembers to
add it — fail-open in the other direction. Subtraction moves the id on an
unclassified new field, which is the fail-closed default everything else here
follows; the exclusions are enumerated and each carries its measurement.

## Standing NO-GOs (unchanged)

Identity Phase B/C (ids still derived, not stored — the coupling prerequisite
is now closed, the re-production decision is the owner's); real mixed-coastal
MPI; the `G33-NCMIN-005` mediation experiment; forcing VJP; C4 addendum, C5,
release, default DA.
