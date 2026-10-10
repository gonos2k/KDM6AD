# PR401 saved center RTTOV K response audit

## Scope and replay

This is a metadata and saved-output replay of the existing PR398 center direct-H/runK case at `(j=86,i=48)`, `2025-07-19_05:56:00`, with seven channels 10–16. It made no new RTTOV, H, K, M, Model_H, native, preprocessing, optimizer, acquisition, or observation-pixel calls. The center is the previously reused direct-H center, not a final accepted analysis.

The production parser recovered `RADIANCE%TOTAL`, native `RADIANCE%BT`, quality, and every `PROFILES_K` field from the same `out/k` outputs. Saved `channels.txt` is exactly `10 11 12 13 14 15 16`; the output profile count is one; `adk_bt=.TRUE.`, `use_q2m=.TRUE.`, active and reference fixture `gas_units=2`, and `run_gas_units=2`. All seven quality flags are zero and support is all one. Applying the existing `transform_rttov_to_kma` to the same-run radiance/native BT scales every K field; converted center BT agrees with the prior receipt within the production `3e-6 K` replay tolerance.

Recomputed dimensionless normalized Huber objective is `26.597684782122` versus saved `26.597684782122` (the saved receipt field is named `Jo_huber_K_units`). Residuals and sigma are in K with `sigma=1 K`. Maximum converted BT difference from the saved center is `0 K`.

## Input directions and linear response

| Direction | Declared input perturbation | Approximate dimensionless delta-Jo, channels 10–15 | Channel 16 IR133 term | All seven channels |
|---|---|---:|---:|---:|
| skin_T_plus_1K | `{"kind": "absolute", "units": "K", "value": 1.0}` | 2.2077723 | 0.095352651 | 2.303125 |
| reference_o3_plus_1pct | `{"fraction": 0.01, "kind": "relative", "units": "of the 69-level reference profile"}` | -0.13390524 | -0.0079017479 | -0.14180699 |
| reference_co2_plus_1pct | `{"fraction": 0.01, "kind": "relative", "units": "of the 69-level reference profile"}` | -0.0039360203 | -0.040563601 | -0.044499622 |
| near_surface_Q2_plus_1pct | `{"actual_delta_ppmv_moist": 298.76367, "fraction": 0.01, "kind": "relative", "reference_value_ppmv_moist": 29876.367}` | -0.002678257 | -0.00032138555 | -0.0029996425 |
| upper_reference_T_plus_1K | `{"kind": "absolute", "units": "K on upper 27 active levels", "value": 1.0}` | 0.2136492 | 0.02104371 | 0.23469291 |
| upper_reference_Q_plus_1pct | `{"active_Q_max_ppmv_moist": 5.999964, "active_Q_min_ppmv_moist": 0.4341651, "fraction": 0.01, "kind": "relative", "units": "of upper 27 active Q values in ppmv moist"}` | -7.7183249e-05 | -4.176969e-06 | -8.1360218e-05 |

Directions are: skin temperature +1 K; source O3 +1%; source CO2 +1%; saved near-surface Q2 +1% in its actual RTTOV ppmv units; upper 27-layer T +1 K with the 39 native T levels fixed; and upper 27-layer Q +1% in active ppmv with the native suffix fixed. The actual Q2 value and 1% delta are explicit in the table and CSV. `K_RESPONSE_DIRECTIONS.csv` lists declared scales, units, affected levels, and channelwise BT/Jo responses; exact per-level input delta vectors, reference beta vectors, P and K arrays are preserved in the private NPZ. Baseline channel order and residuals are in `K_RESPONSE_CHANNELS.csv`.

These are unit/example perturbations, not estimated input errors or corrective fits. `delta-Jo` is the first-order derivative of the unchanged Huber objective at the saved center, not a cost from a perturbed forward run. The channel 10–15 subtotal and channel 16 term only describe the seven-channel result; no channel was removed or ablated.

## Log-pressure interpolation and endpoint correlation

The audit builds `P[active layer,reference layer]` on log pressure from the saved 69-level fixture to the 66-level active profile. `P @ beta_reference` reproduces the active O3 and CO2 files, and `(K_z @ P) @ beta_reference` agrees with `K_z @ (P @ beta_reference)` within the recorded contraction tolerance.

Exactly 6 high-pressure active levels `[60, 61, 62, 63, 64, 65]` fully hold the final reference O3/CO2 value. Two additional active levels `[58, 59]` have fractional final-endpoint weights `[0.20259912553000273, 0.866921786235077]`. The audit separates held and partial K contributions, then confirms their sum matches the last source-reference-level contraction. All of these terms arise from one correlated source endpoint, not eight independent errors. Per-channel endpoint sensitivity and contribution are in `K_RESPONSE.json`.

## Limits and preserved evidence

The stored NPZ preserves native and KMA-coordinate matrices, active and reference profiles, the interpolation matrix, all input directions, and response/cost contractions. Its canonical copy is mode `0600` in a mode `0700` directory. Source, receipt, case output, coefficient, reference profile, active profile and surface hashes are recorded in `K_RESPONSE.json`.

This establishes a local direct observation-operator response for one saved center. It does not establish KDM6AD Model_H, model-composed derivatives, an accepted analysis, valid physical error ranges, or input error. No H/M/model rerun or parameter fitting was performed.
