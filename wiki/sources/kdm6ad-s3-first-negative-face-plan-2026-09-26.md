---
title: KDM6AD S3 first-negative face-event plan 2026-09-26
type: source
date: 2026-09-26
---
# KDM6AD S3 first-negative face-event plan — 2026-09-26

The G2 whole-owned-grid scans found the first sampled QN transition at step 2,
RK1, QNCLOUD `(i,k,j)=(46,1,2)` in both mp237 trajectories. Those values are
intermediate Runge–Kutta states. The ordinary `advect_scalar` path runs at RK1;
the PD limiter is a final-RK path. `flow_dep_bdy` can copy a later negative
value to an edge, so a boundary receiver is not itself the producer.

The source-pinned plan selects the RK1 cell for a one-rank/one-thread/one-tile
capture. Its parser validates exact G2 tile census and candidate ownership,
then requires raw face flux, map metrics, RK coefficients and measured tendency
and store bits before attempting source-order REAL4 replay. It reports an
axis-pair numerator prefix after the source's grouped Y→X→Z differences and
checks the fused RK store against its observed word. The event's native build
and history hashes are not externally receipt-pinned yet, so the raw replay
remains `UNVERIFIED_RECEIPT`; it is not a physical cause or conservation claim.
Accepted STEP_ACCEPTED states receive classification only because microphysics
and boundary changes intervene after RK3. No physical particle-number
interpretation or cause is established; S3 remains open.

Evidence and implementation: `harness/evidence/REPORT_number_face_flux_2026-09-24.md`,
`harness/evidence/REPORT_negative_number_origin_2026-09-24.md`,
`harness/evidence/REPORT_S3_face_budget_backoff_candidate_2026-09-25.md`, and
`harness/evidence/PLAN_S3_first_accepted_state_face_event_2026-09-26.md`. The
G4 restart and surface reports describe separate trajectories, not QN
negativity.
