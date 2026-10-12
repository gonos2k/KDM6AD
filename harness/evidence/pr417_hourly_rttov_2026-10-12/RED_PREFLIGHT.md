# Red preflight: PR417 hourly value-only H comparison

## Disposition

**GO for the two declared value-only all-sky H calls.** The runner and prepared plan agree on saved indices 6 and 7 only, at 06:00 and 07:00 UTC on July 19. They use the already saved PR416 native column at `j=103, i=48`; no new forecast read or native run is part of this experiment. This review did not call H, M, RTTOV or the optimizer, parse private TIME_INPUTS arrays, or reopen the WRF forecast.

## Plan, source and prepared-input bindings

The plan SHA-256 is `0a1e22763b3dca11d5334f8c71c0969c9d810d46a358921e7a4c715dd7009e0c`; it records `PREPARED_INPUTS_NO_H_CALLS` and two logical H calls. The root runner SHA-256 `9518d8a3ae56bafbe283968a8354794bc5d3a01df28c27b6a487ce1d51d3d21b` matches `runner_sha256`, and both it and `prepare_hourly_h.py` are source-bound. The plan records 23 path/hash bindings, 33 external RTTOV assets, and 23 prepared-fixture file hashes. I independently checked every binding, external asset digest/size/resolved path, and fixture hash: all matched. The private PREPARED receipt binds the exact plan SHA and TIME_INPUTS digest; it reports the NPZ mode as `0600`, parent directory mode `0700`, and 33 execution assets checked.

Each time context is distinct and tied to the same fixed native point. Each has its own state, pressure coordinates, frozen dry density, `p_lay`, and `p_half`; both use the same five gas-source files and hashes, common GEOS navigation, channels 10–16, and the explicitly declared P8W Python REAL(4) transcription. Each uses a separate prepared fixture. The source plan preserves 39 native centers plus 27 upper reference layers (66 total), records no external model/reanalysis data, and explicitly identifies the Fortran P8W routine as unexecuted.

## H-call scope and result meaning

The root runner checks the prepared Python/thread environment and Torch version, verifies plan/source/asset/fixture hashes before and after calls, creates a fresh protected output root exclusively, and loops only over indices 6 and 7. It makes one `sharded_allsky` call per time with `grad=False`, fixed seven channels, the snapshot-specific H configuration, and quality gate requiring finite BT and zero model `rad_quality` for all seven channels. Any quality failure aborts with no channel removal or retry.

The zero target and all-one mask are interface placeholders; the returned dummy cost is discarded. No observed BT/DQF, residual, objective comparison, or temporal observation fit is used. The two output BT vectors can describe a joint snapshot-state/pressure/density/surface response under the same declared H rules; they do not isolate individual process effects or establish observed temporal fit. Internal RTTOV direct-call counts remain uninstrumented.

The H10 surface wind inputs are raw WRF `U10/V10`, passed through the existing V4 surface contract without rotation; their basis is explicitly left unverified. The same native `j103/i48` point and original AMI GEOS navigation are used at each time. There is no interpolation, selection change, native forecast execution, M call, or optimizer call.

## Interpretation limits

These calls use existing 06:00 and 07:00 MP137 saved profiles. They are not observations and are not compared with actual BT/DQF targets. The underlying run's executable and exact model input bytes remain unbound, and P8W is reconstructed by the pinned Python REAL(4) transcription rather than produced by executing the host Fortran routine. The raw number-concentration basis is not independently validated. Results cannot establish cloud truth, process attribution, forecast skill, a closed column budget, or a matched comparison with PR415's one-rank local KDM experiment.

This preflight is static plus hash/metadata checks only. No H/M/RTTOV/optimizer execution was made by Red.
