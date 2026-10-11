# Retained Jul19 case: what the actual result supports

Basis main `4ebe3d76` (PR409). This reads the already executed Jul19 case; it does not create another analysis/date or reopen the problem definition. [RESULT.json](RESULT.json) binds the new endpoint comparison to the original checkpoint/receipt and 19 unchanged source files. [read_retained_case.py](read_retained_case.py) reads private arrays and existing public records only: no native, KDM M, RTTOV H/K or optimizer calls. Full arrays remain private.

## Stored actual response

The [original capture receipt](../pr395_tq_state_capture_2026-10-10/RESULT_3d2e97f159.json) contains actual RTTOV outputs for **H(M(x_b))**, call2/c1, and **H(M(x_a))**, call5/c4 final audit. The preceding zero-mask probe is not the initial observation cost. Both retained objective calls have channels10–16, mask7/7 and rad_quality0 under the same declared H auxiliaries/forcing. Direct H(x_b) and H(x_a) outputs are absent; four stored states do not mean four executed H values.

| Original cost | Background | Accepted |
|---|---:|---:|
| Observation J_o | 26.588575903055926 | 26.135616402715186 |
| State prior J_b | 0 | 0.2284737909127953 |
| Total J | 26.588575903055926 | 26.36409019362798 |

Observation-cost decrease is0.4529595003407394; the recorded relative decrease is1.7035869%, total-cost decrease0.8442938%. These are conditional fit measures, not weather skill. The [stored channel residuals](../pr397_actual_native_results_2026-10-10/CHANNEL_RESIDUALS.json) are model−observation, in K:

| AMI | Background residual | Accepted residual |
|---|---:|---:|
|10/WV073|−1.030367|−1.038011|
|11/IR087|+5.133124|+5.067553|
|12/IR096|+6.989291|+6.947445|
|13/IR105|+4.930225|+4.856613|
|14/IR112|+4.983241|+4.888846|
|15/IR123|+4.400014|+4.290242|
|16/IR133|+2.622313|+2.546908|

Six improve and WV073 worsens slightly. Gradient L∞7.8173583084e−5 exceeds tolerance1e−10; termination UNKNOWN and finite evaluation-budget return remain, not strict convergence. Initial theta39/qv12 controls, fixed parameters, sigma1K, zero bias and normalized Huber delta1 are unchanged.

## New endpoint/input comparison

The original private NPZ contains all12 fields of x_b,x_a,M(x_b),M(x_a). For each initial→slot pair:

| Compared quantity | x_b→M(x_b) | x_a→M(x_a) |
|---|---|---|
| Other11 State fields | Bit-identical | Bit-identical |
| Potential temperature theta | Max difference5.684341886080802e−14K | Same maximum |
| Physical T=theta*pii | Bit-identical, all39 cells | Bit-identical, all39 cells |
| Supplied forcing | Same recorded frame0 | Same recorded frame0 |
| Optical rho_d/H auxiliaries | Frozen from background | Same frozen configuration |

NumPy and Torch independently evaluated the literal saved-array T projection and matched bitwise. The executed source hashes match current files: [temperature/profile builder](../../../oracle/kdm6/obs/model_profile_builder.py) reads theta through T=theta*pii; the [cloud bridge](../../../oracle/kdm6/rttov_bridge.py) enters [runtime's coordinate transform](../../../oracle/kdm6/runtime.py) the same way. Its other state inputs and supplied/frozen measures are identical in each pair. The fixed interpolation/upper references/gases/surface/geometry/options/BT conversion therefore receive equal forward-value inputs. This is source/input-equivalence evidence, not a fresh RTTOV evaluation or rebuilt whole optical profile.

**Conditional on the same deterministic unchanged H and its declared fixed auxiliaries, infer R_M(x_b)=R_M(x_a)=0 and I_M=0 in all seven channels for these endpoints.** RESULT.json labels these values `SOURCE_INPUT_EQUIVALENCE`; they are not stored direct-H outputs. No extra H is needed for this limited forward-value claim.

For the same stored initial-state pair, G_M is the actual recorded J_o decrease above. The input-equivalence inference gives G_0=G_M and inferred G_M−G_0=0. The prior difference cancels in this same-state contrast. This does not compare separately reoptimized systems. I_M and cost contrasts remain different quantities in general; their zeros coincide here because both R_M values are zero, not because applying Huber once to I_M gives a cost gain.

The case shows conditional T/Q-fit improvement without an additional forward endpoint response introduced by this20s M. It does **not** establish M_x=I, inactive internal rates, named-process causes, a better no-M optimizer, cloud/NC truth or forecast skill. Small rounding in theta is not a physical heat increment. At all four endpoints, the five condensate mixing ratios and NC are zero; internal states/process rates were not recorded and are not reconstructed here.

## Existing state/measure evidence and remaining limits

The [original saved-array interpretation](../pr397_actual_native_results_2026-10-10/ACTUAL_ARRAY_CALCULATIONS.json) already records maximum initial cooling−0.15252247K, maximum vapor increase1.19243424e−4kg/kg dry, and maximum liquid saturation ratio95.534406%→96.751478%. Those diagnostics are read, not rerun. Fixed host-eta dry-mass water added by analysis is+0.2216824149kg/m²; local M's retained background/analysis water changes are0. Native host20s water change−0.00236003599kg/m² includes a changing-mass term. These measures and T/theta changes do not close external-flux water/heat budgets or identify processes.

Historical native run is scheme337, variant2/dry-number1, one rank/thread; compiled source snapshot/launch checkout/executed consumer remain separately attributed in the [original report](../pr397_actual_native_results_2026-10-10/REPORT.md). Rank/launcher/archive completion and outer harness exit120 are distinct; the latter's precise cause is unresolved. Nominal AMI time, pixel UTC/footprint and upstream SRF limits remain. Original H executable/coefficient hashes were not recorded, so this does not certify another binary/configuration.

[PR398 host-frame H](../pr398_followup_2026-10-10/REPORT_v2.md) and [PR399 neighbor H](../pr399_vertical_neighbor_2026-10-10/) have different state/forcing/density bindings; they cannot fill H(x_b)/H(x_a) as measured counterfactuals. Historical VIIRS/L2 selection labels are not admitted as new phase/truth evidence. Only the fixed AMI L1B observations and declared model inputs are used for these claims. No score, independent case or overall-process completion is added. July20/21 native analyses remain pending; another available date must be selected before residual inspection.
