# QR-only actual-departure candidate on two original B512 blocks

This is a separate fp64 research map built from main593ec50b and the exact
frozen v6 `norm_actual` ice overlay. Only main-substep QR mass/fall updates
change. Direct NR/QS/QG/BRS recurrences remain Legacy; re-sloping from changed
QR can change their later trajectories. No operational source/install/default,
full host step, assimilation optimization or whole-domain replay is changed.

## Derivation, source and actual executions

The [contract](../../../docs/ACTUAL_QR_TRANSPORT.md) derives the mass and first-order
map before implementation. The candidate caps departure against entry QR at
all levels, passes the actual departure by the native dry `rho*dz` ratio and
accumulates actual departure rate. No second donor-post-state arrival cap or
larger attempted-fall diagnostic is used. Inputs require positive native
geometry, nonnegative state/work/fall and fixed count metadata. Python oracle
and generated private C++ use the same order; density/depth remain live.

One private production TU, `sedimentation.cpp`, is rebuilt with original flags
including `-ffp-contract=off`. The other13/14 object members remain byte-identical;
the archive symbol index is handled separately. This is a partial isolated
research build, not a clean host rebuild. A preliminary unused build preceded
additional entry guards; no model evaluations used that build. All results
here use `build_final`, its pinned source and library receipts.

Six value calls retain original chunks34/40,512 columns×39 levels,dt20. For
each block the new library's Legacy selector reproduces the frozen response
bytes, while actual-QR trace-off/on responses match each other. Four separate
recording calls verify candidate trace noninterference in selected raw-state,
JVP/VJP and applied-finish products. This is not old/new physics parity and is
not a whole-Jacobian or unrestricted FD certificate.

## QR closure and remaining kernel residual

The actual request's binary64 DEND×DELZ is the fixed code measure. State-delta
products are rounded to binary64, then summed with `math.fsum`. Returned total
precipitation is counted once; snow/ice/graupel subsets are not added again.
QR-only reported precipitation is reconstructed with the unchanged surface
conversion; applied bottom departure is separately measured.

| Witness, native1-based | Previous raw6-water residual | Candidate raw6-water residual | Candidate QR-only residual |
| --- | ---: | ---: | ---: |
| (113,76),chunk34,row254 | +0.005058514420779037 | −1.4988010832439613e−15 | +2.7755575615628914e−17 |
| (131,88),chunk40,row8 | −0.18177156930768423 | +1.6037645303152823e−15 | −2.7328671010212746e−17 |

Units are kg/m² per column, not area-weighted regional mass. All1024 QR
columns pass the fixed arithmetic budget gate. Maximum absolute QR residuals
are2.0816681711721685e−16 and1.3183898417423734e−16. The actual QR state, fall,
departure and arrival at all199,680 step/layer/column records match an independent
Python-oracle replay bitwise. The saved final QR profiles also match the
independently captured post-sedimentation stage bitwise. Outputs are finite
and nonnegative in all six water/four number fields.

Full six-water raw budgets are **not certified closed**: maxima of the remaining
absolute residual are7.422008460553927e−7 and4.1719494005560995e−7. Saved-stage
accounting localizes these to the subsequent `post_micro` total; non-QR
sedimentation plus its precipitation residual is at most1.25e−16/4.30e−16.
This does not identify a named internal process, threshold or cleanup as the
cause. The separately applied offline host cleanup remains separately saved.

Existing moment problems are not repaired. Active QR cells with raw NR=0
number897 and276 in the two blocks, the same counts as the old map. No mass/
number admissibility, number conservation or historical host-unit certification
is inferred. Number source coordinates and dry conversion remain conditional
as previously documented.

## Native observation-cost connection

The repeatable controller reuses prep, qualified number coordinates, full-B512
selected map, cleanup/finish including direct old-state terms, post-EOS native
pressure/profile/cloud, real RTTOV-K and cost. Only admitted native(131,88)
T/Q directions are evaluated. The other511 background columns remain fixed;
there is no B1 substitution, observation replacement, humidity clipping or
coefficient relaxation. Target KO channels10–16, checkpoint surface/geometry
and fixed reference/gas/emissivity assumptions remain source-pinned.

Final observation results, source metadata and independent public replay are
recorded with `observation_*` files. Endpoint eligibility compares actual RTTOV
quality/masks, cloud fraction and finish/cleanup signatures. Candidate QR cap
masks and KDM integer schedules are not recorded at these endpoints, so their
full-kernel branch preservation is **not certified**. The oracle's branch-
interior/tie tests and selected actual FD comparisons have distinct roles.
Pixel UTC/navigation, number basis, full-host/RK/HVP and forecast-skill limits
remain open. This candidate is not an operational adoption or optimization result.

### Actual cost result and limits

The final source-pinned run made19 KDM and19 RTTOV calls. All seven channels
are quality0 and admitted. Baseline Huber cost is135.1228745063671; the prior
norm_actual cost was135.12287450638345. Difference−1.63e−11 is not a meaningful
observation-fit gain. Both computations remain warm relative to the observed
BT. The primary achievement here is candidate mass accounting and a consistent
selected first-order observation connection.

| Native direction | Cost derivative | Dot relative error | Largest BT/cost FD ratio over3 epsilons |
| --- | ---: | ---: | ---: |
| theta_m | +0.30506959378527665 | 1.09e−15 | 0.04355446 |
| QV | −0.2936013061994755 | 0 | 0.00170711 |
| Mixed | +0.011468287585801096 | 6.05e−15 | 0.00948389 |

All3 directions and all9 trials pass the unchanged `1e-8+3e-5*signal` BT/cost
criterion and `1e-10` dot gate. Endpoint quality/masks, cloud fraction and
finish/cleanup signatures are public arrays and agree with baseline. This
replaces the previous controller-only eligibility evidence for those fields;
it does not extend eligibility to unrecorded internal QR caps, all limiters
or integer KDM schedules. Pressure K, old-state finish, cleanup and EOS remain
part of the actual chain.

The code-readability changes did not require replaying the old M/H campaign.
Their old QR arithmetic replay made zero model calls. One early new-runner
preparation attempt failed on renamed receipt fields before any KDM/RTTOV;
its source/log is preserved. Required field names were restored and a real
prepare-only check passed with zero forwards. The successful final run has
its own frozen source pins and consistent one-place experiment definition.
Total new evaluated KDM calls are29 (6 value,4 selected AD trace comparisons,
19 observation calls), with19 RTTOV calls,0 native host/DA/optimization calls.
