# PR400 fixed-input compatibility audit

Read-only audit of the preserved PR399 direct-H input archive and the source path that constructed it. The audit made zero RTTOV, M, H, Model_H, optimizer, native-run, or acquisition calls. It does not alter controls or claim the fixed values are physically correct.

## Atmospheric profiles and gas reference

The source RTTOV fixture has 69 full pressure layers and 70 interfaces. For each selected native column, 27 upper fixture levels are retained and the native profile supplies its full 39-layer lower suffix, giving 66 RTTOV layers and 67 interfaces. The native center-pressure and REAL(4)-transcribed P8W suffixes are preserved. T and Q use the fixed fixture only above the native top; no fixture-grid remapping of native model layers is used.

O3 and CO2 are interpolated from the same fixture across the full extended pressure grid in log pressure. `numpy.interp` holds endpoint values beyond the reference bounds. The fixture is a reproducible source, not an independently validated atmospheric profile for this observation. The reference pressure range is 0.00035712855–931.65625 hPa; 0 native layers across the nine columns fall below its minimum, and 54 lie above its maximum (six lowest native levels in each column), where O3/CO2 use the held high-pressure endpoint. Native qv is dry mixing ratio and converts to RTTOV gas_units=2, ppmv over moist air, using the recorded molar masses.

All six active profile files (p, p_half, T, Q, O3, CO2) were compared with the PR399 private NPZ and independently reconstructed from the saved native NPZ plus fixture reference. Per-cell file hashes and maximum differences appear in `FIXED_INPUTS.json`.

## Surface inputs and options

Dynamic RTTOV surface fields are TSK, T2, Q2, U10, and V10. All nine saved cells are XLAND=2 and ice-free. HGT, XLAND, and sea ice remain preserved as native context; the comparison reuses one fixed AMI geometry across columns, so HGT is not varied per neighbor. Actual skin and near-surface files match the saved native values after the writer's six-decimal formatting; Q2 uses the dry-mixing-ratio to moist-air ppmv conversion.

The static fixture contributes surface type 1, water type 1, salinity 35, foam/snow fractions 0, and FASTEM values `[3, 5, 15, 0.1, 0.3]`; native TSK replaces its skin temperature. Executed settings include IR sea emissivity model 2, microwave model 3, foam-fraction use disabled, Lambertian disabled, effective skin temperature disabled, and solar disabled. RTTOV `emissivity_out.txt` ranges 0.962274146–0.987494275; it is model output under these pinned settings, not an externally validated emissivity. Channels are 10–16. The profile path uses gas_units=2, native qv as dry mixing ratio, cloud enabled, saved native rho_d, dry-number mode, ncmin 10 for land/sea, and zero T/Q blend octaves. The complete parsed namelist assignments for every cell are retained in JSON; their file hashes are identical across the nine cases.

## Preserved RTTOV K products

The eight new neighbor cases retain seven-channel `profiles_k.txt` products, and the preserved PR398 center case has one K file reused with its center H result. Across those nine direct RTTOV runK outputs, T has 4158/4158 nonzero entries, Q has 4158/4158, O3 has 4095/4158, and CO2 has 4095/4158. Skin-T and near-surface T2/Q2/U10/V10 counts are 63/63, 63/63, 63/63, 63/63, and 63/63. JSON also gives each field's maximum absolute value and file hash. Direct emissivity-K and diffuse-reflectance-K contain 0/63 and 0/63 nonzero entries; FASTEM is 0/315 and salinity is 0/63. These are preserved direct RTTOV K products. No KDM6AD Model_H or model-composed derivative was run, so this does not establish end-to-end KDM6AD derivative support or validation.

## Provenance and scope

`FIXED_INPUTS.json` binds the PR399 plan/result/postrun receipts, PR395 intake, native and PR399 private NPZs, writer and profile reader source, source fixture files, per-case active files, RTTOV coefficient/executable, and actual namelist settings by SHA-256. It makes no input, cost, bias, sigma, support, or acceptance change. The upper fixture atmosphere and surface/emissivity assumptions remain conditional inputs. The separate sensor audit reports IR133_COMPATIBILITY_MISMATCH_IN_DECLARED_CALIBRATION_TUPLE; UPSTREAM_LA_SRF_PAYLOAD_UNVERIFIED: IR133's LA calibration tuple is v3.0 while the installed RTTOV coefficient uses the v3.1 shifted center; the LA header does not identify the upstream SRF payload and no pixel BT arithmetic was recomputed. See `SENSOR_COMPATIBILITY_REPORT.md` and `SENSOR_COMPATIBILITY.json` (result SHA-256 77b759b48f7e4c5537fb1dc0d895bf98dfdd1ed7cb27b770fac3fd3903a4d8e8).

Validation: ran this read-only audit helper and parsed its JSON output. No radiation or model calculation was executed by the audit.
