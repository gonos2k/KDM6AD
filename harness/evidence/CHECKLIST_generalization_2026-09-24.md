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
| G3.4 | Demonstrated, isolated | Derivatives of representation/geometry transformations | Existing conservative kernel generates paired transfers matching independent inventory recurrence; state/rho/dz/velocity JVP/VJP/FD include weight derivatives, not full host AD |
| G4.1 | Open | Execution ownership across MPI/tile decompositions | Unique complete global ownership; separate halos and physical boundaries; preserve fixed single-rank regression |
| G4.2 | Open | Restart first handoff and cumulative transport | Compare equal final physical time with uninterrupted run; no stale or double normalization/export |
| G4.3 | Open | Held-out meteorological inputs | Preselect native columns/time by input properties, not passing BT/cost; report inactive, liquid, mixed/ice and surface-export coverage |
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
