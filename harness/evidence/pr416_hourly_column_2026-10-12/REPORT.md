# Actual hourly native column: 05,06,07 UTC on Jul19

The requested bounded read is completed once: run-specific historical MP137
four-rank child, fixed native column j103/i48 (36.195343N,122.096680E), actual
saved05/06/07 frames,39mass levels/40interfaces. No new host/KDM/RTTOV/optimizer
or L1B decode was performed; no interpolation to06:06/06:16 and no substitution
into the retained one-rank/current-variant PR414/415 problem occurred.

## Observed model-state changes

| Model saved time | QCLOUD path g/m² | QRAIN path g/m² | Model TSK K | Model T2 K |
|---|---:|---:|---:|---:|
| 05:00 | 7.922123 | 0.013222 | 298.629486 | 297.422943 |
| 06:00 | 2.475426 | 0 | 298.691742 | 297.568512 |
| 07:00 | 0 | 0 | 298.750793 | 297.806305 |

QICE/QSNOW/QGRAUP are0 at these samples. Cloud-path changes are modeled endpoint
changes under time-specific host dry-mass weights, not observed cloud truth,
evaporation rates, particle budgets or closed external fluxes. Host dry mass
itself changes; no constant-mass budget is inferred across hourly samples.

| Maximum absolute difference at the same native eta index | 05→06 | 06→07 |
|---|---:|---:|
| Physical temperature K | 2.522444 | 0.890662 |
| QVAPOR g/kg dry | 0.310375 | 0.399122 |
| Center pressure Pa | 36.293274 | 114.959473 |
| Layer-center geometric height m | 11.095432 | 5.261292 |
| Layer thickness m | 7.832907 | 2.762846 |
| Eastward centered wind m/s | 2.921528 | 2.231528 |
| Northward centered wind m/s | 5.004093 | 2.848893 |

These compare the same native layer indices; the pressure/height coordinates
move. They are not fixed-height/isobaric tendencies or Lagrangian parcel
changes. Only three hourly snapshots are saved here; no subhourly trajectory,
process attribution or 10-minute actual host state is manufactured.

The actual historical host column therefore has nonzero thermodynamic,
hydrometeor, metric, surface and wind changes. This gives concrete motivation
for a separately defined time-dependent-input study, rather than further
optimization of the fixed-f0 window. It does not prove which missing host
process caused PR415's flat sampled BT, or that varying forcing alone supplies
advection/mixing/dynamics or reproduces AMI temporal changes. No H was evaluated
on these hourly profiles, so their BT response is unknown.

## Units, selected read and pre-execution correction

Before any weather-column read, root found an error in the unexecuted draft:
`temperature=theta_m*PII` lacked the moisture correction. The corrected path is
`theta_m=THM+300`, `theta_dry=theta_m/(1+(Rv/Rd)*qv)`,
`T=theta_dry*PII`. Earlier Green/Red static endorsements missed this research
postprocessing error; the draft source/plan/reviews are preserved explicitly as
unexecuted drafts. The final plan was regenerated and only the corrected
source executed. No prior PR414/415 analysis or original reader was altered.
Green/Red independently recomputed T from saved raw data after execution.

P and PB are separately promoted to float64 before summation. PH/PHB raw
float32 arrays are retained; geometric interfaces use their float64 sum/G.
Native39centers and Python REAL(4) P8W40 interfaces are retained. P8W is a pinned
source transcription, not an independently saved producer interface-pressure
variable or new producer-binary validation. Derived dry/moist densities and
host eta dry-mass weights follow existing reader conventions. Raw hydrometeor
and number/volume fields, their dtype/unit metadata and source masks remain
separate; no independent native number-basis or process-rate claim is made.

U/V are centered using adjacent staggered faces, with those faces preserved.
Grid-relative winds and earth-rotated components using actual COSALPHA/SINALPHA
are distinct. W retains40interface values; the public table shows lower/upper
interfaces. Surface U10/V10 remain raw source values. There is no reconstruction
of transport tendencies or rebalancing of a host analysis field.

Only declared column and wind-neighbor hyperslabs plus small1D metrics/metadata
were read. All selected masks are0 and raw fields arefloat32.117CSV rows are
three39-level profiles, not117 weather cases. Private NPZ:270raw/derived/mask
arrays, mode0600/directory0700, SHA
`4a2f7e636c90ab38fa7a09d123977d82f093d0a956051d83ced53e21575760ec`.
Forecast before/after stat matches; per-slice hashes bind consumed values.
No whole4.13GB forecast digest was taken, so stat stability does not certify
all unselected bytes. Public profiles are bounded summaries, private NPZ/raw
source assets remain untracked.

## Provenance and completion limits

Historical child `mp137_termparity_720min_hist60_np4_20260718_185625` has known
normal00–12 termination,13hourlyframes, and an attributed historical parity
report. It is not the current retained MP337 one-rank experiment. Parent/child
full-byte equivalence, exact old executable/ICBC bytes and chainp START_DATE2024
versus Times2025 remain unresolved; none was silently certified by this read.
Boundary THIS/NEXT's last interval is09–12, permitting terminal12 rather than
further advancement. Model times are archived model-clock coordinates, not
independent atmospheric truth or verified AMI pixel UTC.

Green/Red independently reviewed the saved selected NPZ without reopening the
forecast, checked raw slice hashes/masks, thermal/pressure/height/density/mass
arithmetic, wind centering/rotation and all117 public profiles. Ruff/compile and
source/plan checks pass. No extra numerical-budget, whole-model/whole-reader
regression, FD campaign or forecast-skill test is claimed. Existing single20s,
natural-QC contribution and bounded three-slot results remain closed in their
original scope; strict convergence, temporal BT reproduction and other dates
remain separate.

[Plan](PLAN.json), [read receipt](SUMMARY.json), [117-level table](PROFILE.csv),
[saved temporal changes](CHANGES.json), [Green](GREEN_POSTRUN.md),
[Red](RED_POSTRUN.md). Jul20/21 native analyses remain pending. No new external
model/reanalysis/satellite/L2 or score recalculation is introduced.
