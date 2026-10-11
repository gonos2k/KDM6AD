# Green review: archived WRF saved-time production bound

## Result

The corrected V4 intake derives the producer initialization from the numeric
`start_year/month/day/hour` fields (with omitted `start_minute/second` defaulting
to zero), then derives an inclusive production stop from all supported
`run_days/run_hours/run_minutes/run_seconds` components. If all run-duration
components are zero, V4 requires numeric `end_year/month/day/hour` fields (with
minute/second defaulting to zero). A `start_date` or `end_date` string, when
present beside numeric fields, must agree; it cannot stand in for missing
producer clock fields. Multi-domain vectors, duplicate assignments, incomplete
clocks, invalid ranges, negative durations, and zero-duration cases without a
numeric end clock fail closed.

This follows WRF's documented time-control rules: duration components may be
combined, take precedence for `wrf.exe`, and an all-zero duration uses the
beginning/ending times. The implementation's one-domain numeric field limit is
explicit. See [WRF namelist best practices](https://www2.mmm.ucar.edu/wrf/site/documentation/namelist.input_best_practices.html),
especially the `&time_control` section.

V4 checks **every** archived `Times` entry against the inclusive interval
`[effective_start_time, effective_stop_time]` during both `load_case` and
`load_bound_intake`. The manifest stores the full coordinate's count, first
time, last time, and ordered-times SHA-256, then the loader reopens and
revalidates it. The required background must also be no later than the stop.
The separate local observation/model slot at background+20 seconds is not a
saved-host-time request and is not capped by production stop. A focused
terminal-background test confirms the local slot can be 20 seconds beyond the
saved-time endpoint.

## Executed evidence and history

The first V3 implementation and its output records remain intact as a
pre-correction attempt. Red's source check clarified that WRF consumes numeric
component clocks; the initial V3 implementation had allowed string-only date
fallbacks. V3 was therefore superseded before it became the accepted
consumer. Its source and records were not overwritten. **The V4 evidence below
is controlling.**

The fresh V4 Jul19 readiness replay binds the original PR397 completion
receipt and existing archive. Its eight saved times span
`2025-07-19_05:55:40` through `2025-07-19_05:58:00`; the derived production
stop is `05:58:00` from `run_minutes=358` beginning at midnight. V4 selected
only index 0, the background at `05:55:40`, and recorded the full-times digest
in its manifest. All 70 common arrays match the historical PR395 eight-frame
fixture's first saved-time slice; 42 time-dependent arrays compare the V4
singleton frame with the historical first slice. V4 writes 71 arrays, one
additional background dry-density array beyond the shared 70.

The intake contains no bound observation. The default analysis loader refuses
it; only the explicit `require_observation=False` readiness path accepts it.
The bound PR397 receipt records launcher exit 0 and `model_completed=true`,
alongside outer-harness exit 120 with cause unconfirmed and
`science_accepted=false`. This replay proves bounded consumer readiness only.

Fresh V4 July20 and July21 cases both return `PENDING_NATIVE_INPUT` with no
forecast open and no NPZ. They preserve the date-specific target times and
existing PR403 bindings. Neither date has native state/forcing or an analysis
result yet. The first ready date can proceed independently.

## Tests and limits

V4 consumer and time-contract tests passed **32/32**. The public-friendly
time-contract module identifies its pure test functions with
`PORTABLE_TIME_TEST_NAMES`; those tests cover additive duration precedence,
numeric end-field fallback, unsupported aliases/ambiguity, earlier valid
initialization, inclusive terminal saved time, and a local +20-second slot
beyond stop. One additional integration test creates a small synthetic
NetCDF and rejects a post-stop `Times` value before loading private helpers.
Ruff, Python compilation, and `git diff --check` passed.

No WRF/native integration, model state beyond the selected column, M/H,
optimizer, new-date analysis, archive inventory, or data acquisition was run.
The user-owned assessment remains **79/100** on the same rubric; correcting a
time-window gate and replaying one same-date background does not demonstrate
new-date science or increase that score.
