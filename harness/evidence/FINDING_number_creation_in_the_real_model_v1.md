# Ten-minute unclipped density-contrast proxy for number transport

## Correction after review of main 2638fb2 (2026-09-05)

The recorded 4.6188% rain and 8.5710% ice figures are **ratios of an unclipped
density-contrast term to unclipped departure**, not measurements of the full
number-transport residual. The prior headline that sedimentation creates that
fraction of number on every transfer is withdrawn. No host trajectory was
rerun for this correction.

## What the original run accumulated

At each `k+1 -> k` interface the reported numerator was

    (den(k) - den(k+1)) * Dz(k+1) * falkn(k+1) * dt

and the denominator was `den(k+1)*Dz(k+1)*falkn(k+1)*dt`, accumulated in
`real(8)` at both number-update sites. Here `den` is the kernel's moist density.
The original ten-minute, np=1 record reports:

| field | recorded interface occurrences | unclipped proxy / unclipped departure | recorded clip frequency |
|---|---|---|---|
| rain number | 163,801,204 | 4.6188% | 0.00180% |
| ice number | 163,801,204 | 8.5710% | 2.9051% |

These historical totals do not identify the amounts removed and received after
both caps. A clip frequency is an occurrence count, not a flux-weighted error
bound. The claims that rain is effectively exact and ice is an upper bound are
withdrawn. The ratio is also not a growth rate of the domain inventory.

## Actual interface accounting

Legacy limits departure and arrival separately. Arrival is capped by the upper
cell's already updated number. Thus the same thickness-weighted amount need not
arrive below. With the actual applied increments, define

    A = Dz_up * dn_out
    B = Dz_lo * dn_in
    R = rho_lo*B - rho_up*A
      = (rho_lo-rho_up)*A + rho_lo*(B-A)

The first term is the density contrast on ACTUAL departure; the second is the
transfer mismatch. Sum the signed `R` values and actual weighted departures
using the same density, rather than averaging interface percentages. A complete
state ledger also checks final state-clamp and rounding effects and surface
removal; this formula accounts for an interface, not every state update.

For unit thickness and dt, upper n=1, lower n=0, unclipped upper departure=.75
and no lower outflow, the upper state becomes .25 and the lower inflow is .25.
With upper/lower density 1/2, the inventory changes from 1 to .75: `R=-.25`.
The density term is +.75 and the mismatch term is -1. The old proxy therefore
has even the wrong sign in this example.

Clipping also changes a ratio's weights. Equal departures across density
contrasts of 1% and 10% yield 5.5%. Reducing one departure by 100x gives either
9.9109% or 1.0891%, depending on which interface clips. Neither a general upper
bound nor an effectively exact ratio follows from clip frequency alone.

## Unit contract and scope

Under the host per-dry-kg interpretation, use `rho_d=den/(1+qv)` and the physical
column number is `sum rho_d*Dz*n_d`. If stored numbers instead mean the kernel
slope equation's `N [m^-3]`, it is `sum Dz*N`, and the interface residual is
`B-A`. The relationship is `N=rho_d*n_d`; the host/kernel contract is still
unresolved. `FINDING_number_basis_is_inherited_from_wdm6_v1` establishes the
inconsistent source assumptions and their origin, not which one is correct.

Moist weighting is a named diagnostic measure, not a resolved number-unit
contract. The older 0.10% moist/dry weight difference on a separate fixture
cannot establish how these ten-minute ratios change. Likewise, similarity to a
6-14% residual on another fixture is not independent validation of this proxy.

## Reproducing the corrected diagnostic

The updated `--nflux` overlay emits the required operands, with no new transport
arm: `TOPOUT` records the top removal, `CAPIN` records each cell's own removal
and applied inflow. Legacy already emitted applied increments, but conservative
previously emitted unscaled source increments. New streams declare
`capin_applied` and include the actual update's metric factors. The analyzer
rejects missing record families and old conservative streams without this marker;
old legacy streams remain readable. `g33_cap_interface.py` pairs the upper
removal with the lower arrival. Its existing `number_created` JSON key is the
signed residual under the selected measure; `number_predicted` is the density
term using actual departure, and `number_transfer_mismatch` is the second term.
`number_residual_over_transported` uses actual weighted departure.

The portable tests in `harness/tests/test_g33_number_residual.py` verify the
sign reversal, unequal thickness, multi-interface pairing and weighted-ratio
counterexamples. These are synthetic accounting tests, not a host rerun.

The analyzer requires a fixed-forcing microphysics window. A future host probe
must capture the current interface density/thickness with the actual increments
at each update and preserve the original run/binary provenance. The archived
proxy totals alone cannot produce that new result. The ten-minute actual
residual and its dry-density weighting remain **UNMEASURED**.
