# KDM state + forcing first-order boundary

This change adds independent fp64 derivatives for the twelve KDM state fields
and `rho,pii,p,delz`. It reuses the second-call native input already captured
in PR #426; the completed two-step forward campaign was not rerun. The new
offline kernel verification does not change the operational installation,
resume the paused KO analysis, or evaluate RTTOV or an observation cost.

## Captured case and provenance

* Base: feature `4cfb774123053baabfd84132644031038ab273ae`, containing PR #426;
  main was `930378598971d9ca1397087a00dfd2c3cefc2b78` at intake.
* Source: saved-T/Q pulse run, second `MP_INPUT`, column `i=156,j=21`, 39 native
  levels. Trace SHA-256 is recorded in [the full sweep](native39_joint_ad.json).
* Native binary32 hex values are promoted exactly to fp64. `dt=20 s`,
  `xland=2`, both `ncmin` values 10, legacy variant and `dry_number=0`.
* A separately built macOS arm64 Release library uses Python-package
  libtorch 2.13.0. This differs from CI's pinned 2.8.0 and from the existing
  operational host library. See [build attribution](build_manifest.json).
  All libtorch/c10 dependencies resolve from the same Python package.
* The historical raw number coordinates are preserved. The host-initialized
  `NN` volume CCN profile is not relabeled or converted into homogeneous
  dry-mass-specific number data. This is an executed-map derivative check,
  not a proof of physical number or mass conservation.

## Native-input result

Old value-only, new value-only, and new graph-recording fp64 outputs agree
in all **468 raw binary64 values**. The new handle returns gradients for all
four forcing inputs. The report includes individual forcing directions so
one successful mixed direction cannot mask an omitted forcing.

| Direction | JVP/VJP dot relative error | Selected central-difference epsilon | Weighted FD relative error |
| --- | ---: | ---: | ---: |
| State theta/QV | 1.63e-16 | 1e-3 | 1.23e-10 |
| DEN | 6.85e-15 | 1e-2 | 4.09e-8 |
| PII | 6.78e-15 | 3e-4 | 7.81e-9 |
| P | 2.36e-16 | 1e-2 | 8.28e-7 |
| DELZ | 5.05e-16 | 1e-2 | 1.39e-5 |
| Mixed | 1.24e-15 | 1e-4 | 1.31e-9 |

The acceptance rule is **per output field**, not the weighted norm in this
table: scaled absolute error must be at most `1e-8 + 3e-5*signal` for every
field at one common epsilon. The best maximum tolerance ratios range from
`9.53e-6` to `8.33e-4`, below the limit 1. All nine epsilon trials are retained;
the weighted norm is descriptive, not an extra acceptance gate.

The chosen state direction perturbs theta and QV. At zero hydrometeor values,
the state direction is zero to avoid pretending that a central difference
through negative mass validates a positivity boundary. Initial-state branch
diagnostics are included, but the ABI does not expose downstream limiter or
integer sedimentation schedule signatures. The evidence establishes a local
first-order map on this profile, not all state directions, all regimes, HVPs,
or parameter identifiability.

## Synthetic numerical limitation retained

An additional Fortran fixture uses a 60-second conservative-interface step,
`dry_number=1`, and an initial NCCN of `1e9`. With the original unscaled
covector, the joint dot products are `-212.80969136100816` and
`-212.80969095556890`: absolute difference `4.05e-7`, relative `1.905e-9`.
This **fails** the initially attempted `1e-10` raw-covector gate. Quad-precision
accumulation of the binary64 products reproduces the discrepancy; final-dot
summation is not the explanation. NCCN-zero covectors remove the discrepancy
to ordinary binary64 rounding levels, localizing the stress to NCCN-seeded
derivatives. The exact internal cause is not established.

The [independent ctypes record](synthetic_raw_stress.json) uses the exact Fortran layout, land/sea
`ncmin=100/10`, and Decimal accumulation of binary64 products. On the same
inputs, joint state-only directions and state gradients are bit-identical to
the old state-only ABI for both dry-number selectors. The old dry-number=1
state-only path itself misses `1e-10` (about `3e-10` relative). This is evidence
against a new Fortran packing or joint state-gradient regression; it is not
evidence that all raw joint derivatives satisfy that tolerance.

The Fortran interoperability test therefore distinguishes a primary
unit-scaled covector gate (`1e-10`, unchanged) from this original raw stress,
which it continues to print. The changed weighting is explicit, and the
unscaled miss remains an open numerical limitation. The actual 39-level
legacy/raw-coordinate result above has its own predeclared criteria and passes.

## Local validation

On the frozen research build (`KDM6_ENABLE_TEST_HOOKS=ON`, Release):

* All 21 CTests passed, including the joint C ABI and ISO_C_BINDING tests
  (71.07 s). Test assertions remain enabled with `-UNDEBUG`.
* Python/C++ state AD comparison: 27 passed (16.63 s); forward comparison:
  4 passed (17.02 s). These retain their existing comparison contracts.
* Verifier error-path/serialization tests: 5 passed. These use an analytic
  test double and do not count as native derivative evidence.
* The diagnostic overlay was re-derived against the changed canonical runtime;
  all four noninterference checks and 65 focused tests passed.
* The final shared library exports exactly 14 allowlisted C symbols, ABI major
  2. Its fresh-process load preserves caller `KMP_DUPLICATE_LIB_OK` settings.

The local library uses libtorch 2.13.0; CI's pinned libtorch 2.8.0 and shipped
test-hooks-OFF build are separate checks. Private host integration and RTTOV
were not rerun. Public-clone skips do not establish private-path coverage.

## Interface and subsequent work

The [API contract](../../../docs/STATE_FORCING_AD.md) describes additive
symbols, packing, independent leaves, retained graphs, and ISO_C_BINDING
wrappers. Old state-only handles are rejected by joint derivative methods;
old entry points and operational f32 forward arithmetic are unchanged.

This result supplies `K_s` and `K_F`. It does not supply the host forcing
Jacobian `G_X`, native RK/finish/limiter derivatives, or a full-host adjoint.
For a later same-coordinate tendency `(y-s)/dt`, the `-ds/dt` term is required;
the actual moist-theta finish map must be differentiated as executed. RTTOV
pressure dependence and a cost-function direction check remain later work.
