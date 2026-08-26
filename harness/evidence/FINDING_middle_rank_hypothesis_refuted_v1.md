# The middle-j-rank hypothesis is refuted, and the discriminator is not j alone

`FINDING_seam_direction_and_1x4_crash_v1` and the last review both graded
"a middle j-rank, with an interior neighbour on both j sides" as the **strong
candidate** cause of the SIGSEGV. The review named `2x3` against `3x2` as the
control that would separate it from orientation. It was run, and it separates
the hypothesis from the data.

## The control

`np = 6`, twenty seconds, `--proc-grid` confirming `requested == actual` on both.

| grid | rank | i patch | j patch | tiles | |
|---|---|---|---|---|---|
| `3x2` | 0 | 1-78 | 1-141 | 2 | ok |
| `3x2` | 1 | 79-156 | 1-141 | 2 | ok |
| `3x2` | 2 | 157-235 | 1-141 | 2 | ok |
| `3x2` | 3 | 1-78 | **142-283** | 2 | **CRASH** |
| `3x2` | 4 | 79-156 | **142-283** | 2 | **CRASH** |
| `3x2` | 5 | 157-235 | **142-283** | 2 | **CRASH** |
| `2x3` | 2 | 1-117 | **95-188** | 2 | **CRASH** |
| `2x3` | 3 | 118-235 | **95-188** | 2 | **CRASH** |
| `2x3` | 0,1,4,5 | — | 1-94, 189-283 | 2 | ok |

**`3x2` cuts j into TWO bands. Neither is a middle band** -- each touches a
physical j boundary -- and three ranks still crash. That alone refutes the
hypothesis as stated.

## And the same j patch decides differently under a different i cut

| grid | i patch | j patch | |
|---|---|---|---|
| `2x2` rank 2 | 1-117 | 142-283 | **ok** |
| `3x2` rank 3 | 1-78 | 142-283 | **CRASH** |

Identical j decomposition, identical tile count, opposite outcome.

**And at identical run settings**, which the first version of this table did not
have: `2x2` was originally a one-minute `--history 1` run and `3x2` a
twenty-second `--history 0` one, so "2x2 survives" could have meant only that it
had not yet reached the fault. `2x2` was re-run at the crashing configuration's
exact settings -- `--minutes 0 --seconds 20 --history 0` -- and exits **0**.
`4x1` likewise. The confound is removed. The
discriminator is therefore a **joint (i, j) patch property**, not a property of
where a rank sits in j.

## What the crashing patches have in common

Every crashing band contains or begins at **row 141/142**, the domain's middle
row (`jde = 283`):

    3x2   j 142-283   begins at 142
    2x3   j  95-188   contains 141
    1x3   j  95-188   contains 141
    1x4   j  71-141 and 142-212   the two that crash

and every surviving band either ends at 141 (`1-141`) or spans the whole domain
(`1-283`, in `3x1` and `4x1`, which run).

**Row 141 is already on this campaign's record**: it is where the `QNCCN`
memory-boundary halo writes were traced and fixed. That is a lead, not a
conclusion -- the CCN block was already excluded as the cause by Arm C, which
crashed identically with it removed.

## Grading, revised

| claim | before | now |
|---|---|---|
| a supported decomposition SIGSEGVs | CONFIRMED | CONFIRMED |
| middle-j-rank topology is the cause | STRONG CANDIDATE | **REFUTED** |
| the discriminator is joint (i, j) | — | **MEASURED** |
| KDM6 is the cause | OPEN | OPEN |

## What to do next, now that the cheap hypothesis is gone

The `2x2` / `3x2` pair is the tightest control this campaign has: same j
decomposition, same tiles, same binary, one crashes. A debug build
(`-g -O0 -fcheck=bounds -fbacktrace -ffpe-trap=invalid,zero,overflow`) run on
`3x2` alone, with the backtrace resolved, would name the statement. That is a
smaller experiment than the grid sweep because the pair is already isolated.
