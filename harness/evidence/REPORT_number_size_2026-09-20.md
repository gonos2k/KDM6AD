# Conditional number-to-size diagnostic on the retained liquid column

This follows PR228's completed finite-width optical-path diagnosis. It addresses
the unresolved meaning of particle number before any independent radiation
accuracy comparison. It does not change production physics, ABI, QC, tolerances,
or the native 5 km model grid. The liquid observation/cost gate remains **0/9**.

## Contract and scope

The earlier source audits remain applicable:
`FINDING_number_basis_is_inherited_from_wdm6_v1.md` and
`FINDING_number_mass_basis_v1.md`. Registry declares number per kilogram; host
mixing ratios use dry mass. The kernel slope instead combines raw number with
`forcing.rho * q`. The bridge's water content uses frozen `rho_d * q`, with
`forcing.rho = rho_d * (1 + background.qv)`. The original background, rather
than the evolved trial humidity, defines that frozen density.

For the fixed cloud generalized-gamma shape `mu=2`, moments are

    M_j = N Gamma(1 + j/(mu+1)) / lambda^j,
    C = (pi rho_water/6) M_3,
    r_eff = M_3/(2 M_2).

Here N is volume number and C is liquid mass per volume. If the stored operands
q and n are both per dry kilogram, a coherent conversion is C=rho_d*q and
N=rho_d*n. Density then cancels from C/N. Converting only n while retaining
the moist-density mass operand leaves a separate factor (1+background.qv).

Three interpretations must therefore remain distinct:

1. **Executed legacy diagnostic:** raw n and `forcing.rho*q`.
2. **Number-only conversion:** `rho_d*n` and `forcing.rho*q`; this is a partial
   conversion experiment, not a physically completed correction.
3. **Coherent dry moments:** `rho_d*n` and `rho_d*q`, conditional on both stored
   operands really representing quantities per dry kilogram.

None of these post-processing alternatives repairs the already evolved model
trajectory or establishes the physical meaning of its stored n. That requires
initialization, dynamics, all microphysical rates and applied transport on one
declared basis. No isolated sedimentation or observation-boundary fix is made.

## Executed precision and gates

The current cloud slope uses the scheme's f32-derived PIDNC and reciprocal
exponent, evaluated through fp64 exp/log. The active slope is unbounded; the
inactive gate substitutes 1/lamdacmax. Effective radius is then limited to
2.51–50 micrometres, followed by the observation builder's 2–52 micrometre
diameter limit. Thus an unchanged limited diameter does not establish that
unlimited sizes, number semantics or their derivatives are unchanged.

The ideal generalized-gamma moment identity and the executed mixed-precision
formula are separate comparisons. Real-arithmetic density cancellation is not
a claim of bit equality with the operational f32 host.

Authoritative public implementations are `oracle/kdm6/cloud_dsd.py`,
`oracle/kdm6/rttov_bridge.py`, and `oracle/kdm6/obs/model_profile_builder.py`.
The local host's `effectRad_kdm6` also uses raw nc in the active slope: its
`rnc=nc*rho` temporary contributes to the presence gate, not that numerator.

## Fixed-column measurement

One offline 20 s KDM baseline step recovered the retained accretion alpha=0
state from the existing forecast frame at 2025-07-19 00:00:20 UTC. There were
**zero new RTTOV calls and zero counterfactual KDM integrations**. The local
calculation used Python 3.10.11, PyTorch 2.13.0 and NumPy 2.2.6, separately from
the Python 3.12 replay tests. No external atmospheric data were acquired.

All nine retained profile vectors (P, P_HALF, T, Q, liquid/ice content and
diameter, cloud fraction) matched exactly. Four hydrometeor vectors also matched
the retained PR228 input text exactly. These are local extraction checks,
recorded in the public JSON; the standalone replay does not rerun the private
model. It consumes published pressure/content/diameter tokens and all 39 layer
operands. Hashes identify the private source and extractor, not independent
authentication of their contents.

The table gives final liquid **diameter**, in micrometres. Layers use RTTOV's
1-based top-down convention; they correspond to native bottom-up layers
14, 12 and 11 respectively.

| User layer | Pressure hPa | Legacy | Number-only conversion | Coherent dry pair | Dry vs legacy |
|---|---:|---:|---:|---:|---:|
| 25 | 604.449 | 7.23977729 | 7.94770530 | 7.92810788 | +9.50762% |
| 27 | 685.311 | 6.92371632 | 7.33927916 | 7.31676733 | +5.67688% |
| 28 | 723.445 | 6.95681470 | 7.26883640 | 7.24370574 | +4.12389% |

These three layers were the active accretion support in the earlier experiment.
The number-only diameters exceed the coherent dry-pair values by 0.247189%,
0.307675% and 0.346931%, respectively. This is consistent with the residual
moist/dry factor, not additional evidence about which stored-number meaning is
correct. The dry-pair column here retains the scheme constants and exp/log
evaluation. The JSON separately provides ideal positive-pair moment radii using
pi*rho_water/6 and an exact real-arithmetic cube-root exponent.

All three diagnostics have 12 active cloud-slope layers. Only five have radius
above the lower limit; seven active layers still have 5.02 micrometre diameter.
The five unrestricted diameters change by 2.80534–9.50762% between legacy and
coherent dry-pair interpretations. Across all 39 layers, 34 hit the lower
radius limit and none hits either upper limit. An unchanged limited diameter
therefore conceals some changes in the underlying radius.

Counterfactuals retain the existing numeric q and number gates (1e-15 and .01).
For the dry-pair size-only diagnostic, the operands are C=rho_d*q, N=rho_d*n
and unit mass-density multiplier. These gate numbers are **not** claimed to be
unit-corrected physical thresholds. All three active sets coincide in this
case; a policy for converted thresholds remains part of the open unit contract.

## Replay and remaining work

Run `python harness/replay_number_size.py`. This uses only the standard library:
it rechecks the 39-layer operands, density relation, explicit pressure vectors,
content/diameter tokens, gates and three size calculations. Scalar-versus-Torch
arithmetic uses a fixed 2e-13 relative comparison (not a new scientific gate);
the recorded extraction's exact profile comparisons remain a separate claim.
The result explicitly leaves physical-number reconciliation and observation
acceptance false. No new JVP, BT, optical coefficient or transport result is
inferred from these size differences.

The next contract measurement must pair initialization/dynamics values and
microphysics entry/exit on one declared mass/volume basis, including converted
floors and applied transfer budgets. Agreement of two radiation solvers given
the same input size would not resolve this upstream ambiguity. Independent
radiation accuracy, nonzero transport and timestep convergence remain open.
