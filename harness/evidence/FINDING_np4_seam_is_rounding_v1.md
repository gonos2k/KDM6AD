# The `np = 4` seam difference is rounding-scale, and not the same kind of thing

`FINDING_second_decomposition_defect_v1` measured that at `np = 4` the model's
own `delz` (`dz8w`) differs in OWNED cells at the i-seam, before the CCN block
runs -- which is why the tile-bounds fix leaves `np = 4` at 77 differing fields.
It located that difference and did not size it. Sized, it is a different
phenomenon from the CCN defect.

## The measurement

`np = 1` against `np = 4`, `delz` at the first-timestep probe, owned cells only:

    differing            26 863 of 2 598 400   (1.018 %)
    layer thickness      51.23 .. 833.38 m in those cells
    absolute            median 4.883e-04   p99 1.953e-03   max 3.906e-03  m
    relative            median 6.909e-07   p99 3.331e-06   max 9.421e-06
    ULP distance        median 8           p99 40          max 103
    sign                np4 > np1 in 49.7 %
    vertical            39 of 40 levels, 329..1016 cells each
    within 1 ULP        2.2 %

## Why that separates it from the CCN defect

|  | CCN halo defect | `np = 4` seam |
|---|---|---|
| relative difference | **1.0** (`delz` is 0.0 against ~408 m) | max **9.4e-06** |
| ULP distance | the whole word | median 8 |
| sign | systematic -- one side is zero | 49.7 % either way, symmetric |

Six orders of magnitude and a symmetric sign. Half a millimetre on layers 51 to
833 metres thick is not a wrong value; it is the same value summed in a
different order. A median of 8 ULP is more than one rounding and consistent with
a handful of them accumulating, which is what a reduction whose order follows
the patch decomposition does.

So `np = 4` carries two unrelated things: the CCN block's halo read and per-tile
overwrite, which the tile-bounds fix removes, and a rounding-scale `dz8w`
difference at the seam, which it cannot.

## What this does NOT settle

**That the seam difference is harmless.** It is rounding-scale at the source and
this case shows it does not stay that way: ten minutes on, `REFL_10CM` differs
by up to 248x its one-minute mask (`FINDING_mpi_trajectory_growth_v1`). A
convective state amplifies small differences, and "small where it starts" and
"small where it ends" are separate claims.

**That it is a defect at all.** A dynamical core whose reductions are not
order-fixed is not bit-reproducible across decompositions, and that is ordinary.
Establishing whether THIS core intends to be would need the dynamics-side
controls the review lists -- microphysics off, a probe at the statement that
writes `dz8w` rather than one that reads it, `PH`/`PHB`/`MU`/`alt` upstream, and
a different `nproc_x` x `nproc_y` at the same rank count -- none of which are
run here.

**Where it comes from.** `dz8w` is written at
`module_big_step_utilities_em.F:4877` from `z_at_w`, and at
`start_em.F:1786`/`:2131` from `PH`+`PHB`. This measures the value the
microphysics was handed, not which of those produced the difference.

One case, one build, one host, first timestep.
