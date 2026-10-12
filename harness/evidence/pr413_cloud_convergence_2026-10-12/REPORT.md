# Bounded convergence observation for the PR412 natural cloudy column

Basis main `732f5482` (PR412). This is one separately declared larger-budget analysis of the **same** original cloudy-column problem, not a new selection, date or four-H contribution experiment. The original PR412 state/forcing/AMI pixel, prior, sigma/bias, physical parameters, geometry, native pressures and H auxiliaries are retained. Controls start at zero from the original native background; the old accepted state is not used as a warm start or new prior background.

## Declared budget and truthful identity

[PREDECLARED.json](PREDECLARED.json) declares `PR413_CLOUD_CONVERGENCE_8ITER_20261012`, a fresh private run root, max_iter8 and the existing PyTorch default nominal max_eval10. No max_eval kwarg is added; strong-Wolfe evaluations need not obey a nominal count as a hard universal limit. Physical time remains one held-forcing20s KDM step per trajectory, not eight physical steps.

[run_cloud_convergence.py](run_cloud_convergence.py) reuses unchanged V4 input construction and its isolated capture adapter. The legacy capture guard recognizes max_iter8 only through the dated PR398 protocol ID. A one-case wrapper therefore verifies the exact new PR413 identity/budget, translates **only a temporary validation copy** to that existing guard, and invokes every original fixed-input/physics check. The driver run manifest and one-shot marker retain the PR413 identity; the legacy-schema CAPTURE is linked by its path and SHA-256. PR398 is the protocol precedent, not this run. V4, capture, M/H, priors and solver source files are unchanged.

The prepared context exactly matches PR412 state/forcing/targets/DQFs/H auxiliaries, apart from a fresh fixture path. The copied fixture files match the old execution. Thirty-six input/source bindings and33 direct execution-asset hashes are checked before/after. System shared-cache and transitive loaded-library mapping remain outside that hash coverage. The original retained native producer has no whole-forecast content digest; its source/path/time/slice/intake qualifications remain.

Green identified that the initial draft receipt recorded environment declarations rather than measured runtime. The unexecuted [draft](PREFLIGHT_DRAFT_BEFORE_ENV_OBSERVATION.json) is preserved. The final runner validates exact interpreter, PYTHONOPTIMIZE0/assertions and four externally supplied one-thread environment variables **before importing Torch**, records Torch2.13.0/thread count1, and matches the observed environment again before execution. [PREFLIGHT.json](PREFLIGHT.json) is the corrected actual prepare-only receipt; the existing unused fixture was reused without M/H/optimizer execution.

[Nine focused guard tests](GUARD_TEST_RESULT.json) passed: valid new identity is not rewritten; old identity, altered budget/prior/sigma/warm start/window and launch-environment mismatches are rejected. The earlier seven-case subset is not added to this count. One NumPy binary-size RuntimeWarning occurred during imports and is recorded; the environment was not changed to hide it. These are validation tests, not new physical cases or derivative campaigns.

## Observed numerical outcome

The single `--execute` invocation returned exit0, `RETURNED_CLOUD_CONVERGENCE_DIAGNOSTIC`, and a `CROSSCHECKED` objective audit. [CAPTURE.json](CAPTURE.json), [DRIVER_RESULT.json](DRIVER_RESULT.json), and [EXECUTION_EXIT.json](EXECUTION_EXIT.json) bind the original result/checkpoint/log. Exit0 is coordinator-observed tool completion, not inferred from file presence or an independently instrumented PID trace. Sources/assets/fixture hashes remained unchanged, with no retry.

[COMPARISON.json](COMPARISON.json) and [CHANNEL_COMPARISON.csv](CHANNEL_COMPARISON.csv) read both preserved results/checkpoints without M/H or optimizer re-evaluation. Costs and priors below are dimensionless normalized costs; O–B/O–A are observed minus modeled. The gradient ratio is descriptive, not a new approval threshold.

| Quantity | Original max_iter3 | Declared max_iter8 |
|---|---:|---:|
| Initial Jo=J |8.461861229522402|8.461861229522402|
| Accepted Jo |6.321445504485183|6.204181698957177|
| Accepted Jb |0.10934786066219129|0.1262125304346976|
| Accepted J |6.430793365147374|6.3303942293918745|
| Full gradient L∞ |0.3041588432993508|0.01508371904916428|
| Full gradient L2 |0.4520949176872311|0.02164017225783262|
| Prior gradient L2=√(2Jb) |0.4676491434017415|0.5024192083005935|
| Full/prior gradient ratio |0.9667395398153262|0.043071944504330086|
| Actual iterations / function evaluations |2 / 4|5 / 10|
| Declared max_iter / effective max_eval |3 / 3|8 / 10|
| Window / final audit evaluations |4 / 1|10 / 1|
| Strict gradient tolerance / exposed termination |1e−10 / UNKNOWN|1e−10 / UNKNOWN|

Relative to the original bounded result, Jo decreases0.1172638055, prior increases0.0168646698, and total J decreases0.1003991358 (about1.56%). The full/prior gradient ratio falls from96.7% to4.31%, but **strict gradient convergence is still false**. The returned iteration/evaluation counts are observed; they do not expose a specific termination cause. Do not retrospectively replace `UNKNOWN` with an asserted budget-stop reason or infer that all eight iterations occurred.

The new run has **12 successful logical H callbacks**: one quality probe, ten window evaluations, one final audit. Every callback has all seven model rad_quality values0 and the fixed support is maintained. This is not an internal RTTOV direct/K or child-process count; those remain uninstrumented. Successful temporary RTTOV raw outputs are removed by the existing worker, while parsed BT/audit/checkpoint persist. Public CI is separate from this private execution.

## Endpoint stability has a limited meaning

Both analyses retain the original initial QCmax3.4602016967e−5 and recorded NC. In both accepted20s slots, **QC and recorded NC are zero**. Background initial/slot fields, forcing, all prior sigma/parameter controls, observations/DQFs, fixed host mass, pressure grids, reference atmosphere and frozen optical density compare exactly across captures. Thus the cloud-removal endpoint classification persists in this one budget comparison.

The accepted initial states nevertheless change: maximum physical-T difference is0.11870823K, maximum qv difference3.84771197e−4kg/kg, and control-vector L2 difference0.42392468. The full T/Q point is not demonstrated stable or converged. QC/NC persistence alone is not a theorem about further iterations, all branches, global uniqueness, observed cloud truth or forecast skill. Native number mass basis remains independently unvalidated; NC is the recorded model coordinate under the declared normalized-dry/dry_number runtime convention.

Six channels improve further relative to the old accepted point. IR096 worsens slightly: absolute O–A3.472231→3.486341K (background2.925323K). All model rad_quality values0 are quality-domain evidence, not seven-channel accuracy certification. The new total cost reduction does not imply every channel improved.

Under the same retained host dry-layer-mass measure, new background water is38.3765209050kg/m² and new accepted initial/slot water is38.2324750368kg/m². Local initial→slot total-water change is0 in this measure; initial analysis changes the water inventory. This remains a saved-state diagnostic, not closure of boundary/external fluxes or named-process budgets.

No new H(initial-state) diagnostic is run. PR412's R_M/I_M and four-H cost contrast remain evidence for **its own finite-iteration accepted state** and are not transferred numerically to this changed accepted point. Named-process rates, isolated QC/NC/latent pathways and second derivatives are not newly certified.

## Closure and remaining dependency

This authorized one-shot budget check is complete: the larger budget substantially reduces gradient and moderately lowers cost while preserving the cloud-removal endpoint classification. It does not complete strict convergence, certify an unchanged full analysis point, or justify silently relaxing tolerance. No further budget expansion or solver change is automatically started.

There were zero native integrations, downloads, selections, endpoint-H contrasts, FD campaigns or other-date analyses. July20/21 remain `PENDING_NATIVE_INPUT`; their L1B data do not supply corresponding model states/forcing. No repeated archive inquiry/search, date relabel, boundary extension or external-model substitution was performed. First-ready genuine other-date native–L1B input remains the independent repeatability task. The historical79/100 reference is not rescored; external satellite/L2/SST/MLS/VIIRS and deployment/global-Hessian work remain outside this phase.
