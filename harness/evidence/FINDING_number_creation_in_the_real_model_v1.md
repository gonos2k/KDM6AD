# Sedimentation creates 4.6% of the rain number and 8.6% of the ice number it moves

Owner review item 20, sixth priority, asked for a conversion-free ice fixture to
isolate the number-moment transfer. A fixture is not needed: the transfer has a
closed form, so it can be measured in the real model with no synthetic state and
no conversion terms to subtract.

## The closed form

A `k+1 -> k` transfer moves, on the `Dz` measure the code conserves,

    Dz(k+1) * falkn(k+1) * dt

and the SAME amount arrives at `k`, because the incoming term carries
`delz(k+1)/delz(k)` (`:1222` for rain, `:1306` for ice) while the flux itself
carries no density (`:1194`, `:1286`). On the physical `rho*Dz` measure it leaves
`k+1` weighted by `rho(k+1)` and arrives at `k` weighted by `rho(k)`, so each
transfer CREATES

    (rho(k) - rho(k+1)) * Dz(k+1) * falkn(k+1) * dt

Falling is downward and `rho` increases downward, so the sign is positive: the
scheme makes number out of nothing, every transfer.

## Measured over ten minutes, np = 1

Accumulated in double precision at both transfer sites, against the transferred
amount `rho(k+1)*Dz(k+1)*falkn(k+1)*dt` as the reference:

| | transfers | created / transferred | clip rate |
|---|---|---|---|
| rain number | 163,801,204 | **4.6188%** | 0.00180% |
| ice number | 163,801,204 | **8.5710%** | 2.9051% |

**For every unit of number the sedimentation moves down, it creates 0.046 more
for rain and 0.086 more for ice.** Ice is worse because ice falls through a
larger density contrast per step.

This sits inside the 6-14% transfer residual `FINDING_number_basis_gap_v1`
measured on `g33_fixture_multisubcycle_v1`, reached independently and on a real
atmosphere.

## Scope

- The ratio is **created per transferred**, not a growth rate of the domain
  number. It does not say the rain number rose 4.6% over the run.
- The `min(..., n(k+1))` clip binds on 2.91% of ice transfers and 0.0018% of rain
  ones; where it binds the unclipped form used here overstates. The ice figure is
  an upper bound to that extent, the rain figure effectively exact.
- `den` is moist-air density against a per-dry-kg number
  (`FINDING_number_mass_basis_v1`, 0.10%), which does not move these ratios.
- Whether this policy is KDM6AD's to change is settled elsewhere and is not:
  `FINDING_number_basis_is_inherited_from_wdm6_v1` shows the flux without
  `dend` and the `delz` ratio are `module_mp_wdm6.F`'s, verbatim.

## Reproducing

Two accumulator pairs at the number updates in `module_mp_kdm6.F` --
`nrs(i,k,1) = max(nrs(i,k,1)-dnr(i,k)+dnr(i,k+1),0.)` and the `nci(i,k,2)`
mirror -- summing the creation and the transferred amount in `real(8)`;
`np = 1`, 10 minutes, history 1.
