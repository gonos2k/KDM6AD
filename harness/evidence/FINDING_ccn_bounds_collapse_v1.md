# The tile-bounds fix does not collapse the difference, and it is not inert at np=1

`FINDING_qnccn_first_write_v1` located the first divergence: the `itimestep == 1`
CCN initialisation loops over MEMORY bounds and reads halo `delz`, which is
`0.0` because the halo has not been exchanged. The repository tree's kernel
revision already carries the fix -- tile bounds instead of memory bounds -- with
a comment stating that "np1 results are unchanged".

This applies those three bound changes to the DEPLOYED revision `a06c954b` and
measures both claims.

## The collapse test

One minute, `np = 1` against `np = 2` and `np = 4`, of 197 f32 time-varying
fields:

| binary | np = 2 | np = 4 |
|---|---|---|
| deployed (memory bounds) | 75 | 77 |
| **+ tile-bounds fix** | **49** | **77** |

**The difference does not collapse.** It shrinks by a third at `np = 2` and is
unchanged at `np = 4`. So the CCN halo seed is a real contributor and is not the
whole cause: at least one other decomposition-dependent site remains.

## And the fix is not inert at `np = 1`

The comment's second claim is that tile-interior values are identical, because
`z_sum` is a per-column recurrence. Measured, deployed against fixed, both at
`np = 1`:

    75 of 197 fields differ
    QNCCN   633 767 of 2 573 532 cells, in all 282 rows
    T       168 rows

That is the whole domain, not an edge. The recurrence argument is right about
the RANGE -- the probe records `mem k 1..40` against `tile k 1..39`, the same
start, so `z_sum` is identical for every output level -- and it does not cover
the horizontal:

    mem i -4..240    tile i 2..233     domain i 1..234
    mem j -4..288    tile j 2..281     domain j 1..282

**The tile loops never reach the domain's outermost ring.** `i = 1`, `i = 234`,
`j = 1` and `j = 282` are written by the memory-bounds loop and not by the
tile-bounds one, so under the fix they keep whatever `QNCCN` came in as -- zero,
from this case's `wrfinput`.

An unwritten edge ring is four lines of cells, and the measured difference is
24.6 % of them. What carries it inward over three timesteps is not established
here, and the same question is open for the seven-row halo seed.

## Measured at one step: what the fix changes, and what it leaves

The one-minute numbers above are three steps in. Re-run for a single 20-second
step, three things resolve.

**Why the fix changes `np = 1`: the overwrite, not the ring.** Deployed
against fixed, single rank, one step: only `QNCCN` differs, in 32.2 % of cells.
In those cells the deployed value is exactly the analytic profile 96.5 % of the
time and the fixed value never is. The deployed binary's per-tile sweep
(`FINDING_ccn_overwrites_microphysics_v1`) reverts the first tile's
microphysics update; the fixed binary keeps it. The "unwritten ring"
explanation given above was wrong -- `start_em.F:1779` initialises the ring and
the kernel block never needed to -- and is withdrawn.

**Why the fix does nothing at `np = 4`: the dynamics.** One step, fixed
binary, `np = 1` against `np = 4`: 28 fields differ and they are `U`, `V`, `W`,
`PH`, `T`, `THM`, `MU`, `P` -- the dynamical core's own prognostics -- at
i-columns 109..125, the seam between patches `2..117` and `118..233`, over every
row. `MU` is the dry column mass. No microphysics change can reach that; it is
the same i-seam where `delz` was found to differ in owned cells, one layer
further upstream.

**What remains at `np = 2`: located, not explained.** One step, fixed binary:
exactly one field, `QNCCN`, in 9 971 cells (0.39 %), spread over every level
and every column, every row except `1` and `133..138`. In every differing cell
one decomposition has `QNCCN = 0` and the other does not; neither equals the
profile. That is the residual the fix leaves at `np = 2`, and this finding does
not name its site.

## What this means for the repository tree

The fix in revision `9354141b` was applied here to a DIFFERENT revision
(`a06c954b`), so this does not measure that tree's binary. What it does show is
that the two claims attached to the fix -- that it removes the `np > 1`
divergence and that it leaves `np = 1` unchanged -- are both worth checking on
the tree that carries it, because neither held here.

## Not claimed

That the fix is wrong. Leaving the boundary ring to its input value may be
correct if the ring is overwritten from the boundary file before it is used;
this measures that it is NOT overwritten within one minute of this case, and
nothing about whether it should be.

One case, one minute, one host. The remaining `np = 4` difference is unmeasured
as to site.
