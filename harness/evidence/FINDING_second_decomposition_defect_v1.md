# Two decomposition dependencies, not one, and only one of them is the CCN loop

`FINDING_ccn_bounds_collapse_v1` measured that the tile-bounds fix takes
`np = 2` from 75 differing fields to 49 and leaves `np = 4` at 77. The probe
explains both numbers, and the second one is a defect the CCN loop has nothing
to do with.

## Owned cells are the right comparison

The probe writes over the memory window, so a cell appears in several ranks'
files: once as owned, and once per neighbour that halos it. Comparing whichever
copy comes first mixes the two. Taking each cell from the rank whose TILE
contains it -- its owned value -- the picture separates:

| | owned cells compared | `nn` differs | `delz` differs |
|---|---|---|---|
| `np = 1` vs `np = 2` | 2 598 400 | **0** | **0** |
| `np = 1` vs `np = 4` | 2 598 400 | **16 741** | **26 863** |

## `np = 2`: the seed is entirely in the halo

Zero owned cells differ at the write. Everything
`FINDING_qnccn_first_write_v1` found -- the seven rows `j = 135..141` -- is in
rank 1's halo, which no rank owns. The owned state leaving the CCN block is
bit-identical to `np = 1`.

That is why the tile-bounds fix helps here: it stops the block writing those
halo cells at all, and the difference falls from 75 fields to 49. What remains
is whatever consumed the bad halo before it was exchanged, which this does not
identify.

## `np = 4`: `delz` itself already differs, before the block runs

`np = 4` is a 2x2 decomposition -- memory windows `i -4..124` and `i 111..240`
crossed with `j -4..148` and `j 135..288` -- so it has an i-seam that `np = 2`
does not. The owned differences sit exactly there:

    nn    differing i columns (21): 111..123, 225, 227..233
    delz  differing i columns (22): 110..123, 225, 227..233

with tiles at `i = 2..117` and `118..233` in a domain of `1..234`. Columns
110-123 straddle the i-split; 225-233 sit against the eastern edge.

**And `delz` differs in OWNED cells.** `dz8w` is an input to the CCN block, not
an output of it, so this difference exists before the block runs and no change
to that block's loop bounds can remove it. That is precisely why the fix left
`np = 4` at 77 fields while it moved `np = 2`.

So there are two dependencies:

    1. the CCN block reading unexchanged halo forcing   -- np = 2 rides on this
    2. dz8w differing in owned cells at an i-seam       -- np = 4 also has this

and only the first is what the repository tree's fix addresses.

## The seventh row, closed

`FINDING_qnccn_first_write_v1` left `j = 141` open: `nn` differed there while
`delz` matched. It is **`xland`**. The probe records it, and at `j = 141` the
land mask differs between the two runs while the thickness does not -- so the
profile takes the land branch in one and the sea branch in the other, in 2 600
of that row's 9 800 cells.

The block reads `xland(i,j)` over memory bounds for the same reason it reads
`delz`, and the halo mask is no more valid than the halo thickness.

Recomputing `nn` from each run's OWN recorded `delz` and `xland`, in f32,
reproduces the emitted values with a maximum relative error of **0.000e+00** at
`j = 140`, `141` and `142`. `nn` is a pure function of those two inputs, so
every differing cell is a cell whose inputs differ, and the account is complete:

    j = 135..140    delz differs (halo, zero) and xland differs
    j = 141         xland differs, delz does not

## Not claimed

Why `dz8w` differs in owned cells at an i-seam. That is upstream of the
microphysics and this finding only locates it.

And what carries the `np = 2` halo seed into the interior, which remains the
open question from `FINDING_qnccn_first_write_v1`: zero owned cells differ at
the write, yet 75 fields differ one minute later.
