# Signed analysis inventories after PR #374

This offline calculation uses the public native analysis fields, the saved
initial forcing and the existing G33 water/enthalpy state functions. It does not
run KDM, RTTOV, an optimizer or the private host. It preserves the earlier
execution artifacts and does not reopen their bounded derivative checks.

For all four endpoints, declare one common background-derived dry measure:

`w_d,k = rho_m,k * dz_k / (1 + qv_background,k)`.

The same weights are held fixed for background, analysis and both slot states.
This matches the current fixed-background optical convention; it does not
certify the canonical dry-air mass carried by host dynamics. The legacy operator
measure `w_m,k = rho_m,k * dz_k` is reported separately. No endpoint-dependent
reweighting is used. KDM's per-step entry-density conversion remains a distinct
internal calculation and is not changed by this inventory analysis.

## Water: signed state changes, kg m^-2

| Difference on fixed dry measure | Vapor | Cloud liquid | Total water |
| --- | ---: | ---: | ---: |
| Initial analysis minus background | +0.101484626 | +0.0000279053 | **+0.101512531** |
| Slot analysis minus slot background | +0.057015022 | +0.044497510 | **+0.101512531** |
| Background model endpoint minus its initial state | +0.000564206 | -0.000564206 | +8.49e-17 |
| Analysis model endpoint minus its initial state | -0.043905398 | +0.043905398 | -6.25e-17 |

Rain, ice, snow and graupel contribute zero to these particular endpoint
differences. The operator-weighted initial analysis change is +0.102902660
kg m^-2. These are different measures applied to the same saved states.

The analysis initially adds about 0.1015 kg m^-2 of water, almost entirely vapor.
At the observation slot, more of the increment is liquid. The background and
analysis model legs have different net vapor/liquid redistribution. Thus the
slot NC or QC increment cannot be attributed to its corresponding initial
control alone. This is endpoint attribution, not identification of an individual
condensation, activation or other named process.

For each species on the common fixed measure,

`slot difference = initial analysis difference + analysis model net change - background model net change`.

The reconstruction is an algebraic identity. The near-zero net total-water
changes on the two model legs are endpoint observations, not evidence that all
applied transfers and boundary fluxes have been measured.

## Heat: conditional state functions, J m^-2

The existing `g33_refine_analyze._h_consistent` uses `T=th*pii`, T_ref=273.15 K,
phase heat capacities and reference latent heats. `_h_code` is a separate
KDM-operator potential. Neither is newly declared an approved host enthalpy.

| Difference on fixed dry measure | Per-phase state function | Operator potential |
| --- | ---: | ---: |
| Initial analysis minus background | +206,766.25 | +202,870.90 |
| Slot analysis minus slot background | +208,414.98 | +198,587.49 |
| Background model net change | -19.11 | +53.03 |
| Analysis model net change | +1,629.62 | -4,230.38 |

A reference offset C_water in all water-species enthalpies of the per-phase
state function changes delta-H by
`C_water * delta-W`. Because the analysis adds water, its heat inventory change
requires a stated enthalpy reference and the enthalpy of any externally supplied
mass. A temperature-increment norm is insufficient for that accounting.

The phase function and operator potential give different model-leg changes.
These values are not conservation residuals: net boundary mass/enthalpy flux,
external heat, pressure work and applied process extents are absent from these
artifacts. They remain explicitly unknown. S17 stays OPEN; no missing term is
set to zero or inferred as an export from the inventory difference.

## Current research interpretation

The executable fixed-forcing research path retains frozen background optical
density and this common inventory reference. The live-entry optical experiment
is a different operator with an extra input-density derivative; its smaller or
larger FD error is not a policy-selection argument. Scientific use still needs
the host mass reference, number/threshold calibration, product compatibility and
independent B/R/bias evidence.

`cloudy_clear` is the existing proxy classification: background slot-time model condensate level sum
above 1e-5 kg/kg, with valid observed IR105 not below 270 K. The retained
IR105=286.160921 K therefore falls in its proxy-clear category. This is not an
independent cloud mask or proof that the physical scene is cloud-free. The
threshold, observation support and loss weights are not changed by this report.

Two optimizer iterations decreased the diagnostic cost; they did not establish
convergence or forecast improvement. The one-hour window kept a fixed nominal
00:00 target. Neither the inventories nor the earlier FD checks close physical
analysis, S2/S11/S17 or operational approval.

- [Executed offline source](NATIVE_analysis_inventory_source_2026-10-05.py)
- [Signed inventories, conventions and input/source hashes](NATIVE_analysis_inventory_result_2026-10-05.json)
- [Original actual native-path report](REPORT_native_KMA_window_2026-10-05.md)
