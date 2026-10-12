# Red preflight: PR415 bounded same-window budget check

## Disposition

**GO for the single declared PR415 attempt.** The declaration and prepared context are bound to the completed PR414 July 19 three-observation window. The only scientific control change is the optimizer iteration budget from 3 to 8. This preflight did not execute analysis.

## Binding review

The adapter `run_finish.py` imports the frozen PR414 runner and sets only its packet destination and `MAX_ITER`. It verifies the old runner's SHA, the original plan SHA, run ID and budget, and equality of the problem-defining plan fields. Its plan retains the PR414 values for V4 driver/intake, native background, H configuration, forcing, all external assets, Python/thread environment, zero-start control, prior, observation policy and time assumption. It copies all 114 original input bindings without repinning, then adds bindings for the adapter, original plan, original result and preflight, and the old private accepted-window checkpoint. The old external assets remain included with resolved path, size and digest checks.

The executed PR414 runner remains SHA-256 `bb01077496cf95263f5f69c3dfc95bba9871e171fa374e29e9b3de3d5217cedf`; PR415 adapter SHA-256 is `073bce6bffdd854b84f40e4234f1eecf5f426d9ea5c658ce8ba16de4eee0e15c`. The declaration binds the adapter to that digest and the old declaration to `fc704e2af5c68674e91afeaffd3e61102ebdcc167660f8b515fe123d6a1111cd`.

The PR415 preflight records `PREPARED_NO_ANALYSIS`, `analysis_executed: false`, Torch 2.13.0, and the plan SHA-256 `83eb8e3873ac22f9947ed5226e8f9930386ce7e3a4f5589cab82c468413d2ad6`. I independently compared the prepared fingerprint to PR414: the initial state, forcing, H configuration, and three slot signatures match after excluding only the expected per-run fixture directory. The packet output root is the fresh PR415 run ID; it is prepared for the single attempt. The adapter refuses a plan, runner, input or execution asset drift rather than updating its expected digest.

## Independent objective check from the existing CSV

I recomputed the per-slot observation Huber sums from PR414 `WINDOW_CHANNELS.csv`, using the declared unit channel scale and normalized delta 1. The background-to-observation sums are 8.461861229522, 9.110309309430 and 9.077670836769, totaling 26.649841375721. The accepted-state sums are 6.296961690078, 6.910692202270 and 6.887257325133, totaling 20.094911217481. These reproduce the recorded initial and final observation costs. The three target vectors are distinct overall; IR087 at 06:06 and 06:16 is exactly equal, so this does not mean every channel value differs at every slot.

## Scope limits to retain in the run report

The declared experiment uses one zero-start prior and holds the July 19 background forcing `f0` over 61 local 20-second transitions, with observations at steps 1, 31 and 61. It adds 21 equally scaled channel-time Huber terms; temporal independence/covariance is not empirically calibrated. The observations retain the nominal-filename-time research assumption because exact pixel UTC was not verified. Report actual accepted iterations and evaluations, termination/convergence status, and per-slot outputs separately. The nominal Torch `max_eval=10` may be exceeded by strong-Wolfe line search; it is unchanged. An accepted point at this budget would not establish strict convergence, temporal BT evolution, host cycling, or results for another date. The plan permits one attempt, with no automatic retry or budget escalation.

No H/M/optimizer analysis call was made for this review; only existing PR414 CSV and recorded declaration/preflight artifacts were read.
