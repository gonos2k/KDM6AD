# Fortran G33F protocol v4/v5 — the outer-loop carry is evidence

Status: **IMPLEMENTED.** Both bridge snapshots are emitted by both backends, the
carry is checked bit-for-bit, and both committed samples are regenerated at v4 after
proving equivalence against their v3 predecessors.

Supersedes `STAGE_PROTOCOL_V2.md` (which documents the v2 and v3 steps and remains
the record of those migrations).

## The gap v3 left

v3 made every outer loop's records distinguishable and gave each loop its own
`outer_pre_sed` entry snapshot. What it never recorded is what happens BETWEEN two
loops.

Concretely: the first real `dt = 300` four-leg run came back `INCONCLUSIVE` with the
Fortran and C++ legs diverging at loop 2's `outer_pre_sed` in `qv` and `t`. Loop 1
was bit-identical, 72/72. From that evidence alone the divergence could have been
born in

* loop 1's sedimentation (after its last `substep_pre` was recorded),
* the microphysics that runs after sedimentation in the same loop, or
* the carry itself — the state handed from one sub-cycle to the next.

Nothing in the record distinguished these. `outer_pre_sed(L+1)` was the first
observation after a long unobserved stretch, so "the divergence appears at loop 2"
was the strongest statement the evidence could support. For a gate whose entire
purpose is attributing a difference to sedimentation or ruling it out, that is not
enough.

## What v4 adds

Two whole-K snapshots per outer loop, at the two ends of the loop body:

| stage | where | what it means |
|---|---|---|
| `outer_post_sed` | end of the ice chain | the sedimentation RESULT |
| `outer_post_micro` | end of the loop body | what loop L+1 starts from |

Fortran anchors (both unique, identical in `module_mp_kdm6.F` and
`module_mp_kdm6_cons.F`):

```
      enddo ! do n = 1, mstepmax_i        -> outer_post_sed injected AFTER
   enddo                  ! big loops     -> outer_post_micro injected BEFORE
```

Both sit inside `do loop = 1,loops`, so the runtime loop index is already in scope
and no new argument, module variable or interface change is needed. The C++ leg
emits the same two stages from `runtime.cpp.overlay`, inside `KDM6_G33_OP_DUMP`.

### The fields

All three outer snapshots carry the same CARRIED state — **at v4**, eight of
`CoordinatorState`'s twelve members. See the v5 section below for the rest; reading
this list as current would understate what "the sedimentation result matched" covers,
which is exactly the mistake v5 was written to correct.

```
qr, nr, qv, t, qc, qi, qs, qg
```

`outer_pre_sed` additionally carries `rho` and `delz`, which are forcings rather than
carried prognostics. The carry can only be STATED about fields both snapshots
observe, which is why `qc/qi/qs/qg` were added to `outer_pre_sed` as well — with only
`qr/nr/qv/t` the bridge would have left the condensate outside, and the condensate is
what the microphysics moves.

Species indices are read from `kdm62D`'s own pack, not from WRF convention
(`module_mp_kdm6.F:380-384`, `module_mp_kdm6_cons.F:400-404` — identical):

```
qc = qci(:,:,1)   qi = qci(:,:,2)
qr = qrs(:,:,1)   qs = qrs(:,:,2)   qg = qrs(:,:,3)
```

### The check that makes it load-bearing

`g33_fortran_semantics` check (8):

```
outer_post_micro(L) == outer_pre_sed(L+1)     for every carried field, bit-exact
```

Bit-exact because a carry is a copy, not a computation. Anything other than equality
is a defect in the evidence itself, not a tolerance question — and it must be found
before the comparator reads the run, or it would surface as a backend divergence.

The comparator also compares both bridge stages across backends like any other
snapshot (`g33_normalize._COMPARATOR_STAGES`), so a divergence in what one loop hands
the next is now a finding rather than something only a human reading two dumps side
by side would notice.

## Compatibility

The line grammar did not change; the record UNIVERSE did. So the expected universe is
keyed off the banner (`_validate_stages(..., version)`):

* `version >= 4` — the bridge stages are required, and `outer_pre_sed` carries ten
  fields;
* `version <= 3` — neither is required, and `outer_pre_sed` carries the original six.

An older stream genuinely does not contain those records. Demanding them regardless
would report a protocol difference as missing evidence, and would also make the
equivalence proof below impossible to run.

## Equivalence, proven before the samples were replaced

The instrumentation must not perturb the run it observes. Every record a v3 stream
could also have carried — all ops, state, precip, mstep, and every pre-existing stage
value — is byte-identical between the v3 sample and a v4 run of the same fixture.
Only the new records are added.

This is the same discipline the v2→v3 migration used, and it is the only thing that
distinguishes "we added observations" from "we added observations and changed the
answer".

## v5 — the carried state is all twelve members

v4 carried eight fields. `CoordinatorState` has twelve, so "the sedimentation result
matched" was a statement about two thirds of it, and a difference in one of the
others could cross `outer_post_sed` unobserved. That mattered concretely: the dt=300
run's first observed difference is at `outer_post_micro`, and attributing it to the
microphysics requires knowing that sedimentation left *nothing* different.

v5 adds the number concentrations and the graupel volume:

```
nc   = nci(:,:,1)        ni  = nci(:,:,2)
nccn = nci(:,:,3)        brs = brs(i,k)      (2-D; the returned STATE calls it bg)
```

read, as before, from kdm62D's own pack rather than from convention. All three outer
snapshots carry the same twelve; `outer_pre_sed` keeps `rho`/`delz` as forcings.

`OUTER_PRE_SED` is now DERIVED from the carried list rather than maintained beside
it. The parallel list is exactly how the two drifted during this change: the post
snapshots gained the four fields and the pre snapshot did not, so the carry would
have been checked over fields one end never emitted. The parser already derived
its expectation the same way, which is why the mismatch surfaced immediately.

`_FINAL_BOUND` became a NAME MAP for check (9), because the state calls the graupel
volume `bg` while the bridge calls it `brs`. That is a rename across a copy. `t`
stays out: `th = t/pii` is a computation, and requiring bit equality there would
assert the conversion rather than the binding.

The expected universe is keyed by version — `{4: eight fields, 5: twelve}` — so a
pre-v5 stream is refused as a protocol difference rather than reported as missing
evidence, and a future tier is one row.

Equivalence proven before the samples were replaced, as at every previous step:

| fixture | shared records | verdict | added |
|---|---|---|---|
| `arithmetic_synthetic_v1` | 1351 | byte-identical | 146 |
| `arithmetic_multisubcycle_v1` | 10610 | byte-identical | 434 |

## Still open

* `substep_post` and the `reslope_*` stages remain outside the comparator's set.
* Per-loop `surface_increment` versus the single cumulative `PREC` (carried over
  from the v3 list).
* The `ProgBOutputs` carried from sedimentation into the microphysics is still not
  recorded, so even at v5 the state bridge is not the whole handoff.
