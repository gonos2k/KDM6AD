# How much of a real domain the scalar `ncmin` mis-thresholds

`ncmin` is a scalar set inside the column loop, so after the loop it holds the
value belonging to the LAST column of the tile, and every column in that tile
is thresholded by that one column's `xland`. Which columns are affected is
therefore a function of the GEOGRAPHY and the TILING alone -- no run, no
corrected arm, no change to frozen code.

## Measured — LC05 5 km analysis state, 2023-02-16

`host/lc05_da_run/wrfinput_d01`, 65,988 columns,
45.4 % land.

Columns handed a threshold belonging to the OTHER surface type:

| i-patches | mis-thresholded |
|---|---|
| 1 | 39.11 % |
| 2 | 29.79 % |
| 4 | 20.19 % |
| 8 | 14.01 % |

Finer tiling helps, because a shorter sweep means the last column speaks for
fewer others. That is not a fix: it means the ANSWER DEPENDS ON THE NUMBER OF
PATCHES.

Columns whose imposed threshold differs between two decompositions:

| pair | disagreeing |
|---|---|
| 1 vs 2 | 24.29 % |
| 1 vs 4 | 31.32 % |
| 1 vs 8 | 35.72 % |
| 2 vs 4 | 13.54 % |
| 2 vs 8 | 23.56 % |
| 4 vs 8 | 11.69 % |

Correct under all four tilings: **49.71 %**.

## Why the second table is the one that matters

If the affected set were the same under every decomposition the operator would
still be wrong, but it would at least be a FUNCTION OF THE STATE. It is not:
between one patch and eight, 35.7 % of columns
receive a different threshold from the same initial state and the same physics.

That is the review's Stage B hypothesis established from geography alone,
before any MPI run.

## What this is and is not

It IS the exposure: how many columns are handed a threshold from a column of
the other surface type, and how much that set moves when the decomposition
does.

It is NOT a rain difference, a precipitation change or a forecast impact. A
column is only ACTUALLY affected when its number concentration lies between
the two thresholds -- a column far from both branches the same way whichever
value it is given. Turning exposure into an effect needs the per-column arm,
which needs the freeze-lift (`REQUEST_freeze_lift_diagnostic_arms`), or the
real MPI one-step the review puts at Stage B.

## Limits

- One domain, one time. Coastal fraction drives this number and another case
  will differ.
- Equal i-patches. Real WRF decomposition is 2-D and not necessarily equal;
  this is the structure of the mechanism, not a prediction for a given run.
- `host/**` is private, so the measurement is reproducible only where that
  state exists. The tool's own properties are tested synthetically and run
  everywhere.

## Exposure is not effect: where the threshold can actually bite

A column is only ACTUALLY affected when its number concentration sits between
the two thresholds. Outside that band it branches the same way whichever value
it is handed, so the exposure above is an upper bound and the band is what
narrows it.

Two states were checked, and neither supports narrowing it here:

| state | `QNCLOUD` | in band (2.5e7 .. 1.0e8) |
|---|---|---|
| `lc05_da_run/wrfinput_d01` (5 km analysis) | identically zero | — |
| `KIM-meso_v1.0/run/wrfout.137.ieee.nc` (ideal, 41x41) | 0.13 % of cells non-zero, median 4.0e9 | **0 cells** |

The LC05 analysis carries hydrometeor MASS (`QCLOUD` 26 %, `QICE` 12 %) but
its number arrays are identically zero: it has not been spun up through a
double-moment scheme, so it cannot answer this question at all.

The ideal run does carry number, and there the cloud concentration is one to
two orders of magnitude ABOVE both thresholds. `ncmin` is a floor, so nothing
in that state is near it.

### What that means, and what it does not

It does NOT weaken the mechanism: the threshold is still decided by another
column, and the imposed value still moves with the decomposition — that is a
property of the operator, established from geography.

It DOES relocate where the mechanism can matter. The synthetic fixture
`boundary_mapping_v1` places the concentration between the thresholds ON
PURPOSE, which is what makes the +/-21 % rain difference visible there. For a
real state to show it, the concentration has to fall to the threshold's own
scale — thin or dissipating cloud, ice initiation, the edges of a field —
not the cores these two states are dominated by.

So the honest bound today is: exposure 39 % of columns, sensitivity NOT
DEMONSTRATED on either state available here. Closing that needs a spun-up
double-moment state over mixed coast — the review's Stage B — and no amount
of analysis of these two files will substitute.
