# The CCN block runs once per TILE and overwrites the microphysics it follows

Two things were open. `FINDING_second_decomposition_defect_v1` measured that at
`np = 2` **zero owned cells differ** at the CCN write, yet one step later 75
fields differ and `QNCCN` differs over 140 rows. And
`FINDING_qnccn_divergence_locus_v1` left one row unexplained: `j = 142`, the
only row inside that band that agrees.

Both have the same answer, and it is not propagation.

## The mechanism

The block is guarded by `itimestep == 1` -- not by anything that makes it run
once. `kdm6` is called once per TILE, so at the first timestep the block runs
once per tile, and each run rewrites `nn` over the whole MEMORY window.

The pack, the kernel and the write-back that follow it all use tile bounds:

    do j = jts,jte
      do k = kts,kte
        do i = its,ite
          nci(i,k,3) = nn(i,k,j)        ... kdm62D ...
          nn(i,k,j)  = nci(i,k,3)

So tile 1 updates `QNCCN` on its own rows, and then **tile 2's CCN sweep
overwrites those rows back to the analytic profile.** Only the LAST tile's rows
keep the microphysics update. Which rows those are is a property of the tiling,
and the tiling is a property of the decomposition.

## The prediction, and the measurement

Tiles, from the probe:

    np = 1  rank 0    2..142, 143..281
    np = 2  rank 0    2..71,  72..141
            rank 1    142..212, 213..281

Rows keeping their update are the last tile's of each rank:

    np = 1   143..281
    np = 2   72..141  and  213..281

The symmetric difference of those two sets is what must differ:

    predicted   140 rows, spanning 72..212, with one interior gap at j = 142
    observed    140 rows, spanning 72..212, with one interior gap at j = 142

`j = 142` agrees because it is overwritten under BOTH decompositions -- it is
inside `np = 1`'s first tile and is `np = 2` rank 1's first tile's own row. The
one anomaly the locus map could not explain is a consequence of the account,
not an exception to it.

## What this settles

**The `np = 2` output difference is not the halo seed propagating.** The halo
seed is real -- `FINDING_qnccn_first_write_v1` measures it -- but it lives in
cells no rank owns, and this is what reaches the output. Two defects in one
block:

    1. it reads `delz` and `xland` over memory bounds, including an
       unexchanged halo
    2. it RUNS once per tile and writes over memory bounds, so it undoes the
       microphysics update of every tile but the last

The repository tree's tile-bounds fix addresses both at once: a sweep confined
to `its:ite/jts:jte` reads no halo and can overwrite no other tile's rows. That
is consistent with the measured `np = 2` improvement from 75 differing fields to
49.

It does not reach zero, and `FINDING_second_decomposition_defect_v1` shows why
for `np = 4`: `delz` itself differs in owned cells at the i-seam, upstream of
this block. What remains at `np = 2` after the fix is not identified here.

## Not claimed

That the overwrite is wrong in intent. Re-imposing a CCN profile at the first
timestep may be deliberate; what is not deliberate is that WHICH rows keep the
microphysics update depends on how the domain was divided.

One case, one host, one revision -- the deployed `a06c954b`. The repository
revision `9354141b` carries tile bounds and does not have this shape.
