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
| V1 | Selected hydrometeor process rates → applied transfers → later rates/states: graph-connected diagnostic records, independent AD/FD, active conditions and zero interpretation. Report untested processes/regimes. | Selected chain verified; cold-regime attribution coverage remains open |
| V2 | Epsilon sweep and stage comparison: distinguish truncation, roundoff and changed recorded branches; masks/values, not just counts. Prove optional diagnostics preserve normal values and products. | Selected masks/epsilon checks verified; full internal branch coverage open |
| V3 | Pin actual observation/assets and execute a connected KDM–RTTOV objective-gradient check; record input/profile/BT/K/J/gradient, mask/aux provenance and serialization resolution. Explicitly identify fixture geometry and missing real auxiliaries. | Connected live execution implemented; FD/actual auxiliary validation partial |
| V4 | For selected actual applied transfers, evaluate residual and its directional derivative under an explicit fixed measure. Differentiate a legacy nonzero residual rather than impose a new conservation law. | Selected applied and whole-step residual derivatives verified; physical basis/enthalpy coverage open |
| V5a | Execute Python ↔ built C ABI JVP/VJP regression on `.so` and `.dylib` paths; CI must not silently skip a missing required library. | Locally verified; see evidence below |
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
- [ ] Nonzero warm→cold rate attribution across representative cold regimes.
- [ ] Internal limiter/reclassification/PSD/satadj mask and threshold atlas,
  including discontinuous topology changes; currently only selected phase masks.
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
- [ ] Resolve clear-path FD disagreement/output resolution for the selected
  directions; a live execution alone does not close this derivative gate.
- [ ] Establish usable all-sky profiles and first-order FD evidence; this run
  does not establish all-sky hydrometeor sensitivity accuracy.
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
