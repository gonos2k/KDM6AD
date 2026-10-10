# PR398 eight-iteration convergence experiment

This report records the one authorized execution of
`PR398_CONVERGENCE_8ITER_20261010`. It used the existing hash-validated PR395
native intake, the same initial state and forcing, same seven-channel H
configuration, observations and fixed prior, with controls initialized to
zero. No native model was rerun. The run had `max_iter=8`; PyTorch L-BFGS
provided the default `max_eval=10` without the driver passing that setting.
The predeclared token `pytorch_lbfgs_default_ceil_1.25_max_iter` is historical
metadata; pinned PyTorch 2.13 computes its default as `int(max_iter*1.25)`,
which is 10 for this eight-iteration case. It does not assert a general ceiling
rule.

The capture returned `RETURNED_DIAGNOSTIC_ONLY` with validated native input and
one final accepted-state audit. The optimizer reported `n_iter=4`,
`func_evals=4`, four window evaluations, and one final audit. It did not reach
the iteration ceiling. The stop reason is `UNKNOWN` because PyTorch L-BFGS did
not expose it. The final total-control gradient has L2 norm
`3.1591637535e-6` and L-infinity norm `1.1849362251e-6`, both evaluated after
the accepted-state audit; the L-infinity value remains above
`tolerance_grad=1e-10`. This is not evidence of optimizer convergence.

The initial zero-control closure reproduced PR397 `Jo0=26.588575903055926`
exactly, with `Jb=Jtheta=0`, seven supported channels, and the same all-one
frozen mask. The final returned objective is `Jb=0.2285274367596143`,
`Jtheta=0`, `Jo=26.13556273499745`, and `Jtotal=26.364090171757063`. Total cost
fell by about `0.84429393%`; the observation term fell by about `1.70378876%`.
Relative to PR397, final total cost differs by about `-2.19e-8`, while a
slightly smaller observation term is balanced by a slightly larger state
prior. The extended iteration ceiling therefore left the combined objective
effectively unchanged in this case. The cost change is not a forecast-skill or
scientific-acceptance result.

The one failing post-run driver assertion is cross-run equality of the
operator-signature hash. PR397 used fixture path
`.../run-3d2e97f159/rttov_fixture`; PR398 used its isolated experiment path.
The H configuration matches after dropping only `fixture_case_dir`, and the
receipt's initial Jo, frozen mask, seven-channel support and within-run
signatures match. Source `oracle/kdm6/da_fulldomain.py` includes the full
`rttov_cfg` in `_h_signature`; `_h_fingerprint_value` hashes string values as
written. Thus the isolated absolute fixture path changes the cross-run
signature even though it points to the separately copied, hash-matched
fixture. The driver accurately records this one false check as
`RETURNED_WITH_CHECK_FAILURES`; no receipt or checkpoint was rewritten to hide
it. The final within-run audit signature is
`cdf933641a10aefa60444c779c5a4ae547a4685b1f53051e0ccc367f2cec5148`.

The run remains diagnostic-only. Pixel-time matchup and physical/scientific
acceptance are `NOT_ASSESSED`. Local background qc/qi/qs level sum is zero,
and non-T/Q state sigmas and physical-parameter controls remain inactive; the
experiment did not seek cloud or adjust the prior.

The private checkpoint has mode `0600` in a `0700` directory and SHA-256
`f69e13259e8617ba9d5a5f4785fc0e9c2d1eb990994a92411e1a7d6d72d1b0e8`. It
contains four distinct 12-field states, initial state arrays equal to the
validated intake, saved final BT/mask/quality, all state/parameter controls,
full final gradients and the pre-audit L-BFGS history arrays. The public
capture RESULT SHA-256 is
`8591e782c07ee62ad290d24be2d3769ed2b6bb1c86fdd9b403e74b5f587dcfb8`; the
driver receipt SHA-256 is
`78e8fd335029d5d147ae9d996eda7f1393f602a9aff21961aaaba6b5df36e188`.
No retries or additional H/M evaluations were run after these artifacts were
published.

## Post-run source and endpoint audit

A separate read-only audit compares the raw signature, initial costs/mask,
within-run trace signature stability, the effective H configuration, copied
fixture contents, and executable/coefficient hashes. It recognizes the
cross-run raw signature difference as path-sensitive: `fixture_case_dir` is
the only differing H configuration field before path normalization, and the
signature source hashes the full `rttov_cfg`. The original failed driver check
remains in the hash-bound DRIVER receipt; the interpretation audit is a
separate artifact and makes no H/M calls. See
[POSTRUN_INTERPRETATION.json](POSTRUN_INTERPRETATION.json).

The saved endpoint arrays show unweighted vertical `qc` and `nc` sums of zero
in all four endpoints for both PR397 and PR398. A separate saved-array check
also found zero `qr`, `qi`, `qs`, `qg`, `ni`, and `nr` across these endpoints;
`nccn` is nonzero but its raw level sum matches between runs and is not a
column-integrated budget. The PR397 and PR398 background state and background
observation-slot state arrays match exactly. Analysis endpoint hydrometeor and
number fields match; the maximum absolute `qv` difference is `1.1612e-7 kg/kg dry`.
The largest phase-aware `qv/qs` ratio is
`96.7514783%` in PR397 and `96.7508980%` in PR398, both at bottom-up level 3.
The liquid-only `qv/qs_water` ratio is separately recorded. Neither ratio is
observed vapor-pressure RH, and the qc/nc sums are not column-integrated
budgets. Full compact summaries are in
[SAVED_ENDPOINTS.json](SAVED_ENDPOINTS.json) and
[SAVED_CONDENSATE_FIELDS.json](SAVED_CONDENSATE_FIELDS.json); these calculations
used saved arrays only.

See [capture RESULT](RESULT_PR398_CONVERGENCE_8ITER_20261010.json),
[driver receipt](DRIVER_PR398_CONVERGENCE_8ITER_20261010.json),
[predeclared protocol](PREDECLARATION.json), and the private checkpoint path
bound by the capture RESULT.
