# Natural native warm-QC column: state response and AMI observation-space contrast

Basis main `381b90f5` (PR411). The completed central V4 integration and PR410 central endpoint interpretation remain closed. This case uses a different naturally cloudy native column from the same existing Jul19 archive, with its own geographically selected AMI L1B pixel. It expands the demonstrated state/process-response range; it is not another date, initialization, independent weather event, or forecast-skill test.

## Selection before residual inspection

[SELECTION_PLAN.json](SELECTION_PLAN.json) fixed one saved native time, Jul19 05:55:40, and a 41×41 box `(j=66..106,i=28..68)` around the original native center. The model-state screen requires ocean/no sea ice, 39 centers/40 interfaces, finite native/derived values, nonnegative mass/moment fields and declared companion-field checks, at least one layer with QC≥1e−8 kg/kg and physical T≥273.15K, and QI/QS/QG≤1e−8 throughout. It is not full moment/DSD admissibility certification, exact frozen absence, observed cloud-phase classification, or a process-response threshold. Ordering is spherical Haversine distance (R=6371000m) then j/i; no BT, innovation, cost, response or maximum-cloud ranking.

The one bounded read screened 1,681 columns; 41 were eligible. The first is `(j=103,i=48)`, latitude36.1953430176°, longitude122.0966796875°, 86.799km from the old center. It has one warm threshold-QC layer (QCmax3.4602016967e−5, T294.889847K); its frozen mass fields are exactly zero. [SELECTION_RECOVERED_RESULT.json](SELECTION_RECOVERED_RESULT.json) and the private slice bind this result.

**A preparation error is preserved:** the executed selector saved the slice, then exited1 because NumPy int64 indices were not JSON-serializable. Its source/plan are unchanged, and the empty partial output is preserved. [SELECTION_FAILURE.json](SELECTION_FAILURE.json) records the error; [recovery](recover_selection_result.py) serialized the result from the immutable slice without rescanning native state fields or expanding selection. Only the small Times coordinate was rechecked. [SELECTION_EXECUTION.json](SELECTION_EXECUTION.json) records coordinator-observed tool exits1/0, not an independent OS/PID trace. The failed selector is historical evidence, not a reusable production entrypoint.

The retained forecast's whole-file SHA was not available. Origin/time/path/completion receipts, stable size/mtime, and selected-slice/intake array hashes are bound; a whole-file content digest is not claimed. Existing narrow 3×3 clear-column diagnostics did not provide this target and were reused as context, not repeated.

## Native–AMI case and unchanged analysis

[BINDING_PLAN.json](BINDING_PLAN.json) and [producer](bind_selected_case.py) bind this native column to the nearest finite-geolocation pixel from the nine already restored original GK2A AMI L1B files. No download or other sensor/model substitution occurred. Pixel **row289/column49** is **425.935m** away; all nine DQFs, including the fixed analysis seven, are zero. Quality/BT were checked after geographic selection. No alternate candidate or pixel was tried. The PR403 wire schema is reused with an explicitly new PR412 producer, not relabeled historical execution.

| Input/setting | This case |
|---|---|
| Native run | `mp337_viirs_norm2_dry1_055540_055800_358min_hist0_20261010_052612_p99148` |
| Initialization / saved background / lead | Jul19 00:00 / 05:55:40 / 5h55m40s |
| Local slot / nominal L1B filename slot | 20s after background / Jul19 05:56 |
| Time qualification | Nominal filename time as model UTC; actual pixel UTC unverified |
| Coordinates/optical inputs | Selected native39 layers and40 interfaces, own pressure/surface/forcing;27 reference upper layers; frozen optical density; same coefficient/BT transform |
| Controls/priors | Initial theta and eligible bottom12 qv; theta0.8K, log-qv0.08; four physical parameters fixed |
| Observation settings | AMI10–16, all-sky, sigma1K/bias0, normalized Huber delta1 |
| Budget | Existing max_iter3/default nominal max_eval3, strong-Wolfe; no warm start/retry |

[CASE.json](CASE.json) and [INTAKE.json](INTAKE.json) passed unchanged V4. The selected 12 State fields and temperature/pressure match the preserved slice; all71 intake arrays are bound. Historical host/native build evidence remains attributed to that producer, not certified as a new current-main host executable.

[PREDECLARED.json](PREDECLARED.json) froze sources and33 direct execution assets before one actual V4 run. The unchanged spawn worker, KDM/AD, all-sky RTTOV, L-BFGS, final audit and checkpoint returned normally (`RETURNED_CASE_DIAGNOSTIC`, CLI exit0). Audit is `CROSSCHECKED`; State, controls, full gradient, BT, fixed mask and quality are stored privately. Sources/assets match afterward. [RESULT.json](RESULT.json), [CAPTURE.json](CAPTURE.json), and [EXECUTION_EXIT.json](EXECUTION_EXIT.json) record the result.

The objective/prior/observation costs below are dimensionless normalized costs.

| Numerical quantity | Value |
|---|---:|
| Initial Jo=J |8.461861229522402|
| Accepted Jo |6.321445504485183|
| Accepted Jb |0.10934786066219129|
| Accepted J |6.430793365147374|
| Optimizer iterations / function evaluations |2 / 4|
| Window / final audit evaluations |4 / 1|
| Final full-control gradient L∞ |0.3041588432993508|
| Declared gradient tolerance / termination |1e−10 / UNKNOWN|

**This is diagnostic return, not strict convergence.** Four evaluations exceeding nominal max_eval3 are observed strong-Wolfe behavior, not a changed budget or retry. Six logical H callbacks returned (probe1+window4+audit1), all seven-channel model rad_quality = 0. Internal RTTOV direct/K calls and PID inventory were not instrumented. Successful raw temporary RTTOV outputs are normally removed; parsed outputs/checkpoint remain.

Six channels' absolute O–A improve, while IR096 worsens from2.925323K to3.472231K. The summed cost decrease is therefore not improvement of every channel. The IR133 baseline and IR087/IR133 accepted residuals lie in Huber's quadratic region; do not reuse the old clear case's all-linear-loss interpretation.

## State change and the two missing H values

The saved background evolves with QC increase3.2176169892e−8, qv decrease3.2176169892e−8, and maximum T increase7.7348936e−5K. The accepted initial state retains the same QC as the native background, but after local M its QC/recorded NC become zero; qv increases3.4602016967e−5 and T decreases by up to0.0831960642K. These net endpoint changes are compatible with condensation/evaporation; **named-process rates and isolated process attribution were not recorded**. Initial T/Q controls induce these changes; QC/NC are not direct analysis controls.

| Saved state | QCmax | Fixed-host-measure QC path, kg/m² | Max model liquid qv/qs ratio, % |
|---|---:|---:|---:|
| Background initial |3.4602016967e−5|0.00418918804|100.00066170|
| Background slot |3.4634193137e−5|0.00419308354|99.99998713|
| Accepted initial |3.4602016967e−5|0.00418918804|96.34100333|
| Accepted slot |0|0|96.89483224|

NC is summarized as the recorded model coordinate under the declared normalized-dry/dry_number=True runtime contract. Native QN dry-vs-moist basis was not independently revalidated here; these values are not observed concentrations or a particle-number budget. QIB is a volume proxy, not water mass.

To quantify this **new** column's joint M observation-space response, [DIAGNOSTIC_PLAN.json](DIAGNOSTIC_PLAN.json) separately declared the only missing evaluations: H(background initial) and H(accepted initial). [diagnose_saved_case.py](diagnose_saved_case.py) made exactly two value-only `grad=False` H calls; no M, KDM backward or optimizer was replayed. Same captured effective H configuration, forcing, reference grid, density, surface, geometry, targets, fixed7 support, paired checkpoint/capture hashes and33 assets were checked before/after. Both calls returned model rad_quality = 0. The existing RTTOV wrapper can still generate K internally; its count is uninstrumented.

[PROCESS_RESPONSE.json](PROCESS_RESPONSE.json) computes R_M(x)=H(M(x))−H(x) and I_M=R_M(xa)−R_M(xb) from those two new values plus the original two slot values. [CASE_CHANNELS.csv](CASE_CHANNELS.csv) contains all seven BTs, O−B/O−A (observed minus modeled), and contrasts.

| Channel | R_M(background), K | R_M(accepted), K | I_M, K |
|---|---:|---:|---:|
| IR087 |−0.000411444|+0.832103632|+0.832515076|
| IR105 |−0.000389311|+0.689020363|+0.689409675|
| IR133 |−0.000059520|+0.139013078|+0.139072598|

The same saved-state pair's dimensionless normalized observation-cost gain is **G_M=2.1404157250**, versus **G_0=0.2054073862** for the evolution-bypassed diagnostic; difference **1.9350083389**. This is computed from four actual BT vectors and the same nonlinear loss, not from I_M alone. It is not a comparison of separately optimized systems, an isolated QC/NC pathway, or forecast improvement. The bypassed-M states are not full host states at the later valid time.

The fixed retained host dry-layer-mass measure gives an analysis-initial water change of **−0.1149768213kg/m²**. Each local initial→slot pair has zero retained total-water change in this measure. That is a checkpoint diagnostic, not closure of unmeasured boundary/external fluxes or every process budget. Model state phase, NC, and cloud removal are not independently observed truth from L1B.

## Closure and remaining work

This one same-date targeted case demonstrates nonzero joint M endpoint/BT response in addition to the earlier clear reference. It does not guarantee convergence, global optimum, physical-state truth, sensor/SRF approval, or an effect for every cloud state. Pixel timing/representativeness, reference atmosphere/fixed gases/surface and IR133 upstream SRF qualifications remain. No production physics, AD, solver, V4 consumer or old evidence was changed; no cloud seed or residual-guided selection was used.

There were **zero native integrations**, one new-column analysis (six logical H callbacks), and two separately declared missing H calls: **eight logical H calls total**, not eight internal RTTOV direct/K launches or child processes. No central integration/FD/R_M campaign was repeated. Private raw arrays/checkpoint remain restricted. July20/21 analyses are still `PENDING_NATIVE_INPUT`; no external model/reanalysis is substituted. The historical79/100 management reference is not rescored. Follow-up should use genuinely available other-date native–L1B pairs under the same declared rules, not repeat this case until a larger effect appears.
