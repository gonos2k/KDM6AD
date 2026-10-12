# Red postrun review: PR415 eight-iteration window

## Result and disposition

The one declared attempt returned `RETURNED_AUDITED_WINDOW` for run `PR415_JUL19_THREE_SLOT_8ITER_20261012_01`. This is a successful audited return, not convergence: the saved full-control gradient has L-infinity `0.0026061003` and L2 `0.0079570380`, strict tolerance is `1e-10`, `strict_gradient_converged` is false, and termination remains `UNKNOWN`.

The run recorded 8 iterations, 10 function evaluations (`max_eval=10`, strong-Wolfe), one audit evaluation, and 33 logical H calls (11 window evaluations × 3 observation slots). Internal RTTOV child/direct call counts were not recorded (`null`); 33 is the logical wrapper count, not an internal RTTOV count. No native integration or new observation date was run, and this was not full host cycling.

## Same-problem and artifact checks

The result plan digest is `83eb8e3873ac22f9947ed5226e8f9930386ce7e3a4f5589cab82c468413d2ad6`. The reused PR414 runner remains SHA-256 `bb01077496cf95263f5f69c3dfc95bba9871e171fa374e29e9b3de3d5217cedf`; the adapter is `073bce6bffdd854b84f40e4234f1eecf5f426d9ea5c658ce8ba16de4eee0e15c`. `DRIVER_RESULT.json` binds both hashes, the plan digest, result path and result digest.

I checked all 119 declared file bindings and all 33 external execution assets after the run: no file was missing or changed, including resolved paths and sizes for the external assets. The old and new private checkpoint NPZs contain the same 137 array keys. Initial background state, forcing arrays, all three observed target/mask pairs, optical density, pressure arrays and background-error standard deviations are exactly equal. The recorded effective H summaries are identical after removing the per-run fixture directory, and observation records are identical. The saved P415 plan keeps the PR414 input/source hashes and changes only the optimizer budget plus run/output identity and provenance bindings.

## Numerical comparison

Both runs start at observation cost `J_o=26.649841375721`. PR414's 3-iteration accepted total was `J=20.294560081329` (`J_o=20.094911217481`, `J_b=0.199648863848`). PR415's 8-iteration accepted total is `J=19.440396100391` (`J_o=18.420371779734`, `J_b=1.020024320656`), a decrease of `0.854163980938` in total cost alongside a larger background penalty. The lower cost is a result of this bounded budget increase, not evidence of a globally optimal or converged solution.

The saved accepted initial-state `th` and `qv` arrays differ between the two budgets (maximum absolute changes `0.2585944822` and `0.0005163288`, respectively); all other accepted initial state fields match exactly. The full-control gradient decreased from PR414's L-infinity `0.3850806305` / L2 `1.3767559787`, but remains well above the strict threshold.

All seven selected channels have model `rad_quality=0` at all three slots, and every reader DQF remains zero. At the accepted endpoint, the seven-channel BT vector is identical across slots 1, 31 and 61 in this saved run. Relative to the PR414 accepted vector, the new endpoint is warmer by `0.0709803` to `0.1776709 K` per channel; these same per-channel changes repeat across all three slots. The observation target vectors differ overall, although IR087 is exactly the same at 06:06 and 06:16. These records therefore show a budget-dependent endpoint and per-slot costs, not a sampled temporal BT response.

## Provenance and interpretation limits

This remains the July 19 local KDM window with fixed `f0` prescribed forcing held over 61 × 20-second transitions, and observations at steps 1, 31 and 61. It is not saved later host forecast states or host cycling. The three actual L1B scenes use the explicit nominal-filename-time-as-model-UTC research assumption; exact pixel UTC is unverified. The additive 21 channel-time Huber terms use equal 1 K scales, without empirical temporal covariance calibration.

The hourly MP137 candidate evidence supports that the named 00–12 run completed normally, saved 13 hourly frames, and passed the recorded MP37 raw-bit comparison. It does not identify the July run's executable bytes or exact input-file bytes. The 2025 `Times` records versus `wrfchainp_d01`'s 2024 `START_DATE` remain unresolved, and the final `[09,12)` boundary interval has an exclusive 12:00 endpoint for further host advancement. These limits do not alter the bound local-window inputs, but they preclude claiming byte-exact producer admission or post-12:00 host coverage.

Review actions were read-only after execution: JSON/result/log inspection, comparison of saved checkpoints, and hashing declared source/input/assets. No additional model, H, M, or optimizer calls were made.
