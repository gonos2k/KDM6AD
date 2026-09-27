# S2 experimental dry-mass number boundary

The host Registry and dry-air-mass scalar update define QN prognostics as
number per kg of dry air. The mp37 particle-size formulas require number per
cubic metre. The opt-in patch
[`s2_dry_number_optin.patch`](../g33_fortran/s2_dry_number_optin.patch)
converts all four QN fields at the mp37 boundary with the entry dry density
`rho_d = den_m / (1 + qv_entry)`, then converts them back with the same frozen
density. `den_m` remains available for air-property calculations. The default
mp37/mp137 source and operational install are unchanged.

The patch applies to the canonical private `phys/module_mp_kdm6.F` with
SHA-256 `fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5`.
Its resulting source SHA-256 is
`7c6f9c7897259c67f6f9bfea9bf2aa0f1e3ff4df39f1c20643ddab48d8fd95e5`.
It is kept as a patch because the host tree is private and the change is not
approved for the operational path.

The first-step CCN profile is already volumetric, so the wrapper divides it by
`rho_d` before its ordinary number ingress. The kernel uses `rho_d*q` for
DSD mass moments, mass sedimentation and q-specific rate conversions; its
number sedimentation still uses `dz*N`. The returned dry-specific numbers and
`rho_d` are paired again in effective-radius and reflectivity diagnostics.
The original `ncmin` scalar used the final tile column's land/sea choice for
all columns. This experimental path indexes the threshold by column. Number
threshold and cap **numeric values are interpreted as volume concentrations**
in this experiment; their empirical provenance and a different dry-specific
threshold policy have not been settled. `qcrmin` remains a mass mixing-ratio
threshold. Density inputs must be finite and positive, or the experiment stops.

## Focused checks

- `patch -p1 --dry-run --fuzz=0` applied cleanly against the canonical private
  host source.
- `gfortran -cpp -DRWORDSIZE=4 -ffree-form -ffree-line-length-none
  -fsyntax-only` passed using the canonical host module includes.
- `harness/tests/test_replay_number_boundary.py`: 24 passed. These are existing
  algebraic representation checks, not this new native variant's acceptance.

## Native result

The isolated mp37 source built with a fresh `module_mp_kdm6.o` and linked into
an executable without changing the canonical host or operational install.
The object SHA-256 is `49264d12af2af946ea47db72b30e7f19b23a995418a98abdc81ca0057e0b59b0`;
the executable SHA-256 is
`bc538fa21ecd11cf24a291fd1303af10a888dda0b7b506e19ebb1fb7c21c3316`.
The retained `wrfinput_d01`, `wrfbdy_d01`, `wrfchainp_d01` and namelist have
SHA-256 prefixes `5a9ae8da`, `d46e5d71`, `c8e300d2`, and `064b6f5e`.
The retained private link map identifies the fresh module object directly.
It also links common host/dynamics objects from earlier isolated S15/S8
worktrees, so this is not a clean rebuild of every canonical host object.
The executed canonical-workspace `run_ss_case.py` SHA-256 is
`fc92f1eff06fb0a5b4d417a6ef24aecfb1fdeee029fa4d848838de69845ad49f`.
The retained command record sets `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`,
`OMP_THREAD_LIMIT=1`, `OPENBLAS_NUM_THREADS=1`, and `--np 1`; these arguments
are not duplicated in the public run files. The one-rank/one-thread 40 s run exited 0 and
logged `SUCCESS COMPLETE WRF`; saved times are 0, 20 and 40 s. Its forecast
file SHA-256 is
`7fc25442d19aed442aa76537725b2c1ee2db71089eaa21584e498f6effebd1ee`.
The private build, logs and input links are retained outside the public
repository; they are not public test fixtures.

In each saved frame, QNCCN, QNCLOUD, QNICE and QNRAIN each had 2,573,532
finite values. At 40 s, their respective negative-cell counts were 0, 2, 2
and 1, versus zero at 0 s. This execution result does not close the separate
host RK/boundary nonnegativity gate. No same-executable instrumented control,
full-domain budget, default-path parity or RTTOV comparison was performed for
this variant.

## Scope

This is one dry-mass/volume interpretation for an opt-in mp37 experiment.
Empirical coefficient units, threshold calibration, mp137/C ABI/AD equivalence,
other host consumers, independent physical accuracy and accepted observations
remain open. In particular, a successful 40 s run would show that this
specific variant executes; it would not settle S2 or authorize a default
switch. No deployment action is attached to this experiment.
