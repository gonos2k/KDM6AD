# Partial actual-auxiliary KDM–RTTOV validation — 2026-09-19

Baseline: PR #218 merge `3f20780efeb7d1b41b49db36255e69f5c1cbe0f3`.
B1/B2 rate-resolution corrections remain closed. This experiment advances V3
with available actual auxiliaries; **full actual-observation-condition validation remains OPEN**.

## Ordered progress

| Item | Evidence | Status |
| --- | --- | --- |
| Actual available inputs | WRF column45577 coordinates/skin/near-surface fields, actual slot UTC applied | Verified selected substitution |
| Fixed comparison conditions | Same observation, sigma=1 K, Huber delta=1, zero bias; ten identical applied auxiliary file sets | Verified |
| First-order derivatives | Two controls × two FD epsilons, live direct/K, genuine KDM/profile forward AD and reverse AD | Verified selected partial-auxiliary case |
| Actual view/solar geometry, upper/gas data | Remain reference or unverified; no measured same-slot navigation available in inspected KO files | OPEN |
| Representative applied paths, units, nonzero M1, N1 convergence | Existing evidence retained; no new closure claim | OPEN / partial |

## Applied values and assumptions

Actual WRF column45577 is (j=194,i=181), ocean XLAND=2 and SEAICE=0.
WRF time and GK2A slot are 2025-07-19 00:00 UTC. The KDM state evolves for
20 seconds under fixed forcing; this is not a proof of temporal representativeness
or per-pixel scan-time matching. Position is the **model column**, not independently
measured per-channel viewing geometry.

| RTTOV input | Requested value/source | Applied text value |
| --- | --- | --- |
| latitude / longitude | WRF XLAT=40.402828216553, XLONG=129.930053710938 degrees | 40.402828 / 129.930054 |
| elevation | WRF HGT=0 m, converted to km | 0.000000 |
| skin temperature | WRF TSK=293.643249511719 K | 293.643250 |
| near-surface temperature | WRF T2=293.082824707031 K | 293.082825 |
| near-surface water vapour | WRF Q2=0.0146863274276 kg/kg; existing dry-mixing-ratio→ppmv-moist conversion | 23067.772582 |
| 10 m winds | WRF U10/V10=3.85882139206/6.37079477310 m/s | 3.858821 / 6.370795 |
| datetime | Actual slot; private clone of fixture, original untouched | 2025 7 19 0 0 0 |

The existing writer rounds auxiliary fields to six decimal places. Both requested
values and actual serialized text are retained. Angles remain reference values
45/0/45/179 degrees; salinity, foam/snow fields, FASTEM and fetch remain declared
configuration values. Not all are necessarily active under the selected IR
options (e.g. use_foam_fraction is false); schema requirements alone do not prove
physical relevance. They are not silently promoted to measured observations.

The fixed RTTOV pressure grid is an interpolation target for actual WRF pressure,
not itself an observed upper atmosphere. Reference upper T/Q and trace gases
remain a separate limitation. Mixed actual/reference geometry is a controlled
partial substitution, not a reconstructed GK2A line of sight.

## Executed derivative evidence

| Process | VJP dJ/dalpha | Forward AD + baseline K | eps | Live central FD | Relative difference |
| --- | ---: | ---: | ---: | ---: | ---: |
| deposition | -0.0399755836827862 | -0.0399755836827863 | 0.03 | -0.039972349999573 | 8.08915e-05 |
| deposition | -0.0399755836827862 | -0.0399755836827863 | 0.1 | -0.0399812149997558 | 0.000140869 |
| riming | -1.73689326474608e-05 | -1.73689326474608e-05 | 0.03 | -1.73833299754733e-05 | 0.000828913 |
| riming | -1.73689326474608e-05 | -1.73689326474608e-05 | 0.1 | -1.7395000071474e-05 | 0.00150081 |

Relative difference uses abs(FD - VJP) / abs(VJP), as in the retained runner.
All four comparisons retain the masks, RTTOV quality and recorded KDM branch
fingerprints, exact profile serialization, and signals above the BT output-spacing
estimate. Existing 5% acceptance rule is unchanged; actual maximum differences
are about 0.0141% (deposition) and 0.1501% (riming). No dK/dx, identifiability or
forecast-skill claim is made. The result describes this mixed-auxiliary operator.

SHA256 equality was checked across all ten cases for angles.txt, datetime.txt,
skin.txt, near_surface.txt and p_half.txt. The same cfg reference profiles,
observation vector and objective definition were reused across the paired runs.

## Reproduction and provenance

Local artifacts (contain private inputs/runtime references; not portable CI assets):
`graphify-out/pr218-science-20260919/run_partial_actual_aux.py`,
`partial_actual_aux.json`, `selected_values.json`, and Green/Red inventory reports.
The wrapper reuses the retained actual_live_control runner and existing writer;
it does not introduce a production auxiliary adapter. An initial wrapper setup
error was corrected before any RTTOV evaluation; no physical result was dropped.

- Result JSON SHA256: `84bb61184f224bca88733bed7484426335bb49a4c7ed0c1631a12492f2d06e15`
- Wrapper SHA256: `d8d7d9e1b2107a9b6026e897ae72b45a4b42f274a6daacc62ae9a9dc8760f90d`
- Actual WRF frame SHA256: `5a9ae8da992028dbf3a2a7652eb61532c1efab2acea7ea0e393e4cac8fd4c970`.
- Source/runtime/observation hashes and applied auxiliary text are retained in the JSON.
- Merge commit3f20780e now has all five GitHub check-runs completed successfully.
  Those baseline CI checks are separate from these new local live calls.

Next required input is authoritative same-slot viewing/solar geometry (or
position/time data sufficient to derive it), and a justified upper/gas ancillary
contract. A path request is pending. No invented values will close those gates.
