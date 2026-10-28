# QNC donor/receiver candidate inputs, 2026-10-28

Base: `main 6c519a4b9ae7971c292df23bb174153fbe0ad8cd`, after PR #474.
The [public packet](../harness/evidence/native_qnc_candidate_inputs_2026-10-28/README.md)
extends the passive full-host QNC trace to the **54 liquid failure-layer
donors**, their six immediate receivers, and four sampled Y faces crossing
the two-tile `j=142/143` seam. The donor/receiver union has 374 cells; eight
seam sentinel cells bring the face capture to 382. The RK writer includes
those cells plus the existing QI-only target, for 383 targets. The model
continues to integrate all 234×282×39 native cells.

## Why another operand boundary was required

PR #474 recorded post-limit correction words but not the pre-limit words used
by `post = RN32(pre × scale)`. The inverse is not unique. For example, the
two f32 pre words `49D51739` and `49D5173A` at the earlier `(113,70,12)`
witness both round to original post word `46B0E9BC`, but at a two-ULP lower
scale they round to **different** words `46B0E9BA` and `46B0E9BB`.
Receiver RK inputs outside the original 54 layers were also absent. Those
missing words prevent a reliable simultaneous changed-face replay.

The new writer snapshots all selected pre-limit correction faces **after
face construction and before any limiter scale write**. It reads post-limit
faces only after every donor limiter loop has finished, before directional
tendency accumulation. The public reader checks the complete field order so
the two stages cannot be shifted by a column when decoded.

## Executed provenance and unchanged endpoint

The final packet records control and α=0.25, each tracing off/on, as **four
accepted READY40→60 s full-domain host steps**. Two preliminary α runs used
an earlier trace selection and are kept separate from this final evidence.
Within each final case the off/on ACK and checkpoint hashes match, and both
endpoints match PR #474. The forward retains `mp_physics=137`,
`no_mp_heating=0`, radiation, one rank and one thread. The isolated build
changed only `module_advect_em.o` and `solve_em.o`; the public module
interface and KDM DSO remained the same. The private executable and full
checkpoint rehashes are attributed to local receipts; public replay checks
the path-free summary and the published raw records.

## What the input join establishes

| Check in each final trace-on case | Result |
| --- | ---: |
| Captured face/state cells | 382 |
| Source-compatible face tendency → RK input | 382/382 |
| Source-compatible original RK output | 382/382 |
| PD old-buffer handoff and scalar-boundary QC/NC identity | 382/382 |
| Donor–receiver internal face incidences with equal PRE/POST/LOW words | 324/324 for each component |
| Post word explained by the recorded outward donor scale | 324/324 |
| Internal faces outgoing from the selected donor / its neighbor | 318 / 6 |
| Sampled tile-seam Y faces with equal PRE/POST/LOW words | 4/4 for each component |
| PR #474 donor operand rows / prior writer words unchanged | 54 / 8,792 |
| `(113,70,12)` pre-limit face words joined to PR #469 | 6/6 |

The seam checks include three nonzero, unscaled Y correction faces and one
face whose active limiter returns signed zero. They establish only those
sampled original face copies on one rank/two tiles. A changed-scale seam or
multi-rank halo is not certified.

No correction scale was changed in these four steps. The same α endpoint
still loses **54 fixed-M0 profiles and 378 channel cells**, so its
whole-support RTTOV cost and a second accepted assimilation remain absent.
The recorded six-face neighborhoods are sufficient to evaluate a **declared
54-donor frozen-input pilot**, with shared face values mirrored to receivers.
A coordinate-independent runtime rule would also act on other active donors
outside this capture and needs a separate whole-domain acceptance check.
The numerical face/RK ledger is not a physical particle-number budget until
the host/KDM/RTTOV NC basis is reconciled. The QI donor subnormal case is a
separate boundary path.
