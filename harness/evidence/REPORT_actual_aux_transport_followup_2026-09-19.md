# Actual auxiliary and number-transport follow-up — 2026-09-19

**Target clarification:** validation must use the current 5 km model's native
horizontal columns and vertical levels, without external model/reanalysis data.
The pressure-bottom substitution below is retained as a historical controlled
experiment only; it is not completion of native-model-level validation. No
external data were incorporated in these experiments.

Baseline: PR #219 partial-auxiliary evidence (`bf63edb`). This is a continuation
of first-order KDM–RTTOV validation, not forecast-skill or cycling acceptance.

## Solar geometry: derived and exercised

The existing RTTOV14 solar-angle formula was replayed at the actual model-column
latitude 40.402828216552734, longitude 129.9300537109375 and slot UTC
2025-07-19 00:00:00. Zenith/azimuth are 47.77047797831327 / 98.15328966988511
degrees (azimuth clockwise from north). Applied text is 47.770478 / 98.153290.
These are calculated slot/model-location angles, not measured pixel scan angles.

The local Python replay agrees with all nine reference cases shipped in
`rttov_test_calc_solar_angles.F90` within the original 1e-4-degree tolerance
(maximum difference 5.43134e-5 degrees). The pre-existing native reference-test
executable also passes. Linking a new native driver for this specific column
failed because the Xcode license is not accepted; no license action was taken.
The actual-column angle calculation is therefore **source-formula replay**,
not a newly linked native RTTOV calculation.

Ten new live direct/K RTTOV evaluations apply these solar angles with the
previous actual WRF surface/near-surface/position and datetime substitutions.
The same five auxiliary-file hashes remain identical across the ten alpha
cases. The nine selected clean IR channels retain their BT and cost derivatives;
maximum relative FD differences remain 0.0141% for deposition and 0.1501% for
riming. The excluded SW038 baseline BT changes by -18.867620962 K. This verifies
that changed solar inputs reach the radiative calculation, while explaining why
the selected objective does not change. It does not establish solar insensitivity
for all channels or regimes.

Satellite view zenith/azimuth remain fixture values 45/0 degrees. The nominal
orbital longitude or LCC central meridian is not promoted to same-slot navigation.
The [NMSC software/data page](https://nmsc.kma.go.kr/enhome/html/base/cmm/selectPage.do?page=static.utilization.software)
provides geolocation resources; geolocation alone does not establish the line of
sight for this selected observation.

## Actual surface pressure: separate follow-up

The inventory found actual WRF PSFC=1008.88234375 hPa versus the fixture bottom
950 hPa. The earlier partial profiles therefore did not extend to the actual
surface. A second isolated experiment replaces only the bottom interface with
PSFC/100, retains the other interfaces and layer count, and obtains the layer
pressures from the existing writer's canonical log-midpoint routine. The last
layer centre is 959.9087746115106 hPa. The same grid is used for KDM/profile
interpolation and serialized RTTOV P/P_HALF. T/Q/cloud quantities are recomputed
by the existing profile builder. The reference gas values remain assumptions,
including their association with the changed bottom layer; no measured gas
profile is inferred from this pressure correction.

Ten further live direct/K evaluations retain identical auxiliary hashes and
recorded branches across alpha. VJP and JVP are exactly equal for both controls:

| Control | VJP = JVP | FD relative error at .03 / .1 |
| --- | ---: | ---: |
| deposition | -0.040080502539961094 | 7.78235e-5 / 1.57619e-4 |
| riming | -1.7230215962412903e-5 | 1.80932e-4 / 2.01876e-3 |

These are separate results from the solar-only experiment above. Both retain
the existing acceptance rule and explicit satellite-view/upper-gas limitations.
The 20 new calls comprise two ten-call experiments, not 20 independent
meteorological cases.

## Evidence boundaries and next completion conditions

| Item | Current evidence | Required to close |
| --- | --- | --- |
| Solar angles | Slot/location derivation and ten fixed-condition live comparisons | Per-pixel timing remains separate |
| Satellite view | Actual navigation not established | Authoritative same-slot angles or sufficient orbit/navigation data |
| Upper T/Q and gases | Actual PSFC bottom applied; reference upper extensions and O3/CO2 remain | Pin actually consumed profiles and their scientific provenance |
| Number units | Existing host/kg versus kernel/volume discrepancy retained | Consistent host/dynamics/PSD boundary, not sedimentation-only density insertion |
| Nonzero applied transport | Existing matched 20-second capture is zero transport | Matched-source nonzero departure/arrival and residual; no recovered-flux substitution |

RTTOV allows coefficient background trace gases when the relevant optional gas
inputs are disabled; absence of a measured profile is not universally an invalid
RTTOV input. This must be distinguished from claiming actual atmospheric gas
validation ([official RTTOV FAQ](https://www.nwpsaf.eu/site/software/rttov/documentation/rttov-faqs/)).
The selected runtime flags and consumed files, rather than schema fields alone,
define which inputs require validation.

## Local artifacts

`graphify-out/pr219-science-20260919/` contains `solar/replay_solar.py`, its JSON
with source hashes and nine reference comparisons, the native reference test
log/hash, `run_derived_solar_aux.py`, ten retained live case directories,
`derived_solar_aux.json` and `solar_comparison.json`. These depend on retained
private RTTOV/source assets and are not portable CI fixtures.

Derived-solar live JSON SHA256: `caa422f0baa041623d84e29cb5d5ae432f3b39c50b00d59b3cc07f5ba69a4028`.

Surface-pressure JSON SHA256: `b63119735026dc7119e824079f397204628ab03ffa78d9908e69a59536eddf29`. Local runner/result: `run_surface_pressure_aux.py` / `surface_pressure_aux.json`.
