# Native column prep and applied-tendency derivative evidence

## Result and scope

The selected native preparation map now supplies state-dependent dry theta and
all four forcing fields to the existing fp64 KDM/cleanup/finish first-order
operators. The saved second-step native 39-layer column passes independent
directional differences and JVP/VJP dot checks for moist theta, QV, total dry
column mass, interface geopotential and their mixed direction. This is an
offline column composition; NativeLiveStepper still has no full-host AD.

Base: PR #428 head `45c7198c72ba74eca4886381da4aa16fd9cb2b79`. No new native
integration, RTTOV call, optimization or accepted posterior was produced.
Previously demonstrated two-step forward carry and kernel/finish derivatives
are reused rather than rerun as new completion gates.

## Data, source and execution attribution

The saved `TWO_STEP_SAVED_DA` case has a 234×282 domain, 39 mass levels and 40
interfaces, 5 km spacing, dt=20 s, one MPI rank/thread and radiation every step.
The analysis increment was applied once to column (156,21); the second step
had an empty command. It was a stored unaccepted diagnostic posterior. The
full native domain was integrated by the historical experiment, whereas this
new derivative campaign evaluates only that one column offline.

`saved_prep_audit.json` pins six active private Fortran sources before/after,
the trace, checkpoints, object and library/executable of the saved experiment.
It records `calc_p_rho_phi`, `moist_physics_prep_em`, mass-phase assignments and
the REAL4 vspow path. The object has FMADD instructions and logf/powf/vspow
dependencies. Raw-bit closure establishes the selected f32 profile on this
platform; it does not certify every compiler or rebuild. The historical native
executable used an incremental build with reused archive members.

`native39_prep_ad.json` pins 14 inputs/public helpers before and after its final
run. `manifest.json` identifies Python 3.10.11, Torch 2.13.0, the isolated
research library (`3e968dcd…`), exact source hashes and system libm resolution.
Eleven files in the prior kernel-build manifest are unchanged. The two changed
Fortran shim/test sources are the prior PR #428 error-contract correction, not
a new change to the C++ kernel used here. Operational host executable and
installed library hashes remain unchanged. No private source/build is copied
into the public implementation.

## Native f32 value and phase checks

| Check | Step 1 | Step 2 |
| --- | ---: | ---: |
| TH/DEN/PII/P/DELZ, five fields ×39 | 195/195 raw bits | 195/195 raw bits |
| Volume perturbation AL from PH/PHB and MU_2+MUB | 39/39 | 39/39 |
| Finish-post T/Q to endpoint checkpoint | 39/39 each | 39/39 each |
| Finish-post theta through EOS to endpoint P+PB | 39/39 | 39/39 |
| Pre-MP pressure versus endpoint P+PB | 14/39 equal | 30/39 equal |
| Wrong-phase MU_1+MUB reproduces AL | 14/39 | 14/39 |

Pre-MP and terminal pressure differ at 25 and 9 levels respectively (maximum
2.5234375 and 1.041015625 Pa). The loader reconstructs pre-MP pressure from
pre-finish theta, instead of substituting terminal pressure.

Pre-finish theta and MP QV are directly traced. PH_2/PHB, mass and hybrid
coefficients come from the matching completed-step checkpoint. The selected
nonhydrostatic source branch reads but does not assign PH/PHB. Output closure
and the source phase trace support this join; a complete prep-entry operand
snapshot was not newly captured. `MUTS` is reconstructed from MU_2+MUB, not
directly read from a MUTS trace.

The loader fails on unsupported options, incomplete native columns, wrong
character Times, fractional-second endpoints that Times cannot represent,
non-binary32 or packed checkpoint data, and failed AL/post-EOS/TQ closure.
Only the explicitly supplied namelist is read and hashed; there is no implicit
sibling configuration lookup.

## fp64 derivatives

The primitive maps native theta_m perturbation, QV, scalar MU and all 40 PH
interfaces to TH/DEN/PII/P/DELZ. Its fixed coefficients/base geopotential and
native binary32-promoted constants are not controls. Gamma and kappa remain
independent. Auxiliary hybrid L/U pressures are not RTTOV interface pressures.
At fixed theta_m, QV affects recovered dry theta, not this EOS pressure.

| Direction | Prep dot relative error | Composed dot relative error | Composed FD maximum tolerance ratio |
| --- | ---: | ---: | ---: |
| theta_m | 2.54e-16 | 3.06e-15 | 0.01031 |
| QV | 0 | 2.57e-16 | 0.11309 |
| MU | 0 | 8.32e-13 | 0.12936 |
| PH interfaces | 1.86e-16 | 1.13e-12 | 0.13674 |
| mixed | 1.91e-16 | 1.53e-14 | 0.00949 |

The composed map is `R(S(X), Z(K(S(X),F(X))))`. It includes all forcing
directions, QV's direct KDM identity, cleanup pullback and the direct old-state
finish derivative. A uniform PH shift has exactly zero JVP; the PH adjoint sum
is -3.47e-18. Synthetic tests independently check interface signs, scalar
equations, Torch autograd, field routing and the direct QV pullback.

Criteria were declared before evaluation: dot relative error ≤1e-10 and each
scaled output's FD error ≤1e-9+3e-6×scaled signal. One common epsilon must pass
every output field; nine epsilons are examined. All five composed directions
select epsilon=0.01, and each also passes at least one other epsilon. Prep's
maximum FD ratio is 0.00184. Finish/cleanup branch signatures must remain
unchanged; private kernel integer schedules are not exposed by this ABI.

Omitting forcing directions changes the theta_m-direction H_RATE JVP by up
to 2.56e-6 K/s (the direction amplitude is specified in the verifier). This is
a derivative-path ablation, not another native integration or cost sensitivity
experiment. Per-output ablations for theta_m, MU and PH are retained in JSON.

## Reproduction and limits

Use `python -m harness.verify_native_prep_ad` with explicit `--trace`,
`--namelist` (the saved executed namelist.output), matching `--checkpoint`,
`--library`, `--step 2 --i 156 --j 21 --levels 39 --xland 2`, and a new
`--output`. The machine-readable report contains every resolved path/hash.
Public tests require no private host; native evidence reproduction additionally
requires the saved private trace/NetCDF and the isolated fp64 library.

Focused prep/finish and adapter/loader checks: **58 passed**. Final full local
harness: **2,521 passed, 59 skipped, 309 local-marked deselected** (98.42 s).
Fake adapter fixtures prove only
chain-rule/refusal mechanics; they are distinct from the actual 39-layer run.
The native run uses Torch 2.13; CI's pinned Torch 2.8 is a separate environment.

This work does not differentiate the evolution of winds, mass or geopotential
through dynamics/RK, retained tendency memory over time, radiation, RTTOV
profiles/pressure/cost, or an assimilation loop. It does not certify all ten
other native kernel state directions, number units/budgets, balance, HVP or
forecast skill. Legacy/raw native number coordinates are preserved. The prior
synthetic NCCN=1e9 raw dot residual (~1.905e-9 versus a 1e-10 goal) remains an
unresolved numerical limitation; this campaign does not fix or relax it.
