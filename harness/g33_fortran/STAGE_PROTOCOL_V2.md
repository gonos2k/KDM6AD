# Fortran G33F protocol v2 — carrying the real outer loop and chain

Status: **IMPLEMENTED.** All six work items below are done, including regenerating
the committed sample. The Fortran evidence can now EXPRESS multi-outer-loop records;
producing one still needs a dt large enough for `loops > 1` plus the
`arithmetic_multisubcycle_v1` fixture (see the scope note).

Equivalence evidence for the migration: a v2 run of the same fixture reproduces the
v1 sample EXACTLY — identical fixture/parameter SHA, all 579 op records, state,
precip, mstep, and all 174 stage values. Only the record framing changed.

## The actual gap (larger than "STAGE lacks two fields")

`G33F STAGE` has no `outer_loop`/`chain` field, so `g33_normalize.from_fortran_run`
derives them (`loop=1`; `outer_pre_sed`/`surface` → `-`, `substep_pre` → `main`).

But the OP records do not carry them either. `make_fortran_overlay._emit_lines`
writes the **literal string**:

```
'G33FOP 1 main', n, i, kte-k, ...
```

so `loop` and `chain` are compile-time constants in the emitted text, not runtime
values. Every op in the committed sample reads `1 main` for that reason alone.

Consequence: the normalizer's "verify the derivation against the ops" guard is
**vacuous** — the ops can never report loop 2. Single-outer-loop is therefore an
ASSUMPTION of the Fortran leg, not a verified property. (The C++ leg is unaffected:
its records carry real `outer_loop`/`chain` from the schedule.)

## Why the fix is small

`kdm62D` (module_mp_kdm6.F:517) contains BOTH

* `do loop = 1,loops`      (L895) — the cloud outer subcycle
* `do n = 1, mstepmax`     (L1138) — the main sed chain, the overlay's STAGE anchor
* `do n = 1, mstepmax_i`   (L1230) — the ice chain

so **`loop` is already in scope at every injection point.** No new argument, module
variable, or counter is needed — only the emission format changes.

## v2 protocol

```
G33FOP  <outer_loop> <chain> <n> <col> <k_top> <op_id> <field> <dtype> <hex>
G33F STAGE <outer_loop> <chain> <stage> <n> <field> <col> <k> <dtype> <hex>
```

`outer_loop` becomes the runtime `loop`; `chain` stays a literal per injection site
("main" at the mstepmax anchor, "ice" at mstepmax_i) because the anchor determines it.

## Work items (all done)

1. `make_fortran_overlay._emit_lines` — emit `loop` as a runtime `I0` instead of the
   `1` literal (the record's token SHAPE is unchanged, so the op regex still matches).
2. `make_fortran_overlay._stage_write` / `_stage_block` — add `loop` + the chain
   literal; bump the `BEGIN v1` banner to `v2`.
3. `g33_fortran_dump` — accept v2 (`_STAGE` regex + the `stages` key gaining
   `(loop, chain)`); keep v1 acceptance for the committed sample until it is
   regenerated, keyed off the banner version so the two cannot be confused.
4. `g33_fortran_semantics` — stage lookups take the wider key.
5. `g33_normalize.from_fortran_run` — use the real values; delete the derivation.
6. **Regenerate `harness/tests/data/g33_legacy_sample.g33f`** — done with owner
   sign-off; the committed sample is now v2 (176 STAGE lines reframed, values
   unchanged).

## Scope note

v2 makes the multi-loop evidence *expressible*. It does not by itself produce a
multi-loop run: that still needs the `arithmetic_multisubcycle_v1` fixture and a
dt large enough for `loops > 1` (dt=300 → loops = ceil(300/120) = 3).

---

# v2.1 — what is still single-loop (owner P0-1)

v2 made multi-loop records *distinguishable*; the Fortran reader still models a
single loop. Concretely, on `main@bb243e98`:

| Site | Loop-1 assumption |
|---|---|
| `G33F MSTEP <col> i32 <bits>` | no loop/chain at all — loop 2's mstep would collide with loop 1's |
| `FortranRun.mstep: dict` | keyed `col -> count`, cannot express `m[L,c] != m[L+1,c]` |
| `_validate_stages` | `L, MAIN = 1, "main"`; a valid loop-2 stage is rejected as an EXTRA record |
| `parse_fortran_run` | `if o["loop"] != 1 or o["chain"] != "main": raise` — v2 records loop 2 correctly, then the strict parser refuses it |
| `_expected_op_universe` | builds a schedule with `loops: 1`, `mstepmax_main=[max_mstep]` |
| `g33_fortran_semantics` | `_sv(..., loop=1)`, one global mstep, and requires `substep_pre.dtcld == PARAM dt` |

That last one is a genuine physics constraint, not just plumbing: with
`loops > 1` the cloud timestep is `dtcld = f32(dt_host / loops)`, so `dtcld == dt`
holds only at `loops == 1`.

## Wire change

```
G33F MSTEP <outer_loop> <chain> <column> i32 <hex>
```

`loop` is in scope at the capture site exactly as for OP/STAGE (see above), so this
is again a format change, not a data-flow change.

## Work items

1. `make_fortran_overlay._cap_lines` — emit `loop` and the chain literal.
2. `g33_fortran_dump` — `_MSTEP` v2 regex; `FortranRun.mstep[(loop, chain, col)]`;
   v1 streams fill `(1, "main", col)` so the key shape is uniform.
3. `_validate_stages` — expected universe per `(outer_loop, chain)` instead of the
   `L, MAIN = 1, "main"` constants, with `n = 1..max(mstep[L, chain, :])`.
4. `_expected_op_universe` — schedule with the observed `loops` and a per-loop
   `mstepmax_<chain>` list; op keys gain `(loop, chain)`; drop the loop/chain guard.
5. `g33_fortran_semantics` — per-loop lookups; `dtcld == f32(dt / loops)`;
   state continuity checked WITHIN a loop, and loop L's exit state against loop
   L+1's `outer_pre_sed`.
6. Surface: separate the per-loop `surface_increment` from the single cumulative
   `PREC`, and check `PREC == sum_L increment_L` in a defined f32 association order
   (today the normalizer attaches the cumulative PREC to the last loop, which is
   ambiguous once `loops > 1`).
7. Regenerate the committed sample; prove single-loop equivalence first, exactly as
   the v1→v2 migration did.
8. Decision parser accepts v2 only; keep v1 in a `parse_historical_v1()` migration
   path so the two grammars stop costing a branch everywhere.

## Why this is not yet exercised

No multi-loop fixture exists: `dt=20` gives `loops = 1`. The generalisation is a
PREREQUISITE for `arithmetic_multisubcycle_v1` (`dt=300` → `loops = ceil(300/120) = 3`),
so its multi-loop paths can only be covered by synthetic parser tests until that
fixture lands.
