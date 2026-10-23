# Native column preparation and its first derivatives

`oracle/kdm6/native_prep.py` implements a continuous binary64 column map for
the selected native `non_hydrostatic=true`, `hypsometric_opt=2`,
`use_theta_m=1` path. It provides values, analytic JVP and analytic VJP. The
offline adapter in `harness/verify_native_prep_ad.py` connects it to the existing
state+forcing KDM ABI, post-microphysics cleanup, and applied finish operator.
It is not a complete host timestep or an implementation of its RK adjoint.

## Boundary and units

The live inputs are native moist-theta perturbation (K), dry-air QV mass ratio
(kg/kg), total dry column pressure mass `MUTS` (Pa), and perturbation interface
geopotential `PH_2` (m²/s²). There are L mass levels and L+1 interfaces. For the
saved case L=39. Base geopotential and hybrid-coordinate coefficients are fixed;
their gradients are explicitly outside this interface. Model constants are
fixed, separately promoted native binary32 values. In particular gamma and
kappa are independent captured constants, not replaced by exact reciprocal
thermodynamic identities.

The authoritative private source is
`dyn_em/module_big_step_utilities_em.F`: `calc_p_rho_phi` produces volume and
pressure; `moist_physics_prep_em` supplies dry theta, density, Exner and thickness.
`solve_em` passes full `p_phy=p+pb` to microphysics. These private files are not
shipped by the public repository and are absent from its AST graph.

## Forward equations

Let T=theta_m_pert+T0, A=1+alpha*qv, Phi=PH+PHB, D=diff(Phi),
H=c3h*mu+c4h+ptop, L=c3f_lower*mu+c4f_lower+ptop, and
U=c3f_upper*mu+c4f_upper+ptop. Then

```
ell = log(L/U)
V = (D/H)/ell
theta_dry = T/A
rho = 1/V
p = p0 * (Rd*T/(p0*V))**gamma
pii = (p/p0)**kappa
delz = D/g
```

`L/U` are auxiliary hybrid mass-coordinate pressures used in the volume
formula. They are not a replacement for actual native RTTOV interface
pressures. No observation-profile pressure derivative is implemented here.
At fixed prognostic moist theta, QV changes recovered dry theta but does not
directly change this EOS pressure. A control that holds dry theta fixed while
changing QV needs the preceding moist-theta coordinate transform as well.

## JVP and VJP contract

With `M=-c3h/H-(c3f_lower/L-c3f_upper/U)/ell`,

```
dV = V * (diff(dPH)/D + M*dmu)
dtheta = dT/A - alpha*T*dqv/A**2
drho = -dV/V**2
dp = gamma*p*(dT/T-dV/V)
dpii = kappa*pii*dp/p
ddelz = diff(dPH)/g
```

VJP includes the contributions from both adjacent layers at every interface;
the first and last interface have their own terms. Uniform PH shifts have zero
JVP. Geometry, shape, dtype, device, finite values, positive volumes and hybrid
pressure ordering are checked in a separate value-only preflight. Computational
tensor operations remain connected to the Torch graph. A positive-volume
continuous map has no limiter branches; downstream cleanup/finish branches
remain subject to their existing conventions and discontinuity refusals.

## Composition with KDM and finish

Define S(X,rest)=(theta_dry(X),qv,rest) and F(X)=(rho,pii,p,delz).
The adapter evaluates `R(S, Z(K(S,F)))`. Its JVP supplies both S_X*dX and
F_X*dX to K. In reverse it adds K's direct QV cotangent to the QV contribution
from recovered dry theta. `KernelFinish` already includes the direct R_s
term and the cleanup pullback. The remaining ten KDM state fields retain the
captured legacy/raw number and mass coordinates; their directions are not
certified by the native prep campaign.

The adapter carries NumPy values and explicit first-order products across an
opaque ABI. It does not promise higher derivatives through that boundary.
`NativeLiveStepper` remains value-only; no full-host derivative capability is
declared by this work.

## Value replay and attribution

`harness/native_prep_replay.py` checks the selected f32 execution profile against
saved MP input values before derivative verification. Native arithmetic replay
and the continuous f64 lift are different checks: f32 rounding/FMA is not
differentiated. The f32 profile's libm and compiler attribution is restricted to
the saved arm64 execution. It is not a universal compiler-independent parity
claim.

The saved trace directly supplies pre-finish moist theta and MP QV. Other
operands are reconstructed from the corresponding completed-step checkpoint.
Their phase validity is checked by source tracing and raw-bit output closure;
they are not represented as a newly instrumented complete prep-entry snapshot.
In particular terminal checkpoint pressure must not be substituted for pre-MP
pressure: finish can change theta before a later EOS recalculation.

Run the verifier with explicit trace, matching completed-step checkpoint,
namelist, isolated kernel library and a new output path. It pins input/helper
hashes before and after, checks all five fields independently, and tests a
common epsilon across every field per direction. Source and numerical evidence
are recorded under `harness/evidence/native_prep_ad_2026-10-21/`.

Full dynamics, time-dependent mass/geometry evolution, horizontal transport,
radiation, RTTOV pressure/profile sensitivity, observation cost, HVP, budgets
and forecast skill remain separate work. Existing native forward carry and
state+forcing/finish evidence is reused; this stage requires no new host run.
