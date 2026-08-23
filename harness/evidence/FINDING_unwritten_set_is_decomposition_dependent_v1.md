# What the tile-bounds arm leaves at `np = 2` is an unwritten set that moves

`FINDING_ccn_bounds_collapse_v1` measured that after the tile-bounds fix,
`np = 1` and `np = 2` still differ at one step in exactly one field, `QNCCN`, in
0.39 % of cells, and did not name the site. Named, it is not a wrong value
anywhere -- it is a set of cells NOBODY WRITES, and which cells those are
depends on the decomposition.

## Every differing cell has a zero on one side

`QNCCN` at 20 s, `np = 1` against `np = 2`:

| | differing cells | zero at `np = 1` | zero at `np = 2` |
|---|---|---|---|
| B tile bounds | 9 971 (0.387 %) | 76.2 % | 0.0 % |
| C block removed | 44 410 (1.726 %) | 17.1 % | 0.0 % |

And counting zeros directly:

| binary | `np = 1` | `np = 2` | `np = 4` |
|---|---|---|---|
| A deployed, memory bounds | **0** | 0 | 0 |
| B tile bounds | **11 152** | 3 557 | 3 557 |
| C block removed | **11 152** | 3 557 | 3 557 |

The deployed sweep writes every cell, because it runs over memory bounds. Both
corrected arms leave cells unwritten, and **leave 7 595 more of them at `np = 1`
than at `np > 1`** -- which is 76.2 % of B's 9 971 differing cells, the same
7 598 counted the other way. The residual IS that gap.

## Not garbage

An earlier reading of this took the extreme relative differences -- median
5.7e+09, max 6.6e+44 among the both-nonzero cells -- as a sign of uninitialised
memory. It is not. Across all three binaries and all three rank counts `QNCCN`
spans `0` to `5.16e+09`, with no cell above `1e+11`; the huge ratios come from
denominators that are denormal-small and nonzero, not from a value that should
not exist. Measured before claimed, and the claim did not survive.

## What is NOT established

**Why the unwritten set depends on the decomposition.** The tile unions look
identical: `np = 1` covers `j` = 2..142 and 143..281, `np = 2` covers 2..71,
72..141, 142..212 and 213..281 -- both 2..281 -- and `i` is 2..233 either way.
An identical union should leave an identical remainder, and it does not. Either
the tiles are not what the probe's first-timestep record implies for every
call, or something else writes `QNCCN` in a decomposition-dependent pattern.
This finding localises the residual and does not explain it.

**Which behaviour is right.** A cell no tile owns keeping its input value may be
correct; `FINDING_ccn_onetime_reference_v1` shows the three implementations
disagree at `np = 1` anyway, so this cannot be settled from inside.

One case, one build, one host, 20 s, deployed revision `a06c954b`.
