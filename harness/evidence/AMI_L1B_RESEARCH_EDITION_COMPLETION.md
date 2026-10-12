# AMI L1B research edition: problem, evidence and completion

This is the current interpretation document. It separates the observation scope, upper scientific goal, current numerical subproblem and engineering execution. It changes no physical map, solver, consumer or executed record.

## Four distinct levels

| Level | Definition | Boundary |
|---|---|---|
| User scope | GK2A AMI L1B is the only satellite-observation input; internal research takes priority over deployment | Other satellites/L2 are deferred. This does not itself prescribe seven channels,39 layers,20 seconds or T/Q-only control |
| Upper scientific goal | Validate differentiable KDM hydrometeor processes, interactions and their connection to GK2A–RTTOV response | Needs claim-matched process/transfer/state/observation evidence; BT fit alone is insufficient |
| Current subproblem | Fixed-forcing microphysics-constrained single-column initial T/Q variational analysis | Prior-conditional adjustment, not direct cloud/NC/parameter retrieval or full-host4D-Var |
| Engineering execution | Bind actual run/state/time/column/observation/configuration to analysis, audit and storage | Input gates and synthetic success establish wiring, not new-date scientific results |

The upper goal remains the [README differentiation contract](../../README.md#scope--differentiation-contract) and [hydrometeor sensitivity checklist](CHECKLIST_hydrometeor_sensitivity_2026-09-06.md). Completion of the narrow T/Q workflow does not complete all process research. Closed selected subcases remain closed.

## Current problem definition

**AMI L1B 기반, 고정 forcing 미세물리 제약의 단일 연직열 초기 온습도 변분분석.**

Given one normal native ocean column, adjust initial dry potential temperature and eligible bottom-level vapor mixing ratio under the declared prior. Apply the prescribed-forcing f64 KDM20s map and all-sky RTTOV, express modeled radiance in the paired KMA BT coordinate, and reduce control-prior plus Huber observation cost. This experiment does not require cloud creation, unique true-state recovery or forecast improvement.

| Quantity | Current role |
|---|---|
| Native background x_b | Initial12-field State on39 native levels; a background, not truth |
| f_b=(rho_m,pii,p,delz) | Fixed supplied moist-air density, Exner, pressure and thickness; not rebuilt or differentiated as forcing during trials |
| Observation y | Preselected AMI L1B channels10–16 BT point, with frozen valid support |
| Microphysics parameters alpha_b | Four parameter controls inactive; values fixed |
| H auxiliaries a_H | Native centers/interfaces, upper reference T/Q, O3/CO2, surface/near-surface inputs, frozen optical dry density, geometry, coefficients/options and BT conversion; declared fixed assets/assumptions |
| Active initial controls | Additive potential temperature on39 levels; pure-log vapor on eligible positive-background cells in bottom12 levels; actual counts computed per case |
| Other initial State fields | Fixed at background in C, including QC/NC; their evolved values can change through M |
| Outputs | Accepted initial/slot States, BT, control/total gradient, costs, quality/support, numerical termination and defined state-change diagnostics |

For active coordinates, mathematically

\[
\theta_{0,k}=\theta_{b,k}+0.8u_{\theta,k},\qquad
r_{v,0,k}=r_{v,b,k}\exp(0.08u_{q,k}).
\]

For positive vapor with epsilon0, the executed f64 CVT uses `r_b+r_b*expm1(0.08*u_q)`, retaining its floating-point behavior. Ineligible/upper vapor controls are inactive; no separate qv clamp-headroom bound is introduced by this prior. There are at most39+12=51 active coordinates. Packed arrays retain inactive coordinates, not extra retrieved quantities. Restricting initial controls to T/Q does not remove intermediate hydrometeor-state sensitivity paths in the full-window state adjoint. Potential-temperature sigma0.8K is not physical-temperature sigma0.8K: with fixed Exner, `delta T=pii*delta theta`. Sources: [control assembly](../../oracle/kdm6/da_single_column.py), [CVT](../../oracle/kdm6/da_cvt.py), [current V4 driver](pr407_native_saved_time_bound_2026-10-11/run_case_analysis.py).

### Map, objective and valid domain

\[
x_0=C(v;x_b),\quad x_1=M^{64}_{20s}(x_0;f_b,\alpha_b),\quad
\widehat y=\mathcal H_{a_H}(x_1),\quad
\mathcal H_{a_H}=\Phi_{KMA}\circ\mathcal R_{RTTOV}\circ\mathcal P.
\]

P converts native states to optical/profile inputs and attaches the upper reference. The differentiated map is branch-local f64 DA, not the literal adjoint of operational f32 machine arithmetic. All H auxiliary bindings belong to the problem; writing H(x) does not imply those inputs are independently validated or may change silently.

\[
J(v)=\tfrac12\|v\|^2+\sum_{c\in S}\rho_1\!\left(\frac{\widehat y_c-(y_c+b_c)}{s_c}\right),\quad
S=\{10,\ldots,16\},\ s_c=1\mathrm K,\ b_c=0,
\]
\[
\rho_1(r)=\begin{cases}\tfrac12r^2,&|r|\le1,\\|r|-\tfrac12,&|r|>1.\end{cases}
\]

Inactive controls remain zero. The1K scale is exploratory residual normalization, not a calibrated observed standard deviation or pure R. This is not Gaussian least squares over every residual. Sources: [observation loss](../../oracle/kdm6/obs/obs_loss.py), [dual minimizer](../../oracle/kdm6/da_dual.py), [single-column helper](../../oracle/kdm6/da_single_column.py).

Within fixed-support domain D_S, trials that lose quality/support stop; channels are not dropped to lower cost. The implementation is a bounded local L-BFGS run, not a global constrained optimizer over D_S. Report its accepted point and actual gradient/termination, not a global optimum or automatic convergence.

With N active controls, seven residuals provide at most seven independent first-order directions. If N=51, at least44 directions are locally unresolved by observations alone. Prior regularization can give a unique linearized solution without independent satellite determination of every control. Neither that linearized property nor a returned point proves nonlinear global uniqueness across branches. No new SVD/Hessian/identifiability gate is required here.

The strong constraint is the chosen local microphysics map. Supplied pressure/rho_m/Exner/metrics are not rebalanced after each T/Q change, so the returned state is not guaranteed to be a balanced host initial field. This does not freeze every derived density: the normalized-dry M path derives dry number density from `rho_m/(1+trial_qv)` and retains that state sensitivity ([runtime](../../oracle/kdm6/runtime.py)); the separate optical rho_d in H is frozen from the background. Rebuilding the supplied forcing from trial state changes the derivative from M_x to M_x+M_f f_x and is a different problem. Full host coupling, writeback/cycling and forecast skill remain separate objectives.

## Completion and claims: three evidence stages

| Stage | Completion evidence | Does not establish |
|---|---|---|
| Calculation | Valid case bindings, same objective/support, baseline→analysis→accepted-point audit, state/control/gradient and failure records | Atmospheric truth, convergence or a mechanism |
| Numerical validation | Existing independent derivatives/transpose checks in declared directions/branches; actual termination and gradient criterion distinguished | All branches, higher derivatives, global optimum or empirical input accuracy |
| Research interpretation | Explain T/Q→modeled state/hydrometeor→BT changes using selected process records or a claim-matched comparison; repeat declared rules across preselected scenes | Cloud/NC/phase truth or forecast improvement from cost decrease alone |

Another-date execution supports calculation/repeatability. The upper process goal also needs evidence matching the scientific claim. External SST/MLS/VIIRS/L2 absence is not a current penalty, and no new full-host adjoint, solver or B/R architecture is made mandatory.

### Existing evidence and its limits

| Evidence | Supported interpretation | Qualification |
|---|---|---|
| [Selected process campaign](CHECKLIST_hydrometeor_sensitivity_2026-09-06.md) | Named rates→applied transfers→later states, selected warm/cold chains, AD/FD and branch/instrumentation records | Selected fixtures/regimes/measures, not all processes or attribution for this native T/Q case |
| [PR391 state response](pr391_tq_response_2026-10-09/) and [composed cost](pr391_tq_cost_2026-10-09/) | Selected satadj/state responses and a declared weak-cloud H∘M T-direction check | Limited point/branch/support; wet NC/NCCN residuals are not uniformly small and cross-scenario seven-support is not universally valid |
| [C5 NC→BT record](C5_nc_bt_17digits_result_2026-10-03.json) | Fixed-profile number-direction optical/BT K/FD | Direct optical H probe, not H∘M or an NC retrieval; number-basis/accepted-cost conditions remain limited |
| [Native number-direction report](REPORT_supported_native_nccn_2026-10-03.md) | Historical isolated native candidate/overlay, one frozen column and two directions | Specific private build/variant/input, not an adopted current build, full process attribution or number truth; unadmitted zero-return probes do not count |
| [Actual Jul19 analysis](pr397_actual_native_results_2026-10-10/REPORT.md) and [bounded follow-up](pr398_followup_2026-10-10/) | One retained native date's conditional analysis and stored diagnostics | No-cloud/cost/gradient outcomes do not complete upper science; keep dated source/build/auxiliary/outer-harness caveats |
| [Retained Jul19 claim evidence](pr410_retained_case_claims_2026-10-11/REPORT.md) | Actual H(M(x_b))/H(M(x_a)) fit change and endpoint-specific H-input equivalence | Direct H(x_b)/H(x_a) absent; R_M/I_M and cost contrast are conditional input-equivalence inferences, not fresh H results, M_x=I or named-process attribution |
| [Vertical/neighbor H](pr399_vertical_neighbor_2026-10-10/) and [fixed-input K](pr401_fixed_input_k_response_2026-10-10/) | Context and declared input sensitivities | Endpoints alone do not identify process causes; sensitivity is not measured input error |
| [PR403 L1B scenes](pr403_l1b_heldout_2026-10-11/) and [V4 admission](pr407_native_saved_time_bound_2026-10-11/) | Other-date observation intake and engineering linkage | Matching real native analyses still pending;70-array replay is one same-date intake, not70 cases |
| [PR408 synthetic success](pr408_synthetic_capture_success_2026-10-11/COORDINATOR_REPORT.md) | Real KDM/AD/minimizer/audit/checkpoint with synthetic H | No real RTTOV or new-date weather result; strict gradient criterion unmet; full spawned-worker path not exercised |
| [PR411 actual V4 integration](pr411_v4_actual_integration_2026-10-12/REPORT.md) | Existing Jul19 real L1B/native binding through fixture copy, configured spawn worker, actual RTTOV, analysis/audit and saved state/gradient | One same-date engineering run; no new native integration/date, strict convergence, process contribution or physical-matchup acceptance |
| [PR412 natural warm-QC column](pr412_native_process_case_2026-10-12/REPORT.md) | Pre-residual native-state selection, actual corresponding AMI pixel, one fixed T/Q analysis/audit and saved endpoint changes; two missing initial-H values quantify joint M response and same-state-pair cost contrast | Same Jul19 initialization/date; nonconverged diagnostic return, not isolated process rates, native number-basis proof, no-M reoptimization, observed phase or forecast skill; other-date analyses pending |
| [PR413 cloudy-column bounded convergence](pr413_cloud_convergence_2026-10-12/REPORT.md) | Same original problem and zero-start controls with an eight-iteration budget; audit/checkpoint, lower cost/full gradient and cloud-removal endpoint persistence compared from saved data | Actual5 iterations/10 evaluations; strict convergence still false/UNKNOWN, full T/Q point changes; no new date, M-attribution contrast, tolerance change or science/score acceptance |

Historical non-AMI selection/labels remain history, not evidence for new AMI-only scientific claims under the [observation contract](CURRENT_OBSERVATION_DATA_CONTRACT.md). Closed selected checks are mapped, not reopened. State Jacobians alone do not prove named-process attribution. An unchanged M endpoint does not imply M_x=I.

### What the closed synthetic success establishes

The reused [synthetic all-sky fixture](../../oracle/tests/test_da_single_column.py) returns the same scalar in every channel: `bt=s(x).expand(1,7)`, where `s=280+mean(theta*pii)-ref_T+0.05*(mean(qv)-ref_qv)+20*mean(qc)`. The coefficients are test choices, not AMI/RTTOV physical sensitivities. Hence, within a differentiable branch,

\[
D_v(\widetilde H\circ M\circ C)=\boldsymbol1_7a(v)^T,
\qquad \operatorname{rank}D_v(\widetilde H\circ M\circ C)\le1.
\]

This upper bound follows from the output structure, including when M is real KDM; it is not a measured rank of actual AMI/RTTOV. In real arithmetic, under the declared zero bias and shared Huber delta, with equal channel scales and full equal masks, permuting targets preserves the summed synthetic loss and state pullback; this is not a raw-bit invariance guarantee for floating-point reductions. Metadata/order checks are separate; this physical-response fixture cannot distinguish channel-specific spectral misassociation. It does not read NC directly (`partial H_tilde/partial NC=0`), which does not exclude indirect NC effects through M. Seven supported output entries therefore do not constitute seven independent spectral responses.

In the [retained PR408 result](pr408_synthetic_capture_success_2026-10-11/SYNTHETIC_CAPTURE_RESULT.json), initial identical BT281.179394596 with targets282–288 puts the first residual in the Huber quadratic region and the other six in its linear region. The real-case all-linear description does not transfer to this fixture. Its cost reduction is a synthetic-objective result, not meteorological improvement. The success/audit/storage test remains closed; no richer fixture or new execution is required by these qualifications.

### Optional comparison matched to a claim

T/Q affects H directly through thermodynamics/gases and indirectly through M, latent/state/hydrometeor/size changes. Cost improvement alone cannot separate these routes. If claiming additional observation-space contribution of M, first connect existing matching state/process/BT records. Where missing, a limited diagnostic may compare

\[
\Delta y_M(v)=H_{a_H}(M(C(v);f_b,\alpha_b))-H_{a_H}(C(v)).
\]

For a retained initial state x, denote this by `R_M(x)=H(M(x))-H(x)`. R_M measures the one-state observation change due to the chosen evolution. For retained background and accepted initial states x_b,x_a, distinguish the analysis-increment response difference

\[
\mathcal I_M=R_M(x_a)-R_M(x_b)
=[H(M(x_a))-H(M(x_b))]-[H(x_a)-H(x_b)].
\]

R_M can be nonzero while I_M is zero: an evolution-induced offset need not change the observation effect of the analysis increment. First use the four stored states x_b,x_a,M(x_b),M(x_a), matching existing BT and process records where available. Only missing values needed for a stated claim justify a limited extra H comparison; neither two new optimizations nor new calls for every case are required. PR409 did not evaluate these quantities. The later [retained Jul19 result](pr410_retained_case_claims_2026-10-11/REPORT.md) provides conditional input-equivalence inferences, without new H evaluations.

If the claim concerns sensitivity, distinguish `H_x(M(x0))*M_x(x0)*C_v` from `H_x(x0)*C_v`. Keep identical H auxiliaries, including frozen optical density, and the same valid seven-channel support on both sides; if a diagnostic side is inadmissible, record that outcome rather than shrink support. No-evolution H is a diagnostic counterfactual, not another same-valid-time host forecast. This neither isolates individual processes without their records nor proves forecast skill. It is not an unconditional completion gate, new optimization campaign or comparison executed by PR409.

## Actual data dependency and management attribution

The next real case needs native background/forcing/pressure/surface bound to admitted L1B, then analysis/audit/storage and interpretation. July20/21 L1B is decoded but remains PENDING_NATIVE_INPUT. Another valid date may be used first if selected by native availability and admitted QA/time/location before inspecting residuals; preserve the original pending records rather than silently substitute a well-fitting case. Scene date, initialization/lead and independent weather event counts differ.

The first prepared date need not wait for the second. Do not repeat the same archive search/request merely to create another receipt. Never relabel July19 states, extrapolate inadequate BC or silently substitute external models/reanalysis. V4 remains the sole new-case consumer; closed time/mask/provenance and finite-step checks stay closed.

The [78→79/100 rubric](AMI_L1B_MANAGEMENT_RUBRIC_2026-10-11.md) was **proposed in conversation reviews and relayed in user messages**. It is not a user-established scientific performance criterion, correctness probability, coverage fraction or proof of upper-goal completion. Earlier user-owned/user-supplied wording is superseded by this attribution correction; immutable dated execution records retain their bytes. Keep79 as historical management context without rescoring here. The three evidence stages above, not that number alone, govern completion claims.
