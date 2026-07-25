# Fortran G33F protocol v2 — carrying the real outer loop and chain

Status: **SPECIFIED, NOT IMPLEMENTED.** Required before any multi-outer-loop
(historical dt=300) four-case verdict. Blocks owner P0-4.

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

## Work items

1. `make_fortran_overlay._emit_lines` — emit `loop` as a runtime `I0` instead of the
   `1` literal (the record's token SHAPE is unchanged, so the op regex still matches).
2. `make_fortran_overlay._stage_write` / `_stage_block` — add `loop` + the chain
   literal; bump the `BEGIN v1` banner to `v2`.
3. `g33_fortran_dump` — accept v2 (`_STAGE` regex + the `stages` key gaining
   `(loop, chain)`); keep v1 acceptance for the committed sample until it is
   regenerated, keyed off the banner version so the two cannot be confused.
4. `g33_fortran_semantics` — stage lookups take the wider key.
5. `g33_normalize.from_fortran_run` — use the real values; delete the derivation.
6. **Regenerate `harness/tests/data/g33_legacy_sample.g33f`** (needs gfortran + the
   gitignored host tree; both are present on this host). This rewrites a COMMITTED
   evidence artifact, so it wants explicit owner sign-off rather than a silent update.

## Scope note

v2 makes the multi-loop evidence *expressible*. It does not by itself produce a
multi-loop run: that still needs the `arithmetic_multisubcycle_v1` fixture and a
dt large enough for `loops > 1` (dt=300 → loops = ceil(300/120) = 3).
