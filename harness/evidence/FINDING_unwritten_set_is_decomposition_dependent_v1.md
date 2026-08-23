# CORRECTED: the `np = 2` residual is three populations, and "unwritten" was not measured

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

## "Unwritten" is not measured

A cell holding zero can be a cell nobody wrote, a cell explicitly assigned zero,
a cell whose input was zero and was left alone, a cell a halo exchange filled
with zero, or a cell microphysics drove to zero. The output distinguishes none
of them. This finding inferred the first from the last and had no instrument for
it.

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
