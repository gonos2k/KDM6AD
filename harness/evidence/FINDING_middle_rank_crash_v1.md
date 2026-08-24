# A rank with interior neighbours on both j sides crashes, and it is not the CCN block

`--proc-grid` was added to separate seam DIRECTION from rank COUNT
(`FINDING_seam_direction_and_1x4_crash_v1`). It found something else: one
decomposition does not run.

## The condition, isolated

    grid   ranks   outcome
    1x4      4     ranks 1 and 2 SIGSEGV; ranks 0 and 3 survive
    2x2      4     runs
    4x1      4     runs
    1x3      3     rank 1 SIGSEGV; ranks 0 and 2 survive
    3x1      3     runs

`1x3` against `3x1` is the discriminating pair: **same rank count, and the only
difference is whether any rank has an interior neighbour on BOTH j sides.**

| grid | rank | j patch | outcome |
|---|---|---|---|
| `1x3` | 0 | 1..94 | ok -- holds the southern domain boundary |
| | **1** | **95..188** | **SIGSEGV** |
| | 2 | 189..283 | ok -- holds the northern boundary |
| `3x1` | all | 1..283 | ok -- every rank holds both |

Every rank that dies is one with no physical j-boundary. `2x2` splits j in two,
so both its ranks still hold one; `4x1` gives every rank all of j. **`2x2` is
also what WRF chooses unaided, so no run in this campaign had ever produced a
middle rank.** The configuration was untested because the tool could not
express it.

## It is not the CCN block

Arm C -- the `itimestep == 1` CCN initialisation removed entirely, cut on an
exact multi-line anchor and verified balanced -- still crashes:

    arm C  1x3   exit 139, 1 rank SIGSEGV
    arm C  3x1   exit 0

So the halo read and the per-tile overwrite that block does commit
(`FINDING_qnccn_first_write_v1`, `FINDING_ccn_overwrites_microphysics_v1`) are
real and are **not** this. Two separate defects touching the same decomposition
machinery.

## What is known about where it dies

Before completing a step. The run writes its initial frame, every rank reaches
the W-damping banner at `2025-07-19_00:00:00`, and there is no second frame and
no error text. The backtrace prints addresses only -- "Could not print
backtrace: executable file is not an executable".

`mp137` crashes identically, so it is not specific to one KDM6 revision.
`mp237` exits 1 for an unrelated reason (`swint_opt=2` rejects that scheme) and
is not a control.

## Two hypotheses this does NOT separate

**KDM6 elsewhere**, in a routine reached on every rank but only fatal without a
physical j-boundary. **WRF infrastructure**, where a middle-rank halo pattern is
mishandled independently of the microphysics.

Telling them apart needs a scheme this configuration can actually run --
`swint_opt = 2` constrains the choice, and `run_ss_case` forces `mp_physics`
from `--mp`, so neither path is available without changing one of them. That is
the next step and it is not taken here.

## Not claimed

That this affects any run anyone makes. `1x4` and `1x3` are decompositions
nothing in this campaign or its operations selects; WRF's own choice at `np = 4`
is `2x2`. What it establishes is that a supported decomposition does not run,
and that the tooling could not previously ask.

One case, one build, one host, `np = 3` and `np = 4`.
