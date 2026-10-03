# C5 retained liquid baseline: completed RTTOV, empty accepted support

The input-selected sea column `(71,101)` at 20 s now completes the actual
installed RTTOV K executable. It produces nine thermal BT values and profile
Jacobians. All nine outputs have nonzero radiance quality: **0/9 observations
are accepted** by the existing combined observation/radiance gate. A zero
masked loss is not an accepted objective or a physical validation result.

## Executed inputs and numerical boundary

The [frozen experiment](C5_EXPERIMENT_CONTRACT_2026-10-03.md) uses the opt-in
`N=rho_d*n_d` optical adapter, unchanged volume-coordinate cutoffs 10/10,
native 39 model layers, and 24 explicitly separate reference layers above the
model top. Native center T/Q/pressure and hydrometeors are preserved; interfaces
are source-backed REAL(4) reconstructions, not captured host P8W. The 00:00
observations are nominally 20 seconds before the model frame; the matched KO
pixel is 0.674 km from the cell. View geometry is nominal-orbit geometry, not
measured satellite ephemeris. Sea skin and near-surface quantities come from
the same history cell. Solar is disabled; IREMIS is selected; zero wind fetch
is unused in this thermal path.

[Prepared native/background arrays](C5_native_background_profile_2026-10-03.npz)
and [serialized input arrays](C5_baseline_input_2026-10-03.npz) are distinct.
The receipt records the executable, coefficient, hydrotable, configuration and
per-file hashes. RTTOV receives `gas_units=2` (ppmv moist), `mmr_hydro=False`
(g/m³), BT-seeded K, stored radiance quality and interpolation mode 4.
The coefficient file is the locally installed v13-predictor 54-level AMI O3/CO2
file, consumed by the installed RTTOV 14 executable; the native model is not
remapped to a fixture grid.

## Results and source-based interpretation

| AMI channel | BT (K) | ReturnQuality | Accepted |
| --- | ---: | ---: | --- |
| 8 | 245.449082593 | 32769 | no |
| 9 | 256.191792898 | 32769 | no |
| 10 | 265.944970128 | 1 | no |
| 11 | 291.306234993 | 1 | no |
| 12 | 261.128525196 | 1 | no |
| 13 | 293.600110756 | 1 | no |
| 14 | 293.513365635 | 1 | no |
| 15 | 290.922251489 | 1 | no |
| 16 | 275.298549910 | 1 | no |

The installed `rttov_const.F90` defines bit 0 as gas optical-depth regression
limits exceeded and bit 15 as Delta-Eddington extinction limits exceeded.
Thus 32769 sets both bits; 1 sets only bit 0. Neither is discarded.
For bit 15, `rttov_eddington_setup.F90` sets the flag if any extinction exceeds
20 km⁻¹ and then caps the extinction at 20 km⁻¹ before the Delta-Eddington
calculation. The returned flag does not identify the layer or separate clear-gas
from hydrometeor extinction, so this output is a flagged, clipped-solver
baseline rather than evidence that the input stayed within the solver's range.
The [actual log](C5_baseline_rttov_log_2026-10-03.txt) reports coefficient-layer
Q=7.7850 ppmv dry at 61.4771 hPa against a local upper bound 7.6890.
This is **not a uniform humidity ceiling**. The v13 coefficient reader averages
adjacent envelope levels onto coefficient layers; default gas limits expand
that envelope by 20%. `rttov_intavg_prof` averages the converted user gases
onto that grid using `rttov_layeravg`; `rttov_check_reg_limits` compares
corresponding layers and sets the quality bit without aborting.

The first binary launch failed because `out/direct/` did not exist, so the
RTTOV test driver could not open `./direct/radiance.txt`. The humidity message
was informational, not that fatal cause. A separate retry added only the
standard empty `direct/` and `k/` output directories; atmospheric, optical,
surface, geometric and coefficient inputs were unchanged. The original failed
case remains private and separately identified in the receipt.

## Public replay and limitations

[The receipt](C5_baseline_receipt_2026-10-03.json) and
[BT/K/quality arrays](C5_baseline_outputs_2026-10-03.npz) preserve the executed
result. [The observation pixel](C5_observation_pixel_2026-10-03.json) records
actual calibration/file hashes and the nine decoded observation BT values;
all observation quality flags are zero. Independently applying the existing
`_build_mask` gives an all-zero combined mask. `compute_obs_loss` consequently
returns algebraic zero and a zero BT cotangent, recorded in
[the gate result](C5_baseline_observation_gate_2026-10-03.json), with
`accepted_observation_cost=False`. This replay does not execute RTTOV again.

No NC-to-BT finite differences or DOM convergence run is claimed here.
K arrays alone do not validate independent derivatives, physical radiative
accuracy or the empirical number thresholds. The input census and initial
case preparation were executed inline; their command source was not archived,
so the full independent preparation/census reproduction claim remains limited.

The next selection, if needed, must declare a **global input-only coefficient
support predicate** before producing new BT/K, apply it uniformly to all
eligible retained columns, and preserve this first selection. Do not clip Q,
disable limit checks, fit sigma, rerank by BT residual/FD success, or convert an
empty support into acceptance. S2 calibration, general coupled DA, S11
independent accuracy and operational approval remain OPEN.
