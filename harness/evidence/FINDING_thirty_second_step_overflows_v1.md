# The OPERATIONAL call step drives `brs` to `-inf` on a real column

The timestep-matrix batch died on a real column. The cause was not the harness
(`FINDING_shared_fixture_contaminates_v1`, retracted); it is an unguarded
division in the kernel, reached when the call step is long enough.

## The measurement

`legacy`, five real columns from `mp37_traj_10min_hist1`, five call steps,
counting records whose decoded `f32`/`f64` payload is not finite:

| column | 5 s | 10 s | 20 s | 30 s | 60 s |
|---|---|---|---|---|---|
| (0, 100) | 0 | 0 | 0 | 0 | 0 |
| (59, 93) | 0 | 0 | 0 | 0 | 0 |
| (66, 105) | 0 | 0 | 0 | 0 | 0 |
| **(71, 147)** | 0 | 0 | **0** | **8** | **4** |
| (77, 80) | 0 | 0 | 0 | 0 | 0 |

The first record is

    G33F STAGE 1 - micro_post_melt 0 brs 1 26 f32 FF800000

`FF800000` is `-inf`. **The operational call step is 20 s and is clean on this
column**; the failure begins at 30 s.

## CORRECTED: the operational step is not clean

This finding said "the operational call step is 20 s and is clean on this
column", and later that "no WRF run in this campaign used a 30 s microphysics
step" as though that bounded the exposure. **Both generalised from one column.**

Column `(100,142)`, also land, swept finely:

| 5 s | 10 s | **15 s** | **20 s** | 30 s |
|---|---|---|---|---|
| 0 | 0 | **0** | **4** | 8 |

`G33F STAGE 1 - micro_post_melt 0 brs 1 27 f32 FF800000` at the 20 s step --
**the operational configuration.** So the threshold is a property of the column
and not of the scheme: `(71,147)` first fails at 30 s and `(100,142)` at 20 s,
and nothing measured here says where the next column fails.

The claim that operations sit inside a safe margin is withdrawn. What is
measured is that one of this sample's land columns produces a non-finite `brs`
at the step operations use.

## It is not one column, and it is land

Re-run over the whole 24-column selection at all four steps, the columns that
fail are:

    (71,147)  xland = 1      (88,130)  xland = 1
    (82,145)  xland = 1     (100,142)  xland = 1

**Four of the sample's five land columns**, and none of its eighteen sea
columns. The fifth land column, `(106,170)`, completes every step.

Land is where this case's graupel is: the melting term below is a graupel term,
and a sea column that never forms graupel never reaches it. So the pattern is
consistent with the site rather than an additional fact about land -- but it
does mean the defect is common in the part of the domain that has the ice phase,
not rare.

## The site

`module_mp_kdm6.F`, the graupel-melting block:

    1413    if(qrs(i,k,3).gt.qcrmin) then
    1414      gfac = (rslope(i,k,3))*n0go(i,k)/qrs(i,k,3)
    1415      nrs(i,k,1) = nrs(i,k,1) - gfac*pgmlt(i,k)
    1416    endif
    1417    qrs(i,k,3) = qrs(i,k,3) + pgmlt(i,k)
    1418    qrs(i,k,1) = qrs(i,k,1) - pgmlt(i,k)
    1419    t(i,k) = t(i,k) + xlf/cpm(i,k)*pgmlt(i,k)
    1420    brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))

and `rhox` is set to zero by the kernel itself where graupel is absent:

    1013    rhox(i,k) =0.

`rhox` is `intent(out)` -- a kernel-computed diagnostic, `qrs(:,:,3)/brs`, not
a host input -- so the driver initialising `rhoxk = 0.0` is not the source. The
kernel writes it.

**The guard that would prevent this is two lines above and closes before the
division.** `qrs(i,k,3) > qcrmin` is exactly the condition under which `rhox` is
computed rather than zeroed; the `nrs` line is inside it and the `brs` line is
outside.

## What is NOT measured

The values of `rhox` and `pgmlt` in that cell at that step. `-inf` rather than
`NaN` requires `pgmlt` to be nonzero with `rhox` zero, which is consistent with
the code above and is inferred from the sign, not read from a probe. Confirming
it needs a dump at that statement, which is not run here.

Whether it affects a forecast. `brs` is graupel bulk volume; a `-inf` there
propagates to `rhox` on the next diagnostic pass and to reflectivity. This
measures a harness replay of one column, not a WRF run, and no WRF run in this
campaign used a 30 s microphysics step.

Whether the other 18 columns of the sample do it. Five were scanned.

## Why it surfaced now

Only because the sample was re-run across call steps. At the 5 s step the
harness has always used, and at the 20 s operational step, this column is clean.
A defect that needs a longer step than anything in use is still a defect, and it
sits one `endif` away from being impossible.
