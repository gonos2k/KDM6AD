# Cross-phenomenon generalization: itemized resolution checklist

Baseline: `main` at PR #236 merge `63fb4d3a`. Prior G1–G3 results retain their
bounded status in `CHECKLIST_generalization_2026-09-24.md`. This checklist
tracks *new* cross-phenomenon work from the 2026-09-24 review. A synthetic
property test is not a native or meteorological validation. Existing legacy
outputs, failed gates, operational transport P1 and liquid observation 0/9
remain unchanged.

| ID | Status | Contract to establish | Completion evidence required |
| --- | --- | --- | --- |
| X1 | **Bounded pilot complete** | Shared reservoir, applied phase extent, paired water transfer and local latent-temperature update | Seeded isolated phase amounts through KDM's freeze cap and inline applier, plus synthetic overdraw/heat/overflow/empty-grid counterexamples; five focused tests; fixed `cpm`, same declared q basis, no phase-rate regeneration or full enthalpy claim |
| X2 | Open | Competing phase changes and other processes at one real coordinator stage | Trace request, shared limiter, applied extent, receiving reservoirs and thermal application in an active native/mixed-phase event; separate any later reclassification and cleanup |
| X3 | Open | Signed two-cell diffusion or soil-water exchange | Declare flux orientation, face ownership, equilibrium, storage upper bound and external supply; test reversal and a capacity-limited case without imposing sedimentation's `v/dz` |
| X4 | Open | Rich admissibility for each population | Add explicit population/moment IDs and species-specific floors/bounds; distinguish valid zero, inactive, undefined, missing observation and inadmissible input; test higher moments only when a corresponding distribution is declared |
| X5 | Open | Time-integrated exchange and cache validity | Sum each `flux_s × dt_s`; identify interval and restart cumulative origin; track state, geometry, parameter and optical dependencies where the phenomenon uses them |
| X6 | Open | Geometry-dependent inventory and derivative | Declare (z=Gx), test (G\delta x+(\delta G)x); use a separate synthetic remap only where a changing-grid operator exists |
| X7 | Open | Coupled operators and equilibrium | Compare same-final-time split/coupled outcomes, feedback and order; check a phenomenon-specific equilibrium, not only component conservation/nonnegativity |
| X8 | Open | Stage-aware accepted state | Distinguish internal solver stage, physical consumer input, accepted output and diagnostic-only values; check validity at the owning boundary |
| X9 | Open | Branch and event-time derivatives | Separate same-branch JVP/VJP/FD, one-sided threshold behavior, finite branch-changing increments and continuous event-time sensitivities where an event model actually exists |
| X10 | Open | Observation/analysis semantics | Specify average-before-transform, support/QC changes and analysis increment as separate terms; compare channel derivatives only on declared support |
| X11 | Open | Reusable execution/evidence specifications | Split fixed legacy case manifests from small common validators; expected events must come from an independent run plan; preserve real/derived/synthetic provenance and missing-record rejection |
| X12 | Open | Independent input-state and environment breadth | Preselect different stored meteorological conditions and held-out times; distinguish native/MPI/restart/ABI, physical time accuracy and independent radiance verification |

X1 is only a local, verification-only pilot. `harness/phase_transfer_contract.py`
does not allocate extents or change the KDM oracle, C++/Fortran, ABI, host,
limiter, QC or acceptance tolerances. Its accepted-state check applies to the
isolated before/after boundary; it does not demand positivity of every solver
internal stage. The next item is X2, not a claim that all phase changes are
coupled correctly in the live host.
