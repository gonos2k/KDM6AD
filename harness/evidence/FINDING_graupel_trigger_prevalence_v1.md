# How common the graupel-melt window is, and why the sample said "land"

The overflow's exposure was known only through a 24-column sample chosen for
rain-number depth. The review asked for the trigger population directly. Two of
the four conditions are measurable from a WRF output frame; the third is not,
and saying which is the point of this finding.

## Over the whole domain

`mp37_traj_10min_hist1`, `np = 1`, at ten minutes, 2 573 532 cells:

| condition | cells |
|---|---|
| `qg > 0` | 30 607 |
| `0 < qg <= qcrmin` | 2 580 |
| ... and `T > T0` | **987** |

**987 cells, 0.04 % of the domain**, in **217 of the 8 102 columns that carry
graupel -- 2.68 %.**

## The sample said land; the domain says sea

| | land | sea |
|---|---|---|
| trigger cells at 10 min | 248 | **739** |

The replay sample had four of five LAND columns failing and no sea column, and
that was read here as the defect living in land columns. **It does not.** Over
the domain it is three times more common at sea. The sample selected columns
carrying `QNRAIN` over at least six levels, and that selection is what leaned
land -- exactly the bias the review warned the prevalence numbers would correct.

## The volume condition CANNOT be tested this way

The full predicate also needs `brs <= brs_min`. Reconstructing `brs` as
`QGRAUP / RHO_ICE` from the output gives `brs = 0` in all 2 580 window cells,
which would make the condition look automatically satisfied. It is an artefact:
`RHO_ICE` is a DIAGNOSTIC export that is snapped to zero wherever
`qrs(i,k,3) <= qcrmin` -- the same threshold -- so the reconstruction returns
zero by the export's rule and not by the kernel's state.

    cells with 0 < qg <= qcrmin      2 580
      of those, RHO_ICE == 0         2 580
      of those, RHO_ICE  > 0             0

So **987 is an upper bound on the trigger population, not the population.** The
cells that also satisfy the volume condition are a subset of it, and measuring
that subset needs the kernel's `brs`, which no output field carries.

## What this does and does not establish

It establishes that the window is a real feature of this state at a rate of a
few percent of graupel-bearing columns, and that its land/sea skew is the
opposite of what the replay sample suggested.

It does not establish that a WRF run reaches the overflow. The replay drives the
kernel with fixed forcing; a forecast does not. Confirming exposure needs an
FPE trap or an instrumented statement in a full run, which is not done here.

One case, one time, one host. The `T > T0` test uses `T + 300` converted with
`(p/p0)^(Rd/Cp)`, which is the output's own convention and not the kernel's
internal temperature at the melt.
