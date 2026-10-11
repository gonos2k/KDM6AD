# Green review: saved-time production-stop bound

## Disposition

The current V4 consumer, capture adapter, driver, portable time facade, and V4
Jul19 evidence are consistent for the bounded saved-time contract. V3 remains
preserved as the earlier attempt and is superseded; V4 is the accepted source
and record. This review covers saved-time bounds and synthetic case wiring,
not broad scientific acceptance.

## Contract and adapter

V4 reads the producer clock from numeric WRF `start_year/month/day/hour`
components, with minute/second defaults of zero. A string `start_date` alias
must agree and cannot supply a missing producer clock. Positive
`run_days/run_hours/run_minutes/run_seconds` fields combine into the inclusive
effective stop, following WRF time-control priority. When all run components
are zero, V4 requires numeric `end_year/month/day/hour` components, with
minute/second defaults of zero; a present `end_date` alias must agree. Vectors,
duplicate or incomplete fields and unsupported aliases fail closed. The
time-control rules are documented in [WRF namelist best practices](https://www2.mmm.ucar.edu/wrf/site/documentation/namelist.input_best_practices.html).

`load_case` checks every WRF `Times` value against the inclusive interval
`[effective_start_time, effective_stop_time]` before loading private reader
helpers. `load_bound_intake` repeats the bound and validates the full ordered
Times count, endpoints and digest. The required background cannot exceed the
producer stop. The +20-second local observation slot remains separate from
saved WRF outputs. The synthetic terminal-background adapter case sets
background equal to producer stop and confirms the local slot 20 seconds later
still maps to a derived experiment state.

The adapter and driver select V4. The driver carries producer start/stop into
its run contract and retains the fixed local 20-second, one-column T/Q setup.
Its eight synthetic tests cover ordinary earlier initialization, terminal
background, State/Forcing mutation, payload/geometry/template checks, and an
analysis-entry stop before M/H/optimizer. They execute no physical analysis.

## Evidence and counts

The controlling Jul19 V4 manifest binds V4 consumer SHA-256
`e1449548820510edc4fb213872df4446405058a318f8b99cd811d8470a139ae5` and the
existing PR397 completion receipt. It records eight archived saved times from
`2025-07-19_05:55:40` to `2025-07-19_05:58:00`; the effective stop is inclusive
at 05:58:00, computed from the actual numeric WRF start components and
`run_minutes=358`. V4 selected only saved index 0, the 05:55:40 background.
All 70 shared arrays match the same-time first slice of the historical PR395
fixture; 42 time-dependent arrays compare the singleton frame with that
first slice. V4 contains 71 arrays, adding one background dry-density array.
The full Times coordinate is represented by count, endpoints and ordered
coordinate SHA-256 in the manifest.

The native-only replay is refused by the default observation-required loader.
The explicit readiness override accepts it without authorizing observation
analysis. The bound PR397 receipt still records launcher exit 0 and
`model_completed=true`, as well as outer-harness exit 120 with an unconfirmed
cause and `science_accepted=false`; this same-date replay does not override
those limits. Fresh V4 July20/21 records remain `PENDING_NATIVE_INPUT`, with
no forecast reads and no NPZs.

The exact reviewer counterexample is also covered synthetically: a run
initialized at `2025-07-19_00:00:00` with `run_minutes=1` cannot contain a
saved July20 background at `05:55:40`; V4 rejects it before private helper
loading and creates neither manifest nor NPZ. That timestamp is 107,680
seconds past the declared producer stop.

Validation totals are **41 focused tests**: 17 V4 intake tests, 15 saved-time
contract tests, 8 synthetic adapter tests, and 1 exact counterexample test. The
two portable Oracle facades passed **15 tests**: 14 pure time-contract tests
and the repeated exact counterexample. Every facade test is already in the
focused set; these are not additional unique cases. The combined command
returned 56 passes, representing 41 unique focused cases and 15 repeated
facade executions. Ruff, Python compilation and `git diff --check` passed.

The initial V3 source and executed files remain unchanged as superseded
history. No new WRF model launch or integration, H/M, optimizer, new-date
native read, archive scan, or external data acquisition was performed for this
review. The user-owned assessment remains **79/100** on the same rubric. This
saved-time fix and a same-date intake do not demonstrate July20/21 science or
increase that score.
