# Representative moment boundaries after PR #467

Base: `main 243d2f646d34d5de2967c709ca26d25e873085e7` (PR #467).
This is a diagnostic comparison of the already rejected alpha=0.25 candidate,
not a newly accepted analysis or a changed limiter rule. Public raw records,
arithmetic and the path-free native run receipt are in the
[representative packet](../harness/evidence/native_qnc_representative_boundaries_2026-10-28/README.md).

## What the additional host runs establish

Four independent READY40→60 s full-domain steps compare control/alpha with
the new recorder off/on. The PR #465 donor-scale variant is present in all
four. The only new archive member is a `solve_em.o` containing records at four
native mass layers. Each case has the same endpoint checkpoint SHA-256 and
application ACK with recording off/on, and each endpoint also matches PR #465.
The forward uses `mp_physics=137`, `no_mp_heating=0`, radiation on, one MPI rank
and one thread. `use_q_diabatic=0` omits the separate RK water-tendency
correction; it does not turn off forward KDM water changes or latent heating.

| Native layer | First recorded NC-bit difference | First recorded moment-pair validity split | KDM input → output in alpha |
| --- | --- | --- | --- |
| `(153,111,4)` | RK2 after | RK3 after: control +0.587423801, alpha −0.305852234 | −0.305852234 → 0 with QC positive |
| `(113,70,12)` | RK2 after | RK3 after: control +0.001692894, alpha −0.006369510 | −0.006369510 → 0 with QC positive |
| `(155,120,15)` | RK2 after | RK3 after: control +0.010239942, alpha −0.003562272 | −0.003562272 → 0 with QC positive |
| `(1,168,33)` | NC equal | QI differs by RK3 before: control 0, alpha `00000002`, NI 0 | QI word unchanged through KDM and finish |

Both cases have negative NC after RK1 at the three liquid layers. The first
recorded NC difference occurs later, after RK2, and the final positive/negative
split occurs after RK3. At RK3, the recorded numerator inputs are bitwise
equal except `ADVECT_TEND`; the reconstructed exact-real numerator from saved
binary32 operands is positive in control and negative in alpha. `MU_NEW`
differs but contributes to a positive denominator. The saved-operand
exact-real calculation independently checks the **observed RK3 sign split**;
it does not identify which transport flux or limiter operation produced the
different `ADVECT_TEND`, or replay the compiled binary32 operation order.

For the ice layer, the previous RK2-after record has QI zero in both cases;
the alpha subnormal positive word is already present at RK3-before. The first
different operation lies between those sampled boundaries. The target-only
QNC donor-scale change does not directly write QI at this layer; this QI
result needs its own process trace.

`POST_FINISH` words match the same-layer checkpoint witnesses from PR #466
and #467. The checkpoint SHA identity means the earlier whole-domain M0
classification still applies: **54 candidate profiles and 378 channel cells
remain invalid**. No full-support candidate cost, accepted update or second
assimilation exists.

## Checklist from this measurement

| Item | State | Next evidence |
| --- | --- | --- |
| Same-layer control/candidate endpoint values | Complete in PR #467 | 54 liquid layers have control QC>0 and small positive NC; the ice layer has control QI=0. |
| Representative stage boundary and recording noninterference | Complete here | Four off/on host runs; raw-bit stage traces and checkpoint joins. |
| Liquid `ADVECT_TEND` producer and applied limiter for these coordinates | Open | Selective flux and shared-face evidence at the first differing RK input, then connect applied terms to the RK3 numerator. |
| Ice subnormal QI creation between RK2 and RK3 | Open | QI update/rounding record within the bracket; treat separately from liquid NC. |
| General donor/receiver correction | Open | Verify positivity and corresponding mass/number budgets beyond one diagnostic cell; preserve shared-face application. |
| Entire fixed M0 and RTTOV cost | Open | Obtain a fully admissible candidate, then evaluate the direct checkpoint→RTTOV cost and actual T/Q/cloud changes. |
| Accepted state and next analysis | Open | Carry an accepted checkpoint into a second assimilation using the fixed-prior control definition. |

The recorded NC numbers do not yet have certified physical units. The traces
are selected positions from a full-domain step, not a domain conservation
proof or a verified full-host derivative. This step adds no RTTOV or optimizer
calls. Its purpose is to choose the next narrow producer-side measurement from
observed differences rather than to add a numerical NC floor or shrink M0.
