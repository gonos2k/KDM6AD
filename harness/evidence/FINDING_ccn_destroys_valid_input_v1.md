# The first-timestep CCN block overwrites valid external `QNCCN` input

`FINDING_ccn_onetime_reference_v1` ended by saying that which CCN
implementation is correct "needs an external criterion for what the
first-timestep CCN field is SUPPOSED to be, which is a modelling decision and
not a measurement". The criterion exists, it is in the code, and one of the two
initialisers already violates it.

## The two guards

`start_em.F:1778` initialises the profile only when there is nothing there:

    ccn_max_val = wrf_dm_max_real ( ccn_max_val )
    IF ( ccn_max_val < 1.0 ) THEN ! initialization of ccn not already done

That guard, and its comment, are a statement of intent: **generate a profile
only in the absence of input.** It is also a distributed maximum, so the
decision is made for the whole domain rather than per rank.

`module_mp_kdm6.F` has no such guard. The block is entered on

    if (itimestep .eq. 1) then

and nothing else.

## The control

`wrfinput_d01` carries `QNCCN` identically zero, which is why the profile is
generated at all. Set it instead to a uniform `3.2100e+08` -- a value neither
land nor sea profile takes at any height, and constant in height, which no
profile is -- and run 20 s at `np = 1` on the deployed binary:

| output cells | share |
|---|---|
| at the analytic **profile** (input overwritten) | **85.41 %** |
| still at the **marker** (input preserved) | **0.01 %** |
| neither (microphysics has since moved them) | 14.58 % |

**The valid external field is destroyed.** `start_em` correctly stood down --
its guard saw `ccn_max_val = 3.21e8` and did nothing -- and the kernel block
overwrote the field anyway, one timestep later.

## What this settles

The three implementations compared in `FINDING_ccn_onetime_reference_v1` -- A
deployed, B tile bounds, C block removed -- disagree with each other at `np = 1`
in 75-76 of 197 fields, and nothing internal chose between them. This does:

    A and B  re-impose the analytic profile over whatever was supplied
    C        leaves start_em's decision standing, whichever way it went

Only C respects the guard that `start_em` already implements. That is not an
argument that C is right in every other way -- it inherits `start_em`'s coverage,
which leaves the domain's outermost ring unwritten, and it does not restore
decomposition invariance either. It is an argument that **A and B are wrong
about this**, from the model's own stated intent rather than from a preference.

## What is NOT established

Whether anything in this configuration supplies a real external `QNCCN`. This
case does not -- the field is zero, which is why the profile fires. The control
constructs an input that does not otherwise occur here, to ask what the code
would do with one. A coupled aerosol run or a restart would supply one, and
neither is run here.

Whether the overwrite changes a forecast when the input IS zero. It does not:
with `QNCCN = 0` on input the profile is what `start_em` would have written, so
A, B and C differ over the tiling and the halo, not over the field's origin
(`FINDING_ccn_overwrites_microphysics_v1`).

One case, one host, deployed revision `a06c954b`, `np = 1`, 20 s.

**Re-checked against the current deployed binary, 2026-09-02.** The 85.41 % / 0.01
% control above was measured on `a06c954b`. Since then the tile-bounds fix landed
in this block and the CCN loop bound in `start_em.F` was corrected, so the binary
is now `6797945d`. The defect itself is unchanged and the check is a source one:
`module_mp_kdm6.F:309` is still `if (itimestep .eq. 1) then` with no
`ccn_max_val` guard. Arm B arrived; the guard did not. The control was not
re-run, and would only re-measure a share the source already determines.
