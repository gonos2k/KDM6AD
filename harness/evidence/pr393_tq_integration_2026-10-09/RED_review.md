# RED review — conditional all-sky routing and T/Q prior alternative

Reviewed the single-column adapter and its focused integration tests as new untracked files on working-tree baseline `e6198816`. `git cat-file` confirms neither `oracle/kdm6/da_single_column.py` nor `oracle/tests/test_da_single_column.py` exists at that base commit. The final focused run I performed was:

```text
/opt/local/bin/python3 -m pytest -q oracle/tests/test_da_single_column.py
12 passed in 2.46s
```

The tests use synthetic states/forcings and monkeypatch H at the all-sky/clear callback boundary. They exercise the existing frozen-support factory, the actual dual minimizer/window and pure-Torch KDM forward/adjoint on synthetic inputs. The added nonzero-control directional check compares `Jb+Jo` central finite differences with the projected window adjoint through the CVT and two KDM steps; it passes, but its H remains synthetic. The tests do not invoke real RTTOV, read a forecast, run a native host, or validate a physical observation case. The synthetic K=39 check verifies shape and CVT counts only; its state and interface grid are fixtures, not a loaded native column.

## Current path and alternate path

The existing `run_fulldomain_analysis` still creates `default_param_prior(0.2)`, which activates all four `PNAMES` parameters. It classifies each column at the observation-slot background, then routes model-cloudy columns through all-sky and model-clear columns through clear unless pseudo-RH regime 2 routes them to all-sky. With `pseudo_rh=False` and a clear slot state, the high-level route is fixed clear H. The code that selects that route and the default prior is unchanged.

The new `run_single_column_analysis` deliberately describes a different normalized-dry study: it requires `obs_time>=1`, routes the one column through all-sky even when its slot-background classifier says clear, freezes all seven AMI 10–16 channels, pins all four microphysics parameters to their current default background with `sigma_log=0`, and gives the initial state only `th` and lower-12-level `qv` controls. It does not alter the full-domain route or the default prior. Its reported physical clear/cloud flag is metadata; it never changes the all-sky routing. It reports only successful non-`None` observation callback results; failed attempts are excluded. It does not claim a count of callback signatures, KDM steps, or RTTOV launches.

The tests provide two complementary witnesses. The forced-all-sky test confirms a synthetic physically clear post-M background can route through all-sky with seven valid channels; a synthetic cloudy trial with `rad_quality=0` changes `Jo` and returns a nonzero `qc`/`th` adjoint. A one-channel background QC loss fails before minimization. The clear-factory compatibility test uses the existing clear evaluator and two-step dual window with `default_param_prior(0.2)` and all four sigma values equal to 0.2; it retains nonzero slot `th`/`qv` adjoints and a positive observation cost through the window. The clear compatibility witness calls the real low-level clear factory and dual minimizer, with a synthetic clear H callback; it does not call the entire `run_fulldomain_analysis` wrapper. Together with the high-level source trace, this supports that the former clear H∘M analysis was not shown wrong by proposing the alternative.

Accounting checks cover the initialized and final state controls, `Jb=0.5||v||²`, `Jtheta=0` under the pinned prior, positive `Jo`, and equality of the final trace total to the three returned components. The added directional check starts from a nonzero CVT control, compares the projected two-step window adjoint with a central finite difference of `Jb+Jo`, and passes. `obs_time=0` is rejected by the new T/Q-through-M adapter. The returned callback-result counter counts only successful non-`None` evaluator results; failed attempts are excluded. No signature count or raw KDM/RTTOV call total is published, and the corresponding underlying runtime counts remain `None`.

## Prior arithmetic from existing receipts

The saved baseline and `T_minus_0p8K` cases both retain the same seven-channel support. The weak case changes physical temperature by −0.8 K at the selected layer, corresponding to `Δθ = −0.8053122875524954 K` in potential temperature. Under a single-component `th` prior sigma of 0.8 K, its arithmetic background penalty is `Jb = 0.506662406627`. Adding that to the saved weak-case observation cost `Jo = 22.616033126543` gives `J = 23.122695533170`, a conditional 13.03522378% reduction versus the saved baseline `Jo = 26.588575903056`. This is a prior-adjusted comparison of saved what-if values, not an optimizer result or proof of a physical case.

For the saved +6% qv perturbation, `Δln(qv)=ln(1.06)` under sigma 0.08 gives `Jb=0.265255129216`. That case has only 6 valid channels while the baseline has 7; its 6-channel Huber sum is not admissible as an improvement under the fixed seven-channel objective. The strict fixed-support callback would reject such quality loss during a trial.

## Limits and open interpretation

The synthetic direct `qc` sensitivity is intentionally supplied by the test callback, so it demonstrates that the existing all-sky factory routes and carries that covector under its contract; it is not evidence that real RTTOV produces the same sensitivity for this candidate. Similarly, default theta parameters being active on the existing path and pinned in the new path does not establish parameter identifiability, a physical need to pin them, or a required correction to an earlier analysis. The hypothesis that a particular clear-background case should use all-sky H or a different parameter policy remains conditional; there is no supported numerical posterior probability.

The adapter preserves the caller's layer-center suffix exactly and passes caller `p_half` unchanged after a `len(p_half)=len(p_lay)+1` coherence check. Since the `Forcing` API contains layer centers but not an independent interface-pressure field, the adapter explicitly records native interface identity as unverified. This is a provenance limitation for the caller-supplied pressure grid, not a claim that an arbitrary interface grid is native.

No actionable issue remains in the reviewed route, theta pin, post-M background QC, objective accounting, or positive-observation-time contract. The `p_half` provenance caveat is explicit. No source default, full-domain routing rule, physical scheme, optimizer, or solver was changed in this review. The conditional P2 concern remains a question for a real accepted observation/native case; this synthetic reproduction alone does not make it mandatory.
