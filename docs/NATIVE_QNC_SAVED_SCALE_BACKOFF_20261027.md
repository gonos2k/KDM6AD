# Saved QNC donor-scale backoff probe — 2026-10-27

The [public replay](../harness/evidence/native_qnc_scale_backoff_2026-10-27/README.md) evaluates a **one-ULP-lower target limiter scale** using the saved PR461 control and alpha0.25 operands. This is an offline counterfactual. The private host limiter and operational f32 forward were not changed or run again.

## Candidate and checks

The target `(i,j,k)=(221,63,6)` takes the outgoing branch of `advect_scalar_pd` in both saved runs. The six recorded outgoing correction faces are recomputed from the original pre-limiter words with the next lower positive binary32 scale. Each recomputed word is installed at both the target and its neighboring cell; low-order faces and other operands remain fixed. Of those six face words, all six change in control and five change in alpha0.25. The alpha `FX_EAST` product rounds to the same word.

The replay first reconstructs the original `PH_LOW` and `FLUX_OUT`, checks the target and six neighbor branch/scale calculations, then checks saved face words, low-order inputs, metrics, seven-cell final tendency handoff and non-`tenddec` RK3 path. It carries only arithmetic modes that reproduced the original tendency and RK3 QNC into the counterfactual; a common mode combination exists across all seven cells (four in control, two in alpha0.25, with an FMA RK candidate in each). It checks the exact operator-weighted face ledger again: 12 internal correction/low-order pairs cancel, the 30 outer incidences are unchanged, and the seven-cell face total is **exactly identical** to the original saved case.

| Target raw QNC | Control | Alpha0.25 |
| --- | ---: | ---: |
| Original recorded RK3 state | +3.442540646 | **−3.814399242** |
| Original exact RK3 expression with saved PD old buffer | +0.285426801 | **−1.838040504** |
| One-ULP-lower-scale exact expression | +5.211649186 | **+1.648786290** |
| One-ULP-lower-scale source-compatible f32 replay | +10.699481010 | **+1.991152167** |

All seven selected cells are nonnegative in both the exact saved-input expression and the original-compatible binary32 replay. For the failed alpha witness, zero ULP backoff is negative and one ULP backoff is positive under these held inputs. The source-compatible result is conditional on the captured arithmetic family; it does not identify emitted instructions.

## Interpretation and remaining gate

The probe shows that a **shared donor-face adjustment**, rather than a more precise final scalar store alone, can cross the target's local zero boundary in this saved case. It does **not** establish that subtracting one ULP is a correct general limiter rule. Other cells, tiles, halos and time steps may need different safety margins, and the RK3 state can be changed again by KDM or later host processes. Raw NC physical units and a closed physical particle-number budget remain unresolved.

Before changing the host physics, a proposed rule needs a derivation in the applied mass-coordinate budget, a bound for the combined face/tendency/RK rounding path, and tests of all donor/receiver states using the actual shared-face application. An isolated variant must then pass a trace-off/on noninterference comparison. Only after a full-domain candidate preserves the fixed observation support can its RTTOV cost and local T/Q/cloud response be evaluated. This probe adds no admissible analysis or second assimilation.
