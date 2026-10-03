# S2 number-coordinate and rate-dimension audit — 2026-10-03

This bounded audit records dimensional consequences of the active source, not a
physical recalibration or a completed S2 acceptance. It complements the prior
[number-basis report](REPORT_S2_number_unit_contract_design_2026-09-25.md) and
[threshold-unit report](REPORT_S2_threshold_units_2026-09-28.md); those remain the
broader boundary analyses.

## Storage, kernel, and conversion path

Active WRF Registry entries describe QNICE, QNRAIN, QNCCN, and QNCLOUD as
`# kg-1` (`host/KIM-meso_v1.0/Registry/Registry.EM_COMMON:536-554`). The
KDM6 wrapper copies host `nc`, `ni`, `nn`, and `nr` directly into `nci`/`nrs`
and copies them back without a density conversion
(`host/KIM-meso_v1.0/phys/module_mp_kdm6.F:385-389,417-429`). It also passes
`den` directly to the kernel (`:398-407`). The DSD closure uses `den*q` with
number in `lambda = (pi*N/(den*q))^(1/d)` and rewrites number as
`den*q*lambda^d/pi` (`:1550-1589`), so the kernel equations treat N as a
volume concentration and `den*q` as water mass per volume. These measures do
not match the Registry labels under the default direct-copy boundary. The
active driver passes `rho` as `DEN` (`module_microphysics_driver.F:2742-2756`).

QIB/BG is a separate graupel-volume moment per dry-air mass, not a number
field. Its physical volume fraction is `rho_d*b_d`, paired with
`rho_d*qg_d`; their ratio is bulk density `qg_d/b_d` in kg m^-3. Snow number
is diagnosed from its intercept/slope, not transported as a KDM6 QNS state.
These distinctions must survive ABI packing and the size/optical interface.

The default legacy host path and opt-in dry-number path are distinct. In the
opt-in oracle path, `rho_d = rho/(1+qv_entry)` multiplies NC/NI/NR/NCCN before
kernel entry, is also supplied as `cf.dend` for the mass DSD moments, and the
same `rho_d` converts all four number outputs back to the dry-mass state
(`oracle/kdm6/runtime.py:533-556,728-739`). This pairs number and mass moments
within that candidate. The separate isolated mp337 wrapper experiment also
converts its volume-initialized timestep-one NN profile once by entry `rho_d`
before dry-specific staging; see the [native mp337 dry-number report](REPORT_S2_native_mp337_dry_number_2026-09-28.md).
Neither changes the default operational wrapper.

For observations, `oracle/kdm6/rttov_bridge.py:122-132` requires an explicitly
frozen `rho_d`, while the runtime's `rho/(1+qv_entry)` density participates in
the differentiable input conversion. The frozen observation density and live
runtime-entry density therefore need an explicitly paired observation-map
contract before physical DA acceptance. This is a map/acceptance distinction,
not an unimplemented mass-moment conversion in the opt-in runtime.

## Number-domain thresholds and limits

| Quantity | Active values and role | Unit status / evidence |
|---|---|---|
| Cloud `ncmin` | Namelist defaults: land 100, sea 10 (`Registry.EM_COMMON:2530-2531`); active Fortran assigns a scalar in an `i` loop, so the final column's surface class sets the tile value (`module_mp_kdm6.F:873-881`), then uses it for cloud/ice gates and budget floors (`:2735-2764`) | Registry has no unit. The port has a per-cell land/sea tensor; active Fortran's scalar last-column behavior is a separate parity detail. The value is compared directly with the kernel number variable; its DSD equations require volume-number dimensions, while the default input basis is the caveat above. Empirical calibration/source basis is not established here. |
| Scalar `NCMIN` | `1e-2`, port safety floor (`oracle/kdm6/constants.py:113`; C++ runtime floors per-cell values at this safety floor, `libtorch/src/runtime.cpp:469-485`) | Numeric volume-kernel floor; distinct from the host land/sea gate. Not a physical cloud threshold claim. |
| Cloud `NCMAX` | `5e10`; if exceeded, the DSD slope is forced to `lamdacmax=5e5 m^-1` and `nc` is recomputed from mass/slope (`module_mp_kdm6.F:77-78,102,3293-3296`; port constant `constants.py:75`) | Slope-limit behavior, not a simple `nc=ncmax` clamp. Number argument is treated as volume concentration by the DSD equation. Calibration is unresolved. |
| Rain `NRMIN`, `NRMAX` | `1e-2`, `5e7`; `nrmin` gates DSD/processes and budgets; above `nrmax`, slope is forced to `lamdarmax=3.5e4 m^-1` and `nr` recomputed (`module_mp_kdm6.F:79-80,100-101,1550-1562,2768-2778,3289-3292`; port constants `constants.py:73-74`) | Number argument is in the volume-kernel coordinate; `NRMAX` acts through the slope bound. Numerical calibration remains open. |
| CCN references used to derive warm mass gates | `XNCR0=5e7`, `XNCR1=5e8`; define `qc0/qc1 = (4/3 π ρ_water r0^3 XNCRx)/ρ0` (`module_mp_kdm6.F:88-90,3407-3408`; port `constants.py:59-61`, `cloud_dsd.py:46-48`) | Formula requires concentration scales `[m^-3]`; they set mass mixing-ratio gates, not standalone number clamps. `XNCR=3e8` is declared but is not used in the active Fortran source. |
| Ice number `NI` | Entry clamp `[0,1e6]` (`module_mp_kdm6.F:860-862`); also compared with `ncmin` in gates/budgets (`:2749-2764`) | Raw numeric clamp; intended physical unit/calibration is not declared at this line. Kernel DSD and transfer rates require a volume-number coordinate. |
| CCN `NCCN` | Entry/post-activation numeric clamp `[1e8,2e10]` (`module_mp_kdm6.F:859,3288`; port `constants.py:93-94`); source comment records `NCCN > 100 cm-3` (`:601`) | The values align with a volume-number interpretation, but the default direct-copy boundary caveat above remains. Park & Lim (2023, §2) state initial `NCCN=100 cm^-3`; this supports the lower-bound scale, not the upper-bound calibration. The cited opt-in mp337 wrapper converts its initialized profile at ingress. |
| Heterogeneous ice target `N_ID` | `0.005 exp(0.304 supcol) * 1000`, clamped at `500e3 m^-3` (`module_mp_kdm6.F:2493-2505`; oracle `cold.py:1133-1155`) | Park & Lim (2023, §2) identify the Cooper curve as capped at 500 L^-1. Thus `500 L^-1 = 500e3 m^-3 = 0.5 cm^-3`. The Fortran `500 m^-3` comment and Python `500 cm^-3` docstring were each wrong by 1000; the numeric operation is unchanged. |
| Mass gates | `qcrmin=1e-9` (qr/qs); `qmin`/epsilon gates and `dtcld` caps (`module_mp_kdm6.F:56,96,1123,1550-1566`) | These are mass mixing-ratio / numerical gates, not number-concentration thresholds. |

The separate DSD slope bounds are cloud `[1.2e4,5e5]`, rain `[9.61e2,3.5e4]`,
snow maximum `1.8e5`, and ice `[9.08e3,1.82e6] m^-1`
(`module_mp_kdm6.F:77-83`). Clamping these bounds can rewrite prognostic
number, so they participate in the number budget even when no explicit number
cap is applied.

For host microphysics, number sedimentation transports `N*dz` and applies the
layer number flux (`module_mp_kdm6.F:1285-1307`). Later number departures are
scaled against `max(ncmin,Nc)`, `max(ncmin,Ni)`, and `max(nrmin,Nr)` before
number state updates add each rate times `dtcld` (`:2735-2778,2795-2813`).
Copy-back to the host remains direct at `:417-429`; the default wrapper does
not reverse a volume-to-mass conversion because it did not perform one. This
completes the source path from stored fields through process budgets and return.

## Rate dimensions checked from implemented equations

| Process | Formula evidence | Dimensional result for volume-number state |
|---|---|---|
| CCN activation | `ncact=(NCCN+NC)*fraction-NC` divided by `dtcld`; same amount moves NCCN→NC (`module_mp_kdm6.F:3181-3195`) | `ncact`: `m^-3 s^-1`; both number moments must share the same coordinate. |
| Warm cloud-rain accretion | `nracw=K1*Nc*Nr*(lambda_c^-3 + lambda_r^-3)` or `K2*Nc*Nr*(lambda_c^-6 + lambda_r^-6)` (`module_mp_kdm6.F:1884-1905`) | With `Nc,Nr [m^-3]`, big-drop `K1 [s^-1]`; small-drop `K2 [m^-3 s^-1]`; either rate is `[m^-3 s^-1]`. The paired mass rates `pracw` have `[kg kg^-1 s^-1]` with those same coefficient dimensions. |
| Warm self-collection | `nccol=K1*Nc^2*lambda_c^-3` or `K2*Nc^2*lambda_c^-6`; analogous rain `nrcol` (`module_mp_kdm6.F:1908-1938`) | Same K1/K2 units yield `[m^-3 s^-1]`. This is the independent dimensional check on the accretion coefficients. |
| Cold ice/rain number collection | `nraci`/`niacr` use `pi*n0i*n0r*|v_i-v_r|*acrfac/4`, capped by `NI/dtcld` or `NR/dtcld` (`module_mp_kdm6.F:2065-2088`) | Gamma-DSD intercepts and slope moments produce `[m^-3 s^-1]`; the cap confirms the state/rate coordinate pairing. |
| Vapor ice nucleation | `Nid` target; `ninud=(Nid-NI)/dtcld`, paired with `pinud=ninud/den*Minud`, then reconstructed after mass limiting (`module_mp_kdm6.F:2490-2505`) | `Nid` and `NI` are used as `[m^-3]`, so `ninud` is `[m^-3 s^-1]`; `pinud` is `[kg kg^-1 s^-1]` when `den` is `[kg m^-3]` and `Minud` `[kg particle^-1]`. |
| Warm number source | `nraut=3.5e9*den*praut` (or `NR/QR*praut`), capped by `NC/dtcld` (`module_mp_kdm6.F:1871-1881`) | Output is a volume-number rate when `den` is `[kg m^-3]`; the first coefficient must carry the corresponding particle-per-water-mass factor. Its empirical calibration was not re-derived here. |

The `NCRK1=3.03e3` and `NCRK2=2.59e15` values are preserved. WDM6 Table A1
prints both units as `m^-3 s^-1`, but direct dimensional derivation from Eqs.
10.1/10.2 and the implemented Long forms requires K1 `[s^-1]` and K2
`[m^-3 s^-1]`; this report follows the equations, not the inconsistent K1
table label in [Lim & Hong (2010), WDM6 formulation](https://www2.mmm.ucar.edu/wrf/site_linked_files/phys_refs/micro_phys/WDM5_6.pdf).
No coefficient or threshold value was changed. [Park & Lim (2023)](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2022MS003009)
supports the Cooper curve's 500 L^-1 cap.

Validation: the directly affected existing warm/cold tests pass (97 tests).
Independent comparison of the three Python syntax trees, excluding comments
and docstrings, matches the `603ea4a` versions exactly. The source changes are
unit documentation, not a new numerical variant or native execution.

## Bounded conclusion

The number-rate and DSD formulas are dimensionally coherent when their number
inputs are volume concentrations, and the Cooper cap conversion is directly
supported by Park & Lim §2. Default operational wrapper behavior remains the
legacy direct-copy path. The opt-in oracle and selected mp337 experiment pair
dry-specific storage with density-scaled number and mass moments. Threshold
intent/calibration is not uniform or fully documented; the 10/100 gates,
numerical safety floors, and large-number slope-limiters must not be promoted
into physically calibrated cutoffs by this audit. The observation path's
frozen versus live density map and empirical threshold/coefficient calibration
remain open. S2 physical acceptance is therefore open.
