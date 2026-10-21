# Native microphysics substep to an RTTOV observation cost

This opt-in offline experiment composes the operators accepted in
[native prep](NATIVE_PREP_AD.md), [applied finish](APPLIED_FINISH_AD.md),
and [native observation profiles](NATIVE_OBSERVATION_AD.md). It uses the
existing isolated fp64 state+forcing C ABI and actual external RTTOV-K.
It does not implement a complete host timestep, RK adjoint or assimilation cycle.

## State and executed stages

Controls are the native prep state `X=(THM_pert,QV,MU_total,PH)` and the ten
remaining kernel blocks `QC,QR,QI,QS,QG,NN,NC,NI,NR,BG`. Each mass field has
the native 39 levels; PH has 40 interfaces. Hybrid coefficients, PHB, host
constants, surface/geometry/trace-gas inputs and the upper reference atmosphere
are fixed. No external model or reanalysis replaces native inputs.

For the selected `MP_PHYSICS=137`, `USE_THETA_M=1`, `NO_MP_HEATING=0`,
`MP_ZERO_OUT=2`, `MP_ZERO_OUT_ALL=0`, `USE_Q_DIABATIC=0` path:

1. Prep recovers dry theta and generates DEN/PII/P/DELZ from the live native state.
2. The isolated KDM kernel updates all twelve state blocks, with state and
   forcing JVP/VJP supplied by the C ABI.
3. Host cleanup clamps QV nonnegative and zeroes each non-vapor water mass
   below `MP_ZERO_OUT_THRESH`. NC/NI and the other number blocks are not
   thresholded: the saved configuration does not apply zero-out to `scalar`.
4. Finish applies the bounded dry-theta increment and moist-theta/QV
   coordinate coupling. Its old-state terms remain live. The observation
   theta coordinate is `T_NEW_AFTER`, not the derived `TH_PHY_M_T0` diagnostic.
5. A diagnostic EOS evaluation uses this finished theta, cleaned QV and the
   original MU/PH. It generates consistent pressure and dry density for this
   **split local map**. It does not advance MU/PH through dynamics/RK.
6. Native pressure/P8W, T/Q and cleaned QC/QI/QS with NC/NI enter the existing
   profile builder. Each trial writes its actual RTTOV P/P_HALF and cloud files.
7. Actual RTTOV supplies BT and first-order K. The KMA BT conversion, fixed
   quality mask and Huber loss define the observation cost.

With `USE_THETA_M=1`, EOS pressure depends on finished moist theta and
MU/PH-derived specific volume; density depends on that geometry. Cleaned QV
is carried through this prep interface but does not directly change P/rho at
fixed moist theta, MU and PH. Its live effects include KDM/finish changes to
theta and the observation temperature/humidity conversions.

The native source calls `microphysics_zero_outa` between the driver and finish.
It operates on all `moist` masses, whereas the prior finish-only helper needs
only theta/QV/QC. Extending the *handoff* to QC/QI/QS therefore requires the
additional mass cleanup. Small condensate removal is not compensated by a
new water or latent-heat transfer here: it reproduces the selected host map.
Its removed mixing ratios must not be advertised as a closed water budget.

## First-order composition

Write `s=S(X,r)`, `F=G(X)`, `y=K(s,F)`, `z=Z(y)` and
`a=R(s,z)`, where `r` contains the ten remaining kernel inputs. Define
`X_after=(a.T_NEW_AFTER,z.QV,X.MU,X.PH)` and evaluate EOS on `X_after`.
The observation state contains finished theta, cleaned QV, the recomputed
full pressure, PH+PHB, dry density and cleaned QC/QI/QS plus NC/NI.

The derivative must contain the direct finish term `R_s ds` as well as
`R_z Z_y (K_s ds + K_F dF)`. Observation cloud cotangents also enter the
kernel outputs directly; they cannot all be routed through the five finish
diagnostics. EOS/pressure, geometry, Exner temperature, unit conversions,
moving partial-layer interpolation and optical-density paths are included.

`harness/native_microphysics_obs.py` exposes a first-order value/JVP/VJP
adapter with an explicitly owned C handle. NumPy buffers serialize values
and first-order products between stages; no higher-order Torch graph crosses
the C ABI. Every recorded handle must be closed, including failure paths.
`harness/verify_microphysics_obs_ad.py` supplies the actual external observation
operator and independent full-composition central differences.

## Validation and attribution

Before execution the verifier binds the trace, executed namelist, endpoint
checkpoint, isolated library/build manifest, public sources, RTTOV executable,
coefficient/calibration data and copied template inputs by SHA-256. Historical
Fortran shim/test hashes in the library manifest are reported separately;
the experiment calls C directly and checks the unchanged C++ sources.

Each representative direction has a JVP/K/cost product and a separate VJP
product. Every central difference reruns prep, KDM, cleanup, finish, diagnostic
EOS, profile construction and actual RTTOV. One common epsilon must satisfy
every retained BT channel and the final cost. The unchanged gates are
`dot_rtol=1e-10`, `FD_atol=1e-8`, `FD_rtol=3e-5`. Trials preserve the exposed
cleanup/finish signature, cloud fraction and quality support. Internal kernel
branch and substep schedules are not fully exposed by this ABI; independent
differences remain necessary even when the transpose test passes.

Separate synthetic tests cover the adapter's routing/transpose, cleanup
thresholds and number identity. They do not replace native/RTTOV evidence.
The prior f32 replay checks are reused when loading the native case; fp64
outputs are a continuous lift, not derivatives of f32 rounding or a claim of
raw-bit equality with a changed host run.

## Scope retained

The same MU/PH are carried across this isolated physics application. The
diagnostic EOS/P8W endpoint is coherent for that defined map, but it is not a
complete WRF end-of-step forecast. The source-reconstructed PH/MU staging and
P8W assumptions from the prior experiments remain. No native integration,
optimizer, radiation or RK step is run by this verifier.

NC/NI are passed unchanged by the legacy raw kernel boundary. The optical
mapping uses the Registry-declared dry-number convention and explicit live
dry density. Composition tests this conditional mathematical convention; it
does not settle legacy raw-kernel number units or number conservation. Raw
CCN, rain and graupel are not new optical slots. Process attribution and
applied mass/number/energy budgets are separate from state/cost derivatives.

KO nominal-slot timing and model-stage time are recorded separately; archived
pixel acquisition time is unverified. Fixed gases do not implement ozone-state
assimilation. The prior 2–3% disagreement when moving the entire reference and
native pressure profile remains unresolved and outside the fixed-reference
controls. No HVP, full-host/retained-memory adjoint, unattended cycling or
forecast-skill claim follows from this local composition.
