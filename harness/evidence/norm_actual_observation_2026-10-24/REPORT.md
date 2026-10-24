# norm_actual through native profile and actual RTTOV cost

This connects the already bounded candidate to the existing observation chain
without changing any physics source/default/install. The selected-column
adapter executes the full original B512 map; the other511 columns stay fixed.
Inputs retain 39 native mass levels and40 interfaces. No host timestep,
optimization, whole-domain rerun or forecast improvement is claimed.

## Admitted native(131,88), chunk40 row8

The same MP137 endpoint00:00:40, native prep variables/hybrid geometry, matched
KO observation bundle and seven channels10–16 are used. Target prep agrees
with its original packet within the previously declared scalar/vmap envelope.
The derived dry-number qualification is source-bound to that captured request,
checkpoint, namelist and coordinates; it does not certify/migrate historical
host number payloads. The initial dry coordinates remain fixed during trials.

The operator is native prep → live-density number conjugation around the selected full-B512
norm_actual K → all-mass cleanup/thermo finish → post-finish EOS → native
pressure/profile/cloud → actual RTTOV-K → Huber cost. The implementation
reuses the existing compositional routines; the finish old-state pullback and
live P/P_HALF paths remain present. Target surface and geometry overlays are
explicit; fixed template/gas/emissivity/upper-reference assumptions remain.

Baseline cost is **135.12287450638345**, with all7 channels quality0 and a
nonempty seven-channel mask. Final verification uses19 KDM and19 actual RTTOV
calls: one base plus3 directions×3 epsilons×two central endpoints.

| Native direction | Cost directional derivative | Dot relative error | Best common BT/cost FD ratio |
| --- | ---: | ---: | ---: |
| theta_m | +0.30506959380048193 | 5.46e−16 | 0.0076830 |
| QV | −0.2936013060648119 | 0 | 0.00016524 |
| Mixed | +0.011468287735670102 | 2.61e−14 | 0.00223484 |

All3 direction gates and all9 epsilon trials pass the existing
`1e-8+3e-5*signal` BT/cost criterion and dot threshold1e−10. Each accepted
trial retains the same channel mask, cloud fraction and cleanup/finish branch
signature according to the pinned executed controller. Public endpoints retain
BT, cost and masks, but not endpoint cloud-fraction or branch-signature arrays;
those two stability comparisons cannot be independently replayed from the
published endpoints alone. These are T/Q directional checks, not unrestricted moment/geometry,
full-host/RK, precipitation/budget or HVP validation.

Direct RTTOV pressure K is active. Removing only P/P_HALF K while retaining
pressure-mediated T/Q changes makes the mixed cost direction
**+0.05882164969053335** instead of+0.011468287735670102; the direct pressure
contribution is−0.047353361954863546. This is a derivative decomposition at
this point, not evidence of assimilation/forecast benefit.

## Rejected native(113,76), chunk34 row254

The mapped KO observations themselves are finite and source-quality-valid.
The candidate simulation instead exceeds RTTOV's water-vapour regression
limit: the log reports7.7329 ppmv at61.4771 hPa against limit7.6890. All7
RTTOV channel qualities become1, so no channel is admitted. The earlier
feasibility controller's all-zero-mask cost0 is **not a fit or validation**.
It is explicitly rejected in `rejected11376.json`, with the original log.
No humidity clipping, coefficient relaxation or observation substitution is
used to make this point pass. Its failure is separate from the valid131/88
case and the earlier raw-direction clamp counterexamples.

## Provenance and assumptions

The executable/coefficient/calibration and all model, helper and template
source pins are in the final prepared/result receipts. The actual diagnostic
K library is the frozen v6-based `e412328b…` isolated link. The final
controller is archived as executed; it invokes the existing algorithms and
the new selected-column adapter. Public source/data replay is distinguished
from rerunning a private CPP/RTTOV installation.

Geometry uses the target native latitude/longitude/elevation and source-bound
AMI viewing angles. Native checkpoint skin T, T2, Q2, wind/rotation, land/ice
and snow are overlaid. Salinity35, foam0, FASTEM, fetch0, spectral emissivity,
upper reference and trace gases remain explicit fixed assumptions. Thermal
solar=false is checked. Pixel UTC and independent per-pixel navigation remain
unverified; source times are nominal00:00, scene00:00:33, endpoint00:00:40.

Call accounting retains exploratory attempts:1 KDM before a unit-label error
(no RTTOV),2 feasibility KDM/RTTOV calls,19 exploratory FD calls each, and19
final source-pinned calls each: **41 KDM and40 RTTOV in total**. The final
certificate is only the19/19 run. No source data or physical formulas were
changed between exploratory/final checks. Model/MU/PH dynamics and full-host
cycling remain outside this operator.

## Final API review corrections

The archived executed adapter is pinned by the prepared receipt. Final review
added a constructor guard: a backend without timestep metadata is bound to
the established20-second contract; a different timestep requires explicit
matching backend metadata. All executed calls used20seconds. No forward or
derivative arithmetic changed, and no model rerun is attributed to this guard.
The independent public dot replay now uses rounded products plus `math.fsum`
and an explicit binary64 rounding envelope, while preserving the1e−10 dot
gate and the existing BT/cost finite-difference thresholds.
