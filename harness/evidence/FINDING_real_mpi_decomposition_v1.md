# The real 5 km forecast is not decomposition-invariant after one step

`partition` -- the count of final states that differ between one tile and
`(2,1)` -- has been an invariant measured on a three-column fixture. This is the
same question put to the real model: one 20 s step of the operational 5 km case
at MPI np = 1, 2 and 4, compared field by field.

## The control comes first

At `t = 00:00:00`, written by each run before any step, **all 197 f32
time-varying fields are bit-identical across all three decompositions.** So
whatever separates the runs is made by the step, not by initialisation, I/O
layout, or the comparison.

## The measurement

`host/lc05_da_run` -> `ss_real_case_20260619_063620/SS`, 235 x 283 x 40 at
dx = 5 km, `mp_physics = 37` (the Fortran KDM6), `time_step = 20`, adaptive
stepping off, one step, `history_interval_s = 20` so the terminal state is a
frame. All three runs exit 0 with `SUCCESS COMPLETE WRF` and two frames each.

| | fields differing at t = 0 | at t = 20 s | worst |
|---|---|---|---|
| np = 2 vs np = 1 | 0 of 197 | **1** | `QNCCN`, 9.800e-01 relative |
| np = 4 vs np = 1 | 0 of 197 | **28** | `REFL_10CM`, 1.917e+00 relative |

At np = 2 the single differing field is `QNCCN`, in 687 086 of 2 573 532 cells
(26.70 %), spread over all 39 levels, 232 of 234 west-east columns, and a
CONTIGUOUS band of south-north rows 71 to 211.

At np = 4 it has reached the dynamical state and the precipitation:

    FOGFRAC_SFC GRAUPELNC MU P PH QCLOUD QGRAUP QIB QICE QNCCN QNCLOUD
    QNICE QNRAIN QRAIN QSNOW QVAPOR RAINNC REFL_10CM RHO_ICE SNOWNC SR
    T THM U V VIS_SFC VIS_SFC_RAW W

**After one 20-second step, this forecast's precipitation and reflectivity
depend on how many MPI ranks it was run on.**

## What the mechanism is NOT established to be

`ncmin` is the obvious candidate: it is assigned inside a `do i = its,ite` loop
to a SCALAR (F:876-882), so only the last column of each tile survives, and a
tile is exactly what changes with np. That is the defect Arm L addresses.

It does not follow from this run, and saying it would be the kind of inference
this campaign has had to withdraw before. `ncmin` gates `nci(i,k,1)` -- CLOUD
droplet number, which surfaces as `QNCLOUD` -- and `QNCLOUD` is UNCHANGED at
np = 2, where `QNCCN` alone moves. Whatever sets `QNCCN` per tile is a different
site, and this finding does not name it.

What the np = 2 column does support, as inference and labelled as such: the
DYNAMICS is decomposition-invariant here. Not one of `U`, `V`, `W`, `P`, `T`
moves at np = 2, so the 28-field spread at np = 4 reads as a cascade out of the
column physics rather than as an independent dynamical-core np-dependence.

## Not claimed

One case, one initial time, one step, `mp_physics = 37`. Not a forecast-skill
statement and not a bound on how the spread grows: a 20-second difference in
`REFL_10CM` says the operator is decomposition-dependent, not how much a
three-hour forecast would move.

Nothing here measures Arm L. The corrected arm was not built into `wrf.exe`;
that is a separate freeze-lift and a separate campaign.

## Reproducing

    cd <SS run dir>
    python3 run_ss_case.py --mp 37 --minutes 0 --seconds 20 \
        --history 0 --history-s 20 --np <1|2|4> --label decomp --fixed-dt

The namelist needs a `history_interval_s` key for the step-granular frame; the
case did not carry one and it was added. `run_ss_case.py` in the run directory
was a STALE copy of the harness script -- it had neither `--seconds` nor `--np`
-- and was refreshed from `harness/run_ss_case.py`. One script in two places
drifts, and this is what the drift cost: the run directory could not express the
experiment the harness already supported.

## Which kernel this was

The binary is `KDM6AD+/KIM-meso_v1.0/main/wrf.exe`, built 24 Jun from kernel
revision `a06c954b`. That is NOT the SHA-pinned reference every fixture result
in this campaign uses (`9354141b`, in the repository tree): the two differ by
114 lines, none of them in `ncmin` or the interface transfer statements, so the
candidate mechanism is present in this binary -- but the revision is different
and was not stated. See `FINDING_two_wrf_trees_v1.md`.

## The `ncmin` candidate is ruled out for these runs

This case sets `ncmin_land = ncmin_sea = 10`, verified in the saved namelist of
every MPI run in this campaign. With the two equal, every column asks for the
same threshold and the scalar holds what the array would have held -- so
`ncmin` is identical under every decomposition and cannot produce a difference
between them. Confirmed directly: an Arm L binary is bit-identical to legacy at
`np = 1` on this case. See `FINDING_arm_l_mpi_null_v1.md`.

## Authority on the mechanism, as it now stands

    Initial seed         CONFIRMED -- the memory-bound CCN initialisation reads
                         unexchanged halo `delz`, which is 0.0 there
                         (FINDING_qnccn_first_write_v1.md)
    Propagation          OPEN -- seven seed rows, a 140-row terminal footprint,
                         and nothing measured in between
    Collapse on fixing   see FINDING_ccn_bounds_collapse_v1.md

This supersedes the sentence above that no mechanism is named. The seed is
named; what is unnamed is how it reaches the interior.
