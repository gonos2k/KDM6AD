# CORRECTED TWICE: the residual is three populations, and nothing is unwritten

This finding said the tile-bounds arm's remaining `np = 2` difference "IS" a set
of cells nobody writes. Two things in that were wrong and one was arithmetic I
did to myself.

## The residual is not one population

`QNCCN` at 20 s, tile-bounds binary, `np = 1` against `np = 2`, all 9 971
differing cells classified:

| | cells | `np = 1` value | `np = 2` value |
|---|---|---|---|
| exactly zero on one side | **7 595** | `0` | physical |
| neither exactly zero, `np = 1` negligible | **1 414** | median 7.6e-05 | physical |
| both physical (> 1e3) | **962** | physical | physical |

`7 595 + 1 414 + 962 = 9 971`.

And the 962 both-physical cells differ by a **median 7.17e-07** relative --
which is the same scale as the `np = 4` `dz8w` seam's 6.91e-07
(`FINDING_np4_seam_is_rounding_v1`), not the scale of a wrong value.

So "the residual IS that gap" was true of 76 % of it. A quarter of the residual
is cells that hold two different physical numbers, and most of those differ by
rounding.

## The three-cell discrepancy was mine

The finding reported the zero-count difference as 7 595 and "the same 7 598
counted the other way", and asked what the three cells were. There are none.
7 598 came from multiplying a printed, rounded 76.2 % by 9 971 -- back-computing
a count from a rounded percentage. Counted directly:

    zero at np = 1              11 152
    zero at np = 2               3 557
    difference                   7 595
    differing AND exactly one side zero   7 595      <- identical
    differing AND both sides zero              0      <- cannot differ
    zero at np = 1 but NOT differing       3 557      <- zero in both

## Measured: nothing is unwritten

The instrument needed no code. `start_em` initialises only when
`ccn_max_val < 1.0`, so replacing `wrfinput`'s identically-zero `QNCCN` with a
SENTINEL of `1e-30` -- a normal f32, far below that guard -- leaves the run
otherwise identical while making absence observable: a cell nobody writes keeps
`1e-30` instead of `0`.

Tile-bounds binary, 20 s:

| | never written (`= 1e-30`) | written zero (`= 0`) | written a value |
|---|---|---|---|
| `np = 1` | **0** | **11 152** | 2 562 380 |
| `np = 2` | **0** | **3 557** | 2 569 975 |

**Nothing is unwritten.** The sentinel survives in zero cells under either
decomposition, and the zero counts are exactly those measured with a zero input
-- 11 152 and 3 557. So every zero-valued cell is a cell something **wrote zero
into**, and the hypothesis this finding was named for is refuted.

The decomposition-dependence is therefore not "which cells are missed" but
**which cells are assigned zero**: the never-written sets are identical (0
against 0) and the written-zero sets differ by 7 595 cells.

WHAT WRITES THE ZERO is narrowed but not identified. The measurement distinguishes
"nobody wrote it" from "something wrote zero" and stops there; naming the writer
needs the per-stage instrumentation below, which this makes worth building for a
narrower question than the one it was proposed for.

## Why "unwritten" was not measured before

A cell holding zero can be a cell nobody wrote, a cell explicitly assigned zero,
a cell whose input was zero and was left alone, a cell a halo exchange filled
with zero, or a cell microphysics drove to zero. The output distinguishes none
of them. This finding inferred the first from the last and had no instrument for
it -- and when one was built, the first is the one the measurement rules out.

What IS measured: the set of zero-valued `QNCCN` cells depends on the
decomposition, 11 152 against 3 557. That is the claim; "unwritten" is a
hypothesis about its cause.

Deciding it needs write-coverage instrumentation -- a diagnostic array recording,
per cell, whether `QNCCN` was written at all and by which stage, rank and tile,
so the output can be classified

    never_written / written_zero / input_zero_retained / halo_received_zero

rather than assumed. That is not built here.

## What stands

The residual is `QNCCN` alone, 0.387 % of cells, and it is decomposition-
dependent. The tile-bounds arm does not remove the `np = 2` difference. Neither
does removing the block (`FINDING_ccn_onetime_reference_v1`).

One case, one build, one host, 20 s, deployed revision `a06c954b`.

## When the zeros appear, and where

The sentinel showed every cell is written. Two more cheap reads narrow when and
where, without instrumentation.

**They are not in the initial state.** `QNCCN` zeros at the output's frame 0 --
the state before any step -- and at frame 1:

| binary | `np` | zeros at frame 0 | zeros at frame 1 |
|---|---|---|---|
| A deployed (memory bounds) | 1 | **0** | 0 |
| A deployed | 2 | **0** | 0 |
| B tile bounds | 1 | **0** | 11 152 |
| B tile bounds | 2 | **0** | 3 557 |
| C block removed | 1 | **0** | 11 152 |
| C block removed | 2 | **0** | 3 557 |

So the zeros are made DURING the first step, and A shows none only because its
per-tile sweep rewrites the whole memory window at the end of that step and
covers them (`FINDING_ccn_overwrites_microphysics_v1`).

**And more ranks means FEWER zeros, in a smaller place.** Under B at one step:

    np = 1    11 152 zeros    i columns 1..234 (all 234), j rows 2..282
    np = 2     3 557 zeros    i columns {1, 234} only, j rows 2..141

`np = 2`'s zeros are confined to the domain's two edge COLUMNS, inside rank 0's
row range; `np = 1`'s are spread across every column. And `np = 2`'s set is a
strict subset of `np = 1`'s -- measured earlier as `zb & ~za = 0`.

That is the opposite of the naive expectation, which is why it is recorded
rather than explained. A story in which more decomposition means more unwritten
or mis-written cells does not survive it.

**Still open:** which stage assigns the zero. The measurements above say it is
not the initial state, it is within the first step, and its footprint shrinks
toward the domain edge as ranks are added. Naming the writer needs the
per-stage instrumentation described above, which is not built.
