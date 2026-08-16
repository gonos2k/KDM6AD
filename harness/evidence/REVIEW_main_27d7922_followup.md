# Review response: `main` at `27d7922`

The owner's review after PR #135 listed thirteen items in a recommended
order (§12). This records what each became. It is a checklist, not a
finding: the numbers it quotes belong to the claims and bundles it points
at.

## Closed in this branch

| Order | Item | What it was |
|---|---|---|
| 1 | the loop universe | the per-loop checks walked the loops a call HAPPENS to carry, so records living only on loop 2 — loop 1 entirely absent — were complete for every loop anyone looked at, and two calls could run disjoint sets. Now every call's set is exactly `{1..L}`, one L per stream, and the same-run contract compares that L against the window header's `loops` — two records of one fact |
| 2 | expected metadata binding | the comparison width came from the header's OWN precision claim, so a G33P forging `precision f32` on an f64 stream re-opened the 29-bit conflation — reproduced on a live member. The width now comes from the EXPECTED arm (f64 writes f64, probe writes f32, source_precision is f32 always), the header must agree, and fixture/algorithm/rho_profile bind to the requested experiment. The manifest validator cross-checks each member row against the bundle's own top level |
| 3–4 | one validator for every raw stream | the density arms were checked only through their G33N identity and the ncmin decompositions through their own gate set — load-bearing raw streams under a WEAKER contract than the members beside them. `validate_member_stream` is the single validator: production routes every arm stream and every decomposition through it, and the chain re-checks arm streams against their typed `ran` block and multi-run inputs against the producer's filename schema (a name the schema cannot parse is refused, not skipped) |
| 5 | the pinned fixture supplies the domain | the chain's re-validation read (B, K) from the WORKING TREE, so editing the fixture source would re-judge every historical bundle against a domain its run never saw. The dims now come from the blob at the bundle's own `repo_commit`, required to hash to `fixture_sha256` first; a manifest whose digest lies gets `FIXTURE-UNRESOLVED`, not a guess |
| 6 | today's capability profile | the strict readers keep INITIAL/forcing/time-geometry OPTIONAL for the archive's sake, and the producer had inherited that leniency: a non-instrumented bundle could publish members with none of them, never compared to the fixture. `_require_current_profile` demands the exact fixture B×K, INITIAL, rho/delz, positive geometry, and the kernel's own `loops × dtcld == delt` rule — measured on all 192 published headers before it became a requirement |
| 7 | NFLUX duplicate facts | `nflux_den`/`nflux_delz` restate the bottom cell's rho/delz and `nflux_dtcld` restates `delt/loops`, and none was ever compared. Measured first: all 4827 published flux groups satisfy both exactly. A group that disagrees is two runs' records in one stream |
| 8 | the surface stage's exact universe | a missing surface cell came back as `None` — a surface-dependent row silently skipped rather than the stream refused. Measured: all 8945 published loops carry exactly cols × {k=−1} with one field set; that is now the contract |
| 9 | adversarial re-validation | every counterexample class the review names refuses on LIVE bytes (forged precision, forged source_precision, forged fixture, loop-2-only records, disjoint loop sets, duplicate-fact mismatches, missing surface rows), and all 21 published members + raw streams of both live bundles report `matches` under the full unified contract |

### Measured before fixed

```
§4   records only on loop 2 / disjoint {1},{2}       both ACCEPTED
§5   G33P header forged to precision=f32 on the
     live f64 member + sub-f32 rho perturbation      ACCEPTED (conflation re-opened)
§6   density arms / ncmin runs                       G33N-identity-only contract
§7   fixture (B,K)                                   read from the CHECKOUT
§8   member with no INITIAL / no forcing /
     no time geometry                                producible
§9.1 4827 flux groups                                duplicate facts never compared
§9.2 8945 loops                                      surface universe unchecked
```

And after: all 151 published G33N streams re-parse unchanged, every figure
the registry pins is untouched (no artifact changed), and the two live
bundles pass the strengthened contract as published — no re-production, for
the same reason as last cycle: the changes are to the CONTRACT, and
re-pointing pins to prove nothing is not evidence work.

## Deferred, with reasons

**Identity Phase B/C (order 10).** The review's own 판정: the five contract
items above were the prerequisites, and they land here — but the
re-production decision and the stored-id implementation remain the owner's,
with the design (subprocess split as step 0) unchanged in
`DESIGN_identity_phase_b.md`.

**F0.6 portability (§9.4).** The raw token is now validated at the parser
(grammar per producer, round-trip at the value), which removes the
formatting-dependence the review flags for the FORGERY direction. What
remains is the half-way-rounding note for exotic runtimes; recording the
rounding mode in the protocol is a header change, batched with the next
protocol bump like the IEEE bit sentinels before it.

**Stage A real MPI (order 11), mediation `G33-NCMIN-005` (order 12),
forcing VJP (order 13).** Science stages, gated exactly as the review
grades them.

## Standing NO-GOs (unchanged)

Identity Phase B/C (designed; contract prerequisites now closed); real
mixed-coastal MPI; the `G33-NCMIN-005` mediation experiment; forcing VJP;
C4 addendum, C5, release, default DA.
