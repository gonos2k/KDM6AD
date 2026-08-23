# `ncmin` cannot be the cause, because this case sets both thresholds equal

Owner authorisation, 2026-08-23, to build and run in the deployed tree. The
question was the one three findings left open: does Arm L remove the MPI
decomposition difference?

## The build

`module_mp_kdm6_lncmin.F` generated from the RUN tree's own kernel revision
(`a06c954b`), 21 lines changed, no line longer than that source already carries.
Built as a separate `wrf.exe`, never replacing the deployed one, which was
restored afterwards and verified.

Two checks came with it. The legacy rebuild is **bit-identical to the deployed
binary**, so that tree's toolchain is deterministic and the deployed binary
matches its own source. And the frozen kernel came back at its original digest.

## The result, and what it is not

One minute, `np = 1` against `np = 2` and `np = 4`, of 197 f32 time-varying
fields:

| arm | np = 2 | np = 4 |
|---|---|---|
| legacy | 75 | 77 |
| **Arm L** | **75** | **77** |

Identical counts, and identical field SETS -- `QNCCN` among them in every case.

That looks like a refutation of `ncmin` and it is not, because of the control
that has to come next:

**`legacy np = 1` and `Arm L np = 1` are bit-identical in all 197 fields.** The
arm did nothing at all. An intervention that changes nothing cannot fail to
change the difference, and reporting it as a refutation would be reading a null
instrument as a null result.

## Why the arm is inert, and what that settles

The case's namelist:

    ncmin_land = 10
    ncmin_sea  = 10

verified in the saved namelist of every MPI run in this campaign. The kernel's
branch is

    do i = its,ite
      if(slmsk(i).eq.2) then
         ncmin = ncmin_sea
      else
        ncmin = ncmin_land
      endif
    enddo

so with the two parameters equal, **every column asks for the same value** and
the scalar keeps the same number the array would have held. The per-column
correction is vacuous here, which is why Arm L changes nothing.

And that is the real result, stronger than the one the experiment was designed
to give:

> **`ncmin` cannot produce ANY decomposition dependence in these runs.** Its
> value is identical in every column and every tile, so it is identical under
> every decomposition. Whatever moves `QNCCN` at `np = 2`, it is not this.

The one-step evidence already pointed here -- `QNCLOUD` unchanged while `QNCCN`
alone moved -- and this settles it by construction rather than by inference.

## What it costs, and what a real test needs

Every MPI finding in this campaign ran with the two thresholds equal, so none of
them could have tested `ncmin` even in principle. That was not known and is now
recorded on them.

A test of Arm L against the decomposition needs a case with
`ncmin_land != ncmin_sea` and a mixed land-sea domain. This domain is mixed --
54.6 % sea, 45.4 % land -- so only the namelist has to change. That is a
different experiment from the ones already run and is not a re-analysis of them.

## Not claimed

The mechanism behind the `QNCCN` divergence remains unnamed;
`FINDING_qnccn_divergence_locus_v1` maps where it starts. Arm L's synthetic
decomposition result stands untouched -- that fixture sets the two thresholds
apart, which is exactly what makes the defect visible there and dormant here.
