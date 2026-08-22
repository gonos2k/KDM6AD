# Cycle checklist: the re-review of `main@59ea169` (PR #155)

Every item the review raises, from its body and not only from its priority
list, with where it landed. Two of them the first pass through this checklist
answered PARTIALLY and reported as done; they are marked.

## P0

| # | item | where | status |
|---|---|---|---|
| 1 | invalid contrast still carried numeric beta into the JSON (§4) | `coefficients()` | **closed** -- every term is `None` |
| 2 | the published masking is `D_ni_metric`, not `R_ni` (§5) | finding | **closed** -- and the second occurrence, in the window section, was missed on the first pass and is fixed |
| 3 | single/split never checked for the same input (§6) | `same_input()` | **closed** |
| 3b | `xland` was not in the record at all (§6) | driver + reader | **closed** -- emitted as a `FORCING` record, reader's name set widened |
| 3c | intended vs imposed `ncmin` not in the record (§6) | `ncmin_exposure()` | **closed by DERIVATION**, not by emission -- see below |

## P1 and HOLD

| # | item | where | status |
|---|---|---|---|
| 4 | `partition` counts compared cells against components (§7) | `_partition()` | **closed** -- both units at all four points |
| 5 | `_den` carried a mass control (§8) | registry | **closed** -- control removed AND reader corrected to `state`, which the first pass missed |
| 6 | cross-arm identity lacked delt/dtcld/loops/**fixture**/window (§9) | `check_identity()` | **closed** -- the fixture was the piece the first pass missed, and needed a new `G33R FIXTURE` record |
| 7 | zero denominator was `0.0`, not invalid (§10) | responses | **closed** -- and for `D_*_metric` too, which the first pass missed |
| 8 | conditionals average over the third factor (§11) | `conditionals()` | **closed** -- simple effects AND a computed `_average_representative` flag, which the first pass left to the reader |
| 9 | evidence binding must require `_valid` (§14-1) | `bindable()` | **closed** |

## Science

| # | item | status |
|---|---|---|
| 10 | physical dry-air Arm N_d (§12.2, §14-8) | **measurable now, not run.** `g33_fixture_moisture_gradient_v1` separates the two ledgers for the first time; the ARM needs a freeze-lift, requested in `REQUEST_freeze_lift_arm_nd.md` |
| 11 | LC05 actual-column factorial (§14-9) | **the recorded blocker was wrong** -- the real case's own forecast carries `QNRAIN` after 20 s. A real-COLUMN fixture is still blocked, by the manifest's vertical anchor |
| 12 | real MPI effect (§14-9) | measured for ONE STEP in `FINDING_real_mpi_decomposition_v1` |
| 13 | operational precipitation impact | **unmeasured** |

## What the two partial passes cost, and the shape they shared

Both were the same mistake: reading the review's PRIORITY LIST rather than its
body. §8 asks for a control removal and a reader change and I did the control;
§9 lists five identity fields and I added three; §10 names two readers and I
fixed one; §11 asks for simple effects AND a rule for when the average may
stand for them, and I supplied the effects. Each time the item was reported
closed.

The generalisation worth keeping: a checklist built from someone's summary
inherits the summary's compression, and the thing that gets dropped is the
second half of a compound item.

## What is still derived rather than measured

`ncmin_exposure()` computes what each column asked for and what its tile
imposed, from the land mask and the manifest's two parameters. It is not an
emitted value: recording the kernel's own scalar would need a new overlay
anchor in the frozen file. The derivation is checkable against Arm L, whose
`partition` is exactly 0 at all four points in both units, and the function
refuses a stream that predates the `xland` record rather than guessing.
