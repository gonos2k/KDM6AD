# Review response: `main` at `fe749ae`

The owner's review after PR #138 listed seventeen items in a recommended
order (§14). This records what each became. It is a checklist, not a
finding: the numbers it quotes belong to the claims and bundles it points
at.

Three sentences from the review are what this branch answers:

> source digest를 기록 ⇏ 그 source가 실제 compiled source임을 증명
>
> original module의 `dtcldcr` ⇏ generated overlay의 `dtcldcr`
>
> canonical expected run + literal argv ⇒ 동일 요청에 복수 recipe ID

## Closed in this branch

| Order | Item | What it was |
|---|---|---|
| 1 | `module_path`/`module_sha256` required at v6 | the two fields the kernel geometry is provenanced to were optional, so a manifest could drop the private module's provenance entirely and keep every other check |
| 2 | `kernel_geometry` ↔ module ↔ build provenance | the digest was length-checked only. `source_sha256` had to be 64 hex and nothing more, so `"0000…0000"` was a valid provenance for the sub-cycle limit; `source_path` was compared to the CHECKOUT's `KERNEL_SOURCES` map rather than to what this bundle recorded. All three records must now name one file and one digest |
| 3 | the compiled overlay is bundle payload | an `--nflux` build compiles a GENERATED overlay, and the bytes the compiler read were not in the bundle at all. `module_mp_ovl.F` is published in `build_artifacts` and its digest must be the `compiled_module_sha256` the build recorded |
| 4 | `dtcldcr` re-read from what was compiled | the limit was read from the original module BEFORE the build, and the equality with the overlay's limit was an assumption. `kernel_geometry(..., compiled=…)` re-parses the overlay's bytes and requires raw-word equality, recording `compiled_source_sha256` and `compiled_dtcldcr_word` |
| 5 | `dtcldcr_storage` is the build's own real kind | `120.0` is exact in both widths, so an f64 bundle could record an f32 limit and derive identical geometry — until a limit that is not f32-exact makes the loop count move silently |
| 6, 7 | one `RunContract` per bundle | the producer read the kernel source once for the primary members, and `ncmin_locality.gated_text()` read it AGAIN per multi-run leg: two geometry authorities inside one bundle, and a source edit between the two reads would bind different parts of one manifest to different limits. A frozen `RunContract` is built once and passed to every raw path |
| 8 | the recipe id is the canonical request | `["12","rezero"]` and `["12","rezero","3","as-is"]` are the same request to the driver and were the same `expected_run` to the validator, but `run_recipe_id` hashed the literal argv, so one experiment had two ids. It hashes `canonical_invocations(man)` — derived from `expected_run`, sorted — and the literal argv stays as a diagnostic |
| 9 | recipe/content/analysis carry their own tags | the container schema was inside the run ids, so an archive-format v6 would move the identity of runs whose executable, fixture and raw members were untouched. `g33_run_recipe_v1`, `g33_run_content_v1` and `g33_analysis_v1` are the tags the ids answer for |
| 10 | the resolved gate runs BEFORE publication | `columns` and `levels` were checked against the pinned fixture by the evidence chain, i.e. AFTER the manifest was in the immutable store. `resolved_violations()` reads the fixture bytes, the kernel witness and the members and refuses at publish time |
| 11 | `build_provenance` is a closed schema | the writer records compiler, `f951`, every compiled source, the executable, both module digests, the fixture and the build script — but the validator only required a non-empty object, so an arbitrary manifest could reduce all of it to one executable digest |
| 12 | private sources are content-addressed | the build compiled from the host tree and the collector re-read those paths afterwards, so an edit in between produced an executable from one byte set and a record of another. Every source is staged by digest outside the output directory, and the compile-time digest is what the collector uses |
| §11 | the driver's window header stops owning a second limit | `loops_used = max(nint(delt_used/120.0), 1)` was a literal that agreed with the pinned kernel by coincidence. The build extracts `dtcldcr` from the bytes it is about to compile and passes it as `-DKDM6_DTCLDCR`; a driver built without it does not compile |
| 14 | v6 + identity-v4 controlled re-production | below |

### Measured before fixed

Each of these was reproduced against a real published manifest before the
check that refuses it existed.

```
§4  source_sha256 "0000…0000" beside the real module       CLEAN
§4  kernel_geometry naming the conservative kernel          CLEAN
§4  build_provenance naming another module                  CLEAN
§4  the overlay the compiler read, absent from the bundle   CLEAN
§5  an f32 limit recorded for an f64 build                  CLEAN
§6  two kernel-source reads inside one bundle               both accepted
§7  ["12","rezero"] vs ["12","rezero","3","as-is"]          TWO recipe ids
§8  a container-schema bump                                 run ids moved
§9  levels 999 beside a K=4 fixture                         published, then refused
§10 an edit between compile and hash                        executable ≠ record
§11 the driver's constant forced to 60, the kernel at 120   header says 5
```

The last one is worth spelling out, because it is the only place a record
disagreed with the run that produced it. Two builds of the same experiment,
identical in every way except the driver's sub-cycle constant:

```
driver 120. (the kernel's)  G33R BEGIN nsplit 1 rezero legacy delt 300.000000 loops 3 dtcld 100.000000
driver  60. (forced)        G33R BEGIN nsplit 1 rezero legacy delt 300.000000 loops 5 dtcld 60.000000
```

Every other byte of both streams is the same — the G33R state stream and
the whole G33F family, `MSTEP` included, so the kernel ran three sub-cycles
of 100 s in both. The header was reporting a geometry the kernel never ran,
and nothing else in the stream could have contradicted it.

### And after: the adversarial sweep

Twenty-two probes against the live `ncmin-001` manifest, every one through
the shipped validator. A row reading CLEAN would be a gap.

```
the published bundle itself                                          clean
v6 without module_sha256                                             refused
v6 without module_path                                               refused
kernel_geometry provenanced to the other kernel                      refused
build_provenance names a different module than the manifest          refused
kernel_geometry source digest is 64 hex but not the pinned module    refused
compiled overlay digest is not the published artifact                refused
the overlay is not published at all                                  refused
the compiled limit is forged to 60 s                                 refused
kernel_geometry reads the limit from other bytes than the compiler   refused
a self-consistent f64 limit recorded for an f32 build                refused
the word and the value name two limits                               refused
v6 bundle wearing the v2 kernel tag                                  refused
v6 bundle wearing the v1 kernel tag                                  refused
expected_run declares a horizon the fixture word does not decode to  refused
expected_run declares the other algorithm                            refused
expected_run drops a required key                                    refused
expected_run gains a key the schema does not close over              refused
the same request spelled with the defaults written out               one id
a genuinely different decomposition                                  moves
the container schema is bumped                                       ids hold
the declared horizon changes                                         recipe moves

22 probes, 0 gaps
```

## Schema v6, identity v4, and the controlled re-production

`module_path`/`module_sha256` become required, `build_provenance` and
`expected_run` become closed key sets, `kernel_geometry` answers for the
COMPILED bytes, and the run ids change what they hash. Every one of those
is a stricter contract, so each arrives as a version rather than as a
demand on history: `refinement_experiment_v6`, `g33_layered_identity_v4`,
`kdm6_subcycle_v3`, with older bundles held to the contracts and id rules
they were published under. Both live bundles were re-produced;
**49 of 49 pinned figures verified byte-identical before the pins moved**.

```
ncmin-001   b97f36f9… -> 9300dd61…      water-001   0a7ca415… -> dfdd55cd…
```

The §11 change was re-produced separately and shown inert: every member's
`output_sha256` is byte-identical across it, which is the property that
matters, since a named parameter holding the kernel's own limit folds to
the constant the literal already was. The executable digest does move —
the driver's SOURCE moved, and gfortran's object carries it — so the
bundles are re-addressed rather than unchanged.

## The Codex stop-time review, in this cycle's own work

Two findings against this branch's own commits, both reproduced before
they were fixed.

* **the public-checkout seam replaced the function under test.** On a
  checkout without `host/**`, `kernel_geometry()` refuses — correctly —
  so the producer tests get a seam that stands in for it. The seam was
  autouse, so it also stood in for the one test whose whole subject is
  that refusal. That test now opts out by marker and exercises the real
  function, verified under a simulated public checkout.
* **logging a path is not recording bytes.** The source log carried the
  logical path alone, which sent the provenance collector back to the host
  file to hash it — the very re-read staging exists to remove. It carries
  `path<TAB>digest` now, with the digest taken at the moment of
  compilation, from the bytes the compiler was fed.

Two mistakes this branch made and caught in its own work are worth
recording beside them, because both are the shape the campaign keeps
hitting:

* **test infrastructure must not hide the thing under test.** Beyond the
  seam above: the producer tests used stand-in files for the module and
  the fixture, so a binding that compares real paths could not fail, and a
  faked `fixture_width` contradicted the fixture the resolved gate reads.
  All three now use the real files. The same seam then failed a third way,
  on CI: it had drifted from the signature of the function it replaces —
  the compiled-overlay argument went to the real one and not the stub —
  and it faked only one of the three records v6 ties together, so every
  bundle-assembly test refused with `source_path … is not the manifest's
  module_path …`. Reproduced in a clone with no host tree, 18 failures,
  the same 18. A test now asserts the two signatures match, so the next
  drift fails on the machine that causes it rather than on CI.
* **a fix can move the artifact's address.** Staging under `$OUT` put
  output-directory paths inside the binaries, so two builds of one
  experiment addressed differently — found by the test that asserts they
  do not. Staging moved to a content-addressed root outside the output
  directory, and two builds in different directories now agree on both
  their sources and their executable digest.

## Deferred, with reasons

**Raw/analysis subprocess split (order 13) and Identity Phase B/C.**
Unchanged and still NO-GO. This cycle closes the three gates the review
named as prerequisites — kernel geometry ↔ actual compiled source, the
immutable `RunContract` on every raw path, and canonical recipe identity —
so what remains before stored ids is the subprocess isolation itself and
the owner's re-production decision.

**Stage A real MPI (order 15), mediation `G33-NCMIN-005` (order 16),
forcing VJP (order 17).** Science stages, gated exactly as the review
grades them. The review moves research-grade Stage A to GO; the raw-stream
record it specifies (global column id, rank id, rank-local bounds, physics
tile bounds, runtime and tile-end `xland`, selected and locally intended
`ncmin`, the margin, and floor/branch activation) is a design item, not a
measurement, and is not attempted here.

## Standing NO-GOs (unchanged)

Identity Phase B/C; real mixed-coastal MPI; the `G33-NCMIN-005` mediation
experiment; forcing VJP; C4 addendum, C5, release, default DA.
