# Native 5 km model levels — validation contract

The current target is the existing 5 km model's native columns and vertical
levels. No external model/reanalysis field is used. Earlier fixture-grid and
bottom-only surface-pressure experiments remain historical comparisons, not
completion of this target.

## Native pressure definition

Selected column45577 is `(j=194,i=181)` on the stored `(282,234)` horizontal
array (`194*234+181=45577`). There are 39 mass levels and 40 interfaces.
The fp64 oracle computes centre pressure as `float64(P)+float64(PB)`. Reusing
stored P_HYD would differ by up to 0.0037841796875 Pa here, so it is only a
cross-check, not the pressure coordinate used for this derivative experiment.

Interface pressure replays the existing host `phy_prep` P8W construction with
FNM/FNP weights and PH+PHB heights: weighted interior centres, z-linear bottom
extrapolation, and log-pressure top extrapolation. The resulting interfaces
strictly interleave all 39 centres and span 1008.8232416207 to 50.0697255262 hPa.
This is an fp64 replay of the host formula, not a host fp32 bit-parity claim.
The extrapolated bottom differs from PSFC; it is not silently overwritten.

Pressure, density and other forcing remain fixed during the selected first-order
control derivatives. The model fields and profile/K directions must use these
same coordinates. The profile target must equal native source pressure exactly;
there is no remapping onto the old 69-layer fixture or reference upper T/Q blend.

## RTTOV boundary

The installed RTTOV14 test driver reads `atm/p.txt` when present and otherwise
uses its internal pressure defaults. Native full-level pressures must therefore
be written and validated explicitly together with `p_half.txt`. All dependent
profile arrays have 39 rows and the driver has 40 pressure interfaces.

The local RTTOV source accepts positive top-interface pressure. Its enabled
interpolation performs coefficient-grid upper extrapolation internally; this
must be distinguished from adding measured atmosphere above the model top.
O3/CO2 file inputs are disabled for this experiment, retaining RTTOV coefficient
background gases as declared radiative-model assumptions. No external gas profile
or total-column-to-layer reconstruction is introduced.

Satellite view angles remain a separate declared limitation. Solar angles are
derived from the current column and slot using the locally retained RTTOV formula.
These assumptions do not establish observed navigation or actual upper gases.

## Evidence provenance

Native vectors and source hashes are retained in
`graphify-out/pr219-science-20260919/green/native_model_levels.json`.
The prepared native experiment is `run_native_model_aux.py` in that output root.
The previous public GFS metadata probe was stopped and quarantined: no GRIB
payload/range was fetched and no external meteorological value entered a run.

## Executed native-level evidence

Ten live RTTOV direct/K evaluations (two controls, alpha0 and plus/minus two
step sizes) completed with the native 39-layer input. The explicit 39-element
P vector equals the fp64 source forcing pressure after reversal and Pa-to-hPa
conversion. The profile builder's target equals its source: there is no change
of model levels. Reference T/Q blending is disabled. P, P_HALF, geometry,
datetime and surface files are identical across paired alpha evaluations.

| Control | Reverse VJP | Forward AD + baseline K | Maximum FD relative difference |
| --- | ---: | ---: | ---: |
| deposition | -0.01318974735577571 | -0.013189747355775704 | 0.00526223 |
| riming | -1.2971554274497282e-5 | -1.2971554274497287e-5 | 0.00231421 |

Both epsilon=.03/.1 comparisons meet the unchanged 5% rule, retain recorded
KDM branches and exact serialization, and exceed the output-spacing signal
bound. The result is selected first-order evidence, not all-state or all-process
coverage, and the bound is not a total numerical-error bound.

**Seven** clean IR channels are jointly usable. WV063/WV069 retain RTTOV quality
32768 (bit15, Delta-Eddington extinction limit) and are excluded by the existing
quality rule in every paired evaluation. This is not a relaxed-QC nine-channel
pass. The earlier nine-channel fixture-grid objective is a different operator
and domain; its derivative values are not directly compared as improvements.

The run keeps reference satellite viewing angles and declared RTTOV coefficient
background gases, with upper extrapolation inside RTTOV. It does not claim
measured navigation, measured atmosphere above the model top, complete physical
number units, or nonzero applied host transport.

Local result: `graphify-out/pr219-science-20260919/native_model_aux.json`;
runner and raw cases are retained alongside it. Independent Green/Red review
and portable writer regression accompany this evidence.


Native live JSON SHA256: `2887a9b9ed82c5c1d74e7c3f1e979777bbc2473315dee4db4239307390d2e680`.

Final metadata/guard revision replay preserves initial native BT, VJP, JVP and
FD values exactly. This repeated ten-call verification is not additional case
coverage. Portable validation: 66 writer tests and 59 profile/input/melt tests
passed (18 existing TorchScript deprecation warnings in the latter suite).
Green and Red final reviews found no remaining blocking issue in this scope.

## Precision audit — native model boundary

A follow-up probe reuses the retained native experiment without new live calls
or external data. Source P/PB/T/QVAPOR/PH/PHB/QCLOUD/QICE are stored float32.
The reader promotes each operand before derived fp64 arithmetic; promotion
preserves stored values but cannot recover information lost before storage.
P+PB in fp64 differs from adding in fp32 first by up to 0.0037841796875 Pa.
The supplied native pressure matches the former exactly.

For both baseline controls, all six T/Q/cloud-content/effective-size fields
retain exact values on the identical native grid. Direct evaluation of the
existing interpolation function gives an exact 39-by-39 identity Jacobian and
identity JVP in all 12 checks. This establishes the field-transfer derivative
with fixed pressure, not pressure sensitivity or the full KDM Jacobian.
All ten retained P/P_HALF file pairs are bit-identical to the expected native
fp64 vectors. The existing six-field serialization records have zero changed
values with 17 significant decimal digits (`%.16E`).

This does not imply bit-preserving precision throughout the radiative model:
geometry and surface namelists use six decimal places. The selected skin T
changes by 4.882812731921149e-7 K, T2 by 2.9296876391526894e-7 K, and solar
azimuth by 3.3011488653755805e-7 degrees. These auxiliary values are identical
across paired alpha runs, but are not fp64 round trips.

The selected BT text spacing is 1e-9 K. Retained cost-FD output-spacing bounds
are 1.1666666666666668e-7 at epsilon .03 and 3.5e-8 at .1; the riming derivative
has magnitude 1.2971554274497282e-5. Thus the text-only bound is approximately
0.90% and 0.27% of that signal. Observed smaller AD/FD discrepancies must not
be presented as a guaranteed sub-percent total accuracy. Neither text spacing
nor identity native-grid transfer bounds RTTOV internal interpolation,
extrapolation, coefficient approximations, or full scientific error.

Probe artifacts: `graphify-out/pr219-science-20260919/precision/probe.py`,
`results.json`, and `auxiliary_decimal_loss.json`. The executed probe has 12
identity-Jacobian/JVP checks and 10 paired pressure-file checks; these are not
additional atmospheric cases. Current code commit 7aad359 has all five CI
checks successful, including both native builds; no new physics change was
needed for this audit.

Green/Red follow-up reviews agree with this limited precision conclusion.
Local RTTOV source, module and build records identify `jprv=8` and
`REAL(jprv)` profile parsing/internal interpolation. This is source/build-record
evidence; an executable-wide rebuild-to-hash precision attestation was not
performed. Output `E21.12` precision is separate from binary arithmetic.

## CI duplication cleanup

Required check names and all test coverage remain unchanged. Independent LCC
runs once in the complete oracle suite; mandatory pyproj import still prevents
a missing dependency from turning it into a skip. Ubuntu no longer reinstalls
already-pinned NumPy. Each workflow cancels superseded runs only for the same
PR ref; main runs are not explicitly cancelled. Both platform-specific native
builds and cross-tree AD gates remain intact. No speedup is claimed before
measurement, and prior-head CI success is not attributed to this workflow edit.
