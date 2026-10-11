# Red review: WRF saved-time stop bound

## Disposition

V2 had a **P2 consumer provenance gap**: the intake could accept a saved state
outside its producer's declared runtime, making a future analysis consume a
time-inconsistent background. V4 closes the reproduced gap. I found no
remaining stop-bound counterexample in the reviewed V4 intake path. This is a
bounded review of effective WRF run time and the local KDM slot contract; it
does not certify a July20/21 native forecast or completed analysis.

## Counterexample and source basis

The full synthetic V2 intake result is preserved in
[`V2_STOP_BOUND_COUNTEREXAMPLE.json`](V2_STOP_BOUND_COUNTEREXAMPLE.json), copied
without alteration from the original local reproduction record (retained under
ignored `graphify-out/pr407-red/`); its current V4 regression is
[`test_saved_time_counterexample.py`](test_saved_time_counterexample.py). It
creates a one-minute producer initialized at `2025-07-19_00:00:00` and a
synthetic one-time NetCDF forecast whose only `Times` value is
`2025-07-20_05:55:40`. V2 executed full `load_case` intake on synthetic NetCDF
and synthetic run receipts, generated its normal 71-array NPZ, and returned
`READY_CORE_NATIVE_INTAKE`; it used the private P8W/reference assets admitted by
that old intake. The effective stop is `2025-07-19_00:01:00`; the saved state is
**107,680 seconds (29 h 54 min 40 s) after the stop**. V4 now rejects this
input before loading the preserved private reader and leaves neither a manifest
nor an NPZ. No actual WRF forecast, KDM analysis, H/M kernel, or optimizer was
run.

The authoritative local host behavior is in
`/Users/yhlee/KDM6AD-k/host/KIM-meso_v1.0/share/set_timekeeping.F`: when any
`run_days`, `run_hours`, `run_minutes`, or `run_seconds` component is positive,
WRF builds one additive interval and sets `stopTime = startTime + run_length`;
otherwise it constructs stop time from numeric
`end_year/month/day/hour/minute/second`. The domain clock is created with that
start and stop. The matching upstream WRF namelist documentation says the
run-duration fields may be combined and take precedence over end fields
([WRF namelist reference](https://github.com/wrf-model/WRF/blob/master/run/README.namelist));
the upstream implementation uses the same interval-versus-end-time branch
([WRF `set_timekeeping.F`](https://github.com/wrf-model/WRF/blob/master/share/set_timekeeping.F)).

## V4 review

V4 computes the interval from the actual numeric WRF start fields and combines
all four duration components. If all duration fields are zero, it falls back
to numeric end fields. It requires a single unambiguous domain clock: missing
required numeric components, invalid ranges, negative durations, duplicate
assignments, vectors, continued assignments, and a string-only `start_date` or
`end_date` fail closed. Optional date aliases are accepted only when their
timestamp agrees with the numeric fields. This deliberately bounded parser is
not a general WRF namelist parser.

At initial intake, V4 checks every forecast `Times` entry against the inclusive
producer interval. The bound reload path repeats that check and validates the
saved-time count, endpoints, and ordered-time digest against the bound
manifest. A saved background exactly at the stop is allowed as a terminal
state; the local observation slot 20 seconds later is a derived KDM experiment
time and does not claim that WRF advanced past its stop. The V4 synthetic
terminal-time tests cover that distinction.

The same-date V4 record reports an effective window of
`2025-07-19_00:00:00` through `2025-07-19_05:58:00` from `run_minutes=358`, and
selects the saved background at `05:55:40`. It is explicitly an intake-only
record (`analysis_executed=false`). The V4 July20 and July21 records remain
`PENDING_NATIVE_INPUT`; neither has a forecast read or NPZ. V1/V2 records and
V3's superseded source/records remain historical and were not changed.

## Validation and limits

I independently ran the V4 intake, time-contract, adapter, and exact
counterexample tests: **41 passed**. I also ran the two portable Oracle
facades: **15 passed**, including a repeat of the counterexample behind guards
that forbid access to private legacy helpers and NetCDF reads. The 15 facade
executions repeat cases from the focused suite; the total is 41 unique cases.
The test commands used local `python3` (Python 3.10). No new-date input or
physical analysis was run.

The graph query available in this worktree did not retrieve relevant saved-time
nodes, so this review relies on direct source inspection and the tests above.
It does not establish that an archived forecast is scientifically accepted,
that July20/21 native inputs exist, or that their analysis succeeds.
