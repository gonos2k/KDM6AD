# PR399 vertical structure and neighbor H checklist

Base: merged PR398 main `c81eab38`. Earlier spatial/budget/gradient/route/quality
closures remain scoped and closed. Fixed native cells and AMI candidate stay
unchanged. No new forecast or optimization.

| Task | Status | Evidence and limits |
| --- | --- | --- |
| Stored native lower12 vertical structure | Done | `VERTICAL_RESULT_v2.csv`:324 rows, actual height/pressure/nonuniform spacing,27 context rows; theta-v forms crosschecked |
| Endpoint S changes and q/T/p partial terms | Done | `VERTICAL_SENSITIVITY_v2.csv`:27 comparisons, warm/unclipped, finite-step remainder; not rates or named-process attribution |
| Incorrect adjacent-pair denominator | Resolved separately | Raw V2/aliases retain891; `VERTICAL_COUNT_AUDIT.json` establishes297 valid pairs,51 inversions/216 positive theta-v gradients; future source V3 unexecuted |
| Central direct H reuse | Done | Exact State/Forcing/rho/P8W/surface/full-profile/geometry/assets identity with PR398; no new center H |
| Neighbor producer gas-vector omission | Fixed before H | Attempt1 failed at fixture preparation, H0; preserved failure/source. Attempt2 offline actual six-vector fixture preparation validated for8 cells |
| Fixed-geometry neighbor H | Done | `NEIGHBOR_RESULT_attempt2.json`:8 new H+1 reused center, all9 rows/7 channels quality0, all costs rechecked; no automatic retry |
| Model versus observed patch ranges | Done | `NEIGHBOR_RANGE_COMPARISON.json`:IR105 model minimum remains2.37395K above observed maximum; fixed inputs/regions/paired-coordinate conditions |
| Original native IC/BC connection | Done, bounded metadata | `IC_BC_SOURCE_TRACE.json`:canonical symlinks resolve to original REAL_EM V4.6.0 outputs,5km/39levels,July19 initialization and BC through09:00; original upstream meteorological input not identified |
| Other native IC/BC archive path | Awaiting optional user input | Existing inspected stock has no other initial days. No external model/reanalysis acquired, dates not relabeled |
| Final Green/Red and canonical source preservation | Done | `GREEN_REVIEW.md` / `RED_REVIEW.md` and `PRESERVATION_VERIFICATION.json`:actual/source hashes and private modes checked; original attempts retained |
| Independent events / footprint / calibrated B,R / full flux closure | Open | Current one-event diagnostics do not close these |

Management basis remains56/75 (74.7%). No additional points for the repeated
event, profile count, new script or CI count. Read reporting corrections before
interpreting the original V2 records.
