# PR401 saved-center K response direction plan

**Frozen before the final versioned response audit.** This plan describes linear contractions of the existing center K matrix only. It does not select directions by their resulting BT or cost response.

## Case and output contract

- Case: saved PR398-reused center at `(j=86, i=48)`, `2025-07-19_05:56:00`, direct-H/runK output already retained in the PR399 packet.
- Preserve AMI channels 10–16 in source order: WV073, IR087, IR096, IR105, IR112, IR123, IR133.
- Read `RADIANCE%TOTAL`, `RADIANCE%BT`, `RADIANCE%QUALITY`, and every `PROFILES_K` field from the same saved `out/k` result. Require the saved run contract `adk_bt=.TRUE.`, `use_q2m=.TRUE.`, profile `gas_units=2` (ppmv over moist air), and seven all-zero quality values.
- Apply the existing `transform_rttov_to_kma` to the same-run native BT, total radiance, and every K field. Verify converted center BT against the saved prior receipt before any direction is summarized.

## Declared directions

These are unit/example perturbations for a local linear response calculation; they are not input-error estimates, recommended correction sizes, or physical acceptance ranges.

1. `skin_T_plus_1K`: +1 K in the saved scalar `SKIN(1)%T`.
2. `reference_o3_plus_1pct`: +1% of the full 69-level O3 reference vector, projected to the active 66-layer profile by matrix `P`.
3. `reference_co2_plus_1pct`: +1% of the full 69-level CO2 reference vector, projected by the same `P`.
4. `near_surface_Q2_plus_1pct`: +1% of the saved `NEAR_SURFACE(1)%Q2M` value, in the actual RTTOV input unit ppmv over moist air.
5. `upper_reference_T_plus_1K`: +1 K on the 27 upper fixture-reference T levels; hold all 39 native T levels fixed.
6. `upper_reference_Q_plus_1pct`: +1% on the 27 upper fixture-reference Q values in active ppmv over moist air; hold the 39 native Q levels fixed. This optional direction is included as an explicitly declared fixture-only example.

## Interpolation, endpoint and cost calculations

Construct `P[active_layer, reference_layer]` from the saved active pressure centers and reference pressure centers using linear interpolation in log pressure and constant endpoint holds, matching the saved `numpy.interp` path. Verify `P @ beta_reference` reproduces the active O3 and CO2 inputs and verify `K_z @ (P beta) == (K_z P) beta` within numeric contraction tolerance. Report the six fully held high-pressure layers separately from any partial weights on the last reference level; they share one source endpoint and therefore one correlated perturbation.

For each direction, report channelwise first-order `deltaBT_K = KMA_K @ delta_input`. With the same fixed center observation, frozen support, `sigma=1 K`, `bias=0 K`, and `Huber delta=1`, report only the local linear term `deltaJo = support * Huber'(residual/sigma) * deltaBT/sigma`. Split the reported sum into channels 10–15 and the channel-16 IR133 term; keep all seven support entries active. Do not evaluate a perturbed H, remove a channel, fit a parameter, or interpret the split as an ablation.
