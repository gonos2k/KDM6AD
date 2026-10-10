# PR399 vertical-neighbor Red review

This review covers the saved-array vertical diagnostic and completed fixed-
geometry 3×3 direct-H comparison. Red read source and saved artifacts only;
Red made no M, H/RTTOV, optimizer, or native forecast calls. The vertical
calculation reads the immutable PR398 native patch NPZ; it does not open or
re-extract the forecast.

## Vertical diagnostic

`VERTICAL_RESULT_v2.json` is `READY_DERIVED_DIAGNOSTIC_ONLY`. Its source is
the hash-bound PR398 V3 NPZ
(`947c72c12ebe289b7ddc84fba1281635d77ffbcfe23f204345cc97abeebc1c21`).
It contains 324 lower-12 profile rows (27 native column/time profiles × 12
levels), 27 maxsat context rows, and 27 finite-endpoint decomposition rows
(three time pairs per nine cells). The native phase-aware maximum `qv/qs`
occurs at bottom-up level 3 for every column/time profile.

Vertical coordinates use float64-first `(PH+PHB)/g`; layer midheight AGL
averages adjacent interfaces and subtracts the saved HGT, retaining nonuniform
spacing. Lower-12 midheight spacings span 60.3–436.8 m. Center pressure is
native `P+PB`; P8W interface values are a separate Python REAL(4)
transcription. The two `theta_v` expressions,
`theta_d*(1+qv/epsilon)/(1+qv)` and `(THM+300)/(1+qv)`, agree within
`5.7e-14 K`; the saved array matches my independent reconstruction exactly.
This uses the native dry mixing-ratio convention, not a relabeling of
`theta_d`.

For `S=100*qv/qs_water`, I independently recomputed the warm-water analytic
qv/T/p partials from the pinned KDM6 unclipped `qs_water(T,p)` equation. The
maximum difference from the saved CSV contributions was below `2e-16`
percentage points; the nonlinear finite-step remainder matched within
`4e-13` points. All layer-3 endpoints were warm and outside the `qs_water`
clipping branches. The remainder is the endpoint difference minus the local
first-order terms, not a process rate or process attribution.

One V2 report statistic is wrong and remains preserved in the raw result. It
reports 891 valid adjacent-level pairs, but the 27 profiles already include
nine cells at three times. Twelve lower levels contain 11 below-neighbor pairs
per profile, for **297** pairs total. The profile CSV has 324 rows, 297 with a
below-neighbor value. The counts 51 temperature-inversion flags and 216
positive `dtheta_v/dz` flags are valid over those 297 pairs. The separate
`VERTICAL_COUNT_AUDIT.json` binds the raw artifacts and records this
correction; no V2 output was rewritten. The future V3 counter is not executed
evidence.

## Direct-H neighbor result

The failed first attempt is preserved. It stopped before any RTTOV call
because `_run_neighbor` omitted the required `o3_rttov_topdown_ppmv` and
`co2_rttov_topdown_ppmv` inputs to the native fixture helper. Manual recovery
used a new attempt-2 plan and output namespace. Before H, the offline preflight
called the existing fixture helper on each of the eight neighbors and checked
the resulting six pressure/temperature/humidity/gas vectors. All vectors
have the expected 66/67 profile lengths, and I independently rebuilt each
profile from the saved PR398 NPZ: all eight fixture files match those values
exactly. No H, M, or model call occurred during this preflight.

The one-shot attempt-2 result is `ALL_NINE_ROWS_RETURNED`: eight new direct-H
calls and the already executed center H reused without a new call. Each row
retains the fixed AMI geometry, channels 10–16, all-seven frozen support, and
the same target, sigma, bias, and Huber delta. Every row has seven zero
`rad_quality` flags and a reported cost. Each neighbor RTTOV log has seven
“Quality OK - no bits set” channel entries and empty stderr. I recomputed all
nine Huber costs from the saved BT vectors and fixed target; every value
matches exactly. The center BT vector and cost are unchanged from PR398 V2.

| Native cell `(j,i)` | Jo (Huber K units) | Maximum absolute BT difference from reused center (K) |
|---|---:|---:|
| (85,47) | 26.8011012031 | 0.1024257 |
| (85,48) | 26.5314165214 | 0.0513597 |
| (85,49) | 26.1407416552 | 0.1174473 |
| (86,47) | 26.7036937938 | 0.1070460 |
| (86,48), reused center | 26.5976847821 | 0 |
| (86,49) | 26.3582751199 | 0.1101141 |
| (87,47) | 26.1833334785 | 0.1518650 |
| (87,48) | 26.2549936230 | 0.1052263 |
| (87,49) | 26.1759997226 | 0.0919929 |

For all eight neighbor runs, the active `p.txt`, `p_half.txt`, `o3.txt`, and
`co2.txt` in the H case directory are byte-identical to the validated offline
fixture vectors. `t.txt` and `q.txt` are overlaid by the observation writer;
their parsed numeric values are exactly equal to those same per-column
preflight vectors. The private NPZ preserves the nine columns' State, Forcing,
rho-d, P8W, surface, profiles, BT, quality, target, and support. Its SHA-256 is
`4e2c36075e69d000bff48db8b2586ff1378adda3297508c58caa72b092e1c793` (file
0600 in a 0700 directory). The result records eight new H calls, zero center
H calls, zero M/optimizer/native calls, and no retry.

These are direct `H(native saved State, Forcing)` diagnostics, not
`H(M(xb))`. All columns use the one fixed AMI candidate geometry; row-to-row
changes combine native State, pressure, density, and surface under that fixed
view. They do not test footprint overlap, per-pixel time, parallax, or
candidate replacement. Cost differences are not a neighbor-selection rule,
forecast-skill result, or scientific matchup approval.

## Evidence and preserved attempts

- Vertical results: `VERTICAL_RESULT_v2.json`, `VERTICAL_RESULT_v2.csv`,
  `VERTICAL_MAXSAT_CONTEXT_v2.csv`, `VERTICAL_SENSITIVITY_v2.csv`,
  `VERTICAL_REPORT_v2.md`, and `VERTICAL_COUNT_AUDIT.json`.
- Attempt 1: `NEIGHBOR_ATTEMPT1_FAILURE.md` and
  `graphify-out/pr399-native-neighbor-h-2026-10-10/private/FAILURE.json`;
  no rows completed and no H was called.
- Attempt 2: `NEIGHBOR_PLAN_attempt2.json`,
  `graphify-out/pr399-native-neighbor-h-attempt2-2026-10-10/private/OFFLINE_FIXTURE_PREFLIGHT.json`,
  `NEIGHBOR_RESULT_attempt2.json`, `NEIGHBOR_TABLE_attempt2.csv`, and
  `NEIGHBOR_REPORT_attempt2.md`.
- There is no attempt-2 failure or retry; its `STARTED_ONCE.json` binds the
  authorized attempt-2 plan and source.
- Attempt-2 plan SHA is
  `5451176d914b5758ffc6315f08a957ae0b6f6ae38019df38faa5b4e58c086afb`,
  executed source SHA is
  `1ab829a94daa80c211984f7ddfbbe9bb825aa859a44bdc5aa83645368459e947`,
  result SHA is
  `2bf488dca1a39f5c8d6fc19fd299a5a4de2560cfa083b98dc0bafd133f150422`,
  and postrun audit is
  `NEIGHBOR_POSTRUN_AUDIT_attempt2.json`.

The vertical output supports saved native structure, and the successful
attempt-2 batch supports fixed-geometry spatial sensitivity for these nine
saved columns. Neither establishes a PBL cause, process-rate attribution,
retrieval identifiability, physical footprint or time match, forecast skill,
or scientific acceptance.
