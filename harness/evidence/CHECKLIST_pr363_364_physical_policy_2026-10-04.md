# PR #363/#364 physical-policy follow-up

Baseline: `6a2fbf7de13b7591a7a31e10e7da933dcb4f21a0`.
The numerical closures below are retained. This note supplies decision evidence;
it does not approve a new physical policy, change code/defaults or deploy a release.

## Checklist

- [x] Close the first-order frozen-density P2, NCCN return arithmetic and
  17-digit output issue at their demonstrated scope. Keep their regressions.
- [x] Close the bounded independent IR105 transport comparison and source-rule
  attribution. The thin-source difference occurs in reference-top layers 1–7,
  not the native liquid layer; the matched FD gap corresponds to 3 BT ULP.
- [x] State one coherent research coordinate and distinguish it from recovered
  calibration. The original 100/10 provenance search is finished, not restarted.
- [x] Distinguish AMI instrument noise thresholds, calibration specifications,
  local scene variation, state error and total observation-error covariance.
- [x] Quantify retained observations at the already fixed C5 pixel and first
  following stored slot. Preserve all QC and the original selected support.
- [ ] S2: approve either documented original calibration or an explicitly new
  physical parameter policy, including units, applicable regimes and validation
  independent of the development case. No approval follows from dimensions alone.
- [ ] S11: specify the observation target/support, bias treatment, channel-error
  policy and separate BT/sensitivity accuracy budgets; validate against that
  predeclared policy before accepting a scientific observation cost.

Existing [scientific OPEN items](CHECKLIST_pr361_followup_2026-10-03.md) remain
OPEN. No new X/F/S layer or general-purpose specification framework is introduced.

## S2: a concrete coordinate decision

For the existing opt-in research map, retain stored `n_d` in #/kg dry air and
`q_d` in kg water/kg dry air. For each call use its own entry measure

$$
R=\rho_m/(1+q_{v,entry}),\quad N=Rn_d,\quad C=Rq_d.
$$

Then `C/N=q_d/n_d` and the physical number inventory is weighted by dry-air mass,
not by bare stored `n_d` times layer thickness. Kernel volume rates/thresholds
act in the `N` coordinate; return number with the same entry `R`. Runtime uses
this dry measure for DSD mass via `dend`, while moist density remains an air-property
input. The explicit composed optical path receives `entry_qv`; the frozen-background
optical path remains a separate supported map. With fixed external rho_m,
`delta R=-rho_m*delta qv_entry/(1+qv_entry)^2`; a balanced-atmosphere control policy
can have different constraints and is not certified by this fixed-forcing derivative.

| Decision | Current reproducible research convention | Physical closure needs |
| --- | --- | --- |
| 100/10 land/sea controls | Unchanged values applied as #/m³ in the volume kernel | Original documented units/calibration, or a named new policy with applicability evidence |
| Numerical floors/caps | Keep NCMIN and other number limits separately inventoried | Their roles and physical calibration must be justified individually |
| Alternative specific threshold | If declared in #/kg_d, map cellwise as `Nmin=R*nmin_d` | Convert affected gates/caps coherently; one rescaled scalar is insufficient |
| Validation | Preserve fixed inputs, units, actual applied rates and branch-local AD | Input-defined independent state/regime coverage after the policy is specified |

The fixed sea C5 case uses equal 10/10 controls; it does not validate the land
100 threshold. This is a proposal to retain the **already declared research convention**, not a
claim that the undocumented historical thresholds were calibrated in #/m³.
Do not tune 100/10 to a BT residual or rename a numerical floor as physical calibration.
Source anchors: [unit audit](REPORT_S2_number_dimensions_2026-10-03.md),
[threshold interpretation](REPORT_S2_threshold_units_2026-09-28.md),
[completed provenance search](REPORT_S2_calibration_provenance_2026-10-03.md),
`oracle/kdm6/runtime.py` dry-number entry/return and coordinator `dend` consumers.

## S11: separate errors before assigning weights

Write an innovation schematically as
`d = H(x_b) - y = state contribution + operator/representation contribution
+ calibration bias + measurement noise + numerical discrepancy`.
These terms are not identified by a single residual. A noise covariance concerns
centered random errors; bias needs separate estimation/treatment. For components
`epsilon_i`, total covariance includes `sum Cov(epsilon_i)` **and cross-covariances**.
Adding variances in quadrature requires justified independence. Forecast-state
uncertainty belongs in B/Q; including it again in R double-counts it. In a linear
independent-error approximation, innovation covariance is `H B H^T + R`, not R alone.

Primary instrument context (accessed 2026-10-04):

| Source/metric | IR105 reference numbers | What it does not provide |
| --- | --- | --- |
| [NMSC ACVS quality thresholds](https://api.nmsc.kma.go.kr/enhome/html/gsics/acvsIntro.do) | NEdT 0.21 K at 240 K; 0.10 K at 300 K | Actual error standard deviation of this 2025 cloudy model/KO comparison |
| [KMA CGMS-50 instrument specifications](https://www.cgms-info.org/Agendas/WP/CGMS-50-KMA-WP-01) | NEdT 0.4/0.2 K at 240/300 K; calibration accuracy 1 K | A calibrated diagonal sigma or full all-sky R |

The CGMS row was checked against indexed text of the official report; direct
PDF retrieval/rendering was unavailable in this run.
The different figures describe different requirements/monitoring contexts; do not
select whichever makes the model pass or combine them as independent variances.
No epoch-specific calibration certificate for this observation is inferred.
[NMSC inter-calibration methodology](https://api.nmsc.kma.go.kr/homepage/html/gsics/infraredIntroGK2A.do)
requires time, angle, spectral-response/FOV and spatial-homogeneity matching.
Its brightness-temperature scene categories are calibration-selection rules,
not independent truth labels for the model's liquid-cloud population.

The current sigma=1 K Huber cost is a diagnostic scale. Scalar/per-channel sigma
support in `obs_loss` does not validate a cloudy error model or implement arbitrary
cross-channel covariance. Do not manufacture R from this one scene or add a
covariance framework before a justified policy actually needs it.

## Actual local support evidence

Reuse C5 pixel `(row,column)=(411,338)`, the original seven common channels,
a centered 3×3 KO window and nominal slots 2025-07-19 00:00/00:02 UTC, fixed before
outputs. All 14 channel/slot windows have 9/9 usable pixels under the existing
decoder, DQ and missingness checks; 00:00 centers exactly reproduce C5 records.
Both slots use the retained 00:00 calibration; calibration drift between scans
is not independently evaluated. The two-minute difference is an increment under
that fixed decoding map, not a validated 20-second interpolation.

| Channel | 00:00 spatial BT std (K, ddof=0) | BT(mean radiance) minus center (K) | Center change over nominal 120 s (K) |
| --- | ---: | ---: | ---: |
| WV073 | 0.151930 | -0.021656 | +0.058423 |
| IR087 | 0.537647 | +0.331006 | +0.040521 |
| IR096 | 0.324612 | +0.190269 | +0.019051 |
| IR105 | 0.522479 | +0.364792 | +0.069077 |
| IR112 | 0.389757 | +0.288830 | +0.070707 |
| IR123 | 0.269176 | +0.143521 | +0.089101 |
| IR133 | 0.112174 | +0.013193 | +0.033922 |

For IR105, observed range is 284.446274–285.888847 K and fixed DOM32 BT is
291.878893 K. Under the same monotone observation conversion, any nonnegative
normalized average of those nine radiances stays inside their BT range.
Therefore that window-averaging choice alone leaves at least **5.990047 K** of
positive residual. This bound does not cover other footprints, cloud parallax,
unknown acquisition times or atmospheric/optical errors; it assigns no causal
fraction to those errors. No observation or model BT is corrected by this analysis.

Mean BT and BT of mean radiance are distinct: at IR105 they differ by 0.001383 K.
Window standard deviation measures observed spatial variability, mixing scene
signal with measurement/resampling effects; it is not isolated error variance or R. Uniform 3×3 weights are a diagnostic, not the actual
5 km cell/pixel PSF. The model's native 39 layers/grid remain unchanged.

[Executed source](AMI_local_support_source_2026-10-04.py) and
[result with exact arguments/input hashes](AMI_local_support_result_2026-10-04.json)
allow replay using retained files. No new atmospheric data, RTTOV/KDM/native run,
physical calibration or accepted-observation cost is claimed.

## Minimum decision required for the next scientific step

Specify the intended footprint/time target (including KO resampling and cloud
parallax), admissible populations/regimes, bias policy and conditional error
model. Allocate BT error limits in K and sensitivity limits in K/control for
**declared directions** separately, before inspecting an independent validation
set. Keep numerical FD thresholds fixed. A one-pixel cost, 3 ULP agreement or
NEdT threshold cannot supply those limits. Use retained input-defined states and
observations for validation; do not select them from their cost or FD outcome.
