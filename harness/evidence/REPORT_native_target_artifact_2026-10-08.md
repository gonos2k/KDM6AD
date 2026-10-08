# Native target-window artifacts and first conditional AMI comparison

2026-10-08. Public baseline: PR #388 `4f1bc9c1612051589185a04e2c841d8afc6b421c`.

The selected VIIRS/native/AMI candidate now has eight actual saved native model
states and eight real RTTOV evaluations. **The long native run is invalid:** WRF
wrote `SUCCESS COMPLETE WRF`, but `prterun` returned 1 and the harness recorded
`experiment_valid=false`. The results below are explicitly diagnostic artifacts
from that failed run, not a passed native experiment, analysis, or forecast-skill
result. R2 remains OPEN. Earlier bounded numerical closures are unchanged.

## Executed model path

An isolated private host copy was configured and compiled; canonical host sources
and the operational library were not changed. Only the isolated mp337 wrapper
selected `physics_variant=2`, `dry_number=1`, `value_only=1`. The public ABI version
is separately 2, with a runtime-checked 344-byte argument structure. The four QN
Registry fields are labelled `# kg(-1)`; this experiment interprets and passes
them as dry-mass number coordinates. That interpretation is conditional S2
policy, not a new physical calibration or host-wide unit approval. On timestep 1
only, the existing volume-concentration NCCN seed was divided by `DEN/(1+Q)`
before entering the dry-number ABI; the ABI makes the inverse internal conversion.
This is an experimental value-only path, not a legacy mp237/mp337 parity pair or
host AD validation. Legacy radius/reflectivity diagnostics do not close S2.

The primary private ISO `.F` source was replaced with the public ABI-v2 shim;
its generated `.f90` is a build artifact. Fresh hook configuration supplies the
isolated `LIB_LOCAL` even when a new `configure.wrf` lacks that assignment.
Compile failures and the final successful build are retained separately.

- WRF executable SHA-256: `f467755ee9952dc2b1806e9dec3220689e2f26a2939234b0959065b1c357cd41`.
- Linked KDM6 C library SHA-256: `64cddefe4fce336a7b9a3979278692324a97a17fe7d5264224bcc05a7f20be2d`.
- A 40-second smoke returned 0, passed the harness validity criterion, and saved
  00:00:00/20/40. Loaded library paths and the normalized/dry wrapper marker were
  checked. This is smoke execution evidence only.
- The 358-minute target used one MPI rank and one thread, 20-second steps and an
  explicit 05:55:40–05:58:00 output window. Its input, executable and library
  hashes remained stable. The archive and case forecast hashes match.

The target forecast SHA-256 is
`ac73e382b3102a9fdad3cd5c9e4ec46b6b25a5997dba53aa1b369b0b9ac8153e`.
All eight expected `Times` exist; all 635,785,640 numeric elements across 253
numeric variables (254 variables total) were checked finite. These checks do
not turn launcher exit 1 into a successful run.

## Failure and diagnostic boundary

The receipt distinguishes a completed monitoring job from a successful model
experiment. WRF's success text and a generic improper-MPI-termination message
coexist. No runtime trace establishes the termination cause. Source-level
`MPI_FINALIZE`/exit ordering alone does not prove which branch finished.
Two isolated 40-second diagnostic attempts did not reach model execution: one
stalled at PMIx bootstrap and was stopped by us; an interface-restricted attempt
returned 213. They do not identify the target run's post-integration failure.

The ordinary comparison gate requires successful, experiment-valid exit 0.
The separate explicit failed-run diagnostic mode checks this run's identity,
nonzero-exit/invalid receipt, WRF success marker, complete finite saved artifacts,
source/input/binary stability and exact output times. Every published comparison
keeps `native_run_valid=false`, `experiment_valid=false`, `diagnostic_only=true`
and `eligible_for_artifact_gates=false`. Exit 1 denotes the runner/launcher code,
not an independently observed standalone WRF process exit code.

## Actual RTTOV inputs and assumptions

At native `(j=86,i=48)`, saved float32 P/PB are promoted before their sum; all 39
native pressure centers and T/Q values are retained. Forty interfaces are a
source-derived REAL(4) transcription of private `share/wrf_timeseries.F::calc_p8w`,
not a saved P8W field. A separately compiled thin Fortran transcription matched
all 40 interfaces in each of the three smoke frames, not the full WRF routine or
an independent target-run P8W measurement.

Each RTTOV profile has 66 layers: 39 native layers plus 27 standard-reference
upper layers. Reference T/Q apply only above the native top. Explicit `p.txt`
preserves native centers rather than replacing them with fixture-layer midpoints.
O3/CO2, absent from the model output, use reference interpolation across the
whole extended grid, including endpoint clamps in six lower layers. These trace
gases are assumptions, not native model values. Density is reconstructed from
saved pressure, THM and QVAPOR; optical dry density is frozen within each direct H
evaluation, not across all eight states. Native surface fields and AMI-center
view geometry are used with recorded ocean/surface assumptions.

The final staged thermal configuration disables solar calculations and sets the
fixture's simple-cloud fraction to zero. It retains the 949-hPa CTP, which the simple-cloud parameter routine still reads;
zero fraction supplies no fallback cloud fraction.
Original reference files remain unchanged. The earlier fraction-0.6 retry is
preserved: all nine BTs, quality values and eight costs are bitwise identical to
the fraction-0 retry. This demonstrates no measured effect in these runs; it is
not a general simple-cloud noninterference claim. The initial solar-enabled
attempt failed input validation and produced no comparison.

The final runner source was copied and hashed **before execution**, with equal
before/after SHA-256 `408bab9756c6ac1a6e8438b8469c87f41fa239ce75414cd8087d10b6a31d54c1`.
RTTOV executable, coefficient and hydrotable before/after hashes, imported-module
identities, executed profile/options hashes and output logs are recorded. Earlier
retry identities captured only after execution are not reclassified as launch
captures. Raw outputs are retained; an additional inventory labels units and
checks the executed native pressure/T/Q suffixes without changing BT or costs.

## Comparison obtained

The table and Huber cost use **KMA v3.0 BT coordinates**, transformed from
RTTOV TOTAL radiance using the paired AMI filter/coefficient and calibration
inputs. They are not native RTTOV BT values. This coordinate calculation does
not certify physical SRF compatibility; that approval remains false.

The original AMI pixel is zero-based `(row=320,col=48)`; IR105 is
291.3025921545636 K. All nine observed DQFs are zero. RTTOV channels 8/9 carry
quality value 32768 (`Delta-Eddington extinction limit exceeded`) in every
frame. Their cause remains unresolved; they are excluded from the frozen common
support. Channels 10–16 have quality zero and form the same seven-channel mask
in all eight evaluations. The cost is a **dimensionless** Huber sum with fixed
sigma 1 K, bias zero and delta 1. It is not a nine-channel accepted cost.

| Saved model time | IR105 H, K | Common-seven Huber cost |
| --- | ---: | ---: |
| 05:55:40 | 296.232817251 | 26.588575903 |
| 05:56:00 | 296.234289029 | 26.597684782 |
| 05:56:20 | 296.235883332 | 26.607456761 |
| 05:56:40 | 296.237174408 | 26.615631826 |
| 05:57:00 | 296.238634818 | 26.624654105 |
| 05:57:20 | 296.239982113 | 26.633180860 |
| 05:57:40 | 296.241311676 | 26.641499400 |
| 05:58:00 | 296.242581617 | 26.649618802 |

Common-support mean absolute residual rises from 4.298367986 to 4.307088400 K.
No minimizer, KDM replay step, DAWindow, FD, KDM6AD adjoint or backward/VJP
is applied here. RTTOV K mode ran and produced matrices, unused in this diagnostic.
The small time change is not optimization descent or forecast improvement.

All saved hydrometeor mass paths in this selected column are zero (LWP/IWP zero).
VIIRS classified its nearby retrieval as liquid. This disagreement is worth
investigating but does not establish a microphysics bug, correct NC recovery or
sensor bias: AMI UTC/pixel timing remains conditional, VIIRS is near the swath
edge, the retrieval footprint/parallax and vertical/cloud QA remain incomplete.
The same AMI observation is compared with eight model times as a timing sensitivity
sample, not a time-aligned observation sequence. Product/SRF compatibility and
scientific observation approval remain false.

## Checklist and next work

| Item | Current evidence | Remaining work |
| --- | --- | --- |
| Independent science/geometry | VIIRS phase, raw QA, scan bracket, height/optical values read in PR388 | Full optical QA, warm single-layer/precipitation interpretation, common footprint |
| Target native state | Eight actual states exist; finite and source-attributed | Resolve native launcher termination before claiming a valid target experiment |
| First comparison | Eight actual H calls and common-seven 1 K/zero-bias diagnostics | Investigate channels 8/9 quality and temporal/geometry assumptions |
| R2 | Partial artifact correspondence | Actual pixel time/UTC, physical correspondence and a valid native run remain OPEN |
| R1/P1/T1/C1/V1 | Previous status preserved | Physical policy/budgets, timestep dependence, different native columns, unused events |

No new solver or generalized data framework is introduced. Do not tune sigma,
bias or candidate selection to this residual. Continue with bounded MPI lifecycle
checks and observation correspondence; neither distribution work nor all-platform
acceptance is required for this internal first attempt.

## Green/Red checks

Three synthetic receipt/fixture checks passed: ordinary acceptance rejects a
completed-but-invalid run, the explicit artifact gate rejects missing verification,
and thermal/simple-cloud edits affect only staged copies. Red independently
recomputed all eight Huber costs and contributions exactly, rehashed assets and
profile inputs, and compared retry1/retry2 radiance/BT/quality outputs bitwise.
Green checked native/build/smoke receipt consistency and the eight table rows.
Review corrected the conditional Registry unit interpretation, CTP still being
read with zero fraction, RTTOV K generation without backward use, and a stale
post-run hash-timing description. These are bounded checks, not additive new
forecast, physics, collocation or derivative acceptance counts.

## Local absolute paths and evidence scope

- Canonical model source: `/Users/yhlee/KDM6AD-k/host/KIM-meso_v1.0/`.
- Actual isolated model source/build: `/private/tmp/KDM6AD-viirs-native-run-20261007/isolated_project/host/KIM-meso_v1.0/`.
- Initial field: `/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS/wrfinput_d01`.
- Boundary file: the same directory's `wrfbdy_d01` (original input bytes reused;
  this directory's historical forecasts were not used as the new trajectory).
- New saved forecast: `/private/tmp/KDM6AD-viirs-native-run-20261007/target_case_055540_055800/runs/mp337_viirs_norm2_dry1_055540_055800_358min_hist0_20261008_064206_p28793/klfs_lc05_fcst.202507190000`.
- RTTOV evaluations: `/private/tmp/KDM6AD-viirs-native-run-20261007/comparison/results_failed_native_artifact_diag_055540_055800_retry2/`.

The small public packet contains retained diagnostic inputs/results and execution
receipts, not the full private host, 2.54-GB forecast or distributable RTTOV assets.
Offline arithmetic replay is distinct from model or RTTOV execution. Graph queries
cover public observation dependencies; this private build/comparison path lacks
complete graph coverage and was audited from source/artifacts. Historical smoke
report statements that the target was still running describe their capture time;
the final target receipt and this report supersede only that live status.

The [public packet](native358_artifact_diag_2026-10-08/README.md) has 374 payloads
plus its manifest; the [receipt archive](NATIVE_target_artifact_receipts_2026-10-08.zip)
passed every ZIP CRC and manifest SHA-256 check. The bounded stored-cost replay
reproduced all eight costs exactly (maximum difference 0). It does not execute
the native model or RTTOV.

Review follow-up (2026-10-08): the historical AMI–native distance field
accidentally held AMI–VIIRS distance. The separate [geometry correction](NATIVE_geometry_correction_result_2026-10-08.json)
records AMI–native 679.550498963 m and AMI–VIIRS 686.643622876 m. Original
result/receipt/archive bytes and all H/cost values are preserved. The
[resolution checklist](CHECKLIST_review388389_resolution_2026-10-08.md) separates
this closed metadata correction from still-open termination and correspondence work.
