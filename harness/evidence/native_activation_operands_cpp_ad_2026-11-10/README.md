# Native activation minimum operands (2026-11-10)

This packet extends the [#575 activation-boundary evidence](../native_activation_upper_boundary_cpp_ad_2026-11-10/README.md) for the same saved native `(203,149)` column, 39 levels, 20-second f64 `kdm6_fn` call. The initial input axes are TH16 (potential temperature, absolute K seed) and QV16 (relative seed). It records the **actual live C++ operands** of two `torch::minimum` operations in the activation path. The production `libtorch/` and `oracle/` trees are unchanged. The executed coordinator is an isolated test-only copy, and a rebuilt private archive and runner produced the saved results.

## Executed path and evidence

The instrumented source computes `activation_fraction_pow = ops::safe_pow(sw_ratio, ACTK)` once and passes that same tensor into `minimum(ones_like(sw_ratio), activation_fraction_pow)`. It then records the source-order activation numerator before and after its zero clamp, `ncact_raw`, the actual `max(NCCN,0)/dt` tensor passed as the other rate-limit operand, the pre-gate minimum output and the post-gate `ncact`. `safe_pow_clamped_base_diagnostic` separately reconstructs the EPS-clamped base for inspection; it is **not** the internal `safe_pow` tensor and is not fed into the physics calculation. Comparison flags state only whether the recorded operand values are less than, equal to or greater than each other. They do not reveal an operator's hidden selector at equality.

The new boundary mode retains the parent's **190 full-call forwards**: baseline off/on 2, value bisections 168, strict-side AD points 4 and one-sided FD endpoints 16. Its saved on/value/AD/FD observations have distinct event IDs and contiguous call ordinals 1–189; the baseline off call is ordinal 0 and has no stage observation. The child replay first runs the SHA-pinned #575 verifier, then compares every old result field of the new run against the parent's saved result, preserving f64 raw bits, array shape and JSON types. The isolated default run also projects exactly to the old C++ result, including all 468 final-state words, existing JVP/VJP rows and thermal endpoints. New instrumented stage fields are the only projection exclusions.

The 189 recorded events represent 105 distinct full TH16/QV16 inputs; **84 inputs were evaluated twice**. The replay now compares their entire new `operand_values` records with JSON types and f64 raw bits, while retaining separate event IDs and call ordinals. Its independent Python `math.pow` diagnostic permits at most 16 ULP relative to the captured C++ operand; the negative regression constructs a 17-ULP difference from the **current runtime calculation**, so an allowed libm difference does not make the test fail spuriously. Simulated offsets of −16, −1, +1 and +16 ULP retain the original saved-result contract and the 16/17-ULP acceptance boundary.

The [manifest](manifest.json) pins the new executed coordinator, runner, default and boundary outputs, flags, CMake caches and build/run receipts. The [build receipt](raw/build_receipt.json) records the isolated archive, DSO and executable hashes and the unchanged native input hash; the [run receipt](raw/run_receipt.json) records commands, controls and output hashes. Public replay checks the saved evidence. It does not rebuild the private archive or repeat host/RTTOV runs.

## Observed operand branches

Across the **189 recorded on/value/AD/FD events** (excluding the off call), the pre-minimum pow operand is below one in **104**, above one in **85**, and exactly one in **0**. The actual activation-rate operand is below `NCCN/dt` in **104**, exactly tied in **85**, and above it in **0**. The smallest recorded `sw_ratio` is about `0.815855`, well above `EPS=10^-15`, so the diagnostic base floor is inactive in this selected sweep.

| Initial axis and adjacent endpoint | `sw_percent` | Actual `activation_fraction_pow` | First minimum | `ncact_raw` versus actual rate-cap operand |
| --- | ---: | ---: | --- | --- |
| TH lower `4073ff3df21f1aca` | `0.48000000000010257` | `1.0000000000001283` | Strict upper operand `1` | Equal: `5,000,000 = 5,000,000` |
| TH upper `4073ff3df21f1acb` | `0.4799999999999027` | `0.9999999999998784` | Strict pow operand | Raw rate below cap |
| QV lower `3f7dfbea42c929bb` | `0.47999999999999154` | `0.9999999999999895` | Strict pow operand | Raw rate below cap |
| QV upper `3f7dfbea42c929bc` | `0.48000000000001375` | `1.000000000000017` | Strict upper operand `1` | Equal: `5,000,000 = 5,000,000` |

The previously observed `activated_fraction=1` at these adjacent points therefore comes from a **strict `pow>1` value comparison**, not an observed first-minimum tie. The second minimum is separately tied there. No first-minimum value tie is present in this packet; the second-minimum tie's derivative selection cannot be identified from these directions because both relevant rate-operand JVPs are zero at the strict interior points. A synthetic tie regression tests the replay's value logic, not an observed native tie gradient.

At the four strict interior points, the pow operand has nonzero JVP even on the fraction-`1` side: TH `−7.402293010971694` and QV `+122.55033260458208`. The selected fraction and applied activation rate have JVP zero on those sides. On the below-one sides, pow and selected-fraction JVPs agree: TH `−7.475034544315362`, QV `+124.56156041756262`. These are derivatives of the same full f64 call at the selected internal points. The packet stores VJP rows and separately run one-sided value endpoints; the replay checks source-order value arithmetic, raw tensor handoffs, JVP/VJP relationships, same-branch difference records and finite outputs.

The pow-operand JVP has at least one resolved same-side one-sided FD scale with relative residual below `10^-5` at **each** interior point. The best recorded residuals are about `2.36×10^-6` (TH fraction-`1`), `1.08×10^-7` (TH below one), `4.06×10^-6` (QV fraction-`1`) and `2.85×10^-7` (QV below one). The two raw-rate-below-cap sides also have an applied minimum-rate FD scale below `10^-6` relative residual. On the observed rate-tie sides, the rate and cap JVPs are both zero and the minimum-rate FD changes are unresolved at output precision; those cases do not measure the tie subgradient. The larger finite-step residuals remain recorded and are not reported as uniform `10^-6` accuracy.

## Limits

The result concerns one native column, two initial state axes and the observed f64 branches. The first minimum has no observed equality case, and a recorded equality of the second minimum's input **values** does not certify a unique mathematical derivative or an operator tie rule. The adjacent-input NC differences in #575 remain numerical diagnostics, not a continuity proof. The new points are isolated C++ evaluations, not independent native-host captures. Operational f32, physical mass/number/volume budgets, whole-host AD and GK2A–RTTOV cost sensitivity remain open. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.

Run `python -m unittest discover -s harness/evidence/native_activation_operands_cpp_ad_2026-11-10 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`.
