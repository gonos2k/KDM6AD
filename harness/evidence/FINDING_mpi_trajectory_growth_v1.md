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

## Four corrections to the table above

Every number in it is real and several are not what they were read as. The
owner's re-review named them; each is measured here rather than argued.

**The quantiles were CONDITIONAL on cells that differ.** Beside the domain's own:

| field | t=10 | conditional p99 | **domain p99** |
|---|---|---|---|
| `REFL_10CM` | | 1.175e+01 | **8.06e-01** |
| `T` | | 7.32e-03 | 6.59e-03 |
| `QVAPOR` | | 2.93e-06 | 2.80e-06 |
| `RAINNC` | | 1.29e-02 | 1.11e-03 |

So "more than ten dBZ at the 99th percentile" is the conditional figure. The
domain's is **0.81 dBZ**, fourteen times smaller, and that is the one a reader
takes a p99 to mean.

**The reflectivity tail was the unphysical one.** Screened to a real
reflectivity range, `[-35, 80]` dBZ, which covers 99.995 % of the domain at ten
minutes, the p99 is **0.80 dBZ**. And in the terms a forecast is read in, the
number of CELLS above 20 dBZ is 47 408 at np = 1 against 47 456 at np = 4 --
a difference of 0.1 %. A cell count is not an area: on this projection cells
differ in size and a physical area needs `DX*DY / MAPFAC_M**2`, which this
frame does not carry.

**The precipitation difference is DISPLACEMENT, not a bias.** Signed against
gross, over the domain at ten minutes: **+0.168 signed** against **13.86 gross**, in mm x columns, so the signed total is 1.2 % of the movement. And by threshold:

| |dRAINNC| | > 1e-3 mm | > 1e-2 mm | > 1e-1 mm |
|---|---|---|---|---|
| t = 5 | 0.635 % | 0.194 % | 0.021 % |
| t = 10 | 1.068 % | 0.300 % | **0.048 %** |

"A tenth of a millimetre depends on the rank count" is true of **0.048 % of
columns**, about one in two thousand -- not of the domain.

**The growth factor compared two different populations.** The differing support
itself grows from 4.76 % to 11.17 %, so a median at one minute and a median at
ten are medians over different sets. Held still on the cells that differ at ONE
minute and followed:

| field | t=1 | t=10 | growth |
|---|---|---|---|
| `T` | 3.05e-05 | 2.14e-04 | 7x |
| `REFL_10CM` | 4.01e-05 | 9.93e-03 | 248x |
| `QVAPOR` | 6.99e-10 | 2.03e-08 | 29x |

The growth is real on a fixed population. The "350x" quoted earlier was over a
support that had more than doubled.

**And the six-minute jump is the radiation call -- measured, not argued.** The
first version of this reasoned from the field NAMES: 27 of the 31 fields that
start differing at frame 6 are radiation accumulators. That is an argument. The
measurement is moving the schedule and seeing whether the jump moves with it:

| `radt` | fields differing, by frame 1..10 | jump at |
|---|---|---|
| 3 min | 77 79 79 **106** 106 106 106 106 106 106 | **frame 4** |
| 5 min | 77 78 79 75 75 **106** 106 106 106 106 | **frame 6** |
| 7 min | 77 79 79 75 75 75 75 **106** 106 106 | **frame 8** |

The jump lands at `radt + 1` in every case -- the frame after the first
radiation call. It is the radiation call carrying an existing difference into
its own diagnostics, and no new mechanism fires at six minutes.

## What it says

**The difference spreads and grows.** Coverage goes from 8.75 % of temperature
cells at one minute to 86.01 % at ten, and from 22.76 % to 94.54 % for vapour.
Magnitude grows with it: the median reflectivity difference rises by a factor of
350 over the same interval, and accumulated precipitation goes from a p99 of
1.4e-06 mm to 1.3e-02 mm, with a maximum of 0.36 mm.

So the one-step result was not a transient: the difference spreads across the
domain and grows on a fixed population.

**Its SIZE is smaller than the first reading of this table suggested.** Stated
in domain terms: the 99th percentile of the reflectivity difference is 0.81 dBZ
(0.80 screened), the CELL COUNT above 20 dBZ moves by 0.1 %, and accumulated
precipitation differs by more than 0.1 mm in 0.048 % of columns while the
signed domain total moves by 1.2 % of the gross. The decomposition changes
WHERE it rains far more than whether it rains.

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

## Area-weighted, from `MAPFAC_M`

`wrfinput_d01` carries the map factor, so `A_ij = DX*DY / MAPFAC_M^2` is
available and the grid-cell statistics above can be checked against physical
ones. At ten minutes, `np = 1` against `np = 4`:

| | grid-cell | area-weighted |
|---|---|---|
| signed mean precipitation difference | 2.546e-06 mm | 2.554e-06 mm |
| signed water volume | -- | 4.42e+03 m3 |
| gross water volume | -- | 3.61e+05 m3 |
| above 20 dBZ | 47 408 / 47 456 cells | 133 252 / 133 386 km2 |
| above 30 dBZ | 24 968 / 25 061 cells | 75 221 / 75 483 km2 |

The map factor moves the mean by 0.3 % and the threshold areas by 0.1 %, so
every conclusion drawn from the cell counts stands in physical units. The
signed volume is 1.2 % of the gross, which is the cancellation ratio already
reported and is dimensionless either way.
