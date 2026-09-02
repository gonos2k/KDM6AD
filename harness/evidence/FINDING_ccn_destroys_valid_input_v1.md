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
would do with one.

**A restart supplies one and does NOT trigger the overwrite**, which corrects an
earlier reading here that named it as a trigger. `qnn` carries `r` in its
Registry io flags, so it is written to and read from restart -- but so does
`itimestep`, whose flags are `rh`. `itimestep` therefore RESUMES across a restart
rather than resetting, so `if (itimestep .eq. 1)` does not fire on the first step
of a restarted segment. The restart path supplies the field and leaves it alone.

That narrows the exposure to a COLD START whose input carries `QNCCN` -- a
coupled aerosol initialisation, or any `wrfinput` that provides the field. That
is exactly what the marker control above constructs, and what it destroys.

**The NEST path is exposed, and worse than a cold start.** The chain is in the
source:

    mediation_integrate.F:671   CALL med_interp_domain( parent, nest )
    mediation_integrate.F:797   CALL start_domain ( nest , .TRUE. )
    solve_em.F:371              grid%itimestep = grid%itimestep + 1

`qnn` carries `d` and `=(bdy_interp:dt)` in its io flags, so it is interpolated
down to the nest: the nest receives its parent's EVOLVED `QNCCN`. `start_domain`
then runs `start_em` for the nest, whose guard sees that non-zero field and
correctly stands down. `itimestep` is per domain and `med_nest_initial` sets only
the PARENT's (the save/restore at 831/848), so the nest's stays at its allocation
default and its first `solve_em` makes it 1 -- and the unguarded kernel block
fires, replacing the interpolated field with the analytic profile.

So the nest discards not merely a supplied input but the parent's evolved state,
one step into the nest's life.

Established from the io flags and the call chain. **No nested run was made**, and
the nest's initial `itimestep` is the allocation default rather than a literal
assignment anyone wrote.

~~Whether the overwrite changes a forecast when the input IS zero. It does not:
with `QNCCN = 0` on input the profile is what `start_em` would have written, so
A, B and C differ over the tiling and the halo, not over the field's origin.~~

**That paragraph is WRONG and is withdrawn.** It has now been measured on the
corrected code and the overwrite changes the forecast substantially even with
`QNCCN = 0` on input -- see below.

One case, one host, deployed revision `a06c954b`, `np = 1`, 20 s.

**Re-checked against the current deployed binary, 2026-09-02.** The 85.41 % / 0.01
% control above was measured on `a06c954b`. Since then the tile-bounds fix landed
in this block and the CCN loop bound in `start_em.F` was corrected, so the binary
is now `6797945d`. The defect itself is unchanged and the check is a source one:
`module_mp_kdm6.F:309` is still `if (itimestep .eq. 1) then` with no
`ccn_max_val` guard. Arm B arrived; the guard did not. The control was not
re-run, and would only re-measure a share the source already determines.

## Arm C on the corrected code: the two initialisers write DIFFERENT profiles

Arm C is the kernel block removed -- one line, `if (itimestep .eq. 1)` made
false, binary `30e69d46` -- against the deployed `6797945d`, `np = 1`, one
minute, 197 fields:

    frame          0s   20s   40s   60s
    differing       0    11    74    76

At 20 s the first to differ are `QNCCN` itself and what it feeds: `QCLOUD`,
`QNCLOUD`, `QVAPOR`, `T`, `P`, `REFL_10CM`, `FOGFRAC_SFC`.

`QNCCN` alone:

    t = 0 s     0 of 2,573,532 cells differ          both start from start_em's profile
    t = 20 s    1,398,566 of 2,573,532 (54.3%)       i 2..233, j 2..281 -- domain-wide
                median |diff| 8.4e+04, max 3.4e+08

**Domain-wide in VALUE, not a coverage gap at the edge.** The kernel block does
not re-impose what `start_em` wrote; it imposes a different field.

The source says why, and the two halves agree. Both initialisers use the same
formula on `z_sum`, and they accumulate different thicknesses:

    start_em.F:1786          dz8w from phb + ph_2, at initialisation
    module_mp_kdm6.F:322     delz as passed at itimestep 1, after one dynamics step

which is exactly consistent with `QNCCN` being identical at `t = 0` and split by
`t = 20 s`.

So the policy question is not "which of two spellings of the same profile", and
the overwrite is not harmless when the input is zero. It is a second, different
initialisation applied one time step later, and removing it moves 76 of 197
fields at one minute.

Scope: one case, `np = 1`, one minute, this configuration. Whether Arm C is
RIGHT is unchanged by this -- it inherits `start_em`'s coverage, which leaves the
outermost ring unwritten. What changed is the size of what is at stake.

Tree restored afterwards: `module_mp_kdm6.F` `9354141b`, `main/wrf.exe`
`6797945d`.
