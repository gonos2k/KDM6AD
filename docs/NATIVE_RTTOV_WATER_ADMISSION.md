# Native checkpoint water-vapor admission to RTTOV

The full-physics checkpoint-to-observation path retains native water vapor.
One unsupported profile must be classified before an external RTTOV call,
without dropping the original native row or changing its gas concentration.

## Actual RTTOV 14 boundary

The pinned executable uses `gas_units=2`: Q is ppmv over moist air. Its
internal profile check uses ppmv over dry air. The executed source order is

```
factor = 1 / (1 - Q_moist * 1e-6)
Q_dry = factor * Q_moist
```

`rttov_const.F90` defines `qmin = 0.1E-10` ppmv dry. The check in
`rttov_check_profiles.F90` rejects `Q_dry < qmin`; equality is admitted.
`rttov_convert_profile_units.F90` supplies the conversion before the check.
Source fingerprints are recorded with the case audit. This is an intrinsic
input-domain check, distinct from coefficient-regression quality flags.

The shared native observation row validator performs this value-only check
in float64. It also rejects an invalid conversion denominator or nonfinite
converted water. Rejected rows receive `rttov_hard_qmin_invalid`; all native
indices and unchanged input values remain in the result. No Q floor, clipping,
replacement profile, disabled RTTOV check, or new model tendency is introduced.
Admitted tensors retain their original AD graph. No derivative through the
discrete admission decision or a changing observation mask is asserted.

## Observed whole-host case

The original baseline call for chunk 55 failed on one zero-Q profile. The
same frozen-case audit found one such profile among 64,914 baseline profiles
and one among 64,903 alpha-1 candidate profiles. The model location is flat
28195, native 1-based `(i=116, j=121, k=30)`; native QV is zero there.
The serialized RTTOV check reports pressure 130.3445573 hPa from its pressure
grid. This pressure is not relabeled as a native mass-center pressure.

The prior 52 successful new chunk calls and four pilot calls pass the added
check. Their results are reused. The failed chunk-55 request remains counted
and preserved; a distinct recovery case removes only its unsupported profile,
retains all 512 source rows, and preserves the other 502 profile inputs.
The authorized filtered chunk-55 RTTOV process returned success; postprocessing
initially failed before writing the final NPZ, then the saved direct output was
recovered with zero additional RTTOV calls. The 72 other continuation chunks
completed. The full baseline audit covers all 65,988 columns in 129 unique
successful chunks and retains the original failed request in the ledger. It
reports 53,906 supported columns / 377,342 channel cells and baseline-only
direct cost 11.007963317242059. Candidate observation costs remain unavailable;
this baseline score does not establish a candidate improvement or physical
closure.

The same rule applies to baseline and candidate before fixing `M_host0`.
Once support is fixed, loss of a supported candidate row rejects the trial;
the support is not reduced to make a candidate acceptable. The separate
alpha-1 QC-positive/NC-zero rejection at flat 5770 is unchanged by this rule.

The initial executed adapter/source and interim evidence are preserved at
commit `7d4d2d85b9c444b7cae9e842bec9ff332a013814`. Adding this observation
admission check does not rebuild or change either completed native host run.
