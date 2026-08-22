# The decomposition difference over ten minutes, not one step

`FINDING_real_mpi_decomposition_v1` showed that one 20-second step of the
operational 5 km case gives different answers at different MPI rank counts, and
said nothing about what happens next. A difference that appears in one step
might damp, saturate, or grow. This measures which.

Two runs of the same case, `mp_physics = 37`, adaptive stepping off, ten
minutes, one frame per minute, at `np = 1` and `np = 4`. Both exit 0 with
`SUCCESS COMPLETE WRF` and eleven frames.

## The control

At `t = 00:00:00` all 197 f32 time-varying fields are bit-identical. Everything
below is made by the integration.

## Coverage

Fields differing, of 197:

| t | 0 | 1 min | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fields | **0** | 77 | 78 | 79 | 75 | 75 | 106 | 106 | 106 | 106 | 106 |

## Magnitude

Over the cells that differ, at three times:

| field | t | cells differing | median | p99 | max |
|---|---|---|---|---|---|
| `T` | 1 min | 8.75 % | 3.05e-05 | 2.05e-03 | 6.03e-01 |
| | 5 min | 72.69 % | 6.10e-05 | 2.20e-03 | 8.09e-01 |
| | **10 min** | **86.01 %** | 9.16e-05 | 7.32e-03 | 9.40e-01 |
| `QVAPOR` | 1 min | 22.76 % | 6.99e-10 | 3.39e-07 | 1.69e-04 |
| | **10 min** | **94.54 %** | 5.09e-09 | 2.93e-06 | 2.32e-04 |
| `RAINNC` | 1 min | 5.15 % | 1.36e-12 | 1.38e-06 | 1.66e-05 |
| | **10 min** | **25.71 %** | 1.25e-06 | 1.29e-02 | 3.62e-01 |
| `REFL_10CM` | 1 min | 4.76 % | 4.01e-05 | 3.52e-01 | -- |
| | **10 min** | **11.17 %** | 1.39e-02 | 1.18e+01 | -- |

`REFL_10CM`'s maximum is left out on purpose: the field's range in this
configuration is -35 to 174.8, and 174.8 dBZ is not a reflectivity. The extreme
tail is dominated by whatever produces those values, so `p99` is the statistic
that means something here.

## What it says

**The difference spreads and grows.** Coverage goes from 8.75 % of temperature
cells at one minute to 86.01 % at ten, and from 22.76 % to 94.54 % for vapour.
Magnitude grows with it: the median reflectivity difference rises by a factor of
350 over the same interval, and accumulated precipitation goes from a p99 of
1.4e-06 mm to 1.3e-02 mm, with a maximum of 0.36 mm.

So the one-step result was not a transient. After ten minutes of the
operational configuration, **a tenth of a millimetre of accumulated
precipitation, and more than ten dBZ at the 99th percentile, depend on how many
MPI ranks the forecast was run on.**

## What it does NOT say

It does not attribute this to `ncmin`. The one-step finding already declined to:
`ncmin` gates cloud droplet number, and at `np = 2` `QNCLOUD` was unchanged
while `QNCCN` alone moved. Whatever sets `QNCCN` per tile is a different site
and neither finding names it.

It does not measure whether Arm L removes the growth. That needs `wrf.exe`
rebuilt with the `lncmin` kernel, which is a change to the operational binary
and an owner decision.

And it is one case, one initial time, ten minutes. Nothing here is a
forecast-skill statement.

## Reproducing

    cd <SS run dir>
    python3 run_ss_case.py --mp 37 --minutes 10 --seconds 0 \
        --history 1 --history-s 0 --np <1|4> --label traj --fixed-dt
