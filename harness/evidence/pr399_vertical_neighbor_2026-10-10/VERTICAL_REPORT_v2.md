# PR399 native vertical-neighbor diagnostic

This diagnostic reads the hash-bound PR398 saved native patch NPZ only. It performs no native forecast read, model integration, M/H call, optimizer, RTTOV execution, or arbitrary-height remapping. The same 27 fixed columns and three saved endpoints are retained.

## Vertical structure

All layer coordinates are native WRF levels in bottom-up order. Interface geopotential is computed from float64-first `(PH+PHB)/g`; native midheight is the average of adjacent interfaces, then surface `HGT` is subtracted for AGL. The lower 12 native levels span 26.5–2381.5 m AGL, with actual adjacent midheight spacing 60.3–436.8 m, so the diagnostic preserves nonuniform vertical spacing. The complete per-column lower-12 profiles are in `VERTICAL_RESULT_v2.csv`; the native maxsat level plus its immediately lower and upper neighbors, with actual height and pressure, are in `VERTICAL_MAXSAT_CONTEXT_v2.csv`.

Across all 27 columns at all three times, the phase-aware `qv/qs` maximum occurs at bottom-up layer 3. At that native layer, center pressure is 977.10–977.16 hPa, midheight is 260.7–260.9 m AGL, and phase-aware saturation diagnostic is 95.146–95.988%. Native center pressure is float64-first `P+PB`. P8W interface pressures are separately shown as the existing Python REAL(4) transcription; they are not actual host-produced interfaces.

The report includes native temperature, dry mixing ratio `qv`, KDM6 liquid `qs_water`, liquid ratio `S=100*qv/qs_water`, and virtual potential temperature. `theta_v` is computed both as `theta_d*(1+qv/epsilon)/(1+qv)` and `(THM+300)/(1+qv)`; the two forms are checked for agreement. Temperature inversion and positive `dtheta_v/dz` stable-sign flags are descriptive diagnostics only; they do not identify PBL forcing or causes.

## Endpoint changes

`VERTICAL_SENSITIVITY_v2.csv` compares frames 1→4, 4→6, and 1→6 at each column’s layer-3 maxsat level. Each finite endpoint change in liquid saturation `S` is decomposed using local partial derivatives with respect to `qv`, `T`, and `p` evaluated at the starting endpoint. The exact endpoint difference minus those first-order terms is reported as a nonlinear/finite-step remainder. The table does not divide by elapsed seconds; neither the terms nor remainder are process rates or process-tendency attribution. All layer-3 endpoints are warm and outside the KDM6 liquid-q saturation clip branches; the result records this gate explicitly.

Detailed data and source identities are in `VERTICAL_RESULT_v2.json`. Canonical private derived arrays: `/Users/yhlee/KDM6AD-k/host/research_evidence/pr399_vertical_neighbor_20261010_v2/vertical_structure_27columns_3times_v2.npz` (SHA256 `5d02e8bbf4e5e54d049a818260adb2f3480aad9edd3661b282d55c24130263c0`, file 0600, parent 0700). Input PR398 NPZ SHA256 `947c72c12ebe289b7ddc84fba1281635d77ffbcfe23f204345cc97abeebc1c21`. Science acceptance is not asserted.

## Quantitative endpoint and stability readout

Across the 27 column/endpoint-pair rows (three endpoint pairs per cell), `ΔS` ranges +0.0154 to +0.0625 percentage points. First-endpoint local `qv` partial contributions range +0.0336 to +0.1009 points; `T` contributions range −0.0560 to −0.0068 points; `p` contributions range −0.0017 to +0.0043 points. The finite-step remainder ranges −3.78×10⁻⁵ to −2.86×10⁻⁶ points. These are partial-change terms for the stated endpoints, with seconds recorded only as interval context and never used as a denominator.

Among the 891 adjacent native-level pairs across 27 columns and three times in the lower 12 levels, 51 have temperature increasing upward and 216 have a positive virtual-potential-temperature gradient. These are sign diagnostics for the sampled profiles; they do not establish a PBL mechanism, cause, or process tendency.
