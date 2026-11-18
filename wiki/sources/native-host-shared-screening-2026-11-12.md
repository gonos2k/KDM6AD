---
title: Same-column stage and derivative screening
type: source
date: 2026-11-12
---

# Same-column stage and derivative screening

The [batch report](../../docs/NATIVE_HOST_SHARED_SCREENING_20261112.md) and [replay packet](../../harness/evidence/native_host_batch3_shared_2026-11-12/README.md) analyze the exact-widened input of the [[native-host-column-f32-2026-11-11|selected host f32 column]]. It compares saved f32 and f64 full-stage captures at one input, then screens three f64 centers along state and independent forcing directions. Installed Legacy f64 value output and isolated capture-DSO output match in all recorded value calls. The installed DSO did not export joint state+forcing AD, so those tangents and adjoints belong to the isolated DSO only.

At native level 12 the first *recorded* number-field difference is `fd_satadj_inner.ncact_raw`; at level 16 the first recorded NR mismatch is `d1_melt_consumer.nr_after`. The recorded `d1_postmelt_progb` Boolean comparison differs by dtype path, but no counterfactual calculation attributes the final mismatch to that branch. The lower TH interior point has equal NC16 words through the recorded stage fields at its sampled endpoints. Stage order identifies where a difference was first **observed**, not the earliest causal operation.

The first f64 screening step crosses recorded masks in two PII endpoints. A bounded smaller-step follow-up keeps recorded masks and schedules stable but does not certify hidden-branch stability or derivative accuracy. NCCN directions are unresolved in the archived outputs, and positive NC perturbations show an NC16 output plateau across three step scales. The screening leaves these cases open rather than labeling JVP agreement or failure.

The packet also recomputes a 39-layer conditional water inventory from the archived f32 B=1 input and output words. Its residual is approximately `−0.4662958822 kg m⁻²` under an **unverified** dry-air density and mixing-ratio assumption. It omits host cleanup and transport, and does not establish conservation or physical units. The future process ledger must record applied departure and arrival amounts, surface export, total f64 precipitation, live operand tangents, and the host measure before scientific or physical-unit status can change from `INCONCLUSIVE`.
