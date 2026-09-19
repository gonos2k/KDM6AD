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
