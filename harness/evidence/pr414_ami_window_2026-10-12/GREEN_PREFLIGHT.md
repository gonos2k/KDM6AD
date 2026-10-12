# Green preflight review: PR414 three-slot Jul19 window

I checked the final `WINDOW_PREDECLARED.json`, `PREFLIGHT.json`, `run_window.py`, `OBSERVATIONS.json`, the S3 download receipt, and the read-only compact observation payload. The one-shot preflight is internally consistent and source-bound. The coordinator has since started the separately declared single analysis; this note does not report its post-run outcome. Green made no M, H, optimizer, or native-model call.

## Observation inputs and time linkage

The plan SHA-256 is `fc704e2af5c68674e91afeaffd3e61102ebdcc167660f8b515fe123d6a1111cd`; the recorded preflight names that exact declaration and is `PREPARED_NO_ANALYSIS` with `analysis_executed=false`. The runner SHA matches its declaration. I independently checked all 114 declared file/source bindings and 33 external asset paths, sizes, and SHA-256 values. The observation receipt separately binds 42 paths: 27 raw inputs (the original nine 05:56 files plus exactly 18 newly downloaded 06:06/06:16 files), the compact NPZ, receipts, calibration, readers, and source listing. The new S3 download receipt reports exactly 18 files / 8,849,101 bytes; each object has one recorded request attempt, and all per-file SHA/size/ETag records match the retained bytes. The compact NPZ SHA and `0600` mode match; its three y_BT/DQF vectors equal `OBSERVATIONS.json`. No full-scene L1B arrays are published.

The briefly reported 16/18 interruption is retracted in [DOWNLOAD_INTERRUPTION_CORRECTION.json](DOWNLOAD_INTERRUPTION_CORRECTION.json). The successful private download/decode receipts and `OBSERVATIONS.json` are authoritative: all 18 files completed in the same original no-retry pass, decoding completed, and there are no remaining partial files. No second download request occurred.

Each scene independently selected the nearest finite GEOS pixel to the fixed PR412 native column before inspecting BT/DQF. All three resolve exactly to row 289 / column 49 and the original coordinates/GEOS navigation; distance is 425.935 m. All seven channels 10–16 are finite and DQF0 at every slot. The reader retains per-slot time metadata:

| Local index | Filename OBT | Raw scene acquisition OBT | Planned UTC metadata | Pixel UTC |
|---:|---|---|---|---|
| 1 | 202507190556 | 20250719_055656 | 2025-07-19 05:50:00Z | unverified / null |
| 31 | 202507190606 | 20250719_060656 | 2025-07-19 06:00:00Z | unverified / null |
| 61 | 202507190616 | 20250719_061656 | 2025-07-19 06:10:00Z | unverified / null |

These timestamps remain distinct. The declared research assumption maps nominal filename labels to model UTC for the local window; planned UTC and raw OBT are not treated as actual pixel time. The numeric observation/synchronization fields remain raw seconds without a resolved epoch.

## Same-case model and H contract

The input background fingerprint exactly matches the PR412 05:55:40 saved state, and its forcing fingerprint exactly matches the original PR412 `f0`. The H fingerprint matches the PR412 configuration after the fresh fixture directory is removed: AMI 10–16, native pressure/reference grids, 39-level frozen optical `rho_d`, surface and geometry, coefficients, dry-number mode, and existing blend/number-floor controls. The plan preserves the native column `j=103, i=48`, zero controls from original `xb`, one common initial prior, 61 local 20-second KDM steps, and slot indices `[1,31,61]`; it declares the same validated initial forcing `f0` held across those steps. The T prior has 39 active levels at 0.8 K and qv has 12 active bottom levels at log sigma 0.08, for 51 initial controls; all other state controls and the four physical parameter controls are fixed. The three observations use one 7-channel all-sky cost each with 1 K sigma, zero bias, normalized Huber delta 1. This gives 21 equal-scale channel-time Huber terms; temporal error independence/covariance is an explicit uncalibrated assumption, not a measured error model.

This is a declared held-forcing local KDM window from the retained July19 native background, not a full WRF forecast through 06:16 or host cycling. No later native states or time-varying forcing sequence are bound by the observation producer; the analysis is explicitly the predeclared local-forcing hypothesis. Pixel UTC and atmospheric truth remain unverified. The bounded optimization budget is max_iter 3 with Torch's default nominal max_eval 3; line-search behavior and convergence must be reported from the actual run.

## Disposition

Green preflight passes for the one declared three-observation window. The coordinator's execution marker is now present, so subsequent claims must come from its single captured result/checkpoint and audit. This preflight does not establish solver convergence, physical forecast accuracy, time-collocated satellite truth, or independent-date evidence.
