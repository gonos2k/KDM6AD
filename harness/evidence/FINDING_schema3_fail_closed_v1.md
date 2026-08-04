# The extension protocol was not fail-closed, in six separate ways

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-PROTOCOL-002` | **active** | confirmed | The G33N stream contract. It makes the protocol fail-closed; it does not re-verify physics already measured under schema 2, and the cap-attribution run has not been re-published under the new contract. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner §4 and §14 priority-1. Schema 2 declared features and checked sub-step
universes, and the PR describing it said undeclared records were rejected and
duplicates refused. Neither was true. Six holes, each of which let a malformed or
incomplete stream reach an analysis that then reported a number.

## The six

| # | hole | what passed | consequence |
|---|---|---|---|
| P0-1 | `capin` declared, **zero** CAPIN records | a stream with no cap data | the cap attribution — 39/255 interfaces, 100.00% of the ice residual — computed over nothing |
| P0-2 | duplicate with the **same value** | `_put` raised only when values *differed* | a duplicated stream is not a record of a run, whatever the values agree on |
| P0-3 | record whose feature was **not declared** | parsed anyway, universe check skipped | the record entered the analysis with nothing verifying it was complete |
| P0-4 | extension record **outside** a call | silently dropped by `cur is None: continue` | records drifted out of their brackets and the stream still looked complete |
| P0-5 | **NaN/Inf** in XFER or TOPOUT | finite checks covered NFLUX and CAPIN only | NaN residual, and a JSON writer emitting a bare `NaN` token — not even valid JSON |
| P0-6 | TOPOUT at the **wrong level** | only the sub-step set was checked | TOPOUT is the *top* cell's removal; a record at k=2 is a different quantity |

To these the same pass adds one the owner's §14 list names separately: the stage
level universe was **pooled across columns**, so a column short a level passed
whenever another column supplied it. That one is not a protocol nicety — the
matched closure builds each column's integral from exactly those per-column level
sets, so a short column silently integrates over fewer cells *and* takes the
wrong cell as the bottom one.

## What schema 3 requires

Per `(call, loop, column, chain)`, with `mstep` and `K` from the stream itself:

```
XFER    n = 1..mstep                    the bottom-cell transfer
TOPOUT  n = 1..mstep, k = 0             the top-cell removal
CAPIN   n = 1..mstep, k = 1..K-1        one per interface
```

verified against the run: CAPIN and TOPOUT are emitted **unconditionally** at
their sites — not only when a cap binds — so an exact universe is the right
contract rather than an over-strict one.

Stages carry an exact **rectangular** universe: every cell of a stage carries the
same field set, and every column carries levels `0..K-1`. The field set is taken
from the stream rather than hardcoded, so a field the driver adds needs no change
here; what the parser additionally requires by name are the fields the closure
*reads* (`rho`, `delz`, and the four species), because rectangularity alone would
accept a stream with no `rho` at all — every cell agreeing about not having it.

Declaration is now binding in **both** directions: a declared feature that no
record emits is an error, and a record whose feature was not declared is refused.

## The one that was asserting the defect

`test_records_outside_any_call_are_not_attributed_to_one` asserted that a stray
`MSTEPI` was *ignored*. It was written to check that stray records are not
misfiled, and it passed for exactly the reason P0-4 is a defect. Not attributing
evidence to the wrong call was never sufficient — discarding it quietly is the
same failure. It is now `test_an_extension_record_outside_any_call_is_REFUSED`.

## Verification

The tightened parser **accepts the real stream unchanged** and reproduces the
same numbers (`main/nr` +15.0036 / +13.3377 / +11.8402%), so this refuses
malformed streams rather than valid ones. Each hole has a test that constructs
the specific malformed stream and requires refusal.

## Limits

- **This makes the protocol fail-closed; it does not re-verify the physics.**
  The cap numbers this protects (39/255, 100.00%) were measured before the
  contract was tight enough to guarantee the stream behind them was complete.
  They now *are* protected going forward, and re-running under schema 3
  reproduces the closure numbers — but the specific cap-attribution run has not
  been re-published under the new contract, so its grade stays where the owner
  put it.
- **`K` is trusted from `CALL_BEGIN`.** A stream that lies consistently about
  both `K` and its record set is self-consistent and passes. The declared range
  is checked against the state, which is what makes the lie hard, not impossible.
- The exact universes assume every site fires unconditionally. That is true of
  this overlay, verified against a run; a future overlay that guards an emission
  would need the contract to change with it.
