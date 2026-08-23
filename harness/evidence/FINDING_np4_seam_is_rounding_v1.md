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

## Traced upstream: `dz8w` is a symptom, not the source

This finding located the `np = 4` difference in `delz` and called it upstream of
microphysics. It is further upstream than that. Comparing the arm-C binary --
where the CCN block does not exist, so nothing in microphysics can be
implicated -- at `np = 1` against `np = 4` after ONE 20 s step:

| field | cells | relative median | relative max | i columns |
|---|---|---|---|---|
| `PHB` base geopotential | **0** | -- | -- | -- |
| `PH` perturbation geopotential | 91 090 | 2.19e-07 | 1.10e-04 | 109..233 |
| `MU` dry column mass | 3 829 | 1.42e-06 | 1.69e-03 | 109..233 |
| `T` | 10 869 | 1.49e-06 | 8.82e-02 | 2..233 |
| `U` | 123 227 | 7.40e-07 | 1.37e-01 | 110..234 |
| `V` | 105 955 | 5.72e-07 | 9.23e-02 | 109..233 |
| `W` | 202 664 | 7.12e-06 | 1.03e+01 | 108..234 |

`dz8w` is `z_at_w(k+1) - z_at_w(k)`, computed from `PH` + `PHB`
(`module_big_step_utilities_em.F:4877`). `PH` differs and `PHB` does not, so the
`delz` difference reported above is DERIVED from a `PH` difference, and every
other prognostic differs beside it. Naming `dz8w` as the site was naming the
first place it was looked for.

**`PHB` being bit-identical is the control that matters.** The base-state
geopotential is a function of the grid and the reference profile, not of the
integration; identical means this is not a grid setup or a decomposition-
dependent static field. It is the prognostic solve.

### And the first step creates it

Same two runs, the initial frame against the one-step frame:

    frame 0 (initial state)     0 of 197 fields differ
    frame 1 (after one 20 s)   28 of 197 fields differ

The decompositions start from a bit-identical state. Everything above is made by
the first integration.

### The medians are rounding-scale and the maxima are not

Median relative differences of 2e-07 to 7e-06 are a handful of ULP. The maxima
are not: `W` reaches 1.03e+01 -- more than 100 % -- and `T` 8.8e-02, in a single
step. So "rounding-scale" describes the bulk of the distribution and not its
tail, and the amplification the trajectory finding measures over ten minutes has
already begun within the first one.

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
