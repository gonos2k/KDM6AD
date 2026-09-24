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
| X4 | **Bounded declarative pilot complete** | Rich admissibility for each population | Explicit population/phase/moment IDs, volume units and species floors/bounds wrap the prior G3 C/N validator; valid zero, inactive, undefined, conditional, inadmissible, missing and QC-rejected statuses are separate. Declared M0/M1/M2 pass only a necessary realizability inequality; no native producer/unit or full DSD certification |
| X5 | **Bounded synthetic pilot complete** | Time-integrated exchange and cache validity | Independent two-interval plan integrates each signed rate with its own duration, binds a restart checkpoint to the complete plan/revision digest and exact completed prefix, and permits intentional cached reuse only within a declared validity window and matching state/geometry/parameter/optical/unit revisions. Thirteen tests; no production radiation or restart run |
| X6 | **Bounded existing derivative + synthetic remap complete** | Geometry-dependent inventory and derivative | G3's retained density/thickness/velocity JVP–VJP–FD tests verify `δ(rho*dz*x)` including measure directions; eleven synthetic remap tests check normalization-specific fraction-weighted conservation, constant behavior, tiny overlap scale and invalid tolerances. No native changing grid or real remapper |
| X7 | **Bounded synthetic coupling complete** | Coupled operators and equilibrium | Two exact nonnegative, conservative one-way maps are compared in AB/BA order against the analytic same-final-time coupled equation; order and coupled equilibrium differ despite both component passes. Eleven synthetic tests; no KDM/host coupling or physical time-error claim |
| X8 | **Bounded declarative pilot complete** | Stage-aware accepted state | Independent event plan distinguishes solver-internal, physical-consumer-input, accepted-state and diagnostic-only roles; internal finite negatives are recorded, while negative physical-consumer/accepted values and diagnostic-to-physics links are rejected. Nine synthetic tests; actual host negativity repair remains OPEN |
| X9 | **Bounded existing KDM branch + synthetic event pilot complete** | Branch and event-time derivatives | Retained freeze-cap JVP/VJP/FD and one-sided branch checks are separate from a synthetic continuous cooling event's time derivative; an exact kink has code-selected tangent 1, left/right differences 1/0, centered 1/2, and finite crossing increment is not called a local JVP. No KDM continuous-event/saltation model |
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
reported in `REPORT_cross_phenomena_signed_face_2026-09-24.md`. X4's
declarative adapter is `REPORT_cross_phenomena_validity_2026-09-24.md`.
X5's interval/cache pilot is `REPORT_cross_phenomena_time_cache_2026-09-24.md`;
X6's existing derivative/new synthetic remap evidence is
`REPORT_cross_phenomena_geometry_2026-09-24.md`.
X7's noncommuting synthetic pair is `REPORT_cross_phenomena_coupling_2026-09-24.md`;
X8's stage-role pilot is `REPORT_cross_phenomena_stage_validity_2026-09-24.md`;
X9's branch/event timing distinction is
`REPORT_cross_phenomena_event_derivatives_2026-09-24.md`; X10 is next.
