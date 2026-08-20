# The number-transport defect's coefficient in a real atmosphere

`g33_number_transport` establishes the residual as an identity. Dividing each
interface term by what should have arrived makes the transfer cancel:

    eps_j = den(lower)/den(upper) - 1

That is the fraction of number the legacy metric over-delivers across one
interface, and it depends on the DENSITY PROFILE ALONE. So the magnitude the
defect can reach in a real atmosphere is measurable without running the model,
without the corrected arm, and without touching the frozen kernel.

## Measured — LC05 5 km analysis state, 2023-02-16

`host/lc05_da_run/wrfinput_d01`, 65,988 columns, 2,507,544 interfaces.

| statistic | value |
|---|---|
| median | 8.59 % |
| mean | 7.03 % |
| p90 | 10.88 % |
| max | 11.51 % |
| negative | 0.019 % |

It grows with height, which is the physical content: the stratification the
metric ignores is weakest where layers are thin and the air is nearly uniform,
and strongest aloft.

| model k | ~hPa | median eps |
|---|---|---|
|  0 |    999 |  0.47 |
|  6 |    914 |  2.26 |
| 12 |    699 |  5.38 |
| 18 |    419 |  9.01 |
| 24 |    222 |  9.01 |
| 30 |    117 | 10.43 |
| 36 |     62 | 11.17 |

## What this is and is not

It IS the per-interface error of the transport metric, over a real
atmosphere rather than a synthetic fixture, and it is the same quantity the
synthetic arms vary deliberately -- the uniform arm sets it to zero, the
inverted arm reverses its sign, the x2 arm doubles it.

It is NOT a forecast impact, a column-number increase, or a precipitation
change. How much number actually crosses each interface is the transfer `b`,
which this does not measure: a column where nothing sediments carries the same
`eps` profile as one that rains. Turning this into a trajectory statement
needs the corrected arm, which needs the freeze-lift
(`REQUEST_freeze_lift_diagnostic_arms`).

Density here is MOIST, matching the kernel's own `den` (`dend(i,k) = den(i,k)`,
F:870). The dry-air basis offset is `FINDING_number_mass_basis_v1`.

## Limits

- One state, one time, one domain. No seasonal or regime sampling.
- An ANALYSIS state, not a forecast trajectory: it says what the coefficient
  is in a realistic atmosphere, not what a run does with it.
- `host/**` is private, so this measurement is reproducible only where that
  state exists. The tool's own properties are tested synthetically and run
  everywhere.
