# PR408 synthetic capture success

Run ID: `PR408_SYNTHETIC_ALLSKY_TQ_20261011_01`. Status: `RETURNED_DIAGNOSTIC_ONLY`.

This one-time persisted run reused the PR407 V4 case builder and the existing `oracle/tests/test_da_single_column.py::_install_synthetic_allsky` fixture with `InlinePool`. The real `run_single_column_analysis`, LBFGS step, final accepted-state audit, PR395 capture validators and private checkpoint writer ran. The existing all-sky callback was replaced by the explicit synthetic H fixture; RTTOV was not executed.

The synthetic case returned with 5 logical H calls, one final audit and seven frozen valid channels. The existing initial-objective audit returned `CROSSCHECKED`. The total objective is 23.0297987783 (`Jb=0.228225844439`, `Jtheta=0`, `Jo=22.8015729339`); parameter priors remain inactive. Checkpoint SHA-256 is `9410e2717bb8af4914e7eca4d761311ba5f8a837a341e2f7128bffceabd2188f`. It is mode 0o600 under a mode 0o700 directory.

A second call on these same output paths was refused before analysis by the existing fresh-path guard; the checkpoint and public receipt hashes stayed unchanged. This is synthetic capture wiring only. It does not use actual July20/21 native state and does not establish pixel-time matchup or science acceptance. The user-owned assessment remains 79/100.

The final control-gradient Linf is1.5642977119201262e-7, above the declared1e-10 tolerance; L-BFGS termination attribution isUNKNOWN. This is a finite-budget diagnostic return, not demonstrated convergence. A separate summary serialization script raised a post-capture NameError (omitted Path import) after checkpoint/receipt publication. The report was recovered by reading those existing files, without repeating capture or overwriting either output; see [postprocessing note](POSTPROCESSING_NOTE.json).

See [SYNTHETIC_CAPTURE_RESULT.json](SYNTHETIC_CAPTURE_RESULT.json) for hashes, control gradients and detailed audit values, [CAPTURE.json](runs/PR408_SYNTHETIC_ALLSKY_TQ_20261011_01/CAPTURE.json) for the capture receipt, and [private checkpoint](</Users/yhlee/KDM6AD-k/host/research_evidence/pr408_synthetic_capture_20261011/private/PR408_SYNTHETIC_ALLSKY_TQ_20261011_01.npz>) for full state/control arrays.
