# The ρΔz weight is moist-air density; `nr` is per kg of dry air

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-BASIS-001` | **active** | confirmed | g33_fixture_multisubcycle_v1 for the magnitude; source for the bases |
| `G33-BASIS-002` | **hold** | open-question | owner engineering-compatibility and release policy; the physics is G33-BASIS-006 and the operator's measured behaviour is G33-NUMBER-003 |
| `G33-BASIS-006` | **active** | confirmed | source definitions only; which measure the correction adopts as default is G33-BASIS-002, which stays an owner decision |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

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
- **Settled since (owner review §10, superseding the line that stood here)**:
  the PHYSICAL column number is `Σ ρ_d Δz nr` -- unit-forced, because `nr` is
  per kg of dry air, so it is not an owner preference (G33-BASIS-006).
  `Σ ρ_m Δz nr` remains meaningful only as the legacy operator's
  pseudo-measure. What stays an owner decision is narrower than this line
  originally said: whether a corrected transport keeps compatibility with the
  pseudo-measure, and whether the default promotes to the physical measure
  (G33-BASIS-002).
- **Not measured**: the effect on a real case, where qv is 20× larger and varies
  strongly in the vertical.
