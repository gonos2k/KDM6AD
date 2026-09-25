# Generalization review: resolution checklist

Baseline review: PR233 merge `cff7c9b2`. Follow-ups: G1 PR234 and G2 PR235.
Each item closes only its stated completion condition. A passed replay, synthetic
property or isolated native experiment does not authorize production adoption.
Order requested: G3 physical contracts, then G4 execution/representativeness,
with a separate PR for each. Prior captures and failed gates remain intact.

| ID | Status | Finding / remaining work | Completion condition / current evidence |
| --- | --- | --- | --- |
| G1.1 | Demonstrated, bounded | Dynamic velocity producer→normalization→consumer, differing column schedules | PR234 synthetic dynamic ice chain checks fresh generations, exactly-once normalization and finished-column inactivity |
| G1.2 | Open | Native actual second/subsequent ice substeps, main reslope and restart | Capture an executed n≥2 path and link every consumer to its latest producer; existing native census is all mstep=1 |
| G1.3 | Demonstrated, bounded | Selected vs consumed velocity differs | PR234 detects C=0.8→2.4 insufficient initial budget; no unapproved silent reselection |
| G2.1 | Demonstrated, bounded | Upstream PD face/limiter budget→RK negatives | PR235 pairs all 384 limited faces, 192 directional stores and 256 host stores in two retained trajectories |
| G2.2 | Demonstrated, bounded | Final-cell selection misses transient negatives | PR235 scans owned domain at call boundaries in original and normalized trajectories; examples capped at eight, events inside calls unmeasured |
| G2.3 | Open | Executed final-stage positivity and conservation, all boundary branches | Design and validate a common face budget through final floating-point update, boundary supply and host application; no blanket clipping |
| G3.1 | Demonstrated, conditional | Recompute physical process under consistent number/mass representations | G3 actual DSD/accretion regeneration and independent volume equation pass on the declared domain; near-EPS floor mismatch explicitly remains outside den=1 invariance |
| G3.2 | Partial; native open | Admissible moment pairs and inactive producer outputs | Explicit volume-pair validity and masked consumption tested; native ProgB conditional INTENT(OUT) read still needs policy and execution validation |
| G3.3 | Open | Native-host physical number basis and threshold policy | Resolve Registry/kernel conflict and verify entry, producers, applied transfer and return in one declared physical basis; no default density factor inserted by assumption |
| G3.4 | Demonstrated, isolated | Derivatives of representation/geometry transformations | The analysis-only, opt-in conservative ice function generates paired transfers matching an independent inventory recurrence; state/rho/dz/velocity JVP/VJP/FD include weight derivatives. Operational legacy/native transfer remains open |
| G4.1 | Ownership demonstrated; trajectory failure open | Execution ownership across MPI/tile decompositions | G4 complete rank-territory/consumer census passes; 1×2 matches serial, 2×1 differs in 71 numeric fields at 40 s. Localize first upstream i-seam divergence before approval |
| G4.2 | Bounded producer localized; cause open | Restart first handoff and cumulative transport | Checkpoint matches parent/child saved common fields 235/235. Same shadow binary reproduces both retained G4 histories bitwise; five preselected profiles match through `phy_prep` and radiation, then surface outputs first differ for clear/ice/rain. Surface inputs are incomplete and five profiles cannot establish a full-domain first divergence or causal source; add missing surface operands and trace their producer. |
| G4.3 | Demonstrated, bounded spatial sample | Held-out meteorological inputs | Five native input-property columns preselected before comparisons; full profiles retained. Samples miss the x-decomposition domain failure, so full-domain checks remain mandatory; no new time/observation validation |
| G4.4 | Open | Physical time convergence | Separate normalized fixed-speed, reslope column and full host experiments; compare distribution, export, sizes, thermodynamics and branches |
| AD.1 | Open | Full normalized state-dependent AD/ABI | Include actual velocity/size paths and declared controls; distinguish same-branch derivatives from threshold-crossing increments |
| SRC.1 | Open | Historical source certification | Preserve failed old pin; independently authenticate new approved source/build, not replace SHA to obtain green |
| OBS.1 | Open | Independent physical/radiative accuracy | Resolve optical input semantics separately from solver accuracy; inherited liquid acceptance remains 0/9, not a newly measured normalized result |

Completed evidence is not reopened by later scope expansion. New defects and
counterexamples are recorded against the corresponding item. No aggregate
percentage is assigned to the project. Detailed results and actual test/run
counts belong in each follow-up report and PR.

G3 detailed evidence: `REPORT_moment_contract_2026-09-24.md` and
`moment_contract_2026-09-24.json`. No operational unit conversion or native
inactive-output initialization was introduced to turn open rows into passes.

G3 validation: 32 new + 29 retained focused tests passed on Python 3.12;
Green/Red final review found no remaining blocker within the declared scope.
Graphify code and semantic updates completed with the existing eight
edge-metadata warnings; no full private-host graph coverage is claimed.

G4 evidence: `REPORT_native_execution_2026-09-24.md` and
`native_execution_2026-09-24.json` plus complete compressed rank logs. Seven
native runs preserve within-configuration outputs. The x-decomposition and
restart trajectory failures are **not resolved** by a complete execution census.
Next actionable measurements: pre-KDM owned geometry/forcing at the i seam,
and complete the bounded restart producer trace beyond its first surface
output difference. Keep the measured
failures and source attribution; do not relax their comparison to close rows.

G4.2 bounded restart evidence: `REPORT_g4_restart_checkpoint_2026-09-25.md`,
`g4_restart_shadow_runs_2026-09-25.json`, and the compressed step-2 traces.
The comparison rules out a mismatch in common saved checkpoint fields and
localizes the first observed selected-profile output difference to the surface
driver, but does not capture its complete input dependency set or establish a
domain-wide earliest cause. The restart trajectory gate remains open.

G4 validation: 67 focused checks passed (51 new, 16 retained). Final Green/Red
review closed masked-input and metadata-consistency counterexamples; no reviewed
blocker remains for the evidence/tooling PR. That review does not close the
measured x-decomposition or restart trajectory failures. Graphify code and
focused semantic refresh retains the eight existing edge-metadata warnings.
