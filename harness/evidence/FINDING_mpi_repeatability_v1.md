# The same decomposition reproduces exactly, and np=2 is not a smaller np=4

`FINDING_real_mpi_decomposition_v1` and `FINDING_mpi_trajectory_growth_v1`
compared one run at `np = 1` against one run at `np = 4` and attributed the
difference to the decomposition. One run against one run cannot separate that
from run-to-run nondeterminism -- a reduction order that varies, an
uninitialised local, anything timing-dependent -- and the `t = 0` bit identity
those findings rest on controls the INITIALISATION, not the integration.

This is the control that was missing, and the `np = 2` trajectory the one-step
result asked for.

## Within a decomposition

Two runs of the same case at each rank count, one minute, same host, same
build, `mp_physics = 37`, adaptive stepping off. Of 197 f32 time-varying fields:

| | fields differing |
|---|---|
| `np = 1` twice | **0 of 197** |
| `np = 2` twice | **0 of 197** |
| `np = 4` twice | **0 of 197** |

**Bit-identical, at every rank count.** So `D_within = 0` exactly, not merely
small, and the attribution criterion `D_between >> max D_within` is satisfied in
the strongest form it can be.

## Between decompositions

Same one minute, same runs:

| | fields differing |
|---|---|
| `np = 1` vs `np = 2` | 75 of 197 |
| `np = 1` vs `np = 4` | 77 of 197 |

**The decomposition causes the difference.** That is now a measurement rather
than an inference from a single pair.

## And `np = 2` is not a smaller effect

The one-step finding reported that `np = 2` differed from `np = 1` in exactly
ONE field, `QNCCN`, while `np = 4` differed in 28. That reads as an effect that
grows with rank count. It is not:

| | `np = 2` | `np = 4` |
|---|---|---|
| fields differing, 1 min | 75 | 77 |
| fields differing, 10 min | 105 | 106 |
| `RAINNC` signed domain sum, 10 min | +4.797e-01 mm | +1.680e-01 mm |
| `RAINNC` gross domain sum | 1.252e+01 mm | 1.386e+01 mm |
| columns over 0.1 mm | 0.042 % | 0.048 % |
| `REFL_10CM` screened p99 | 0.784 dBZ | 0.803 dBZ |
| cells over 20 dBZ (`np = 1`: 47 408) | 47 471 | 47 456 |

**Three** independent runs at each rank count, not two: all nine pairwise
comparisons (three per rank count, at `np` = 1, 2 and 4) are bit-identical
across all 197 f32 time-varying fields. `D_within = 0` exactly, and
`D_between` is unchanged at 75 fields for `np = 2` and 77 for `np = 4`.

By one minute the two are indistinguishable in scale, and they stay so for ten.
The single-field `np = 2` result was the SEED, one step in, and it cascades to
the same place.

**So the effect is not proportional to the number of tiles.** It fires as soon
as there is more than one MPI patch.

The first version of this said "tile boundary", and the instrumentation that
followed showed that is the wrong word. `np = 1` is ALREADY two physics tiles --
`jts..jte` of 2..142 and 143..281 -- and it is bit-identical to itself. What
`np = 2` adds is not a second tile but a second MPI PATCH, and with it a memory
halo that `np = 1` does not have inside the domain. The boundary that matters is
the patch/halo one (`FINDING_qnccn_first_write_v1.md`).

## What is still not established

The MECHANISM. `ncmin` remains the obvious candidate and remains unnamed here
for the reason `FINDING_real_mpi_decomposition_v1` gave: it gates cloud droplet
number, and at `np = 2` one step in, `QNCLOUD` was unchanged while `QNCCN` alone
moved. What sets `QNCCN` per tile is a different site.

And whether Arm L removes it. That needs a diagnostic `wrf.exe` built with the
`lncmin` kernel -- as a SEPARATE executable, not by replacing the operational
binary, which is the shape the next experiment should take.

One case, one initial time, one host. The repeatability result is about this
build on this machine; a different MPI library or thread count is a different
question.

## Reproducing

    cd <SS run dir>
    for n in 1 2 4; do for r in a b; do
      python3 run_ss_case.py --mp 37 --minutes 1 --seconds 0 \
          --history 1 --history-s 0 --np $n --label "rep$r" --fixed-dt
    done; done

then `g33_mpi_divergence.py <run_a> <run_b>`.

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

## Authority, as of the arm-C round

Superseded readings are kept in the sections above so the correction is legible;
this table is what the evidence now says. Where they disagree, this table wins.

| | grade |
|---|---|
| Same decomposition reproduces exactly (`D_within = 0`, 3 runs x 3 rank counts) | CONFIRMED |
| Different decompositions diverge (`D_between` = 75 / 77 fields at 1 min) | CONFIRMED, one case and build |
| Deployed `np = 2`, one-step `QNCCN` band | CONFIRMED -- per-tile whole-memory reinitialisation, `FINDING_ccn_overwrites_microphysics_v1` |
| Halo input defect (`delz` and `xland` read unexchanged) | CONFIRMED -- `FINDING_qnccn_first_write_v1` |
| Tile-bounds fix removes the `np > 1` difference | REFUTED -- 75 to 49, and 77 unchanged |
| Tile-bounds fix leaves `np = 1` unchanged | REFUTED -- 75 of 197 fields |
| `np = 2` residual after the fix | OPEN -- `QNCCN` alone, 0.39 % of cells |
| `np = 4` upstream `dz8w` seam difference | MEASURED; source and numerical significance OPEN |
| Ten-minute multi-field cascade | MEASURED; process-by-process propagation OPEN |
| `ncmin` as a cause | REFUTED for this case -- both thresholds are 10 |
| Forecast-skill impact | UNMEASURED |

Two phrases in the sections above were wrong and are corrected where they
appear: "tile-boundary mechanism" (`np = 1` is already two tiles and is
bit-identical to itself; what `np = 2` adds is an MPI PATCH) and "not a boundary
artefact" (a wide terminal footprint does not refute a boundary origin). The
"7-row seed propagates to a 140-row footprint" account is superseded outright by
the per-tile overwrite, which predicts the band exactly.
