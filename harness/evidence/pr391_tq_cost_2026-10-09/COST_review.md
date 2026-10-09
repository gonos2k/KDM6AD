# Green review: native T/Q cost path

This packet runs actual RTTOV on the six saved KDM endpoints and keeps the original requested cost settings: channels 10–16, sigma 1 K, bias 0 K, and Huber delta 1. The checksum-matched executed harness is [run_native_column_cost_at_execution.py](run_native_column_cost_at_execution.py); [run_native_column_cost.py](run_native_column_cost.py) includes the later scratch-isolation fix. The profile keeps the native 39 centers and 40 interfaces, original 27-layer upper reference, gases, geometry, and surface. Solar input is off and the simple-cloud fallback is zero. Channels 8 and 9 remain excluded under the predeclared gas warning.

| Case | Huber sum under its actual RTTOV quality mask | Support | RTTOV quality 32768 |
| --- | ---: | ---: | --- |
| Baseline | 26.588575903 | 7/7 | none |
| T−0.5 K | 26.492680186 | 7/7 | none |
| T−1 K | 13.266850803 | 4/7 | channels 10, 11, 16 |
| qv×1.02 | 26.573211293 | 7/7 | none |
| qv×1.06 | 19.141737707 | 6/7 | channel 10 |
| Supplemental T−0.8 K | 22.616033127 | 7/7 | none |

The two strong cloudy cases carry `32768 = 1<<15`, RTTOV’s `qflag_delta_edd_ext_limits` (“Delta-Eddington extinction limit exceeded”). Their masked sums use four and six channels, so they are not valid common-seven comparisons. All seven BTs, residuals, unmasked contributions, and actual masks are in [RESULT.json](RESULT.json). A channels 12–15 intersection is also reported there as a secondary diagnostic only.

At the predeclared weak-cloud T−0.8 K point, one native level has `qc=2.005882014e-5 kg/kg dry`, and all seven channels remain usable. The full H∘M cost derivative reruns the 20 s f64 normalized-dry KDM step, native profile/cloud map with the baseline optical dry-density reference fixed, and fresh RTTOV KMA BT/K before applying the Huber loss. The WRF `k=3` physical-temperature direction is +1 K with scalar FD step `h=1e-4` (actual endpoint perturbations ±1e-4 K): AD is 45.00625885 and central FD is 45.00626611 (relative error 1.61e-7). The qv direction is +0.01 kg/kg dry with `h=1e-5`, so the actual endpoint perturbations are ±1e-7 kg/kg: AD is −393.2833111 and FD is −393.2833294 (relative error 4.67e-8). The qv direction’s 0.01 kg/kg scale is a control-space direction; it is separate from the observation sigma of 1 K. Both plus/minus pairs preserve all seven RTTOV quality flags and the same cloudy-layer branch. All twelve recomputed KDM endpoint fields match the cached weak-point output bitwise.

The separate baseline H-only check holds baseline cloud optics fixed; it is not a derivative through M. The full H∘M check is shown only at T−0.8 K. Neither check establishes higher derivatives, NC identifiability, or a descent step.

The [execution-path identity record](ExecutionPathIdentity.json) resolves a later file-path mismatch. The runner hash at cost execution was `33f64841…`; an exact checksum-matched copy is preserved as [run_native_column_cost_at_execution.py](run_native_column_cost_at_execution.py). The current [future-path runner](run_native_column_cost.py) hashes to `cd7dee06…` and was not used to produce these values. At the original baseline call, `q.txt` had the recorded hash `8d5b00aa…`, which matches the immutable paired case profile. The old runner then reused `run_baseline` for local H finite differences; its present `q.txt` hash is `3b2cbbbb…` from the final qv-plus call. Read the saved result’s baseline profile digest as the input identity; do not interpret the current scratch `q.txt` as the baseline file.

M’s after-run identity is pinned in [M_source_identity.json](M_source_identity.json): tracked KDM source hashes match Red’s current receipt at `a85b39eb`, and the sidecar hash matches this cost result. This is after-run source inspection, not a pre-launch capture. The existing RTTOV executable and coefficient hashes are recorded; no new source-to-binary build attestation was made.

These values use outputs from the historically invalid native host run. They are diagnostics on that saved artifact, not a valid forecast, accepted observation cost, analysis, operational result, or approval of the observation match. Time/QA correspondence and physical SRF compatibility remain unresolved.

This bounded review agrees with section 5 of the [main report](../REPORT_pr391_review_resolution_2026-10-09.md) and checklist item A2 in the [resolution checklist](../CHECKLIST_pr391_review_resolution_2026-10-09.md).
