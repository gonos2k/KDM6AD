# Actual nine-channel native T/Q analysis and matched seven-channel experiment

Completed on **2026-10-13 KST**, based on main `569892ae` (PR418) plus the
PR419 source-binding/capture-test fixes (`0b85d04a`). The nine-channel experiment
now traverses actual native intake, CWT controls, KDM/AD, all-sky RTTOV/K,
L-BFGS, final objective audit and saved State/control/full gradient. All nine
channels have model quality zero throughout this **explicit DOM1 research
variant**. The original seven-channel Edd3 research closeout remains closed.

This is a bounded diagnostic analysis, not a converged or independently
validated atmospheric retrieval. The saved filename `accepted_state.npz`
does not override the receipt status `RETURNED_DIAGNOSTIC_ONLY`.

## Extinction warning diagnosed before changing the research operator

The private passive trace uses the historical **MP137 07:00 UTC** snapshot
from PR417/418, not the PR412 analysis background. Its lower two RTTOV layers
exceed the Eddington extinction cap of **20 km⁻¹**:

| Physical channel | RTTOV top-down layer | Pressure bounds, hPa | Pre-limit extinction, km⁻¹ | Post-limit |
|---|---:|---|---:|---:|
| WV063 (8) | 65 | 991.875–999.498 | 29.082485 | 20 |
| WV063 (8) | 66 | 999.498–1005.490 | 35.488847 | 20 |
| WV069 (9) | 65 | 991.875–999.498 | 20.922746 | 20 |
| WV069 (9) | 66 | 999.498–1005.490 | 21.780880 | 20 |

Clear/gas extinction alone produces these values; aerosol and hydrometeor
additions are zero in this snapshot. The bit changes from 0 to 32768 in both
direct/K paths. This identifies the warning's numerical location and mechanism,
not an individual-gas attribution, a defect in KDM, or the same layer values in
the different analysis case. See [trace summary](EXTINCTION_TRACE_SUMMARY.json)
and [trigger rows](EXTINCTION_TRIGGER_ROWS.csv).

The isolated control and passive trace produce byte-identical radiance,
transmission and K-profile products and exactly reproduce the saved PR418 BTs
for this one profile. The recorded source was not independently attested to the
original installed binary. No proprietary RTTOV source, patch or binary is
published. The first trace's channel-filter omission and the corrected trace's
postprocessing-schema failure are preserved; recovery reads retained outputs
and does not repeat a model call.

After identifying the cap, the new experiment explicitly selects RTTOV's
existing **DOM thermal solver 1** on isolated fixture copies. RTTOV documents
DOM1 and Eddington3 as distinct thermal options ([RTTOV14 user guide,
Table 8.11](https://nwp-saf.eumetsat.int/site/download/documentation/rtm/docs_rttov14/users_guide_rttov14_v1.1.pdf)).
The original installed executable, coefficient/hydrometeor files, native
inputs and operational/default Edd3 setting are preserved. No quality-bit
waiver, channel deletion, humidity/condensate tuning or error inflation occurs.
The old Edd3 warning is not declared repaired; DOM1 is a separate scientific H.

## Same case, controls and numerical budget as PR412

The original geographically selected natural warm-QC case is reused: native
`j=103,i=48`, 36.1953430176°N/122.0966796875°E; retained **MP337 one-rank**
background at **2025-07-19 05:55:40 UTC**, followed by one held-forcing 20-second
KDM step to nominal **05:56 UTC**. Existing AMI row289/column49 is 425.935m away;
all nine source DQFs are zero. The same pixel-center viewing geometry used by
the PR412 analysis is retained. This differs from the native-center geometry
of the historical hourly trace.

Fresh V4 intake reproduces all **71** previous core arrays exactly. The new
9-channel payload binding checks IDs/order, selected BT/DQF, coordinates and
payload hash. Native39 centers/40 supplied interfaces and 27 upper reference
layers are retained. Interface-pressure identity and actual pixel UTC are
still independently unverified; nominal filename/model UTC is the time assumption.
See [case](CASE.json), [fresh preparation](PREPARATION.json) and
[paired DOM preparation](PAIRED_DOM1_PREPARATION.json).

Both DOM9 and DOM7 start at the same zero control and use initial theta39
(sigma0.8K) and eligible bottom12 log-qv (sigma0.08). Non-T/Q controls and four
physical parameters are fixed. Optical density, pressure, surface/reference
inputs and held forcing are fixed. Observation sigma1K/bias0 and Huber delta1,
normalized-dry/dry-number conventions, max_iter3/default max_eval3 and
strong-Wolfe are unchanged. The pair changes only selected support, within
the same explicitly selected DOM1 H. There is no warm start or optimizer retry.

## Actual fit, audit and saved returned state

The costs below are dimensionless normalized costs; O−B/O−A mean observed
minus modeled BT at the **20-second slot**, respectively H(M(x_b)) and H(M(x_a)).

| Quantity | DOM7 | DOM9 |
|---|---:|---:|
| Initial observation/total cost | 8.0298636774 | 13.2247006976 |
| Final common-seven observation cost | 6.2246563481 | 6.2137447247 |
| Final additional-two observation cost | — | 5.1350736129 |
| Final state prior cost | 0.1072051854 | 0.1198412176 |
| Final total cost | 6.3318615336 | 11.4686595552 |
| Final full-control gradient L∞ | 0.2946562133 | 0.2929647968 |
| Optimizer iterations / function evaluations | 2 / 4 | 2 / 4 |
| Window / final audit evaluations | 4 / 1 | 4 / 1 |
| Full selected support / model quality | 7/7 / all0 | 9/9 / all0 |

Both objective audits are `CROSSCHECKED`; all state/control/gradient arrays,
BT, mask and quality are saved in bound private checkpoints. Every retained H
case writes the declared physical channels in order and DOM1/solar-off.
At the background slot, common channels' raw direct/K products are identical
between DOM7 and DOM9. Final states are separately optimized, so the raw total
costs are not an improvement ratio. The common-seven cost differs by only
−0.0109116235 at these two returned states; that is not evidence of forecast skill.

| Added channel | O−B, K | O−A, K | Absolute residual decrease, K |
|---|---:|---:|---:|
| WV063 | 3.289721495 | 3.261075929 | 0.028645567 |
| WV069 | 2.905115525 | 2.873997684 | 0.031117840 |

Eight of nine absolute residuals decrease; **IR096 worsens**, from −3.053123469K
to −3.463261886K. The new channels retain substantial residuals. Their inclusion
does not activate upper-level humidity controls. Full-channel BT/residual/loss
values and T/qv/RH/QC/NC state diagnostics are in [SUMMARY.json](SUMMARY.json),
[CHANNELS.csv](CHANNELS.csv) and [PROFILE.png](PROFILE.png).

Both final gradients exceed the declared 1e−10 tolerance. PyTorch does not
expose a termination reason here (`UNKNOWN`); four observed evaluations versus
nominal max_eval3 are preserved strong-Wolfe behavior, not an expanded budget.

## Same joint KDM-response analysis as the seven-channel case

Three separately declared value-only H calls fill only missing saved **initial**
BTs: common background with nine channels and each returned initial state with
its own support. Existing slot BTs are reused, with no new M or optimization.
The common background seven-channel slice is reused after exact shared-state
and background-slot BT checks. [PROCESS_RESPONSE.json](PROCESS_RESPONSE.json)
computes R_M(x)=H(M(x))−H(x), I_M=R_M(x_a)−R_M(x_b), and nonlinear Jo gains.

| Joint M-response quantity | DOM7 | DOM9 |
|---|---:|---:|
| R_M(x_a), IR087 | +0.600190483K | +0.600339988K |
| R_M(x_a), IR105 | +0.531204550K | +0.531380474K |
| R_M(x_a), IR133 | +0.134548858K | +0.134567923K |
| I_M, IR087 | +0.600574287K | +0.600723791K |
| I_M, IR105 | +0.531560141K | +0.531736065K |
| I_M, IR133 | +0.134608802K | +0.134627866K |
| R_M(x_a), WV063 / WV069 | — | 0 / 0K in these sampled outputs |
| G_M = Jo(M(x_b))−Jo(M(x_a)) | 1.8052073293 | 1.8758823600 |
| G_0 = Jo(x_b)−Jo(x_a) | 0.2128142657 | 0.2833375310 |
| G_M−G_0 | 1.5923930636 | 1.5925448290 |

For both DOM7 and DOM9, the initial T/Q change leaves QC/NC without direct
controls. After local M, returned QC/NC become zero while background cloud
persists; the paired maxima and fixed-mass water diagnostics are tabulated
below.
The response is jointly caused through the controlled initial state and whole
M; no named-process rates, isolated cloud-only pathway or contribution fractions
were measured. Sampled zero WV R_M does not certify zero humidity sensitivity.
The M-bypassed initial states are not full host states at the later valid time.

| State diagnostic | DOM7 | DOM9 |
|---|---:|---:|
| Largest initial temperature increment | +0.188413508K | +0.186733822K |
| Largest initial qv reduction | 0.000438696kg/kg dry | 0.000436472kg/kg dry |
| Initial liquid-water saturation-ratio maximum | 96.331687% | 96.338890% |
| Returned slot liquid-water saturation-ratio maximum | 96.975776% | 96.999014% |
| Initial QC max, background / analysis | 3.4602017e−5 / 3.4602017e−5 kg/kg dry | 3.4602017e−5 / 3.4602017e−5 kg/kg dry |
| Initial NC max, background / analysis | 23,088,648 / 23,088,648 kg⁻¹ dry | 23,088,648 / 23,088,648 kg⁻¹ dry |
| Slot QC max, background / analysis | 3.4634193e−5 / 0 kg/kg dry | 3.4634193e−5 / 0 kg/kg dry |
| Slot NC max, background / analysis | 23,088,139 / 0 kg⁻¹ dry | 23,088,139 / 0 kg⁻¹ dry |
| Initial analysis-minus-background total water, fixed host measure | −0.1170143635kg/m² | −0.1142649477kg/m² |
| Returned initial→slot total-water increment, same measure | 0kg/m² | 0kg/m² |

Fixed retained host dry-layer-mass water diagnostics are reported separately
from optical rho_d*dz paths and from unmeasured external/boundary budgets.
The QC loss corresponds to −0.0041891880kg/m² and equal qv gain in each
returned initial→slot pair under that fixed measure. These are net endpoint
diagnostics, not a process-ledger or full conservation proof. NC plots use the
declared normalized-dry/dry-number model coordinate; native QN dry-versus-moist
basis was not independently certified. Model q/qs ratios are not observed
vapor-pressure RH. Observed phase/state truth and IR133 SRF qualifications
remain the earlier case's limitations.
For these saved states the phase-aware and liquid-only q/qs maxima are
numerically equal because each maximum occurs in the warm cloud layers
(native levels 3 and 4, about 295K); their saturation definitions remain
distinct at colder levels.

## Independent derivative and provenance checks

The saved DOM9 full state-control gradient was checked against two independent
value-only CWT→M20s→DOM9 evaluations, with Huber/prior recomputed from returned
BT rather than the grad=False worker's zero j. A normalized fixed gradient
direction and h=1e−3 control units give **AD0.5093536523613577** versus
**FD0.5093536529727771**, relative error **1.20038e−9**, with both quality vectors
zero. [DIRECTION_RESULT.json](DIRECTION_RESULT.json) and
[RED_LINEAGE_CHECK.json](RED_LINEAGE_CHECK.json) bind the saved gradient/control
arrays to the public capture checkpoint receipt. This verifies one first-order
direction at one returned iterate, not a full Jacobian, higher derivatives or
identifiability.

The original DOM pair checked its declared source/input/fixture/executable
hashes before/after each whole analysis, not every internal subprocess. Red
found that the KMA BT/K calibration **JSON** was missing from that original
list, although its Python reader was included. Its current tracked bytes are
unchanged; that post hoc fact cannot prove in-run identity. Later direction
and process diagnostics bind the JSON before/after. This limit is explicit in
[PROVENANCE_LIMITS.json](PROVENANCE_LIMITS.json); the old plan is not rewritten.

The PR412 Edd3 seven-channel contrast uses the same **05:55:40** case/profile
and matching fixture files except the solver setting. It is an operator
comparison, distinct from the **07:00 MP137** warning trace. The old temporary
template was not wholly restored byte-for-byte; prepared trace fixtures and
fresh analysis assets have their own bindings. Historical PR417/418 PLAN,
hash, BT and quality evidence remain unchanged. Bound old build records with
incorrect display-zone labels are preserved with the additive
[KST correction](TIMEZONE_CORRECTION.json); model valid times stay UTC.

The campaign contains **20 logical H calls**: three extinction trace/control,
twelve paired-analysis callbacks, two directional checks and three saved-state
process diagnostics. This is not a count of internal RTTOV direct/K launches
or child PIDs. There are two bounded optimizer calls, two explicit FD M steps,
and zero new native integrations or data acquisitions. The initial FD command
failed its thread-environment preflight before any H/M and is preserved.

Local portable support/capture/source-binding tests pass (32); current
scientific runs use Torch2.13 f64 and the retained private RTTOV installation.
Public CI and native-build evidence are reported separately in
[VALIDATION.json](VALIDATION.json), with [Green](GREEN_REVIEW.md) and
[Red](RED_REVIEW.md) reviews. Other dates, strict convergence, actual temporal
fit, atmospheric truth and forecast/cycling validation remain follow-up work;
they do not reopen the existing seven-channel functional closeout.
