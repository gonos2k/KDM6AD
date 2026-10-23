# Native pressure, cloud profile and RTTOV cost derivatives

This opt-in column path connects native model fields to RTTOV-14 pressure K
and the existing masked Huber observation cost. It preserves all 39 native mass
levels and 40 interfaces. It does not declare a full-host derivative backend or
enable `HostWindow` optimization with an incomplete model transition.

## Native model/profile boundary

`oracle/kdm6/obs/native_profile_builder.py` consumes one bottom-to-top column:
moist potential-temperature perturbation (K), QV (kg/kg dry air), full mass-level
pressure `P+PB` (Pa), and full interface geopotential `PH_2+PHB` (m²/s²).
Thermodynamic constants and FNM/FNP are fixed. Native pressures are not
interpolated onto the historical RTTOV fixture grid.

The selected host's `moist_physics_prep_em` constructs P8W from full mass
pressure. For interior interface k, P8W uses `FNM[k]*P[k]+FNP[k]*P[k-1]`.
At the surface it linearly extrapolates the first two mass pressures in height;
at the top it extrapolates their logarithms using the last two mass heights.
Mass heights are means of adjacent interface heights, with `z=Phi/g`.
The Torch implementation follows this real-valued map, then reverses the native
arrays to RTTOV's increasing-pressure order and divides Pa by 100 to obtain hPa.
This is distinct from prep's auxiliary hybrid C3F/C4F pressures and P_HYD_W.
P8W is not saved in these checkpoints; its connection is source-derived rather
than a newly captured interface-array parity experiment.

RTTOV sets its surface pressure from the final P_HALF. Its K therefore already
contains that surface-pressure contribution; no separate PSFC adjoint is added.
Centre P remains an independent input to the observation/profile boundary.
The temperature and humidity maps are

```
Pi = (P/P0)**kappa
T  = (theta_m_pert+T0) * Pi / (1+alpha*QV)
Q  = ppmv_moist(QV)                 # gas_units=2
```

Thus the temperature pullback includes Exner/pressure and moist-theta/QV terms.
Constants use the captured native binary32 values promoted to binary64.
This is a continuous fp64 derivative, not a derivative of f32 rounding.

## Above-model reference atmosphere

The saved native model top is near 50 hPa. The existing, separately identified
RTTOV reference profile supplies 27 upper layers; it is not model/reanalysis
data and does not replace any native layer. The last upper layer is partial:
its centre is `sqrt(reference_half[U-1]*native_P8W_top)` and its T/Q are
log-pressure interpolated from the fixed reference. These weights remain live
Torch operations. The native 39/40 suffix is appended unchanged.

U and all reference arrays are fixed, with gradients explicitly forbidden.
The native top must stay strictly inside the selected reference bracket, and
the moving partial centre must avoid an interpolation knot. Old fixed-pressure
profile/interpolation defaults remain unchanged. RTTOV's own coefficient-grid
pressure interpolation is differentiated by its pressure-K implementation.
Trace-gas layer values (including ozone and CO2), surface, geometry and the
reference atmosphere's remaining properties are fixed inputs in this objective.
The AMI ozone channel does not imply native ozone-state assimilation.

## Native cloud and density boundary

`native_cloud_profile.py` adds QC, QI, QS, NC and NI through the existing optical
bridge. The explicit live dry-air measure is native `rho_d=1/(AL+ALB)`; it is not
silently inferred from a trial EOS or frozen. Content in g/m³ is
`1000*rho_d*QC` and `1000*rho_d*(QI+QS)`; number-to-volume conversion uses
`rho_d*NC` and `rho_d*NI` before the existing DSD/size calculations.

The input contract interprets NC/NI according to the Registry's `# kg-1`
declaration and selects the existing dry-number optical bridge. This does not
prove that every number field produced/transported by the legacy raw kernel
has a coherent dry-number basis or closes a number budget. Raw CCN is excluded;
its special legacy volume initialization is not relabelled. Operational KDM
defaults, ABI packing and the unresolved raw NCCN stress case are unchanged.

The optical bridge uses its moist forcing coordinate `rho_d*(1+QV)` while
retaining the explicit dry measure for content and moments. This is an optical
mapping contract, not a change to native DEN or a native forward-parity claim.
QC/QI with nonpositive corresponding NC/NI are rejected. Upper layers are clear,
with valid inactive size floors. Existing radius/diameter clamps and the detached
cloud-fraction gate are retained, and FD eligibility requires the same fraction
signature. The legacy VIS/IR slots map QC to liquid and QI+QS to ice; rain and
graupel are not relabelled into those slots.

## RTTOV pressure K and file boundary

`RttovInputConfig.pressure_gradients=True` explicitly opts in. The default false
case preserves the previous config fingerprint and fixed-pressure grid-witness
behavior. Opt-in requires P and P_HALF tensors and their K blocks; missing,
nonfinite or malformed K is refused. The backward contracts every field K with
the channel cotangent, including pressures and cloud content/diameters. Shared
in-memory pressure-grid adjoints are reduced to their original shape.

The external writer currently supports one native profile in this mode. It
writes both pressure files at every trial and enables the actual copied-case
`opts%interpolation%pressure_gradients`. It validates centre/interface
interleaving, source/output separation and duplicate namelist assignments. The
source case is never modified. RTTOV runs in a separate process with a one-thread
OpenMP fence. KMA BT conversion scales all K fields with the same-run radiance
derivative, and its calibration/coef inputs are pinned.

This remains first-order: cached external K does not provide dK/dx for an HVP.
The pressure flag is not a certification of arbitrary pressure directions.
In particular the separate whole-profile pressure counterexample below is
unresolved; the native application keeps the upper reference inputs fixed.

## Verification and limitations

`harness/verify_native_obs_ad.py` runs real RTTOV-K and independent central
differences of both BT and final cost, with explicit clear/all-sky mode and model
time. Its input/source/template/executable hashes must agree before and after.
The primary all-sky evidence uses the saved MP137 20-second checkpoint at
(156,21), including its density and cloud fields. Initial time-zero QC/QI have
zero NC/NI and are not accepted as a native all-sky moment state. A separate
time-zero clear diagnostic is retained.

The observed KO nominal slot is 00:00 UTC; the primary model state is 00:00:20.
The +20 s offset is explicit and KO pixel acquisition time remains unverified.
This is a nominal-slot cost derivative diagnostic, not proof of operational
observation-time matching or window coverage. Sigma=1 K, Huber delta=1 and the
quality/channel masks are fixed for this diagnostic. No new optimization,
native integration or existing paused assimilation restart is performed.

Nine all-sky directions test temperature, QV, pressure, two geopotential scales,
dry density, cloud mass, cloud number and a mixture. The captured ice Deff is at
its lower bound, so the native NI-number direction is a verified local zero;
it does not establish number identifiability. Synthetic tests cover nonzero
number-size derivatives, G-to-profile graph composition, interface endpoints,
moving upper T/Q weights and refusal behavior.

The separate direct RTTOV component checks find passing native P and P_HALF
directions at an eligible epsilon. A combined direction moving every reference
and native pressure still disagrees by about 2–3% after a bounded epsilon sweep.
Its exact cause is unproven; the raw failed comparisons are preserved. They
are not counted as a successful closure or repaired by changing tolerances.
Full-host/RK/memory derivatives, arbitrary reference-pressure controls, ozone
state, all cloud regimes, physical budgets, forecast skill and unattended cycling
remain outside this validation. Evidence is in
`harness/evidence/native_observation_ad_2026-10-21/`.
