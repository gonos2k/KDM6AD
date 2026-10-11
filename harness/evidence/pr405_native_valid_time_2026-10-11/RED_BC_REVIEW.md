# Red review: LC05 lateral-boundary time coverage

## Scope

This check reads only the boundary-time fields from canonical `host/lc05_da_run/wrfbdy_d01` and small runnable-host snippets that write/read `THISBDYTIME` and `NEXTBDYTIME`. It does not read boundary meteorological arrays, inspect other boundary files, scan archives, request data, or run the model. GK2A AMI L1B remains the sole observation platform in scope.

The graph query for boundary-time producers and consumers returned broad, weakly related nodes; the exact source snippets below were verified directly. The relevant packet is on PR405 head `cc0a2edb5d92ca7c92102c37173023248f011598`.

## Values read from the canonical boundary file

The WRF domain-time metadata is stored in the file as encoded variables, not as ordinary global attributes. I read only `Times`, `md___thisbdytimee_x_t_d_o_m_a_i_n_m_e_t_a_data_`, and `md___nextbdytimee_x_t_d_o_m_a_i_n_m_e_t_a_data_` from the symlink target:

`/Users/yhlee/KDM6AD-k/host/lc05_da_run/wrfbdy_d01` → `/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS/wrfbdy_d01`.

All three are `char(Time, DateStrLen)` arrays with shape `(4, 19)`:

| Record | `Times` | `md___thisbdytime…` | `md___nextbdytime…` |
|---:|---|---|---|
| 1 | 2025-07-19 00:00:00 | 2025-07-19 00:00:00 | 2025-07-19 03:00:00 |
| 2 | 2025-07-19 03:00:00 | 2025-07-19 03:00:00 | 2025-07-19 06:00:00 |
| 3 | 2025-07-19 06:00:00 | 2025-07-19 06:00:00 | 2025-07-19 09:00:00 |
| 4 | 2025-07-19 09:00:00 | 2025-07-19 09:00:00 | 2025-07-19 12:00:00 |

Thus the last `Times` value at 09:00 is the **start of the final interval**, not its end. `NEXTBDYTIME=12:00` is the final interval endpoint. Calling the file's coverage “ending at 09:00” confuses the last record start with the interval end.

## Runnable-host source interpretation

In `share/output_wrf.F:982-987`, the boundary writer sets `bdy_increment` from `NINT(config_flags%bdyfrq)`, computes `next_time = currentTime + bdy_increment`, writes `THISBDYTIME=current_date`, and writes `NEXTBDYTIME=next_datestr`. This makes the first time the current record's start label and the second its following boundary interval endpoint.

The read path in `share/input_wrf.F:1182-1193` loads those two domain-time fields into `grid%this_bdy_time` and `grid%next_bdy_time`. Restart selection accepts the half-open condition `this_bdy_time <= currentTime < next_bdy_time`; when scanning forward it advances once `currentTime >= next_bdy_time`. The later non-restart input guard at `share/input_wrf.F:1252-1268` is compiled under `DA_CORE != 1` and returns at `currentTime >= next_bdy_time` in the ordinary branch. A compiled `WRFPLUS`/`dyn_em_ad` branch uses `>` instead, so equality behavior is build/option-specific. I did not inspect build macros or assert which branch the archived executable used. The metadata endpoint is 12:00 and the restart selection interval is `[2025-07-19 09:00, 12:00)`; this does not establish usable forcing at 12:00 or later. A run may reach a terminal saved state at 12:00, but that does not extend the forcing interval.

`frame/module_io.f90` routes domain-time reads to the NetCDF backend. `external/io_netcdf/wrf_io.F90:2410-2418` appends the domain metadata suffix when retrieving `THISBDYTIME` or `NEXTBDYTIME`, matching the encoded arrays read from the file.

## Coverage conclusion

This exact July 19 boundary file advertises a final usable forcing interval ending at 12:00 under the ordinary host guard. It cannot cover a July 20 or July 21 target time. That is a file-specific limit; this review did not search for or rule out a different boundary file covering those dates.

An earlier initialization remains eligible in principle when its native valid time is correctly bound and the selected boundary file covers the target valid time. Matching dates are not a requirement by themselves. The July 19 file inspected here does not supply that later coverage. No conversion from GK2A OBT labels to UTC was inferred, and no blanket claim about all configurations or all later boundary files is made.

No forecast, boundary-array read, model run, archive-wide search, data acquisition, or new observation platform was used.
