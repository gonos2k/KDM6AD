# Native QC–NC boundary trace completion — 2026-10-26

Base main `a1c63630` / PR454. This page supersedes the *measurement-pending*
status in the older dated checklist without rewriting its pinned bytes.

## Measured result

The actual 39-level QC/NC states are now recorded before/after finish, alongside
packed input, FP64 input/output, REAL4 return, writeback, wrapper-post and
pre-zero-out boundaries. Control, alpha1 and alpha0.25 off/on pairs reproduce
their historical full checkpoints bitwise. The telemetry records 6,318 values
and all representation-boundary checks match exactly.

The decisive new observation is that negative NC already arrives at KDM:

| Native witness | Case | NC at MP_INPUT | NC at FP64_OUTPUT |
| --- | --- | ---: | ---: |
| `(221,63,6)` | alpha0.25 | −3.8143992424 | 0 |
| `(91,94,4)` | alpha1 | −0.03163810074 | 0 |
| `(91,94,4)` | alpha0.25 | −0.1718383133 | 0 |

QC remains positive in these failed endpoints. Their zero NC is not introduced
by the REAL4 return, writeback or finish. The first witness `(155,25,19)` instead
starts QC-positive/NC-zero: control/alpha0.25 remove QC within the KDM map,
whereas alpha1 retains it. No positive NC loss is newly established there.

The upstream interval still includes analysis application and native host
preparation/dynamics/other physics. This trace does not identify a named process
or prove that scalar advection is the cause. It also does not certify raw NC units.

## Execution accounting

Eight independent same-origin 40→60 s steps completed, with 16 KDM wrapper
entries, zero RTTOV and zero optimizer calls. Two initial control steps are
retained: their state outputs matched, but their trace included an extra top
storage slot and was rejected. The corrected producer was tested against that
storage/native-level distinction and the three off/on pairs were completed.
No trace rows or criteria were relaxed. This is not eight forecast steps or a DA cycle.

The full forward keeps configured nonadiabatic physics enabled. Runtime readback
confirms `NO_MP_HEATING=0`, `USE_THETA_M=1`, `USE_Q_DIABATIC=0`, RRTMG4/4,
PBL11, CU37 and LSM2; `MP_ZERO_OUT=2`, `MP_ZERO_OUT_ALL=0` are unchanged.

## Updated checklist

| Item | Current status |
| --- | --- |
| R1 FP-environment predicate | Closed in PR454; unchanged here |
| R2 requested-direction Q65 resolution | Closed in PR454; unchanged here |
| R3 producer/reader and actual finish QC/NC | Implemented, strict 39-level coverage verified |
| R4 selected witness boundary measurements | Complete for control, alpha1, alpha0.25 with paired noninterference |
| R5 physically justified admissible proposal | Open; investigate the READY→KDM-input NC transitions and inherited invalid pairs |
| R6 candidate full-domain RTTOV cost | Not computed; original trials remain inadmissible |
| R7 general representable trial wiring | Still open |
| R8 cumulative fixed-prior optimization | Still open |
| R9 second actual assimilation | Not performed |

Next work should trace the signed number update in the upstream interval at the
same native points and original tiles, preserving the full forward. No arbitrary
NC floor, mask shrink or physical-policy change follows from this measurement.

Full data, source/build attribution, exact values and replay:
[native QC–NC evidence](../harness/evidence/native_qc_nc_trace_2026-10-26/README.md).
