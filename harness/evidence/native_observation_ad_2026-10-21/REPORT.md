# Native observation profile and real RTTOV-K cost evidence

## Result and validation boundary

The opt-in native profile path now includes moving centre/interface pressure,
Exner temperature, upper partial-layer interpolation, live dry density, cloud
content/diameters, real RTTOV pressure/cloud K and the final observation cost.
The selected saved MP137 column passes nine all-sky cost/BT direction checks.
The old fixed-pressure defaults and their config fingerprint are preserved.

This is a column observation-operator derivative. It does not implement a
complete native timestep/RK adjoint, run an assimilation optimizer, resume the
paused KO campaign, or declare `derivative_scope="full_host"`. A synthetic test
also composes the existing prep P/rho outputs into the new profile and cost;
that mock test is wiring evidence, not another real coupled-host experiment.

One separate comparison remains unresolved: moving the whole reference and
native pressure profile together at fixed T/Q gives a 2–3% discrepancy. The
failed comparison and its bounded epsilon sweep are retained below. It is
outside the new native application's fixed-reference controls and is not
counted as a successful pressure-K closure.

## Inputs, time and executed path

The source is the saved `TWO_STEP_SAVED_DA` MP137 case, native 234×282×39 at
5 km, column i=156/j=21 (zero-based flat index 4835). The original two-step
experiment applied a stored unaccepted diagnostic T/Q posterior once. This
work reuses its checkpoints; it produces no new accepted analysis or model
integration. The operational host executable/library are unchanged.

The primary all-sky input is the completed 00:00:20 checkpoint. All selected
T/Q, P/PB, PH_2/PHB, FNM/FNP, AL/ALB and cloud moments come from that same
checkpoint. At time zero QC/QI are positive while NC/NI are zero; the new cloud
boundary refuses those active but inadmissible moment pairs. At 20 seconds,
four QI layers have positive NI, one QS layer is active, and QC is zero.
The source Registry declares NC/NI as `# kg-1`; the selected optical map uses
that dry-air convention. It does not establish uniform number units or number
budget closure for the as-executed legacy raw kernel/CCN initialization.

The KO bundle has seven real channels 10–16 and nominal 00:00 UTC slot. The
20-second model offset is explicit. The archived KO product does not establish
pixel acquisition time, so this is a nominal-slot diagnostic, not a proof of
observation-time matching or window coverage. The source time audit is pinned.
Sigma=1 K, Huber delta=1, bias=0 and observed quality masks are fixed for the
diagnostic; RTTOV quality and cloud-fraction signatures must remain unchanged
for eligible FD trials. The observed BT and RTTOV K use the paired KMA v3.0
BT coordinate, with calibration and the actual AMI coefficient file pinned.

The existing 66/67 template supplies 27 above-model reference layers, fixed
trace-gas mixing-ratio values, surface and geometry. T/Q and both pressure
files are overwritten from the new map at every trial. Cloud fields are
overwritten in the all-sky run. Ozone/CO2 are fixed by layer, not regenerated
from moving pressure; using the AMI ozone channel does not certify ozone-state
assimilation. Native model layers are not remapped to the reference grid.

RTTOV executes out of process with OMP_NUM_THREADS=1 and OMP_THREAD_LIMIT=1.
The actual copied namelist enables `interpolation%pressure_gradients`; the
unchanged binary has SHA-256 `0909d289…`. The original template is never edited.
The binary and relevant vendor source files are identified, but this work did
not rebuild RTTOV or establish a new clean source-to-binary build certificate.

## Native pressure, units and optical map

The source `moist_physics_prep_em` constructs P8W from full mass pressure:
FNM/FNP interpolate interior interfaces; the bottom extrapolates pressure in
height, and the top extrapolates log-pressure in height. The new Torch map
reconstructs those 40 interfaces, reverses native bottom-up arrays and converts
Pa to hPa. This is not prep's auxiliary C3F/C4F pressure or P_HYD_W. The
checkpoints do not store P8W; this is a source-derived diagnostic, not a newly
captured P8W raw-bit parity result. All native 39 centres and 40 reconstructed
interfaces remain an unchanged suffix of the 66/67 emitted profile.

T includes both dry/moist-theta conversion and live Exner pressure. The last
upper reference centre is `sqrt(ref_half[U-1]*native_top)`, with live Torch
log-pressure interpolation of its T/Q. Reference arrays/U are fixed and their
bracket/knot boundaries are explicitly refused. RTTOV's P_HALF bottom already
includes surface-pressure sensitivity, so PSFC is not independently added.

The cloud map uses explicit native `rho_d=1/(AL+ALB)` from the checkpoint.
Content is `1000*rho_d*QC` and `1000*rho_d*(QI+QS)` in g/m³; number-to-volume
conversion is `rho_d*NC/NI`. Existing DSD, effective-diameter clamps and cloud
fraction conventions are retained. No EOS substitution/frozen density is
introduced. The optical bridge's moist forcing coordinate is separate from
the native dry DEN; operational KDM packing/defaults are not changed.
The existing VIS/IR slots map QC and QI+QS, not rain/graupel or raw CCN.

## Real all-sky cost result

`native39_cloud_cost.json` is the final source-pinned 91-call run. Every tested
direction passes its JVP/VJP dot check and a common epsilon for all seven BT
channels and final cost. Criteria were declared before evaluation: dot relative
error ≤1e-10; FD error ≤1e-8+3e-5×signal, with five epsilons. At least three
epsilons pass per direction. Selected source constants are f32-promoted while
the new graph and first-order products are continuous fp64.

| Direction | Dot relative error | Best epsilon | Max BT/cost FD tolerance ratio |
| --- | ---: | ---: | ---: |
| theta_m | 9.22e-16 | 0.01 | 0.00102 |
| QV | 0 | 0.003 | 0.01205 |
| native centre pressure | 2.08e-16 | 0.01 | 0.000831 |
| native geopotential | 1.06e-14 | 0.01 | 0.01724 |
| geopotential, larger resolved signal | 1.11e-14 | 0.001 | 0.07627 |
| dry density | 1.14e-16 | 0.01 | 0.00000866 |
| cloud mass | 2.33e-16 | 0.01 | 0.00000483 |
| cloud number | 0 | 0.01 | 0 |
| mixed | 4.40e-16 | 0.003 | 0.00247 |

The larger geopotential direction is additional to the original small direction;
it resolves the pressure-only BT signal above external-run roundoff without
changing the acceptance criteria. Its amplitude and all failed epsilon trials
are retained in the verifier/report. The maximum dot error is 1.11e-14 and
maximum best FD ratio 0.07627, below the limit of 1.

All seven channels survive the quality mask in this case. Ice Deff for the
four active QI layers is at the 20.02-micron floor, so the number direction is
a verified local zero, not evidence of number identifiability. The snow layer's
effective diameter is about 65.36 microns. No liquid/NC direction is nonzero in
this saved case; synthetic tests cover liquid and non-clipped number effects.

The native pressure cost direction is −0.01664573 with full pressure K, versus
+0.01123417 with pressure K omitted. The sign changes: pressure is a material
path, not only a graph annotation. Density and cloud-content contributions are
also nonzero. Raw profile arrays, K, controls, covectors and every FD trial are
included for recomputation. These are first-order derivatives; cached external
K does not provide its state derivative for HVP.

`native39_clear_cost.json` separately retains the 00:00:00 clear diagnostic
(six directions/61 calls). It intentionally omits the active initial cloud and
is not the primary native all-sky evidence. The costs of the two different
states/modes must not be compared as an optimization or forecast improvement.

## Pressure component checks and retained counterexample

The independent probe (`pressure_k_probe.json`) compares pressure-gradient
on/off with the same inputs: BT is raw-bit identical, while actual K has 459
nonzero P entries and 462 nonzero P_HALF entries. This establishes executed
option noninterference for that profile, not universal pressure-K correctness.

These independent probe JSON files call the linear sum of native RTTOV BT
"cost"; that probe functional is distinct from the primary KMA-BT Huber cost.
`pressure_components_fd.json` holds T/Q, upper-reference inputs and the native
transition interface fixed, and isolates native P and P_HALF directions. At
epsilon .003 their linear-functional relative errors are 2.91e-8 and 5.78e-8;
maximum channel tolerance ratios are 0.00427 and 0.01323.
P at epsilon .01 fails (maximum channel ratio
18.87); both raw failures and the passing smaller epsilon are retained.

The separate combined direction moves *all* reference/native P and P_HALF at
fixed T/Q. Its initial linear-functional error is about 2.67%. A bounded follow-up at epsilon
.3/.1/.03 still gives 2.36%/2.67%/2.24%, with channel ratios well above 1.
`whole_profile_pressure_sweep.json` has `passed_any=false`. No exact-knot or
other root cause has been proven. RTTOV has branch-local pressure interpolation,
but that fact alone does not explain this counterexample. The raw failure is
not overwritten, counted as a pass, or fixed by rescaling tolerances. The
native application's frozen upper-reference inputs do not expose this arbitrary
reference-pressure direction. Universal pressure controls remain unvalidated.

## Source, tests and reproduction

The final clear/cloud reports pin 43/81 input/helper/template/executable files
before and after. Their paths and SHA-256 values, the independent probe source
pins and runtime versions are in the reports/manifest. Raw host NetCDF,
coefficient/hydrotable assets and RTTOV binary remain private. Public tests
use explicitly labelled synthetic data and analytic mock K; they do not stand
in for the actual calls above. No Fortran/C++ ABI source is changed.

Focused native/profile/cloud/pressure/loader/composition tests: **78 passed**.
Full local harness: **2,538 passed, 59 skipped, 309 local-marked deselected**.
Ruff undefined-name checks over the whole harness/oracle and focused production
checks pass. Main-branch CI and feature-head CI are reported separately in the
PR; local research Torch 2.13 differs from CI's pinned Torch 2.8.

Run `python -m harness.verify_native_obs_ad` with explicit `--all-sky`,
`--model-time 2025-07-19_00:00:20`, matching checkpoint, executed namelist,
KO archive/time audit, prepared 66/67 template, actual executable, and new
workspace/output paths. Clear mode requires explicit `--clear-sky`. See each
machine-readable report for resolved input paths and hashes.

Remaining limits include exact pixel time, full-domain evaluation, complete
host/RK/retained-memory adjoints, optimization/cycling, arbitrary reference
pressure controls, ozone state, rain/graupel optics, number-unit/budget closure,
all cloud/limiter regimes and HVP. The prior raw NCCN stress residual is retained.
