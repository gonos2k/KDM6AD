# Applied thermodynamic finish derivatives

`oracle/kdm6/native_finish.py` supplies a continuous fp64 lift of the selected
`use_theta_m=1`, `no_mp_heating=0` finish expression, plus explicit analytic
JVP/VJP operators. `harness/verify_native_finish_ad.py` connects it to the
independent state/forcing kernel ABI added in PR #427. It reuses saved native
inputs; no host integration or observation optimization is performed.

## Executed boundary

For the captured interior column, the active source order is

```
cached pre-MP dry theta/QV/QC
        |                     K(s,F) -> raw MP_OUTPUT
        |                                   |
        |                     post-MP zero_outa, Z
        |                                   |
        +----------------> moist-theta finish R
                              |
                 T_NEW_AFTER, H/QV/QC rates, TH_PHY_M_T0
```

The native configuration has `MP_ZERO_OUT=2` and binary32 threshold
`0x322BCC77` (approximately `1e-8`). For the thermodynamic fields, `Z` leaves
theta unchanged, clamps QV to nonnegative values, and sets QC below the
threshold to zero. This is a separate operation after KDM. Boundary-only
`zero_outb` does not affect the selected interior column `(i=156,j=21)`.
The Python cleanup represents only theta/QV/QC consumed by this finish;
it does not supply all moist/tracer fields of a complete host state.

Here the old state is the physics-call entrance, after the host's preceding
dynamics/preparation, not the raw preceding restart or analysis control. The
adapter does not differentiate that preceding host transition.

`FINISH_PRE.H_PRE/QV_PRE` match `MP_INPUT.TH/Q` bitwise, and the captured new
theta/QV agree with the corresponding post-kernel/cleanup values. QC is not
recorded directly in `FINISH_PRE`: its handoff is supported by source order,
rate replay, and checkpoint comparison. In saved step 1, a tiny positive QC
at level 2 is removed by cleanup. Its difference rounds away in QC_RATE, so
QC_RATE alone cannot establish that cleanup occurred. The checkpoint and
source are necessary evidence. Both native steps remain the prior campaign;
they were not rerun for this change.

## Continuous finish map

`ThermoState(th,qv,qc)` before/after contains full dry potential temperature
(K) and the native dry-mass mixing ratios (kg/kg). `FinishConfig` freezes
`dt`, host alpha, reference `T0`, and `mp_tend_lim`. In the saved case these
are 20 s, binary32 alpha `0x3FCDDED2` promoted exactly to fp64, 300 K, and
10 K/s. Number-concentration coordinates are not changed.

The finish domain requires finite fp64 tensors with equal shape/device,
positive theta and nonnegative QV/QC. Raw negative QV/QC are accepted by the
separate cleanup where its selected mode corrects them. The direct forward
expression preserves live Torch graph dependencies; the analytic operators
return the two partials for composition. The C ABI adapter uses explicit
value serialization and first-order products, not a live Python graph across
the opaque kernel handle.

Write the old/new thermodynamic inputs as `(theta0,q0,c0)` and
`(theta1,q1,c1)`, with the new input already cleaned. Define

```
m = clip(theta1-theta0, -mp_tend_lim*dt, +mp_tend_lim*dt)
A = 1 + alpha*q0
B = 1 + alpha*q1
D = q1-q0
N = m*B + alpha*D*theta1
Tfull = theta0*A + N
```

The five result fields are

| Output | Definition | Unit |
| --- | --- | --- |
| `t_new_after` | `Tfull-T0` | moist-theta perturbation, K |
| `h_rate` | `N/dt` | stored moist-theta heating memory, K/s |
| `qv_rate` | `(q1-q0)/dt` | kg/kg/s |
| `qc_rate` | `(c1-c0)/dt` | kg/kg/s |
| `th_phy_m_t0` | `Tfull/B-T0` | dry-theta diagnostic perturbation, K |

This preserves the actual cross term rather than replacing finish with
`theta1*(1+alpha*q1)`. The continuous fp64 expression is distinct from the
rounded f32 function: `harness/native_finish_replay.py` retains the sampled
FMADD/FDIV sequence, including the perturbation/T0 round trip. Its existing
value replay is unchanged. The new derivative does not differentiate
binary32 rounding or certify the arithmetic of another host compiler.

## Tangent and adjoint composition

Let `g=1` strictly inside the temperature clip and `0` on the clipped side.
The derivative of the applied increment is

```
dm = g*(dtheta1-dtheta0)
dN = B*dm + alpha*m*dq1 + alpha*(dq1-dq0)*theta1 + alpha*D*dtheta1
dTfull = A*dtheta0 + alpha*theta0*dq0 + dN
```

The other outputs follow by differentiation of the five definitions. In
particular, the old QV/QC derivatives include `-I/dt`; the old theta/QV
dependence of heating and moist-theta is also retained.

With `P` selecting theta/QV/QC from the twelve kernel state fields, the
executed local composition is `Phi(s,F)=R(Ps,Z(PK(s,F)))`. The adapter computes

```
dPhi = R_old*P*ds + R_new*Z_y*P*(K_s*ds + K_F*dF)

uK = P^T*Z_y^T*R_new^T*u
gs = P^T*R_old^T*u + K_s^T*uK
gF = K_F^T*uK
```

The direct old-state adjoint is added once. Skipping it or treating the
kernel output derivative divided by dt as the tendency derivative is incorrect.
The explicit analytic finish operators are tested against Torch autograd,
independent finite differences, scalar expectations, and adjoint identities.
An identity-kernel test checks zero rate tangents when cleanup is inactive.
A separate below-threshold QC test checks the surviving old-state `-I/dt`.

## Branches and applied amounts

At nonzero temperature-clip ties the function is not differentiable. The
explicit operators choose the clipped-side derivative zero, with one-sided
tests; central differences crossing a tie are not accepted as evidence.
A zero temperature limit is a constant clip with zero derivative.

At a positive QC cleanup threshold the strict host rule is discontinuous.
Explicit cleanup JVP/VJP reject exact threshold equality. At a zero threshold,
QC and mode-2 QV select the zero-side derivative at zero. The verifier records
cleanup/clip signatures and accepts finite-difference trials only when the
selected branches are preserved. Kernel integer substep schedules and other
internal limiter signatures are not exposed by the existing ABI.

Differentiating the cleanup forward expression directly with Torch at a
positive QC-threshold equality can produce a formal branch value; no actual
derivative exists there. The explicit derivative APIs enforce the rejection.

Cleanup is an applied sink/source, not a conservation correction. For mode 2,
let `removed_qc=qc_raw-qc_clean` and
`qv_correction=qv_clean-qv_raw`. The two-field applied change is

```
dt*(QV_RATE+QC_RATE)
 = (qv_raw+qc_raw-qv0-qc0) + qv_correction - removed_qc.
```

This identity does not establish the complete hydrometeor water, enthalpy, or
number budget. It distinguishes host cleanup from the kernel-applied amount.

## Fortran error-output preservation

The public shim's real array outputs use `INTENT(INOUT)` at both the
`bind(C)` and friendly-wrapper layers, including the analogous legacy entries.
Handles retain `INTENT(OUT)` and their deterministic null-on-error behavior.
This preserves a caller's defined output values on C validation/thread failures,
including compiler-created temporaries for noncontiguous output sections.
It neither initializes undefined caller buffers nor promises rollback after an
internal error. Fortran callers must be rebuilt with the updated module to
receive the new argument-intent semantics; changing a shared library alone
does not change an old caller's packing code.

This follows the undefinition rule in [J3/18-007r1, 19.6.6](https://j3-fortran.org/doc/year/18/18-007r1.pdf)
and the copy-in distinction documented by [LLVM Flang](https://flang.llvm.org/docs/ArrayRepacking.html).
The isolated GFortran before/after test and its compiler scope are recorded in
the [experiment report](../harness/evidence/applied_finish_ad_2026-10-21/REPORT.md).

## Scope and reproduction

Run the offline verifier with the intended research library and saved trace:

```sh
python3 -m harness.verify_native_finish_ad \
  --library /absolute/research/libkdm6_c.dylib \
  --trace /absolute/saved/native_trace.hex \
  --namelist /absolute/saved/namelist.output \
  --step 2 --i 156 --j 21 --levels 39 --xland 2 \
  --output /new/finish_ad_report.json
```

Inputs and executed helper sources are hashed before/after evaluation. Each
direction uses a common epsilon across all five output-field error gates.
Zero native directions are explicitly untested. The selected native column
has no active temperature clip, and its post-MP QC is below threshold at all
39 levels; synthetic cases cover the other local branches.

This is a first-order kernel/thermodynamic-application boundary. Host prep,
`F=G(X)`, RK, full checkpoint/replay, all other moist fields, RTTOV pressure
and cost derivatives, and higher derivatives remain separate work.
`NativeLiveStepper` remains value-only. In this configuration the host consumes
`H_DIABATIC` with mass/map factors in its temperature tendency; the explicit
water-rate RK-add option is off, while the updated water states still persist.
The new map does not isolate or differentiate the resulting RK temperature
increment. It does not assert balance, forecast skill, or full-domain DA.

The subsequent, separately bounded column prep composition is described in
[NATIVE_PREP_AD.md](NATIVE_PREP_AD.md). It supplies state-dependent forcing from
moist theta, column mass and interface geopotential, without changing this
finish map or declaring a full-host adjoint.
