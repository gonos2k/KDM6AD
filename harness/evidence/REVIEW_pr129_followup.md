# Review response: PR #129 follow-up

> Superseded in part by `REVIEW_main_followup.md`, which answers the review of `main` at
> `4274da2` and closes items 9 and 11 of the table below.

The owner's post-merge review of PR #129 (`main` at `3180dbc`) listed twelve
items in priority order. This records what each one became. It is a checklist,
not a finding: nothing here is a measurement, and the numbers it quotes belong
to the claims it points at.

## Closed in this branch

| # | Item | What it was | Where |
|---|---|---|---|
| 1 | G33FOP semantic/storage dtype | `_emit_lines` chose its Z descriptor and its label from the SCHEMA dtype, so an f64 build wrote an eight-byte default real through `Z8.8` | `g33_fortran_bindings.storage_class`, `make_fortran_overlay._storage`, `test_g33_storage_dtype.py` |
| 2 | `G33N PROTOCOL` single/early | the width was a variable the record loop reassigned, so a stream that was f32 for its first calls and f64 for the rest parsed as one run | `g33_number_transport.calls` |
| 3 | strict-parser coverage | `KNOWN_G33F` accepted a family NAME; the whole op ladder and every unconsumed STAGE went unread, an overflowed `********` payload included | `g33_number_transport._shape` |
| 4 | identity: content vs anchor | every pin carries `commit` beside `content_sha256` and `repo_commit` sits at the top, so all three ids moved on every commit | `g33_identity.content_only` |
| 5 | two-commit regression | the layering was measured by mutating a synthetic manifest, never by re-publishing the same bytes at a new HEAD | `test_g33_identity.py`, against this repository's real history |
| 6 | f64 analysis applicability | three f32-only analyses were dispatched at any precision | `g33_refine_manifest.ANALYSIS_PRECISIONS` |
| 7 | `G33-NCMIN-004` re-grade | held for a proposition it does not make | `CLAIMS.yaml`: `confirmed-with-scope`, causal question split to `G33-NCMIN-005` |
| 8 | coverage vs verification | one word answered "how much is bound" and "did it check out" | `g33_evidence_chain._coverage_status` / `_verification_status` |

### Measured, not argued

Items 1 and 3 were checked against a real f64 build of the pinned legacy module
on `g33_fixture_boundary_mapping_v1` (`refine_build.sh --f64 --nflux`, owner's
host — the reference Fortran is gitignored and absent from CI), before and
after:

```
before   G33FOP 1 main 1 1 0 QR_FALK mul_dend_q       f32 ********
         G33FOP 1 main 1 1 0 QR_FALK falk_f32         f32 ********
         G33FOP 1 main 1 1 0 QR_FALK shadow_falk_f32  f32 2FF173B7
         287 overflowed records in one stream, every one of them dropped in
         silence by the reader

after    G33FOP 1 main 1 1 0 QR_FALK mul_dend_q       f64 3F11B1D931BC5580
         G33FOP 1 main 1 1 0 QR_FALK falk_f32         f64 3DFE2E76D93CB2C8
         G33FOP 1 main 1 1 0 QR_FALK shadow_falk_f32  f32 2FF173B7
         0 overflowed records
```

`Z8.8` on an eight-byte default real overflows its field, so the payload was
never a truncated number -- it was asterisks, and asterisks matched no pattern,
reached the family check and were skipped. The wrong-number path therefore
presented as a stream with fewer records than the run emitted.

`shadow_falk_f32` is unmoved across the change and its bits are exactly
`float32(falk_precast)` -- `2FF173B7` against `3DFE2E76D93CB2C8` -- so the
pinned `real(...,4)` rung is emitting the right value at the right width rather
than a plausible one.

The new reader parses the new stream and REFUSES the old one, at the first
record that used to be dropped.

At f32 the generated overlay is byte-identical for both variants, checked by
generating from the pinned source with and without the change. Item 3 is also
checked against the three archived `.g33f` samples, ~17k records, so the new
strictness is not rejecting the archive.

## Not closed, and why

**9. f64 bundle publication — NO-GO.** Items 1, 2, 3 and 6 were its blockers
and are closed in the code, but closing a blocker is not the same as producing
the artifact. Publishing needs an f64 `--nflux` run on the owner's host against
the pinned Fortran (`host/**` is gitignored and absent from CI), the eight
per-member analyses re-run on that stream, and the three f64-blocked claims
re-evaluated against it. None of that is a repository change and none of it is
done here.

**10. Stage A real MPI one-call gate — not started.** Every ncmin figure in the
registry comes from a three-column synthetic fixture called as one tile by a
sequential driver. The gate the review asks for needs real ranks, haloes and a
real coastal `xland`, which is a host campaign rather than a harness change.
The scope prose on `G33-NCMIN-001` already says the operational magnitude is
unmeasured, and it still is.

**11. Identity Phase B/C — NO-GO, and now for a smaller reason.** Phase B
writes the ids into published manifests and Phase C re-points claim bindings at
them, so both re-produce the archive. The canonicalization those phases were
waiting on is items 4 and 5, which are closed; what remains is that the ids are
still DERIVED and stored nowhere, and making them authoritative is a
re-production decision with a cost attached. That decision is the owner's.

**12. Forcing VJP — not implemented.** It is what would answer `G33-NCMIN-005`
in its adjoint form, and it is downstream of a corrected forward contract.

`C4 addendum`, `C5`, release and default-DA promotion stay NO-GO for the
reasons already recorded against them; nothing in this branch touches them.

## Two judgements worth naming

The review's §5.4 lists the compiler among the things that should not move
`run_content_id`. It still does, deliberately: two builds of identical sources
by different compilers are not the same run content, and an id that called them
equal would answer a question nobody asked. The retrieval anchors -- `commit`,
`repo_commit`, `analyzer_commit` -- are what came out.

§5.4 also proposes a fourth layer, `provenance_anchor_id`, over the commits and
refs the other three now exclude. Not built. The anchors are not lost -- they
stay in the manifest, which is where the evidence chain resolves them -- and
`repo_commit` already answers "was this published from that commit" directly.
A derived id nobody consumes is the shape this file argues against elsewhere:
an id over nothing is an id that never moves.
