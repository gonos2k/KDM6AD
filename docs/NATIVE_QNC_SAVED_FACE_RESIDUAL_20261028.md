# Saved-face QNC residual: a counterexample to a sign-only correction

Base: `main f3d84bfa0697b943e89a57495897ddb757b65d30`, after PR #469.
The [versioned packet](../harness/evidence/native_qnc_saved_face_probe_2026-10-28/README.md)
replays the frozen control and α=0.25 records at native `(113,70,12)`.
No new native step, RTTOV call or optimizer step was performed here.

The recorded RK3 target limiter is active in both runs with scale word
`3C54898F`. Its six outgoing correction faces are individually reproduced
from their stored pre-limit words and that scale in binary32. The stored
low-order face words are unchanged. The scale word is compatible with a
binary32 replay of `max(0, PH_LOW/(FLUX_OUT+1e-20))`. Using the saved RK old state and
mass factors, exact arithmetic on these binary32 words gives:

| Numerical saved-face quantity | Control | α=0.25 |
| --- | ---: | ---: |
| State-based availability `A` | 4,237,102,030.521587 | 4,237,098,504.170056 |
| Applied correction outflow `O` | 4,237,101,865.984564 | 4,237,098,913.951257 |
| **`A−O`** | **+164.537023** | **−409.781200** |
| Corresponding exact-real QNC | +0.001727296861 | **−0.004301851181** |

The α face values already yield a negative state residual before the final
RK binary32 arithmetic. Raising precision only in the last subtraction,
division or store does not establish positivity for those frozen faces.

The limiter's recorded `PH_LOW` and `FLUX_OUT` are a different numerical
pair. Their exact stored-input margin `PH_LOW−FLUX_OUT×SCALE` is
**−44.020629883** in control and **+28.576782227** in α. A positive margin
in this limiter proxy therefore does not prove that the rounded post-limit
faces leave a positive state-based residual. The replay keeps the two
definitions separate.

An offline one-ULP scale reduction (`3C54898F → 3C54898E`) makes five of
the six α correction-face words change. The exact-real state residual remains
**−111.694128672**, with QNC **−0.001172556278**. All four directional
arithmetic modes compatible with the original α recording, combined with
its original-compatible RK mode, instead produce a **positive binary32 QNC
+0.001692894381**. This is a local saved-input counterfactual, not an
executed host correction or a physical particle-number verdict.

## Acceptance checklist for a limiter proposal

| Check | Current result | Required next evidence |
| --- | --- | --- |
| Original face and RK source linkage at `(113,70,12)` | Complete in PR #469 and this companion | Preserve the original bitwise joins. |
| One-ULP local final-state sign | Positive in the α arithmetic probe | Evaluate the same applied faces' state-based availability and outflow; α exact-real residual remains negative. |
| Shared-face donor/receiver application | Not evaluated by this packet | Apply each changed face identically on both sides and inspect all six neighboring states and budgets. |
| General rule across the remaining failures | Open | Establish admissible moment-pair and physical-unit contracts before changing the full host. |
| Full fixed M0 and satellite cost | Open | Run a justified host variant and keep every fixed M0 profile before direct checkpoint→RTTOV evaluation. |
| QI boundary branch at `(1,168,33)` | Target pre/post known from PR #469 | Record `flow_dep_bdy`'s actual donor QI, x-boundary velocity and branch selection in matched control/α runs. |

The existing full-host α endpoint remains invalid at **54 M0 profiles and
378 channel cells**. Its fixed-support RTTOV cost is still undefined and no
analysis has been accepted or carried into a second assimilation. The saved
NC coordinate has no certified physical unit. The FMA-compatible arithmetic
modes identify possible evaluation orders, not executed compiler opcodes.
