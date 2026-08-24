# The seam's direction does not change the size, and one decomposition does not run

`FINDING_mpi_growth_is_not_distinguishable_v1` bounded the SIZE of the `np = 4`
difference and left open whether the difference is a property of the SEAM'S
GEOMETRY. `run_ss_case --proc-grid` now expresses that control: the same rank
count with the domain cut a different way.

## Direction does not change the size

`np = 4`, one minute, against the `np = 1` baseline, of 197 f32 time-varying
fields:

| grid | seams | fields differing |
|---|---|---|
| `2x2` | one i-seam and one j-seam | **77** |
| `4x1` | three i-seams, no j-seam | **77** |
| `1x4` | three j-seams, no i-seam | *did not run -- see below* |

`2x2` is also what WRF chooses unaided, so every `np = 4` result in this
campaign was a `2x2`.

**Identical counts, and not the identical difference:** `2x2` against `4x1`
differs in **78** of 197 fields. Each cut produces the same amount of divergence
and a different divergence.

That is what a rounding-scale seed amplified by the flow looks like, and not
what a defect tied to a particular seam looks like -- a geometry-specific fault
would make three i-seams differ from one. It is the second independent line on
the same question: the first was that a one-ULP perturbation of one prognostic
reaches as many fields as the decomposition does.

The footprints are both domain-wide, which is the same reading:

    2x2   225 067 cells   j rows 2..281   i cols 2..233
    4x1   292 905 cells   j rows 2..281   i cols 2..233

## `1x4` does not run

    1x4   exit 139 (SIGSEGV)
    2x2   exit 0
    4x1   exit 0

WRF accepted the decomposition -- `Ntasks in X 1, ntasks in Y 4` is in the log --
and died before completing a step: the run wrote its initial frame and never
produced a second one. The last line is the ordinary W-damping banner, with no
error text.

**`1x4` is the only decomposition here where a rank owns the domain's full
width.** Every halo defect this campaign has found sits on an i- or j-patch
boundary, and this is the arrangement with no i-boundary at all. That is a
coincidence worth recording and is NOT a diagnosis -- nothing here identifies
what faults.

## Not claimed

That `1x4` is broken by the kernel. A crash under one decomposition can come
from anywhere in the model, and no probe was run.

That direction is irrelevant to the seam question generally. Two grids ran, one
did not, and both survivors put an i-seam in play -- `1x4`, the only pure
j-cut, is exactly the case that could have separated them and is the one
missing.

One case, one build, one host, `np = 4`, one minute. Binary `a40bd80fae33`,
recorded in each run directory.
