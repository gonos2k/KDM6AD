# One bounded numerical finish of the Jul19 three-slot local window

The PR414 review's bounded same-problem budget check was executed **once**.
The original background, three actual AMI scenes, one initial T/Q prior,
61×20s KDM transitions, f0, H auxiliaries, seven-channel support,1K scale/zero
bias and normalized Huber delta1 are unchanged. Only optimizer max_iter changes
3→8, with a separate run ID/output. It starts again from control0 on the
original05:55:40 background, not the earlier accepted state/prior.

The returned point has substantially smaller gradient, but still does not meet
strict1e-10 convergence. Its sampled model BT remains identical at05:56,
06:06 and06:16: this improves the common BT-level compromise, not observed
temporal evolution. The one declared budget check is complete; no16/32 or
unlimited continuation is started.

## Actual same-problem comparison

| Quantity | PR414 max_iter3 | This max_iter8 |
|---|---:|---:|
| Initial J | 26.649841376 | 26.649841376 |
| Accepted Jo | 20.094911217 | 18.420371780 |
| Accepted Jb | 0.199648864 | 1.020024321 |
| Accepted total J | 20.294560081 | 19.440396100 |
| Full-gradient Linf | 0.385080631 | 0.002606100 |
| Full-gradient L2 | 1.376755979 | 0.007957038 |
| Prior-gradient L2=control norm | 0.631900093 | 1.428302713 |
| Full/prior gradient norm ratio | 2.178755777 | 0.005570974 |
| Actual iterations/evaluations | 2/4 | 8/10 |
| Full-window accepted audit | 1 | 1 |
| Logical H callbacks | 15 | 33 |
| Strict convergence / exposed stop | false / UNKNOWN | false / UNKNOWN |

Extra total-cost reduction is **0.854163981 (4.20883%)**, initial-to-new reduction
**27.05249%**. Jo decreases1.674539438 while prior increases0.820375457;
**48.9911%** of the extra observed-cost reduction is exchanged for prior cost.
These are objective trade-offs, not atmospheric-error or information fractions.
Linf gradient decreases **147.76×**. Full/prior gradient ratio is now **0.5571%**,
a descriptive numerical balance, not a new acceptance or physical-error limit.
Observed8 iterations/10evaluations reach the declared counts, but the actual
optimizer termination branch is not exposed; `UNKNOWN` is retained.

| Nominal slot | New Jo | New quadratic-region channels |
|---|---:|---|
| 05:56 (index1) | 5.755355103 | IR087,IR105,IR123,IR133 |
| 06:06 (index31) | 6.340511428 | IR087,IR133 |
| 06:16 (index61) | 6.324505248 | IR087,IR105,IR133 |

Each slot retains all seven source/model quality0 channels. The three observation
vectors are distinct; some individual values coincide (e.g. IR087 at the last
two scenes). There are21 channel-time cost terms, not21 independent weather
cases or empirically independent errors. The PR414 review's particular
common-output Huber decomposition constant belongs to its old residual
regions: IR105/IR123 now cross regions across time. Costs here are computed
separately for each of21 residuals; no old constant or linear-loss shortcut is
transferred to the new point. Huber's first derivative remains continuous.

## Level fit, temporal response and state change remain separate

All12 sampled accepted State fields at1/31/61 are bit-identical; every channel's
sampled simulated temporal BT range is **0K**. Three nonidentical observed
vectors therefore constrain one repeated accepted H profile at these samples.
This does not establish intermediate stepwise identity, M_x=I, zero process
rates or an unnecessary VJP; the existing full61-step reverse sweep remains.
It also does not establish zero initial-to-first-slot microphysics contribution.
No new direct-H/R_M/I_M comparison was requested; old PR412 values stay attached
to their old accepted point.

The accepted initial control nevertheless moves substantially: norm of the
old/new difference **1.229891869**, **86.1086%** of the new control norm, angle
**59.1102degrees** in the same prior-scaled coordinate space. Maximum initial
physical-T difference **0.248864568K**, qv difference **0.516328773g/kg dry**.
Maximum old/new accepted BT difference **0.177670868K**. These describe finite
points, not physical state-error percentages, measured identifiability or
proof that the full state has stabilized. Lower gradient is recognized without
claiming a global/sufficiently converged atmospheric retrieval.

QC and recorded-coordinate NC are0 at all three accepted samples. New initial
fixed-host-dry-mass water change is **−0.390707485kg/m²**, sampled water
37.985813420kg/m². This is the analysis increment versus a defined measure;
local endpoint equality is not an external-flux budget or process attribution.
Initial hydrometeors remain unchanged by C. NC native number-basis truth and
actual cloud phase are not independently revalidated by this result.

The clock/interpretation remains PR414's: native initialization00UTC, saved
BG05:55:40; actual host producer stops05:58; later states are local KDM under
held forcing through06:16, not saved host forecasts/cycling. Filename nominal
AMI05:56/06:06/06:16 is a model-UTC research hypothesis. Raw scene OBT ends
in`:56`; plannedUTC05:50/06:00/06:10 is distinct; pixelUTC remains unverified.
All three observations, including later06:16 information, estimate the initial
state retrospectively. This is not an online05:56 forecast or withheld future
observation validation. Time-error covariance and absolute error scales remain
exploratory assumptions. More iterations did not supply missing transport,
forcing evolution, dynamics/PBL/radiation or surface tendencies.

## Hourly native candidate: positive completion evidence, partial lineage

The narrowed [hourly identity audit](HOURLY_IDENTITY_AUDIT.md) located the
run-specific child `mp137_termparity_720min_hist60_np4_20260718_185625`.
Its exit0 and all four rank logs confirm normal termination at12:00 and13
hourly Jul19 frames. `terminal_parity.log` names that run and reports13 strict
MP37/MP137 comparisons, a historical campaign not newly rerun here.
Thus the earlier lack of known completion evidence is corrected for this
specific child. It is separately attributed to the historical four-rank MP137
path, not the current one-rank retained case/variant.

Do not assume the parent forecast is byte-identical: its inode differs from
the run-specific child, and no forecast digest was recorded. The current wrf.exe
is newer than the historical run; no old executable/input digest binds its exact
build/IC/BC bytes. `wrfchainp_d01` START_DATE2024-07-23 differs from its Times2025
Jul19, still unresolved. Boundary THIS/NEXT confirms final interval09–12;09 is
its start, not coverage end. Terminal12 is distinguished from further advance.
No weather arrays/4GB file hashes, host run or current intake were performed in
this audit. The candidate was **not substituted into this budget experiment**;
hourly frames do not create06:06/06:16 hydrometeor snapshots by interpolation.

## Implementation and validation scope

A small adapter loads the immutable PR414 runner, explicitly supplies only the
new packet/output identity and max_iter8, then uses its unchanged validation,
real RTTOV/M/AD/dual optimizer, all-slot audit and private checkpoint writer.
No original source, physics, solver, prior, weight or consumer version is changed.
The legacy result schema is reused truthfully; new driver/plan/marker bind the
PR415 identity and source hashes.119 input/source bindings,33 executable/asset
bindings and24 fixture hashes match; prepared fingerprints match PR414 after
only the fresh fixture-directory difference. Old/new stored background, f0, pressure/frozen-density, observations/masks
and control sigmas are independently byte-compared; reference/surface/geometry
H auxiliaries are checked through matching prepared fingerprints and shared
input hashes. Saved BT loss/prior/full-gradient checks are separate.

Private checkpoint mode0600 under0700 directory, SHA
`7eb09d4302ab11932dcc0a4ad15714d9c408d0a1ecaa2f5aae37b48d06b3de11`.
No private weather/NPZ arrays are published. Green/Red reviews pass their stated
receipt/array/source scope. Comparison makes no M/H/optimizer calls. Ruff
passes; no new independent61-step KDM directional finite-difference campaign,
full host adjoint or forecast-skill test is claimed. Public portable CI is
separate from the actual private experiment.

[Declaration](WINDOW_PREDECLARED.json), [preflight](PREFLIGHT.json),
[actual result](RESULT.json), [saved comparison](COMPARISON.json),
[channel table](CHANNEL_COMPARISON.csv), [Green](GREEN_POSTRUN.md),
[Red](RED_POSTRUN.md), [hourly candidate audit](HOURLY_IDENTITY_AUDIT.json).

Only Jul19 has actual analyses. Jul20/21 remain native-pending; the historical
management79 is not rescored. Current calculation/audit/storage and this single
bounded numerical check are completed. Strict convergence and actual temporal
response remain distinct unresolved claims.
