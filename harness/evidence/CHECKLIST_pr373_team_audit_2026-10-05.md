# PR #373 fresh Green/Red audit

Baseline: merged `5f6da8a`. Source review, focused counterexamples and actual
retained-input execution are distinguished below. The canonical private host
and its dirty working tree were not changed.

| Finding | Reproduction | Resolution | Status |
| --- | --- | --- | --- |
| P2: native T/Q changed by the inherited reference blend | On the retained pressure grid, controlled native perturbations were attenuated at 7/39 T and 30/39 Q levels. At the native top, both sensitivities were zero. FD agreement of that blended operator did not enforce native preservation. | Zero-width reference extension uses reference values only strictly above the top. Normalized clear/all-sky callers select it; tests inspect consumed profiles and native gradients. Historical positive widths retain their formula. | CLOSED in corrected research mode |
| P2: normalized OSSE shard could never execute | Valid normalized `ShardSpec` requires `cloud=True`; the invoked `run_osse_sensitivity` immediately rejected it. The old test mocked that receiver. | The normalized worker uses existing all-sky truth evaluation, a frozen cloud callback and the real window. New tests mock only RTTOV. Actual serial and spawned workers execute successfully. | CLOSED |
| P2: generic normalized callback could admit mismatched optical policy or be reused with another model mode | Wrong background density was accepted; model mode was absent from callback identity. Freezing could also hide a supplied live density. The guarded C5 full-domain route was unaffected by these generic-helper cases. | Validate original density before freezing; require dry-number optics, background density and zero blends for normalized all-sky callbacks. Tag/fingerprint the captured mode and reject tagged callback/window mismatch. Live and zero-dual-tangent density rejection is tested. | CLOSED for tagged normalized callbacks |
| Subtop pressure accepted within old tolerance | A 5e-11 hPa offset could pass native admission while changing the above-top selector. | Normalized entry points require exact native-center equality; offset rejection is tested. | CLOSED |
| Optional channel gate was underspecified | No gate keeps all QC-valid channels; nine zero-QC channels remain nine. The experiment's explicit binary gate retains seven. | Test and document the optional behavior; do not silently impose the experimental seven-channel set on every caller. | CLARIFIED |
| Receipt label scope | Input-unchanged checks cover the selected column; `full_domain_elapsed_s` includes the optimizer, window checks and shard run. | Report explicitly defines those scopes and the separate optimizer `wall_s`, while preserving the executed source/JSON pair. | CLARIFIED |
| Corrected native H and real shard execution | [Fresh actual evidence](REPORT_native_KMA_window_2026-10-05.md): 20 s and 3,600 s directional errors 2.36e-9 and 3.66e-8; six fixed-parameter primal states match the prior experiment bitwise. Actual serial/spawn cost and QV covector agree bitwise. | Same inputs, direction, h=1e-4, 1e-5 criterion, native levels, calibration and diagnostic settings. New artifacts preserve the historical ones. | CLOSED, bounded execution |
| Physical/operational questions | S2 calibration, product/SRF compatibility, B/R/bias, forecast skill and host cycling are not established by these checks. | Keep existing approval flags false. | OPEN |

The original `UNIFIED_KMA_*` source, receipt, arrays and analysis fields remain
unchanged. They validate their recorded blended observation operator, rather
than the corrected native-preserving operator. The new `NATIVE_KMA_*` evidence
records the latter separately. Neither scalar directional test certifies all
state directions, parameter identification or solver-branch invariance.

Focused local verification: Green's combined suite reports **155 passed / 6
skipped**. These are software test cases, not meteorological scenes; the skipped
legacy fixtures need private RTTOV/wrfout assets or a longer stored forecast.
