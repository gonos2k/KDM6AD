# Differentiable KDM → GK2A–RTTOV: resolution checklist

Baseline: `bb04e52b4aca8028257e1529fa7005a61c2f54c7` (PR #215).
Scope agreed with the user on 2026-09-06: mathematical, engineering,
meteorological and numerical validation of differentiable KDM, including
hydrometeor process interactions, through GK2A–RTTOV data assimilation.
Forecast skill, unattended cycling and a full host-model adjoint are not gates
for this task. Team work uses Luna (`gpt-5.6-luna`), reasoning `high`.

## Completion rules

An implementation, an executed verification and a scientific interpretation
are different evidence. Mark only the verified subcase complete; retain the
unmeasured range explicitly. Test counts do not measure process/regime coverage.
State-to-state Jacobians do not establish named process attribution. A zero
response alone does not establish structural independence.

For fixed forcing and a declared branch, validate the executed discrete map
with independent directional differences and the identity
`<M v,u> = <v,Mᵀ u>`. Restrict initial controls only at the input/output control
boundary. Preserve intermediate state sensitivity paths. For composed
observations, validate `D(H∘M)v = H_x M_x v` with the same input, mask,
geometry, surface, bias and error weights. First-order RTTOV K products do not
establish `dK/dx` or a full second-order Hessian.

## Work items

| ID | Action and acceptance evidence | Status |
| --- | --- | --- |
| V1 | Selected hydrometeor process rates → applied transfers → later rates/states: graph-connected diagnostic records, independent AD/FD, active conditions and zero interpretation. Report untested processes/regimes. | Selected warm/cold controlled chains verified; representative process/regime coverage remains open |
| V2 | Epsilon sweep and stage comparison: distinguish truncation, roundoff and changed recorded branches; masks/values, not just counts. Prove optional diagnostics preserve normal values and products. | Phase, ProgB knot and selected shared-cap checks verified; full internal branch coverage open |
| V3 | Pin actual observation/assets and execute a connected KDM–RTTOV objective-gradient check; record input/profile/BT/K/J/gradient, mask/aux provenance and serialization resolution. Explicitly identify fixture geometry and missing real auxiliaries. | Selected actual-input clear/cloud first-order FD verified; actual auxiliary validation partial |
| V4 | For selected actual applied transfers, evaluate residual and its directional derivative under an explicit fixed measure. Differentiate a legacy nonzero residual rather than impose a new conservation law. | Selected water and local thermal-work derivatives verified; full physical number/enthalpy budget open |
| V5a | Execute Python ↔ built C ABI JVP/VJP regression on `.so` and `.dylib` paths; CI must not silently skip a missing required library. | Local and Ubuntu/macOS CI verified; see dated evidence below |
| V5b | Fortran shim invokes JVP with asymmetric arrays and checks an independent expected product/layout. | Locally verified; see evidence below |
| V6a | Reject fixture/output overlap before filesystem mutation. | Locally verified; see evidence below |
| V6b | Live writer and prepared runner agree on workspace ownership and locking. | Locally verified; see evidence below |
| V6c | Preserve parser failure diagnostics after a successful external exit. | Locally verified; see evidence below |
| N1 | Bounded fixed-interval timestep study: state and directional derivative changes, aligned forcing/observations, recorded branch scope. This is distinct from correctness of each discrete map. | Fixed-interval comparison executed; convergence not established |
| O1 | Higher-order RTTOV derivatives and parameter identifiability: document the current first-order scope; do not claim full Newton or unique data-driven retrieval. | Deferred: optional, not a first-order completion gate |

## Physical interpretation kept open

- Host/kernel particle-number units remain conditional until their boundary
  contract is established. A chosen numerical measure does not resolve it.
- M1 (actual ten-minute applied transport residual), M2 (first negative QIB
  operands) and D4 operation-order attribution retain their existing measurement
  status. Portable sensitivity diagnostics do not substitute for those runs.
- A direct RTTOV input omission does not imply an absent indirect KDM path.
  In particular, number/volume moments can affect later observable cloud states.
- Successful fixture RTTOV gradients establish wiring within declared auxiliary
  conditions, not independently validated actual satellite geometry/surface.

## Executed evidence

Resolution artifacts are recorded under
`graphify-out/resolution-20260906/`. Commands, exact tested source, failures,
skips and asset limitations will be recorded here as the items are verified.
The preceding audit remains a dated record under
`graphify-out/final-goal-audit-20260906-2045/parent/`.

### V5 — cross-implementation products

- A clean local `kdm6_c` / Fortran smoke build passed the asymmetric `(2,3,4)`
  tile JVP, output support and JVP/VJP inner-product checks.
- `KDM6_C_LIBRARY=... python3 -m pytest tests/test_cross_tree_adjoint_parity.py -rs -q`:
  **2 passed** against the rebuilt macOS library. An invalid explicit path fails
  collection instead of silently skipping.
- Both port CI jobs now require the library built in that job. Linux execution
  of the new selection is pending CI; local macOS is the executed evidence.
- Build commands and library/source provenance:
  `graphify-out/resolution-20260906/native/V5.md`.

### V6 — RTTOV ownership and failure records

- Equal/ancestor/descendant fixture-output paths are refused before mutation.
- Writer/live/prepared runners share a case owner, including a case named `out`.
- Parse failures retain a bounded failure record before disposable case cleanup.
- Runner/writer/process/timeout suite: **111 passed**. A second selection with
  fulldomain tests returned **51 passed / 2 skipped**; selections overlap and
  must not be added together.
- Evidence: `graphify-out/resolution-20260906/rttov-boundary/evidence.md`.

Parent validation: shipped local CTest **17/17 passed** (3.91 s),
`RelWithDebInfo`, `KDM6_ENABLE_TEST_HOOKS=OFF`, CMake source directory
`/Users/yhlee/KDM6AD-audit-pr205/libtorch`. This is port-only validation.

### V1/V2/V4/N1 — selected process diagnostic campaign

- [x] Optional graph-connected stage rates and actual state deltas; the normal
  forward, JVP and VJP are bitwise unchanged in the selected fixture.
- [x] `praut`, `pracw`, `prevp` have nonzero independent FD responses; epsilon
  sweep `1e-3, 1e-4, 1e-5` and scaled errors protect the small derivatives.
- [x] `warm.prevp → state_update.qv/qr/t` is graph-connected; qv/qr local
  derivative magnitudes are 20 in the 20-second fixture. Cold consumer links
  are zero in this fixture; that does not establish general independence.
- [x] Exact tapped phase-mask comparison, mask hashes, first changed cell,
  missing-stage reporting and per-column main/ice subcycle records distinguish
  changed layouts even when aggregate counts remain unchanged.
- [x] Actual D2–D4 deltas and the full-step fixed `rho*delz` water residual have
  directional checks. Full residual AD `-1.0774085518e-3` vs signed FD
  `-1.0774085712e-3`; these include the perturbed initial inventory on both sides.
  This operator measure is not a resolution of the physical dry-air unit issue.
- [x] One 20-second versus two 10-second steps compare states and transported
  tangents under the same forcing; the result is a refinement diagnostic,
  not proof of convergence or branch stability.
- [x] Selected nonzero warm-control→later cold-rate sensitivity (2026-09-19
  autoconversion case below). Representative cold-regime coverage remains open.
- [ ] Internal limiter/reclassification/PSD/satadj mask and threshold atlas,
  including discontinuous topology changes; selected phase, shared-cap, satadj
  and final DSD decisions are recorded, not an exhaustive atlas.
- [ ] Applied enthalpy/particle-number directional residuals with closed unit
  contracts; selected water residual checks do not substitute for these.

Evidence: `graphify-out/resolution-20260906/sensitivity/report.md` and
`report.json`. Fixture shape is **one column × two levels**, not two columns.
Final parent diagnostic selection: **6 passed** (including the equal-count,
changed-cell/column counterexample). Agent full oracle before this final metadata
addition: **1123 passed / 30 skipped**. Parent earlier full run: **1122 passed /
30 skipped**; these are successive runs, not additive results.

### V3 — actual input and live objective chain (partial)

- [x] Actual KDM/GK2A slot `202507190000`: 6,424 assigned columns with all nine
  clean IR quality flags usable. Input files, the executed KDM code, selected
  clear/cloud fixture, named coefficient/hydrotable and executable are hashed.
- [x] One 20-second KDM step remains graph-connected through profile conversion,
  live RTTOV K and the same fixed-mask Huber objective. Initial `th/qv/qc`
  directions use multiple epsilons on the clear path.
- [x] Exact mask comparisons, serialized profile changes, BT text quantum
  (`0.001 K`) and the resulting FD rounding bound are reported. Empty masks,
  zero/nonfinite directions and insufficient output resolution cannot pass.
- [x] The actual all-sky bridge and cloud K execute on one hydrometeor-bearing
  column; the final result has **zero jointly usable IR channels** and is
  explicitly unresolved. Zero J/gradient is not derivative verification.
- [x] Resolve the selected clear-path FD/output-resolution gap; see the
  2026-09-07 precision and connected first-order evidence below.
- [x] Establish selected usable all-sky first-order FD evidence; see the
  2026-09-07 actual cloudy-column and 2026-09-19 named-control evidence below.
  The historical zero-mask run remains unresolved and is not reused as proof.
- [ ] Replace and validate fixture geometry/surface/datetime where actual
  auxiliary inputs are required. Current live results remain **wiring-only for
  those auxiliaries**, with actual geolocation/observation data distinguished.

Authoritative final artifacts are `live-gradient/clear-final.json` and
`live-gradient/cloud-final.json` under the resolution directory. Earlier
`live*.json` are development attempts and are excluded from the final manifest;
notably the old zero-mask `live-allsky.json` was falsely labelled complete by
an intermediate runner. The final code and portable refusal test correct that
label; the old artifact is not evidence of a successful gradient check.

Portable completion-boundary test plus private inventory/KDM smoke: **3 passed**.
Optional second-order/identifiability work (O1), physical M1/M2/unit/D4 work,
and the open coverage above remain explicit; no all-process or full-DA scientific
validation completion is claimed.

Final integration run: **1125 passed / 30 skipped** (65.29 s). Subsequent
changes were limited to the evidence runner's clear/cloud batching, input
selection and provenance; its three tests and both live modes were rerun.
The authoritative clear case now uses the same hydrometeor-bearing column
`20004` as the cloud case, so an empty-cloud negative control is not mistaken
for the target sensitivity experiment. Clear mode has 9 usable channels and
`dJ/dε` for the selected initial qc direction is `-0.004329378946021511`.
This establishes a nonzero indirect path; all three direction checks remain
unresolved under the FD accuracy/output-resolution gate.

## Goal-audit follow-up (2026-09-06, baseline `2a0afaee`)

Evidence directory: `graphify-out/goal-resolution-20260906-2307/`.
The work below extends selected diagnostic evidence. It does not reopen the
previously resolved window projection, AMI decoding or freeze-domain issues.

| ID | Bounded action | Completion boundary |
| --- | --- | --- |
| A1 | Separate the clear qv discrepancy into input-domain, KDM/profile and live H/J checks. | Invalid negative-mass FD endpoints cannot validate a physical tangent. A new admissible direction is a separate experiment, not a correction of old measurements. |
| A2 | Preserve the zero-quality cloud case and find a nonzero-cloud case with usable channels; check content and effective-size K independently. | Output-quantization bounds must be small relative to the derivative signal before a numerical-accuracy pass. Fixture auxiliaries remain explicit. |
| A3 | Record existing named ProcessControls across warm, mixed-phase and melt singleton fixtures. | An active controlled group is not every raw process; inactive or unresolved pairs remain visible. |
| A4 | Check nonzero cold/moment indirect paths using physically admissible producer/consumer inputs. | A prescribed kernel operand alone cannot establish reachability from the upstream process. |
| A5 | Compare stage rate and actual state-delta AD/FD per cell before reduction. | Fixed numerical water measure and tapped phase masks do not close physical number/enthalpy units or all internal branches. |
| A6 | Compose verified M/P/H with a declared control transform, prior and fixed observation objective over a window. | Live one-step direct AD and portable window tests are separate evidence until the combined experiment is executed. |

- [x] A5 diagnostic reduction gap: rate/state-delta JVPs and independent FD
  now retain per-cell arrays and maximum local error. An opposing-cell
  counterexample has zero aggregate error but nonzero local error.
- [x] Rate-only records with identical input/output state objects no longer
  emit an apparent applied-state delta. Actual state-update records retain it.
- [x] Diagnostic comments now identify the exact tapped masks/subcycles and
  the unverified internal-branch range.
- [x] The live evidence runner can select an explicitly identified column from
  the same quality-validated candidate set. The failed high-cloud case remains
  a negative control rather than being overwritten by a successful selection.
- [ ] Full internal-branch atlas, physically closed enthalpy/number budgets,
  representative warm-to-cold attribution and combined live window/CVT/prior
  evidence remain open unless explicitly supported by the results below.

### Follow-up executed results

- A1 selected clear qv: the historical absolute direction makes negative input
  qv and reaches the state-update positivity cap. A separate relative direction
  bounded by `0.1*qv` passes the unchanged 5% actual-J FD/resolution criterion
  at epsilon `0.2,0.3`: AD `-0.60017974713`, FD `-0.5925,-0.59833333333`.
  Observation masks and nonnegative qv/qc endpoints are preserved. This closes
  this selected valid-neighborhood check, not every clear direction.
- A2 actual column 42558 retains positive post-step cloud content and 8/9 usable
  clean IR channels. Direct HYDRO6 K at epsilon `1e-4 g/m³` passes the unchanged
  5% error/resolution criterion for zero-based channel indices 10,12,13.
  Effective-size K and smaller epsilon checks remain resolution-limited.
  Column 20004 still has no usable channels; column 23860 is cloud-free after
  the KDM step. Neither is relabelled a successful cloud-sensitivity test.
- The current admissible all-sky whole-chain run remains unresolved: qc has a
  nonzero AD direction (`1.2213730e-5`) below BT text FD resolution, while qv/th
  perturbations change the quality mask at the tested scales. Fixture auxiliary
  inputs remain explicit. No quality flag or criterion was weakened.
- A3 existing six controls × three singleton regimes: nine selected directions
  verified, eight inactive pairs, one cold-freeze output-resolution limitation.
  Cold deposition/riming affect mass, bg and actual temperature. Per-field
  output-ULP bounds separate insufficient FD resolution from an unproven AD
  defect. This table does not cover every raw process or internal branch.
- A4 reachable coordinator warm.prevp→cold pinud/pidep is graph-connected but
  zero in the selected case. A non-reachable prescribed-input candidate was
  discarded; nonzero physical cross-process attribution remains open.
- Parent full oracle: **1136 passed / 30 skipped / 51 warnings** (89.45 s).
  The final helper-boundary selection passed **22 tests** (23.16 s),
  including the data-driven boundary classifier and refusal guards. Production f32 physics and native ABI are unchanged.

Authoritative follow-up evidence: `clear/v3-relative20-30-live.json`,
`cloud/diagnosis.json`, `cloud/full-mhj-admissible-42558.json`,
`process/attribution.json`, and `parent/report_ko.md` under the directory above.
Earlier live files are historical attempts, not additional successful cases.


## Precision and connected first-order evidence (2026-09-07)

Evidence: `graphify-out/goal-completion-20260906/`. These measurements extend
selected coverage; they do not certify all processes, branches or meteorological
regimes. Forecast skill/cycling are outside this checklist's completion gates.

- [x] **A2 serialization boundary:** profile and cloud inputs use 17 significant
  decimal digits (`%.16E`), with f64 bit-roundtrip tests. Copied RTTOV cases use
  `defn%realprec=12` (`E21.12`, measured BT quantum `1e-9 K`). This is output
  formatting, not a claim about the binary's internal arithmetic precision.
- [x] **A2 selected actual cloudy column:** at column 42558, initial qc/qv/th
  directions pass the existing 5% AD/actual-J FD and resolution criteria at
  epsilon .008 and .01, preserving candidate quality masks. Direct HYDRO6
  content and HYDRO_DEFF6 size K checks resolve channel indices 10–15 at the
  tested scales. See `cloud/common-eps-mhj-42558.json`; no quality gate weakened.
- [x] **A6 selected composed window:** two actual KDM steps, scalar initial-qv
  transform, prior `0.5*z**2`, and fixed GK2A/RTTOV Huber objective. Retained
  JVP/VJP and direct-unroll VJP give `-0.5473831819460413` (duality error
  `4.44e-16`); total derivative including prior is `-0.4973831819460413`.
  Actual total-J FD at epsilon .2/.3 differs by `4.0674e-5` / `3.9735e-5`,
  with unchanged masks and output rounding bounds `2.25e-8` / `1.50e-8`.
  This selected first-order check does not certify every state component or dK/dx.
- [x] **A3 fixture correction:** earlier cold/melt fixtures had qg/bg=1000,
  outside [100,900]. Their numerical measurements remain historical evidence;
  an admissible-moment claim for those old fixtures is withdrawn. Diagnostic
  fixtures now use qg/bg=500. The rerun 6-control × 3-regime matrix retains
  9 verified selected directions, 8 inactive/zero pairs and 1 cold-freeze
  output-resolution limitation. These are synthetic fixed-forcing fixtures.
- [x] **Selected named-control → live J:** a declared synthetic transformation
  of column 20709 scales hydrometeor masses/numbers by .1 and resets bg=qg/500.
  With fixed background dry density and 7 usable channels, deposition alpha-J
  AD=9.57672925 and riming AD=-.0113245275 agree with actual RTTOV FD at .03/.1
  (maximum relative errors .00278/.00166). This is total group intervention,
  not unique attribution to each raw rate. See `process/synthetic-live/`.
- [x] **Unmodified actual named-control case:** resolved for deposition and
  riming on column 45577 in the 2026-09-19 follow-up below. The inactive 42558
  and three zero-usable alternatives remain excluded; no synthetic replacement.
- [ ] Internal-branch runtime coverage, full physical number/enthalpy contracts,
  and representative upstream-process→downstream-process routes remain bounded
  by the recorded tests. Static kernel/branch inventories are not coverage counts.
- [ ] Fixture pressure/geometry/surface/time and loaded RTTOV source-build
  identity remain explicit limitations; external K evidence is first-order only.

Validation: full local oracle **1145 passed / 30 skipped / 51 warnings** (91.26 s),
then focused writer/process/cold/window tests **138 passed** (13.46 s). Later
small diagnostic/test changes require their own focused result below; counts
are overlapping and must not be added. Prior five-check CI success belongs to
`93b0f5d`, until a new head's checks are separately verified. Native f32 physics
and the packed ABI are unchanged in this follow-up.

### Table-knot and local-neighborhood diagnosis

- [x] The density-500 bg central-FD mismatch is explained by the ProgB table
  knot: AD agrees with the selected one-sided slope; the opposite slope differs.
  The production interpolation is unchanged. A dedicated one-sided regression
  preserves this boundary. The cold-profile smooth probe explicitly uses density
  450; bg→T/Q/HYDRO now verifies at .01/.03/.1 (selected T relative error 8.9e-7).
- [x] Cold-profile comparisons share a small local status/endpoint-ULP helper;
  named rate checks cannot inherit a pass from profile-only checks.
- [x] Follow-up below identifies the ice-budget transition. At this earlier
  checkpoint, the selected tiny deposition pidep agreed with FD at epsilon <=.03
  (relative error <=1.1e-4), but epsilon .1 differs by about82%. This larger
  neighborhood was unresolved at that checkpoint; it was not classified as output quantization or
  an established local AD defect. Tapped topology is not every internal branch.
- Focused post-diagnostic validation: **15 passed** (ProgB + cold-profile),
  in addition to the overlapping earlier tests above.

- Reachable warm.prevp→cold investigation used an 18-state admissible grid.
  Selected qv→pinud/pidep FD agrees, but direct traced pinud/pidep/psdep/pgdep
  derivatives with respect to warm.prevp are zero in the selected state.
  These are different claims: this is a locally dormant connected edge, not
  a nonzero named-process causal validation. See `process/warm_prevp_cold_grid.*`.


## Shared-budget and thermal-work follow-up (2026-09-07, baseline b1ee885)

- [x] **V1 reachable cross-process partial:** in the admissible cold fixture at
  qg/bg=450, raw `pidep` (negative: ice sublimation) changes the ice budget that
  limits `pgaci` (ice collection by graupel). The traced conditional derivative
  is positive (`0.0106928195`). Replaying the exact reached limiter operands
  reproduces all limited rates bitwise; independent local-operand differences
  at epsilon 1e-4/1e-3 agree within 1e-6 relative error. This conditional
  partial is not an independently realizable physical-control intervention.
  `test_reached_ice_budget_couples_deposition_and_collection` guards this link.
- [x] `warm.prevp` diagnostics now include the later `psdep` and `pgdep`
  consumers. A bounded 24-configuration actual-coordinator probe (36 substeps)
  found these direct edges locally dormant; zeros are not general independence.
- [x] **V4 selected local thermal identity:** actual `state_update` captures
  graph-connected cpm/xl/supcol only when diagnostics are requested. Sensible
  work `cpm*deltaT` and reconstructed latent/amount work are specific model
  energy in J/kg, not J/m³. Their qv-direction derivatives are approximately
  16.60761452 J/kg and agree with independent FD at .01/.03/.1. Residual is
  approximately 2.09e-11 J/kg. Scope: first coordinator subcycle before satadj;
  these coefficients do not establish a physically closed full-column enthalpy.
- [ ] Actual auxiliary inventory confirms real surface/coordinate fields and
  their units/hashes, but lacks verified RTTOV viewing geometry and several
  surface ancillary quantities. No adapter with invented defaults was added.
- [ ] Full physical energy/number budget still requires declared mass-reference
  conventions, later satadj latent work and sedimentation enthalpy outflow.
  Local applied-work agreement does not remove these missing terms.

- [x] **V2 exact cap transition:** the existing ice-mass limiter now records
  its actual `source`, `value` and `source > value` mask through the existing
  optional stage trace. Deposition alpha +0.1 binds the cap and -0.1 releases
  it at density 450. The diagnostic therefore reports changed tapped topology;
  a cross-branch central difference is not certified as a local derivative.
  Smaller same-branch perturbations retain their existing agreement. No new
  limiter, physical formula, tolerance or parallel trace protocol was added.
- [ ] **M1 applied transport:** read-only inventory found no paired applied
  departure/arrival streams in the archived ten-minute runs. Their executable
  identities also differ from the current binary. Those runs cannot close M1;
  a source-attributed, isolated instrumented run is still required.

Validation of this follow-up: **13 focused tests passed** (stage diagnostics,
cold-profile cap transitions and local energy identity; overlapping earlier
suites). Local thermal FD maximum relative error is 2.6896472278e-11. Artifacts:
`graphify-out/goal-budget-20260907/parent/`. Prior full-oracle and CI results
remain attached to their recorded commits until this head is checked.

## Applied satadj and downstream melting (2026-09-07, baseline 43b5426)

- [x] **V1 total control→later process:** on the existing admissible melt
  fixture, total riming alpha changes D5 `pgeml`. The actual source is the
  controlled **pre-conservation** `cold` bundle, not the later `cold_limited`
  record. Genuine forward-mode JVP and reverse VJP both equal
  -8.751409092818744e-10; independent FD at .01/.03/.1 has maximum relative
  difference .001664725 and unchanged tapped topology. The example paacw_adj
  value does not establish its unique causal contribution. No runtime or
  global diagnostic monkeypatch is used.
- [x] **V4 actual satadj boundary:** move the existing stage record to the
  executed update and retain pcact, pcond, xl and cpm. No duplicate boundary
  or change to physics arithmetic is introduced. The local identity is
  `cpm*(T_out-T_in) = xl*(pcact+pcond)*dtcld`, including activation.
  Cold pointwise residual is 2.01794137e-12 J/kg. A resolved warm qv direction
  gives about1193.77672658 J/kg; actual/formula AD and independent FD at
  1e-4/1e-3/1e-2 agree with maximum relative differences 2.217e-10/9.213e-11.
  The cold pcond-only derivative remains unresolved numerically. A few endpoint
  ULPs do not exclude upstream roundoff. Full-column/all-subcycle energy,
  sedimentation enthalpy and physical mass-reference conventions remain open.
- [x] **N1 bounded refinement evidence:** three existing singleton regimes at
  fixed forcing/final time20s, 1/2/4/8 external steps, transported initial-qv
  JVPs and independent endpoint trajectories. Warm qc successive state and
  tangent differences decrease; melt qc state differences decrease while
  tangent differences flatten/increase at the finest pair. Cold nccn changes
  are unresolved at output spacing. This measures behavior, not universal
  convergence order or an all-branch proof.

Final focused validation: **14 passed /18 deprecation warnings** (12.21s).
Warnings originate in torch.jit.script during genuine forward-mode execution.
Counts overlap prior suites. Reproducible public-source artifacts live in
`graphify-out/goal-applied-20260907/` (parent, energy, process). M1 copied-host
instrumentation is separate work; no ten-minute applied residual is claimed
by these portable tests. Operational f32 and packed ABI are unchanged.

## Actual named controls and M1 build boundary (2026-09-19)

- [x] **V3 selected actual process controls:** unmodified WRF column 45577,
  `as_stored` CCN (no fallback), actual sea `xland=2`, one 20-second KDM step.
  Nine clean IR channels remain jointly usable. Deposition and riming controls
  are applied before the evolved state is passed to live RTTOV. The objective
  is the same fixed-mask Huber sum, sigma=1 K and delta=1, effective bias zero.
  This is total named-group sensitivity, not unique attribution to each rate.
- [x] **Independent first-order connection:** genuine forward-mode KDM/profile
  directions contracted with fixed baseline RTTOV K and the cost cotangent
  agree with reverse VJP. Deposition dJ/dalpha=-0.03907693895509639;
  riming=-1.926767776136752e-5. Independent scalar replay gives duality errors
  4.85723e-17 and 6.77626e-21. Actual direct RTTOV differences at alpha
  epsilon .03/.1 have maximum relative errors .000102080 and .00219655,
  respectively. Signals exceed measured BT text-rounding bounds, serialized
  profiles round-trip exactly, and observed stage masks remain unchanged.
  Tapped masks do not constitute a complete internal branch atlas.
- [ ] **V3 actual auxiliaries:** pressure/reference upper profiles, geometry,
  surface and datetime retain fixture assumptions. The actual WRF/GK2A inputs
  do not close this separate auxiliary-validation boundary. No dK/dx,
  parameter identifiability, all-process or all-regime claim is made.
- [ ] **M1 actual applied ledger:** one capture-enabled binary with runtime
  capture OFF/ON completed matched 20-second runs. At t=0 and20s, all253
  numeric common fields plus Times match raw bits (254/254, zero skipped).
  The selected capture has76 samples and2 aggregates, all transport zero.
  This proves runtime-capture neutrality only, not compiler-macro neutrality
  or nonzero applied transport. Matched macro ON/OFF module objects were
  produced in isolated copies; executable linking stopped at the unaccepted
  Xcode license. No new matched executable or ten-minute run was produced.
  The original deployed host was unchanged. Kernel `den*delz` ledger closure
  is conditional on that measure; dry-air number units remain unresolved.

Reproduction artifacts (local, actual-input assets required):
`graphify-out/goal-completion-20260919/process/actual_live_control/` contains
`run_actual_live_control.py`, retained raw cases, `actual_live_control.json`,
and independent standard-library `parent_replay.py/json`. The latter recomputes
Huber cost/seed and scalar K-direction products without another live call.
M1 commands/hashes/failure evidence:
`graphify-out/goal-applied-20260907/m1/m1-compile-off-prerequisite-20260919.json`.
These local artifacts are not bundled private host assets in the public repo.

This follow-up changes evidence/checklist state only. Existing five-check CI
success is attached to source887d0ba; it is not a native rebuild on19September.
No operational f32, AD ABI, physical formula or numerical acceptance tolerance
was changed. Remaining representative process/branch, physical unit and full
budget coverage must retain their individual open status; no100% claim.

Final local artifact identities (SHA-256):
- `run_actual_live_control.py`: `249aaa27c8fa6ed046383508ce3abf3a8badd7afb222dc0ab3e9b07d62f49eac`
- `actual_live_control.json`: `ed9ef9aa1e212fdd4fab294133f10103adcb811d20852c3a0d509038df5fa024`
- `parent_replay.py`: `bfd6ba1080eef9d007da12be164ec3e0faadc575c52d78042f9330e3209a359b`
- `parent_replay.json`: `f4e612ef94ff180ba7f0dc30696f66d2e1d8039ffe900919a11d7dbe2ca4bb3c`

The standalone M1 ledger/producer artifact checks pass (2 pytest tests;
producer module also validates its transformations at import). They are
synthetic/source checks, not a completed host run.

## Diagnostic interpretation and activation branch (2026-09-19)

- [x] Reverse-AD scalar derivatives in `process_attribution` and the cold
  profile probe are now labelled as reverse AD, including report fields.
  Repeated scalar VJPs can assemble a Jacobian column, but do not constitute
  an independently executed forward-mode check. Historical numerical values
  remain valid within their recorded scope; their JVP labels are corrected.
- [x] The basic two-level sensitivity fixture's graupel ratio was still 1000.
  It now uses 450, inside [100,900] and away from the ProgB table node at 500.
  Existing tests pass with unchanged error thresholds. Older fixture results
  are not reclassified as admissible-moment measurements.
- [x] The satadj trace now retains the actual `sw_percent > 0` activation
  mask alongside `pcond != 0`, with an explicit leading mask axis and labels.
  The same computed gate feeds the activation arithmetic and diagnostic.
  A one-cell fixture at 290 K / 90000 Pa, qc=.001, nc=1e6, nccn=1e9 and
  qv=qs_water±1e-8 changes activation while both pcond masks stay nonzero.
  This formerly invisible switch is now distinguishable by existing exact
  mask comparisons. The no-CCN component path keeps its pcond-only scope.
- [ ] The remaining internal branch atlas is not exhaustively validated.
  Selected complete-evaporation and final DSD gates are addressed in the
  follow-up below; sampled endpoints do not certify every internal branch.

The conditional raw `prevp` injection probe in local
`graphify-out/goal-cross-process-20260919/` is a cut-graph derivative experiment,
not a paired, physically admissible process intervention. It cannot by itself
close representative warm-process→cold-process control coverage.


- [x] **V1 selected admissible warm→cold control route:** existing paired
  `alpha_autoconv` control, cold fixture with only initial qr changed to 3e-4,
  fixed forcing and 300 s step. Step 0 warm transfer changes the carried state;
  step 1 signed `pgdep` responds. Baseline pgdep=-1.2778163266e-8 is sublimation
  in this fixture. Forward-mode JVP=-7.204959215733750e-11 and reverse VJP=
  -7.204959215733754e-11 agree (relative 5.382e-16); independent direct differences
  at 1e-4/3e-5/1e-5/3e-6/1e-6 have maximum relative error 5.790e-6, unchanged
  tapped masks and resolved output spacing. The parent reran the artifact and
  confirmed identical scope/results. No raw-rate injection or model monkeypatch
  is used by this control experiment. This synthetic route does not establish
  a unique individual-rate causal contribution or actual-weather coverage.
  Reproducer: `graphify-out/goal-cross-process-20260919/run_process_control_rate_check.py`;
  parent result: `parent/control-replay.json` in the same directory.

Parent focused regression after activation/metadata changes: 64 passed (14.47s),
covering coordinator, sensitivity diagnostics, cold-profile and process
attribution tests. Counts overlap earlier 18/8-test selections and are not additive.

Final public warm-to-cold regression: **1 passed**, requiring nonzero
producer/target response, exact forward primal, relative JVP/VJP agreement,
two independent FD epsilons, matching tapped masks/subcycles and output
spacing. Green/Red Luna high session-end reviews completed with no remaining
blocking findings in this diff. Their bounded scope does not close the
remaining physical units, actual auxiliaries or full branch atlas.

## Complete evaporation and final DSD decisions (2026-09-19)

- [x] **Satadj complete-evaporation gate:** record the existing exact
  `pcond == -qc_pp/dtcld` predicate as the third satadj mask. It is the same
  predicate used for NC→NCCN transfer. With qv=qs_water−1e-5, qc=1e-6 versus
  1e-3, the earlier pcond/activation masks are identical while transfer is
  1e6 versus zero. At fixed branches, the analytic NC/NCCN derivatives with
  respect to input NC are (0,1) versus (1,0). The exact-saturation qc=±0 case
  separately verifies bare floating-point equality and signed zero. That
  number-without-mass boundary probe is not a populated atmospheric state.
- [x] **Final DSD decision capture:** the existing final `dsd_limiter` record
  retains actual per-species active/lambda-low/lambda-high decisions, cloud
  and ice ncmin selection, and rain/cloud absolute caps. Lambda decisions
  discarded by an outer ncmin gate are explicitly distinguishable from an
  applied snap. Absolute-cap input operands are captured before the cap;
  the recorded final state is the same object returned by the helper.
  Early slope calculations remain uninstrumented by this final-stage option.
- [ ] These selected gates do not complete the full internal branch atlas,
  numerical-domain coverage, physical number units or all-regime sensitivity.
  In particular, a recorded DSD gate is evidence of the executed numerical
  decision, not a resolution of the host/kernel number-unit contract.

Independent complete-evaporation evidence and parent replay:
`graphify-out/goal-branch-20260919/red/complete_evap_evidence.py`,
`complete-evaporation-audit.json`, and `parent_complete_evap.json`.
Parent satadj/sensitivity/local-energy selection: **13 passed** (9.77s).
The new satadj tests check exact masks, actual transfer and analytic derivatives;
no cross-switch central difference is labelled a local derivative.


Final parent combined selection: **77 passed /18 torch.jit deprecation warnings**
(14.72s), including existing analytic DSD JVP/VJP checks, exact trace/plain
products, new evaporation/DSD tests and the warm→cold control regression.
Selections overlap earlier tests and must not be summed. Green/Red review
found no blocking issue in this bounded change.

The legacy absolute-number trigger is a lambda_max back-derivation, not
`min(n,NMAX)`. The cloud trigger regression deliberately records a case where
its output exceeds its input. This validates the executed diagnostic operands;
it does not establish a physical upper-number bound or justify changing the
inherited arithmetic. Operational f32 and ABI remain untouched.


## Next bounded connection audit (2026-09-19)

- [ ] `alpha_melt` → evolved profile → BT/cost: existing melt process/state
  attribution and riming→D5 checks do not establish this observation edge.
  Reuse the existing melt fixture and fixed-K mock for a nonzero first-order
  JVP/VJP/FD regression; label it synthetic and keep live RTTOV and `dK/dx`
  separate. This is a selected coverage gap, not a demonstrated core defect.

## Selected Picons reclassification (2026-09-19)

- [x] The existing ice→snow helper now optionally records its actual ice-active,
  cold-temperature, diameter and applied gates. The caller passes the existing
  trace/step/dtcld; no reclassification arithmetic, f32 code or ABI changed.
- [x] Four direct cases cover active cold, small-diameter cold, warm and the
  explicitly invalid ni=0 moment boundary. Independent real-arithmetic diameter
  expectations are used away from the threshold; analytic d(qs_out)/d(qi_in)
  is 1 for the applied branch and 0 for the other cases. Genuine forward AD,
  reverse AD and direct differences agree. Endpoint recorded masks and forward
  primals are checked explicitly.
- [x] Equality/nextafter of the executed diameter threshold and T=t0c test
  branch semantics separately. This discontinuous reclassification does not
  have a general smooth derivative at its threshold. The legacy claim that a
  subgradient there is automatically valid has been removed.
- [x] The existing runtime regression now requires the Picons record and checks
  the actual applied mass transfer. Existing trace/plain value and JVP/VJP
  noninterference tests pass. Number is cleared, not transferred to an absent
  snow-number state; no physical number-conservation claim is made.

Parent combined selection: **78 passed /18 torch.jit deprecation warnings**
(13.73s), covering Picons, coordinator, sensitivity diagnostics, final DSD,
complete evaporation, warm→cold controls, process attribution and local energy.
The subsequent primal/mask assertion-only strengthening passed the five direct
Picons cases. Final Green/Red Luna high reviews found no blocking findings.
These overlapping counts do not add to previous runs. Full branch/regime coverage
and physical number/enthalpy contracts remain open.
