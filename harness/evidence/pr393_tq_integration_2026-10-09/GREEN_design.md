# GREEN design — bounded native-column T/Q → KDM → all-sky cost integration

Review basis: PR393 head `c543b98c`, merged main `ce77afa2`. This is a historical source/API follow-through design for the proposed `oracle/kdm6/da_single_column.py` and its tests. It did not launch the prepared native run, read a forecast, call RTTOV/host, or make a matchup/analysis claim. At its preparation the target was unlaunched; see the [case preparation](../pr393_target_preparation_2026-10-09/PREPARATION.md). The later [PR395 checklist](../CHECKLIST_pr395_native_tq_case_2026-10-10.md) separately records the authorized fresh run and state-capture work.

## Finding

A minimal faithful composition can reuse the current CVT, slot-trajectory, fixed-support all-sky adapter, and existing §8 dual minimizer. It calls `run_dual_minimizer` for a single-column T/Q control and does not call `run_fulldomain_analysis` or launch a native/host study. This reuses the existing solver rather than creating another one; the integration test can mock `sharded_allsky`/RTTOV while preserving the callback, shape, QC, cost, prior, and adjoint contracts.

The important slot-time detail is that `make_fulldomain_obs_eval(..., obs_time>=1)` defaults its frozen background H probe to `xb_sub`. That default only matches the observation slot at `t=0`. The wrapper must first collect the background trajectory through the declared `obs_time` with the same fixed parameters, forcing, `dt`, `xland`, and `normalized_dry` setting, then pass that `x_slot_bg` explicitly. The production full-domain path already follows this pattern in `_forward_to_slot` and passes `x_slot_bg` to the evaluator ([slot state](../../../oracle/kdm6/da_fulldomain.py#L1112), [factory call](../../../oracle/kdm6/da_fulldomain.py#L1223)).

## Proposed call path

```mermaid
flowchart LR
  xb[Native State B=1, K=39] --> CVT[make_default_cvt<br/>th + qv only]
  CVT --> x0[CVT state x0, v=0]
  x0 --> BG[collect_window_trajectory<br/>fixed M steps to obs_time]
  BG --> Hbg[make_fulldomain_obs_eval<br/>allsky=[0], clear=[]<br/>freeze S at H(M(xb))]
  x0 --> Dual[run_dual_minimizer<br/>existing §8 solver]
  Dual --> W[run_da_window per closure<br/>value M + local VJP recompute]
  W --> Obs[obs_adjoint at obs_time only]
  Obs --> Htrial[sharded_allsky → worker<br/>profile → RttovObsOp → J/adj]
  Htrial --> J[Jo + Jb + Jtheta]
  W --> g[adj_x0]
  g --> chain[grad_v = v + jac * adj_x0]
```

Concrete configuration for the proposed T/Q-only problem:

- Input `xb` and `forcing` stay in their supplied native `(B,K)` shapes. For the reviewed 5 km candidate the source-bound shape is `B=1`, `K=39` native full levels; the matching interface profile has `K+1=40` levels when supplied. Do not hard-code a 37-level substitute, remap the model column to a fixture grid, or import an external model/reanalysis profile. The adapter must reject mismatched State/Forcing and target-profile shapes rather than broadcast.
- Build `cvt, b_sigma = make_default_cvt(xb, th_sigma=0.8, qv_sigma=0.08, qv_levels=12, sigma_overrides={...})`. Set every non-`th`/`qv` state field (`qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg`) to sigma 0. Use `active_fields=("th", "qv")` both for CVT validation and `WindowConfig`. The builder's actual `n_controlled` counts are data dependent; record them from the current `b_sigma`/CVT record. The archived background happened to give 39 theta plus 12 qv controls, but that number is not an invariant for a new valid background.
- Initialize the state control `v` to all zeros. Then `cvt_apply(xb, b_sigma, v, cvt)` returns the unchanged background state and its Jacobian. The prior is `Jb = 0.5 * sum(v**2)`. Do not rewrite the background to the old −0.8 K diagnostic point or treat it as a warm start.
- The four physical process parameters are **not** controls in this T/Q-only scope. There is no current `active_params()` API. The caller supplies `WindowConfig.params=None`; the actual helper rejects custom parameters, calls `default_param_prior(active=())`, and internally builds `params_from_vtheta(prior, zeros4, live=False)`. The prior has a nominal `sigma_log=0.2` default, but with no active names it creates an all-zero effective `sigma_log` vector. Record zero active parameter names and zero parameter-prior cost. Do not silently inherit the full-domain prior default.
- Use a nonempty full forcing sequence and an observation time `1 <= obs_time <= len(forcings)`; `obs_time=0` is rejected because this adapter is specifically for T/Q through M→H. Collect `background_slot = collect_window_trajectory(xb, forcings, window_cfg, {obs_time})[obs_time]` using the same base `Parameters` and model controls as `run_da_window`; pass it as `x_slot_bg=background_slot` when creating the frozen H evaluator. The H forcing is `forcings[min(obs_time, len(forcings)-1)]`, matching the existing dual factory.
- The H inputs use exactly one all-sky column and no clear columns: `cloudy_pos=torch.tensor([0], dtype=torch.int64)`, `clear_pos=torch.empty(0, dtype=torch.int64)`, `y_bt.shape == y_rq.shape == (1,7)`, and `xland.shape == (1,)`. Keep channels 10–16, observation sigma 1 K, bias 0, Huber delta 1, and the background-frozen seven-channel support. For normalized-dry mode set `require_frozen_quality=True`; strict trial QC must fail closed if a channel in S is newly flagged.
- The chosen full-domain H route is `sharded_allsky` → `_allsky_columns_worker` → `model_to_rttov_tensors` → `RttovObsOp.apply` → `_part_loss` and the worker's local adjoint ([allsky_shard.py](../../../oracle/kdm6/obs/allsky_shard.py#L59), [factory callback](../../../oracle/kdm6/da_fulldomain.py#L774)). `batched_allsky_bt` is a separate direct singleton-capable route ([da_driver.py](../../../oracle/kdm6/da_driver.py#L198)); it does not itself provide the full-domain frozen-S/empty-clear contract and is not the route in this design.
- The all-sky worker constructs `RttovProfileConfig` with gas units 2, dry-air mixing-ratio convention, `cloud=True`, `dry_number` from the frozen all-sky controls, frozen `rho_d`, and explicit `p_lay`/`p_half` arrays ([allsky_shard.py](../../../oracle/kdm6/obs/allsky_shard.py#L88)). The native state/forcing remains on the native 39-center/40-interface grid. The profile builder flips bottom-up to top-down, converts center pressure Pa→hPa, and interpolates T/Q to its explicitly declared RTTOV layer pressure grid. If that target is extended with reference upper layers, state it as an RTTOV operator assumption; do not call it native model data or replace the native pressure suffix. No external model/reanalysis profile is part of this integration.

## Exact composition and returned accounting

The wrapper calls `make_fulldomain_obs_eval` with the singleton all-sky position, empty clear-position tensor, declared positive `obs_time`, `huber_delta=1`, and normalized-dry strict quality. At factory creation the background H quality probe runs on `x_slot_bg`; `_clear_bt_chunked` explicitly returns empty `(0,nch)` fields without touching clear RTTOV. The fixed mask and signature are then reused by the trial closure.

The wrapper calls `run_dual_minimizer` with the one-column state, full forcing window, fixed-support evaluator, T/Q-only `b_sigma`, no partition, and `default_param_prior(active=())` (effective parameter sigma all zero). For each dual closure, `run_da_window` sees `obs_adjoint(t, x_t)` return `None` at times other than `obs_time`; at `obs_time>=1` it calls the full-domain evaluator, records its scalar `j`, and returns the `State` covector. The window result carries the full pullback through every preceding M step, projected to active `th/qv` fields by `active_fields`.

The existing dual solver assembles `J_state + J_theta + J_obs`; with zero parameter sigma, the theta control remains at zero and `J_theta=0`. It applies the CVT chain rule `grad_v = v + jac * stack(adj_x0)`. Report `J_state`, `J_theta`, `J_obs`, `J_total`, support count/signature, state-field `n_controlled`, active parameter names/count, `n_window_evals`, `n_audit_evals`, and trial callback-result count separately. For a successful closure without callback/step errors or model-gate shortcuts, the source path requests one background all-sky support probe at factory construction and one trial H call per returned observation callback; clear H has zero calls. The background support trajectory requests `obs_time` value-only M steps. Each window closure requests `T=len(forcings)` value-only M forward steps and `T` VJP graph recomputations. These are source-path expectations, not instrumented call totals; report `runtime_kdm6_step_calls` and `runtime_rttov_launches` as unknown unless counted at those call boundaries.

`n_window_evals` and `n_audit_evals` are optimizer closure counters in `MinimizeResult`/`DualMinimizeResult`; they are not `max_iter`, actual RTTOV call counts, or total KDM executions. This module reuses the dual optimizer and reports those counters with their existing meanings. It leaves `runtime_kdm6_step_calls` and `runtime_rttov_launches` as `None` because it does not instrument those underlying calls. `n_obs_callback_results` counts returned trial observation results, not the one background H support probe. `WindowResult.vjp_steps` counts backward recompute steps; it does not count value-only forward passes.

## API follow-through and source checks

| Link | Existing source contract | Integration consequence |
| --- | --- | --- |
| Native state and forcing | `State`/`Forcing` tensor fields have `(B,K)` shape (`state.py:26–51`) | Keep the selected column as `(1,39)` and validate all forcing/profile shapes. |
| T/Q CVT | `make_default_cvt` at `da_cvt.py:206` sets theta add and qv mul; defaults also activate hydrometeor controls where admissible | Explicitly override every non-T/Q field to zero and record the resulting control counts. |
| CVT chain rule | `cvt_apply` at `da_cvt.py:103` returns state plus diagonal Jacobian | Build controls at zero and use `v + jac*adj_x0` for state-control gradients. |
| Parameter prior | `default_param_prior` at `da_dual.py:77` defaults `active=PNAMES`; zeros in `sigma_log` pin parameters | The current helper passes `active=()`; its nominal `sigma_log=0.2` default then yields an all-zero effective vector. No `active_params()` helper exists today. |
| Background slot state | `collect_window_trajectory` at `da_window.py:156` reproduces the value-only path; `run_da_window` at `:210` calls obs at `t=0..T` and performs the VJP | For `obs_time>=1`, precompute and pass `x_slot_bg=M_0:obs_time(xb)` to the frozen-quality factory. |
| Full-domain all-sky H and gradients | `make_fulldomain_obs_eval` at `da_fulldomain.py:672` freezes support; `sharded_allsky` dispatches each selected column through `_allsky_columns_worker` at `obs/allsky_shard.py:59`, which creates profile tensors, calls RTTOV, computes fixed-S loss, and extracts local adjoints | Route the one column at position 0 through all-sky; clear stays an empty tensor and receives no H call. |
| Empty clear branch | `_clear_bt_chunked` at `da_fulldomain.py:632` returns empty `(0,nch)` fields without calling clear RTTOV | Use `allsky=[0]`, `clear=[]`; test that clear H is never invoked. |
| Scalar J + covector | `make_fulldomain_obs_eval.obs_eval` returns `ObsEvalResult(j, adj, n_valid, signature)` after `sharded_allsky` | Accumulate `j` exactly once at `t=obs_time`; return only the `State` adjoint to `run_da_window`. |
| Existing lower-level dual solver | `run_dual_minimizer` calls LBFGS with `max_iter`, counts actual objective closure windows in `n_window_evals`, then performs the final accepted-control audit counted in `n_audit_evals` | Reuse it for the bounded one-column T/Q problem; do not call `run_fulldomain_analysis` or imply a full-domain run. |

## Focused test contract for the new module

The module and tests should demonstrate the complete API connection without the full-domain driver, real native forecast, or RTTOV binary:

1. Construct at least one `(1,39)` native-shape all-sky candidate with seven observations, `allsky=[0]`, and an empty typed clear index. Keep the existing small synthetic K case as an additional shape-generic test if useful. Assert the factory's frozen mask is `(1,7)`, `n_valid=7` for clean mock QC, and the callback returns one scalar cost and a shape-matched `State` adjoint only at the declared `obs_time`.
2. Make the fake all-sky H identify the supplied column/slot and assert the background QC probe receives exactly `collect_window_trajectory(...)[1]`, not `xb` at `t=0`. Make any clear H invocation fail the test.
3. Run the real `run_da_window`/dual closure and real KDM6 transitions with a mocked all-sky worker. Choose a nonzero but bounded synthetic observation innovation so the T/Q control gradient is exercised; assert the final slot state matches an explicit value-only trajectory, one VJP recompute is made for each forcing step, finite nonzero T/Q control gradient returns, and there are zero controls outside `th/qv` after the active-fields projection. A spy wrapping the real `da_dual.run_da_window` can inspect the returned `WindowResult`, because `DualMinimizeResult` itself does not expose it.
4. Assert `b_sigma` has nonzero entries only for theta and the lowest 12 qv levels (subject to builder zeroing), with all masses/numbers including `nccn` zero. Record dynamic counts rather than hardcode 51 for all backgrounds. Assert `prior.sigma_log` has shape 4 and all zero; `active_parameter_names == ()`.
5. Assert the optimizer starts from zero controls, so the first CVT state is `xb`; the final audited scalar satisfies `j_trace[-1]["total"] == jb_final + jtheta_final + jobs_final`, with `jtheta_final == 0` and no unrequested bias, sigma change, seed, or warm start.
6. Assert no call to `run_fulldomain_analysis` or the legacy `run_minimizer`; verify the existing `run_dual_minimizer` receives the one-column state, active fields `th/qv`, `sigma_log=0`, and no partition. Its closure may call `run_da_window`, the local M/VJP engine under audit. Check `n_window_evals` and `n_audit_evals` are reported as closure counters and actual KDM/RTTOV call totals remain unclaimed unless instrumented.
7. Reject `obs_time=0` and verify the observation callback only returns at the declared later slot. Verify shapes reject silent broadcasting: state/forcing `(1,K)`, `y_bt/y_rq/mask` `(1,7)`, one-element `xland`, explicit RTTOV layer grid and half-level grid with their declared `nlay`/`nlay+1` dimensions. Preserve native model pressure centres/interfaces and report RTTOV upper-grid assumptions separately.

The historical e619-era T/Q spec did not explicitly pin the `ParamPrior`, so “T/Q-only analysis” could be misread because `default_param_prior()` activates all four warm parameters by default. The current PR393 limited T/Q spec now explicitly routes through `run_single_column_analysis`, which passes `default_param_prior(active=())`; its nominal `sigma_log=0.2` default therefore yields an all-zero effective vector. Record zero active parameter controls, and do not reuse closure or max-iteration counts as execution counts.

## Current implementation verification and remaining coverage

The focused test file passes **12 tests** (`python3 -m pytest -q oracle/tests/test_da_single_column.py`). It covers singleton all-sky/empty-clear routing, a clear physical background routed through all-sky, a K=39 native-shape fixture with 51 T/Q controls, zero active parameters, the `obs_time=0` guard, strict seven-channel background/trial support, and the legacy clear-sky factory path. A nonzero 0.8 K synthetic innovation exercises the optimizer; the test checks positive `Jb`/`Jo`, zero `Jtheta`, the final `j_trace` decomposition, and a bounded central directional difference of `Jb+Jo` through CVT → real two-step KDM `run_da_window` → mocked all-sky H.

Limits: the directional derivative uses a synthetic K=13 profile and mocked H; the separate K=39 test checks shape/control-count handling but does not execute a native 39-level profile with RTTOV. Runtime KDM/RTTOV call totals remain explicitly `None`; the result records optimizer closure and audit counts plus successful observation-callback results. No real RTTOV, host, native input, or scientific result was used by these tests.

## Graph coverage

The required graph query returned the relevant `run_da_window`, `make_fulldomain_obs_eval`, `make_default_cvt`, `cvt_apply`, `batched_allsky_bt`, `make_dual_frozen_obs_eval`, and optimizer nodes, but its broad BFS produced 328 nodes and no compact trustworthy call path. The source follow-through above is therefore source-verified. `graphify-out/pr393-integration-green/semantic.json` records the bounded relationships and the graph-coverage limitation; it is not a full graph refresh.
