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
| X2 | **Bounded native event complete** | Competing phase changes and other processes at one real coordinator stage | Input-selected 39-level mp37 cell: D2/D3 raw requests, sequential cap inputs and applied mass/number, source-ordered f32 water/number/T stores, later state-update/final stages; two 40 s runs have 254/254 raw-bit-equal numeric fields at 0/20/40 s. All four D2/D3 mass·number caps are unbound and the tiny thermal increments round away in stored f32 T; cap-active native and full enthalpy generality belong to later breadth/accuracy rows |
| X3 | **Bounded synthetic pilot complete** | Signed two-cell diffusion or soil-water exchange | One declared face, positive left→right; water-depth inventory `theta*dz`; signed reversal, equal-head (zero-gradient) equilibrium of the toy law, donor and porosity capacity limits, external supply, invalid-state rejection. Thirteen synthetic tests; no operational soil/diffusion kernel or meteorological run |
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
internal stage. X2 is one selected native event, not a claim that all phase
changes or cap-binding branches are coupled correctly in the live host. Its
report and lossless token evidence are `REPORT_cross_phenomena_real_phase_2026-09-24.md`
and `native_phase_event_2026-09-24.json`; the separate 39-level fp64 oracle
profile is `real_phase_profile_2026-09-24.json`. X3's verification-only pilot is
reported in `REPORT_cross_phenomena_signed_face_2026-09-24.md`; X4 is next.
