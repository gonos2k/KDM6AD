# The ρΔz weight is moist-air density; `nr` is per kg of dry air

Owner §7. The number-transport result is stated against the column measure
`Σ den·Δz·nr`. That is only the physical column number if `den`'s kilogram and
`nr`'s kilogram are the same kilogram. They are not exactly.

## From source

`nr` is `# kg-1` (`Registry.EM_COMMON:122`, "rain num concentration"), and WRF
mixing ratios are per kg of **dry** air (`QVAPOR` is `kg kg-1` on that basis).

The `den` the kernel receives is `DEN=rho` from the microphysics driver
(`module_microphysics_driver.F:2742`), and `rho` is built in
`module_big_step_utilities_em.F:4856`:

```fortran
rho(i,k,j) = 1./alt(i,k,j)*(1.+moist(i,k,j,P_QV))
```

`alt` is inverse **dry**-air density, so `1/alt = ρ_d` and

    den = ρ_d · (1 + qv)          — MOIST-air density

The kernel then uses it directly: `dend(i,k) = den(i,k)` (F:870).

## The size of it

The column measure should weight a per-dry-kg quantity by ρ_d, so
`Σ den·Δz·nr` overstates by `(1 + qv)` per cell. Measured on
`g33_fixture_multisubcycle_v1` at h = 25 s:

| | max qv | weight error |
|---|---|---|
| this fixture | 1.03e-03 | **0.10%** |
| a moist operational layer (qv ≈ 0.02) | 2e-02 | ~2% |

**This does not explain the number-closure residual.** 0.10% is an order of
magnitude below the measured 6–14%, so the ρΔz-vs-Δz transfer defect stands. What
the basis does affect is the **absolute** [# m⁻²] figures, which carry a
systematic 0.1% offset here and would carry ~2% on a moist real case.

## What is and is not settled

- **Settled from source**: `den` is moist-air density; `nr` is per dry kg; the
  two bases differ by `(1 + qv)`.
- **Settled by measurement**: the resulting weight error is 0.10% on this fixture.
- **Not settled**: whether the reference intends `Σ ρ_d Δz nr` or
  `Σ ρ Δz nr` as *the* conserved column measure. That is a physics-definition
  question for the owner, and it changes which quantity a corrected number
  transport should conserve.
- **Not measured**: the effect on a real case, where qv is 20× larger and varies
  strongly in the vertical.
