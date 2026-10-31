# Synthetic ice-number fate after sedimentation

The [replay](replay.py) reuses the exact two-column, three-level synthetic fixture declared in PR #504's `test_ice_chain_applied_budget.py`. The first column has one active ice substep under the **legacy raw first-ice handoff**. Its QI is zero and NI remains positive at the end of the full sedimentation chain. A second ice substep is called for the batch but gated off for this column; the replay checks that its first-substep and full-chain QI/NI words match.

The replay then flips the completed sedimentation state from top-first to WRF bottom-first order, rebuilds the post-fall cloud slope and auxiliary inputs, and calls the existing `kdm62d_one_step_torch()` for one `dtcld=1` microphysics pass. It uses the previously fixed entry heat coefficients and the existing `SensitivityTrace` stage taps. The component call sets `nccn=None`, so this is **not** a full `_kdm6_pure()` run with its CCN reservoir or adaptive `mstep` selection. The manually prescribed chain schedule is `mstep_main=mstep_ice=2`, per-column `[1,2]`; the runtime's initial speed rule would instead choose `[1,1]` for both loops on this input. PR #504 also omitted runtime's pre-sedimentation BRS reclamp. This replay applies that reclamp in a separate fixed-schedule contrast: BRS changes from `1e-7` to `1e-10`, but every completed chain state and surface output remains bit-identical for this fixture. The main fate path retains PR #504's exact input. No host, C++ or RTTOV executable is run. Scientific status stays **INCONCLUSIVE**.

| First synthetic column, top-first | QI at three levels | NI at three levels |
| --- | --- | --- |
| Completed sedimentation | `0, 0, 0` | `26.20391534, 28.30833287, 20.95601635` |
| D1 melt | unchanged | unchanged |
| D2–D4 freeze | `1.58935e-15, 1.91502e-15, 2.23665e-15` | rises by `8.98377e-5, 1.06922e-4, 1.23704e-4` |
| State update | `2.08160e-10, 1.62748e-10, 1.48010e-10` | `104.52596193, 104.52590892, 104.52596725` |
| Picons, satadj, paired cleanup, final DSD limiter | unchanged from state update | unchanged from state update |

The applied cold rates are checked against the state update's QI and NI differences, with floating-point operation-scale bounds. At the top level, `pinud=2.050470559e-10` and `pidep=3.111496863e-12` dominate QI growth; `ninud=78.322210997` dominates the NI increase, while the other recorded NI rates sum to about `-0.000254244`. Complete-sublimation is false. Picons does not reclassify the new ice; QI remains above the paired-cleanup threshold; the final ice number limiter does not snap it. The D2–D4 QI is only `0.589e-15` above the `1e-15` threshold at the top level, so this f64 synthetic branch should not be presumed identical in an unmeasured f32 host run. The replay retains all seven named value boundaries, the selected branch masks and the applied rate values in its JSON output.

Calling the paired cleanup **directly on the post-sedimentation state** sets NI to zero because QI is zero; the replay explicitly checks this counterfactual. It is not the executed order: the actual one-step sequence has D2–D4 and cold rates before cleanup, and in this fixture they create enough QI for NI to survive. The first ice substep's orphan pair must not be labelled the completed microphysics or host state.

The replay checks 43 public source files against the **bundled SHA-256 manifest**, then verifies the selected post-chain to microphysics handoff, exact trace-off/on output bits for the public one-step function, stage order, D1 unchanged state, D2–D4 applied amounts, rate accounting, the selected Picons/cleanup/DSD branch masks and final handoff. The manifest is versioned with this code, not an independent trust root for arbitrary checkouts. The replay does not authenticate a private checkpoint/build, infer how often this branch occurs in the native domain, certify QNICE units, or provide an end-to-end host/RTTOV derivative.

```bash
python3 -m harness.evidence.ice_post_sed_fate_2026-10-31.replay
python3 -m unittest discover -s harness/evidence/ice_post_sed_fate_2026-10-31 -v
```
