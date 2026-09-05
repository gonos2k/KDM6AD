# Moist versus dry density under the host number-unit interpretation

Review correction (2026-09-05, main 2638fb2): Registry/dynamics support a
per-dry-kg interpretation, but the kernel slope formula requires per-volume
number without a boundary conversion. The end-to-end contract is unresolved;
see `FINDING_number_basis_is_inherited_from_wdm6_v1`. The historical claim
table below does not establish `nr`'s physical units inside the kernel.

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-BASIS-001` | **active** | confirmed | g33_fixture_multisubcycle_v1 for the magnitude; source for the bases |
| `G33-BASIS-002` | **hold** | open-question | owner engineering-compatibility and release policy; the physics is G33-BASIS-006 and the operator's measured behaviour is G33-NUMBER-003 |
| `G33-BASIS-006` | **active** | confirmed | source definitions only; which measure the correction adopts as default is G33-BASIS-002, which stays an owner decision |

The historical statuses above are retained for provenance. The conditional unit
contract in this correction supersedes their unconditional physical-unit claim.
<!-- /claim-status -->

Owner §7. The number-transport result is stated against the column measure
`Σ den·Δz·nr`. That is only the physical column number if `den`'s kilogram and
`nr`'s kilogram are the same kilogram. They are not exactly.

## From source

Registry declares `nr` as `# kg-1`, and the host's mixing-ratio interpretation
uses kg of **dry** air. This declaration does not settle the kernel's competing
per-volume assumption.

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

Under the per-dry-kg interpretation, the column measure weights by ρ_d, so
`Σ den·Δz·nr` overstates by `(1 + qv)` per cell. Measured on
`g33_fixture_multisubcycle_v1` at h = 25 s:

| | max qv | weight error |
|---|---|---|
| this fixture | 1.03e-03 | **0.10%** |
| a moist operational layer (qv ≈ 0.02) | 2e-02 | ~2% |

This is a per-cell weight comparison, not a bound on a signed transport
residual or its ratio to throughput. Those can change through cancellation and
spatial weighting and must be recomputed from actual transfers on one basis.

## What is and is not settled

- **Settled from source**: `den` is moist-air density; moist and dry density
  differ by `(1 + qv)`; Registry and kernel number-unit assumptions disagree.
- **Settled by measurement**: the resulting weight error is 0.10% on this fixture.
- **Conditional identity**: if `n_d` is per dry kg, physical column number is
  `Σ ρ_d Δz n_d`; if `N` is per m³, it is `Σ Δz N`, with `N=ρ_d*n_d`.
  The earlier unconditional G33-BASIS-006 reading is withdrawn. Closing the
  host/kernel boundary contract is a prerequisite to choosing a conversion;
  a sedimentation-only density factor is not an established remedy.
- **Not measured**: the effect on a real case, where qv is 20× larger and varies
  strongly in the vertical.
