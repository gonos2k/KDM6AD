# Native dry-number boundary v1: execution and observation-cost verification

The research boundary proposed after #432 is implemented as
`Psi = C_entry_rho^-1 K_legacy C_entry_rho`, preserving the native physical
forcing. Only NN/NC/NI/NR change coordinate. Entry/exit density JVP/VJP terms,
their species sum and KDM's own DEN derivative are included. An explicit
version/source/unit receipt is required. The default legacy path, C/Fortran
ABI, kernel physics and operational executable/library are unchanged.

This completes the **versioned local research execution boundary**, not a
host initializer/RK/restart migration or certification of historical payload
units. [Contract and equations](../../../docs/NATIVE_DRY_NUMBER_BOUNDARY.md).

## Qualified input and coordinate provenance

The input is native 39-level/40-interface step 2 at `(156,21)`, reconstructed
from the same saved trace and endpoint checkpoint as #431. Its geometry,
thermodynamics and original kernel number operands are model-derived; no
external model/reanalysis or invented cloud values replace them. As before,
the source T/Q posterior was diagnostic and unaccepted, not a scientifically
accepted analysis.

`native39_admission.json` fixes this captured kernel-volume coordinate once,
then defines each dry research control by division by its native entry DEN.
The receipt binds trace, executed namelist, endpoint checkpoint, step, column,
levels, initial-X digest and complete baseline state/forcing. It records the
exact four-field row/unit map and forcing-row-0 DEN source. TH (state row 0)
is preserved; it is never mistaken for density.

| Control | Source operand | Declared research coordinate |
| --- | --- | --- |
| NN / NCCN | `MP_INPUT.NN`, kernel activation/profile coordinate | `NN_volume / rho_entry` |
| NC | `MP_INPUT.NC`, kernel DSD coordinate | `NC_volume / rho_entry` |
| NI | `MP_INPUT.NI`, kernel DSD coordinate | `NI_volume / rho_entry` |
| NR | `MP_INPUT.NR`, kernel rain DSD coordinate | `NR_volume / rho_entry` |

All four derived controls and outputs are per kg dry air for this defined
map. `origin=derived_kernel_volume_coordinate` is distinct from
`verified_dry_producer`. The receipt explicitly leaves the original host
payload basis `unknown_not_migrated` and uncertified. It does not infer dry
units from Registry labels or repair timestep-1 NN initialization. This is a
declared coordinate pullback of an executed kernel input, not proof of the
historical file/host producer's physical units.

The density spans `0.0898140292…1.1295170512 kg m-3`. A predeclared divide/
multiply limit is 2 ULP per number field. Observed maxima are:

| Field | Maximum volume-coordinate roundtrip | Maximum absolute difference |
| --- | ---: | ---: |
| NN | 1 ULP | 1.490116119e-8 |
| NC | 0 ULP | 0 |
| NI | 0 ULP | 0 |
| NR | 1 ULP | 1.421085472e-14 |

These are not claimed bit-identical input conversions. The dry controls are
fixed after admission. During each trial, the live prep density changes both
the kernel number operands and the inverse output conversion; archived values
are not re-divided by trial density. `DEN,PII,P,DELZ` passed to KDM remain the
original live prep forcing, with no `DEN/(1+QV)` or moist-density substitute.

## Actual microphysics and RTTOV cost

`native39_dry_boundary_cost.json` uses the distinct
`kdm6.microphysics_observation_ad.native_dry_numbers.v1` schema. The same
prep → KDM → cleanup → applied finish → diagnostic EOS → native all-sky
profile → real RTTOV-K → KMA Huber-cost verifier is reused by explicit
`--native-number-admission`. Its default legacy behavior remains selected
when that argument is absent.

The final run has **91 actual KDM calls and 91 RTTOV executable invocations**:
one base point and nine directions × five epsilons × two central evaluations.
All seven KO channels 10–16 retain their quality support. The unchanged gates
are dot relative error `1e-10`, and channelwise BT/final-cost FD error
`1e-8 + 3e-5*signal`. One common eligible epsilon must pass every channel and
the cost, with finish/cleanup signature, cloud fraction and quality unchanged.

An earlier 91-call run of the same nine-direction experiment is retained
privately. The final run pins the source after end-of-file formatting cleanup;
that cleanup changed source bytes, not the operator. Published primary values
refer to the final run, and the manifest counts both executions separately.

| Direction | Cost direction | Dot relative error | Best epsilon | Max BT/cost tolerance ratio | Passing epsilons |
| --- | ---: | ---: | ---: | ---: | ---: |
| moist theta | 0.3806388600 | 2.92e-16 | .003 | .00018730 | 5/5 |
| QV | -0.04710189094 | 4.42e-16 | .003 | .0153989 | 4/5 |
| cloud mass | -0.000476551951 | 7.92e-14 | .01 | .00320076 | 5/5 |
| NC/NI control | 2.328588052e-7 | 4.55e-16 | .001 | .00796916 | 4/5 |
| MU | 0.05895110427 | 0 | .01 | .00047115 | 5/5 |
| PH interfaces | 0.01670438571 | 0 | .01 | .00180782 | 5/5 |
| mixed | 0.4087161761 | 1.36e-16 | .001 | .00139204 | 5/5 |
| NN interior | 0 | 0 | .01 | 0 | 5/5 |
| NR | 3.612759170e-8 | 0 | .003 | .00136788 | 5/5 |

The mixed direction includes thermodynamics, cloud mass, all available number
directions and MU/PH density changes. NN probes exclude its known entry clamp
cells; the reported NN response is locally zero. NC is zero at this native
point, so the joint cloud-number perturbation is NI-only. Independent affine
tests exercise nonzero NC and all four species plus shared-density terms.
Neither a zero nor nonzero directional result proves identifiability.

The baseline cost is `101.90147755152957`. It happens to equal #431's scalar
at this cold, diameter-clipped case; this is not a general equality of the
two number conventions and not a cost/forecast improvement. The report
contains the internal volume state, external dry output, input receipt,
profile/K, covectors, directions, per-channel FDs and all epsilon results.
All **120** input/source pins match before and after. Independent recomputation
of the cost, dot products and FD selection agrees with the stored result.

## Legacy result kept separate

`legacy_separation.json` adds five calls to the same isolated research library,
with no RTTOV or native-host run. An earlier five-call replay is retained
privately; the manifest counts both, while the published JSON describes the
final five calls. Legacy value-only calls before/after the
wrapper are raw-bit identical; its graph-recording and value-only forward
also agree. Original input arrays/forcing are unchanged. The versioned output
matches an independent explicit C → K → inverse-C calculation bitwise for
the same converted operands, and physical forcing is bitwise preserved.

Compared with the original recorded volume operands, the new inner K input
has the 1-ULP number roundtrip above. Its volume output matches legacy on all
39 layers of TH, QV, QC, QR, QI, QS, QG, NC, NI and BG; NN matches 38/39 and
NR 37/39 (max differences `1.49e-8` and `1.42e-14`). These comparisons remain
explicit rather than silently calling the versioned map identical to legacy.

This is research **fp64** replay/value evidence, not a fresh operational-f32
mp37/mp137 parity campaign. No old parity tolerance or default is changed.
The supplementary five-call replay producer is private; its SHA-256 is bound
in the manifest. The comparison pattern is described above, but its result
JSON alone is not an independently rerun campaign in a public checkout. The
primary nine-direction verifier and the boundary itself are public source.
The reused library is SHA-256
`3e968dcd43f6d361a2e1be6b963f76dcb9de1381313875e5c805af187a1693e4`;
its source/build attribution remains the prior isolated research manifest.

## Validation and remaining scope

NumPy-only boundary tests use a distinct affine kernel with known transpose,
nonunit density, all four number controls, independent directional differences
and an identity-kernel density cancellation check. Admission tests reject
unknown/missing units, modified semantics despite recomputed content hashes,
wrong source binding, wrong density row and changed baselines. They preserve
TH/BG, prove no in-place mutation, and exercise value-only/foreign/closed
handles and failure cleanup. Modified-verifier refusal tests cover the new
receipt input alias. Local/CI counts and source hashes are in `manifest.json`.

There is no new native integration, first-step NN producer repair, checkpoint
migration, scalar RK or full-host adjoint. The operational processes remain
paused. Closed water/number/energy budgets, HVPs, optimization and forecast
skill are not certified. The source-reconstructed prep/P8W assumptions,
+40 s nominal KO offset, unknown pixel acquisition time, fixed surface/
viewing/reference/gases, prior raw NCCN stress limit and unresolved 2–3%
whole-reference pressure discrepancy remain. The new schema is refused by
the older legacy-raw applied-budget reader, preventing a silent basis mix.
