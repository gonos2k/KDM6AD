# Differentiable KDM → GK2A–RTTOV: resolution checklist

Baseline: `bb04e52b4aca8028257e1529fa7005a61c2f54c7` (PR #215).
Scope agreed with the user on 2026-09-06: mathematical, engineering,
meteorological and numerical validation of differentiable KDM, including
hydrometeor process interactions, through GK2A–RTTOV data assimilation.
Forecast skill, unattended cycling and a full host-model adjoint are not gates
for this task. Team work uses Luna (`gpt-5.6-luna`), reasoning `high`.

Follow-up review on merged main `ca23480b` is tracked in
[the ordered PR #215 resolution checklist](CHECKLIST_pr215_review_2026-09-19.md).
V5a execution evidence is retained, but its former NaN-blind comparison and
unbounded allowed divergence required gate correction; fresh CI is tracked
there separately from prior successful runs.

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
  auxiliary inputs are required. These historical runs were wiring-only for
  those auxiliaries. The PR #218-baseline follow-up below applies actual WRF
  coordinates/skin/near-surface fields and UTC; full geometry remains open.

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
- [ ] These historical runs used fixture geometry/surface/time. The later partial
  substitution applies actual coordinates, skin/near-surface fields and UTC;
  viewing/solar angles, upper/gas assumptions and source-build identity retain
  their declared limits. External K evidence remains first-order only.

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
- [x] **Independent first-order connection (before partial auxiliary substitution):**
  The following values belong to the earlier reference-auxiliary experiment.
  Genuine forward-mode KDM/profile
  directions contracted with fixed baseline RTTOV K and the cost cotangent
  agree with reverse VJP. Deposition dJ/dalpha=-0.03907693895509639;
  riming=-1.926767776136752e-5. Independent scalar replay gives duality errors
  4.85723e-17 and 6.77626e-21. Actual direct RTTOV differences at alpha
  epsilon .03/.1 have maximum relative errors .000102080 and .00219655,
  respectively. Signals exceed measured BT text-rounding bounds, serialized
  profiles round-trip exactly, and observed stage masks remain unchanged.
  Tapped masks do not constitute a complete internal branch atlas.
- [x] **V3 partial actual-auxiliary follow-up (PR #218 baseline):** actual WRF
  coordinates/elevation, skin and near-surface T/Q/winds, and slot UTC were
  applied in ten live RTTOV evaluations. Applied auxiliary text hashes match
  across all paired runs. Deposition/riming maximum AD–FD relative differences
  are 0.0141%/0.1501%, with the previous acceptance rule unchanged. Requested
  values and six-decimal applied values are distinguished. See
  [partial actual-auxiliary report](REPORT_partial_actual_aux_2026-09-19.md).
- [ ] **V3 full actual auxiliaries:** viewing/solar angles and upper T/Q/gases
  remain reference or unverified. The fixed pressure grid is an interpolation
  target, not evidence of actual upper-atmosphere conditions. The follow-up is
  a mixed actual/reference operator; it does not close full actual-condition
  validation. No dK/dx, identifiability, all-process or all-regime claim is made.
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

- [x] Selected synthetic `alpha_melt` → evolved T/Q profile → fixed-K BT/cost:
  `test_melt_profile_bt_cost.py` verifies nonzero genuine forward AD, reverse
  bridge AD and two resolved direct differences at unchanged tapped topology.
  See R5 in the ordered PR215 follow-up checklist. Live RTTOV/cloud-K and
  `dK/dx` coverage are not established by this clear-sky synthetic case.

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

## PR #216 follow-up tracking — 2026-09-19

The ordered [follow-up checklist](CHECKLIST_pr216_review_2026-09-19.md)
tracks final-output resolution independent of derivative agreement, same-alpha
primal equality, asymmetric channelwise melt sensitivities, and the selected
freeze CCN-return discrepancy. Previously closed checks remain closed. Actual
auxiliaries, physical number units, nonzero M1 transport and sensitivity
convergence retain their existing open evidence requirements.

## PR #217 follow-up — rate resolution

The [ordered rate-resolution checklist](CHECKLIST_pr217_review_2026-09-19.md)
records consumer-level rejection of one-spacing nonzero rate responses,
unchanged existing 18-case products/classifications, report propagation and
the selected post-evaporation zero-NC/nonzero-CCN sensitivity transfer.
Representative applied-process coverage and physical-unit/actual-input gates
remain open.

## Native 5 km model-level requirement (2026-09-19)

User clarification: use the current model, without external model/reanalysis
inputs. Native horizontal columns and vertical levels define the calculation.
Earlier fixture-grid and bottom-only PSFC substitution results are bounded
historical comparisons, not native-level validation completion.

- [x] Pin selected column45577's 39 native fp64 P+PB centres and 40 interfaces
  replayed from the host P8W formula. These interleave without midpoint replacement;
  stored P_HYD is a separate fp32 cross-check, not the fp64 forcing coordinate.
- [x] Pass native T/Q/hydrometeors and explicit P/P_HALF through the input/writer
  boundary. The writer honors p.txt as the actual RTTOV driver does; native target
  equals model source, and reference upper T/Q blending is disabled.
- [x] Identify model-top/gas treatment from the installed RTTOV: positive native
  top is accepted, upper interpolation is internal, and disabled external gas-file
  inputs use coefficient backgrounds. This is a declared operator assumption,
  not verification of actual atmosphere above the model top or measured gases.
- [x] Selected native-level first-order validation: ten live calls, two controls
  and two epsilons; seven fixed jointly usable IR channels. WV063/WV069 retain
  bit15 quality failure, with no QC relaxation. Maximum AD/FD relative differences
  0.5263% deposition / 0.2314% riming; JVP/VJP agree. See
  [native-model report](REPORT_native_model_levels_2026-09-19.md).
- [ ] Broader representative native model columns/processes and actual satellite
  view-angle provenance remain separate from this selected directional result.
- [ ] Resolve host/kernel number units and measure nonzero applied transport on
  this model. Historical recovered-flux proxies and zero M1 capture do not close
  this requirement; source-matched instrumented executable remains unavailable.


### PR219 review follow-up — pressure coordinate contract

- [x] Confirm absent-P default against local RTTOV v14 consumer source: top
  interface floored at 1e-12 hPa, then arithmetic means. Replace the historical
  geometric Python fallback; retained historical results are not recomputed or
  relabelled as correct-coordinate evidence.
- [x] Keep explicit model P authoritative. With p.txt present, require exact
  P/P_HALF witness equality; reject a one-ULP drift. Legacy no-P comparisons
  retain compatibility tolerance. Optional P omission is not a native-grid
  certification; the selected native runner supplies and checks both vectors.
- [x] Check ten retained native cases against the stricter contract without
  rerunning their radiative calculation. Writer suite: 69 passed, including
  fixed arithmetic expectations, top-floor behavior, and explicit-grid drift.
- [ ] Directly expose/compare RTTOV's internal consumed vectors if executable
  provenance or profile construction changes. Current evidence combines exact
  input files with local reader/population source, not a new internal dump.
- [ ] Resolve actual viewing-angle provenance from existing local GK2A navigation;
  a nominal orbit calculation must remain labelled as an assumption.
- [ ] Repeat selected native sensitivity with justified viewing angles and retain
  channel-wise derivatives; extend representative active process cases separately.
- [ ] Quantify upper-background and P8W-versus-PSFC boundary assumptions separately.
  Particle-number units/nonzero applied transport and sensitivity convergence
  remain open. This fallback correction does not close those scientific items.

- [x] CI interpreter policy: Python 3.12 only in all four setup-python entries;
  automatic Python version matrices are on hold. Both OS native gates remain.
  Prior Python 3.11 CI results are not evidence for the changed interpreter.
- [x] Local scoped validation: writer 69 passed; profile/cloud/input/melt 59
  passed (18 existing TorchScript deprecation warnings). These local Python
  3.10 runs are distinct from pending Python 3.12 CI. Workflow syntax passes
  actionlint with shellcheck disabled; existing shellcheck warnings are separate.


### PR220 follow-up — scene-anchor view, not exact pixel navigation

- [x] Preserve closed pressure findings. PR220 merge e2854f80 has all five CI checks successful.
- [x] Inventory existing KO/FD same-slot navigation. FD has first/centre/last
  spacecraft ECEF anchors; KO lacks per-pixel navigation. No external model data.
- [x] Derive centre-anchor view at the same native column, with independent
  ECEF position check, explicit RTTOV azimuth convention and first/last angle
  comparisons. No undocumented scan-time interpolation.
- [x] Repeat native-layer deposition/riming with fixed paired geometry, unchanged
  QC/cost, and record per-channel JVP/VJP/direct FD. Ten calls, seven usable IR;
  cost maximum differences 0.527615% / 0.126333%; channel maxima
  0.553005% / 0.646217%. See REPORT_scene_anchor_view_2026-09-19.md.
- [ ] Exact target-pixel acquisition-time/view-vector mapping remains unavailable
  in inspected local files. Scene-anchor-derived geometry is not a per-pixel
  measured-angle completion claim.
- [ ] Model-top/gas/bottom-boundary effects, broader active processes, physical
  number units/nonzero transport, and timestep sensitivity remain separate.

### PR221 follow-up — reproducible endpoints and anchor comparison

- [x] Publish ECEF anchors, ellipsoid, target coordinates, applied angles and
  raw channel/epsilon BT strings in scene_anchor_precision_2026-09-19.json.
  Standalone Python 3.12 replay checks three geometries and 28 comparisons.
- [x] Separate observed agreement from text-rounding-aware 5% evidence: 28/28
  observed, 27/28 stronger conditions. Riming WV073 epsilon .03 remains limited;
  epsilon .1 satisfies the text-only bound. No tolerance/QC changes.
- [x] Establish shared alpha-zero baseline (44/44 files identical), reuse both
  profile tangents, evaluate first/last direct/K and recompute each Huber seed.
  Two valid calls after two explicitly rejected auxiliary-key replacement attempts.
  Channel QC unchanged; see REPORT_anchor_precision_2026-09-19.md.
- [ ] Exact pixel navigation, upper/gas/bottom assumptions, representative active
  paths, physical number units/nonzero applied transport and timestep convergence
  remain open. Anchor spread is not a navigation uncertainty bound.

### PR222 follow-up — same-model PSFC bottom assumption

- [x] Read PSFC from the same pinned WRF column; independently prove only the
  final P_HALF scalar changes by +5.91021293 Pa. Keep all 39 native P values,
  other interfaces and inputs unchanged; strict interleaving passes.
- [x] One new direct/K call reuses both retained process tangents, recomputes
  Huber seeds and preserves seven-channel QC. Public raw BT/gradient/seed evidence
  is in psfc_bottom_comparison_2026-09-19.json and REPORT_psfc_bottom_2026-09-19.md.
- [x] Separate BT text spacing from internal/K precision: all seven BT changes
  exceed the 1e-9 K text-difference bound; no total K-error claim or new FD check.
- [ ] General surface-boundary choice, upper/gas effects, exact pixel navigation,
  representative active paths, number units/nonzero transport and timestep
  convergence remain open. This is one selected bottom-assumption measurement.

### PR223 follow-up — layer contributions and active liquid accretion

- [x] Publish retained layer/field K tokens and fixed tangents with a Python 3.12
  standard-library replay. Fourteen channel-gradient boundary differences exceed
  conditional K-text rounding bounds; this is not a total numerical error bound.
- [x] Select an active warm accretion column from the existing 5 km forecast by
  declared state/rate criteria. Verify applied rates, native state/profile
  JVP/VJP/FD and selected mass-transfer directional identities. No external
  atmospheric data or production physics change.
- [x] Execute five native RTTOV endpoints after two recorded setup failures.
  All nine observation-clean IR channels have quality 32768 (Delta-Eddington
  extinction limit); preserve raw channel diagnostics and the empty cost mask.
- [ ] Accepted liquid-process observation/cost sensitivity remains open. Zero
  masked cost is not a success. Physical number units, nonzero transport,
  timestep convergence, upper/gas assumptions and exact pixel timing remain open.

See CHECKLIST_pr223_followup_2026-09-19.md and its three linked reports.

### PR224 follow-up — extinction definition and blocked layer measurement

- [x] Correct the public nine-channel JVP/VJP report exponent to 5.4210e-20.
- [x] Trace retained cloud input units, diameter conversion and installed
  pre-delta extinction cap (20 km^-1), separately from optical-depth cap 30.
- [ ] Measure exact channel/layer/combination cap masks and component causes.
  Retained outputs omit them; isolated diagnostic executable linking failed.
  Zero new diagnostic runs; no QC/solver/input changes or license acceptance.

See CHECKLIST_pr224_followup_2026-09-20.md. The existing QC-excluded result
and all broader physical-unit/transport/convergence limitations remain open.

### PR225 follow-up — measured cap arrays and column weights

- [x] Resolve the isolated link path using installed CLT ld by absolute path;
  preserve installed binaries, original inputs, QC and license state.
- [x] Verify uninstrumented baseline and five instrumented endpoints against
  archived direct/K outputs: byte-identical in all five compared files.
- [x] Measure exact cap predicates and components: 62 active rows, identical
  endpoint masks; publish column mappings/weights and selected tangent overlap.
- [ ] The nine IR observations remain QC-excluded. This closes selected cap
  diagnosis, not accepted BT/cost validation or full derivative attribution.

See CHECKLIST_pr225_followup_2026-09-20.md and REPORT_extinction_layers_2026-09-20.md.

## PR227 follow-up: fixed-column optical derivative boundary

The file-completeness P2 and selected cap-location diagnosis remain closed.
See `CHECKLIST_radiance_boundary_2026-09-20.md` and
`REPORT_radiance_boundary_2026-09-20.md` for five isolated boundary captures,
exact retained-output comparisons, and baseline-adjoint × finite-width optical
contractions. Maximum differences from retained channel JVPs are 0.0154858%
(epsilon 0.03) and 0.171884% (epsilon 0.1). These measurements identify surviving
SSA/asymmetry responses; they are not genuine intermediate JVPs or independent
radiative-accuracy evidence. Existing QC still excludes all nine liquid-case IR
channels. Number-unit reconciliation, transport and timestep convergence remain
open; no production physics or QC change is made.

## PR228 follow-up: conditional number-to-size contract

One offline baseline reproduces the retained native 39-layer liquid profile.
Public operands now distinguish raw-number execution, number-only conversion,
and a coherent dry-moment pair. At the three accretion-active layers, the latter
changes diagnostic diameters by +9.50762%, +5.67688% and +4.12389%; seven other
cloud-active layers retain the lower diameter limit. These are conditional
interpretation effects, not corrected model trajectories or new BT derivatives.
See `CHECKLIST_number_size_2026-09-20.md` and `REPORT_number_size_2026-09-20.md`.
Physical number-unit reconciliation, independent radiation accuracy, nonzero
transport and timestep convergence remain open. No new RTTOV run, production
change or accepted liquid observation is added.

### PR229 follow-up — selected number boundary (2026-09-20)

- [x] Correct inactive-only cloud-slope docstring; executable physics unchanged.
- [x] One offline baseline on existing column 35711: capture producer operands,
  applied rates and actual state-update boundaries; replay complete selected nc
  budgets including self-collection and the twice-applied naacw term.
- [x] Conditional dry-mass/volume ledger, inverse and density-direction witnesses;
  synthetic paired transfer is explicitly not native sedimentation evidence.
- [ ] Physical number basis, matched native-host measurement and actual nonzero
  transport remain open. Independent radiation accuracy and liquid BT/cost
  approval remain open (0/9). No new RTTOV calls.

See `REPORT_number_boundary_2026-09-20.md` and its focused checklist/evidence.

### PR230 follow-up — actual mp37 native number boundaries (2026-09-20)

- [x] Existing 5 km inputs, fixed column 35711 and original 39 layers: complete
  isolated control/capture runs, 40 s at dt=20 s, np1 and one thread.
- [x] Actual entry/process/rate-update/return capture; nc/nr returned values
  match history. All 254 common numeric variables match raw bits at 0/20/40 s.
- [x] Actual nonzero rain/ice internal departures and arrivals measured at step 2.
  This supersedes the earlier absence of native measurement for this mp37 scope.
- [ ] Physical conservation is **not** approved: ice upper post-state caps the
  next cell's incoming transfer, producing a large measured interface mismatch.
  Number-unit basis, corrected paired transfers, mp137 ABI, other species/mass,
  nonzero surface export and time-step convergence remain open.
- [ ] Independent radiation accuracy and liquid BT/cost approval remain open
  (0/9); zero new RTTOV calls. No operational physics/ABI/QC/CI changes.

See `REPORT_native_number_2026-09-20.md`, its checklist and full public capture.

### PR231 follow-up — existing conservative ice path (2026-09-20)

The measured legacy ice transfer mismatch is a **P1 OPEN operational task**;
unknown physical number units do not excuse positive departure with zero arrival.
One additional noninterfering native run captures the original binary64 work
coefficients and binary32 stores. Existing C++ legacy reproduces all 78 native
ni outputs; existing Python/C++ promoted kernels agree. The conservative local
substep closes the declared dz-number/rho-dz-mass budgets, with mixed-f32 number
interface residual about 3.35e-9 relatively. This validates the existing opt-in
alternative on these operands, not an operational fix or a full host trajectory.
See `REPORT_native_ice_transfer_2026-09-20.md` and its focused checklist.


### PR232 follow-up — formal time refinement and layer JVP (2026-09-20)

- [x] Reuse the same captured 39-layer operands with fixed work and metrics;
  compare m=1..128 at the same numerical final interval, including a surface
  inventory counter and both mass/number distribution and total closure.
- [x] Cross-check a matrix exponential with a positive Poisson series and known
  two-cell solution. Check one nonuniform layer direction using true
  `torch.func.jvp`, VJP and independent centered differences.
- [x] Audit the coefficient handoff: first ice work is raw terminal velocity
  after a main-loop reslope overwrite, not an established inverse-time rate.
  The fixed numeric-coefficient curves are formal operator diagnostics;
  `dt*work` is not a physical Courant number at this handoff.
- [ ] Operational transfer P1, raw handoff normalization, physical number basis
  and full coupled time accuracy remain open. No default or QC is changed;
  liquid observation approval remains 0/9.

See `REPORT_ice_time_accuracy_2026-09-20.md`.

### Isolated mp237 trajectory follow-up (2026-09-21)

- [x] Existing conservative Fortran variant on the same 5-km input, 39 layers,
  40-s window with dt=20; current module compiled separately, host dependencies
  reused. Not mp337 or C ABI validation.
- [x] Control/capture have identical complete history bytes, 253 numeric fields
  and Times at 0/20/40 s. Initial legacy state matches; later differences are
  described, not required to match.
- [x] Capture 156 ice before/after records; measured capped departures pair with
  adjacent upper-departure records. Source-ordered receiver reconstruction
  reproduces all qi/ni post stores; conditional f32 transfer residuals retained.
- [ ] Whole-host positivity: small negative number history values in both
  legacy and conservative tracks at 40 s; origin not localized by this capture.
- [ ] Operational P1, physical number basis, raw ice work normalization, coupled
  time convergence and representative number surface export remain open.

Three completed runs (one initial-frame-only exploratory run, two accepted
three-frame runs) and two MPI startup failures are distinguished. Historical
source SHA pin fails while four permitted structural clusters match; no gate
was weakened. See `REPORT_conservative_native_2026-09-21.md`.

Final Green/Red reviews found no blocking arithmetic/scope issues after adding
fail-closed run-validity and source-strip evidence checks. Focused Python 3.12
checks: 4 formal-reference/layer-AD tests and 8 native-evidence tests. Graphify
AST and focused semantic refresh completed; eight pre-existing graph metadata
warnings remain, and full graph coverage is not claimed.


### PR233 follow-up — normalization and negative-number origin (2026-09-24)

- [x] Preserve legacy/original mp237. In an isolated source copy, add only the
  two missing ice-slot divisions after main reslope; leave initial mstep and
  later ice normalization unchanged. Execute normalized control/capture at the
  same 5-km, 39-layer, 40-s input; all 253 numeric fields plus Times match.
- [x] Record 702 coefficient/state rows. All 234 paired raw/dz transitions and
  78 first-ice handoffs replay. Selected mstep is 1: later normalization is
  measured preparation, not an executed n>=2 consumer or coupled time convergence.
- [x] Independently trace original mp237's 11 final negative edge cells and their
  11 donors. Capture 1188 records; replay 132 RK and 44 PD stores with the archived
  host object's fused arithmetic. Inner RK negatives are copied by outflow BC;
  microphysics changes inner cells while excluding the specified edge strip.
- [x] Both read-only negative traces retain original mp237 history bytes.
  No boundary clipping, transport setting or KDM strict-FP policy is changed.
- [x] Locate matching historical pinned source and the exact one-line rhox
  deletion leading to current source. Record rationale and approval gap.
- [ ] Historical pin certification remains FAILED; no SHA replacement.
- [ ] Operational P1/default adoption, physical number basis, full normalized
  AD/ABI behavior, upstream advective flux/limiter cause, whole-host positivity,
  coupled time accuracy and independent radiation accuracy remain open.
  Liquid observation approval remains 0/9.

See `REPORT_ice_normalization_2026-09-24.md`,
`REPORT_negative_number_origin_2026-09-24.md` and the paired public JSON/replayers.
Focused Python 3.12 tests: 8 normalization + 7 negative-trace tests passed; both
replayers reject Python -O. Native executions and public arithmetic tests are
separate evidence.

Final Green/Red review approved the scoped arithmetic and evidence. Graphify
code and focused semantic updates completed; eight pre-existing missing-edge
metadata warnings remain, with no claim of complete graph coverage.
