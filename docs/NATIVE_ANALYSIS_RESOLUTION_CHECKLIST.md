# Native satellite analysis: resolution checklist

Baseline: main `340c9a1d969f4aaf25765a6c4a1a6eef96b910ae` (2026-10-25).
Case: unchanged KO nominal 2025-07-19 00:00 and native MP137 checkpoint
00:00:40; 65,988 columns, 39 mass levels, original 128 B512 plus B452.

An item is checked only when its stated evidence exists. Code, synthetic tests,
saved-array replay, local KDM/RTTOV execution and full-host execution are distinct.
Past successful QR/finish/observation checks remain valid within their scope.
The current one-shot update has not demonstrated effective domain-wide cloud
analysis. No new optimizer, host step or second assimilation is implied here.

## Ordered work

- [x] **C0 — Identify the current calculation.** The existing satellite runner
  evaluates each candidate from the same original checkpoint and adds its T/Q
  increment once. The one-step microphysics call obtains an applied mean
  tendency; its output is not relabeled as step zero or fed into the next
  candidate. The existing alpha trials do not relinearize at an accepted point.
  Evidence: `run_native_satellite_case.evaluate_block`, `run_trials`, and
  `native_batch_microphysics.NativeBatchMicrophysics._evaluate` at the baseline.
- [x] **C1 — Prepare the actual binary32 update (code and arithmetic).** Add one value-only shared
  preparation function; predict exact wire rounding/addition, omit pairs with
  no bit change, retain strict `apply_pair`, report requested/applied/omitted
  counts and all-no-update status. Test mixed pairs, signed zeros, underflow,
  invalid states and immutable inputs. Recalculate the published candidate.
- [x] **C2 — Connect preparation to the host command (code and synthetic protocol).** Read THM_2 and QVAPOR
  arrays once in their declared native layout. Send only effective pairs, bind
  preparation to the current checkpoint/time/geometry, and validate every ACK.
  Synthetic command tests are necessary but do not count as a native run.
- [x] **C3 — Evaluate a representable candidate consistently (code and one B512 value pilot).** Observation cost
  and prior must use the same effective state; define
  `z_eff = (x_eff - x_b) / S` on active controls. Keep the original background,
  scales, total bounds, frozen blocks and observation support fixed. Quantized
  candidate acceptance is value-only; its exact derivative is not asserted.
  This item covers the shared evaluation boundary and block22 pilot only;
  full-domain reevaluation remains C6.
- [ ] **C4 — Verify the actual search direction where it dominates.** Preserve
  original full batches and independent FD criteria. Record native, profile,
  BT/cost and branch results separately, retaining failures. Block22 already
  has a separately prepared requested-direction measurement packet: native17 and BT/cost8 pass at
  epsilon 1e-6; strict profile8/common-epsilon joint33 does not pass. The other
  three dominant columns are not yet measured. Do not mark this item complete
  from JVP/VJP transpose checks alone.
- [ ] **C5 — Implement cumulative fixed-scene iterations.** Recompute the
  continuous KDM/RTTOV-K gradient after every accepted effective state; include
  the nonzero prior gradient `lambda*z_eff/Z`. Generate every trial relative
  to the original background, limit total displacement and backtracking, and
  record an explicit termination reason. Never restart z at zero or reuse g0.
- [ ] **C6 — Execute and assess the full-domain iterations.** All 129 original
  blocks, fixed support, exact effective-state receipts and fresh gradients
  must complete. Report actual T/QV/QC/QI/QS, LWP/IWP and regional O-B/O-A;
  cost decrease alone does not establish cloud-analysis success.
- [ ] **C7 — Connect completed host state directly to RTTOV.** Build native
  profiles from the checkpoint without an extra microphysics call. Preserve
  actual center/interface pressures, geometry, hydrometeors and unit/number
  conventions. Test the adapter independently of full-host AD claims.
- [ ] **C8 — Run paired full-model one-step forward checks.** Use separate,
  pinned no-update/analysis sessions from the same initial condition, one rank
  and one thread, with the intended isolated library. Apply T/Q once before
  solve. Verify ACK, actual saved time, linked library, state/tendency response
  and budgets including externally introduced analysis water. One step does
  not by itself certify balance or forecast improvement.
- [ ] **C9 — Perform the second assimilation on the carried state.** Bind its
  input/time/hash to the first step's output and compute a new observation
  cost/gradient. Declare observation valid time and reuse policy; reusing one
  scene as an independent likelihood is not an automatic new assimilation.
- [ ] **C10 — Close with Green/Red review and reproducible evidence.** Resolve
  actionable findings; publish source/input/build/call attribution and exact
  CI scope, update Graphify code and documentation semantics, and distinguish
  numerical connection, optimizer outcome, cloud efficacy and loop completion.

## Current work

C1/C2 code, arithmetic and synthetic protocol checks are complete in the
isolated `fix/native-effective-analysis` worktree. C3 completed one original
B512 value-only KDM/RTTOV pilot at the effective input. The canonical private host and operational install are unchanged.
The independent offline cloud-field audit completed without model calls and
is being preserved in a separate research evidence packet.

## Scientific distinctions retained

For a fixed analysis state x, a one-step map F gives the mean tendency
`r(x) = (F(x) - x)/dt`, in matching state coordinates. Therefore
`Dr = (DF - I)/dt`; finish's old-state dependence must remain.
An inner optimization iteration changes x while holding analysis time and
prior fixed. A full-host time step changes model time and includes dynamics
and other physics. The local microphysics gradient is not a full-host adjoint.

The existing fixed controls are moist-theta perturbation and dry QV. Actual
temperature must be reconstructed with live EOS; QC, QI, QS and number changes
are subsequent model responses. CFRAC is a recomputed threshold diagnostic,
not an independently optimized continuous cloud fraction.

### Progress log

- 2026-10-25: Created the ordered checklist in a clean worktree from the
  verified main commit. Existing canonical changes and the separate activation
  measurement packet are preserved.
- C1/C2: Vectorized preparation and live-stepper integration passed the
  focused source/boundary checks. Requested 1,679,418 pairs become 561,407
  effective pairs; 1,118,011 are omitted as bitwise no-ops. No host was run.
- C3: One original B512 block22 value pilot finished, retaining 2,037
  supported observations. Observation inputs are exact widened effective f32
  values; the prior uses z_eff. One earlier attempt completed KDM/direct RT
  but failed during KMA postprocessing because the frozen source packet lacked
  the calibration JSON. Both attempts and exact source snapshots are retained.
  Total new calls: 2 KDM value forwards + 2 direct RTTOV; AD/K/host/optimizer=0.
- Validation: 248 focused and related native-boundary tests passed; current
  changed sources and new tests pass Ruff. Actual host execution remains C8.
- C4: Preparing a new, fixed effective-displacement direction check at all
  four dominant columns. Epsilon endpoints remain continuous f64; the f32
  quantizer is not differentiated. No new C4 model calls have started.

### Actual-host prerequisite

The existing private live WRF executable is linked to the operational
libkdm6_c, not the actual-QR research DSO used by the local satellite case.
Mode environment flags cannot replace that code. C8 needs an isolated linked
variant, resolved Torch/libc10 dependencies and actual loader/hash evidence.
The operational install is not modified by C1–C3.

The ready hook is after conditional lateral-boundary input and before solve.
ACK comparisons cover emitted update coordinates only. C8 must establish the
full ready T2/QV background, including omitted no-op points: verify the pinned
boundary schedule or measure full-domain fields after boundary I/O and before
command. No actual boundary mismatch is asserted from source alone. The C8
controller must record/assert both nonsecret variant selectors explicitly;
an environment hash alone does not show their values or prevent legacy fallback.
