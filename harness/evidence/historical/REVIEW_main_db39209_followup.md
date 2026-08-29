# Review response: `main` at `db39209`

The owner's review after PR #133 listed eighteen items in a recommended order
(§13). This records what each became. It is a checklist, not a finding: the
numbers it quotes belong to the claims and bundles it points at.

## Closed in this branch

| Order | Item | What it was |
|---|---|---|
| 1 | `validated_run_identity(expected B, K)` on every primary member | each split covered `1..W` congruently — and nothing checked `W = B_fixture`; the strict identity path guarded the f64 arms while the PRIMARY members it was built for went unpinned |
| 2 | empty-call refusal | a `CALL_BEGIN`/`CALL_END` pair with no records had `loops = ∅`, so the per-loop checks ran zero times and the call passed as complete |
| 3 | split/tile ranges + exact Cartesian universe | `cid = (split-1)·ntile + tile` is an equation, not a range check: `split=0, tile=3` under `ntile=2` satisfies it with `cid=1`; the universe is now exactly `1..nsplit × 1..ntile` |
| 4 | call geometry domain | `K ≥ 1`, `1 ≤ i0 ≤ i1`, positive-finite `delt` — checked at `CALL_BEGIN`, with one K and one delt per stream ("one stream describes one problem") |
| 5 | G33N ↔ G33R/G33P cross-check | `_require_fixture_domain` ties the three protocols at production: the transport header's width/levels against the window protocol's columns and level sets, for both f32 members and f64 probes |
| 6–7 | Phase-B ID storage design (`DESIGN_identity_phase_b.md`) | design only, implementation stays NO-GO: `derived_ids` inside the identity block (excluded from every hash input by the existing reduction rule, so `I = H(M ∪ {I})` cannot form), recompute-then-compare verification, per-id schema tags decoupled from the container schema |
| 8 | canonical list sort in the id inputs | two manifests recording the same set-valued rows in different order carried different ids — pins sort by path, members by `(nsplit, mode, file)`, artifacts by file; `runtime_argv` stays order-sensitive because a command line is not a set |
| 9 | producer/analyzer execution separation | analyzers now import at dispatch time, after every raw member is on disk and strict-parsed; a lazy `_an("…")` dispatch still counts as a dependency edge in BOTH AST derivations, so the recorded role graph is byte-identical |
| 10 | water col-2 ULP binding + "10x" unbound | column 2's residual bound in its own inventory's ULPs (5.75e8 — the honest magnitude of UNESTABLISHED); the rain-diagnostic "up to 10x" declared `unbound:` instead of floating free in prose |
| 11 | operator/physical terminology | the module docstring called `Σ den·Δz·nr` the physical column number; it is the OPERATOR's pseudo-measure, and the physical measure is `Σ ρ_d·Δz·nr` (G33-BASIS-006) — corrected where a corrected-physics implementer would read it first |
| 12 | closure operation count | the γₙ bound counted terms, not flops: a 17-term signed sum is 2 ops per fused term plus the final subtraction — `closure_ops` is now 69 for that column, and the bound grew accordingly rather than shrinking |
| 13* | both bundles re-produced | required this cycle anyway: the schema now demands `ran.levels`, so the published v3 arm streams became MANIFEST-SCHEMA-MISMATCH — the designed cost of a new required field, paid the designed way |

\* the bundle-re-production half; the "ID recompute equality" half is the
Phase-B validator and stays with items 14–15 below.

### Measured before fixed

Every P0 was reproduced before it was touched:

```
§4  call with zero records          -> loops == set(), _check() PASSED
§5  split=0, tile=3 (ntile=2)       -> cid == 1, ACCEPTED
§4  members() production path       -> no validated_run_identity call at all
§6  K=0 / i0>i1 / delt=-25          -> all parsed clean before the geometry gate
```

And the re-production was verified before the registry moved: all 49 figures
CLAIMS.yaml pins from either bundle were compared against the NEW artifacts —
49 of 49 byte-identical, 0 moved. Old → new:

```
ncmin-001   d26d6759… -> 937df8b3…   (manifest ec6ec144… -> 5eb82f01…)
water-001   a0f9e8c1… -> e9371952…   (manifest 759a9d3c… -> 72286e09…)
```

## Deferred, with reasons

**ID storage in the manifest (order 14) and claim → `analysis_id` (order 15).**
Phase B/C were NO-GO in the review's own 판정 and remain so. What this branch
did is close every prerequisite the review listed for them (orders 6–9) and
write the design down (`DESIGN_identity_phase_b.md`), so the owner's
re-production decision is the only thing left between the design and the
implementation.

**Stage A real MPI (order 16), mediation `G33-NCMIN-005` (order 17), forcing
VJP (order 18).** Science stages, out of scope for a hardening branch, all
still gated exactly as the review graded them (PREDICTED-UNMEASURED / HOLD /
미구현).

## Standing NO-GOs (unchanged)

Identity Phase B/C (designed, not implemented); real mixed-coastal MPI; the
`G33-NCMIN-005` mediation experiment; forcing VJP; C4 addendum, C5, release,
default DA.
