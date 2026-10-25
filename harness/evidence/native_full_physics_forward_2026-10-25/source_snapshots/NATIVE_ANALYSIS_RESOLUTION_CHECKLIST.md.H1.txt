# Native satellite analysis: resolution checklist

Baseline: main `340c9a1d969f4aaf25765a6c4a1a6eef96b910ae` (2026-10-25).
Case: unchanged KO nominal 2025-07-19 00:00 and native MP137 checkpoint
00:00:40; 65,988 columns, 39 mass levels, original 128 B512 plus B452.

An item is checked only when its stated evidence exists. Code, synthetic tests,
saved-array replay, local KDM/RTTOV execution and full-host execution are distinct.
Past successful QR/finish/observation checks remain valid within their scope.
The current one-shot update has not demonstrated effective domain-wide cloud
analysis. One no-analysis control and one T/Q candidate host step now complete
the paired forward execution from a matched ready state. Independent
saved-field arithmetic review also passes. Candidate RTTOV, physical
interpretation/acceptance, optimizer iterations and second assimilation remain
unexecuted.

**Current priority:** before making full-case C4/C5 claims, complete the
candidate checkpoint-to-RTTOV assessment and physical review for the paired
40-to-60 s full-physics host values. The two host steps, ready-state match and
independent saved-field arithmetic review are complete; candidate observation
cost and physical interpretation remain pending. The C4 v6 effective-direction packet is prepared but unlaunched. Its
scope is separate from the older requested-direction FD result. The host clock
advances 40 s to 60 s; do not retimestamp the endpoint to fixed time.

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
  BT/cost and branch results separately, retaining failures. Block22's older
  requested-continuous-direction packet has native17 and BT/cost8 pass at
  epsilon 1e-6; strict profile8/common-epsilon joint33 fails. That is not the
  post-binary32 effective-native direction. C4 v6 prepared that distinct
  effective direction but no calls have launched. The other three dominant
  columns remain unmeasured. Do not mark this item complete from JVP/VJP
  transpose checks alone.
- [ ] **C5 — Implement cumulative fixed-scene iterations.** Recompute the
  continuous KDM/RTTOV-K gradient after every accepted effective state; include
  the nonzero prior gradient `lambda*z_eff/Z`. Generate every trial relative
  to the original background, limit total displacement and backtracking, and
  record an explicit termination reason. Never restart z at zero or reuse g0.
- [ ] **C6 — Execute and assess the full-domain iterations.** All 129 original
  blocks, fixed support, exact effective-state receipts and fresh gradients
  must complete. Report actual T/QV/QC/QI/QS, LWP/IWP and regional O-B/O-A;
  cost decrease alone does not establish cloud-analysis success.
- [ ] **C7 — Connect completed full-host state directly to RTTOV.** Build
  profiles from each saved post-solve checkpoint without another MP137 call.
  Preserve native center/interface pressures, temperature, QV, hydrometeors,
  geometry and unit/number assumptions. Derive fresh `M_host0` from the
  completed CONTROL profiles with RTTOV quality=0, intersected with the
  original observation/source-valid mask and finite control BTs. Freeze its
  observations and weights; candidate quality may not shrink the support. Do
  not assume the old microphysics-only support count of 381,528 applies. This
  is a value connection, not a host derivative.
- [ ] **C8 — Complete and assess paired full-physics one-step host forwards.**
  The control and candidate forwards have run; independent saved-field
  arithmetic passes, but physical interpretation and candidate RTTOV remain
  pending. Start both independent sessions from the same pinned 40 s origin
  and identical initialization recipe, boundary assets and cadence. In each,
  run through boundary input and capture the entire ready state immediately
  before solve. Compare every retained schema and state value, including T/Q,
  H memory, LBC-updated and other evolving fields. Do not treat a ready capture
  as a restart-complete state or restart either run from that capture. If the
  ready states differ, do not claim a common-background paired effect. Bind
  candidate T/Q to its own ready-state hash and run each through the 60 s solve.
  Keep MP137, `NO_MP_HEATING=0`,
  `USE_THETA_M=1`, `USE_Q_DIABATIC=0`, RRTMG LW/SW 4/4 at `radt=1/3` minute,
  Noah LSM 2, Shin-Hong PBL 11 and KSAS cumulus 37 enabled. Pin the actual
  namelist, boundary assets, linked library, and executable; use one rank,
  one thread, and retain both internal tiles. Capture all 65,988 host columns,
  including LBC cells. With `SPECIFIED=T`/`SPEC_ZONE=1`, direct MP covers
  64,960 interior columns; the 1,028 outer one-cell-ring columns are outside
  that MP crop but remain in the full host output. `RELAX_ZONE=4` does not
  define the MP crop. Record ready-entry and post-step H memory separately.
  Verify actual time, ACK, state/tendency response and externally introduced
  analysis water. The endpoint is the actual 60 s state, not a retimestamped
  40 s state. The normal C ABI remains native REAL4 KDM; C8 must explicitly
  bind the isolated forward-only `kdm6_native_fp64_value_c` bridge. That bridge
  widens 12 state + 4 forcing inputs, evaluates the selected FP64 KDM map, then
  writes 12 state + 3 precipitation + RHOG outputs back to REAL4 once. All
  other host physics remain native REAL4. The separate fp64 C API gate covers
  block34 B512, block40 B512 and a nonsquare 2x4 subset. It accounts for 22
  positive-dt requests (including references), 12 fresh completed C API
  forwards, four dt=0 identities and nine refusals; arithmetic/ABI checks pass.
  The block34 FP-environment capture is unavailable. Preserve that limitation;
  it is neither C4 FD evidence nor a paired host run. Then send each saved
  post-step checkpoint directly to RTTOV.
  The observation is nominally 00:00 UTC and pixel-specific UTC is unknown;
  declare use of that scene across model time 40–60 s as an assumption.
  A value pair does not certify balance, forecast improvement or `g_host`.
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

The no-analysis control and T/Q candidate C8 host steps have both completed
from the same 40 s origin using the explicit fp64 KDM value symbol. The origin
contains an earlier unaccepted single-column KO7 T/Q diagnostic;
“no-analysis” means no new increment in the control step, not a pristine
atmosphere. The control post-LBC ready capture differs from its origin only in
`WE_JUST_D01_LBC` (0→1). Before candidate command, all 652 serialized variables
and 322,426,586 numeric elements matched the control ready capture exactly
(zero mismatches; shared ready SHA
`0c4836a2a44531c98d38d3ded15cab5048679b1139f3e4fd96fb62eff84bfad3`). The
candidate ACK passed with 561,407 applied rows, 855,443 changed components,
zero remaining requested no-op rows and 2,012,125 empty points. Its actual 60 s
output checkpoint SHA is
`ff3c101e3b352594471ac5dfd0daab07c0daff3b6d406c88e2461283389978b5`.
Independent saved-field arithmetic review passes across all 652 variables and
322,426,586 numeric elements (26,454,541 stored values differ; 13 selected-field
count/max/fsum metrics reproduced). This is not physical-process attribution,
actual-temperature reconstruction or a closed water budget. Candidate RTTOV
and paired observation cost remain pending. The 60 s output is not retimestamped
to 40 s.

An offline endpoint audit reports `(output60-ready40)/20 s` for `THM_2`,
QVAPOR, QCLOUD, QICE, QSNOW and `H_DIABATIC` over all 65,988×39 cells.
These are whole-host elementwise responses, not a KDM-only process budget.
`THM_2` is moist-potential-temperature perturbation, not actual temperature;
`H_DIABATIC` delta/20 has units K s-2, not a temperature tendency. No exact T
reconstruction, conservation, or forecast claim is made. See the endpoint audit
summary in [`NATIVE_FULL_PHYSICS_FORWARD.md`](NATIVE_FULL_PHYSICS_FORWARD.md).

C7 has a four-block direct-RTTOV pilot at the control 60 s checkpoint: chunks
0, 34, 40 and 128, four direct calls, 8,218 fresh `M_host0` channel cells and
zero KDM/RTTOV-K/extra-MP calls. The old 381,528 microphysics-only support was
not reused. The remaining 125 blocks are in progress; full-domain C7 and the
full cost are not complete. Candidate checkpoint-to-RTTOV has not completed.
Details and receipt hashes are in
[`NATIVE_FULL_PHYSICS_FORWARD.md`](NATIVE_FULL_PHYSICS_FORWARD.md).

The next measurement priority is candidate C7 RTTOV evaluation and physical
interpretation of the completed C8 host pair, described in
[`NATIVE_FULL_PHYSICS_FORWARD.md`](NATIVE_FULL_PHYSICS_FORWARD.md). This is a
40-to-60 s response diagnostic, not a fixed-time retimestamp. Saved-field
arithmetic is reviewed; candidate RTTOV and physical interpretation remain
pending. C4 v6 is prepared but not
launched; the old requested-direction joint33 failure remains scoped to that
older vector. C5 iterations remain unimplemented and unexecuted.

The conditional fp64 KDM value bridge is isolated: the operational `kdm6_step_c`
body and default 14 exports stay unchanged. The explicit bridge was used in the
two host steps. The separate C API boundary gate has arithmetic/ABI pass status
but its block34 FP-environment capture remains unavailable; no full bridge
qualification is claimed.

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
- C4: A v6 fixed effective-displacement direction packet is prepared for the
  four dominant columns but remains unlaunched. Its scope is distinct from the
  older requested-continuous-direction joint33 failure.
- C7/C8: Control and candidate full-physics host steps ran from a bitwise-matched
  post-LBC ready state. The control output has a four-block direct RTTOV pilot.
  Candidate output SHA `ff3c101e...9978b5` and ACK 561,407 rows/855,443
  components are receipt-pinned. Independent saved-field arithmetic passes;
  physical interpretation and candidate RTTOV remain pending. Another 125
  observation blocks are in progress.

### Actual-host attribution and remaining limits

The operational executable/install remain unchanged. Both C8 sessions loaded
the isolated private executable and explicit fp64 KDM value DSO; the recorded
selectors were `norm_actual` and `actual_departure`. Ready-state equality and
saved-field arithmetic are proved. Candidate RTTOV, full-domain support review
and physical-process interpretation remain pending. The host forward values do
not supply a full-host derivative.
