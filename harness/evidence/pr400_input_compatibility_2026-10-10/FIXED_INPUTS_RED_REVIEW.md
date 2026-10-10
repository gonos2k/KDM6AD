# PR400 fixed-input Red review

Red independently audited the preserved PR399 attempt-2 inputs and outputs after the Green sensor/SRF audit was completed. This review made no RTTOV, H, M, Model_H, optimizer, native-run, or pixel-data calls.

## Findings

No new blocking integrity issue was found in the fixed-input packet. The active p, p_half, T, Q, O3, and CO2 profile files for all nine rows agree with the hash-bound PR399 NPZ within serialization precision. An independent reconstruction from the saved PR398 native patch, PR395 reference fixture, and archived profile-building equations reproduced the 66-layer profiles. The original fixture files still match the PR395 receipt hashes; its 69 layers/70 interfaces provide 27 upper levels, followed by 39 native layers and 40 native pressure interfaces.

The source gas extrapolation limit is material and now explicit: fixture centers span 0.00035712855–931.65625 hPa. No native layers are below the lower-pressure bound; 54 across the nine columns, six in each column at the high-pressure end, exceed the fixture maximum. The executed `numpy.interp` behavior therefore holds the fixture O3/CO2 endpoint for those lowest native levels. This is a reproducible fixed reference assumption, not proof that the gases represent the observed atmosphere.

The actual dynamic RTTOV surface files match native TSK, T2, Q2, U10, and V10 after six-decimal writer formatting; Q2 conversion uses the recorded dry-mixing-ratio to moist-air ppmv equation. All cells are open ocean and ice-free. One AMI geometry is reused across the nine cases, so HGT is preserved as context and is not varied between neighbor calls. Static skin values, emissivity options, complete namelist maps, coefficient/executable hashes, channel IDs, and profile options are recorded in `FIXED_INPUTS.json`.

The read-only inventory finds eight new PR399 neighbor RTTOV runK K files and one existing PR398 center K file reused with the H result. Gas and selected skin/near-surface K fields are present in the saved files. Direct emissivity-K, reflectance-K, FASTEM, and salinity perturbation fields are zero. These are observation-operator K products; they do not demonstrate a KDM6AD Model_H derivative or an end-to-end model sensitivity.

I cross-checked Green’s sensor/SRF result against its saved metadata-only audit and the local source receipts. It correctly limits the finding to a declared calibration tuple mismatch for IR133: the LA files identify v3.0 while the installed RTTOV coefficient uses the v3.1 shifted center. The files do not identify the upstream LA SRF response and no pixel BT arithmetic was recomputed. This is an unresolved channel-16 compatibility caveat for the seven-channel batch, not evidence that it caused the residual. The official [NWP SAF supported-platform table](https://nwpsaf.eu/site/software/rttov/documentation/platforms-supported/) maps AMI sensor ID 93 and channels 1–16 to RTTOV 1–16; its [SRF documentation](https://nwpsaf.eu/site/software/rttov/download/coefficients/spectral-response-functions/) directs channel-order checks to coefficient headers or `rttov_coef_info`. The actual installed coefficient header/utility output supplies this run’s local channel centers.

## Disposition and coverage

The packet is source-attributed and its limits are stated. Keep the fixed fixture gas reference, held high-pressure endpoint, fixed surface model, and IR133 mismatch visible when interpreting the PR399 radiances. No input, sigma, bias, support, or acceptance setting was changed.

The existing code graph query follows `qv_to_q_ppmv_moist` through `model_to_rttov_tensors`, `make_live_run_k`, and PR399 `_run_neighbor`. It does not semantically index the new Markdown evidence, so the scoped semantic fragment and graph save-result are retained under `graphify-out/pr400-input-compatibility-2026-10-10/`.
