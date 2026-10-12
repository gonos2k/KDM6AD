# Jul19 actual AMI ten-minute joint observation window

The requested Jul19 window was **executed once and returned with all-three-slot
objective audit and a private state/control/full-gradient checkpoint**. No
other-date analysis or new native integration was performed. This is a
forecast-backed local prescribed-forcing window, not full host forecast cycling.

## Inputs, times and mathematical map

Normal retained native run initialized **2025-07-19 00:00 UTC**, effective stop
**05:58**, selected natural-QC ocean column `(j103,i48)` on the native5km/39-layer
grid. Its actual **05:55:40** saved state is the sole initial background.
The original input is admitted through unchanged V4 and verified against PR412.
A 20 s KDM step is repeated61 times with the same saved forcing `f0`; the
observation indices1/31/61 map to nominal **05:56/06:06/06:16**. The later local
states are not saved host output; 05:58 host termination is not re-labelled.
Native centres/interfaces, upper reference, surface/gases/view geometry and
initial-background optical dry density are retained/frozen throughout.

The nine original0556 files are immutable reuses. Eighteen new0606/0616 thermal
L1B files (**8,849,101bytes**) were acquired once, with size/ETag/MD5/SHA checks,
then decoded by the unchanged LA reader/calibration. All three scenes select
the same nearest finite pixel `(289,49)` by geography before QA, **425.935m**
from the fixed native column, and have seven source DQF0 channels10–16.
No scene/pixel is replaced based on quality, BT residual or fitted cost.

| Model nominal slot | Local index | Source acquisition raw OBT | Mission planned UTC | Actual pixel UTC |
|---|---:|---|---|---|
| 05:56 | 1 | 05:56:56 | 05:50 | unverified/null |
| 06:06 | 31 | 06:06:56 | 06:00 | unverified/null |
| 06:16 | 61 | 06:16:56 | 06:10 | unverified/null |

The explicit research hypothesis treats filename nominal OBT labels as model
UTC. Planned UTC/OBT/synchronization numbers are retained as their own fields;
this is not verified simultaneous pixel-time collocation.

For initial controls `v`, `x0=C(v;xb)`, `x_{k+1}=M20(x_k;f0,alpha_fixed)` and

`J(v)=0.5||v||² + sum_{t in {1,31,61}} sum_{c=10..16} Huber1((H(x_t)-y_t,c)/1K)`.

One initial prior is used, not three reinitialized analyses. Active controls
are theta39 (sigma0.8K) and eligible bottom12 log-qv (sigma0.08); other initial
State controls and four parameter controls remain zero. H is actual all-sky
RTTOV/KMA BT. Equal-scale additive21 time-channel terms are an exploratory
error assumption; temporal error independence/covariance is not calibrated.
The longer held-forcing interval is a declared experimental change from the
historical single20s case, not proof that forcing/transport can be neglected.

## Actual finite-budget result

| Nominal slot | Background Jo | Accepted Jo | Background MAE K | Accepted MAE K |
|---|---:|---:|---:|---:|
| 05:56 | 8.461861230 | 6.296961690 | 1.682871 | 1.346510 |
| 06:06 | 9.110309309 | 6.910692202 | 1.780843 | 1.444527 |
| 06:16 | 9.077670837 | 6.887257325 | 1.772232 | 1.435958 |

Initial Jo/J = **26.649841376**. Final Jo = **20.094911217**, initial-state prior
= **0.199648864**, final total J = **20.294560081** (**23.84735% reduction**).
This is fit to these three actual scenes under the declared local map, not
forecast-skill improvement, cloud truth or independent-date validation.

One bounded L-BFGS run: max_iter3, actual2 iterations/4 objective evaluations
plus1 accepted-point audit. All five full windows observe all three slots:
**15 logical H callbacks**, no separate quality probe/repeated baseline, and
no measured count of internal RTTOV direct/K processes. Every callback retained
all seven model quality0 channels. Each complete window uses61 forward and61
recomputed VJP transitions in the unchanged window implementation.

Full accepted gradient **Linf0.385080631, L2 1.376755979**; strict1e-10 criterion
**unmet**, exposed termination **UNKNOWN**. No convergence/stable-point claim,
post-hoc tolerance change or automatic larger-budget run is made. The
strong-Wolfe actual4 evaluations exceed nominal default max_eval3; counts are
reported as observed rather than a promised absolute cap.

Accepted QC is0 at all three slots. In this fixed-forcing local experiment,
the three sampled accepted slot states and their BT are exactly identical;
observed target vectors are distinct. This is not three reused observations or
three saved host forecasts. Initial maximum temperature increment0.266525K,
qv increment0.635272g/kg dry; initial fixed-host-mass water change
−0.143685535kg/m². Slot water remains38.232835370kg/m² under that same measure.
Intermediate steps2–60 were not checkpointed here; sampled equality does not
prove every intervening transition is identity. These endpoint diagnostics do
not identify individual rates/external fluxes or
independently retrieved cloud/NC truth. Earlier PR412 R_M/I_M values are not
transferred to this new accepted point; no extra four-H contrast was requested.

## Evidence, corrections and limits

Source/input114 bindings,33 external assets and fixture files were checked
before/after execution. All three initial and accepted Huber sums were
independently recomputed; exact CVT reconstruction, inactive parameters, full
gradient norm and final audit slot sequence were verified. Private checkpoint
SHA **d3bad26034b327128dfbf1242f32eb013e3dda0bc30315cd8368c4440c02ca26**,
mode0600 under0700 directory. Arrays remain private; public channel/state-change
summaries are additive. Existing gate tests:5 passed/33 deselected, not a full
repository/native CI campaign. Ruff passes the new scripts.

A first preparation-only window declaration lacked comparison with the
published decode receipt's expected input digests. Red found it; the comparison
was added and the unexecuted draft declaration/preflight/fixture were preserved.
Only the corrected plan was executed. The acquisition process was prematurely
assessed interrupted at16/18 while it continued asynchronously; the assessment
was retracted against all18 successful one-attempt receipts. No second GET or
model retry was issued; see the correction record. Green/Red final reviews
separately report their direct coverage.

[Time/material/search inventory](INPUT_AND_TIME_INVENTORY.md),
[actual result](RESULT.json), [independent saved summary](WINDOW_SUMMARY.json),
[channel table](WINDOW_CHANNELS.csv), [observations](OBSERVATIONS.json),
[window declaration](WINDOW_PREDECLARED.json), [preflight](PREFLIGHT.json).

Only Jul19 has actual analyses. Jul20/21 remain decoded-L1B/native-pending.
Additional searched directories yielded a Jul19 hourly00–12 host candidate
without the needed completion/identity evidence, and a Dec23 different-MP8
candidate; neither was silently substituted. Management79 is not reassessed.
The user-prioritized Jul19 local three-time analysis is now executed; normal
full-host cycling and other-date inputs remain separate dependencies.
