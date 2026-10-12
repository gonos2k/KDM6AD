# Green preflight review: PR415 bounded budget run

**Disposition: GO for the single declared analysis.** At review time the packet is prepared and `RUN_STARTED_ONCE.json`, `RESULT.json`, and `FAILED.json` are absent from the output root; the output root contains only the prepared RTTOV fixture. No model, H, M, or optimizer call was made during this review.

The declaration is `PR415_JUL19_THREE_SLOT_8ITER_20261012_01`, with `max_iter=8`, original Torch-default nominal `max_eval=10` under strong-Wolfe, one initial state/prior, slots 1/31/61, `dt=20 s`, and 61 local steps. It explicitly starts from the original PR414 background at zero control and changes only the finite iteration budget, destination/run identity, and the new adapter/declaration. It does not pass a new `max_eval`, alter tolerance, retry, add a date, or invoke native integration. The saved forcing remains original `f0` held across all 61 transitions; observations remain the same three actual Jul19 L1B scenes and seven-channel targets under the filename-OBT-as-model-UTC research hypothesis.

I independently checked the declaration and source bindings:

- The old PR414 plan hash is exactly `fc704e2af5c68674e91afeaffd3e61102ebdcc167660f8b515fe123d6a1111cd`; the new plan hash is `83eb8e3873ac22f9947ed5226e8f9930386ce7e3a4f5589cab82c468413d2ad6` and matches `PREFLIGHT.json`.
- The immutable PR414 `run_window.py` hash matches the declared runner SHA. The small PR415 adapter hash matches its declared SHA. It loads that runner unchanged, changing only its packet destination and `MAX_ITER=8`; the original runner's assertions and one-shot result guards remain active.
- All 114 original PR414 input/source bindings are preserved. The five added bindings cover the adapter, original plan/result/preflight, and prior private checkpoint. All 119 declared binding hashes currently match.
- All 33 execution-asset path/resolved-path/size/hash checks match. All 24 prepared fixture files match their preflight hashes.
- The prepared-context fingerprint exactly matches PR414 after removing only the fresh fixture-directory path: original initial state, forcing, H configuration, and three observation signatures are unchanged. The state/forcing and H pressure grids and frozen optical density remain the prior PR414 values.

The unchanged window runner constructs one prior and the same 51 controls: 39 potential-temperature levels (`theta`, sigma 0.8 K) and the eligible bottom 12 water-vapor levels (log sigma 0.08). Other state controls and physical parameters remain inactive. The preflight retains channels 10–16, the same AMI coefficients/reference fields, pressure grids, geometry, surface, and fixed optical density. Thread environment and pinned Python/Torch declarations match the original prepared run.

The hourly-candidate audit is retained separately in this packet. It confirms a completed MP137 00–12 host integration and its output metadata, while leaving executable-byte and input-byte hashes unresolved. The final boundary interval is `[09:00,12:00)` and end-exclusive; this run does not advance the host candidate beyond its endpoint. The `wrfchainp_d01` `START_DATE` versus `Times` metadata discrepancy is recorded unresolved. These limits do not change the PR415 numerical experiment, which reuses the pinned PR414 intake, forcing, and observations rather than selecting or rereading the hourly forecast.

This preflight authorizes review of the one declared eight-iteration run; it does not predict strict convergence. The run must report actual evaluations, full gradient, termination label, three-slot audit, and checkpoint integrity as returned.
