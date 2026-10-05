# Unified KMA full-domain and window check

The live normalized-dry/KMA v3.0 path completed a bounded full-domain analysis and separate one-step and one-hour `run_da_window` directional checks on the retained C5 column. The full `FrameData` came from the retained 5-km forecast at time index 1. It has 65,988 domain columns; the observation/QC record selected exactly one interior column, flat index 36,576 (i=73, j=157). Thus this is full-domain input/membership integration, with a one-column optimization subspace, not a 65,988-column optimization.

The selected native state and forcing matched the retained C5 profile bit for bit. The selected column retains 39 native layers. The optical grid contains 24 declared reference-top layers, 63 centers and 64 interfaces. The last 39 optical center pressures equal the retained native centers, and the last 40 interfaces equal the reversed native P8W real4 vector after conversion to hPa. The input-frame state and forcing for the selected column remained unchanged. The result preserves the full-domain output fields NPZ as a public artifact.

The observation is the same raw KO pixel `(411,338)` and channel files from the pinned C5 receipt. Its older saved BT values used the archived nominal-wavelength decoder. This run decoded the same raw words with the current paired-wavenumber KMA v3.0 table; IR105 changes by +1.57635 K, for example. All nine raw channel quality flags at the pixel are zero, and the predeclared channel gate retains seven channels. The current v3.0 decode is used consistently for the model coordinate and observation target.

The full-domain call used `normalized_dry=True`, `observation_coordinate="kma_v3_0"`, channels 8–16, one worker, `max_iter=2`, `max_cloudy=1`, `max_clear=0`, boundary 10, `obs_time=1`, `dt=20 s`, `qv_levels=39`, `ncmin_land/sea=10/10`, Huber delta 1 and zero bias. Geometry and surface came from the selected-profile preparation receipt; the explicit C5 fixture supplies the RTTOV optical background and coefficient assets. The nominal observation is 00:00:00 and the model frame is 00:00:20, so the data-derived offset is −20 s. For the one-step observation slot, the difference is 40 s and the caller explicitly used a 40-second tolerance.

The full-domain objective trace begins at 19.9634318 and ends at 13.4689338 (observation term 13.2355702). Mean absolute O−B is 3.32062 K and mean absolute O−A is 2.37027 K on the fixed support. The run used two minimizer iterations and ended with gradient norm 1.50461; it is not reported as converged. The full-domain report shows no nonfinite fields or hydro pathologies at t0 or slot time. Its NC increment is large and remains an unaudited numerical result, not an accepted physical adjustment.

The independent one-step window check uses the same frozen-background-density callback for BASE and both initial-qv endpoints. With direction `0.01 * initial_qv` and `h=1e-4`, its directional VJP is −7.5465777376 and central FD is −7.5465777388 (relative difference 1.59e−10). The 180-step, fixed-forcing window uses the same single frozen callback and support; BASE contributes the VJP while plus/minus are value endpoints. Its VJP is −7.4240808993 and FD is −7.4240811538 (relative difference 3.43e−8). All runs report seven valid cost channels.

The 180-step check applies the retained 00:00:00 target at a 01:00:20 model slot. It is a fixed-target numerical window check, not time-collocated forecast evidence. Both windows use the frozen background-density contract; they do not enable the separate PR372 live-entry-density map. Stable objective signatures and seven-value support do not establish that every raw RTTOV quality bit or internal solver branch stayed unchanged.

The receipt pins the runner, profile, raw observation files, legacy and current calibration tables, forecast, fixture, resolved coefficient, RTTOV executable and every Python source file under `oracle/kdm6` at campaign start and end. It also records Git HEAD, HEAD tree and porcelain status at both points. The source inventory remained unchanged across the run. Native P8W and full-profile inputs are tied to the private preparation receipt. Thread settings were fixed at one. The receipt's `full_domain_elapsed_s` field spans the full campaign, including both independent window checks, rather than only the full-domain optimizer call.

After adding the expanded provenance, final3 reproduced final2 exactly: all 13 arrays in the window NPZ and all 60 full-domain field arrays are raw-bit identical; the objective trace, window costs, VJP/FD values and report audits also match. The copied public analysis-fields NPZ has the same SHA-256 as the final3 run output.

Final3 artifact SHA-256: runner `b0ebcb54bf5580659762f25221ff0159d16e34d39f7eaa44d08ecee16bbe3083`, result `ff8b4c840458e8841f264ab3234079d02dc72ed0fc18cddbc358a392cabe0359`, window arrays `f18717ba3e719590aff7fbe778ec10ffa476d7245b3b016a046821ca87c6e1fb`, and analysis fields `4489b0722c3dd9c0fa7490ffa52c68be0743a400f71d653ffa1e8b00a82b398b`. Git HEAD was `a79f95c30c8dbdcc7ace0ef198b54f6828c8ae6b` with tree `e54f9fd9036c131beca3b7ff45246bd1c617625d`; start/end library-source hashes match.

This experiment does not approve the observation cost or covariance, resolve physical number calibration or SRF compatibility, establish forecast skill or time accuracy, validate repeated assimilation cycling, or authorize host writeback. It does not demonstrate a full-state Jacobian or operational analysis.

Artifacts:

- [Runner](UNIFIED_KMA_window_source_2026-10-05.py)
- [Result receipt](UNIFIED_KMA_window_result_2026-10-05.json)
- [Window arrays](UNIFIED_KMA_window_arrays_2026-10-05.npz)
- [Full-domain analysis fields](UNIFIED_KMA_analysis_fields_2026-10-05.npz)
