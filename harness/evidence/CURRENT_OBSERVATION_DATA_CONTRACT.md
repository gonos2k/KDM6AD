# Current observation-data contract

User instruction, 2026-10-11: **the current research edition uses GK2A AMI Level-1B as its only satellite-observation input**. Other sensors and Level-2 products are later extensions after this edition is completed.

## Admitted observations

- Source-pinned GK2A AMI L1B files, their original DN/packed words, radiance/BT conversion metadata, DQF, geolocation/navigation and available acquisition-time metadata.
- Existing native model State/Forcing and IC/BC remain model inputs. RTTOV coefficients, optical conversion, fixed gases/surface and upper reference atmosphere remain separately declared model assets or research assumptions, not measured independent observations.

## Deferred observation extensions

- GK2A L2 SST, AAP, cloud mask/phase/top/optical products and total ozone.
- VIIRS, NOAA-20 SST, MLS and other instruments' observed values, masks, phase classifications or profile constraints.
- Newly acquired/substituted external model or reanalysis data. Original native-input provenance and the already-requested archive path remain separate open items.

External SST, ozone/temperature profiles, cloud-phase truth and cross-sensor validation are not current completion prerequisites or score deductions. Existing native initial/boundary inputs and required RTTOV model assets remain in scope; the satellite-data limit does not remove them.

Published historical evidence is preserved. It does not authorize excluded sources as evidence for a new GK2A-L1B-only result. Admitted GK2A L1B bytes and the native column at previously recorded coordinates may be reused as an explicitly fixed test case. That reuse does not admit the historical VIIRS phase label or selection rationale as a current criterion, establish a warm-liquid matchup, or add independent-validation credit. New physical candidate selection and interpretation must use only admitted L1B information and stated model assumptions.

## Interpretation limits

L1B DQF measures the stated L1B data quality; it is not a clear-sky, cloud-phase or SST retrieval-quality flag. Window-channel BT is not an independently retrieved SST. A single absorption channel or BT vector is not an observed vertical O3/temperature profile. Derived cloud or input-error hypotheses must be labeled as hypotheses and cannot become independent truth through residual fitting.

Source identity, units, channel order, native pressure interfaces, KMA BT coordinate and fixed support remain explicit. Do not redo closed arithmetic/finite-difference campaigns solely because this data policy changed. Future case/time extensions must keep L1B provenance and distinguish new observations from reused or fitted evidence.

Earthdata/MLS and NMSC L2 file/key questions issued earlier in this session are withdrawn; no reply or credential is needed for them. Untracked external/L2 planning is preserved privately as withdrawn and is not active scientific input. No production physics, AD, solver, covariance or support default was changed by this contract.

## Current completion focus

Assess L1B decoding/calibration/time/location/quality and RTTOV compatibility; analysis in the declared T/Q control space; reproducible baseline, minimization, accepted-point reevaluation and failure handling; scoped numerical/physical diagnostics; and date/scene-separated L1B cases. Unknown pixel time, geometry or spectral identity must be explicit checked assumptions/limits, not fabricated certificates. Do not increase the prior broad56/75 management score solely by narrowing scope; map the current evidence against these revised requirements before reassessment.

BT fit and modeled T/Q/cloud/number changes are current outputs. They need no mandatory external truth source for this edition, but better BT alone does not independently validate phase, height or particle number. Conditional residual statistics are not automatically pure observation error R. Keep the existing1K sigma, zero bias and T/Q prior as declared exploratory assumptions unless a separately specified comparison changes them.

The user's PR403 review now defines a separate [78/100 management baseline](AMI_L1B_MANAGEMENT_RUBRIC_2026-10-11.md) with explicit weights. It is not a performance gain relative to56/75; subsequent fixes do not increment it without an evidence-based reassessment.

The PR404 user review updates the same management rubric to79/100. Native admission depends on provenance-bound valid time, required boundary/forcing coverage and native state/pressure/surface, not an initialization-date equality requirement. ExistingBC record starts through09UTC have a finalNEXTBDYTIME endpoint12UTC; neither establishes July20/21 availability. Nominal L1B time assumptions remain separate from observed pixelUTC.
