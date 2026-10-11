# One actual V4 top-level integration: retained Jul19 case

Basis main `f46658a2` (PR410). The requested actual V4 success path is now exercised once: fresh observation/native binding → unchanged V4 `execute()` → fixture copy → configured spawn pool → actual all-sky RTTOV/KDM/AD/L-BFGS → final audit → checkpoint. The CLI exited0 and the original driver returned `RETURNED_CASE_DIAGNOSTIC`. This is engineering completion on the existing Jul19 case, not another weather date, stricter convergence or a new microphysics-contribution result.

## Input preparation was necessary

The preserved PR407 Jul19 replay was **native-core only**. Its observation paths/hashes were null, so unchanged V4 correctly refused it as an analysis input. The native archive/RTTOV assets existed, but the known original AMI raw directory was empty; named preservation records contained no raw backup. No native archive search or model rerun was performed.

[RESTORE_PLAN.json](RESTORE_PLAN.json) and [RESTORE_RESULT.json](RESTORE_RESULT.json) record restoration of exactly nine GK2A AMI Jul19 files, all matching their original SHA-256. This restores old input bytes, not new dates or independent observations. No other sensor/L2/model/reanalysis was acquired. The [new one-case producer](bind_existing_case.py) uses the existing LA reader and current source-mask/geometry helpers, selects by fixed native geolocation, and verifies the original row320/column48 and seven BT/DQF values exactly. Raw words, source missing, padding and embedded DQF stay separate in the private payload.

[L1B_WIRE_RESULT.json](L1B_WIRE_RESULT.json) explicitly identifies a **new PR411 producer**. It uses the PR403 v1 wire schema required by unchanged V4; it is not a historical PR403 execution. Payload/reader metadata/result hashes are bound. Pixel UTC remains unknown and filename time is the stated nominal-model-time assumption; no historical VIIRS phase/height/geometry is admitted as new input or truth.

[CASE.json](CASE.json) and [INTAKE.json](INTAKE.json) are fresh records. V4 intake/reload passed the original observation, native source, saved-time, pressure, unit and quality gates without weakening them. All71 arrays match the prior native-core replay bitwise. The selected saved background remains Jul19 05:55:40, and its separate20s local slot is nominal05:56. The original native archive/358min forecast and old receipts were preserved.

## One frozen execution and its actual return

[PREDECLARED.json](PREDECLARED.json) pins the entrypoint/companion sources, input hashes, exact Python environment and33 RTTOV/template/direct-library assets. The paired executable, AMI coefficient, hydrotable and directly linked non-system libraries were hashed before/after. System shared-cache and transitive/runtime loaded-map coverage are not claimed. [EXECUTION_STARTED_ONCE.json](EXECUTION_STARTED_ONCE.json) and the driver's [RUN_STARTED_ONCE.json](RUN_STARTED_ONCE.json) identify the one invocation; output paths were fresh and no retry/overwrite occurred.

The unchanged settings are all-sky channels10–16, one saved forcing held20s, initial T/Q only, four physical parameters fixed, sigma1K/bias0, theta prior0.8K, vapor log prior0.08 on eligible bottom12 levels, max_iter3/default nominal max_eval3, no warm start and configured spawn pool size1. Strong-Wolfe can exceed its nominal evaluation setting; the counts below are observed. The historical `huber_delta_K` metadata key is retained by V4, but delta1 acts on standardized residuals and is dimensionless.

| Recorded result | Value |
|---|---:|
| Initial observation/total cost |26.588575903055926|
| Final observation cost |26.135616402715186|
| Final state prior |0.2284737909127953|
| Final total cost |26.36409019362798|
| L-BFGS iterations / function evaluations |2 / 3|
| Window evaluations / final audit |3 / 1|
| Returned logical H callbacks, including probe |5|
| Final full-control gradient L∞ |7.817358308397082e−5|
| Gradient tolerance |1e−10|
| Exposed termination |UNKNOWN|

All five H callbacks returned actual seven-channel BT and rad_quality0; the zero-mask probe is separate from the initial cost. Accepted-state objective audit is `CROSSCHECKED`, with fixed7/7 support. These values coincide with the old bounded Jul19 result but do not show new performance improvement. Normal diagnostic return is **not strict convergence**.

The actual entrypoint uses `multiprocessing.get_context("spawn").Pool(1)`, not the PR408 synthetic H/InlinePool fixture. Distinct channel BT/K-derived pullbacks and the existing real worker/runner path were exercised. Runtime PID inventory and internal RTTOV direct/K calls were not instrumented; report the five logical callbacks, not an invented internal-call count. Successful per-H `TemporaryDirectory` workspaces are removed by the unchanged all-sky worker. The parsed output, audit and checkpoints remain; raw temporary direct/K files are not claimed as preserved evidence.

## Saved state and evidence limits

[CAPTURE.json](CAPTURE.json) is byte-identical to the original public-format capture in the private run directory. [RESULT.json](RESULT.json) binds the original private `DRIVER_RESULT.json`, capture and checkpoint hashes. The mode0600 checkpoint stores all four State groups, accepted controls, total gradient, BT, frozen mask and quality. Their hashes/values were checked against the receipt/final callback; no receipt-derived repair is needed for this new checkpoint. All predeclared assets and source guards matched after return.

No V4, physical M/H, AD, solver, ABI, native option or budget was changed. The data-preparation scripts are specific to this required binding, not a new consumer or general validation framework. No native integration was launched, no closed R_M/I_M or derivative campaign was repeated, no raw private arrays were published, and no score is reassessed. The retained Jul19 native build remains historically attributed rather than current-main certified. Nominal-time/footprint/SRF/model-assumption and physical-budget limits remain, as do unknown convergence and physical science acceptance.

The actual V4 top-level success-path gap is closed for this bounded case. July20/21 native-linked analyses remain pending. Future cases must use genuinely available native data and admitted AMI observations selected before residual inspection; this same-date integration is not substituted for them.
