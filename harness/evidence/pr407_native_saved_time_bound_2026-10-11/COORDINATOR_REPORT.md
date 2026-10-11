# Saved native states versus effective producer stop

Basis: main `2d7d1000`, user PR406 review, 2026-10-11. Satellite observations remain GK2A AMI L1B only. The conditional P2 is a case-input consistency gap, not a demonstrated error in the retained July19 analysis or a reason to modify physics, AD or the solver.

## Fixed relation and source contract

The current `intake_native_case_v4.py` computes producer start/stop independently of forecast Times from the hashed effective namelist. It combines nonnegative integer `run_days`, `run_hours`, `run_minutes`, `run_seconds`; a positive combined duration takes precedence over end fields. If all are zero, stop comes from one-domain numeric `end_year/month/day/hour/minute/second`. Start comes from the numeric start components. Optional string aliases must agree and cannot supply missing producer clocks. Unsupported ambiguous/vector clock assignments fail closed within this bounded format.

This follows the current runnable host's `share/set_timekeeping.F` and [official WRF namelist description](https://www2.mmm.ucar.edu/wrf/users/wrf_users_guide/build/html/namelist_variables.html). Source reading is not a certificate for arbitrary historical executable branches. The supported configuration remains the existing one-rank native39-layer,20s,mp337 research variant; operational mp37/137 and production kernels are unchanged.

Initial intake and `load_bound_intake()` require all saved host timestamps within inclusive `[effective_start_time,effective_stop_time]`, verify their ordered coordinate digest and bind the derived producer window to the original case/namelist/receipt. The bounds apply to saved host states. A terminal background can still initialize the separate held-forcing local20s experiment; this does not certify host output or lateral-boundary coverage at the calculated local slot.

The corrected PR407 adapter/driver selects V4 and carries the producer window into capture provenance. The declared T/Q control, all-sky channels10–16, fixed physics, sigma1K, bias0, prior, objective, minimizer, final audit and checkpoint body remain the established path. Its positive earlier-initialization fixture now describes a30-hour producer, instead of a one-minute producer with a next-day state.

## Evidence and team corrections

Red reproduced V2 acceptance using a small synthetic NetCDF/run archive: initialization July19 00:00, run_minutes1, saved background July20 05:55:40. This called synthetic intake and array construction with pinned local reference assets; it was not a real geophysical forecast or M/H/optimizer. The exact V4 regression checks the107,680-second overrun and rejects it before private helper loading or manifest/NPZ publication. The public integration facade uses only temporary synthetic NetCDF and receipt data.

The first V3 draft enforced stop bounds but still admitted string-only start/end aliases. Red checked the actual host getters/Registry and identified that those aliases were not clock sources. V3 source, cases, manifests and private NPZ remain frozen as superseded evidence. V4 requires the consumed numeric components and rejects alias-only or conflicting clocks. Use only V4 for new cases; no recorded source hash was rewritten to conceal the draft correction.

Fresh [V4 core intake](CORE_REPLAY19_V4_INTAKE.json) reads the retained July19 05:55:40 background only. The actual producer starts00:00 and stops05:58:00 from358 minutes; all8 advertised saved times end at05:58:00 and satisfy the inclusive range. [Comparison](CORE_REPLAY19_V4_COMPARISON.json) reports exact equality for70 common arrays against the historical PR395 first saved-time slice (42 time-dependent arrays use that slice); the NPZ has71 arrays. No native integration, M, H, K or optimizer was run. Default observation-required loading refuses this observation-less readiness case; the explicit readiness-only loader passes. The original PR397 outer-harness exit120/unconfirmed cause and science_accepted=false caveats remain.

[July20](PENDING_20250720_V4.json) and [July21](PENDING_20250721_V4.json) retain original PR403 L1B result/payload/metadata bindings but still have no selected native run, no native NPZ and no analysis. No new archive candidate was provided. The same directories were not rescanned, the outstanding archive question was not repeated, and no external model/reanalysis or other satellite/L2 was acquired.

## Validation and remaining work

The focused suite comprises17 intake,15 clock,8 adapter and1 exact counterexample cases: **41 unique cases**. The15 portable facade executions repeat14 pure clock cases plus the exact synthetic NetCDF counterexample; the combined56 executions are not56 unique cases. Pure clock CI tests forbid native helper/NetCDF access; the public integration test permits temporary synthetic NetCDF but rejects private helper access. See [Green](GREEN_STOP_BOUND_REVIEW.md), [Red](RED_STOP_BOUND_REVIEW.md) and [local validation](VALIDATION.json). Broader remote CI is attributed to its head separately; native build skips do not certify builds or private execution.

Actual successful M→H→minimizer→accepted-point saving through the new case adapter is still unexecuted. Complete it on the first genuinely ready date without waiting for the second, using fresh case/output IDs. Preserve unchanged settings and no-cloud/stagnation/quality-failure outcomes; extra host diagnostics can remain N/A. PixelUTC, footprint and IR133 product-SRF assumptions remain conditional. Defined state water/heat changes are not unmeasured flux closure or forecast-skill verification.

The user-owned **79/100** remains unchanged: this correction closes a time-coupling gap but provides no new-date analysis or physical result. [Checklist](../CHECKLIST_pr407_native_saved_time_bound_2026-10-11.md).
