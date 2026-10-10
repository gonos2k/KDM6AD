# PR402 actual four-trial finite response

Baseline: preserved central native direct-H at nominal2025-07-19 05:56, j86/i48. Four isolated trials returned, each with all seven quality flags zero. Actual fresh direct and K-path native BT agree exactly in each case. No fifth baseline, KDM M, native integration or optimizer was run.

## Actual objective changes

| Trial | Jo | Actual deltaJo | Linear deltaJo (serialized input) | Difference |
|---|---:|---:|---:|---:|
| skin_minus_0p5K | 25.4474979506 | -1.1501868315 | -1.1515624922 | +0.0013756607 |
| skin_plus_0p5K | 27.7506172978 | +1.1529325156 | +1.1515624922 | +0.0013700234 |
| o3_source_minus_1pct | 26.7399358990 | +0.1422511169 | +0.1418069928 | +0.0004441241 |
| o3_source_plus_1pct | 26.4563180914 | -0.1413666907 | -0.1418069928 | +0.0004403021 |

Jo and deltaJo are dimensionless normalized Huber costs; BT and E are K. These are forward evaluations at fixed inputs, not minimized objectives or changes in an accepted T/Q analysis.

## Central difference and one-sided linearization error

Skin uses d=+1K and h=.5. O3 uses d=+1% of the common69-node source and h=1. Thus both central differences divide by2h in their respective declared direction coordinates. E± is B±−B0∓hK0d; serialized-input E instead subtracts the contraction of the actual ASCII input delta. The effective serialized derivative is also saved.

| Channel | Skin DFD−K0d, K/unit | Skin max abs E, K | O3 DFD−K0d, K/unit | O3 max abs E, K |
|---|---:|---:|---:|---:|
| WV073 | +1.27743431e-11 | 5.35808137e-09 | -9.17684234e-11 | 1.14298989e-08 |
| IR087 | -1.63821675e-06 | 0.000359254295 | +1.07717078e-08 | 5.28730072e-06 |
| IR096 | -1.05245548e-06 | 0.000247393105 | -1.91031669e-06 | 0.000425316839 |
| IR105 | -1.33327657e-06 | 0.000267687203 | -2.7375384e-08 | 1.01365109e-07 |
| IR112 | -1.00991974e-06 | 0.00024770103 | +1.01885239e-08 | 5.75520237e-08 |
| IR123 | -5.00297676e-07 | 0.0001858096 | +9.12105468e-09 | 2.07539115e-06 |
| IR133 | -1.03139695e-07 | 6.78208429e-05 | -3.51666945e-09 | 1.14293176e-05 |

Maximum one-sided serialized-input errors are **0.000359254 K** for skin and **0.000425317 K** for O3. Maximum central derivative discrepancies are1.63822e−6 K/unit for skin and1.91032e−6 K/unit for O3. The dominant O3 IR096 derivative discrepancy is about1.53e−5 relative; the weak IR112 O3 response has about0.65% relative discrepancy but only1.02e−8 K/unit absolute discrepancy. This illustrates why relative-only errors are misleading for nearly zero responses.

The frozen relative-error rule uses max(abs(DFD),abs(K0d)) and emits null below1e−6 K/unit. All absolute discrepancies remain recorded. These numerical diagnostics describe two selected directions and step sizes at one point; no universal tolerance was introduced or derivative acceptance criterion relaxed.

## Provenance, counts and limits

- Four wrapper launches returned four fresh direct files and four fresh K products. Internal RTTOV direct/adjoint invocation counts were not instrumented and remain unknown.
- Runtime assets and all22 inputs per trial were checked before/after execution. Only the intended skin or O3 file differs from the preserved baseline; original center files remain unchanged. The common P mapping includes the held and partially linked gas-source endpoint.
- Executable/coefficient hashes match historical records. Historical baseline hydrotable and dylib SHA were not recorded; the current hydrotable and readable library files are frozen and unchanged across these four trials. libSystem is a shared-cache install name without a regular-file SHA. E± is conditional on the reused baseline, while the central pair difference cancels B0.
- The full trial inputs/outputs remain in private isolated cases. Raw and converted K, actual input deltas, BT/quality, sourceO3 and P are hash-bound in the private payload referenced by FINITE_RESULT.json.
- This demonstrates local finite-step agreement with the saved K; it does not identify actual SST/O3 error, establish SRF identity, certify higher derivatives or extend to other events. The O3/upper-temperature ambiguity from PR401 is not resolved by this experiment.

[Frozen plan](K_RESPONSE_PLAN.json) · [Actual result](FINITE_RESULT.json) · [Channel table](FINITE_CHANNELS.csv)
