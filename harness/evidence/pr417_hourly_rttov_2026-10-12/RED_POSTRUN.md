# Red postrun review: PR417 two-time value-only H result

## Result

The root runner returned `RETURNED_TWO_ACTUAL_VALUE_ONLY_H` with exactly two logical all-sky H calls: saved time indices 6 and 7, 06:00 and 07:00 UTC on July 19. Both calls requested `grad=False`; both produced finite `(1, 7)` BT vectors with all seven `rad_quality` entries zero. The recomputed `07 − 06` vector matches the recorded result:

| Channel | ΔBT (K) |
| --- | ---: |
| WV073 | +0.070823 |
| IR087 | +0.857550 |
| IR096 | +0.541396 |
| IR105 | +0.769501 |
| IR112 | +0.741998 |
| IR123 | +0.663093 |
| IR133 | +0.375447 |

The largest change is IR087 at `+0.857550 K`. `internal_RTTOV_direct_K_calls` is `null`, so these are two logical `sharded_allsky` calls, not an asserted count of internal RTTOV subprocess/K calls. The dummy zero target and all-one channel gate are placeholders only; returned cost is discarded. No observed BT/DQF, residual, fit cost, or temporal-observation reproduction is assessed.

## Input, context, and execution integrity

The result plan digest matches `PLAN.json` (`0a1e22763b3dca11d5334f8c71c0969c9d810d46a358921e7a4c715dd7009e0c`). The root runner SHA `9518d8a3ae56bafbe283968a8354794bc5d3a01df28c27b6a487ce1d51d3d21b` matches the plan. After the H calls, all 23 file bindings, 33 external asset hashes/sizes/resolved paths, and 23 prepared-fixture file hashes still match. The private and packet `RESULT.json` files are equal; the one-shot marker binds the same plan digest, and no failure marker is present. The private run output directory has mode `0700`.

I read the prepared TIME_INPUTS NPZ and compared its value arrays to the already saved PR416 private profile NPZ; I did not reopen the WRF forecast. At both times, the prepared 39-element `th` equals the corrected PR416 dry-potential-temperature array, the prepared `th × PII` equals the saved physical temperature exactly, pressure and `delz` equal the native derived arrays, `forcing.rho` equals the recorded `rho_m`, and `rho_d_frozen` equals the snapshot `rho_d`. QVAPOR, QCLOUD, and QIB state arrays also match their source profile values exactly. Each prepared profile has 66 `p_lay`, 67 `p_half`, and 66 temperature/humidity reference values; each context has its own pressure/reference arrays and frozen `rho_d`. Both contexts use the same pinned five gas-source files/hashes and common GEOS navigation. The zero `(1,7)` dummy target and one `(1,7)` gate were verified in the private bundle.

The H context uses snapshot-specific state, pressure, density, and surface values under common seven-channel all-sky rules. Raw WRF U10/V10 are passed without rotation under the unchanged V4 surface contract; their basis is explicitly unverified. No native forecast execution, H call by Red, M call, or optimizer execution occurred.

## Interpretation limits

The positive BT differences are a joint response to all per-time context differences—temperature, water species, pressure/reference profiles, density, and surface inputs—under one fixed H configuration. They cannot be assigned to QCLOUD or any individual KDM process and are not an observed temporal fit. The profiles are one hour apart; they are not the 20-second local KDM window used in PR415 and do not form a matched experiment.

The corrected PR416 liquid-water diagnostic is `Σ QCLOUD × rho_d × delz`, using geometric dry-air density and layer thickness, not the eta-layer host dry-air mass weights used in the earlier local-analysis path. QCLOUD is present only at low level `k=3` at 06:00 and absent at 07:00; that level warms. The profile-wide cooling minima occur aloft, not in the QCLOUD-bearing layer. The distinction and exact saved-CSV values are recorded in [MEASURE_AND_LAYER_CLARIFICATION.md](MEASURE_AND_LAYER_CLARIFICATION.md). These snapshot column masses do not close a flux budget or establish physical conservation.

The source run's executable and exact model input bytes remain unbound. P8W is the hash-validated Python REAL(4) transcription, not an execution of the host Fortran routine; the raw number-concentration basis is not independently validated. This result establishes a bounded H response for the two retained hourly snapshots only, not cloud truth, process attribution, forecast skill, or a new-date result.
