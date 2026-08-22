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
| area over 20 dBZ (`np = 1`: 47 408) | 47 471 | 47 456 |

By one minute the two are indistinguishable in scale, and they stay so for ten.
The single-field `np = 2` result was the SEED, one step in, and it cascades to
the same place.

**So the effect is not proportional to the number of tiles.** It fires as soon
as there is more than one, which is what a tile-BOUNDARY mechanism looks like
and not what a per-rank accumulation looks like. That narrows where to look
considerably: whatever it is, splitting the domain once is enough to trigger all
of it.

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
