# The one-time-initialisation reference does not collapse the difference either

The review asks for a gold reference: initialise `QNCCN` once over the owned
patch, exchange if needed, then run microphysics on every tile --

    X^1 = M_all( I_owned(X^0) )

-- and says that if the tile-bounds arm matches it, the correction is closed.

## Arm C is a deletion

`start_em.F:1778` already does exactly `I_owned`: guarded by
`ccn_max_val < 1.0`, over `jts,MIN(jte,jde-1)` and `its,MIN(ite,ide-1)`, once.
So the reference is the kernel with its `itimestep == 1` block **removed** --
eighteen lines deleted, nothing written. Arm C is that binary.

## Three implementations

| | `np = 2` | `np = 4` |
|---|---|---|
| **one step (20 s)** | | |
| A deployed, memory bounds | 1 | 28 |
| B tile bounds | 1 | 28 |
| C block removed | **8** | 28 |
| **one minute** | | |
| A deployed, memory bounds | 75 | 77 |
| B tile bounds | **49** | 77 |
| C block removed | 66 | **76** |

**None of them collapses.** The reference implementation is not
decomposition-invariant either, so the tile-bounds arm cannot be closed by
matching it -- there is nothing there to match.

## Two things this does settle

**`np = 4` is not about the CCN block at all.** 28 fields at one step and 76-77
at one minute, under all three treatments including the one where the block does
not exist. That is independent confirmation of
`FINDING_np4_seam_is_rounding_v1`, which located the `np = 4` difference in
`dz8w` at the patch seam, upstream of microphysics and out of its reach.

**The per-tile overwrite was MASKING something, not only causing.** Arm C is
WORSE at `np = 2` at one step -- 8 fields against 1. Removing the overwrite
cannot introduce a difference; it can only stop hiding one. Under A and B the
block runs at the end of the first step and rewrites `QNCCN` from the analytic
profile, so whatever the step did to `QNCCN` before that is discarded. Arm C
lets it through. A fix that makes a symptom worse is evidence about the causal
chain, not a failed fix.

## And the question the reference was supposed to answer is now sharper

At `np = 1`, where there is no decomposition at all, the three implementations
disagree with **each other**:

    A vs B    75 of 197 fields
    A vs C    76
    B vs C    76

Three different single-rank trajectories. So "which of these is the physically
intended reference" cannot be settled by internal consistency or by agreement
between them -- it needs an external criterion for what the first-timestep CCN
field is SUPPOSED to be, which is a modelling decision and not a measurement.
This experiment did not answer the question; it made it exact.

## Not established

What `QNCCN` is decomposition-dependent THROUGH under arm C. The candidate is
that its halo is never exchanged after `start_em` sets it, but the code does not
settle it: `HALO_EM_INIT_5.inc`, which carries `scalar`, appears at
`start_em.F:1435` -- BEFORE the CCN block at 1778 -- and again at 2016 and 2562,
which may or may not be on the same execution path. Deciding it needs the branch
trace, not a grep, and that is not run here.

Nor which implementation is correct. Arm C inherits `start_em`'s own coverage,
which leaves the domain's outermost ring (`i` = 1, 234; `j` = 1, 282) at its
input value, because that block uses tile bounds too.

One case, one build, one host. The deployed revision `a06c954b` throughout; the
repository revision `9354141b` carries B's bounds and was not rebuilt here.
